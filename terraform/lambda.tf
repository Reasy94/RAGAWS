# ─── LAMBDA: INGESTION ────────────────────────────────────────────────────────

data "archive_file" "ingestion" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/ingestion"
  output_path = "${path.module}/builds/ingestion.zip"
}

resource "aws_lambda_function" "ingestion" {
  function_name    = "${var.project_name}-ingestion"
  filename         = data.archive_file.ingestion.output_path
  source_code_hash = data.archive_file.ingestion.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.ingestion_role.arn
  timeout          = 900
  memory_size      = 2048
  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda_sg.id]
  }
  layers           = [aws_lambda_layer_version.shared.arn, aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
      S3_BUCKET     = aws_s3_bucket.rag_documents.id
      SQS_QUEUE_URL = aws_sqs_queue.doc_processing_queue.url
    }
  }
}

# ─── LAMBDA: RETRIEVAL ────────────────────────────────────────────────────────

data "archive_file" "retrieval" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/retrieval"
  output_path = "${path.module}/builds/retrieval.zip"
}

resource "aws_lambda_function" "retrieval" {
  function_name    = "${var.project_name}-retrieval"
  filename         = data.archive_file.retrieval.output_path
  source_code_hash = data.archive_file.retrieval.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.retrieval_role.arn
  timeout          = 30
  memory_size      = 2048
  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.lambda_sg.id]
  }
  layers           = [aws_lambda_layer_version.shared.arn, aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
    }
  }
}

# ─── LAMBDA: UPLOAD ────────────────────────────────────────────────────────

data "archive_file" "upload" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/upload"
  output_path = "${path.module}/builds/upload.zip"
}

resource "aws_lambda_function" "upload" {
  function_name    = "${var.project_name}-upload"
  filename         = data.archive_file.upload.output_path
  source_code_hash = data.archive_file.upload.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.upload_role.arn
  timeout          = 30
  memory_size      = 256
  layers           = [aws_lambda_layer_version.shared.arn, aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = {
      S3_BUCKET     = aws_s3_bucket.rag_documents.id
    }
  }
}


resource "aws_lambda_event_source_mapping" "sqs_to_ingestion" {
  event_source_arn = aws_sqs_queue.doc_processing_queue.arn
  function_name    = aws_lambda_function.ingestion.arn
  batch_size       = 1
  enabled          = true
}
