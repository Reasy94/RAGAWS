# SQS 1: For downloading PDF (Scraper)
resource "aws_sqs_queue" "ingestion_url_queue" {
  name                      = "${var.project_name}-url-queue"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10
}

# COSQS A 2: For S3's files (Processor)
resource "aws_sqs_queue" "doc_processing_queue" {
  name                      = "${var.project_name}-main-queue"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.doc_processing_dlq.arn
    maxReceiveCount     = 3
  })
}

# CODA 3: Dead Letter Queue (For error messages)
resource "aws_sqs_queue" "doc_processing_dlq" {
  name = "${var.project_name}-dlq"
}