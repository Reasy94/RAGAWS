import boto3
import os
import logging
import json
import hashlib
import numpy as np
import psycopg2
import psycopg2.pool

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── CONFIGURAZIONE ────────────────────────────────────────────────────────────

MAX_INPUT_CHARS   = 8000
RETRIEVAL_TOP_K   = 20
RERANK_TOP_N      = 5
CACHE_SIMILARITY  = 0.95
CACHE_TTL_HOURS   = 24

TITAN_MODEL_ID   = "amazon.titan-embed-text-v2:0"
HAIKU_MODEL_ID   = "anthropic.claude-3-haiku-20240307-v1:0"
RERANK_MODEL_ID  = "cohere.rerank-v3-5:0"

bedrock = boto3.client("bedrock-runtime")


# ─── DATABASE ─────────────────────────────────────────────────────────────────

def get_db_config() -> dict:
    secret_arn = os.environ.get("SECRET_ARN")
    client     = boto3.client("secretsmanager")
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


# ─── EMBEDDING ────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    response = bedrock.invoke_model(
        modelId     = TITAN_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = json.dumps({"inputText": text[:MAX_INPUT_CHARS]}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]


# ─── SEMANTIC CACHE ───────────────────────────────────────────────────────────

def check_cache(query_embedding: list[float]) -> dict | None:
    """
    Check if a semantically similar query has been cached recently.
    Returns cached response if similarity > CACHE_SIMILARITY and within TTL.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT query_text, response, sources,
                   1 - (query_embedding <=> %s::vector) AS similarity
            FROM query_cache
            WHERE created_at > NOW() - INTERVAL '%s hours'
            ORDER BY query_embedding <=> %s::vector
            LIMIT 1
        """, (query_embedding, CACHE_TTL_HOURS, query_embedding))
        row = cur.fetchone()
        if row and row[3] >= CACHE_SIMILARITY:
            logger.info(f"Cache HIT (similarity: {row[3]:.3f}) for query similar to: {row[0][:50]}...")
            return {
                "response": row[1],
                "sources":  json.loads(row[2]) if isinstance(row[2], str) else row[2],
                "cached":   True,
            }
        logger.info("Cache MISS")
        return None
    except Exception as e:
        logger.warning(f"Cache check failed: {e}")
        return None
    finally:
        connection_pool.putconn(conn)


def store_cache(query_text: str, query_embedding: list[float], response: str, sources: list[dict]):
    """Store query-response pair in semantic cache."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO query_cache (query_text, query_embedding, response, sources)
            VALUES (%s, %s::vector, %s, %s)
            ON CONFLICT (query_text) DO UPDATE SET
                query_embedding = EXCLUDED.query_embedding,
                response        = EXCLUDED.response,
                sources         = EXCLUDED.sources,
                created_at      = CURRENT_TIMESTAMP
        """, (query_text, query_embedding, response, json.dumps(sources)))
        conn.commit()
        logger.info("Cache stored successfully")
    except Exception as e:
        conn.rollback()
        logger.warning(f"Cache store failed: {e}")
    finally:
        connection_pool.putconn(conn)


# ─── HyDE (Hypothetical Document Embeddings) ─────────────────────────────────

def generate_hypothetical_document(query: str) -> str:
    """
    Use Haiku to generate a hypothetical document that would answer the query.
    The embedding of this synthetic doc matches better against real chunks
    than the short query embedding alone.
    """
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        300,
        "messages": [{
            "role": "user",
            "content": (
                "Scrivi un breve paragrafo (massimo 200 parole) che risponda "
                "in modo dettagliato e tecnico alla seguente domanda. "
                "Non aggiungere preamboli, scrivi direttamente la risposta.\n\n"
                f"Domanda: {query}"
            )
        }],
    })

    response = bedrock.invoke_model(
        modelId     = HAIKU_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    result = json.loads(response["body"].read())
    hypothetical_doc = result["content"][0]["text"].strip()
    logger.info(f"HyDE generated ({len(hypothetical_doc)} chars)")
    return hypothetical_doc


# ─── VECTOR SEARCH ────────────────────────────────────────────────────────────

def vector_search(query_embedding: list[float], top_k: int = RETRIEVAL_TOP_K) -> list[dict]:
    """
    Retrieve top_k chunks from pgvector ordered by cosine similarity.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.file_hash, c.page_number, c.chunk_id, c.chunk_type, c.content,
                   f.file_name, f.id_domain,
                   1 - (c.embedding <=> %s::vector) AS similarity
            FROM chunks c
            JOIN fileIngested f ON c.file_hash = f.file_hash
            WHERE f.status = 'completed'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, top_k))

        results = []
        for row in cur.fetchall():
            results.append({
                "file_hash":   row[0],
                "page_number": row[1],
                "chunk_id":    row[2],
                "chunk_type":  row[3],
                "content":     row[4],
                "file_name":   row[5],
                "id_domain":   row[6],
                "similarity":  row[7],
            })
        logger.info(f"Vector search returned {len(results)} chunks")
        return results
    finally:
        connection_pool.putconn(conn)


# ─── RERANKER ─────────────────────────────────────────────────────────────────

def rerank(query: str, chunks: list[dict], top_n: int = RERANK_TOP_N) -> list[dict]:
    """
    Use Cohere Rerank 3.5 on Bedrock to reorder chunks by relevance.
    """
    if not chunks:
        return []

    documents = [c["content"] for c in chunks]

    body = json.dumps({
        "query":       query,
        "documents":   documents,
        "top_n":       top_n,
        "api_version": 2,
    })

    response = bedrock.invoke_model(
        modelId     = RERANK_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    result = json.loads(response["body"].read())

    reranked = []
    for item in result["results"]:
        idx   = item["index"]
        score = item["relevance_score"]
        chunk = chunks[idx].copy()
        chunk["rerank_score"] = score
        reranked.append(chunk)

    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    logger.info(f"Reranked to top {len(reranked)} chunks. "
                f"Scores: {[round(c['rerank_score'], 3) for c in reranked]}")
    return reranked


# ─── GENERATION ───────────────────────────────────────────────────────────────

def generate_response(query: str, chunks: list[dict]) -> str:
    """
    Use Haiku to generate a grounded response based on retrieved chunks.
    """
    if not chunks:
        return "Non ho trovato informazioni sufficienti per rispondere alla domanda."

    # Build context from reranked chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source_info = f"[Fonte {i}: {chunk['file_name']}, pag. {chunk['page_number']}]"
        context_parts.append(f"{source_info}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        1024,
        "system": (
            "Sei un assistente esperto che risponde basandosi ESCLUSIVAMENTE "
            "sui documenti forniti come contesto. Se il contesto non contiene "
            "informazioni sufficienti, dillo chiaramente. "
            "Cita le fonti usando il formato [Fonte N] quando fai riferimento "
            "a informazioni specifiche."
        ),
        "messages": [{
            "role": "user",
            "content": (
                f"Contesto:\n\n{context}\n\n"
                f"---\n\nDomanda: {query}\n\n"
                "Rispondi in modo chiaro e dettagliato basandoti solo sul contesto fornito."
            )
        }],
    })

    response = bedrock.invoke_model(
        modelId     = HAIKU_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    """
    API Gateway integration.
    Expects: { "query": "..." }
    Returns: { "response": "...", "sources": [...], "cached": bool }
    """
    try:
        # Parse request
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        query = body.get("query", "").strip()
        if not query:
            return _api_response(400, {"error": "Missing 'query' parameter"})

        logger.info(f"Query received: {query[:100]}...")

        # Step 1: Embed the original query
        query_embedding = get_embedding(query)

        # Step 2: Check semantic cache
        cached = check_cache(query_embedding)
        if cached:
            return _api_response(200, cached)

        # Step 3: HyDE — generate hypothetical document and embed it
        hypothetical_doc = generate_hypothetical_document(query)
        hyde_embedding   = get_embedding(hypothetical_doc)

        # Step 4: Vector search using HyDE embedding
        candidates = vector_search(hyde_embedding, top_k=RETRIEVAL_TOP_K)

        if not candidates:
            response_text = "Non ho trovato documenti rilevanti per rispondere alla domanda."
            return _api_response(200, {
                "response": response_text,
                "sources":  [],
                "cached":   False,
            })

        # Step 5: Rerank using original query (not HyDE)
        top_chunks = rerank(query, candidates, top_n=RERANK_TOP_N)

        # Step 6: Generate grounded response
        response_text = generate_response(query, top_chunks)

        # Step 7: Build sources list
        sources = [{
            "file_name":   c["file_name"],
            "page_number": c["page_number"],
            "chunk_type":  c["chunk_type"],
            "rerank_score": round(c["rerank_score"], 3),
            "snippet":     c["content"][:200],
        } for c in top_chunks]

        # Step 8: Store in cache
        store_cache(query, query_embedding, response_text, sources)

        return _api_response(200, {
            "response": response_text,
            "sources":  sources,
            "cached":   False,
        })

    except Exception as e:
        logger.error(f"Retrieval pipeline error: {e}")
        return _api_response(500, {"error": "Internal server error"})


def _api_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type":                "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }