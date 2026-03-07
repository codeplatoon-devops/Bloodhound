#!/usr/bin/env bash

# ------------------------------------------------------------
# Bloodhound Validation History
#
# Displays the full validation history stored in:
#
# logs/validation_history.log
# ------------------------------------------------------------

HISTORY_FILE="logs/validation_history.log"

echo ""
echo "Bloodhound Validation History"
echo "-----------------------------"
echo ""

if [ ! -f "$HISTORY_FILE" ]; then
  echo "No validation history found."
  exit 0
fi

cat "$HISTORY_FILE"

echo ""