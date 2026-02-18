output "ingestion_bucket" {
  value = aws_s3_bucket.rag_documents.id
}

output "sqs_url" {
  value = aws_sqs_queue.doc_processing_queue.id
}