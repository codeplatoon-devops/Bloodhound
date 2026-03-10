#!/usr/bin/env bash

# ------------------------------------------------------------------------------
# bootstrap_imports.sh
#
# Purpose
# -------
# Terraform cannot automatically manage resources that already exist in AWS.
# If IAM roles or policies were previously created manually (or by earlier
# tooling), Terraform will fail during `terraform apply` with:
#
#   EntityAlreadyExists
#
# This helper script detects existing Bloodhound IAM resources and imports
# them into Terraform state so Terraform can manage them safely.
#
# When to run
# -----------
# Run this script once before the first `terraform apply` in an account where
# Bloodhound infrastructure may already exist.
#
# Typical workflow:
#
#   cd infra
#   ./bootstrap_imports.sh
#   terraform apply
#
# The script is safe to run multiple times.
#
# Requirements
# ------------
# - AWS CLI configured
# - Terraform installed
# - Appropriate AWS IAM permissions
#
# ------------------------------------------------------------------------------

set -e
set -o pipefail # makes bash fail if any command in a pipeline fails

# ------------------------------------------------------------------------------
# Safety Check
# ------------------------------------------------------------------------------
# This script must be executed from the `infra/` directory because Terraform
# commands rely on the Terraform configuration files in this directory.
#
# If someone runs the script from the repository root (or another location),
# Terraform would fail because it cannot find the infrastructure configuration.
#
# We detect this by verifying that a known Terraform file exists locally.
# ------------------------------------------------------------------------------

if [ ! -f "lambda.tf" ]; then
  echo "Error: this script must be run from the infra/ directory."
  echo "Example:"
  echo "  cd infra"
  echo "  ./bootstrap_imports.sh"
  exit 1
fi

ROLE_NAME="bloodhound-v2-role"
POLICY_NAME="bloodhound-v2-policy"

echo "Checking existing IAM resources..."

# Retrieve AWS account ID for constructing policy ARN
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# ---------------------------------------------------
# Check if IAM role exists
# ---------------------------------------------------
ROLE_EXISTS=$(aws iam get-role --role-name $ROLE_NAME 2>/dev/null || true)

if [ -n "$ROLE_EXISTS" ]; then
  echo "Existing IAM role detected. Importing into Terraform state..."
  terraform import aws_iam_role.lambda_role $ROLE_NAME || true
fi

# ---------------------------------------------------
# Check if IAM policy exists
# ---------------------------------------------------
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

POLICY_EXISTS=$(aws iam get-policy --policy-arn $POLICY_ARN 2>/dev/null || true)

if [ -n "$POLICY_EXISTS" ]; then
  echo "Existing IAM policy detected. Importing into Terraform state..."
  terraform import aws_iam_policy.bloodhound_policy $POLICY_ARN || true
fi

echo "Terraform import check complete."