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

variable "opensearch_admin_username" {
  description = "Administrative username for OpenSearch cluster authentication"
  type        = string
  default     = "RAGUser"
}

variable "opensearch_admin_password" {
  description = "Administrative password for the OpenSearch RAGUser"
  sensitive   = true
}