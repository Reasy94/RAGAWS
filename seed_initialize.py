import os
import json
import boto3
import psycopg2

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

DB_HOST = os.environ.get('DB_HOST')
DB_NAME = os.environ.get('DB_NAME', 'ragdb')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS')

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"

bedrock = boto3.client("bedrock-runtime")

domains_data = [
    {"name": "aws_architecture",       "desc": "AWS whitepapers, cloud infrastructure, serverless, technical guides."},
    {"name": "imf_economics",          "desc": "IMF Working Papers, energy economics, euro area, macroeconomic modeling, potential output."},
    {"name": "world_bank_development", "desc": "World Bank reports, global development, poverty, sustainability, emerging markets."},
]


# ─── EMBEDDING ────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    response = bedrock.invoke_model(
        modelId     = TITAN_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = json.dumps({"inputText": text}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]


# ─── SEED ─────────────────────────────────────────────────────────────────────

def seed():
    try:
        conn = psycopg2.connect(
            host     = DB_HOST,
            database = DB_NAME,
            user     = DB_USER,
            password = DB_PASS,
        )
        cur = conn.cursor()
        print("Connected to RDS successfully.")
        cur.execute("CREATE SCHEMA IF NOT EXISTS rag;")
        cur.execute("SET search_path TO rag;")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id_domain        SERIAL PRIMARY KEY,
                domain_name      TEXT UNIQUE,
                description      TEXT,
                embedding_domain vector(1024)
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fileIngested (
                id_file         SERIAL PRIMARY KEY,
                id_domain       INTEGER REFERENCES domains(id_domain) ON DELETE CASCADE,
                file_hash       TEXT UNIQUE,
                file_name       TEXT,
                embedding_model TEXT,
                ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ingested_from   TEXT,
                status          TEXT DEFAULT 'processing'
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                file_hash   TEXT REFERENCES fileIngested(file_hash) ON DELETE CASCADE,
                page_number INTEGER,
                chunk_id    INTEGER,
                chunk_type  TEXT,
                content     TEXT,
                embedding   vector(1024),
                PRIMARY KEY (file_hash, page_number, chunk_id)
            );
        """)
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS chunks_embedding_hnsw_idx 
            ON chunks USING hnsw (embedding vector_cosine_ops);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS query_cache (
                id SERIAL PRIMARY KEY,
                query_text TEXT NOT NULL,
                response TEXT,
                sources JSONB,
                query_embedding VECTOR(1024),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS query_cache_embedding_hnsw_idx 
            ON query_cache USING hnsw (query_embedding vector_cosine_ops);
        """)

        print("Starting seeding process...")
        for item in domains_data:
            vector = get_embedding(item["desc"])
            cur.execute("""
                INSERT INTO domains (domain_name, description, embedding_domain)
                VALUES (%s, %s, %s)
                ON CONFLICT (domain_name) DO NOTHING;
            """, (item["name"], item["desc"], vector))
            print(f"  ✓ Indexed domain: {item['name']}")

        conn.commit()
        cur.close()
        conn.close()
        print("Seeding completed successfully.")

    except Exception as e:
        print(f"  ✗ Database Error: {str(e)}")


if __name__ == "__main__":
    seed()