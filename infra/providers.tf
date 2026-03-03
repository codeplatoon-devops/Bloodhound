/*
infra/providers.tf

AWS provider configuration for this module.
We keep provider config separate so main.tf can stay provider-requirements-only.
*/

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}


