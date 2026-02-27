import boto3
import logging
import json

from shared.config import (
    HAIKU_MODEL_ID, RERANK_MODEL_ID,
    RETRIEVAL_TOP_K, RERANK_TOP_N, CACHE_SIMILARITY, CACHE_TTL_HOURS,LIMIT_QUERY_HISTORY
)
from shared.db import get_conn, put_conn
from shared.embeddings import get_embedding, _find_closest_domain

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime")


# ─── SEMANTIC CACHE ───────────────────────────────────────────────────────────

def check_cache(query_embedding: list[float]) -> dict | None:
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
            logger.info(f"Cache HIT (similarity: {row[3]:.3f})")
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
        put_conn(conn)


def store_cache(query_text: str, query_embedding: list[float], response: str, sources: list[dict]):
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
        put_conn(conn)

# ─── Context History Query ─────────────────────────────────────────────────────────────────────

def get_recent_history(session_id: str, limit: int = LIMIT_QUERY_HISTORY) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT original_query, answer 
            FROM queries_history
            WHERE answer IS NOT NULL
            AND session_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT %s
        """, (session_id, limit))

        rows = cur.fetchall()
        logger.info(f"History retrieved: {len(rows)} entries for session {session_id}")

        return [
            {"query": row[0], "answer": row[1]}
            for row in reversed(rows)
        ]
    except Exception as e:
        logger.warning(f"History retrieval failed: {e}")
        return []
    finally:
        put_conn(conn)


def rewrite_query(query: str, history: list[dict]) -> str:
    if not history:
        logger.info("No history available, skipping query rewrite")
        return query

    history_text = "\n".join([
        f"User: {h['query']}\nAssistant: {h['answer'][:200]}..."
        for h in history
    ])

    prompt = (
        "Given this conversation history:\n\n"
        f"{history_text}\n\n"
        "Rewrite the following question to be self-contained and unambiguous, "
        "without changing its meaning. "
        "If the question is already self-contained, return it as-is.\n\n"
        f"Question: {query}\n\n"
        "Rewritten question:"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = bedrock.invoke_model(
        modelId     = HAIKU_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    result = json.loads(response["body"].read())
    rewritten = result["content"][0]["text"].strip()
    logger.info(f"Query rewritten: '{query[:50]}...' → '{rewritten[:50]}...'")
    return rewritten
# ─── HyDE ─────────────────────────────────────────────────────────────────────

def get_style_chunks_by_domain(domain_id: int, limit: int = 3) -> list[str]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.content 
            FROM chunks c
            JOIN fileIngested f ON c.file_hash = f.file_hash
            WHERE f.id_domain = %s
            ORDER BY RANDOM() 
            LIMIT %s
        """, (domain_id, limit))
        
        rows = cur.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error fetching style chunks: {e}")
        return []
    finally:
        put_conn(conn)


def generate_hypothetical_document(query: str, style_chunks: list[str]) -> str:
    examples_text = "\n\n".join([f"EXAMPLE {i+1}:\n{chunk}" for i, chunk in enumerate(style_chunks)])

    prompt_content = (
        "You are an expert technical writer. Below are examples of the writing style, "
        "terminology, and structure used in our database documents.\n\n"
        f"=== STYLE EXAMPLES ===\n{examples_text}\n\n"
        "=== TASK ===\n"
        "Write a brief paragraph (max 200 words) that answers the following question. "
        "You must strictly mimic the style, professional tone, and specific vocabulary "
        "shown in the examples above. Do not include any preambles; write the answer directly.\n\n"
        f"Question: {query}"
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        300,
        "messages": [{
            "role": "user",
            "content": prompt_content
        }],
        "temperature" : 0.5
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
        put_conn(conn)


# ─── RERANKER ─────────────────────────────────────────────────────────────────

def rerank(query: str, chunks: list[dict], top_n: int = RERANK_TOP_N) -> list[dict]:
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
    if not chunks:
        return "I could not find sufficient information to answer the question."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source_info = f"[Source {i}: {chunk['file_name']}, page {chunk['page_number']}]"
        context_parts.append(f"{source_info}\n{chunk['content']}")

    context = "\n\n---\n\n".join(context_parts)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        1024,
        "system": (
            "You are an expert assistant. Your answers must be grounded strictly and exclusively in the "
            "provided context. If the context lacks sufficient information to answer the question, "
            "explicitly state that you cannot find the answer. "
            "Always cite your sources using the format [Source N] for any specific information referenced."
        ),
        "messages": [{
            "role": "user",
            "content": (
                f"Context:\n\n{context}\n\n"
                f"---\n\Question: {query}\n\n"
                "Answer clearly and in detail, relying strictly on the provided context only."
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
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)

        query = body.get("query", "").strip()
        if not query:
            return _api_response(400, {"error": "Missing 'query' parameter"})

        logger.info(f"Query received: {query[:100]}...")

        # Step 1: Embed original query
        query_embedding = get_embedding(query)

        # Step 2: Check semantic cache
        cached = check_cache(query_embedding)
        if cached:
            return _api_response(200, cached)

        # Step 3: HyDE
        domain_id = _find_closest_domain(query_embedding)
        if domain_id is None:
            logger.info("Query rejected: does not match any known domain.")
            return _api_response(200, {
                "response": "The question does not appear to be relevant to the available documentation.",
                "sources": [],
                "cached": False
        })
        style_chunks = get_style_chunks_by_domain(domain_id)
        hypothetical_doc = generate_hypothetical_document(query, style_chunks)
        hyde_embedding   = get_embedding(hypothetical_doc)

        # Step 4: Vector search with HyDE embedding
        candidates = vector_search(hyde_embedding, top_k=RETRIEVAL_TOP_K)

        if not candidates:
            return _api_response(200, {
                "response": "I could not find any relevant documents to answer the question.",
                "sources":  [],
                "cached":   False,
            })

        # Step 5: Rerank with original query
        top_chunks = rerank(query, candidates, top_n=RERANK_TOP_N)

        # Step 6: Generate response
        response_text = generate_response(query, top_chunks)

        # Step 7: Build sources
        sources = [{
            "file_name":    c["file_name"],
            "page_number":  c["page_number"],
            "chunk_type":   c["chunk_type"],
            "rerank_score": round(c["rerank_score"], 3),
            "snippet":      c["content"][:200],
        } for c in top_chunks]

        # Step 8: Cache
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
