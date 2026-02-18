resource "aws_ecr_repository" "lambda_ai_repo" {
  name                 = "${var.project_name}-processor-repo"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true # Controlla automaticamente se ci sono vulnerabilità nell'immagine
  }
}

# Questo output ti servirà per i comandi Docker di push
output "ecr_repository_url" {
  value = aws_ecr_repository.lambda_ai_repo.repository_url
}