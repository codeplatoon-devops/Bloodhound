#!/usr/bin/env bash

# =========================================================
# Bloodhound GitHub OIDC Bootstrap Script
# =========================================================
#
# PURPOSE
#
# This script bootstraps AWS infrastructure required for
# GitHub Actions to securely invoke the Bloodhound Lambda
# using OpenID Connect (OIDC).
#
# It eliminates the need for long-lived AWS credentials
# stored in GitHub repository secrets.
#
# After this script runs successfully, GitHub Actions will
# authenticate to AWS using temporary credentials issued
# via IAM role assumption.
#
#
# RESULTING ARCHITECTURE
#
# GitHub Actions
#       ↓
# GitHub OIDC Token
#       ↓
# AWS STS AssumeRoleWithWebIdentity
#       ↓
# BloodhoundGitHubInvokeRole
#       ↓
# Temporary AWS Credentials
#       ↓
# Invoke BloodhoundLambdaV2
#
#
# WHAT THIS SCRIPT DOES
#
# 1. Detects whether the GitHub OIDC provider exists
# 2. Creates the provider if it does not exist
# 3. Creates an IAM role for GitHub Actions
# 4. Configures a trust relationship with the GitHub repo
# 5. Attaches permissions allowing Lambda invocation
# 6. Outputs the role ARN for GitHub workflow configuration
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
# aws sts get-caller-identity
#
#
# HOW TO RUN
#
# chmod +x scripts/bootstrap_github_oidc.sh
# ./scripts/bootstrap_github_oidc.sh
#
#
# AFTER RUNNING
#
# Update the GitHub Actions workflow to use:
#
# aws-actions/configure-aws-credentials@v4
#
# with the role ARN printed by this script.
#
# =========================================================

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
# 2. Create trust policy allowing GitHub to assume role
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
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:$GITHUB_ORG/$GITHUB_REPO:*"
        }
      }
    }
  ]
}
EOF


# ---------------------------------------------------------
# 3. Create IAM role for GitHub Actions
# ---------------------------------------------------------

echo ""
echo "Creating IAM role: $ROLE_NAME"

if aws iam get-role --role-name $ROLE_NAME > /dev/null 2>&1; then
  echo "Role already exists."
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
# 4. Create policy allowing Lambda invocation
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
        "lambda:InvokeFunction"
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
# 5. Output role ARN for GitHub workflow configuration
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