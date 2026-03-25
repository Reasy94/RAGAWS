import json
import logging
import numpy as np
import boto3
import time

from rank_bm25 import BM25Okapi
from shared.config import (
    NOVA_PRO_MODEL_ID,
    RETRIEVAL_TOP_K,
    CACHE_SIMILARITY,
    CACHE_TTL_HOURS,
    BUCKET_NAME
)
from shared.db import get_conn, put_conn
from shared.embeddings import get_embedding, _find_closest_domain

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client("bedrock-runtime")

# ── In-memory warm cache (reused across hot Lambda instances) ─────────────────
_domain_chunks_cache: dict[int, list[dict]] = {}
_domain_bm25_cache:   dict[int, BM25Okapi]  = {}

VECTOR_BROAD_K = 20
BM25_BROAD_K   = 20
RRF_K          = 60


# ══════════════════════════════════════════════════════════════════════════════
# SEMANTIC CACHE
# ══════════════════════════════════════════════════════════════════════════════

def check_cache(query_embedding: list[float]) -> dict | None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT answer, sources,
                   1 - (query_embedding <=> %s::vector) AS similarity
            FROM rag.query_cache
            WHERE created_at > NOW() - INTERVAL '%s hours'
            ORDER BY query_embedding <=> %s::vector
            LIMIT 1
        """, (query_embedding, CACHE_TTL_HOURS, query_embedding))
        row = cur.fetchone()
        if row and row[2] >= CACHE_SIMILARITY:
            logger.info(f"Cache HIT (similarity: {row[2]:.3f})")
            return {
                "response": row[0],
                "sources":  json.loads(row[1]) if isinstance(row[1], str) else row[1],
                "cached":   True,
            }
        logger.info("Cache query MISS")
        return None
    except Exception as e:
        logger.warning(f"Cache check failed: {e}")
        return None
    finally:
        put_conn(conn)


def store_cache(
    query_text:      str,
    query_embedding: list[float],
    response:        str,
    sources:         list[dict],
) -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO rag.query_cache (query_text, query_embedding, response, sources)
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
        try:
            conn.rollback()
        except Exception:
            pass
        logger.warning(f"Cache store failed: {e}")
    finally:
        put_conn(conn)


# ══════════════════════════════════════════════════════════════════════════════
# DOMAIN CHUNK LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _load_domain_chunks(domain_id: int) -> tuple[list[dict], BM25Okapi | None]:
    if domain_id in _domain_chunks_cache:
        logger.info(f"Domain {domain_id}: served from warm cache")
        return _domain_chunks_cache[domain_id], _domain_bm25_cache[domain_id]

    logger.info(f"Domain {domain_id}: loading from RDS...")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.file_hash, c.page_number, c.chunk_id, c.chunk_type,
                   c.content, c.embedding, f.file_name, c.s3_path
            FROM rag.chunks c
            JOIN rag.fileIngested f ON c.file_hash = f.file_hash
            WHERE f.id_domain = %s AND f.status = 'completed'
            ORDER BY c.file_hash, c.page_number, c.chunk_id
        """, (domain_id,))

        chunks = []
        for row in cur.fetchall():
            emb = row[5]
            if isinstance(emb, str):
                emb = json.loads(emb.replace("'", '"'))
            chunks.append({
                "file_hash":   row[0],
                "page_number": row[1],
                "chunk_id":    row[2],
                "chunk_type":  row[3],
                "content":     row[4],
                "embedding":   np.array(emb, dtype=np.float32),
                "file_name":   row[6],
                "s3_path":     row[7],
                "id_domain":   domain_id,
            })
        if not chunks:
            logger.warning(f"Domain {domain_id}: no chunks found")
            return [], None

        tokenized = [c["content"].lower().split() for c in chunks]
        bm25      = BM25Okapi(tokenized)

        _domain_chunks_cache[domain_id] = chunks
        _domain_bm25_cache[domain_id]   = bm25

        logger.info(f"Domain {domain_id}: loaded {len(chunks)} chunks")
        return chunks, bm25

    finally:
        put_conn(conn)


def _get_presigned_url(s3_path: str | None, expiry: int = 3600) -> str | None:
    if not s3_path:
        return None
    try:
        s3 = boto3.client("s3")
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": s3_path},
            ExpiresIn=expiry,
        )
    except Exception as e:
        logger.warning(f"Failed to generate presigned URL: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════════════
# V3 RETRIEVAL — BM25 + Vector → RRF
# ══════════════════════════════════════════════════════════════════════════════

def _vector_search(
    query_embedding: np.ndarray,
    chunks:          list[dict],
    top_k:           int,
) -> list[dict]:
    scores = [
        (
            np.dot(query_embedding, c["embedding"]) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(c["embedding"]) + 1e-9
            ),
            c,
        )
        for c in chunks
    ]
    scores.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scores[:top_k]]


def _bm25_search(
    query:  str,
    chunks: list[dict],
    bm25:   BM25Okapi,
    top_k:  int,
) -> list[dict]:
    scores      = bm25.get_scores(query.lower().split())
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [chunks[i] for i in top_indices if scores[i] > 0]


def _rrf(results_list: list[list[dict]]) -> list[dict]:
    scores    = {}
    chunk_map = {}
    for results in results_list:
        for rank, chunk in enumerate(results):
            key            = (chunk["file_hash"], chunk["page_number"], chunk["chunk_id"])
            scores[key]    = scores.get(key, 0) + 1.0 / (RRF_K + rank + 1)
            chunk_map[key] = chunk
    sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [chunk_map[key] for key in sorted_keys]


def _retrieve_v3(
    query:           str,
    query_embedding: np.ndarray,
    chunks:          list[dict],
    bm25:            BM25Okapi,
) -> list[dict]:
    vec_results  = _vector_search(query_embedding, chunks, top_k=VECTOR_BROAD_K)
    bm25_results = _bm25_search(query, chunks, bm25, top_k=BM25_BROAD_K)
    fused        = _rrf([vec_results, bm25_results])[:RETRIEVAL_TOP_K]
    logger.info(f"V3 RRF returned {len(fused)} chunks")
    return fused


# ══════════════════════════════════════════════════════════════════════════════
# GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def _generate_response(query: str, chunks: list[dict], window_context: str = "") -> str:
    context = "\n\n---\n\n".join(
        f"[{c['file_name']}, p.{c['page_number']}]\n{c['content']}"
        for c in chunks
    )
    conversation_block = (f"\n\n---\n\n{window_context}" if window_context else "")

    body = json.dumps({
        "system": [{"text": (
            "You are an expert financial analyst assistant specializing in World Bank "
            "economic reports specifically the Global Economic Prospects (GEP) and Commodity Markets Outlook (CMO) series. "
            "Answer questions based strictly on the provided context. If the context lacks sufficient information, say so explicitly. "
            "Write in a clear and professional tone."
        )}],
        "messages": [{
            "role": "user",
            "content": [{
                "text": (
                    f"Context:\n\n{context}"
                    f"{conversation_block}\n\n"
                    f"---\nQuestion: {query}\n\n"
                    "Answer clearly and in detail."
                )
            }]
        }],
        "inferenceConfig": {"max_new_tokens": 1024},
    })

    response = bedrock.invoke_model(
        modelId     = NOVA_PRO_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = body,
    )
    raw = json.loads(response["body"].read())
    return raw["output"]["message"]["content"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
# FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════

def _handle_feedback(event) -> dict:
    try:
        body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event.get("body", {})
        query_id   = body.get("query_id")
        feedback   = body.get("feedback")  # True = thumbs up, False = thumbs down

        if query_id is None or feedback is None:
            return _api_response(400, {"error": "Missing query_id or feedback"})

        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE rag.queries_history
                SET feedback = %s
                WHERE id = %s
            """, (feedback, query_id))
            conn.commit()
            logger.info(f"Feedback saved: query_id={query_id} feedback={feedback}")
            return _api_response(200, {"status": "ok"})
        except Exception as e:
            conn.rollback()
            logger.error(f"Feedback DB error: {e}")
            return _api_response(500, {"error": "Internal server error"})
        finally:
            put_conn(conn)

    except Exception as e:
        logger.error(f"Feedback handler error: {e}")
        return _api_response(500, {"error": "Internal server error"})

# ══════════════════════════════════════════════════════════════════════════════
# QUERY HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def _store_query_history(
    session_id: str | None,
    query:      str,
    answer:     str,
    sources:    list[dict],
    latency_ms: int,
    cache_hit:  bool,
) -> int | None:
    """
    Salva la query corrente.
    Se le query normali dopo l'ultimo summary sono >= WINDOW_SIZE,
    genera un summary PRIMA di inserire la query corrente.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        if session_id:
            # Step 1 — Trova l'ultimo summary id
            cur.execute("""
                SELECT COALESCE(MAX(id), 0) FROM rag.queries_history
                WHERE session_id = %s AND is_summary = TRUE
            """, (session_id,))
            last_summary_id = cur.fetchone()[0]

            # Step 2 — Conta le query normali dopo l'ultimo summary
            cur.execute("""
                SELECT COUNT(*) FROM rag.queries_history
                WHERE session_id = %s
                  AND is_summary = FALSE
                  AND id > %s
            """, (session_id, last_summary_id))
            count = cur.fetchone()[0]

            # Step 3 — Se count >= WINDOW_SIZE, genera summary
            if count >= WINDOW_SIZE:
                cur.execute("""
                    SELECT query, answer FROM rag.queries_history
                    WHERE session_id = %s
                      AND is_summary = FALSE
                      AND id > %s
                    ORDER BY created_at ASC
                """, (session_id, last_summary_id))
                to_summarize = [{"query": r[0], "answer": r[1]} for r in cur.fetchall()]

                # Includi il summary precedente se esiste
                if last_summary_id > 0:
                    cur.execute("""
                        SELECT summary FROM rag.queries_history
                        WHERE id = %s
                    """, (last_summary_id,))
                    prev_summary_row = cur.fetchone()
                    if prev_summary_row and prev_summary_row[0]:
                        to_summarize = [{"query": "Previous summary", "answer": prev_summary_row[0]}] + to_summarize

                summary_text = _summarize_history(to_summarize)
                if summary_text:
                    cur.execute("""
                        INSERT INTO rag.queries_history
                            (session_id, is_summary, summary, cache_hit)
                        VALUES (%s, TRUE, %s, FALSE)
                    """, (session_id, summary_text))
                    conn.commit()
                    logger.info(f"Summary generated for session {session_id[:8]}")

        # Step 4 — Inserisci la query corrente
        cur.execute("""
            INSERT INTO rag.queries_history
                (session_id, query, answer, sources, latency_ms, cache_hit, is_summary)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
            RETURNING id
        """, (session_id, query, answer, json.dumps(sources), latency_ms, cache_hit))
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else None

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.warning(f"Failed to store query history: {e}")
        return None
    finally:
        put_conn(conn)


def _load_session_history(session_id: str) -> dict:
    """
    Carica l'ultimo summary + le query successive per la sessione.
    Ritorna: {"summary": str|None, "recent": list[dict]}
    """
    if not session_id:
        return {"summary": None, "recent": []}

    conn = get_conn()
    try:
        cur = conn.cursor()

        # Trova l'ultimo summary
        cur.execute("""
            SELECT id, summary FROM rag.queries_history
            WHERE session_id = %s AND is_summary = TRUE
            ORDER BY id DESC
            LIMIT 1
        """, (session_id,))
        summary_row = cur.fetchone()
        last_summary_id = summary_row[0] if summary_row else 0
        summary_text    = summary_row[1] if summary_row else None

        # Carica le query normali dopo l'ultimo summary
        cur.execute("""
            SELECT query, answer FROM rag.queries_history
            WHERE session_id = %s
              AND is_summary = FALSE
              AND id > %s
            ORDER BY created_at ASC
        """, (session_id, last_summary_id))
        recent = [{"query": row[0], "answer": row[1]} for row in cur.fetchall()]

        return {"summary": summary_text, "recent": recent}

    except Exception as e:
        logger.warning(f"Failed to load session history: {e}")
        return {"summary": None, "recent": []}
    finally:
        put_conn(conn)


# ══════════════════════════════════════════════════════════════════════════════
# WINDOW MEMORY
# ══════════════════════════════════════════════════════════════════════════════

WINDOW_SIZE = 3


def _summarize_history(history: list[dict]) -> str:
    """Riassume la history con Nova Pro."""
    conversation = "\n\n".join(
        f"User: {h['query']}\nAssistant: {h['answer']}"
        for h in history
    )
    body = json.dumps({
        "messages": [
            {
                "role": "user",
                "content": [{
                    "text": (
                        "Summarize the following conversation in a concise paragraph "
                        "that captures the key topics discussed and information exchanged. "
                        "This summary will be used as context for future questions.\n\n"
                        f"{conversation}"
                    )
                }]
            }
        ],
        "inferenceConfig": {"max_new_tokens": 300},
    })
    try:
        response = bedrock.invoke_model(
            modelId     = NOVA_PRO_MODEL_ID,
            contentType = "application/json",
            accept      = "application/json",
            body        = body,
        )
        raw = json.loads(response["body"].read())
        return raw["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"Summarization failed: {e}")
        return ""


def _build_window_context(history: dict) -> str:
    """
    Costruisce il contesto della memoria a window.
    history = {"summary": str|None, "recent": list[dict]}
    """
    summary = history.get("summary")
    recent  = history.get("recent", [])

    if not summary and not recent:
        return ""

    parts = []

    if summary:
        parts.append(f"Summary of previous conversation:\n{summary}")

    if recent:
        recent_text = "\n\n".join(
            f"User: {h['query']}\nAssistant: {h['answer']}"
            for h in recent
        )
        parts.append(f"Recent conversation:\n\n{recent_text}")

    return "\n\n---\n\n".join(parts)
# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def lambda_handler(event, context):
    path = event.get("rawPath", "")
    if path == "/feedback":
        return _handle_feedback(event)
    try:
        raw_body = event.get("body")
        if raw_body is None:
            body = event
        elif isinstance(raw_body, str):
            body = json.loads(raw_body)
        else:
            body = raw_body

        query = body.get("query", "").strip()
        session_id = body.get("session_id")
        
        if not query:
            return _api_response(400, {"error": "Missing 'query' parameter"})

        logger.info(f"Query: {query[:100]}... | session_id: {session_id}")
        start_time = time.time()

        # Step 1 — Embed query
        query_embedding = get_embedding(query)

        # Step 2 — Semantic cache check
        cached = check_cache(query_embedding)
        if cached:
            _store_query_history(
                session_id = session_id,
                query      = query,
                answer     = cached["response"],
                sources    = cached["sources"],
                latency_ms = int((time.time() - start_time) * 1000),
                cache_hit  = True,
            )
            return _api_response(200, cached)

        # Step 3 — Domain detection
        domain_id = _find_closest_domain(np.array(query_embedding, dtype=np.float32))
        if domain_id is None:
            return _api_response(200, {
                "response": "The question does not appear to be relevant to the available documentation.",
                "sources":  [],
                "cached":   False,
            })

        # Step 4 — Load domain chunks (warm cache on hot instances)
        chunks, bm25 = _load_domain_chunks(domain_id)
        if not chunks:
            return _api_response(200, {
                "response": "I could not find any relevant documents to answer the question.",
                "sources":  [],
                "cached":   False,
            })

        # Step 5 — V3: BM25 + Vector → RRF
        top_chunks = _retrieve_v3(
            query,
            np.array(query_embedding, dtype=np.float32),
            chunks,
            bm25,
        )

        if not top_chunks:
            return _api_response(200, {
                "response": "I could not find any relevant documents to answer the question.",
                "sources":  [],
                "cached":   False,
            })

        # Step 6 — Load session history + build window context
        history        = _load_session_history(session_id)
        window_context = _build_window_context(history)
        response_text = _generate_response(query, top_chunks, window_context)

        latency_ms = int((time.time() - start_time) * 1000)

        # Step 8 — Build sources
        sources = [
            {
                "file_name":   c["file_name"],
                "page_number": c["page_number"],
                "chunk_type":  c["chunk_type"],
                "snippet":     c["content"][:200],
                "image_url":   _get_presigned_url(c.get("s3_path")) if c["chunk_type"] in ("FIGURE", "TABLE") else None,
            }
            for c in top_chunks
        ]

        # Step 9 — Store cache
        store_cache(query, query_embedding, response_text, sources)

        # Step 10 - Store History
        query_id = _store_query_history(
            session_id = session_id,
            query      = query,
            answer     = response_text,
            sources    = sources,
            latency_ms = latency_ms,
            cache_hit  = False,
        )


        return _api_response(200, {
            "response": response_text,
            "sources":  sources,
            "cached":   False,
            "query_id": query_id,
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

