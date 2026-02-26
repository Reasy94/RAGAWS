terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region  = "eu-central-1"
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "RAG-AWS"
      Environment = "Dev"
      ManagedBy   = "Terraform"
    }
  }
}