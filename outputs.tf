output "s3_bucket_name" {
  value       = aws_s3_bucket.rag_documents.id
  description = "S3 bucket for document uploads"
}

output "db_instance_address" {
  value       = aws_db_instance.rag_db.address
  description = "RDS endpoint"
}

output "db_password" {
  value       = random_password.db_password.result
  sensitive   = true
  description = "RDS password (sensitive)"
}

output "secret_arn" {
  value       = aws_secretsmanager_secret.db_credentials.arn
  description = "Secrets Manager ARN for DB credentials"
}

output "retrieval_api_url" {
  value       = "${aws_apigatewayv2_stage.default.invoke_url}/query"
  description = "POST endpoint for RAG queries"
}
