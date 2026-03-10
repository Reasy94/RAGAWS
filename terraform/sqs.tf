resource "aws_sqs_queue" "doc_processing_queue" {
  name                       = "${var.project_name}-doc-processing"
  visibility_timeout_seconds = 1200
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.doc_processing_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "doc_processing_dlq" {
  name                      = "${var.project_name}-doc-processing-dlq"
  message_retention_seconds = 604800
}
