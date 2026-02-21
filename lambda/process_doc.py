import boto3
import os
import logging
import json
import psycopg2
import onnxruntime as ort
from tokenizers import Tokenizer
import io
import hashlib
import pdfplumber  # Assicurati che sia incluso nel layer della Lambda

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Container Paths ---
MODEL_PATH = '/var/task/models/model.onnx'
TOKENIZER_PATH = '/var/task/models/tokenizer.json'

# --- Global Constants ---
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50  # Piccola sovrapposizione per non perdere contesto tra chunk

class AIModel:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIModel, cls).__new__(cls)
            cls._instance.tokenizer = None
            cls._instance.session = None
        return cls._instance

    def load(self):
        if self.tokenizer is not None and self.session is not None:
            return
        self.tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
        self.session = ort.InferenceSession(MODEL_PATH)

    def get_embedding(self, text):
        encoding = self.tokenizer.encode(text)
        ids = encoding.ids[:512] 
        inputs = {self.session.get_inputs()[0].name: [ids]}
        outputs = self.session.run(None, inputs)
        return outputs[0][0][0].tolist()

ai_model = AIModel()

def calculate_file_hash(data):
    """Genera l'impronta digitale univoca del file"""
    return hashlib.sha256(data).hexdigest()

def get_db_config():
    secret_arn = os.environ.get('SECRET_ARN')
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response['SecretString'])
    return {
        "host": secret['host'],
        "database": secret['db_name'],
        "user": secret['username'],
        "password": secret['password'],
        "port": secret.get('port', 5432)
    }

DB_CONFIG = get_db_config()

def lambda_handler(event, context):
    ai_model.load()
    batch_item_failures = []

    for record in event.get('Records', []):
        try:
            s3_event = json.loads(record['body'])
            for s3_record in s3_event.get('Records', []):
                bucket = s3_record['s3']['bucket']['name']
                key = s3_record['s3']['object']['key']
                process_single_file(bucket, key)
        except Exception as e:
            logger.error(f"Errore messaggio {record['messageId']}: {e}")
            batch_item_failures.append({"itemIdentifier": record['messageId']})

    return {"batchItemFailures": batch_item_failures}

def process_single_file(bucket, key):
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket, Key=key)
    file_content = response['Body'].read()
    
    # 1. Calcolo Hash (Identità del file)
    file_hash = calculate_file_hash(file_content)
    all_chunks_data = []

    # 2. Estrazione Testo per Pagina
    if key.lower().endswith('.pdf'):
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            for page in pdf.pages:
                page_num = page.page_number
                text = page.extract_text() or ""
                
                # --- [PROSSIMO STEP]: Qui chiamerai Gemini Flash se trovi grafici ---
                # if page.images: visual_desc = call_gemini(page.to_image())
                
                # 3. Chunking della pagina
                # Usiamo uno split semplice (o RecursiveCharacterTextSplitter se lo importi)
                page_chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP)]
                
                for idx, content in enumerate(page_chunks):
                    if len(content.strip()) < 15: continue
                    
                    all_chunks_data.append({
                        'file_hash': file_hash,
                        'page_num': page_num,
                        'chunk_id': idx + 1,  # Ricomincia da 1 per ogni pagina
                        'content': content,
                        'vector': ai_model.get_embedding(content)
                    })
    else:
        # Gestione altri file (TXT/etc) come "Pagina 1"
        text = file_content.decode('utf-8')
        page_chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP)]
        for idx, content in enumerate(page_chunks):
            all_chunks_data.append({
                'file_hash': file_hash, 'page_num': 1, 'chunk_id': idx + 1,
                'content': content, 'vector': ai_model.get_embedding(content)
            })

    if all_chunks_data:
        save_to_rds(key, file_hash, all_chunks_data)

def save_to_rds(file_name, file_hash, chunks):
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Inserimento File (Genitore)
        # Se l'hash esiste già, aggiorniamo solo il timestamp
        cur.execute("""
            INSERT INTO fileIngested (file_hash, file_name, id_domain, embedding_model, ingested_from)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE SET ingested_at = CURRENT_TIMESTAMP
        """, (file_hash, file_name, 1, "bge-micro-v2", "S3_Lambda_Processor"))

        # Inserimento Chunk (Figli) con Chiave Composta
        # Usiamo ON CONFLICT per evitare duplicati se la Lambda riesegue
        insert_query = """
            INSERT INTO chunks (file_hash, page_number, chunk_id, content, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_hash, page_number, chunk_id) DO UPDATE SET content = EXCLUDED.content;
        """
        
        batch_values = [
            (c['file_hash'], c['page_num'], c['chunk_id'], c['content'], c['vector']) 
            for c in chunks
        ]
        
        cur.executemany(insert_query, batch_values)
        conn.commit()
        logger.info(f"Successo: {file_name} -> {len(chunks)} chunks salvati.")

    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Errore DB: {e}")
        raise e
    finally:
        if conn: conn.close()