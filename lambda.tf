# 2. AI HEAVY LAMBDA (PROCESSOR) - DOCKERIZED
resource "aws_lambda_function" "process_doc" {
  function_name = "${var.project_name}-processor"

  # Rimane Image perché usiamo Docker per i modelli pesanti
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.lambda_ai_repo.repository_url}:latest"

  role = aws_iam_role.processor_role.arn
  
  # Abbiamo rimosso il limite di parallelismo stringente (5) 
  # perché RDS gestisce meglio le connessioni rispetto a un t3.small OpenSearch,
  # ma teniamolo a 10 per sicurezza iniziale.
  reserved_concurrent_executions = 10

  environment {
    variables = {
      DB_HOST = aws_db_instance.postgres_db.address
      DB_NAME = aws_db_instance.postgres_db.db_name
      DB_USER = var.rds_rag_username
      DB_PASS = random_password.db_password.result
      
      MODEL_PATH     = "/var/task/models/model.onnx"
      TOKENIZER_PATH = "/var/task/models/tokenizer.json"
      
      SQS_QUEUE_URL  = aws_sqs_queue.doc_processing_queue.id
    }
  }


  timeout     = 300
  memory_size = 2048 

  vpc_config {
    subnet_ids         = aws_subnet.private_subnets[*].id
    security_group_ids = [aws_security_group.lambda_sg.id]
  }
} 	