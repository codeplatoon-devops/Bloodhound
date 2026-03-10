# Bloodhound Validation — User Guide

This guide explains **when and how to run the Bloodhound validation workflow**.

The validation workflow confirms that the full system is functioning correctly, including:

* AWS infrastructure
* Lambda execution
* Slack command routing
* teardown logic
* resource deletion

This process uses **temporary disposable resources** and is safe when run as described.

---

# When to Run Validation

Run the validation workflow when:

• deploying Bloodhound for the first time
• modifying Lambda code
• modifying teardown logic
• modifying IAM permissions
• modifying Terraform infrastructure
• upgrading AWS SDK dependencies
• before enabling destructive mode in production

You **do not need to run validation for every small code change**, but it should be executed before production use.

---

# Quick Validation Workflow

The fastest way to run the full validation is:

```
tools/run_validation_workflow.sh
```

This script performs the following checks in order:

1. Lambda infrastructure smoke test
2. Controlled teardown validation

If any step fails, the workflow stops immediately.

---

# Step 1 — Run the Validation Workflow

From the repository root:

```
tools/run_validation_workflow.sh
```

You will see output similar to:

```
Bloodhound Validation Workflow

Step 1: Running Lambda smoke test
Smoke test passed.

Step 2: Starting controlled teardown validation
```

If the smoke test fails, fix the deployment before continuing.

---

# Step 2 — Follow Slack Instructions

During teardown validation the script will pause and instruct you to run Slack commands.

YYou will be prompted to run:

`/v2_seek`

(Optional) You may preview the teardown plan before execution:

`/v2_seek_destroy_plan`

After confirming detection, the script will prompt you to run:

`/v2_seek_destroy CONFIRM`

This command tells Bloodhound to **execute the teardown plan**.

---

## Validate Lambda Health Endpoint

Optional system status verification:

/v2_status

This command returns the Bloodhound system status including
execution mode, deletion safety limits, and recent scan results.

Before testing Slack integrations, confirm the Lambda service is reachable.


curl https://YOUR_LAMBDA_URL/health

Expected response:

{
  "ok": true,
  "service": "BloodhoundLambdaV2",
  "status": "healthy"
}

This check verifies the Lambda deployment without triggering a scan.


# Step 3 — Automatic Deletion Verification

After the Slack command runs, the validation script will automatically verify that the resource was deleted.

Example output:

```
SUCCESS: Instance no longer exists.
RESULT: PASS
```

If the resource still exists:

```
ERROR: Instance still exists.
RESULT: FAIL
```

This indicates that the teardown pipeline did not execute correctly.

---

# Step 4 — Validation Logs

Every validation run produces a log file.

Location:

```
logs/validation/
```

Example log:

```
logs/validation/teardown_validation_20260307_143221.log
```

Each log records:

* validation run ID
* created resource ID
* test steps executed
* final result (PASS / FAIL)

Only the **3 most recent logs** are kept automatically.

---

# What the Validation Tests

# Bloodhound Execution Modes

Bloodhound has three safety modes controlled by environment variables.

Dry Run Mode (default)

APPLY_CHANGES=false
TEARDOWN_SIMULATE=true

Behavior:
• resources are scanned
• teardown plan is generated
• nothing is deleted


Simulation Mode

APPLY_CHANGES=true
TEARDOWN_SIMULATE=true

Behavior:
• deletion calls are simulated
• AWS DryRun APIs are used
• nothing is deleted


Apply Mode (destructive)

APPLY_CHANGES=true
TEARDOWN_SIMULATE=false

Behavior:
• Bloodhound executes deletion actions
• non-whitelisted resources may be removed

The validation workflow confirms the following systems work together:

| Component              | Verified |
| ---------------------- | -------- |
| Lambda deployment      | ✓        |
| environment variables  | ✓        |
| Slack command routing  | ✓        |
| resource detection     | ✓        |
| teardown plan creation | ✓        |
| resource deletion      | ✓        |
| Slack reporting        | ✓        |

---

# Expected Slack Output

When `/v2_seek_destroy CONFIRM` runs successfully, Slack will show a message similar to:

```
Bloodhound v2 — Teardown Results

Deleted resources:
ec2.instance=1
```

---

# If Validation Fails

Check the following:

**Smoke test failure**

Run:

```
tools/smoke_test_lambda.sh
```

Fix infrastructure problems before continuing.

---

**Resource not detected**

Check:

* instance region
* instance state
* whitelist tags

Ensure the instance does **not** have:

```
bloodhound:keep=true
```

---

**Resource not deleted**

Check:

```
APPLY_CHANGES=true
TEARDOWN_SIMULATE=false
```

Verify IAM permissions allow deletion.

---

# Safety Reminder

The teardown validation temporarily enables **real deletion mode**.

Always restore safe mode after testing:

```
APPLY_CHANGES=false
TEARDOWN_SIMULATE=true
```

Then run:

```
terraform apply
```

This returns Bloodhound to **dry-run mode**.

---

# Recommended Validation Order

Always run validations in this order:

```
1. Infrastructure smoke test
2. Slack command validation
3. Controlled teardown validation
```

This ensures problems are caught early before destructive operations are attempted.

---

# Related Documentation

Slack validation:

```
docs/validate_slack_lambda.md
```

Architecture and configuration:

```
docs/bloodhound_v2_plan.md
```
