
# Bloodhound v2 Configuration Guide

This document describes the configuration system used by **Bloodhound v2**, including environment variables, teardown behavior, and operational safety controls.

Configuration is primarily provided through environment variables.

For local development, variables are defined in:

```
.env
```

For AWS deployment, variables are configured in the Lambda **Environment Variables** section.

An example configuration template is provided in:

```
env.example
```

---

# Configuration Sources

Bloodhound loads configuration from the following sources:

| Source                       | Purpose                            |
| ---------------------------- | ---------------------------------- |
| `.env`                       | Local development configuration    |
| `env.example`                | Template for creating `.env`       |
| Lambda environment variables | Production configuration           |
| Terraform variables          | Infrastructure-level configuration |

---

# Teardown Mode Configuration

Bloodhound supports both **safe planning mode** and **real deletion mode**.

Two environment variables control teardown behavior:

```
APPLY_CHANGES
TEARDOWN_SIMULATE
```

These variables must follow specific combinations.

| APPLY_CHANGES | TEARDOWN_SIMULATE | Meaning                               |
| ------------- | ----------------- | ------------------------------------- |
| false         | true              | Safe dry-run mode (default operation) |
| true          | false             | Real deletion mode                    |
| false         | false             | Allowed but uncommon configuration    |
| true          | true              | ❌ Invalid configuration               |

If both values are set to `true`, the configuration becomes contradictory.

Example:

```
APPLY_CHANGES=true
TEARDOWN_SIMULATE=true
```

This would instruct Bloodhound to:

* perform destructive actions
* simulate destructive actions

This configuration is invalid.

The validation scripts will refuse to run if this state is detected.

---

# Deletion Safety Limit

Bloodhound includes a safety rail that limits how many resources may be deleted in a single run.

Environment variable:

```
TEARDOWN_MAX_DELETE_COUNT
```

Example:

```
TEARDOWN_MAX_DELETE_COUNT=5
```

If a teardown plan contains more resources than this limit, execution will stop.

This protects against:

* scanning bugs
* AWS API anomalies
* incorrect filtering logic
* accidental large-scale deletion events

---

# AWS Account Safety Guard

Validation scripts include a safety guard that verifies the AWS account ID before executing destructive tests.

Environment variable:

```
EXPECTED_AWS_ACCOUNT_ID
```

Example:

```
EXPECTED_AWS_ACCOUNT_ID=123456789012
```

When validation scripts run, they compare the current AWS credentials against this value.

If the account does not match, execution stops.

This prevents validation scripts from running against the wrong AWS account.

---

# Terraform Deployment Safety

Terraform includes an additional safety guard preventing destructive deployment configuration.

Variable:

```
allow_apply_mode
```

Bloodhound can delete resources when:

```
APPLY_CHANGES=true
```

However Terraform will refuse deployment unless the engineer explicitly confirms the action.

Example deployment command:

```
terraform apply -var allow_apply_mode=true
```

This prevents accidental enabling of destructive mode.

---

# Bloodhound Safety Architecture

Bloodhound includes multiple independent safety mechanisms designed to prevent accidental infrastructure deletion.

These controls operate at different layers of the system.

| Safety Layer                    | Purpose                                                    |
| ------------------------------- | ---------------------------------------------------------- |
| Slack confirmation token        | prevents accidental teardown commands                      |
| max deletion count              | prevents mass deletion events                              |
| Terraform apply guard           | prevents destructive deployment configuration              |
| Terraform account guard         | prevents deploying infrastructure in the wrong AWS account |
| validation script account guard | prevents running validation tests in the wrong AWS account |
| config consistency guard        | prevents invalid teardown configuration                    |

These protections are intentionally redundant.

If one safety mechanism fails or is bypassed, others remain in place.

This **defense-in-depth model** is common in internal cloud automation systems.

---

# Teardown Execution Flow

The teardown process follows this sequence of safety checks.

```
Engineer
   │
   ▼
Slack Command (/seek_destroy CONFIRM)
   │
   ▼
Slack Confirmation Guard
   │
   ▼
Lambda Execution
   │
   ▼
Configuration Consistency Guard
   │
   ▼
Deletion Limit Guard
   │
   ▼
AWS API Delete Calls
   │
   ▼
CloudWatch Logging
```

Each stage ensures that destructive operations occur only when explicitly intended.

---

# Related Documentation

Validation procedures are documented separately.

Slack command validation:

```
docs/validate_slack_lambda.md
```

Teardown validation workflow:

```
docs/validate_teardown.md
```

System architecture overview:

```
docs/bloodhound_v2_plan.md
```

---
