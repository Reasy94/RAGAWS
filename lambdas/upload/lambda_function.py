import json
import boto3
import os
import uuid
from datetime import datetime, timezone

from shared.config import (URL_FRONTEND)

s3_client = boto3.client("s3")
BUCKET = os.environ["S3_BUCKET"]


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        filename = body.get("filename")
        content_type = body.get("content_type", "application/pdf")

        if not filename:
            return {
                "statusCode": 400,
                "headers": cors_headers(),
                "body": json.dumps({"error": "filename is required"}),
            }

        if not filename.lower().endswith(".pdf"):
            return {
                "statusCode": 400,
                "headers": cors_headers(),
                "body": json.dumps({"error": "only PDF files are allowed"}),
            }

        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        s3_key = f"ingestion/{timestamp}_{unique_id}_{filename}"

        upload_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET,
                "Key": s3_key,
                "ContentType": content_type,
            },
            ExpiresIn=600,
        )

        return {
            "statusCode": 200,
            "headers": cors_headers(),
            "body": json.dumps({
                "upload_url": upload_url,
                "s3_key": s3_key,
            }),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": cors_headers(),
            "body": json.dumps({"error": str(e)}),
        }


def cors_headers():
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": URL_FRONTEND,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }