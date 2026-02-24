# ─── RDS POSTGRES (pgvector) ──────────────────────────────────────────────────

resource "random_password" "db_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_db_subnet_group" "rds_subnet_group" {
  name       = "${var.project_name}-rds-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
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
  publicly_accessible    = true  # Prototype only — use VPC in production
  db_subnet_group_name   = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}


# ─── SECRETS MANAGER ──────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "rag/rds/credentials-v1"
  description             = "RAG DB Vector Credentials"
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
