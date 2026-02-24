# ─── LAMBDA LAYERS ─────────────────────────────────────────────────────────────

data "archive_file" "shared_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../layers/shared"
  output_path = "${path.module}/builds/shared_layer.zip"
}

resource "aws_lambda_layer_version" "shared" {
  layer_name          = "${var.project_name}-shared-utils"
  filename            = data.archive_file.shared_layer.output_path
  source_code_hash    = data.archive_file.shared_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
  description         = "Shared utilities: DB connection, embeddings, config"
}

resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "${var.project_name}-python-deps"
  s3_bucket           = aws_s3_bucket.rag_documents.id
  s3_key              = "layers/dependencies.zip"
  compatible_runtimes = ["python3.12"]
  description         = "Python dependencies: psycopg2, pdfplumber, fitz, numpy, etc."
}


# ─── LAMBDA: INGESTION ────────────────────────────────────────────────────────

data "archive_file" "ingestion" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/ingestion"
  output_path = "${path.module}/builds/ingestion.zip"
}

resource "aws_lambda_function" "ingestion" {
  function_name    = "${var.project_name}-ingestion"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.ingestion.output_path
  source_code_hash = data.archive_file.ingestion.output_base64sha256
  role             = aws_iam_role.ingestion_role.arn

  reserved_concurrent_executions = 5

  layers = [
    aws_lambda_layer_version.shared.arn,
    aws_lambda_layer_version.dependencies.arn,
  ]

  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
    }
  }

  timeout     = 300
  memory_size = 2048
}

resource "aws_lambda_event_source_mapping" "sqs_to_ingestion" {
  event_source_arn                   = aws_sqs_queue.doc_processing_queue.arn
  function_name                      = aws_lambda_function.ingestion.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}


# ─── LAMBDA: RETRIEVAL ────────────────────────────────────────────────────────

data "archive_file" "retrieval" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/retrieval"
  output_path = "${path.module}/builds/retrieval.zip"
}

resource "aws_lambda_function" "retrieval" {
  function_name    = "${var.project_name}-retrieval"
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.retrieval.output_path
  source_code_hash = data.archive_file.retrieval.output_base64sha256
  role             = aws_iam_role.retrieval_role.arn

  layers = [
    aws_lambda_layer_version.shared.arn,
    aws_lambda_layer_version.dependencies.arn,
  ]

  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.db_credentials.arn
    }
  }

  timeout     = 30
  memory_size = 512
}


# ─── API GATEWAY (Retrieval) ──────────────────────────────────────────────────

resource "aws_apigatewayv2_api" "retrieval_api" {
  name          = "${var.project_name}-retrieval-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["Content-Type"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.retrieval_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "retrieval_integration" {
  api_id                 = aws_apigatewayv2_api.retrieval_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.retrieval.invoke_arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "retrieval_route" {
  api_id    = aws_apigatewayv2_api.retrieval_api.id
  route_key = "POST /query"
  target    = "integrations/${aws_apigatewayv2_integration.retrieval_integration.id}"
}

resource "aws_lambda_permission" "apigw_invoke_retrieval" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.retrieval.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.retrieval_api.execution_arn}/*/*"
}
