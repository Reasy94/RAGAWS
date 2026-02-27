import os
import logging
import boto3
import psycopg2

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

DB_HOST = os.environ.get('DB_HOST')
DB_NAME = os.environ.get('DB_NAME', 'ragdb')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS')

COHERE_MODEL_ID = "cohere.embed-multilingual-v3"
EMBEDDING_TYPE_DOCUMENT = "search_document"
bedrock = boto3.client("bedrock-runtime")

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

domains_data = [
    {"name": "aws_architecture",       "desc": "AWS whitepapers, cloud infrastructure, serverless, technical guides."},
    {"name": "imf_economics",          "desc": "IMF Working Papers, energy economics, euro area, macroeconomic modeling, potential output."},
    {"name": "world_bank_development", "desc": "World Bank reports, global development, poverty, sustainability, emerging markets."},
]


# ─── EMBEDDING ────────────────────────────────────────────────────────────────

def seed():
    conn = None
    try:
        conn = psycopg2.connect(
            host     = DB_HOST,
            database = DB_NAME,
            user     = DB_USER,
            password = DB_PASS,
        )
        conn.autocommit = False
        cur = conn.cursor()
        print("Connected to RDS successfully.")
        logger.info("Connected to RDS successfully.")

        cur.execute("CREATE SCHEMA IF NOT EXISTS rag;")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector SCHEMA rag;")
        cur.execute("SET search_path TO rag;")

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
            CREATE TABLE IF NOT EXISTS query_cache (
                id SERIAL PRIMARY KEY,
                query_text TEXT NOT NULL,
                answer TEXT,
                sources JSONB,
                query_embedding VECTOR(1024),
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS queries_history (
                id SERIAL PRIMARY KEY,
                original_query TEXT NOT NULL,
                hypotethical_doc TEXT,
                answer TEXT,
                sources JSONB,
                latency_ms INTEGER,
                cache_hit BOOLEAN DEFAULT FALSE,
                feedback BOOLEAN DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)

        print("Starting seeding process...")
        logger.info("Starting seeding process...")

        for item in domains_data:
            vector = get_embedding(item["desc"], EMBEDDING_TYPE_DOCUMENT)
            cur.execute("""
                INSERT INTO domains (domain_name, description, embedding_domain)
                VALUES (%s, %s, %s)
                ON CONFLICT (domain_name) DO NOTHING;
            """, (item["name"], item["desc"], vector))
            print(f"  ✓ Indexed domain: {item['name']}")
            logger.info(f"Indexed domain: {item['name']}")

        conn.commit()
        print("Tables and domains seeded successfully.")
        logger.info("Tables and domains seeded successfully.")
        cur.close()

        # ─── INDICI CONCURRENTLY (fuori transazione) ──────────────────────────
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SET search_path TO rag;")

        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fileingested_id_domain 
            ON fileIngested(id_domain);
        """)
        print("  ✓ Index idx_fileingested_id_domain created")
        logger.info("Index idx_fileingested_id_domain created")

        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS chunks_embedding_hnsw_idx 
            ON chunks USING hnsw (embedding vector_cosine_ops);
        """)
        print("  ✓ Index chunks_embedding_hnsw_idx created")
        logger.info("Index chunks_embedding_hnsw_idx created")

        cur.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS query_cache_embedding_hnsw_idx 
            ON query_cache USING hnsw (query_embedding vector_cosine_ops);
        """)
        print("  ✓ Index query_cache_embedding_hnsw_idx created")
        logger.info("Index query_cache_embedding_hnsw_idx created")

        cur.close()
        conn.close()
        print("Seeding completed successfully.")
        logger.info("Seeding completed successfully.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"  ✗ Database Error: {str(e)}")
        logger.error(f"Database Error: {str(e)}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    seed()