import os
import boto3
import psycopg2 # Sostituito OpenSearch con psycopg2
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
    {"name": "hr", "desc": "human resources, employee management, payroll, vacations, recruitment"},
    {"name": "legal", "desc": "legal department, contracts, privacy policy, GDPR, compliance"},
    {"name": "finance", "desc": "accounting, taxes, invoices, expense reports, budget"}
]

def get_embedding(text, tokenizer, session):
    encoding = tokenizer.encode(text)
    inputs = {session.get_inputs()[0].name: [encoding.ids]}
    outputs = session.run(None, inputs)
    return outputs[0][0][0].tolist()

def seed():
    # 1. Download/Load Modelli (Invariato)
    # ... (logica download s3 come prima) ...
    # Assumiamo che i modelli siano in /var/task/models nel container
    tokenizer = Tokenizer.from_file('/var/task/models/tokenizer.json')
    session = ort.InferenceSession('/var/task/models/model.onnx')

    # 2. Connessione a RDS PostgreSQL
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        print("Connected to RDS successfully.")

        # Assicuriamoci che l'estensione pgvector sia attiva e la tabella esista
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS domains (
                id SERIAL PRIMARY KEY,
                domain_name TEXT UNIQUE,
                description TEXT,
                embedding vector(384) -- 384 è la dimensione di BGE-micro
            );
        """)

        print(f"Starting seeding process...")
        for item in domains_data:
            vector = get_embedding(item['desc'], tokenizer, session)
            
            # Query per inserire o aggiornare se il nome dominio esiste già
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