resource "aws_secretsmanager_secret" "opensearch_auth" {
  name        = "${var.project_name}/opensearch/creds"
  description = "OpenSearch credentials for RAG"
}

resource "aws_secretsmanager_secret_version" "opensearch_auth_val" {
  secret_id     = aws_secretsmanager_secret.opensearch_auth.id
  secret_string = jsonencode({
    username = var.opensearch_admin_username
    password = var.opensearch_admin_password
  })
}
