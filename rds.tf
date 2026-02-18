resource "random_password" "db_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "rag/rds/credentials-v1"
  description = "RAG DB Vector Credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_credentials_val" {
  secret_id     = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.rds_rag_username
    password = random_password.db_password.result
    engine   = "postgres"
    host     = aws_db_instance.rag_db.address
    port     = 5432
    db_name  = "ragdb"
  })
}

resource "aws_db_instance" "rag_db" {
  allocated_storage      = 20
  db_name                = "ragdb"
  engine                 = "postgres"
  engine_version         = "16.1"
  instance_class         = "db.t3.micro"
  
  username               = var.rds_rag_username
  password               = random_password.db_password.result

  parameter_group_name   = "default.postgres16"
  skip_final_snapshot    = true
  publicly_accessible    = false
  db_subnet_group_name   = aws_db_subnet_group.rds_subnet_group.name  
  vpc_security_group_ids = [aws_security_group.rds_sg.id]	
}

resource "aws_security_group" "rds_sg" {
  name        = "rds_sg"
  description = "Postgres Traffic"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block] 
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


