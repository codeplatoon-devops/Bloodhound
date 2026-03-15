#!/usr/bin/env bash

# =========================================================
# Bloodhound GitHub OIDC Bootstrap Script
# =========================================================
#
# PURPOSE
#
# This script bootstraps the AWS infrastructure required
# for GitHub Actions to securely invoke the Bloodhound
# Lambda function using OpenID Connect (OIDC).
#
# Using OIDC eliminates the need to store long-lived AWS
# credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
# inside GitHub repository secrets.
#
# Instead, GitHub exchanges a short-lived OIDC token with
# AWS STS to assume an IAM role and obtain temporary
# credentials during workflow execution.
#
#
# RESULTING AUTHENTICATION FLOW
#
# GitHub Actions workflow
#        ↓
# GitHub OIDC token
#        ↓
# AWS STS AssumeRoleWithWebIdentity
#        ↓
# BloodhoundGitHubInvokeRole
#        ↓
# Temporary AWS credentials
#        ↓
# Invoke BloodhoundLambdaV2
#
#
# WHAT THIS SCRIPT CONFIGURES
#
# 1. Ensures the GitHub OIDC provider exists in the AWS account
# 2. Creates or updates the IAM role used by GitHub Actions
# 3. Configures the trust policy for GitHub OIDC
# 4. Attaches permissions allowing the Lambda to be invoked
# 5. Outputs the role ARN for GitHub workflow configuration
#
#
# IMPORTANT DESIGN CHOICE
#
# The trust policy allows:
#
#     repo:*/Bloodhound:*
#
# This permits GitHub workflows running from forks of the
# Bloodhound repository to assume the IAM role.
#
# This is necessary because contributors typically run CI
# from their personal forks before opening pull requests
# to the canonical repository:
#
#     codeplatoon-devops/Bloodhound
#
# Without this rule, AWS would reject OIDC tokens issued
# from forked repositories because the repository owner
# would not match the organization name.
#
#
# SCRIPT BEHAVIOR
#
# This script is intentionally idempotent:
#
# • Safe to run multiple times
# • Existing infrastructure will not be duplicated
# • IAM trust policy will be updated if the role exists
#
#
# PREREQUISITES
#
# - AWS CLI installed
# - AWS CLI authenticated
# - IAM permissions to create roles and policies
#
#
# VERIFY AWS AUTHENTICATION
#
#     aws sts get-caller-identity
#
#
# HOW TO RUN
#
#     chmod +x scripts/bootstrap_github_oidc.sh
#     ./scripts/bootstrap_github_oidc.sh
#
#
# AFTER RUNNING
#
# Update the GitHub Actions workflow to use:
#
#     aws-actions/configure-aws-credentials@v4
#
# with the role ARN printed by this script.
#
# =========================================================


# ---------------------------------------------------------
# Cleanup temporary IAM policy artifacts
#
# The AWS CLI requires policy documents to be supplied as
# files when creating IAM roles and attaching policies.
#
# This script dynamically generates the following files:
#   trust-policy.json
#   lambda-policy.json
#
# These files are temporary artifacts and should never be
# committed to the repository.
#
# The EXIT trap ensures they are automatically removed when
# the script finishes, regardless of whether execution
# succeeds, fails, or is interrupted.
# ---------------------------------------------------------
trap "rm -f trust-policy.json lambda-policy.json" EXIT

set -euo pipefail

# Disable AWS CLI pager so scripts never hang
export AWS_PAGER=""


# ---------------------------------------------------------
# Configuration
#
# These values define the AWS and GitHub environment
# this bootstrap script will configure.
#
# The AWS account ID is automatically detected using STS
# so the script can run safely in any AWS account without
# requiring manual configuration.
#
# NOTE:
# We use the canonical repository owner (Code Platoon org)
# instead of a personal fork so the role remains valid
# when CI runs from the upstream repository.
# ---------------------------------------------------------

# Detect AWS account automatically
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

AWS_REGION="us-west-2"

# Canonical repository (not personal fork)
GITHUB_ORG="codeplatoon-devops"
GITHUB_REPO="Bloodhound"

LAMBDA_NAME="BloodhoundLambdaV2"

ROLE_NAME="BloodhoundGitHubInvokeRole"


# GitHub OIDC provider information
OIDC_PROVIDER_URL="https://token.actions.githubusercontent.com"
OIDC_PROVIDER_ARN="arn:aws:iam::$ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"


echo "======================================="
echo "Bootstrapping GitHub OIDC for Bloodhound"
echo "Account: $ACCOUNT_ID"
echo "Repository: $GITHUB_ORG/$GITHUB_REPO"
echo "======================================="


# ---------------------------------------------------------
# 1. Check if the GitHub OIDC provider already exists
# ---------------------------------------------------------

echo ""
echo "Checking for existing GitHub OIDC provider..."

EXISTING_PROVIDER=$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" \
  --output text)

if [[ -z "$EXISTING_PROVIDER" ]]; then
  echo "OIDC provider not found. Creating..."

  aws iam create-open-id-connect-provider \
    --url $OIDC_PROVIDER_URL \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

  echo "OIDC provider created."

else
  echo "OIDC provider already exists."
fi


# ---------------------------------------------------------
# 2. Generate GitHub OIDC trust policy
#
# GitHub OIDC Trust Policy (Strict Repo Control)
#
# This IAM role allows GitHub Actions workflows to assume
# the role using OIDC (sts:AssumeRoleWithWebIdentity).
#
# SECURITY MODEL
#
# Access is restricted to explicitly listed repositories
# instead of allowing all repositories named "Bloodhound".
#
# Currently allowed repositories:
#
#   • codeplatoon-devops/Bloodhound
#   • mmccla1n/Bloodhound
#
# Branch restrictions:
#
#   • The upstream repository is restricted to the main branch
#   • The maintainer fork allows all branches for development
#
# CONTRIBUTOR NOTE
#
# If another contributor wants to run GitHub Actions from
# their fork of the repository, their fork must be added
# to the "sub" condition below using the format:
#
#   repo:<github-user>/Bloodhound:ref:refs/heads/*
#
# Example:
#
#   repo:janedoe/Bloodhound:ref:refs/heads/*
#
# This keeps the role secure while still allowing approved
# forks to run CI workflows.
# ---------------------------------------------------------

echo ""
echo "Creating trust policy..."

cat <<EOF > trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "$OIDC_PROVIDER_ARN"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:codeplatoon-devops/Bloodhound:ref:refs/heads/main",
            "repo:mmccla1n/Bloodhound:ref:refs/heads/*"
          ]
        }
      }
    }
  ]
}
EOF


# ---------------------------------------------------------
# 3. Create or update IAM role for GitHub Actions
#
# If the role already exists, the trust policy is updated
# to ensure it reflects the current repository policy.
# ---------------------------------------------------------

echo ""
echo "Creating IAM role: $ROLE_NAME"

if aws iam get-role --role-name $ROLE_NAME > /dev/null 2>&1; then
  echo "Role already exists. Updating trust policy..."

  aws iam update-assume-role-policy \
    --role-name $ROLE_NAME \
    --policy-document file://trust-policy.json

else

  aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document file://trust-policy.json \
    --tags \
        Key=Project,Value=Bloodhound \
        Key=Owner,Value=CodePlatoon-DevOps \
        Key=ManagedBy,Value=GitHubActions \
        Key=Component,Value=CI-Infrastructure

  echo "Role created."

fi


# ---------------------------------------------------------
# 4. Configure IAM permissions for Lambda invocation
#
# The role requires permission to invoke the Bloodhound
# Lambda function and optionally read its CloudWatch logs
# for debugging CI failures.
# ---------------------------------------------------------

echo ""
echo "Creating Lambda invoke policy..."

cat <<EOF > lambda-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeBloodhoundLambda",
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": "arn:aws:lambda:$AWS_REGION:$ACCOUNT_ID:function:$LAMBDA_NAME"
    },
    {
      "Sid": "ReadLambdaLogs",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:GetLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
EOF


aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name BloodhoundInvokePolicy \
  --policy-document file://lambda-policy.json

echo "Policy attached."


# ---------------------------------------------------------
# 5. Output IAM role ARN for GitHub workflow configuration
#
# This ARN must be referenced in the GitHub Actions
# workflow using the configure-aws-credentials action.
# ---------------------------------------------------------

ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"

echo ""
echo "======================================="
echo "Bootstrap complete."
echo ""
echo "Use this role in your GitHub workflow:"
echo ""
echo "$ROLE_ARN"
echo ""
echo "======================================="