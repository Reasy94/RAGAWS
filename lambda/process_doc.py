import boto3
import os
import logging
import json
import psycopg2
import io
import hashlib
import pdfplumber
import numpy as np

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Global Constants ---
CHUNK_SIZE      = 500
CHUNK_OVERLAP   = 50
PAGE_FLUSH_SIZE = 50  # Flush al DB ogni N pagine per file molto grandi

TITAN_MODEL_ID  = "amazon.titan-embed-text-v2:0"

# Client Bedrock — inizializzato a livello di modulo per riuso tra invocazioni
bedrock = boto3.client("bedrock-runtime")

#Domain
PAGE_WEIGHTS = [0.5, 0.3, 0.2]
TEXT_PAGES_NEEDED = 3
MIN_TEXT_LENGTH   = 100
MAX_INPUT_CHARS = 8000 #Titan v2 input limit 8192 tokens
DOMAIN_SIMILARITY_THRESHOLD = 0.75

# ─── EMBEDDING ────────────────────────────────────────────────────────────────
#check TPS per modello
def get_embedding(text: str) -> list[float]:
    response = bedrock.invoke_model(
        modelId     = TITAN_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = json.dumps({"inputText": text}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def calculate_file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_db_config() -> dict:
    secret_arn = os.environ.get("SECRET_ARN")
    client = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_arn)
        secret   = json.loads(response["SecretString"])
        return {
            "host":     secret["host"],
            "database": secret["db_name"],
            "user":     secret["username"],
            "password": secret["password"],
            "port":     secret.get("port", 5432),
        }
    except Exception as e:
        logger.error(f"Failed to retrieve database secrets: {str(e)}")
        raise

DB_CONFIG = get_db_config()

connection_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    **DB_CONFIG
)


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
            id_domain = get_document_domain(pdf)   # ← prima di upsert
        upsert_file_record(key, file_hash, id_domain)
        _process_pdf(file_content, file_hash, key)
    else:
        text      = file_content.decode("utf-8")
        embedding = get_embedding(text[:MAX_INPUT_CHARS])
        id_domain = _find_closest_domain(embedding)
        upsert_file_record(key, file_hash, id_domain)
        _process_text(file_content, file_hash, key)

def get_conn():
    conn = connection_pool.getconn()
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        logger.warning("Zombie connection detected, reopening...")
        try:
            conn.close()
        except Exception:
            pass
        conn = psycopg2.connect(**DB_CONFIG)
    return conn

def get_document_domain(pdf: pdfplumber.PDF) -> int | None:
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

    #Dynamic Weight Normalization based on available pages. If PDf has less than 3 text pages, 
    #we adjust the weights accordingly.
    weights = PAGE_WEIGHTS[:len(text_pages)]
    total   = sum(weights)
    weights = [w / total for w in weights]

    embeddings = [get_embedding(t[:MAX_INPUT_CHARS]) for t in text_pages]

    # Weighted centroid
    centroid = (v_total := np.dot(weights, embeddings)) / np.linalg.norm(v_total)
    return _find_closest_domain(centroid)


def _find_closest_domain(centroid: list[float]) -> int | None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id_domain, domain_name,
                   1 - (embedding_domain <=> %s::vector) AS similarity
            FROM domains
            ORDER BY embedding_domain <=> %s::vector
            LIMIT 1
        """, (centroid, centroid))
        row = cur.fetchone()

        if not row:
            return None  # nessun dominio nel DB

        id_domain, domain_name, similarity = row

        if similarity < DOMAIN_SIMILARITY_THRESHOLD:
            logger.warning(
                f"Closest domain '{domain_name}' similarity {similarity:.3f} "
                f"is below threshold {DOMAIN_SIMILARITY_THRESHOLD} → unknown domain"
            )
            return None

        logger.info(f"Domain detected: '{domain_name}' (similarity: {similarity:.3f})")
        return id_domain

    finally:
        connection_pool.putconn(conn)

def _process_pdf(file_content: bytes, file_hash: str, key: str):
    buffer = []

    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
        total_pages = len(pdf.pages)

        for page in pdf.pages:
            page_num = page.page_number

            # --- FUTURE INTEGRATION: Vision per pagine con grafici ---
            # if _page_has_figure(page):
            #     visual_chunks = call_vision_model(page)
            #     buffer.extend(visual_chunks)
            # else:

            text = page.extract_text() or ""
            raw_chunks = [
                text[i:i + CHUNK_SIZE]
                for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP)
            ]

            for idx, content in enumerate(raw_chunks):
                if len(content.strip()) < 15:
                    continue
                buffer.append({
                    "file_hash": file_hash,
                    "page_num":  page_num,
                    "chunk_id":  idx + 1,
                    "content":   content,
                    "vector":    get_embedding(content),  # ← Titan API
                })

            is_last_page    = (page_num == total_pages)
            hit_flush_limit = (page_num % PAGE_FLUSH_SIZE == 0)

            if buffer and (hit_flush_limit or is_last_page):
                logger.info(
                    f"Flushing {len(buffer)} chunks "
                    f"(pages up to {page_num}/{total_pages}) -> {key}"
                )
                save_chunks_to_rds(buffer)
                buffer.clear()

    logger.info(f"Completed ingestion for PDF: {key}")


def _process_text(file_content: bytes, file_hash: str, key: str):
    text       = file_content.decode("utf-8")
    raw_chunks = [
        text[i:i + CHUNK_SIZE]
        for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP)
    ]

    chunks = []
    for idx, content in enumerate(raw_chunks):
        if len(content.strip()) < 15:
            continue
        chunks.append({
            "file_hash": file_hash,
            "page_num":  1,
            "chunk_id":  idx + 1,
            "content":   content,
            "vector":    get_embedding(content),
        })

    if chunks:
        save_chunks_to_rds(chunks)
        logger.info(f"Completed ingestion for text file: {key} ({len(chunks)} chunks)")
    else:
        logger.warning(f"No valid text extracted from file: {key}")


# ─── DATABASE ─────────────────────────────────────────────────────────────────
def upsert_file_record(file_name: str, file_hash: str):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO fileIngested (file_hash, file_name, id_domain, embedding_model, ingested_from)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE SET ingested_at = CURRENT_TIMESTAMP
        """, (file_hash, file_name, 1, TITAN_MODEL_ID, "S3_Lambda_Processor"))
        conn.commit()
        logger.info(f"File record upserted: {file_name}")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"DB error upserting file record: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()


def save_chunks_to_rds(chunks: list[dict]):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()

        insert_query = """
            INSERT INTO chunks (file_hash, page_number, chunk_id, content, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_hash, page_number, chunk_id)
            DO UPDATE SET content = EXCLUDED.content, embedding = EXCLUDED.embedding;
        """

        batch_values = [
            (c["file_hash"], c["page_num"], c["chunk_id"], c["content"], c["vector"])
            for c in chunks
        ]

        cur.executemany(insert_query, batch_values)
        conn.commit()
        logger.info(f"Flushed {len(chunks)} chunks to RDS successfully.")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"DB error saving chunks: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()