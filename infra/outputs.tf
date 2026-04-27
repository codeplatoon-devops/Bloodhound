/*
infra/outputs.tf

Outputs used by operators when configuring Slack commands
and validating deployments.

To retrieve the Slack command endpoint:

terraform output bloodhound_lambda_url
*/

output "lambda_function_name" {
  value = aws_lambda_function.bloodhound_v2.function_name
}

output "bloodhound_lambda_url" {
  description = "Public Lambda Function URL used by Slack slash commands"
  value       = aws_lambda_function_url.bloodhound_url.function_url
}