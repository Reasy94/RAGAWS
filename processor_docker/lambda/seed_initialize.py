import os
import boto3
import onnxruntime as ort
from tokenizers import Tokenizer
from opensearchpy import OpenSearch, RequestsHttpConnection

# --- CONFIGURATION FROM ENVIRONMENT ---
BUCKET_MODELS = os.environ.get('BUCKET_MODELS')
MODEL_KEY = os.environ.get('MODEL_KEY', 'models/model.onnx')
TOKENIZER_KEY = os.environ.get('TOKENIZER_KEY', 'models/tokenizer.json')
OPENSEARCH_HOST = os.environ.get('OPENSEARCH_HOST') # Make sure to set this

# English Domain Data
domains_data = [
    {
        "name": "hr", 
        "desc": "human resources, employee management, payroll, vacations, recruitment, hiring, labor contracts"
    },
    {
        "name": "legal", 
        "desc": "legal department, contracts, privacy policy, GDPR, compliance, terms of service, regulations"
    },
    {
        "name": "finance", 
        "desc": "accounting, taxes, invoices, expense reports, budget, financial planning, treasury"
    }
]

def get_embedding(text, tokenizer, session):
    # Mirroring your Lambda logic exactly
    encoding = tokenizer.encode(text)
    inputs = {session.get_inputs()[0].name: [encoding.ids]}
    outputs = session.run(None, inputs)
    # CLS Token extraction
    return outputs[0][0][0].tolist()

def seed():
    if not BUCKET_MODELS:
        print("Error: BUCKET_MODELS environment variable is missing!")
        return

    s3 = boto3.client('s3')
    tmp_model = '/tmp/model.onnx'
    tmp_tokenizer = '/tmp/tokenizer.json'

    # Ensure /tmp exists (for local testing)
    os.makedirs('/tmp', exist_ok=True)

    # 1. Download Model and Tokenizer (Same logic as Lambda)
    print(f"Downloading models from S3 bucket: {BUCKET_MODELS}...")
    if not os.path.exists(tmp_tokenizer):
        s3.download_file(BUCKET_MODELS, TOKENIZER_KEY, tmp_tokenizer)
    if not os.path.exists(tmp_model):
        s3.download_file(BUCKET_MODELS, MODEL_KEY, tmp_model)

    tokenizer = Tokenizer.from_file(tmp_tokenizer)
    session = ort.InferenceSession(tmp_model)

    # 2. OpenSearch Connection
    # Replace auth with your actual credentials or IAM signers
    client = OpenSearch(
        hosts=[{'host': OPENSEARCH_HOST, 'port': 443}],
        http_auth=('admin', 'YourPassword123!'), 
        use_ssl=True, 
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

    print(f"Starting seeding process for index 'domain'...")
    for item in domains_data:
        vector = get_embedding(item['desc'], tokenizer, session)
        
        document = {
            "domain_name": item['name'],
            "description": item['desc'],
            "embedding": vector
        }

        # Indexing
        client.index(index='domain', body=document, refresh=True)
        print(f"✅ Indexed domain: {item['name']} (Vector size: {len(vector)})")

if __name__ == "__main__":
    seed()