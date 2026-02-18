variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "rag-storage-project"
}

variable "bucket_models_name" {
  description = "Name of the S3 bucket containing the ONNX models and PDF documents"
  type        = string
  default     = "rag-storage-project-054375299743"
}

variable "rds_rag_username" {
  description = "RAG username for RDS"
  type        = string
  default     = "ragadmin"
}
