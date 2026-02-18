# --- ROLE: SCRAPER ---
resource "aws_iam_role" "scraper_role" {
  name = "${var.project_name}-scraper-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "scraper_policy" {
  name = "${var.project_name}-scraper-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.ingestion_url_queue.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = ["${aws_s3_bucket.rag_documents.arn}/ingestion/*"]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "scraper_attach" {
  role       = aws_iam_role.scraper_role.name
  policy_arn = aws_iam_policy.scraper_policy.arn
}

resource "aws_iam_role_policy_attachment" "scraper_basic" {
  role       = aws_iam_role.scraper_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}



# --- ROLE: PROCESSOR ---
resource "aws_iam_role" "processor_role" {
  name = "${var.project_name}-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "processor_policy" {
  name = "${var.project_name}-processor-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.doc_processing_queue.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.rag_documents.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["es:ESHttpPost", "es:ESHttpPut", "es:ESHttpGet"]
        Resource = ["${aws_opensearch_domain.rag_db.arn}/*"]
      },
      {
  	Effect: "Allow",
  	Action: "secretsmanager:GetSecretValue",
  	Resource: "${aws_secretsmanager_secret.opensearch_auth.arn}"
      }
    ]
  })
}


resource "aws_iam_role_policy_attachment" "processor_attach" {
  role       = aws_iam_role.processor_role.name
  policy_arn = aws_iam_policy.processor_policy.arn
}

resource "aws_iam_role_policy_attachment" "processor_basic" {
  role       = aws_iam_role.processor_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}