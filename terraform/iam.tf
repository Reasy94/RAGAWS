# ─── INGESTION ROLE ───────────────────────────────────────────────────────────

resource "aws_iam_role" "ingestion_role" {
  name = "${var.project_name}-ingestion-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "ingestion_policy" {
  name = "${var.project_name}-ingestion-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SQSAccess"
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.doc_processing_queue.arn]
      },
      {
        Sid      = "S3ReadDocuments"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = ["${aws_s3_bucket.rag_documents.arn}/*"]
      },
	  {
        Sid      = "S3ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = ["${aws_s3_bucket.rag_documents.arn}"]
      },
      {
        Sid      = "SecretsManagerRead"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.db_credentials.arn]
      },
      {
        Sid    = "MarketplaceSubscription"
        Effect = "Allow"
        Action = [
          "aws-marketplace:Subscribe",
          "aws-marketplace:Unsubscribe",
          "aws-marketplace:ViewSubscriptions"
        ]
        Resource = ["*"]
      },
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = ["kms:Decrypt","kms:DescribeKey"]
        Resource = [aws_kms_key.secrets_key.arn]
      },
      {
        Sid      = "BedrockInvoke"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ingestion_policy_attach" {
  role       = aws_iam_role.ingestion_role.name
  policy_arn = aws_iam_policy.ingestion_policy.arn
}

resource "aws_iam_role_policy_attachment" "ingestion_basic" {
  role       = aws_iam_role.ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "ingestion_vpc" {
  role       = aws_iam_role.ingestion_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# ─── RETRIEVAL ROLE ───────────────────────────────────────────────────────────

resource "aws_iam_role" "retrieval_role" {
  name = "${var.project_name}-retrieval-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "retrieval_policy" {
  name = "${var.project_name}-retrieval-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "SecretsManagerRead"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.db_credentials.arn]
      },
      {
        Sid      = "BedrockInvoke"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = ["*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "retrieval_policy_attach" {
  role       = aws_iam_role.retrieval_role.name
  policy_arn = aws_iam_policy.retrieval_policy.arn
}

resource "aws_iam_role_policy_attachment" "retrieval_basic" {
  role       = aws_iam_role.retrieval_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}


# ─── UPLOAD ROLE ───────────────────────────────────────────────────────────

resource "aws_iam_role" "upload_role" {
  name = "${var.project_name}-upload-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "upload_policy" {
  name = "${var.project_name}-upload-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "S3PutDocuments"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.rag_documents.arn}/ingestion/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "upload_policy_attach" {
  role       = aws_iam_role.upload_role.name
  policy_arn = aws_iam_policy.upload_policy.arn
}

resource "aws_iam_role_policy_attachment" "upload_basic" {
  role       = aws_iam_role.upload_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
