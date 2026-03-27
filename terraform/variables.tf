variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "rag-aws"
}

variable "rds_rag_username" {
  description = "RDS master username"
  type        = string
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = ""
}

variable "my_ip" {
  description = "My IP to access RDS"
  type        = string
}

variable "bastion_public_key" {
  description = "Public SSH key for bastion host access"
  type        = string
}

variable "github_repo_url" {
  description = "GitHub repository URL for CodeBuild"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-1"
}