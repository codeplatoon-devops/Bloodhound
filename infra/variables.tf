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

/*
Safety override for destructive mode.

Bloodhound can delete infrastructure when APPLY_CHANGES=true.
To prevent accidental deletion, Terraform blocks deployment
unless this variable is explicitly enabled.

Example failure:

APPLY_CHANGES=true
allow_apply_mode=false

Terraform will stop with an error.

To intentionally enable destructive mode for testing:

terraform apply -var allow_apply_mode=true

Default is false so deletion cannot be enabled accidentally.
*/
variable "allow_apply_mode" {
  description = "Explicit override required to deploy Bloodhound with APPLY_CHANGES=true."
  type        = bool
  default     = false
}

# ------------------------------------------------------------
# Unique ID used to trace validation runs.
# Passed from validation scripts so AWS resources can be
# associated with a specific validation execution.
# ------------------------------------------------------------

variable "validation_run_id" {
  description = "Unique validation run identifier"
  type        = string
  default     = "manual"
}

# ------------------------------------------------------------
# Enables temporary infrastructure used for validation tests.
# This should normally be disabled during regular Terraform
# deployments.
# ------------------------------------------------------------

variable "enable_validation_resources" {
  description = "Create temporary validation infrastructure"
  type        = bool
  default     = false
}