/*
infra/variables.tf

Input variables for the Terraform module.
Keep these minimal; most per-environment config is passed via lambda_env.
*/

variable "aws_region" {
  type        = string
  description = "AWS region to deploy the Lambda into."
  default     = "us-west-2"
}

variable "aws_profile" {
  type        = string
  description = "Optional AWS CLI profile name for Terraform."
  default     = null
}

variable "name_prefix" {
  type        = string
  description = "Prefix for IAM resources."
  default     = "bloodhound-v2"
}

variable "lambda_function_name" {
  type        = string
  description = "Name of the Bloodhound v2 Lambda function."
  default     = "BloodhoundLambdaV2"
}

variable "lambda_runtime" {
  type        = string
  description = "Lambda runtime."
  default     = "python3.10"
}

variable "lambda_timeout_seconds" {
  type        = number
  description = "Lambda timeout in seconds."
  default     = 120
}

variable "lambda_memory_mb" {
  type        = number
  description = "Lambda memory size."
  default     = 256
}

variable "lambda_env" {
  type        = map(string)
  description = "Lambda environment variables (copy from your .env, minus secrets you don't want in TF state)."
  default     = {}
}

/*
Optional override for the Lambda alias version.

When null (default), the alias points to the newest published version.

When set to a specific version number, Terraform will point the
production alias to that version instead. This allows safe rollbacks
without modifying infrastructure code.
*/
variable "lambda_alias_version_override" {
  type        = string
  default     = null
  description = "Optional Lambda version to pin the prod alias to for rollback."
}


variable "expected_aws_account_id" {
  description = "Safety guard: ensure Terraform is running against the correct AWS account."
  type        = string
}