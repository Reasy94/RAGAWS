# ─── CODEBUILD ────────────────────────────────────────────────────────────────

resource "aws_codebuild_project" "terraform_apply" {
  name         = "${var.project_name}-terraform-deploy"
  description  = "Build layers, run Terraform, seed DB"
  service_role = aws_iam_role.codebuild_role.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type = "BUILD_GENERAL1_SMALL"
    image        = "aws/codebuild/standard:7.0"
    type         = "LINUX_CONTAINER"

    environment_variable {
      name  = "TF_VAR_rds_rag_username"
      value = var.rds_rag_username
    }

    environment_variable {
      name  = "ARTIFACTS_BUCKET"
      value = aws_s3_bucket.rag_documents.id
    }
  }

  source {
    type            = "GITHUB"
    location        = "https://github.com/Reasy94/RAGAWS"
    git_clone_depth = 1
  }
}


# ─── CODEBUILD IAM ───────────────────────────────────────────────────────────

resource "aws_iam_role" "codebuild_role" {
  name = "${var.project_name}-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "codebuild.amazonaws.com" }
    }]
  })
}

# NOTE: AdministratorAccess is used for simplicity in a prototype.
# In production, scope down to specific Terraform resources.
resource "aws_iam_role_policy_attachment" "codebuild_admin" {
  role       = aws_iam_role.codebuild_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
