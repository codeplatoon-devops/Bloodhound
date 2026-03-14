#!/usr/bin/env bash

# ------------------------------------------------------------
# Bloodhound Validation Workflow Runner
#
# This script orchestrates the full validation workflow.
#
# It runs validation tools in the correct order:
#
# 1. Infrastructure smoke test
# 2. Controlled teardown validation
#
# If the smoke test fails, the workflow stops immediately.
#
# Usage:
#
#   ./tools/run_validation_workflow.sh
#
# ------------------------------------------------------------

set -euo pipefail  # exit immediately if any command fails

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
# Validation Run Identifier
# ------------------------------------------------------------

RUN_ID=$(date +"%Y%m%d_%H%M%S")

# ------------------------------------------------------------
# Workflow Logging
# ------------------------------------------------------------

LOG_DIR="logs/validation"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/workflow_validation_${RUN_ID}.log"

# send all output to terminal AND log
exec > >(tee -a "$LOG_FILE") 2>&1


echo ""
echo "================================================"
echo "Bloodhound Validation Workflow"
echo "================================================"
echo ""

# ------------------------------------------------------------
# Step 1 — Run infrastructure smoke test
# ------------------------------------------------------------

echo "Step 1: Running Lambda smoke test..."
echo ""

./tools/smoke_test_lambda.sh

echo ""
echo "Smoke test passed."
echo ""

# ------------------------------------------------------------
# Step 2 — Run controlled teardown validation
# ------------------------------------------------------------

echo "Step 2: Starting controlled teardown validation..."
echo ""

echo "Validation Run ID: $RUN_ID"

./tools/validate_teardown.sh "$RUN_ID"

echo ""
echo "================================================"
echo "Validation workflow completed successfully."
echo "================================================"
echo ""

# ------------------------------------------------------------------
# Workflow Log Retention
#
# Keep only the 3 most recent workflow validation logs.
# Older logs are removed automatically to prevent the
# validation directory from growing indefinitely.
#
# Detailed teardown logs have their own retention policy
# inside validate_teardown.sh.
# ------------------------------------------------------------------

echo "Keeping only the 3 most recent workflow logs."

ls -1t "$LOG_DIR"/workflow_validation_* 2>/dev/null | tail -n +4 | xargs -r rm