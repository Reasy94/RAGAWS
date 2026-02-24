variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "rag-aws"
}

variable "rds_rag_username" {
  description = "RDS master username"
  type        = string
  default     = "postgres"
}
