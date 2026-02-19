resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = aws_sqs_queue.doc_processing_queue.arn
  function_name    = aws_lambda_function.process_doc.arn
  batch_size       = 10
  maximum_batching_window_in_seconds = 10
  function_response_types = ["ReportBatchItemFailures"]
  enabled = true
}