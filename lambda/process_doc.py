import boto3
import os
import logging
import json
import psycopg2
import onnxruntime as ort
from tokenizers import Tokenizer
import seed_initialize

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Container Paths ---
MODEL_PATH = '/var/task/models/model.onnx'
TOKENIZER_PATH = '/var/task/models/tokenizer.json'

# --- Database Config ---
DB_CONFIG = {
    "host": os.environ.get('DB_HOST'),
    "database": os.environ.get('DB_NAME', 'ragdb'),
    "user": os.environ.get('DB_USER', 'postgres'),
    "password": os.environ.get('DB_PASS')
}

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
        try:
            logger.info(f"Loading AI Model from: {MODEL_PATH}")
            self.tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
            self.session = ort.InferenceSession(MODEL_PATH)
            logger.info("AI Assets loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize AI Model: {str(e)}")
            raise e

ai_model = AIModel()

def lambda_handler(event, context):
    # This list will track which messages failed to process
    batch_item_failures = []
    
    # 1. Check for Seed Action (Single Trigger)
    if event.get("action") == "seed":
        logger.info("Manual action: Seeding database...")
        return seed_initialize.seed()
    
    # Pre-load model (Singleton)
    ai_model.load()

    # 2. Process Batch
    for record in event.get('Records', []):
        message_id = record['messageId']
        try:
            # Parse SQS message body (contains S3 event)
            s3_event = json.loads(record['body'])
            
            for s3_record in s3_event.get('Records', []):
                bucket_name = s3_record['s3']['bucket']['name']
                file_key = s3_record['s3']['object']['key']
                
                logger.info(f"Processing message {message_id} for file: {file_key}")

                # Processing Logic
                process_single_file(bucket_name, file_key)
                
        except Exception as e:
            logger.error(f"Partial failure for message {message_id}: {str(e)}")
            # If ANY sub-step fails, we mark this specific SQS message as failed
            batch_item_failures.append({"itemIdentifier": message_id})

    # 3. Report Success/Failure to SQS
    # If the list is empty, SQS deletes all messages. 
    # If not, SQS retries ONLY the failed ones.
    return {"batchItemFailures": batch_item_failures}

def process_single_file(bucket, key):
    """Encapsulated logic for text extraction, embedding, and RDS storage"""
    s3 = boto3.client('s3')
    
    # Download content
    response = s3.get_object(Bucket=bucket, Key=key)
    text = response['Body'].read().decode('utf-8')

    # Inference
    encoding = ai_model.tokenizer.encode(text)
    inputs = {ai_model.session.get_inputs()[0].name: [encoding.ids]}
    outputs = ai_model.session.run(None, inputs)
    vector = outputs[0][0][0].tolist()

    # Database Persistence
    save_to_rds(key, text, vector)

def save_to_rds(file_key, chunks_data, vector_domain_comparison):
    model_name = "bge-micro-v2"
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        logger.info("Connected to RDS successfully.")
        # Find ID domain based on vector similarity (pgvector <=> operator)
        cur.execute("""
            SELECT id_domain FROM domains 
            ORDER BY embedding_domain <=> %s::vector 
            LIMIT 1;
        """, (vector_domain_comparison,))
        id_domain = cur.fetchone()[0]

        # Insert File into fileIngested table and return id_file for chunk association
        cur.execute("""
            INSERT INTO fileIngested (id_domain, file_name, embedding_model, ingested_from)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (file_name) DO UPDATE SET ingested_at = CURRENT_TIMESTAMP
            RETURNING id_file;
        """, (id_domain, file_key, model_name, "S3_Bucket_Scraper"))
        
        id_file = cur.fetchone()[0]


        cur.execute("DELETE FROM chunks WHERE id_file = %s;", (id_file,))
        
        insert_query = """
            INSERT INTO chunks (id_file, content, embedding)
            VALUES (%s, %s, %s);
        """
        batch_data = [(id_file, c['content'], c['vector']) for c in chunks_data]
        cur.executemany(insert_query, batch_data)

        conn.commit()
        logger.info(f"Successfully ingested {file_key} with {len(batch_data)} chunks.")
        
    except Exception as e:
        if conn: conn.rollback()
        logger.error(f"Failed to save to RDS: {str(e)}")
        raise e
    finally:
        if conn: cur.close(); conn.close()