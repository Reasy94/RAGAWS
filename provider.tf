terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    opensearch = {
      source  = "opensearch-project/opensearch"
      version = "2.2.0"
    }
  }
}

provider "aws" {
  region = "eu-central-1"
}

provider "opensearch" {
  url         = "https://${aws_opensearch_domain.rag_db.endpoint}"
  username    = var.opensearch_admin_username
  password    = var.opensearch_admin_password
}