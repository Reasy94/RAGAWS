data "aws_caller_identity" "current" {}

# ─── S3 BUCKET ────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "rag_documents" {
  bucket = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
}

# Blocca qualsiasi accesso pubblico
resource "aws_s3_bucket_public_access_block" "rag_documents" {
  bucket                  = aws_s3_bucket.rag_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Encryption AES256
resource "aws_s3_bucket_server_side_encryption_configuration" "rag_documents" {
  bucket = aws_s3_bucket.rag_documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Versioning abilitato
resource "aws_s3_bucket_versioning" "rag_documents" {
  bucket = aws_s3_bucket.rag_documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 notification → SQS quando nuovi doc caricati in ingestion/
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.rag_documents.id

  queue {
    queue_arn     = aws_sqs_queue.doc_processing_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "ingestion/data/"
  }
}

resource "aws_sqs_queue_policy" "allow_s3" {
  queue_url = aws_sqs_queue.doc_processing_queue.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.doc_processing_queue.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_s3_bucket.rag_documents.arn } }
    }]
  })
}