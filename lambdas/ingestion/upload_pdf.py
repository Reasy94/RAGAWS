import os
import requests
import boto3
import logging
import uuid
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# Logger configuration
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class PDFDownloader:
    def __init__(self, bucket_name):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        self.s3_folder = "ingestion/"
        self.session = requests.Session()
        retries = Retry(
            total=3, 
            backoff_factor=1, 
            status_forcelist=[502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def process_url(self, url, s3_key):
        try:
            if not s3_key.lower().endswith('.pdf'):
                s3_key += '.pdf'
                
            logger.info(f"Starting download for URL: {url}")
            
            response = self.session.get(url, timeout=(5, 30), stream=True)
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' not in content_type:
                logger.warning(f"Skipping {url}: Invalid Content-Type ({content_type})")
                return False

            full_key = f"{self.s3_folder}{s3_key}"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=full_key,
                Body=response.content,
                ContentType='application/pdf',
                Metadata={'source-url': url}
            )
            logger.info(f"Successfully uploaded to S3: {full_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to process {url}. Error: {str(e)}")
            # Re-raising exception ensures SQS visibility timeout kicks in for retry
            raise e

def lambda_handler(event, context):
    """
    AWS Lambda entry point. 
    Triggered by SQS messages containing PDF URLs.
    """
    bucket = os.environ.get('BUCKET_OUTPUT')
    if not bucket:
        logger.critical("Environment variable 'BUCKET_OUTPUT' is missing!")
        return {"status": "error", "message": "Configuration missing"}

    downloader = PDFDownloader(bucket)
    
    # Track results in the batch
    success_count = 0
    records = event.get('Records', [])
    logger.info(f"Received batch of {len(records)} records from SQS")

    for record in records:
        # The URL is passed as the plain text body of the SQS message
        url = record['body'].strip()
        
        if not url:
            logger.warning("Empty message body received, skipping.")
            continue

        # Generate a unique filename to avoid collisions during concurrent execution
        unique_filename = f"doc_{uuid.uuid4().hex[:12]}.pdf"
        
        try:
            if downloader.process_url(url, unique_filename):
                success_count += 1
        except Exception:
            # If one fails, the batch might be retried depending on SQS config
            continue
    
    logger.info(f"Batch processing finished. Success: {success_count}/{len(records)}")
    
    return {
        "status": "completed",
        "processed": success_count,
        "total": len(records)
    }