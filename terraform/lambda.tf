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
  handler          = "main.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.ingestion_role.arn
  timeout          = 300
  memory_size      = 512

  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
      S3_BUCKET     = aws_s3_bucket.rag_documents.id
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
  handler          = "main.handler"
  runtime          = "python3.11"
  role             = aws_iam_role.retrieval_role.arn
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      DB_SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
    }
  }
}