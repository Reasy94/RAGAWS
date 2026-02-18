resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn = aws_sqs_queue.doc_processing_queue.arn
  function_name    = aws_lambda_function.process_doc.arn
  
  # Ridotto a 5 per bilanciare velocità e rischio timeout con ONNX
  batch_size = 5 

  # Finestra di accumulo per ottimizzare i costi (meno invocazioni)
  maximum_batching_window_in_seconds = 20

  # Report dei fallimenti parziali: se 1 PDF su 5 fallisce, 
  # solo quello torna in coda, non tutti e 5.
  function_response_types = ["ReportBatchItemFailures"]

  enabled = true
}