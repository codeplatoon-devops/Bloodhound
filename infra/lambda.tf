/*
infra/lambda.tf

The Bloodhound v2 Lambda function resource.

Key points:
- Code package comes from infra/build.tf (archive_file output)
- Env vars are provided via var.lambda_env (often sourced from terraform.tfvars)
*/

resource "aws_lambda_function" "bloodhound_v2" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "handlers.lambda_function.lambda_handler"
  runtime       = var.lambda_runtime

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout     = var.lambda_timeout_seconds
  memory_size = var.lambda_memory_mb

  environment {
    variables = var.lambda_env
  }
}


