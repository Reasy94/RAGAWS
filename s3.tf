data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "rag_documents" {
  bucket = "${var.project_name}-${data.aws_caller_identity.current.account_id}"
  lifecycle {
    prevent_destroy = true # Protezione extra per i tuoi modelli ONNX
  }
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.rag_documents.id

  queue {
    queue_arn     = aws_sqs_queue.doc_processing_queue.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "ingestion/"
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