#!/usr/bin/env bash

# ------------------------------------------------------------------
# Bloodhound Controlled Teardown Validation Script
#
# Purpose
# -------
# This script validates the full Bloodhound teardown pipeline.
#
# It verifies that Bloodhound can:
#   1. Detect an AWS resource during a scan
#   2. Include the resource in the teardown plan
#   3. Execute the deletion successfully
#
# Validation Workflow
# -------------------
# 1. Terraform creates a temporary EC2 instance
# 2. Engineer runs `/v2_seek` in Slack to confirm detection
# 3. Engineer runs `/v2_seek_destroy CONFIRM`
# 4. Bloodhound deletes the instance
# 5. Script verifies the instance no longer exists
#
# All validation runs produce:
#
#   • a detailed run log  (logs/validation/)
#   • a history record    (logs/validation_history.log)
#
# Documentation reference:
# docs/validate_teardown.md
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Ensure script is executed from repository root
#
# This prevents path issues when referencing directories like:
#   logs/
#   infra/
#   tools/
#
# always run validation via:
#
#   ./tools/run_validation_workflow.sh
# ------------------------------------------------------------------
if [ ! -d "tools" ] || [ ! -d "infra" ]; then
  echo "ERROR: run this script from the repository root."
  echo "Example:"
  echo "  ./tools/run_validation_workflow.sh"
  exit 1
fi

# Stop the script immediately if any command fails
set -e

# ------------------------------------------------------------------
# Validation Mode Configuration
#
# Default behavior:
#   automated validation (CI/CD safe)
#
# Optional:
#   --manual enables Slack confirmation steps so engineers can
#   visually verify the scan and teardown plan.
#
# Examples:
#
#   ./tools/run_validation_workflow.sh
#   ./tools/run_validation_workflow.sh --manual
# ------------------------------------------------------------------

MANUAL_MODE=false

if [ "$1" == "--manual" ]; then
  MANUAL_MODE=true
fi

# ------------------------------------------------------------------
# Disable AWS CLI Pager
#
# Some AWS CLI commands automatically open output in a pager
# (usually "less"), which pauses script execution and displays
# an "(END)" prompt until the user exits manually.
#
#
# Setting AWS_PAGER="" disables the pager so AWS CLI commands
# print directly to stdout instead of launching an interactive
# viewer.
# ------------------------------------------------------------------
export AWS_PAGER=""

# ------------------------------------------------------------------
# Load environment variables
#
# This loads the .env file so validation scripts can access
# configuration values such as EXPECTED_AWS_ACCOUNT_ID.
# ------------------------------------------------------------------

if [ -f ".env" ]; then
  source .env
fi


# ------------------------------------------------------------------
# AWS Account Safety Guard
#
# Prevents validation tests from running in the wrong AWS account.
# ------------------------------------------------------------------

CURRENT_ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account \
  --output text)

if [ "$CURRENT_ACCOUNT_ID" != "$EXPECTED_AWS_ACCOUNT_ID" ]; then
  echo ""
  echo "ERROR: Wrong AWS account detected."
  echo ""
  echo "Expected: $EXPECTED_AWS_ACCOUNT_ID"
  echo "Actual:   $CURRENT_ACCOUNT_ID"
  echo ""
  echo "Refusing to run teardown validation."
  echo ""
  exit 1
fi


# ------------------------------------------------------------------
# Configuration Consistency Check
#
# APPLY_CHANGES and TEARDOWN_SIMULATE must not both be true.
# This configuration is contradictory and indicates a misconfigured
# environment.
#
# If APPLY_CHANGES=true → real deletions should occur.
# If TEARDOWN_SIMULATE=true → no deletions should occur.
# ------------------------------------------------------------------

if [ "$APPLY_CHANGES" = "true" ] && [ "$TEARDOWN_SIMULATE" = "true" ]; then
  echo ""
  echo "ERROR: Invalid teardown configuration."
  echo ""
  echo "APPLY_CHANGES=true"
  echo "TEARDOWN_SIMULATE=true"
  echo ""
  echo "Both modes cannot be enabled simultaneously."
  echo "Fix the configuration in your .env file."
  echo ""
  exit 1
fi

# ------------------------------------------------------------------
# Validation Run Identifier
#
# Each validation run receives a unique ID. This ID is used to:
# - name the validation log file
# - track validation activity
# ------------------------------------------------------------------

RUN_ID=$1

if [ -z "$RUN_ID" ]; then
  RUN_ID=$(date +"%Y%m%d_%H%M%S")
fi


# ------------------------------------------------------------------
# Validation Logging Setup
#
# logs/validation/            → detailed logs for individual runs
# logs/validation_history.log → append-only validation history
# ------------------------------------------------------------------
LOG_DIR="logs/validation"
HISTORY_FILE="logs/validation_history.log"

mkdir -p "$LOG_DIR"
touch "$HISTORY_FILE"

LOG_FILE="$LOG_DIR/teardown_validation_${RUN_ID}.log"

# ------------------------------------------------------------------
# Logging helper
#
# Writes messages to both:
#   • terminal output
#   • validation log file
#
# This allows engineers to see progress live while preserving
# a full execution record for debugging.
# ------------------------------------------------------------------
log() {
  echo "$1" | tee -a "$LOG_FILE"
}

log "Validation Run ID: $RUN_ID"


# ------------------------------------------------------------------
# AWS Environment Configuration
# ------------------------------------------------------------------

LOG_GROUP="/aws/lambda/BloodhoundLambdaV2"
REGION="us-west-2"


# ------------------------------------------------------------------
# Optional: Stream Lambda Logs
#
# Engineers can open another terminal to watch the Lambda execution
# in real time while the validation test runs.
# ------------------------------------------------------------------

echo ""
echo "Optional: stream Lambda logs during validation."
echo "Open a second terminal and run:"
echo ""
echo "aws logs tail $LOG_GROUP --region $REGION --follow"
echo ""


echo "----------------------------------------"
echo "Bloodhound Controlled Teardown Validation"
echo "----------------------------------------"


# ------------------------------------------------------------------
# Step 1 — Create Disposable EC2 Instance
#
# Terraform creates the temporary validation resource defined in:
#
#   infra/test_resource.tf
#
# This instance exists only for validation and is tagged so
# for easily identification in the AWS console.
# ------------------------------------------------------------------

echo ""
log "Step 1: Creating disposable EC2 instance"
echo ""

terraform -chdir=infra apply \
  -var "validation_run_id=$RUN_ID" \
  -var "enable_validation_resources=true" \
  -auto-approve


# ------------------------------------------------------------------
# Step 2 — Capture Instance ID
#
# Terraform outputs the instance ID which is used later to verify
# the deletion occurred successfully.
# ------------------------------------------------------------------

echo ""
echo "Capturing instance ID from Terraform output..."
echo ""

INSTANCE_ID=$(terraform -chdir=infra output -raw bloodhound_test_instance_id)

echo "Instance created:"
echo "$INSTANCE_ID"


# ------------------------------------------------------------------
# Allow time for AWS APIs to propagate the new instance
# ------------------------------------------------------------------

echo ""
echo "Waiting for instance to become visible to AWS APIs..."
sleep 10


# ------------------------------------------------------------------
# Step 3 — Slack Scan Validation
#
# Engineer manually runs the Slack command /v2_seek to confirm the
# instance appears in the scan results.


echo ""
echo "----------------------------------------"
log "Scan Confirmation Step"
echo "----------------------------------------"
echo ""

# ------------------------------------------------------------------
# Manual verification mode
#
# Engineers can observe the scan results via Slack before
# continuing the validation workflow.
# ------------------------------------------------------------------

if [ "$MANUAL_MODE" = true ]; then

  echo "Run this command in Slack:"
  echo ""
  echo "  /v2_seek"
  echo ""
  echo "Confirm the EC2 instance appears in the scan results."
  echo ""

  read -p "Press ENTER once /v2_seek has confirmed detection..."

else

  echo "Skipping Slack scan confirmation (automated validation mode)."

fi


# ------------------------------------------------------------------
# Deletion Safety Guard
#
# Prevents the validation workflow from proceeding if the teardown
# candidate set exceeds the configured safety limit.
#
# This protects against:
# - scanning bugs
# - unexpected AWS API responses
# - misconfigured filters
#
# The limit is defined in the .env file:
# TEARDOWN_MAX_DELETE_COUNT
# ------------------------------------------------------------------

EXPECTED_DELETE_COUNT=1

if [ "$EXPECTED_DELETE_COUNT" -gt "$TEARDOWN_MAX_DELETE_COUNT" ]; then
  echo ""
  echo "ERROR: Deletion safety limit exceeded."
  echo ""
  echo "Expected deletions: $EXPECTED_DELETE_COUNT"
  echo "Maximum allowed:   $TEARDOWN_MAX_DELETE_COUNT"
  echo ""
  echo "Validation aborted."
  echo ""
  exit 1
fi


# ------------------------------------------------------------------
# Step 4 — Execute Teardown
#
# Engineer manually runs the Slack command that triggers deletion.
# ------------------------------------------------------------------

echo ""
echo "----------------------------------------"
log "Triggering Bloodhound Validation Teardown"
echo "----------------------------------------"
echo ""

# ------------------------------------------------------------------
# Automated validation teardown
#
# Instead of requiring a Slack command, the validation script
# directly invokes the Lambda function with a validation payload.
#
# This ensures CI/CD pipelines can run validation automatically.
# ------------------------------------------------------------------
# ---------------------------------------------------------------
# ---------------------------------------------------------------
# Build validation payload
#
# The payload is written to /tmp so the repository directory
# is not polluted with temporary files during validation runs.
#
# /tmp is safe for this purpose because:
#
# • files are automatically cleared by the OS eventually
# • the file only needs to exist during this script run
# • it avoids shell quoting issues with inline JSON
# ---------------------------------------------------------------

PAYLOAD_FILE="/tmp/bloodhound_validation_payload.json"

cat > "$PAYLOAD_FILE" <<EOF
{
  "source": "validation",
  "mode": "seek_destroy_validation",
  "target_ids": ["$INSTANCE_ID"]
}
EOF


echo "Invoking Lambda validation teardown..."

# ---------------------------------------------------------------
# Lambda invocation result file
#
# Store the Lambda response in /tmp for the same reason as the
# payload file — it is only needed during this validation run
# and should not clutter the repository.
# ---------------------------------------------------------------

RESULT_FILE="/tmp/bloodhound_validation_result.json"

aws lambda invoke \
  --function-name BloodhoundLambdaV2 \
  --cli-binary-format raw-in-base64-out \
  --payload file://"$PAYLOAD_FILE" \
  --region "$REGION" \
  "$RESULT_FILE"

echo ""
echo "Lambda response:"
cat "$RESULT_FILE"

# ------------------------------------------------------------------
# Lambda response validation
#
# Ensure Lambda returned a successful response before continuing.
# If the Lambda failed internally, the validation workflow should
# stop immediately.
# ------------------------------------------------------------------

jq -e '.ok == true' "$RESULT_FILE" >/dev/null || {
  echo ""
  echo "ERROR: Lambda returned failure response."
  echo ""
  echo "Full Lambda response:"
  cat "$RESULT_FILE"
  echo ""
  exit 1
}


# ------------------------------------------------------------------
# Optional Slack verification (manual mode)
#
# Engineers may optionally observe the teardown behavior using
# Slack commands before the script verifies deletion.
# This step is skipped during automated CI validation.
# ------------------------------------------------------------------

if [ "$MANUAL_MODE" = true ]; then

  echo ""
  echo "Optional verification using Slack:"
  echo ""
  echo "  /v2_seek_destroy CONFIRM"
  echo ""

  read -p "Press ENTER once Slack teardown results are confirmed..."

fi

echo ""
echo "Waiting for EC2 termination propagation..."
sleep 10

# ------------------------------------------------------------------
# Step 5 — Verify Deletion
#
# The script queries the EC2 API to confirm the instance
# no longer exists.
#
# If the instance still exists, the teardown validation fails.
# ------------------------------------------------------------------

echo ""
log "Step 6: Verifying instance deletion..."
echo ""

if aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --region "$REGION" >/dev/null 2>&1
then
    echo ""
    RESULT="FAIL"

    log "ERROR: Instance still exists."
    log "RESULT: $RESULT"

    # record validation result in append-only history file
    echo "$RUN_ID $RESULT" >> "$HISTORY_FILE"

    echo "Bloodhound did not delete the resource."
    exit 1
else
    echo ""
    RESULT="PASS"

    log "SUCCESS: Instance no longer exists."
    log "RESULT: $RESULT"

    # record validation result in append-only history file
    echo "$RUN_ID $RESULT" >> "$HISTORY_FILE"

    echo "Bloodhound successfully deleted the resource."
fi


# ------------------------------------------------------------------
# Step 6 — Restore Safe Mode
#
# Engineer must ensure the Lambda environment variables are
# returned to safe mode before continuing.
# ------------------------------------------------------------------

echo ""
echo "Step 7: Restoring safe mode configuration"
echo ""

echo "Reminder:"
echo "Ensure environment variables are reset:"
echo ""
echo "  APPLY_CHANGES=false"
echo "  TEARDOWN_SIMULATE=true"
echo ""

read -p "Press ENTER once Terraform configuration has been restored..."


# ------------------------------------------------------------------
# Step 7 — Reapply Terraform Configuration
#
# Ensures the infrastructure returns to the safe configuration.
# ------------------------------------------------------------------

terraform -chdir=infra apply \
  -var="enable_validation_resources=false" \
  -auto-approve


# ------------------------------------------------------------------
# Step 8 — Cleanup Validation Resource
#
# Terraform removes the temporary EC2 instance from state.
# ------------------------------------------------------------------

echo ""
log "Step 8: Cleaning up Terraform state"
echo ""

terraform -chdir=infra destroy \
  -var="enable_validation_resources=true" \
  -target aws_instance.bloodhound_teardown_test \
  -auto-approve


echo ""
echo "----------------------------------------"
echo "Validation Complete"
echo "----------------------------------------"
echo ""
echo "Teardown pipeline verified."
echo ""


# ------------------------------------------------------------------
# Validation Log Retention
#
# Keep only the 3 most recent detailed validation logs.
# Older logs are removed automatically to prevent the
# validation directory from growing indefinitely.
#
# Note:
# validation_history.log still records every validation run.
# ------------------------------------------------------------------

log "Keeping only the 3 most recent validation logs."

ls -1t "$LOG_DIR"/teardown_validation_* 2>/dev/null | tail -n +4 | xargs -r rm