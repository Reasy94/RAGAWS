"""
aggregato.py
-------------------
Lambda di ingestion PDF con pdf_splitter integrato.

Modifiche rispetto alla versione precedente:
  - Rimossa pipeline vision basata su _inspect_page() / has_vector / has_image
  - Integrato process_page() da pdf_splitter.py
  - FIGURE/TABLE → PNG croppato + ctx_before/ctx_after → Haiku Vision → chunk atomico
  - TEXT → _build_context_header() + splitter.split_text() + embedding
  - Tutte le funzioni geometriche adattate per bytes invece di path
  
Integrazione da debug_splitter.py (try2):
  - TABLE → sempre figure_side="full" (non si taglia mai)
  - FIGURE → logica empirica migliorata con gutter 25pt e check colonna opposta
  - split_by_columns usa mid (center page) come crop point, non blk["x0"]
"""

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
import os
import threading
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_text_splitters import RecursiveCharacterTextSplitter
import gc

from shared.config import (
    CHUNK_SIZE, CHUNK_OVERLAP, PAGE_FLUSH_SIZE,
    MAX_INPUT_CHARS, HAIKU_MODEL_ID,
    PAGE_WEIGHTS, TEXT_PAGES_NEEDED, MIN_TEXT_LENGTH,
    MAX_EMBEDDING_WORKERS, MAX_VISION_RETRIES, MAX_VISION_BASE_DELAY,
    NOVA_PRO_MODEL_ID, BUCKET_NAME, COHERE_MODEL_ID, INGESTION_SOURCE
)
from shared.db import get_conn, put_conn
from shared.embeddings import get_embedding, find_closest_domain

_EXCLUDE_SECTION_TYPES = re.compile(
    r'^(text tables?|list of tables?|appendix|appendixes|cover|contents|preface|'
    r'figure|fig\.|table|tbl\.|annex|annexes|box|boxes|references|bibliography|'
    r'selected topics|statistical appendix|abbreviations|acknowledgments?|foreword|'
    r'glossary|data and conventions|assumptions and conventions|further information|'
    r'country abbreviations|heading)\b',
    re.IGNORECASE
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(read_timeout=30, connect_timeout=10),
)
s3 = boto3.client("s3")

# ── Regex patterns ────────────────────────────────────────────────────────────
#ORPHAN_TOKEN   = re.compile(r'(?<!\w)[A-Z]{1,2}(?!\w)')
ORPHAN_TOKEN = re.compile(r'(?<![.\w])[A-Z](?![.\w])')
BLOCK_KEYWORDS = re.compile(r'^(FIGURE|TABLE)$', re.IGNORECASE)


# ==============================================================================
# LEVEL 0 — ENTRY POINT
# ==============================================================================


def _extend_visibility(sqs_client, queue_url, receipt_handle, stop_event):
    """Estende la visibility del messaggio SQS ogni 5 minuti."""
    while not stop_event.wait(300):
        try:
            sqs_client.change_message_visibility(
                QueueUrl          = queue_url,
                ReceiptHandle     = receipt_handle,
                VisibilityTimeout = 600
            )
            logger.info("SQS visibility extended")
        except Exception as e:
            logger.warning(f"Failed to extend SQS visibility: {e}")


def lambda_handler(event, context):
    batch_item_failures = []
    sqs       = boto3.client("sqs")
    queue_url = os.environ["SQS_QUEUE_URL"]

    for record in event.get("Records", []):
        message_id     = record["messageId"]
        receipt_handle = record["receiptHandle"]

        stop_event = threading.Event()
        heartbeat  = threading.Thread(
            target = _extend_visibility,
            args   = (sqs, queue_url, receipt_handle, stop_event),
            daemon = True,
        )
        heartbeat.start()

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
        finally:
            stop_event.set()
            heartbeat.join()

    return {"batchItemFailures": batch_item_failures}

def process_single_file(bucket: str, key: str):
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
            toc = offset = last_content_page = None
        else:
            logger.info(f"Resuming {key} from last ingested page")
            update_file_status(file_hash, "processing")
            last_ingested_page, toc, offset, last_content_page = _get_resume_data(file_hash)

        try:
            _process_pdf(file_content, file_hash, key, last_ingested_page, toc, offset, last_content_page)
            update_file_status(file_hash, "completed")
            delete_toc_cache(file_hash)
        except Exception as e:
            update_file_status(file_hash, "failed")
            logger.error(f"PDF processing failed for {key}: {e}")
            raise


# ==============================================================================
# LEVEL 1 — PDF ORCHESTRATION
# ==============================================================================

def _process_pdf(
    file_content: bytes,
    file_hash: str,
    key: str,
    last_ingested_page: int,
    toc: list | None = None,
    offset: int | None = None,
    last_content_page: int | None = None,
):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        separators    = ["\n\n", "\n", ". ", " ", ""],
    )

    total_chunks = 0

    with fitz.open(stream=file_content, filetype="pdf") as fitz_doc, \
         pdfplumber.open(io.BytesIO(file_content)) as plumber_pdf:

        total_pages = len(fitz_doc)
        logger.info(f"PDF opened: {total_pages} pages, hash: {file_hash[:8]}...")

        # ── Fase 0: Document analysis ──────────────────────────────────────
        if toc is None or offset is None:
            doc_meta = _analyze_document(fitz_doc, plumber_pdf, file_hash)
        else:
            logger.info("Resume: TOC and offset loaded from cache")
            doc_meta = {
                "doc_name":    _extract_doc_name(fitz_doc),
                "total_pages": total_pages,
                "toc":         toc,
                "offset":      offset,
                "last_content_page": last_content_page,
            }

        logger.info(f"Document: '{doc_meta['doc_name']}' | TOC entries: {len(doc_meta['toc'])}")

        if last_ingested_page > 0:
            logger.info(f"Resuming from page {last_ingested_page + 1}")

        # ── Fase 1: sliding window ─────────────────────────────────────────
        for window_start in range(0, total_pages, PAGE_FLUSH_SIZE):
            window_end = min(window_start + PAGE_FLUSH_SIZE, total_pages)

            if window_end <= last_ingested_page:
                logger.info(f"Skipping window {window_start+1}–{window_end} (already ingested)")
                continue

            window_pages = [p for p in range(window_start, window_end) if p < doc_meta["last_content_page"]]
            if not window_pages:
                logger.info(f"All pages past last content page — stopping ingestion")
                break

            logger.info(f"Processing window: pages {window_start+1}–{window_end}")

            chunks = _build_and_embed_window(
                window_pages, fitz_doc, plumber_pdf,
                file_content, doc_meta, splitter, file_hash,
            )

            if chunks:
                save_chunks_to_rds(chunks)
                total_chunks += len(chunks)
                logger.info(f"Flushed {len(chunks)} chunks (window {window_start+1}–{window_end})")

    logger.info(f"Ingestion complete: {key} → {total_chunks} total chunks")


# ==============================================================================
# LEVEL 2 — DOCUMENT ANALYSIS
# ==============================================================================

def _analyze_document(
    fitz_doc: fitz.Document,
    plumber_pdf: pdfplumber.PDF,
    file_hash: str,
) -> dict:
    doc_name = _extract_doc_name(fitz_doc)
    toc, toc_strategy, toc_end = _build_hierarchical_toc(fitz_doc, plumber_pdf)
    offset = _calculate_page_offset(plumber_pdf, toc, toc_end)
    last_content_page = _find_last_content_page(plumber_pdf, toc, offset)
    save_toc_cache(file_hash, toc, offset, last_content_page)
    logger.info(f"strategy={toc_strategy} | toc_entries={len(toc)} | offset={offset}")

    if not doc_name:
        logger.warning("Info Dictionary.Title empty — TOC fallback")
        first    = toc[0] if toc else None
        doc_name = first["title"] if first else "Unknown Document"


    return {
        "doc_name":    doc_name,
        "total_pages": len(fitz_doc),
        "toc":         toc,
        "offset":      offset,
        "last_content_page": last_content_page,
    }


def _extract_doc_name(fitz_doc: fitz.Document) -> str:
    metadata = fitz_doc.metadata or {}
    title    = metadata.get("title") or metadata.get("Title") or ""
    return title.strip()


def _find_toc_start(plumber_pdf: pdfplumber.PDF) -> int | None:
    for i in range(min(50, len(plumber_pdf.pages))):
        text  = plumber_pdf.pages[i].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            if line.lower() in ("contents", "table of contents"):
                logger.info(f"TOC anchor found at page {i+1}")
                return i
    logger.warning("TOC anchor not found")
    return None


def _find_toc_end(plumber_pdf: pdfplumber.PDF, toc_start: int) -> int:
    END_WITH_NUMBER = re.compile(r'^.+\s+(\d+)\s*$')
    last_toc_page = toc_start
    last_page_num = 0
    stop          = False

    for i in range(toc_start, min(toc_start + 10, len(plumber_pdf.pages))):
        if stop:
            break
        text  = plumber_pdf.pages[i].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            m = END_WITH_NUMBER.match(line)
            if not m:
                continue
            page_num = int(m.group(1))
            if last_page_num > 0 and page_num < last_page_num:
                stop = True
                break
            last_page_num = page_num
            last_toc_page = i

    logger.info(f"TOC end detected at page {last_toc_page + 1}")
    return last_toc_page


def _extract_toc_with_llm(
    plumber_pdf: pdfplumber.PDF,
    toc_start: int,
    toc_end: int,
) -> list:
    END_WITH_NUMBER = re.compile(r'^(.+?)[\s\.]+\s*(\d+)\s*$')
    toc_text      = ""
    stop_global   = False
    last_page_num = 0

    for i in range(toc_start, toc_end + 1):
        if stop_global:
            break
        text  = plumber_pdf.pages[i].extract_text() or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        page_content = []
        for line in lines:
            m = END_WITH_NUMBER.match(line)
            if m:
                current_num = int(m.group(2))
                if last_page_num > 0 and current_num < last_page_num:
                    stop_global = True
                    break
                last_page_num = current_num
            page_content.append(line)
        toc_text += f"\n--- page {i+1} ---\n" + "\n".join(page_content)

    if not toc_text.strip():
        logger.warning("TOC text empty — returning empty list")
        return []

    prompt = (
        "This is the table of contents of a document.\n\n"
        f"{toc_text}\n\n"
        "Extract ONLY the navigable content sections — chapters and subsections.\n"
        "Ignore everything that is not content navigation: List of Tables, List of Figures, "
        "Boxes, Annexes, Appendixes, Glossary, Abbreviations.\n"
        "Preserve the exact order in which entries appear in the TOC — do not reorder.\n"
        "If a line starts with 'Chapter N' and that chapter number has already been defined earlier in the TOC, "
        "it is a page continuation header — ignore it and assign its subsections to the already-defined chapter.\n"
        "For each entry return the physical page number as it appears in the TOC, "
        "the section title, and its parent section (null if top-level chapter).\n"
        "Return ONLY a valid JSON array, no other text:\n"
        '[{"page": 14, "chapter": "Introduction", "parent_chapter": "Chapter 1 Global Outlook"}, ...]'
    )

    body = json.dumps({
        "messages": [
            {"role": "user",      "content": [{"text": prompt}]},
            {"role": "assistant", "content": [{"text": "["}]},
        ],
        "inferenceConfig": {"max_new_tokens": 8192},
    })
    
    try:
        response = bedrock.invoke_model(
            modelId     = NOVA_PRO_MODEL_ID,
            contentType = "application/json",
            accept      = "application/json",
            body        = body,
        )
        raw  = json.loads(response["body"].read())
        text = raw["output"]["message"]["content"][0]["text"].strip()
        entries = json.loads("[" + text)
        toc = []
        for entry in entries:
            page   = entry.get("page")
            chapter = (entry.get("chapter") or "").strip()
            parent  = (entry.get("parent_chapter") or "").strip() or None
            if page and chapter:
                toc.append({"page": int(page), "title": chapter, "parent": parent})
        logger.info(f"LLM TOC extraction: {len(toc)} entries")
        return toc
    except json.JSONDecodeError as e:
        logger.error(f"TOC JSON parse error: {e}")
        return []
    except Exception as e:
        logger.error(f"TOC LLM extraction failed: {e}")
        return []


def _build_hierarchical_toc(
    fitz_doc: fitz.Document,
    plumber_pdf: pdfplumber.PDF,
) -> tuple[list, str, int]:
    toc_start = _find_toc_start(plumber_pdf)

    if toc_start is not None:
        toc_end = _find_toc_end(plumber_pdf, toc_start)
        toc     = _extract_toc_with_llm(plumber_pdf, toc_start, toc_end)
        if toc:
            return toc, "llm_extraction", toc_end

    logger.warning("LLM TOC extraction failed — fitz flat fallback")
    raw = fitz_doc.get_toc()
    toc = []
    for _, title, page in raw:
        if not _EXCLUDE_SECTION_TYPES.match(title.strip()):
            toc.append({"page": page, "title": title.strip(), "parent": None})
    return toc, "fitz_flat_fallback", 0


def _get_section_for_page(page_num: int, toc: list, offset: int) -> str:
    stamp         = page_num - offset
    current_entry = None
    for entry in toc:
        if entry["page"] <= stamp:
            current_entry = entry
        else:
            break
    if not current_entry:
        return ""

    parts   = [current_entry["title"]]
    parent  = current_entry["parent"]
    visited = set()
    while parent and parent not in visited:
        visited.add(parent)
        parent_entry = next((e for e in toc if e["title"] == parent), None)
        parts.insert(0, parent)
        if parent_entry:
            parent = parent_entry["parent"]
        else:
            break

    return " | ".join(parts)


def _build_context_header(doc_meta: dict, page_num: int) -> str:
    """
    Costruisce il context header per ogni chunk.
    Formato: [doc_name | section]
    Fonte: Anthropic (2024) Contextual Retrieval.
    """
    section = _get_section_for_page(page_num, doc_meta["toc"], doc_meta["offset"])
    if section:
        return f"[{doc_meta['doc_name']} | {section}]"
    return f"[{doc_meta['doc_name']}]"


HEADER_NUMBER = re.compile(r'^\s*(\d+)\s+\S')

def _calculate_page_offset(
    plumber_pdf: pdfplumber.PDF,
    toc: list,
    toc_end: int,
) -> int:
    if not toc:
        logger.warning("TOC empty — offset=0")
        return 0

    for page_idx in range(toc_end, len(plumber_pdf.pages)):
        text  = plumber_pdf.pages[page_idx].extract_text() or ""
        lines = [l for l in text.split("\n") if l.strip()]
        if not lines:
            continue

        m = HEADER_NUMBER.match(lines[0].strip())
        if not m:
            continue

        found_num = int(m.group(1))
        offset    = (page_idx + 1) - found_num
        logger.info(f"Page offset={offset} (fisica={page_idx+1}, stampata={found_num})")
        return offset

    logger.warning("Numeric header not found — offset=0")
    return 0


# ==============================================================================
# LEVEL 2 — PDF SPLITTER FUNCTIONS (adattate per bytes)
# ==============================================================================

def _is_bold_font(fontname: str) -> bool:
    base = fontname.split("+")[-1]
    return "Bold" in base or "bold" in base


def _clean_orphans(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        cleaned = ORPHAN_TOKEN.sub("", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)

def _find_last_content_page(plumber_pdf, toc, offset):
    if not toc:
        logger.info("_find_last_content_page: empty TOC — returning len(pages)")
        return len(plumber_pdf.pages)
    
    # Pagina fisica dell'ultima entry TOC
    last_toc_entry = toc[-1]
    last_toc_physical = last_toc_entry["page"] + offset
    logger.info(f"_find_last_content_page: last entry='{last_toc_entry['title']}' page={last_toc_entry['page']} offset={offset} → fisica={last_toc_physical}")
    # Scannerizziamo in avanti dall'ultima entry TOC
    # Cerchiamo una pagina vuota che segna la fine del contenuto
    for page_idx in range(last_toc_physical, len(plumber_pdf.pages)):
        text = plumber_pdf.pages[page_idx].extract_text() or ""
        chars = len(text.strip())
        logger.info(f"_find_last_content_page: page {page_idx+1} → {chars} chars")
        if chars < 50:
            logger.info(f"_find_last_content_page: STOP at page {page_idx}")
            return page_idx
    logger.info(f"_find_last_content_page: no blank page found — returning {len(plumber_pdf.pages)}")
    return len(plumber_pdf.pages)


def _find_content_blocks(plumber_pdf: pdfplumber.PDF, page_idx: int) -> list[dict]:
    """
    Trova i titoli di FIGURE e TABLE via font bold.
    
    Logica da debug_splitter.py (try2):
      - TABLE → sempre figure_side="full" (non si taglia mai una tabella)
      - FIGURE → full se titolo centrale, o se colonna opposta vuota;
                 left/right solo se c'è testo nella colonna opposta
      - Gutter: 25pt (area di rispetto centrale)
    """
    results = []
    page    = plumber_pdf.pages[page_idx]
    width   = page.width
    height  = page.height
    words   = sorted(
        page.extract_words(extra_attrs=["fontname", "size"]),
        key=lambda w: (round(w["top"]), w["x0"])
    )

    i = 0
    while i < len(words):
        cur = words[i]
        matched_type = matched_x0 = matched_top = matched_font = None
        advance = 1

        # Strategy 1: "FIGURE 1.1" or "TABLE 1.1" (bold keyword + number)
        if BLOCK_KEYWORDS.match(cur["text"]) and _is_bold_font(cur["fontname"]):
            if i + 1 < len(words) and re.match(r'^[\dA-Z][\d\.]*$', words[i+1]["text"]):
                matched_type = cur["text"].upper()
                matched_x0   = cur["x0"]
                matched_top  = cur["top"]
                matched_font = cur["fontname"]

        # Strategy 2: "F" + "IGURE" (kerned) + number
        elif (cur["text"] == "F"
              and _is_bold_font(cur["fontname"])
              and i + 1 < len(words)
              and words[i+1]["text"] == "IGURE"
              and abs(cur["top"] - words[i+1]["top"]) < 5):
            if i + 2 < len(words) and re.match(r'^[\dA-Z][\d\.]*$', words[i+2]["text"]):
                matched_type = "FIGURE"
                matched_x0   = cur["x0"]
                matched_top  = cur["top"]
                matched_font = cur["fontname"]
                advance      = 2

        if matched_type:
            mid    = width / 2
            margin = 15

            if matched_type == "TABLE":
                figure_side = "full"
            else:
                # Check empirico: controlliamo sempre la colonna opposta
                if matched_x0 < mid:
                    check_area = (mid + margin, matched_top - 2, width, matched_top + 10)
                else:
                    check_area = (0, matched_top - 2, mid - margin, matched_top + 10)

                neighbor_txt = page.crop(check_area).extract_text() or ""

                if not neighbor_txt.strip():
                    figure_side = "full"
                else:
                    figure_side = "right" if matched_x0 > (mid - 2) else "left"

            results.append({
                "type":        matched_type,
                "x0":          matched_x0,
                "top":         matched_top,
                "figure_side": figure_side,
                "page_width":  width,
                "page_height": height,
            })

        i += advance

    return results


def split_simple_two_columns(page):
    """Estrae il testo da una pagina standard dividendolo in due colonne geometriche."""
    results = []
    width, height = page.width, page.height
    margin_left = 2
    margin_right = 2
    mid = width / 2
    # Margini per evitare testate e numeri di pagina
    top_limit, bottom_limit = 45, height - 45
    
    # Controllo per evitare di spezzare titoli centrati o copertine
    full_text = page.crop((0, top_limit, width, bottom_limit)).extract_text() or ""
    if len(full_text) < 300:
        return [{"type": "TEXT", "content": _clean_orphans(full_text), "source": "geom_full_page"}]

    for side, x0, x1 in [("left", 0, mid - margin_left), ("right", mid - margin_right, width)]:
        column_area = page.crop((x0, top_limit, x1, bottom_limit))
        text = column_area.extract_text() or ""
        if text.strip():
            results.append({
                "type": "TEXT",
                "content": _clean_orphans(text),
                "source": f"geom_{side}_pure"
            })
    return results


def _find_bottom_boundary(
    plumber_pdf: pdfplumber.PDF,
    page_idx: int,
    block: dict,
) -> float | None:
    """Trova y_bottom di un blocco. Riceve plumber_pdf già aperto."""
    x0    = block["x0"]
    y_top = block["top"]
    side  = block["figure_side"]
    width = block["page_width"]

    words = plumber_pdf.pages[page_idx].extract_words(extra_attrs=["fontname", "size"])

    if side == "full":
        col_words = [w for w in words if w["top"] > y_top]
    elif side == "right":
        col_words = [w for w in words if w["x0"] >= (x0 - 5) and w["top"] > y_top]
    else:
        col_words = [w for w in words if w["x0"] < width / 2 and w["top"] > y_top]

    col_words = sorted(col_words, key=lambda w: (w["top"], w["x0"]))

    anchor_y = anchor_size = None
    for w in col_words:
        if re.match(r"^(Sources?|Note):?$", w["text"], re.IGNORECASE):
            anchor_y    = w["top"]
            anchor_size = w.get("size", 0)
            break

    if not anchor_y or not anchor_size:
        return None

    last_valid_y = anchor_y
    for w in col_words:
        if w["top"] < anchor_y:
            continue
        if w.get("size", 0) > (anchor_size + 0.5):
            return w["top"] - 3
        last_valid_y = w["bottom"]

    return last_valid_y


def _split_by_columns(
    plumber_pdf: pdfplumber.PDF,
    page_idx: int,
    content_blocks: list[dict],
) -> list:
    """
    Pattern Sandwich (da upload_pdf.py, adattato per bytes):
    
    La pagina viene divisa in 3 fasce orizzontali:
      - SOPRA  (0 → y_top):     testo puro, estratto a due colonne
      - CENTRO (y_top → y_bot): il blocco FIGURE/TABLE
      - SOTTO  (y_bot → H):     testo puro, estratto a due colonne
    
    Regole blocco centrale:
      - TABLE → sempre full-width (non si taglia mai)
      - FIGURE full → full-width
      - FIGURE left → crop solo colonna sinistra; colonna destra come TEXT
      - FIGURE right → crop solo colonna destra; colonna sinistra come TEXT
    
    Le fasce SOPRA e SOTTO vengono sempre estratte a due colonne
    per evitare che numeri di tabelle/figure sporchino il testo.
    """
    results = []
    page    = plumber_pdf.pages[page_idx]
    width   = page.width
    height  = page.height
    mid     = width / 2
    margin_left = 2
    margin_right = 2

    for blk in content_blocks:
        side = blk["figure_side"]
        y_t  = max(blk["top"] - 10, 0)  # Piccolo margine sopra il titolo
        y_b  = _find_bottom_boundary(plumber_pdf, page_idx, blk) or (y_t + 300)

        # ── BLOCCO CENTRALE ───────────────────────────────────────────
        if side == "full":
            # TABLE o FIGURE full-width: crop a tutta larghezza
            f_txt = page.crop((0, y_t, width, y_b)).extract_text() or ""
            if f_txt.strip():
                results.append({"type": blk["type"], "content": f_txt.strip(), "source": "geom_fig"})

        elif side == "right":
            # FIGURE a destra: crop solo colonna destra
            f_txt = page.crop((mid - margin_right, y_t, width, y_b)).extract_text() or ""
            if f_txt.strip():
                results.append({"type": blk["type"], "content": f_txt.strip(), "source": "geom_fig"})
            # Colonna opposta (sinistra) nella fascia del blocco → TEXT
            opp_txt = page.crop((0, y_t, mid - margin_left, y_b)).extract_text() or ""
            if opp_txt.strip():
                results.append({"type": "TEXT", "content": _clean_orphans(opp_txt), "source": "geom_left_mid"})

        else:  # left
            # FIGURE a sinistra: crop solo colonna sinistra
            f_txt = page.crop((0, y_t, mid - margin_left, y_b)).extract_text() or ""
            if f_txt.strip():
                results.append({"type": blk["type"], "content": f_txt.strip(), "source": "geom_fig"})
            # Colonna opposta (destra) nella fascia del blocco → TEXT
            opp_txt = page.crop((mid - margin_right, y_t, width, y_b)).extract_text() or ""
            if opp_txt.strip():
                results.append({"type": "TEXT", "content": _clean_orphans(opp_txt), "source": "geom_right_mid"})

        # ── FASCE SOPRA E SOTTO (testo puro, due colonne) ─────────────
        text_bands = [
            ("top",    5,   y_t),
            ("bottom", y_b, height - 5),
        ]

        for band_name, band_start, band_end in text_bands:
            if band_end - band_start < 20:
                continue

            for col_side, x0, x1 in [("left", 0, mid - margin_left), ("right", mid - margin_right, width)]:
                col_txt = page.crop((x0, band_start, x1, band_end)).extract_text() or ""
                if col_txt.strip():
                    results.append({
                        "type": "TEXT",
                        "content": _clean_orphans(col_txt),
                        "source": f"geom_{col_side}_{band_name}",
                    })

    return results


def _process_page(
    fitz_doc: fitz.Document,
    plumber_pdf: pdfplumber.PDF,
    page_idx: int,
) -> list[dict]:
    """
    Coordina le strategie di estrazione: Sandwich (se ci sono FIGURE/TABLE) 
    o Due Colonne (se è solo testo).
    """
    page = plumber_pdf.pages[page_idx]
    
    # 1. SCOUTING: Cerchiamo FIGURE o TABLE nella pagina
    blocks = _find_content_blocks(plumber_pdf, page_idx)
    
    if blocks:
        # 2. STRATEGIA SANDWICH: Usa la logica a colonne rispettando i blocchi trovati
        source_blocks = _split_by_columns(plumber_pdf, page_idx, blocks)
    else:
        # 3. STRATEGIA DUE COLONNE: Testo standard pulito
        source_blocks = split_simple_two_columns(page)
        
    return source_blocks


def _extract_figure_png_b64(
    fitz_doc: fitz.Document,
    plumber_pdf: pdfplumber.PDF,
    page_idx: int,
    blk: dict,
    dpi: int = 150,
) -> str:
    """Estrae il blocco FIGURE/TABLE come PNG base64."""
    page = fitz_doc[page_idx]
    side = blk["figure_side"]

    y_bottom = _find_bottom_boundary(plumber_pdf, page_idx, blk)

    # Coordinate di crop allineate alla logica try2:
    # full → tutta la larghezza
    # right → da metà pagina a destra
    # left → da sinistra a metà pagina
    if side == "full":
        x0 = 0
        x1 = page.rect.width
    elif side == "right":
        x0 = page.rect.width / 2
        x1 = page.rect.width
    else:  # left
        x0 = 0
        x1 = page.rect.width / 2

    y0 = blk["top"]
    y1 = y_bottom if y_bottom else page.rect.height

    scale = dpi / 72
    pix   = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=fitz.Rect(x0, y0, x1, y1))
    raw_bytes = pix.tobytes("jpeg", jpg_quality=85)
    del pix
    img_b64 = base64.standard_b64encode(raw_bytes).decode("utf-8")
    return img_b64, (x0, y0, x1, y1), raw_bytes


def _extract_table_text(
    plumber_pdf: pdfplumber.PDF,
    page_idx: int,
    coords: tuple[float, float, float, float],
) -> str:
    x0, y0, x1, y1 = coords
    tables = plumber_pdf.pages[page_idx].crop((x0, y0, x1, y1)).extract_tables()
    if not tables:
        return ""

    rows = []
    for table in tables:
        for row in table:
            cells = [str(c).strip() for c in row if c and str(c).strip()]
            if cells:
                rows.append(" | ".join(cells))
    return "\n".join(rows)


# ==============================================================================
# LEVEL 3 — CHUNK BUILDING + EMBEDDING WINDOW
# ==============================================================================

def _build_and_embed_window(
    window_pages: list[int],
    fitz_doc: fitz.Document,
    plumber_pdf: pdfplumber.PDF,
    file_content: bytes,
    doc_meta: dict,
    splitter: RecursiveCharacterTextSplitter,
    file_hash: str,
) -> list[dict]:
    
    all_window_chunks = []
    last_text_chunks = []

    for page_idx in window_pages:
        raw_chunks       = []
        page_num    = page_idx + 1
        header      = _build_context_header(doc_meta, page_num)
        page_blocks = _process_page(fitz_doc, plumber_pdf, page_idx)
        if not page_blocks:
            continue

        for i, block in enumerate(page_blocks):

            # ── TEXT ──────────────────────────────────────────────────────
            if block["type"] == "TEXT":
                chunks = splitter.split_text(block["content"])
                if chunks and len(chunks[0].strip()) < 100:
                    chunks = chunks[1:]
                for chunk_text in chunks:
                    raw_chunks.append(_make_raw_chunk(
                        file_hash  = file_hash,
                        page_num   = page_num,
                        chunk_id   = len(raw_chunks) + 1,
                        chunk_type = "TEXT",
                        content    = f"{header}\n{chunk_text}",
                    ))
                    if len(chunk_text.strip()) >= 100:
                        last_text_chunks.append(chunk_text)
                        if len(last_text_chunks) > 2:
                            last_text_chunks.pop(0)

            # ── FIGURE / TABLE ────────────────────────────────────────────
            else:
                ctx_before = "\n\n".join(last_text_chunks) if last_text_chunks else None

                geom_blocks      = _find_content_blocks(plumber_pdf, page_idx)
                fig_geom_blocks  = [b for b in geom_blocks if b["type"] == block["type"]]
                same_type_before = sum(
                    1 for b in page_blocks[:i] if b["type"] == block["type"]
                )
                blk = (
                    fig_geom_blocks[same_type_before]
                    if same_type_before < len(fig_geom_blocks)
                    else (fig_geom_blocks[0] if fig_geom_blocks else None)
                )

                if blk is None:
                    logger.warning(f"Page {page_num}: no geom block for {block['type']} — skipping vision")
                    continue

                try:
                    img_b64, coords, image_raw_data = _extract_figure_png_b64(fitz_doc, plumber_pdf, page_idx, blk)
                    table_text = None
                    if block["type"] == "TABLE":
                        table_text = _extract_table_text(plumber_pdf, page_idx, coords) or None
                    caption = _call_haiku_vision(
                        image_b64   = img_b64,
                        media_type  = "image/jpeg",
                        source_text = block["content"],
                        ctx_before  = ctx_before,
                        table_text  = table_text,
                    )
                    del img_b64
                    if caption:
                        chunk_id = len(raw_chunks) + 1
                        s3_path = _upload_image_to_s3(image_raw_data, file_hash, page_num, chunk_id, BUCKET_NAME)
                        raw_chunks.append(_make_raw_chunk(
                            file_hash  = file_hash,
                            page_num   = page_num,
                            chunk_id   = chunk_id,
                            chunk_type = block["type"],
                            content    = f"{header}\n{caption}",
                            s3_path = s3_path
                        ))
                    del image_raw_data
                except Exception as e:
                    logger.error(f"Vision error page {page_num} {block['type']}: {e}")
        all_window_chunks.extend(raw_chunks)
        del raw_chunks
        gc.collect()
    return _embed_chunks_parallel(all_window_chunks)


# ==============================================================================
# LEVEL 4 — EMBEDDING
# ==============================================================================

def _embed_chunks_parallel(raw_chunks: list[dict]) -> list[dict]:
    if not raw_chunks:
        return []

    results = [None] * len(raw_chunks)

    def _embed_one(idx: int, chunk: dict) -> tuple[int, dict]:
        raw_embedding   = get_embedding(chunk["content"][:MAX_INPUT_CHARS])
        chunk["vector"] = np.array(raw_embedding).tolist()
        return idx, chunk

    with ThreadPoolExecutor(max_workers=MAX_EMBEDDING_WORKERS) as executor:
        futures = {
            executor.submit(_embed_one, i, chunk): i
            for i, chunk in enumerate(raw_chunks)
        }
        for future in as_completed(futures):
            try:
                idx, chunk    = future.result()
                results[idx]  = chunk
            except Exception as e:
                logger.error(f"Embedding error: {e}")

    return [c for c in results if c is not None]


# ==============================================================================
# HELPERS
# ==============================================================================

def _make_raw_chunk(
    file_hash: str,
    page_num: int,
    chunk_id: int,
    chunk_type: str,
    content: str,
    s3_path: str | None = None
) -> dict:
    return {
        "file_hash":  file_hash,
        "page_num":   page_num,
        "chunk_id":   chunk_id,
        "chunk_type": chunk_type,
        "content":    content,
        "vector":     None,
        "s3_path":    s3_path
    }


def calculate_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _call_haiku_vision(
    image_b64: str,
    media_type: str = "image/jpeg",
    source_text: str = "",
    ctx_before: str | None = None,
    table_text: str | None = None,
) -> str:
    """
    Chiama Haiku Vision con:
    - source_text: testo estratto dal blocco figura (titolo + descrizione + Sources)
    - ctx_before: chunk TEXT immediatamente prima (se presente)
    - table_text: dati strutturati della tabella (se presente)
    """
    context_parts = []
    if ctx_before:
        context_parts.append(f"Text before this figure:\n{ctx_before}")
    if source_text:
        context_parts.append(f"Text extracted from the figure block:\n{source_text}")
    if table_text:
        context_parts.append(f"Structured table data:\n{table_text}")

    context_block = "\n\n".join(context_parts)

    prompt = (
    "You are analyzing a visual element (figure or table) from an economic report. "
    "Your description will be indexed in a RAG system and retrieved via semantic search.\n\n"
    )
    if context_block:
        prompt += f"Here is the surrounding context:\n\n{context_block}\n\n"
    prompt += (
    "Use this context to better understand the visual element. "
    "Write a single dense paragraph — no headers, no bullet points, no lists. "
    "Include: the main topic, all key data points with their exact values, "
    "all entities mentioned (countries, regions, indicators), time periods, "
    "and the main insight or message conveyed. "
    "Be specific and include all visible numbers and labels. Avoid vague language."
    )

    user_content = [
        {"type": "text",  "text": prompt},
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
    ]

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        1024,
        "messages": [{"role": "user", "content": user_content}],
    })

    logger.info(f"Haiku Vision prompt length: {len(prompt)} chars")

    for attempt in range(MAX_VISION_RETRIES):
        try:
            response  = bedrock.invoke_model_with_response_stream(
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

# ==============================================================================
# DOMAIN DETECTION
# ==============================================================================

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

    weights    = PAGE_WEIGHTS[:len(text_pages)]
    total      = sum(weights)
    weights    = [w / total for w in weights]
    embeddings = [get_embedding(t[:MAX_INPUT_CHARS]) for t in text_pages]
    centroid   = (v := np.dot(weights, embeddings)) / np.linalg.norm(v)
    domain_id  = find_closest_domain(centroid)
    logger.info(f"Domain detected: id={domain_id}")
    return domain_id


# ==============================================================================
# DATABASE
# ==============================================================================

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
        """, (file_hash, file_name, id_domain, COHERE_MODEL_ID, INGESTION_SOURCE))
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
            INSERT INTO chunks (file_hash, page_number, chunk_id, chunk_type, content, embedding, s3_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (file_hash, page_number, chunk_id)
            DO UPDATE SET
                chunk_type = EXCLUDED.chunk_type,
                content    = EXCLUDED.content,
                embedding  = EXCLUDED.embedding,
                s3_path    = EXCLUDED.s3_path
        """, [
            (c["file_hash"], c["page_num"], c["chunk_id"],
             c["chunk_type"], c["content"], c["vector"], c.get("s3_path"))
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


def _get_resume_data(file_hash: str) -> tuple[int, list | None, int | None]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(MAX(c.page_number), 0) as last_page,
                   t.toc,
                   t.page_offset,
                   t.last_content_page
            FROM chunks c
            LEFT JOIN toc_cache t ON t.file_hash = c.file_hash
            WHERE c.file_hash = %s
            GROUP BY t.toc, t.page_offset, t.last_content_page
        """, (file_hash,))
        row = cur.fetchone()
        if row:
            return row[0], row[1], row[2], row[3]
        return 0, None, None, None
    except Exception as e:
        logger.error(f"DB error getting resume data: {e}")
        return 0, None, None, None
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


def save_toc_cache(file_hash: str, toc: list, page_offset: int, last_content_page: int):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO toc_cache (file_hash, toc, page_offset, last_content_page)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE SET
                toc    = EXCLUDED.toc,
                page_offset = EXCLUDED.page_offset,
                last_content_page = EXCLUDED.last_content_page
            """,
            (file_hash, json.dumps(toc), page_offset, last_content_page)
        )
        conn.commit()
        logger.info(f"TOC cache saved for hash {file_hash[:8]}...")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error saving TOC cache: {e}")
    finally:
        put_conn(conn)


def delete_toc_cache(file_hash: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM toc_cache WHERE file_hash = %s",
            (file_hash,)
        )
        conn.commit()
        logger.info(f"TOC cache deleted for hash {file_hash[:8]}...")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error deleting TOC cache: {e}")
    finally:
        put_conn(conn)


# ==============================================================================
# S3
# ==============================================================================

def _upload_image_to_s3(
    image_bytes: bytes,
    file_hash:   str,
    page_num:    int,
    chunk_id:    int,
    bucket_name: str,
) -> str:
    s3_key = f"ingestion/assets/{file_hash}/p{page_num}_c{chunk_id}.jpg"
    
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/jpeg"
    )
    return s3_key