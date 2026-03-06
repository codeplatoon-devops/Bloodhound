# Safe Operations Guide (Bloodhound V2)

This document describes the operational safeguards built into Bloodhound V2 and the procedures engineers must follow before enabling destructive actions.

Bloodhound is capable of identifying and deleting unused cloud infrastructure. Because of this capability, strict safeguards are enforced to prevent accidental resource deletion.

---

# Core Safety Principles

Bloodhound follows a layered safety model:

```
Detection
   ↓
Planning
   ↓
Dry-run validation
   ↓
Explicit operator confirmation
   ↓
Deletion
```

Deletion should **never be enabled without first reviewing the dry-run plan.**

---

# Default Safety Configuration

The system ships in **safe mode** by default.

These environment variables enforce non-destructive behavior:

```
APPLY_CHANGES=false
TEARDOWN_SIMULATE=true
TEARDOWN_ALLOW_ALL=false
```

This configuration ensures:

* Infrastructure scans run normally
* Teardown plans are generated
* No resources are deleted

Slack will show a **Teardown Plan (dry-run)** message but no destructive actions will execute.

---

# Safe Validation Procedure

Before enabling deletion, the following validation process must be completed.

## Step 1 — Run Scan

In Slack:

```
/seek
```

Confirm that the system reports:

* scan summary
* budget summary
* teardown plan

---

## Step 2 — Review Teardown Plan

Carefully review the Slack message:

```
Bloodhound v2 — Teardown Plan (dry-run)
```

Verify:

* resources are expected candidates
* no production resources appear
* whitelisted resources are excluded

Example:

```
simulate: true
planned_actions: 36
```

---

## Step 3 — Confirm Whitelisted Resources

Resources that should never be deleted must have the tag:

```
bloodhound:keep=true
```

Bloodhound will list these in Slack under:

```
Whitelisted Resources (Kept)
```

If a resource should be protected but does not appear here, add the tag before proceeding.

---

# Controlled Deletion Procedure

Deletion should only occur after the dry-run plan has been reviewed.

## Enable Deletion Mode

Update environment configuration:

```
APPLY_CHANGES=true
TEARDOWN_SIMULATE=false
```

Keep this safeguard enabled unless a full cleanup is intended:

```
TEARDOWN_ALLOW_ALL=false
```

This forces operators to explicitly specify targets.

---

## Targeted Deletion (Recommended)

Specify the exact resources to delete:

```
TEARDOWN_TARGET_IDS=<comma separated resource IDs>
```

Example:

```
TEARDOWN_TARGET_IDS=i-0123456789abcdef
```

Then execute:

```
/seek_destroy CONFIRM
```

---

# Full Cleanup (Use Extreme Caution)

Only enable full cleanup when the environment is confirmed safe.

Required configuration:

```
APPLY_CHANGES=true
TEARDOWN_SIMULATE=false
TEARDOWN_ALLOW_ALL=true
```

Then run:

```
/seek_destroy CONFIRM
```

Bloodhound will execute the teardown plan.

---

# Terraform Safety Guard

Terraform includes an account safety guard to prevent deploying Bloodhound to the wrong AWS account.

Variable:

```
expected_aws_account_id
```

Terraform validates:

```
current AWS account ID
    ==
expected account ID
```

If the IDs do not match, the deployment fails.

This prevents accidental deployments to production or unrelated accounts.

---

# Lambda Version Rollback

Bloodhound uses Lambda versioning with a `prod` alias.

Every deployment publishes a new immutable version:

```
BloodhoundLambdaV2
   ├ Version 1
   ├ Version 2
   └ Version 3
        ↑
       prod
```

If a deployment introduces a problem, the alias can be moved to a previous version.

Rollback procedure:

1. Open AWS Console
2. Navigate to Lambda → BloodhoundLambdaV2
3. Open **Aliases**
4. Edit **prod**
5. Select the previous working version

Slack integration will continue working because the Function URL always invokes the alias.

---

# Emergency Stop

If unexpected behavior occurs:

1. Set:

```
APPLY_CHANGES=false
TEARDOWN_SIMULATE=true
```

2. Redeploy or update Lambda environment variables.

This immediately disables destructive actions.

---

# Summary

Bloodhound V2 implements multiple safety layers:

* dry-run mode enabled by default
* explicit confirmation required
* whitelist protection via resource tags
* Terraform account guard
* Lambda version rollback capability

Operators must always review teardown plans before enabling deletion.
