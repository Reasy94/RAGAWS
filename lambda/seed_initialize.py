import os
import psycopg2
import onnxruntime as ort
from tokenizers import Tokenizer

# --- CONFIGURATION ---
BUCKET_MODELS = os.environ.get('BUCKET_MODELS')
MODEL_KEY = os.environ.get('MODEL_KEY', 'models/model.onnx')
TOKENIZER_KEY = os.environ.get('TOKENIZER_KEY', 'models/tokenizer.json')

# Credenziali RDS (da passare come variabili d'ambiente nella Lambda)
DB_HOST = os.environ.get('DB_HOST')
DB_NAME = os.environ.get('DB_NAME', 'ragdb')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS')

domains_data = [
    {"name": "aws_architecture", "desc": "AWS whitepapers, cloud infrastructure, serverless, technical guides."},
    {"name": "academic_research", "desc": "ArXiv papers, computer science, AI, machine learning, deep learning."},
    {"name": "global_development", "desc": "World Bank, international economy, poverty, sustainability, policy."}
]

def get_embedding(text, tokenizer, session):
    encoding = tokenizer.encode(text)
    inputs = {session.get_inputs()[0].name: [encoding.ids]}
    outputs = session.run(None, inputs)
    return outputs[0][0][0].tolist()

def seed():
    tokenizer = Tokenizer.from_file('/var/task/models/tokenizer.json')
    session = ort.InferenceSession('/var/task/models/model.onnx')

    # Connection to RDS
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        print("Connected to RDS successfully.")

        # Check if the pgvector extension is available and create the table
        cur.execute("CREATE SCHEMA IF NOT EXISTS rag;")
        cur.execute("SET search_path TO rag;")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id_domain SERIAL PRIMARY KEY,
                domain_name TEXT UNIQUE,
                description TEXT,
                embedding_domain vector(384)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS fileIngested (
            id_file SERIAL PRIMARY KEY,
            id_domain INTEGER FOREIGN KEY REFERENCES domains(id_domain) ON DELETE CASCADE,
            file_name TEXT UNIQUE,
            embedding_model TEXT,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ingested_from TEXT,
            status TEXT DEFAULT 'processing'
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
            file_hash TEXT REFERENCES fileIngested(file_hash) ON DELETE CASCADE,
            page_number INTEGER,
            chunk_id INTEGER,
            chunk_type TEXT,
            content TEXT,
            embedding vector(1024),
            PRIMARY KEY (file_hash, page_number, chunk_id)
            );
        """)
        print(f"Starting seeding process...")
        for item in domains_data:
            vector = get_embedding(item['desc'], tokenizer, session)
            
            query = """
                INSERT INTO domains (domain_name, description, embedding)
                VALUES (%s, %s, %s)
                ON CONFLICT (domain_name) DO NOTHING;
            """
            cur.execute(query, (item['name'], item['desc'], vector))
            print(f"✅ Indexed domain in RDS: {item['name']}")

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Database Error: {str(e)}")

if __name__ == "__main__":
    seed()