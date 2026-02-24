import boto3
import logging
import json
import io
import hashlib
import base64
import pdfplumber
import fitz
import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter

from shared.config import (
    CHUNK_SIZE, CHUNK_OVERLAP, IMAGE_MIN_SIZE, DRAWING_THRESHOLD,
    MIN_TABLE_ROWS, PAGE_FLUSH_SIZE, MAX_INPUT_CHARS, HAIKU_MODEL_ID,
    PAGE_WEIGHTS, TEXT_PAGES_NEEDED, MIN_TEXT_LENGTH,
)
from shared.db import get_conn, put_conn
from shared.embeddings import get_embedding, _find_closest_domain

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime")


# ─── PAGE INSPECTOR ────────────────────────────────────────────────────────────

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


# ─── VISION ────────────────────────────────────────────────────────────────────

def _page_to_jpeg_base64(fitz_page) -> str:
    pix = fitz_page.get_pixmap(dpi=120)
    return base64.standard_b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode("utf-8")


def _image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def _call_haiku_vision(image_b64: str, media_type: str = "image/jpeg", context_text: str = "") -> str:
    user_content = []

    if context_text:
        user_content.append({
            "type": "text",
            "text": (
                "Here is the text extracted from the same page as the chart:\n\n"
                f"{context_text}\n\n"
                "Based on this text, describe in detail the content of the chart/figure "
                "present in the image: panels, trends, key values, scenarios and countries represented."
            )
        })
    else:
        user_content.append({
            "type": "text",
            "text": (
                "Describe in detail the content of this chart/figure: "
                "panels, trends, key values, scenarios, and countries represented."
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

    response = bedrock.invoke_model(
        modelId     = HAIKU_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def calculate_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

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


# ─── PROCESS FILE ─────────────────────────────────────────────────────────────

def process_single_file(bucket: str, key: str):
    s3           = boto3.client("s3")
    file_content = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    file_hash    = calculate_file_hash(file_content)

    if key.lower().endswith(".pdf"):
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            id_domain = get_vector_domain(pdf)
        upsert_file_record(key, file_hash, id_domain)
        try:
            _process_pdf(file_content, file_hash, key)
            update_file_status(file_hash, "completed")
        except Exception as e:
            update_file_status(file_hash, "failed")
            logger.error(f"PDF processing failed for {key}: {e}")
            raise


# ─── DOMAIN DETECTION ─────────────────────────────────────────────────────────

def get_vector_domain(pdf: pdfplumber.PDF) -> int | None:
    text_pages = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        if len(text.strip()) >= MIN_TEXT_LENGTH:
            text_pages.append(text)
        if len(text_pages) == TEXT_PAGES_NEEDED:
            break

    if not text_pages:
        logger.warning("No text-based pages found in the document")
        return None

    weights = PAGE_WEIGHTS[:len(text_pages)]
    total   = sum(weights)
    weights = [w / total for w in weights]

    embeddings = [get_embedding(t[:MAX_INPUT_CHARS]) for t in text_pages]
    centroid   = (v_total := np.dot(weights, embeddings)) / np.linalg.norm(v_total)
    return _find_closest_domain(centroid)


# ─── PDF PROCESSING ───────────────────────────────────────────────────────────

def _process_pdf(file_content: bytes, file_hash: str, key: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        separators    = ["\n\n", "\n", ". ", " ", ""],
    )

    buffer        = []
    total_chunks  = 0
    last_caption  = None

    with fitz.open(stream=file_content, filetype="pdf") as fitz_doc, \
         pdfplumber.open(io.BytesIO(file_content)) as plumber_pdf:

        total_pages = len(fitz_doc)

        for i in range(total_pages):
            page_num      = i + 1
            fitz_page     = fitz_doc[i]
            page_chunk_id = 0
            page_info     = _inspect_page(fitz_page, fitz_doc)

            # ── VECTOR GRAPHIC ────────────────────────────────────────────
            if page_info["has_vector"]:
                logger.info(f"Page {page_num}: VECTOR_GRAPHIC → Haiku Vision")
                try:
                    page_jpeg_b64 = _page_to_jpeg_base64(fitz_page)
                    caption       = _call_haiku_vision(page_jpeg_b64, media_type="image/jpeg")
                    page_chunk_id += 1
                    buffer.append(_build_chunk(
                        file_hash  = file_hash,
                        page_num   = page_num,
                        chunk_id   = page_chunk_id,
                        chunk_type = "VECTOR_GRAPHIC",
                        content    = caption,
                    ))
                    last_caption = caption
                except Exception as e:
                    logger.error(f"Vision error on page {page_num} (VECTOR_GRAPHIC): {e}")

                total_chunks += page_chunk_id
                _maybe_flush(buffer, page_num, total_pages, key)
                continue

            # ── IMAGE PURA (no testo) ─────────────────────────────────────
            if page_info["has_image"] and not page_info["has_text"]:
                logger.info(f"Page {page_num}: pure IMAGE → Haiku Vision")
                for img in page_info["images"]:
                    xref = img[0]
                    try:
                        info = fitz_doc.extract_image(xref)
                        w, h = info.get("width", 0), info.get("height", 0)
                        if w <= IMAGE_MIN_SIZE or h <= IMAGE_MIN_SIZE:
                            continue
                        ext        = info.get("ext", "png")
                        media_type = f"image/{ext}" if ext in ("png", "jpeg", "gif", "webp") else "image/png"
                        img_b64    = _image_bytes_to_base64(info["image"])
                        caption    = _call_haiku_vision(img_b64, media_type=media_type)
                        page_chunk_id += 1
                        buffer.append(_build_chunk(
                            file_hash  = file_hash,
                            page_num   = page_num,
                            chunk_id   = page_chunk_id,
                            chunk_type = "IMAGE",
                            content    = caption,
                        ))
                        last_caption = caption
                    except Exception as e:
                        logger.error(f"Vision error on page {page_num} xref {xref}: {e}")

                total_chunks += page_chunk_id
                _maybe_flush(buffer, page_num, total_pages, key)
                continue

            # ── IMAGE MISTA (has_text = True) ─────────────────────────────
            if page_info["has_image"]:
                plumber_page = plumber_pdf.pages[i]
                context_text = plumber_page.extract_text() or ""
                logger.info(f"Page {page_num}: mixed IMAGE+TEXT → Haiku Vision with context")
                for img in page_info["images"]:
                    xref = img[0]
                    try:
                        info = fitz_doc.extract_image(xref)
                        w, h = info.get("width", 0), info.get("height", 0)
                        if w <= IMAGE_MIN_SIZE or h <= IMAGE_MIN_SIZE:
                            continue
                        ext        = info.get("ext", "png")
                        media_type = f"image/{ext}" if ext in ("png", "jpeg", "gif", "webp") else "image/png"
                        img_b64    = _image_bytes_to_base64(info["image"])
                        caption    = _call_haiku_vision(img_b64, media_type=media_type, context_text=context_text)
                        page_chunk_id += 1
                        buffer.append(_build_chunk(
                            file_hash  = file_hash,
                            page_num   = page_num,
                            chunk_id   = page_chunk_id,
                            chunk_type = "IMAGE",
                            content    = caption,
                        ))
                        last_caption = caption
                    except Exception as e:
                        logger.error(f"Vision error on page {page_num} xref {xref}: {e}")

            # ── TEXT + TABLE ───────────────────────────────────────────────
            if page_info["has_text"]:
                plumber_page = plumber_pdf.pages[i]
                tables       = plumber_page.find_tables()
                table_bboxes = [t.bbox for t in tables]

                for table in tables:
                    extracted = table.extract()
                    if not extracted:
                        continue
                    header = extracted[0]
                    rows   = []
                    for row in extracted[1:]:
                        pairs = []
                        for h, cell in zip(header, row):
                            h_clean    = str(h).strip()    if h    else "?"
                            cell_clean = str(cell).strip() if cell else ""
                            if h_clean and cell_clean:
                                pairs.append(f"{h_clean}: {cell_clean}")
                        if pairs:
                            rows.append(" | ".join(pairs))

                    if rows and len(rows) >= MIN_TABLE_ROWS:
                        page_chunk_id += 1
                        buffer.append(_build_chunk(
                            file_hash  = file_hash,
                            page_num   = page_num,
                            chunk_id   = page_chunk_id,
                            chunk_type = "TABLE",
                            content    = "\n".join(rows),
                        ))

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

                if page_text and page_text.strip():
                    first_text_chunk = True
                    for chunk_text in splitter.split_text(page_text.strip()):
                        # Context enrichment: prepend caption to first TEXT chunk
                        if first_text_chunk and last_caption:
                            truncated_caption = _truncate_at_sentence(last_caption, CHUNK_OVERLAP)
                            chunk_text = f"[Figura: {truncated_caption}]\n\n{chunk_text}"
                            last_caption     = None
                            first_text_chunk = False

                        page_chunk_id += 1
                        buffer.append(_build_chunk(
                            file_hash  = file_hash,
                            page_num   = page_num,
                            chunk_id   = page_chunk_id,
                            chunk_type = "TEXT",
                            content    = chunk_text,
                        ))
                    last_caption = None

            total_chunks += page_chunk_id
            _maybe_flush(buffer, page_num, total_pages, key)

        if buffer:
            save_chunks_to_rds(buffer)
            buffer.clear()

    logger.info(f"Completed ingestion for PDF: {key} ({total_chunks} total chunks)")


def _truncate_at_sentence(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_period = cut.rfind(". ")
    return cut[:last_period + 1] if last_period > 0 else cut


def _build_chunk(file_hash: str, page_num: int, chunk_id: int,
                 chunk_type: str, content: str) -> dict:
    return {
        "file_hash":  file_hash,
        "page_num":   page_num,
        "chunk_id":   chunk_id,
        "chunk_type": chunk_type,
        "content":    content,
        "vector":     get_embedding(content[:MAX_INPUT_CHARS]),
    }


def _maybe_flush(buffer: list, page_num: int, total_pages: int, key: str):
    is_last_page    = (page_num == total_pages)
    hit_flush_limit = (page_num % PAGE_FLUSH_SIZE == 0)
    if buffer and (hit_flush_limit or is_last_page):
        logger.info(f"Flushing {len(buffer)} chunks (up to page {page_num}/{total_pages}) → {key}")
        save_chunks_to_rds(buffer)
        buffer.clear()


# ─── TEXT FILE PROCESSING ─────────────────────────────────────────────────────

def _process_text(file_content: bytes, file_hash: str, key: str):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        separators    = ["\n\n", "\n", ". ", " ", ""],
    )
    text   = file_content.decode("utf-8")
    chunks = []
    for idx, chunk_text in enumerate(splitter.split_text(text.strip()), start=1):
        if len(chunk_text.strip()) < 15:
            continue
        chunks.append(_build_chunk(
            file_hash  = file_hash,
            page_num   = 1,
            chunk_id   = idx,
            chunk_type = "TEXT",
            content    = chunk_text,
        ))

    if chunks:
        save_chunks_to_rds(chunks)
        logger.info(f"Completed ingestion for text file: {key} ({len(chunks)} chunks)")
    else:
        logger.warning(f"No valid text extracted from file: {key}")


# ─── DATABASE ─────────────────────────────────────────────────────────────────

def upsert_file_record(file_name: str, file_hash: str, id_domain: int | None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO fileIngested (file_hash, file_name, id_domain, embedding_model, ingested_from, status)
            VALUES (%s, %s, %s, %s, %s, 'processing')
            ON CONFLICT (file_hash) DO UPDATE SET
                ingested_at = CURRENT_TIMESTAMP,
                status      = 'processing'
        """, (file_hash, file_name, id_domain, "amazon.titan-embed-text-v2:0", "S3_Lambda_Processor"))
        conn.commit()
        logger.info(f"File record upserted with status 'processing': {file_name}")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error upserting file record: {str(e)}")
        raise
    finally:
        put_conn(conn)


def update_file_status(file_hash: str, status: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE fileIngested
            SET status = %s
            WHERE file_hash = %s
        """, (status, file_hash))
        conn.commit()
        logger.info(f"File status updated to '{status}' for hash {file_hash[:8]}...")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error updating file status: {str(e)}")
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
        logger.info(f"Flushed {len(chunks)} chunks to RDS successfully.")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB error saving chunks: {str(e)}")
        raise
    finally:
        put_conn(conn)
