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

RUN_ID=$(date +"%Y%m%d_%H%M%S")

echo "Validation Run ID: $RUN_ID"

./tools/validate_teardown.sh "$RUN_ID"

echo ""
echo "================================================"
echo "Validation workflow completed successfully."
echo "================================================"
echo ""