# 1. LIGHTWEIGHT LAMBDA (SCRAPER) - OK as ZIP
resource "aws_lambda_function" "scraper_doc" {
  function_name = "${var.project_name}-scraper"
  filename      = data.archive_file.lambda_zip.output_path
  role          = aws_iam_role.scraper_role.arn
  handler       = "scraper.lambda_handler"
  runtime       = "python3.9"

  timeout     = 60
  memory_size = 128
  reserved_concurrent_executions = 10
  
  environment {
    variables = {
      BUCKET_OUTPUT = aws_s3_bucket.rag_documents.id
    }
  }
}

# 2. AI HEAVY LAMBDA (PROCESSOR) - MUST BE DOCKER (IMAGE)
resource "aws_lambda_function" "process_doc" {
  function_name = "${var.project_name}-processor"

  # CHANGE THIS: Use Image instead of filename
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_ai_repo.repository_url}:latest"

  role = aws_iam_role.processor_role.arn
  
  # LIMIT PARALLELISM to protect OpenSearch t3.small
  reserved_concurrent_executions = 5

  environment {
    variables = {
      BUCKET_MODELS   = aws_s3_bucket.rag_documents.id
      MODEL_KEY       = "models/model.onnx"
      TOKENIZER_KEY   = "models/tokenizer.json"
      SQS_QUEUE_URL   = aws_sqs_queue.doc_processing_queue.id
      OPENSEARCH_HOST = "https://${aws_opensearch_domain.rag_db.endpoint}"
    }
  }

  # INCREASE THESE: AI and ONNX need more resources
  timeout     = 300   # 5 minutes
  memory_size = 1024  # 1GB RAM minimum
}