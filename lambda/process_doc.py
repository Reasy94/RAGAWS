import boto3
import os
import logging
import time
import onnxruntime as ort
from tokenizers import Tokenizer
import seed_initialize

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- Env Variables ---
BUCKET_MODELS = os.environ.get('BUCKET_MODELS')
MODEL_KEY = os.environ.get('MODEL_KEY', 'models/model.onnx')
TOKENIZER_KEY = os.environ.get('TOKENIZER_KEY', 'models/tokenizer.json')

class AIModel:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIModel, cls).__new__(cls)
            cls._instance.tokenizer = None
            cls._instance.session = None
        return cls._instance

    def is_loaded(self):
        return self.tokenizer is not None and self.session is not None

    def load(self):
        if self.is_loaded():
            return

        s3 = boto3.client('s3')
        tmp_model = '/tmp/model.onnx'
        tmp_tokenizer = '/tmp/tokenizer.json'

        try:
            logger.info(f"Download model from S3 bucket: {BUCKET_MODELS}...")
            
            if not os.path.exists(tmp_tokenizer):
                s3.download_file(BUCKET_MODELS, TOKENIZER_KEY, tmp_tokenizer)
            if not os.path.exists(tmp_model):
                s3.download_file(BUCKET_MODELS, MODEL_KEY, tmp_model)

            self.tokenizer = Tokenizer.from_file(tmp_tokenizer)
            self.session = ort.InferenceSession(tmp_model)
            logger.info("Modello e Tokenizer caricati correttamente in memoria.")
            
        except Exception as e:
            logger.error(f"Errore fatale nel caricamento del modello: {str(e)}")
            raise e

# global instance for Cold Start
ai_model = AIModel()

def lambda_handler(event, context):
    start_time = time.time()
    
    try:
        if event.get("action") == "seed":
            return seed_initialize.seed()
        ai_model.load()

        # 2. Parsing dell'evento S3 (il file appena caricato)
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        file_key = event['Records'][0]['s3']['object']['key']
        logger.info(f"Elaborazione file: {file_key} dal bucket: {bucket_name}")

        # 3. Lettura del testo dal documento
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=bucket_name, Key=file_key)
        document_text = response['Body'].read().decode('utf-8')

        # 4. Generazione Embedding
        # Trasformiamo il testo in ID numerici
        encoding = ai_model.tokenizer.encode(document_text)
        
        # Eseguiamo il modello ONNX
        inputs = {ai_model.session.get_inputs()[0].name: [encoding.ids]}
        outputs = ai_model.session.run(None, inputs)
        
        # Estraiamo il vettore (embedding)
        # Per BGE-micro, prendiamo l'ultimo strato (solitamente index 0)
        embeddings = outputs[0][0][0].tolist() 

        duration = time.time() - start_time
        logger.info(f"Embedding generato con successo in {duration:.2f}s. Dimensione: {len(embeddings)}")

        # TODO: Prossimo step -> Inviare a OpenSearch
        return {
            "statusCode": 200,
            "body": {
                "message": "Embedding creato",
                "key": file_key,
                "vector_preview": embeddings[:5] # Mostriamo solo i primi 5 valori nei log
            }
        }

    except Exception as e:
        logger.error(f"Errore durante l'elaborazione del file {file_key}: {str(e)}")
        return {
            "statusCode": 500,
            "body": str(e)
        }