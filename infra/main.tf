terraform {
  /*
  infra/main.tf

  Terraform root settings for Bloodhound v2.
  This file intentionally contains ONLY provider requirements and version constraints.
  Resources are split into dedicated files (iam.tf, lambda.tf, function_url.tf, build.tf, ...).
  */
  # terraform main file intentionally keeps only provider requirements.
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}


