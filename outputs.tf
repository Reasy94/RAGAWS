# Il nome del bucket dove caricherai i tuoi PDF
output "s3_bucket_name" {
  value = aws_s3_bucket.rag_documents.id
}

# L'indirizzo del database (ti servirà per configurare la Lambda o DBeaver)
output "rds_endpoint" {
  value = aws_db_instance.rag_db.endpoint
}

# L'ID del segreto dove AWS ha salvato la password generata casualmente
output "secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}