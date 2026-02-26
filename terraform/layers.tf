# Layer codice condiviso
data "archive_file" "shared_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../layers/shared"
  output_path = "${path.module}/builds/shared_layer.zip"
}

resource "aws_lambda_layer_version" "shared" {
  layer_name          = "${var.project_name}-shared-utils"
  filename            = data.archive_file.shared_layer.output_path
  source_code_hash    = data.archive_file.shared_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

# Layer dipendenze (CodeBuild caricherà lo zip su S3)
resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "${var.project_name}-python-deps"
  s3_bucket           = aws_s3_bucket.rag_documents.id
  s3_key              = "layers/dependencies.zip"
  compatible_runtimes = ["python3.12"]
  skip_destroy        = true
}