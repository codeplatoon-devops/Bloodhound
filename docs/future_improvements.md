# Bloodhound V2 – Future Infrastructure Hardening (TODO)

WIP .. HERE AS A REMINDER

This document records security and platform improvements that should be implemented **after the V2 migration is stable**.

These items were intentionally deferred during the V2 takeover in order to follow the engineering principle:

> One axis of change at a time.

The initial goal was to successfully deploy and stabilize **BloodhoundLambdaV2** without introducing additional infrastructure changes that could complicate debugging.

Once V2 has run successfully for several cycles, the following improvements should be implemented.

---

## 1. Move Slack Secrets to AWS Secrets Manager

### Current State

Slack secrets are currently provided through Lambda environment variables via Terraform:

* `SLACK_BOT_TOKEN`
* `SLACK_SIGNING_SECRET`

These values are supplied through `terraform.tfvars` and therefore appear in Terraform state.

### Risks

* Secrets may be stored in Terraform state
* Secrets could be exposed if state storage is misconfigured
* Secrets exist outside AWS secret management systems

### Target Architecture

Secrets should be stored in **AWS Secrets Manager** and retrieved at runtime.

Example secret:

```
bloodhound/slack
```

Secret value example:

```
{
  "bot_token": "...",
  "signing_secret": "..."
}
```

### Implementation Steps

1. Create secret in AWS Secrets Manager.
2. Grant Lambda IAM role permission:

```
secretsmanager:GetSecretValue
```

3. Pass secret ARN to Lambda via environment variable:

```
SLACK_SECRET_ARN
```

4. Update Lambda code to retrieve secret at runtime.

Result:

```
Secrets Manager
       ↓
Lambda IAM Role
       ↓
Lambda runtime retrieval
```

Benefits:

* Secrets are encrypted
* Access is auditable
* Secrets can be rotated without redeploying Lambda

---

## 2. Remove Secrets from Terraform Variables

Once Secrets Manager is implemented:

Remove the following from `terraform.tfvars`:

```
SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
```

Terraform should only provide the **secret ARN**, not the secret value.

Example:

```
lambda_env = {
  SLACK_SECRET_ARN = "arn:aws:secretsmanager:..."
}
```

---

## 3. Introduce CI/CD Deployment Role (GitHub OIDC)

### Current State

Terraform is executed locally using developer AWS credentials.

### Risks

* Infrastructure depends on developer access
* Manual deployments increase risk of configuration drift

### Target Architecture

Deploy infrastructure through GitHub Actions using **OpenID Connect (OIDC)**.

Flow:

```
GitHub Actions
      ↓
OIDC authentication
      ↓
Assume IAM role
      ↓
Terraform apply
```

Benefits:

* No long-lived AWS credentials
* Infrastructure ownership belongs to the organization
* Deployments become auditable and reproducible

---

## 4. Restrict Lambda IAM Permissions

The Lambda role currently has broad permissions to support scanning and teardown operations.

Future improvements should include:

* splitting scanning and deletion permissions
* limiting actions to specific services used by Bloodhound
* adding explicit resource constraints where possible

Example separation:

```
BloodhoundScanRole
BloodhoundDeleteRole
```

This reduces the blast radius of the Lambda.

---

## 5. Configure Terraform Remote State

Terraform state should be stored remotely instead of locally.

Recommended backend:

```
S3 + DynamoDB state locking
```

Benefits:

* prevents state corruption
* supports multiple maintainers
* enables CI/CD workflows

---

## 6. Add Structured Logging

Lambda logs should include structured JSON logs to improve observability.

Example fields:

```
event_type
command
region
resource_count
teardown_plan
execution_mode
```

This improves debugging and monitoring.

---

## 7. Implement Slack Request Validation Monitoring

Slack signature verification is already implemented.

Future improvement:

Log validation failures with rate limits to detect potential abuse.

---

## Summary

These improvements move Bloodhound toward a production-grade serverless architecture.

Target state:

```
Slack
   ↓
Lambda Function URL
   ↓
BloodhoundLambdaV2
   ↓
AWS APIs

Secrets:
AWS Secrets Manager

Deployments:
GitHub Actions (OIDC)

Infrastructure:
Terraform with remote state
```

These changes should only be implemented **after the V2 migration is confirmed stable**.

## Future Infrastructure Hardening

Bloodhound v2 currently prioritizes **deployment stability and operational safety**.

Several platform improvements were intentionally deferred during the V2 migration in order to follow the engineering principle:

> One axis of change at a time.

The current architecture already includes operational safeguards such as:

* Lambda version publishing
* a production alias (`prod`)
* Terraform-controlled rollback support
* immutable Lambda versions
* Slack integration that does not depend on version changes

These mechanisms ensure that deployments and rollbacks remain safe while the new V2 infrastructure stabilizes.

Additional security and platform improvements are planned once the system has been validated in production.

Examples include:

* migrating Slack secrets to **AWS Secrets Manager**
* introducing **GitHub OIDC deployment roles**
* configuring **Terraform remote state (S3 + DynamoDB)**
* tightening Lambda IAM permissions
* improving observability and structured logging


Yes — adding a **reminder section for the AWS account guard** in that document is a very good idea. It belongs alongside the other **post-stabilization hardening tasks** because it’s a **runtime safety control** and not required to stabilize V2.

Below is a section you can **append to your document** in the same style and structure you are already using.

---

# 8. Implement AWS Account Runtime Guard

### Current State

Bloodhound v2 includes **documentation and validation-script guards** that verify the AWS account ID before executing destructive operations.

However, the **Lambda runtime itself does not yet enforce this check**.

The `/v2_status` command currently displays:

```
expected_account_id: not-configured
```

This indicates that the runtime guard has not yet been connected to the configuration system.

The guard is partially implemented in the codebase but has not yet been integrated into:

```
config.py
app.py
```

---

### Risks

Without a runtime account guard, it is theoretically possible for Bloodhound to execute against the wrong AWS account if credentials are misconfigured.

Examples:

```
running teardown against production instead of development
running validation scripts against the wrong account
```

Other safeguards already exist (dry-run defaults, deletion limits, Terraform guards), but adding an account verification layer provides **additional defense-in-depth**.

---

### Target Architecture

Bloodhound should verify the AWS account identity during Lambda startup before performing any scan or teardown operations.

Runtime flow:

```
Lambda start
   ↓
Load configuration
   ↓
Retrieve AWS caller identity (STS)
   ↓
Compare to EXPECTED_AWS_ACCOUNT_ID
   ↓
Abort execution if mismatch
```

---

### Implementation Steps

1. Add environment variable:

```
EXPECTED_AWS_ACCOUNT_ID
```

Example:

```
EXPECTED_AWS_ACCOUNT_ID=123456789012
```

---

2. Extend `AwsConfig` in `config.py`:

```
expected_account_id: Optional[str]
```

---

3. Load the variable during configuration loading.

Example:

```
expected_account_id = _env("EXPECTED_AWS_ACCOUNT_ID")
```

---

4. Add runtime verification in `app.py` after configuration loading.

Example logic:

```
sts = clients.sts
identity = sts.get_caller_identity()
runtime_account_id = identity["Account"]

if expected_account_id and runtime_account_id != expected_account_id:
    abort execution
```

---

5. Update `/v2_status` to display:

```
expected_account_id
runtime_account_id
account_verified
```

Example output:

```
Safety Guards

max_deletion_limit: 5
expected_account_id: 123456789012
runtime_account_id: 123456789012
account_verified: true
```

---

### Benefits

This guard prevents infrastructure automation from operating in the wrong AWS account.

It is particularly valuable in environments with multiple accounts such as:

```
development
staging
production
```

This mechanism is commonly used in internal cloud automation systems to provide an additional safety layer before destructive operations.

---

### Deployment Timing

This change should be implemented **after V2 stability is confirmed**.

It introduces additional AWS API calls (`sts:GetCallerIdentity`) and runtime checks, which were intentionally deferred during the V2 migration to minimize moving parts.

---

# Resulting Safety Architecture

Once implemented, Bloodhound will include the following independent safety mechanisms:

```
Slack confirmation guard
Deletion limit guard
Terraform destructive-mode guard
Validation script account guard
Runtime AWS account verification
```

This creates a **defense-in-depth safety model** for automated infrastructure cleanup.


