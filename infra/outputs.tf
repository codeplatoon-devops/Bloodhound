/*
infra/outputs.tf

Outputs you copy into Slack configuration:
- lambda_function_url -> Slack slash command Request URL
*/

output "lambda_function_name" {
  value = aws_lambda_function.bloodhound_v2.function_name
}

output "lambda_function_url" {
  value = aws_lambda_function_url.bloodhound_url.function_url
}


