# Layer codice condiviso — semplice zip
data "archive_file" "shared_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../layers/shared"
  output_path = "${path.module}/builds/shared_layer.zip"
}

resource "aws_lambda_layer_version" "shared" {
  layer_name          = "shared-utils"
  filename            = data.archive_file.shared_layer.output_path
  source_code_hash    = data.archive_file.shared_layer.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

# Layer dipendenze — build in CodeBuild
resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "python-dependencies"
  s3_bucket           = aws_s3_bucket.artifacts.id
  s3_key              = "layers/dependencies.zip"
  compatible_runtimes = ["python3.12"]
}