/*
infra/alias.tf

Defines the Lambda alias used for production traffic.

Key points:
- The alias provides a stable name ("prod") that points to a specific
  published Lambda version.
- Each Terraform deploy publishes a new immutable Lambda version.
- The alias automatically shifts to the latest version during deploys.
- An optional override variable allows pinning the alias to an older
  version for rollback without modifying infrastructure code.
*/

resource "aws_lambda_alias" "bloodhound_prod" {
  name          = "prod"
  description   = "Production alias for Bloodhound Lambda"
  function_name = aws_lambda_function.bloodhound_v2.function_name
  function_version = coalesce(
    var.lambda_alias_version_override,
    aws_lambda_function.bloodhound_v2.version
  )
}