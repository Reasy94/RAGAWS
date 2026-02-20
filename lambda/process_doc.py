import boto3
from botocore.exceptions import ClientError
import os
import logging
import json
import psycopg2
import onnxruntime as ort
from tokenizers import Tokenizer
import seed_initialize
import io
from pypdf import PdfReader

# --- Logger Setup ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Container Paths ---
MODEL_PATH = '/var/task/models/model.onnx'
TOKENIZER_PATH = '/var/task/models/tokenizer.json'

# --- Global Constants ---
DEFAULT_REGION = "eu-central-1"
SECRET_ARN = os.environ.get('SECRET_ARN')

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

import os
import boto3
import json
from botocore.exceptions import ClientError

# --- COSTANTI GLOBALI ---
# Queste sono info strutturali, non segreti.
DEFAULT_REGION = "eu-central-1"
SECRET_ARN = os.environ.get('SECRET_ARN')

def get_db_config():
    region = os.environ.get('AWS_REGION', DEFAULT_REGION)
    if not SECRET_ARN:
        raise ValueError("SECRET_ARN variable is not set in the environment variables.")

    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region)

    try:
        response = client.get_secret_value(SecretId=SECRET_ARN)
        secret = json.loads(response['SecretString'])
        
        return {
            "host": secret['host'],
            "database": secret['db_name'],
            "user": secret['username'],
            "password": secret['password'],
            "port": secret['port']
        }
    except ClientError as e:
        print(f"[ERROR] Cannot retrieve the secret {SECRET_ARN}: {e}")
        raise e

# Esecuzione
DB_CONFIG = get_db_config()

def lambda_handler(event, context):

    batch_item_failures = []
    
    if event.get("action") == "seed":
        logger.info("Manual action: Seeding database...")
        return seed_initialize.seed()
    
    ai_model.load()

    for record in event.get('Records', []):
        message_id = record['messageId']
        try:
            s3_event = json.loads(record['body'])
            for s3_record in s3_event.get('Records', []):
                bucket_name = s3_record['s3']['bucket']['name']
                file_key = s3_record['s3']['object']['key']
                
                logger.info(f"Processing message {message_id} for file: {file_key}")

                process_single_file(bucket_name, file_key)
                
        except Exception as e:
            logger.error(f"Partial failure for message {message_id}: {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})

    # 3. Report Success/Failure to SQS
    # If the list is empty, SQS deletes all messages. 
    # If not, SQS retries ONLY the failed ones.
    return {"batchItemFailures": batch_item_failures}

def process_single_file(bucket, key):
    s3 = boto3.client('s3')
    
    response = s3.get_object(Bucket=bucket, Key=key)
    file_content = response['Body'].read()
    if key.endswith('.pdf'):
        pdf_file = io.BytesIO(file_content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
    else:
        text = file_content.decode('utf-8')
    encoding = ai_model.tokenizer.encode(text)
    inputs = {ai_model.session.get_inputs()[0].name: [encoding.ids]}
    outputs = ai_model.session.run(None, inputs)
    vector = outputs[0][0][0].tolist()

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