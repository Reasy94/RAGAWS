resource "aws_sqs_queue" "doc_processing_queue" {
  name                      = "${var.project_name}-main-queue"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10
  
  visibility_timeout_seconds = 310

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.doc_processing_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "doc_processing_dlq" {
  name = "${var.project_name}-dlq"
}