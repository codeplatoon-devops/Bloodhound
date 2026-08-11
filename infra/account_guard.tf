/*
infra/account_guard.tf

Safety guard to prevent Terraform from deploying
to the wrong AWS account.
*/

data "aws_caller_identity" "current" {}

resource "terraform_data" "account_guard" {
  lifecycle {
    precondition {
      condition     = data.aws_caller_identity.current.account_id == var.expected_aws_account_id
      error_message = "Terraform is connected to the wrong AWS account."
    }
  }
}