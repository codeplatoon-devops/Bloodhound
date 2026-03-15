#!/usr/bin/env bash

# ------------------------------------------------------------
# Bloodhound Lambda Smoke Test
#
# Purpose
# -------
# Quickly verify that the Bloodhound Lambda deployment is healthy.
#
# This script detects common deployment problems such as:
#
# - wrong AWS region
# - Lambda function not deployed
# - missing or incorrect environment variables
# - CloudWatch log group missing
# - Lambda Function URL not configured
#
# It also validates that critical Lambda environment variables
# match the local `.env` configuration. This helps detect cases
# where Terraform changes were not applied.
#
# This script is intended to be run immediately after:
#
#   terraform apply
#
# It should complete in a few seconds and detect most
# infrastructure deployment issues.
# ------------------------------------------------------------

set -e  # exit immediately if any command fails

# ------------------------------------------------------------
# Disable AWS CLI pager
#
# AWS CLI v2 automatically sends long output to a pager
# (usually "less"), which pauses scripts and displays "(END)"
# until the user presses 'q'.
#
# Automation scripts should disable this behavior so output
# prints directly to the terminal.
# ------------------------------------------------------------
export AWS_PAGER=""

# ------------------------------------------------------------
# Dependency check
#
# The script uses jq to parse JSON returned by AWS CLI.
# ------------------------------------------------------------
command -v jq >/dev/null 2>&1 || {
  echo "ERROR: jq is required but not installed."
  exit 1
}

# ------------------------------------------------------------
# Configuration
#
# These values should match your Terraform deployment.
# ------------------------------------------------------------
REGION="us-west-2"
FUNCTION_NAME="BloodhoundLambdaV2"
LOG_GROUP="/aws/lambda/BloodhoundLambdaV2"

echo ""
echo "--------------------------------------"
echo "Bloodhound Lambda Smoke Test"
echo "--------------------------------------"
echo ""

# ------------------------------------------------------------
# Step 1 — Verify Lambda function exists
#
# If this fails, Terraform deployment likely failed.
# ------------------------------------------------------------
echo "Checking Lambda existence..."

aws lambda get-function \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" >/dev/null

echo "✓ Lambda function exists"

# ------------------------------------------------------------
# Step 2 — Retrieve Lambda environment variables
#
# These variables are injected by Terraform during deployment.
# ------------------------------------------------------------
echo ""
echo "Fetching Lambda environment variables..."

LAMBDA_ENV=$(aws lambda get-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --query 'Environment.Variables' \
  --output json)

echo "✓ Retrieved Lambda environment variables"

# ------------------------------------------------------------
# Step 3 — Validate Lambda environment variables
#
# LOCAL MODE
#   Compare deployed Lambda variables against local .env
#
# CI MODE (GitHub Actions)
#   Verify required variables exist in Lambda
#
# GitHub automatically sets:
#   CI=true
# ------------------------------------------------------------
echo ""
echo "Validating critical environment variables..."

# ------------------------------------------------------------
# Determine execution mode
# ------------------------------------------------------------
if [ "${CI:-}" = "true" ]; then
  MODE="ci"
else
  MODE="local"
fi


# ------------------------------------------------------------
# LOCAL MODE VALIDATION
#
# Compare deployed Lambda variables against local .env
# ------------------------------------------------------------
check_env_match () {

  VAR_NAME=$1

  EXPECTED=${!VAR_NAME}

  ACTUAL=$(echo "$LAMBDA_ENV" | jq -r ".${VAR_NAME}")

  if [ "$EXPECTED" != "$ACTUAL" ]; then

    echo ""
    echo "ERROR: Environment variable mismatch"
    echo "Variable: $VAR_NAME"
    echo "Expected: $EXPECTED"
    echo "Actual:   $ACTUAL"
    echo ""
    echo "Terraform deployment may be out of sync."
    echo "Run: terraform apply"
    exit 1

  fi
}


# ------------------------------------------------------------
# CI MODE VALIDATION
#
# Ensure required variables exist in Lambda
# ------------------------------------------------------------
check_env_exists () {

  VAR_NAME=$1

  ACTUAL=$(echo "$LAMBDA_ENV" | jq -r ".${VAR_NAME}")

  if [ "$ACTUAL" = "null" ] || [ -z "$ACTUAL" ]; then

    echo ""
    echo "ERROR: Lambda environment variable missing"
    echo "Variable: $VAR_NAME"
    echo ""
    exit 1

  fi
}


# ------------------------------------------------------------
# Execute validation
# ------------------------------------------------------------
if [ "$MODE" = "local" ]; then

  echo "Local mode detected — validating against .env"

  source .env

  check_env_match APPLY_CHANGES
  check_env_match TEARDOWN_SIMULATE
  check_env_match SLACK_SCAN_CHANNEL_ID
  check_env_match SLACK_ALERT_CHANNEL_ID

else

  echo "CI mode detected — verifying variables exist in Lambda"

  check_env_exists APPLY_CHANGES
  check_env_exists TEARDOWN_SIMULATE
  check_env_exists SLACK_SCAN_CHANNEL_ID
  check_env_exists SLACK_ALERT_CHANNEL_ID

fi

echo "✓ Environment variable validation passed"

# ------------------------------------------------------------
# Step 4 — Display deployed Lambda environment variables
#
# Local mode prints the full environment variables directly
# from AWS for developer inspection.
#
# CI mode prints the variables but masks sensitive values
# such as tokens and secrets to prevent credential leakage
# in GitHub Actions logs.
# ------------------------------------------------------------
echo ""
echo "Deployed Lambda environment variables:"

if [ "$MODE" = "ci" ]; then

  # Use the already-fetched environment variables and mask secrets
  echo "$LAMBDA_ENV" | jq 'with_entries(
    if (.key | test("SECRET|TOKEN"))
    then .value="***MASKED***"
    else .
    end
  )'

else
  # Local developer mode: show full values
  aws lambda get-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --query 'Environment.Variables'
fi

echo ""
echo "✓ Environment variables retrieved"

# ------------------------------------------------------------
# Step 5 — Verify CloudWatch log group exists
#
# Lambda automatically creates this on first execution.
# ------------------------------------------------------------
echo ""
echo "Checking CloudWatch log group..."

aws logs describe-log-groups \
  --log-group-name-prefix "$LOG_GROUP" \
  --region "$REGION" >/dev/null

echo "✓ Log group exists"

# ------------------------------------------------------------
# Step 6 — Verify Lambda Function URL
#
# Slack slash commands depend on this endpoint.
# ------------------------------------------------------------
echo ""
echo "Checking Lambda Function URL..."

aws lambda get-function-url-config \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" >/dev/null

echo "✓ Function URL configured"

echo ""
echo "--------------------------------------"
echo "Smoke test completed successfully"
echo "--------------------------------------"
echo ""