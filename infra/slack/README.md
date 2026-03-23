# Slack App Manifest — Bloodhound-V2

This directory contains the Slack App configuration for Bloodhound-V2.

## Source of Truth

The Slack configuration for Bloodhound is managed via a manifest to
ensure reproducibility and prevent configuration drift.

Slack configuration is defined in:

infra/slack/bloodhound_v2_manifest.json

All Slack app settings must be applied from this manifest to ensure reproducibility and prevent configuration drift.

---

## Bloodhound Slack Command Interface

Bloodhound exposes both legacy and versioned commands.

Legacy compatibility commands:

/seek
    Run AWS resource scan

/seek_destroy CONFIRM
    Execute destructive teardown

Preferred V2 commands:

/v2_seek
    Run AWS resource scan

/v2_seek_destroy_plan
    Preview teardown plan

/v2_seek_destroy CONFIRM
    Execute destructive teardown

/v2_status
    Show system status and safety configuration

## Manifest Structure Overview

### display_information

Controls how the app appears in Slack.

- `name` — App name displayed in Slack.
- `description` — Short summary of purpose.
- `background_color` — Cosmetic only.

Safe to modify:
- Description
- Background color

Changing the name should be reviewed.

---

### features.bot_user

Defines the bot identity.

- `display_name` — Name used when posting messages.
- `always_online=false` — Bot does not simulate presence.

No presence spoofing is enabled.

---

### features.slash_commands

Bloodhound supports both **legacy commands** and **versioned v2 commands**.

Legacy commands (kept for compatibility):

- `/seek` — Non-destructive AWS scan.
- `/seek_destroy CONFIRM` — Execute destructive cleanup.

Preferred v2 command interface:

- `/v2_seek` — Non-destructive AWS resource scan.
- `/v2_seek_destroy_plan` — Preview the teardown plan without deleting resources.
- `/v2_seek_destroy CONFIRM` — Execute destructive cleanup of non-whitelisted resources.
- `/v2_status` — Show Bloodhound system status and safety configuration.

Important:

The `url` field is a placeholder during setup.  
After Lambda deployment, it must be updated to the Lambda Function URL.

Note:

The `/seek_destroy` and `/v2_seek_destroy` commands require the confirmation token `CONFIRM`.  
Slack sends this token as command text, and Bloodhound validates it before
executing destructive operations.

---

### oauth_config.scopes.bot

Defines bot permissions.

Current scopes:

- chat:write
- commands
- channels:read
- groups:read
- im:read
- mpim:read

These are intentionally minimal.

Do not add:
- admin scopes
- user impersonation scopes
- channel history scopes
- additional permissions

Without review.

---

### settings

- `socket_mode_enabled=false`
  - The app uses HTTPS (Lambda Function URL), not persistent sockets.

- `token_rotation_enabled=false`
  - Token rotation is not currently implemented.

- `interactivity.is_enabled=false`
  - No interactive components (buttons/modals).

---

## Architectural Notes

Slack commands provide the operational interface for Bloodhound.

Command flow:

```text
Slack
  ↓
Lambda Function URL
  ↓
Lambda event router
  ↓
Slack command handler (bloodhound.slack_commands)
  ↓
Execution pipeline (bloodhound.app)
```

Supported operational commands:

`/v2_seek`
    Run AWS resource scan

`/v2_seek_destroy_plan`
    Preview teardown plan

`/v2_seek_destroy CONFIRM`
    Execute destructive teardown

`/v2_status`
    Show system health and configuration

Slack only triggers execution.  

All scanning and deletion logic lives inside AWS Lambda.

Destructive behavior is gated by:

- confirmation token (`CONFIRM`)
- environment variables
- Lambda safety rails

Slack never performs deletion directly.

### Lambda Execution Logging

Bloodhound Lambda executions emit structured log markers:

[BLOODHOUND][EVENT_TYPE][request_id=...]

Examples:

[BLOODHOUND][SLACK][request_id=...]
[BLOODHOUND][SCAN][request_id=...]
[BLOODHOUND][STATUS][request_id=...]

The request_id corresponds to the AWS Lambda invocation ID
(context.aws_request_id) and allows engineers to trace a single
execution across CloudWatch logs.

---

## Change Policy

Allowed changes without review:
- Display text updates
- Slash command descriptions

Changes requiring review:

- Adding OAuth scopes
- Enabling socket mode
- Enabling token rotation
- Enabling interactivity
- Adding new slash commands beyond the current interface

Current supported command set:

`/v2_seek`
`/v2_seek_destroy_plan`
`/v2_seek_destroy CONFIRM`
`/v2_status`

---

# Terraform First-Time Setup (Existing AWS Resources)

If the IAM role or IAM policy already exist in the AWS account,
Terraform must import them into state before the first `terraform apply`.

This situation commonly occurs when:

- Bloodhound resources were created manually
- The project was previously deployed outside Terraform
- The AWS account already contains earlier Bloodhound infrastructure

To prevent Terraform errors such as:

EntityAlreadyExists: Role with name bloodhound-v2-role already exists

this repository includes a helper script that automatically imports
existing resources into Terraform state if they are detected.

### Run the bootstrap helper

From the `infra/` directory:

```bash
./bootstrap_imports.sh
```

The script will:

- Detect if the IAM role `bloodhound-v2-role` exists
- Detect if the IAM policy `bloodhound-v2-policy` exists
- Import them into Terraform state if necessary

After running the script, proceed normally:

terraform apply

When this step is required

You typically only need to run the bootstrap script:

the first time Terraform is introduced into an AWS account

when existing infrastructure already exists

Once resources are managed by Terraform, this step is no longer necessary.

Why this script exists

Terraform cannot automatically adopt resources that already exist in AWS.

The bootstrap script ensures Terraform can safely begin managing
existing infrastructure without requiring engineers to manually run
terraform import commands.

This helps avoid common onboarding errors and keeps infrastructure
management consistent across environments.

