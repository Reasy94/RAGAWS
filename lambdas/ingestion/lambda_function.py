import boto3
import logging
import json
import io
import re
import hashlib
import base64
import pdfplumber
import fitz
import time
import numpy as np
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_text_splitters import RecursiveCharacterTextSplitter

from shared.config import (
    CHUNK_SIZE, CHUNK_OVERLAP, IMAGE_MIN_SIZE, DRAWING_THRESHOLD,
    MIN_TABLE_ROWS, PAGE_FLUSH_SIZE, MAX_INPUT_CHARS, HAIKU_MODEL_ID,
    PAGE_WEIGHTS, TEXT_PAGES_NEEDED, MIN_TEXT_LENGTH,
    MAX_EMBEDDING_WORKERS, MAX_VISION_RETRIES, MAX_VISION_BASE_DELAY,
)
from shared.db import get_conn, put_conn
from shared.embeddings import get_embedding, _find_closest_domain

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(
        read_timeout=30,
        connect_timeout=10,
    ))


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 0 — ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def lambda_handler(event, context):
    batch_item_failures = []
    for record in event.get("Records", []):
        message_id = record["messageId"]
        try:
            s3_event = json.loads(record["body"])
            for s3_record in s3_event.get("Records", []):
                bucket = s3_record["s3"]["bucket"]["name"]
                key    = s3_record["s3"]["object"]["key"]
                logger.info(f"Starting ingestion for file: {key}")
                process_single_file(bucket, key)
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": batch_item_failures}


def process_single_file(bucket: str, key: str):
    s3           = boto3.client("s3")
    file_content = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    file_hash    = calculate_file_hash(file_content)
    logger.info(f"File downloaded: {len(file_content)} bytes, hash: {file_hash[:8]}...")


    if key.lower().endswith(".pdf"):
        status = _get_file_status(file_hash)
        if status == "completed":
            logger.info(f"File already completed — wiping and re-ingesting: {key}")
            _delete_file_data(file_hash)
            status = None
        if status is None:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                id_domain = get_vector_domain(pdf)
            upsert_file_record(key, file_hash, id_domain)
            last_ingested_page = 0
        else:
            logger.info(f"Resuming {key} from last ingested page")
            update_file_status(file_hash, "processing")
            last_ingested_page = _get_last_ingested_page(file_hash)

        try:
            _process_pdf(file_content, file_hash, key, last_ingested_page)
            update_file_status(file_hash, "completed")
        except Exception as e:
            update_file_status(file_hash, "failed")
            logger.error(f"PDF processing failed for {key}: {e}")
            raise


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 1 — PDF ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def _process_pdf(file_content: bytes, file_hash: str, key: str, last_ingested_page: int):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        separators    = ["\n\n", "\n", ". ", " ", ""],
    )

    total_chunks = 0
    last_caption = None

    with fitz.open(stream=file_content, filetype="pdf") as fitz_doc, \
         pdfplumber.open(io.BytesIO(file_content)) as plumber_pdf:

        total_pages = len(fitz_doc)
        logger.info(f"PDF opened: {total_pages} pages, hash: {file_hash[:8]}...")

        # ── Fase 0: analisi documento (una volta sola) ─────────────────────
        doc_meta = _analyze_document(fitz_doc, plumber_pdf)
        logger.info(f"Document: '{doc_meta['doc_name']}' | TOC entries: {len(doc_meta['toc'])}")

        # ── Fase 1: classify all pages ─────────────────────────────────────
        page_classifications = [
            _inspect_page(fitz_doc[i], fitz_doc)
            for i in range(total_pages)
        ]

        # ── Resume: trova ultima pagina già ingested ───────────────────────
        if last_ingested_page > 0:
            logger.info(f"Resuming from page {last_ingested_page + 1} (skipping {last_ingested_page} already ingested)")

        # ── Fase 2: sliding window ─────────────────────────────────────────
        for window_start in range(0, total_pages, PAGE_FLUSH_SIZE):
            window_end    = min(window_start + PAGE_FLUSH_SIZE, total_pages)

            # Salta window già completate
            if window_end <= last_ingested_page:
                logger.info(f"Skipping window {window_start+1}–{window_end} (already ingested)")
                continue

            window_pages  = list(range(window_start, window_end))
            window_infos  = page_classifications[window_start:window_end]

            logger.info(f"Processing window: pages {window_start+1}–{window_end}")

            # 2a: vision seriale
            captions = _process_vision_window(
                window_pages, window_infos, fitz_doc, plumber_pdf
            )

            # 2b + 2c: build chunks + embed
            chunks, last_caption = _build_and_embed_window(
                window_pages, window_infos,
                fitz_doc, plumber_pdf,
                doc_meta, splitter,
                captions, last_caption,
                file_hash,
            )

            # 2d: flush
            if chunks:
                save_chunks_to_rds(chunks)
                total_chunks += len(chunks)
                logger.info(f"Flushed {len(chunks)} chunks (window {window_start+1}–{window_end})")

    logger.info(f"Ingestion complete: {key} → {total_chunks} total chunks")


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 2 — DOCUMENT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def _analyze_document(fitz_doc: fitz.Document, plumber_pdf: pdfplumber.PDF) -> dict:
    """
    Estrae doc_name da Info Dictionary e TOC da Content Stream.
    Eseguito una volta sola per documento.
    """
    doc_name  = _extract_doc_name(fitz_doc)
    toc_start = _find_toc_start(plumber_pdf)
    toc       = _parse_toc(plumber_pdf, toc_start) if toc_start is not None else {}

    if not doc_name:
        logger.warning("Info Dictionary.Title vuoto — fallback al TOC")
        doc_name = next(iter(toc.values()), "Unknown Document")

    logger.info(f"doc_name='{doc_name}' | toc_start={toc_start} | toc_entries={len(toc)}")

    return {
        "doc_name":    doc_name,
        "total_pages": len(fitz_doc),
        "toc_start":   toc_start,
        "toc":         toc,
    }


def _extract_doc_name(fitz_doc: fitz.Document) -> str:
    """
    Estrae il titolo dall'Info Dictionary del PDF.
    Fonte: ISO 32000-1:2008 — PDF Info Dictionary standard.
    """
    metadata = fitz_doc.metadata or {}
    title    = metadata.get("title") or metadata.get("Title") or ""
    return title.strip()


def _find_toc_start(plumber_pdf: pdfplumber.PDF) -> int | None:
    """
    Trova la pagina dell'indice cercando il textual anchor 'Contents'.
    Fonte: Déjean & Meunier (2005) — textual anchors come marker strutturali affidabili.
    """
    for i in range(min(20, len(plumber_pdf.pages))):
        text  = plumber_pdf.pages[i].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            if line.lower() in ("contents", "table of contents"):
                logger.info(f"TOC anchor 'Contents' found at page {i+1}")
                return i
    logger.warning("TOC anchor not found in first 20 pages")
    return None


def _parse_toc(plumber_pdf: pdfplumber.PDF, toc_start_idx: int) -> dict:
    """
    Parsa il TOC usando il pattern leader dots (...)  come separatore titolo/pagina.
    Pattern: "Latin America and the Caribbean ... 69"
    Fonte: Déjean & Meunier (2005) — pattern-based TOC extraction.
    """
    EXCLUDE_TOC_PREFIXES = re.compile(
    r'^(\d+\.\d+|B\d+\.\d+|A\d+\.\d+)',
    re.IGNORECASE
    )
    toc = {}
    for i in range(toc_start_idx, min(toc_start_idx + 5, len(plumber_pdf.pages))):
        text  = plumber_pdf.pages[i].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            if line.lower() in ("contents", "table of contents"):
                continue
            match = re.match(r'^(.+?)\s*\.{2,}\s*(\d+)\s*$', line)
            if match:
                title    = match.group(1).strip()
                page_num = int(match.group(2))
                if EXCLUDE_TOC_PREFIXES.match(title):
                    continue
                if len(title) > 5 and not title.isdigit():
                    toc[page_num] = title
    return toc


def _get_section_for_page(page_num: int, toc: dict) -> str:
    """
    Lookup O(1) della sezione per numero pagina.
    Ritorna il titolo dell'ultima sezione iniziata prima o alla pagina corrente.
    """
    current_section = ""
    for p in sorted(toc.keys()):
        if p <= page_num:
            current_section = toc[p]
        else:
            break
    return current_section


def _build_context_header(doc_meta: dict, page_num: int) -> str:
    """
    Costruisce il context header per ogni chunk.
    Formato: [doc_name | section]
    Fonte: Anthropic (2024) Contextual Retrieval — riduzione failure rate fino al 67%.
    """
    section = _get_section_for_page(page_num, doc_meta["toc"])
    if section:
        return f"[{doc_meta['doc_name']} | {section}]"
    return f"[{doc_meta['doc_name']}]"


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 2 — PAGE INSPECTION
# ══════════════════════════════════════════════════════════════════════════════

def _has_table_heuristic(fitz_page) -> bool:
    drawings = fitz_page.get_drawings()
    h_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].height < 2]
    v_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].width  < 2]
    return len(h_lines) > 3 and len(v_lines) > 3


def _inspect_page(fitz_page, fitz_doc) -> dict:
    has_text  = bool(fitz_page.get_text().strip())
    images    = fitz_page.get_images(full=True)
    has_image = any(
        fitz_doc.extract_image(img[0]).get("width", 0) > IMAGE_MIN_SIZE
        for img in images
    ) if images else False
    has_vector = len(fitz_page.get_drawings()) > DRAWING_THRESHOLD
    has_table  = _has_table_heuristic(fitz_page)
    return {
        "has_text":   has_text,
        "has_image":  has_image,
        "has_vector": has_vector,
        "has_table":  has_table,
        "images":     images,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 3 — VISION WINDOW (parallelo)
# ══════════════════════════════════════════════════════════════════════════════

def _process_vision_window(
    window_pages: list[int],
    window_infos: list[dict],
    fitz_doc,
    plumber_pdf,
) -> dict:
    captions = {}

    for idx, page_idx in enumerate(window_pages):
        page_num  = page_idx + 1
        page_info = window_infos[idx]
        fitz_page = fitz_doc[page_idx]

        try:
            if page_info["has_vector"]:
                caption = _dispatch_vision_task(page_num, "vector_graphic", fitz_page, None, None)
            elif page_info["has_image"] and not page_info["has_text"]:
                caption = _dispatch_vision_task(page_num, "pure_image", fitz_page, fitz_doc, None)
            elif page_info["has_image"] and page_info["has_text"]:
                plumber_page = plumber_pdf.pages[page_idx]
                context_text = (plumber_page.extract_text() or "")[:1000]
                caption = _dispatch_vision_task(page_num, "mixed_image", fitz_page, fitz_doc, context_text)
            else:
                continue

            if caption:
                captions[page_num] = caption

        except Exception as e:
            logger.error(f"Vision error on page {page_num}: {e}")

    return captions


def _dispatch_vision_task(
    page_num: int,
    task_type: str,
    fitz_page,
    fitz_doc,
    context_text: str | None,
) -> str | None:
    if task_type == "vector_graphic":
        return _process_vector_graphic_page(page_num, fitz_page)
    elif task_type == "pure_image":
        return _process_pure_image_page(page_num, fitz_page, fitz_doc)
    elif task_type == "mixed_image":
        return _process_mixed_image_page(page_num, fitz_page, fitz_doc, context_text)
    return None


def _process_vector_graphic_page(page_num: int, fitz_page) -> str | None:
    """
    Pagina con grafico vettoriale → jpeg intera pagina → Haiku.
    NO page_text: pdfplumber legge i caratteri del grafico vettoriale come spazzatura.
    """
    logger.info(f"Page {page_num}: VECTOR_GRAPHIC → Haiku Vision")
    page_jpeg_b64 = _page_to_jpeg_base64(fitz_page)
    return _call_haiku_vision(page_jpeg_b64, media_type="image/jpeg")


def _process_pure_image_page(page_num: int, fitz_page, fitz_doc) -> str | None:
    """
    Pagina con immagine embedded senza testo → extract image → Haiku.
    """
    logger.info(f"Page {page_num}: pure IMAGE → Haiku Vision")
    for img in fitz_page.get_images(full=True):
        xref = img[0]
        info = fitz_doc.extract_image(xref)
        w, h = info.get("width", 0), info.get("height", 0)
        if w <= IMAGE_MIN_SIZE or h <= IMAGE_MIN_SIZE:
            continue
        ext        = info.get("ext", "png")
        media_type = f"image/{ext}" if ext in ("png", "jpeg", "gif", "webp") else "image/png"
        img_b64    = _image_bytes_to_base64(info["image"])
        return _call_haiku_vision(img_b64, media_type=media_type)
    return None


def _process_mixed_image_page(
    page_num: int, fitz_page, fitz_doc, context_text: str
) -> str | None:
    """
    Pagina con immagine embedded + testo → extract image → Haiku con context_text.
    """
    logger.info(f"Page {page_num}: mixed IMAGE+TEXT → Haiku Vision with context")
    for img in fitz_page.get_images(full=True):
        xref = img[0]
        info = fitz_doc.extract_image(xref)
        w, h = info.get("width", 0), info.get("height", 0)
        if w <= IMAGE_MIN_SIZE or h <= IMAGE_MIN_SIZE:
            continue
        ext        = info.get("ext", "png")
        media_type = f"image/{ext}" if ext in ("png", "jpeg", "gif", "webp") else "image/png"
        img_b64    = _image_bytes_to_base64(info["image"])
        return _call_haiku_vision(img_b64, media_type=media_type, context_text=context_text)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 3 — CHUNK BUILDING + EMBEDDING WINDOW
# ══════════════════════════════════════════════════════════════════════════════

def _build_and_embed_window(
    window_pages: list[int],
    window_infos: list[dict],
    fitz_doc,
    plumber_pdf,
    doc_meta: dict,
    splitter,
    captions: dict,
    last_caption: str | None,
    file_hash: str,
) -> tuple[list[dict], str | None]:
    """
    2b: build chunks sequenziale (per caption chaining)
    2c: embedding parallelo
    Ritorna (chunks_con_embedding, last_caption_aggiornato)
    """
    raw_chunks = []

    for idx, page_idx in enumerate(window_pages):
        page_num  = page_idx + 1
        page_info = window_infos[idx]
        printed_page = int(fitz_doc[page_idx].get_label() or 0)
        header    = _build_context_header(doc_meta, printed_page) 

        # ── Vision chunks ──────────────────────────────────────────────────
        if page_info["has_vector"]:
            caption = captions.get(page_num)
            if caption:
                raw_chunks.append(_make_raw_chunk(
                    file_hash, page_num,
                    chunk_id   = 1,
                    chunk_type = "VECTOR_GRAPHIC",
                    content    = f"{header}\n{caption}",
                ))
                last_caption = caption
            continue

        if page_info["has_image"] and not page_info["has_text"]:
            caption = captions.get(page_num)
            if caption:
                raw_chunks.append(_make_raw_chunk(
                    file_hash, page_num,
                    chunk_id   = 1,
                    chunk_type = "IMAGE",
                    content    = f"{header}\n{caption}",
                ))
                last_caption = caption
            continue

        if page_info["has_image"] and page_info["has_text"]:
            caption = captions.get(page_num)
            if caption:
                raw_chunks.append(_make_raw_chunk(
                    file_hash, page_num,
                    chunk_id   = 1,
                    chunk_type = "IMAGE",
                    content    = f"{header}\n{caption}",
                ))
                last_caption = caption

        # ── Text + Table chunks ────────────────────────────────────────────
        if page_info["has_text"]:
            plumber_page  = plumber_pdf.pages[page_idx]
            table_chunks  = _build_table_chunks(page_num, plumber_page, header, file_hash)
            raw_chunks.extend(table_chunks)

            text_chunks, last_caption = _build_text_chunks(
                page_num, plumber_page, header,
                splitter, last_caption,
                file_hash, len(table_chunks),
            )
            raw_chunks.extend(text_chunks)

    # 2c: embedding parallelo
    chunks_with_embeddings = _embed_chunks_parallel(raw_chunks)
    return chunks_with_embeddings, last_caption


def _build_table_chunks(
    page_num: int,
    plumber_page,
    header: str,
    file_hash: str,
) -> list[dict]:
    """
    Estrae tabelle dalla pagina — ogni tabella è un chunk atomico (no overlap).
    Fonte: principio di unità atomica per dati strutturati.
    """
    chunks = []
    tables = plumber_page.find_tables()

    for table_idx, table in enumerate(tables):
        extracted = table.extract()
        if not extracted:
            continue
        table_header = extracted[0]
        rows = []
        for row in extracted[1:]:
            pairs = []
            for h, cell in zip(table_header, row):
                h_clean    = str(h).strip()    if h    else "?"
                cell_clean = str(cell).strip() if cell else ""
                if h_clean and cell_clean:
                    pairs.append(f"{h_clean}: {cell_clean}")
            if pairs:
                rows.append(" | ".join(pairs))

        if rows and len(rows) >= MIN_TABLE_ROWS:
            chunks.append(_make_raw_chunk(
                file_hash, page_num,
                chunk_id   = table_idx + 1,
                chunk_type = "TABLE",
                content    = f"{header}\n" + "\n".join(rows),
            ))

    return chunks


def _build_text_chunks(
    page_num: int,
    plumber_page,
    header: str,
    splitter,
    last_caption: str | None,
    file_hash: str,
    chunk_id_offset: int,
) -> tuple[list[dict], str | None]:
    """
    Estrae testo dalla pagina escludendo le bbox delle tabelle.
    Applica caption chaining sul primo chunk se last_caption è presente.
    Overlap: 100 token tramite RecursiveCharacterTextSplitter.
    """
    chunks       = []
    tables       = plumber_page.find_tables()
    table_bboxes = [t.bbox for t in tables]

    if table_bboxes:
        filtered  = plumber_page.filter(
            lambda obj: not any(
                obj["x0"] >= bbox[0] and obj["top"]    >= bbox[1] and
                obj["x1"] <= bbox[2] and obj["bottom"] <= bbox[3]
                for bbox in table_bboxes
            )
        )
        page_text = filtered.extract_text()
    else:
        page_text = plumber_page.extract_text()

    if not page_text or not page_text.strip():
        return chunks, None

    first_chunk = True
    page_text_clean = page_text.strip()
    text_chunks     = (
        [page_text_clean]
        if len(page_text_clean) <= CHUNK_SIZE
        else splitter.split_text(page_text_clean))
    for idx, chunk_text in enumerate(text_chunks):
        # Caption chaining: prepend last_caption al primo chunk TEXT
        if first_chunk and last_caption:
            truncated    = _truncate_at_sentence(last_caption, CHUNK_OVERLAP)
            chunk_text   = f"[Figura: {truncated}]\n\n{chunk_text}"
            first_chunk  = False

        chunks.append(_make_raw_chunk(
            file_hash, page_num,
            chunk_id   = chunk_id_offset + idx + 1,
            chunk_type = "TEXT",
            content    = f"{header}\n{chunk_text}",
        ))

    return chunks, None  # last_caption reset dopo uso


# ══════════════════════════════════════════════════════════════════════════════
# LEVEL 4 — EMBEDDING (parallelo)
# ══════════════════════════════════════════════════════════════════════════════

def _embed_chunks_parallel(raw_chunks: list[dict]) -> list[dict]:
    """
    Calcola embedding in parallelo su tutti i chunk della window.
    Fonte: Titan embed-text-v2 via Bedrock.
    """
    if not raw_chunks:
        return []

    results = [None] * len(raw_chunks)

    def _embed_one(idx: int, chunk: dict) -> tuple[int, dict]:
        raw_embedding = get_embedding(chunk["content"][:MAX_INPUT_CHARS])
        chunk["vector"] = np.array(raw_embedding).tolist()
        return idx, chunk

    with ThreadPoolExecutor(max_workers=MAX_EMBEDDING_WORKERS) as executor:
        futures = {
            executor.submit(_embed_one, i, chunk): i
            for i, chunk in enumerate(raw_chunks)
        }
        for future in as_completed(futures):
            try:
                idx, chunk = future.result()
                results[idx] = chunk
            except Exception as e:
                logger.error(f"Embedding error: {e}")

    return [c for c in results if c is not None]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _make_raw_chunk(
    file_hash: str, page_num: int,
    chunk_id: int, chunk_type: str, content: str
) -> dict:
    """Crea chunk senza embedding — l'embedding viene aggiunto in _embed_chunks_parallel."""
    return {
        "file_hash":  file_hash,
        "page_num":   page_num,
        "chunk_id":   chunk_id,
        "chunk_type": chunk_type,
        "content":    content,
        "vector":     None,
    }


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut         = text[:max_chars]
    last_period = cut.rfind(". ")
    return cut[:last_period + 1] if last_period > 0 else cut


def calculate_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _page_to_jpeg_base64(fitz_page) -> str:
    pix = fitz_page.get_pixmap(dpi=120)
    return base64.standard_b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode("utf-8")


def _image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def _call_haiku_vision(
    image_b64: str,
    media_type: str = "image/jpeg",
    context_text: str = "",
) -> str:
    user_content = []

    if context_text:
        user_content.append({
            "type": "text",
            "text": (
                "You are analyzing a visual element from a document. "
                "Your description will be indexed in a RAG system and retrieved via semantic search. "
                "Here is the text extracted from the same page:\n\n"
                f"{context_text}\n\n"
                "Use this text as context to better understand the visual element. "
                "Describe what you see in detail: the main topic, key data points, "
                "entities mentioned, time periods if present, and the main insight or message conveyed. "
                "Be specific and include all visible numbers and labels. Avoid vague language."
            )
        })
    else:
        user_content.append({
            "type": "text",
            "text": (
                "You are analyzing a visual element from a document "
                "Your description will be indexed in a RAG system and retrieved via semantic search. "
                "Describe what you see in detail: the main topic, key data points, "
                "entities mentioned (countries, regions, indicators), time periods if present, and the main insight or message conveyed. "
                "Be specific and include all visible numbers and labels. Avoid vague language."
            )
        })

    user_content.append({
        "type": "image",
        "source": {
            "type":       "base64",
            "media_type": media_type,
            "data":       image_b64,
        }
    })

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        1024,
        "messages": [{"role": "user", "content": user_content}],
    })

    for attempt in range(MAX_VISION_RETRIES):
        try:
            response = bedrock.invoke_model_with_response_stream(
                modelId     = HAIKU_MODEL_ID,
                contentType = "application/json",
                accept      = "application/json",
                body        = body,
            )
            full_text = ""
            for event in response["body"]:
                chunk = json.loads(event["chunk"]["bytes"])
                if chunk.get("type") == "content_block_delta":
                    full_text += chunk["delta"].get("text", "")
            return full_text.strip()

        except Exception as e:
            if "ThrottlingException" not in str(e):
                raise
            if attempt == MAX_VISION_RETRIES - 1:
                raise
            delay = MAX_VISION_BASE_DELAY * (2 ** attempt)
            logger.warning(f"Haiku throttled (attempt {attempt+1}/{MAX_VISION_RETRIES}), retry in {delay}s...")
            time.sleep(delay)

# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def get_vector_domain(pdf: pdfplumber.PDF) -> int | None:
    text_pages = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        if len(text.strip()) >= MIN_TEXT_LENGTH:
            text_pages.append(text)
        if len(text_pages) == TEXT_PAGES_NEEDED:
            break

    if not text_pages:
        logger.warning("No text-based pages found for domain detection")
        return None

    weights = PAGE_WEIGHTS[:len(text_pages)]
    total   = sum(weights)
    weights = [w / total for w in weights]

    embeddings = [get_embedding(t[:MAX_INPUT_CHARS]) for t in text_pages]
    centroid   = (v := np.dot(weights, embeddings)) / np.linalg.norm(v)
    domain_id  = _find_closest_domain(centroid)
    logger.info(f"Domain detected: id={domain_id}")
    return domain_id


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def upsert_file_record(file_name: str, file_hash: str, id_domain: int | None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fileIngested (file_hash, file_name, id_domain, embedding_model, ingested_from, status)
            VALUES (%s, %s, %s, %s, %s, 'processing')
            ON CONFLICT (file_hash) DO UPDATE SET
                ingested_at = CURRENT_TIMESTAMP,
                status      = 'processing',
                id_domain   = EXCLUDED.id_domain
        """, (file_hash, file_name, id_domain, "amazon.titan-embed-text-v2:0", "S3_Lambda_Processor"))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error upserting file record: {e}")
        raise
    finally:
        put_conn(conn)


def update_file_status(file_hash: str, status: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE fileIngested SET status = %s WHERE file_hash = %s",
            (status, file_hash)
        )
        conn.commit()
        logger.info(f"File status → '{status}' for hash {file_hash[:8]}...")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error updating file status: {e}")
    finally:
        put_conn(conn)


def save_chunks_to_rds(chunks: list[dict]):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO chunks (file_hash, page_number, chunk_id, chunk_type, content, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_hash, page_number, chunk_id)
            DO UPDATE SET
                chunk_type = EXCLUDED.chunk_type,
                content    = EXCLUDED.content,
                embedding  = EXCLUDED.embedding
        """, [
            (c["file_hash"], c["page_num"], c["chunk_id"],
             c["chunk_type"], c["content"], c["vector"])
            for c in chunks
        ])
        conn.commit()
        logger.info(f"Saved {len(chunks)} chunks to RDS.")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error saving chunks: {e}")
        raise
    finally:
        put_conn(conn)


def _get_last_ingested_page(file_hash: str) -> int:
    """
    Ritorna l'ultima pagina già ingested per questo file_hash.
    Usato per il resume mechanism in caso di Lambda timeout.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(page_number), 0) FROM chunks WHERE file_hash = %s",
            (file_hash,)
        )
        return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"DB error getting last ingested page: {e}")
        return 0
    finally:
        put_conn(conn)


def _get_file_status(file_hash: str) -> str | None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT status FROM fileIngested WHERE file_hash = %s", (file_hash,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        put_conn(conn)


def _delete_file_data(file_hash: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM chunks WHERE file_hash = %s", (file_hash,))
        cur.execute("DELETE FROM fileIngested WHERE file_hash = %s", (file_hash,))
        conn.commit()
        logger.info(f"Deleted all data for hash {file_hash[:8]}...")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error deleting file data: {e}")
        raise
    finally:
        put_conn(conn)