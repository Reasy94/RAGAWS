# ─── LAMBDA: INGESTION ────────────────────────────────────────────────────────

data "archive_file" "ingestion" {
  type        = "zip"
  source_dir  = "${path.module}/../lambdas/ingestion"
  output_path = "${path.module}/builds/ingestion.zip"
}

resource "aws_lambda_function" "ingestion" {
  # ... tutto il resto del codice che hai postato sopra ...
  # Terraform troverà automaticamente "aws_lambda_layer_version.shared" 
  # perché lo ha letto nel file layers.tf
}

# ... e tutto il resto del file ...