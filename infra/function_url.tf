/*
infra/function_url.tf

Public HTTPS endpoint for Slack slash commands.

We use a Lambda Function URL (single endpoint) and validate Slack signatures in code.

AWS change (Oct 2025):
Function URLs now require BOTH permissions:
 - lambda:InvokeFunctionUrl
 - lambda:InvokeFunction
*/

# ---------------------------------------------------------
# Lambda Function URL
# ---------------------------------------------------------

resource "aws_lambda_function_url" "bloodhound_url" {
  function_name      = aws_lambda_function.bloodhound_v2.function_name
  authorization_type = "NONE"
}

# ---------------------------------------------------------
# Allow public HTTP invocation of the Function URL
# ---------------------------------------------------------

resource "aws_lambda_permission" "function_url_public" {
  statement_id           = "AllowFunctionUrlPublic"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.bloodhound_v2.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# ---------------------------------------------------------
# Allow the Lambda service to execute the function
# ---------------------------------------------------------

resource "aws_lambda_permission" "function_url_invoke" {
  statement_id  = "AllowFunctionInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bloodhound_v2.function_name
  principal     = "*"
}