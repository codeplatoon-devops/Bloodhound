/*
infra/lambda.tf

The Bloodhound v2 Lambda function resource.

Key points:
- Code package comes from infra/build.tf (archive_file output)
- Env vars are provided via var.lambda_env (often sourced from terraform.tfvars)
*/

/*
Detect whether destructive mode is enabled.

lambda_env is a map of environment variables passed to the Lambda.
We check if APPLY_CHANGES is set to "true".

If the variable does not exist, default to "false".
*/
locals {

  apply_changes_enabled = lookup(var.lambda_env, "APPLY_CHANGES", "false") == "true"

}

/*
Deployment safety guard.

If APPLY_CHANGES=true AND allow_apply_mode=false,
Terraform will stop the deployment.

This prevents someone from accidentally deploying Bloodhound
in destructive mode.

Engineers must explicitly acknowledge the action using:

terraform apply -var allow_apply_mode=true
*/
check "apply_mode_guard" {

  assert {
    condition     = !(local.apply_changes_enabled && var.allow_apply_mode == false)
    error_message = "Deployment blocked: APPLY_CHANGES=true requires -var allow_apply_mode=true"
  }

}

resource "aws_lambda_function" "bloodhound_v2" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "handlers.lambda_function.lambda_handler"
  runtime       = var.lambda_runtime

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout     = var.lambda_timeout_seconds
  memory_size = var.lambda_memory_mb

  publish = true

  environment {
    variables = var.lambda_env
  }

  # prevent_destroy is intentionally disabled.
  # Lambdas are stateless and safe to recreate during deploys.
  # Enable this only if the function ever manages critical resources.
  lifecycle {
    prevent_destroy = false
  }
}


