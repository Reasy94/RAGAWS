import json
import boto3
import logging

from shared.config import MAX_INPUT_CHARS, DOMAIN_SIMILARITY_THRESHOLD, COHERE_MODEL_ID
from shared.db import get_conn, put_conn

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_bedrock = None


def _get_bedrock():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def get_embedding(text: str, input_type: str = "search_document") -> list[float]:
    response = _get_bedrock().invoke_model(
        modelId     = COHERE_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = json.dumps({
            "texts": [text],
            "input_type": input_type
        }),
    )
    body = json.loads(response["body"].read())
    return body["embeddings"][0]


def find_closest_domain(centroid: list[float]) -> int | None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id_domain, domain_name,
                   1 - (embedding_domain <=> %s::vector) AS similarity
            FROM domains
            ORDER BY embedding_domain <=> %s::vector
            LIMIT 1
        """, (centroid.tolist(), centroid.tolist()))
        row = cur.fetchone()
        if not row:
            return None

        id_domain, domain_name, similarity = row
        if similarity < DOMAIN_SIMILARITY_THRESHOLD:
            logger.warning(
                f"Closest domain '{domain_name}' similarity {similarity:.3f} "
                f"below threshold {DOMAIN_SIMILARITY_THRESHOLD} → unknown domain"
            )
            return None

        logger.info(f"Domain detected: '{domain_name}' (similarity: {similarity:.3f})")
        return id_domain
    finally:
        put_conn(conn)