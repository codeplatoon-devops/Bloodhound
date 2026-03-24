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

The `url` field in the manifest is a placeholder during setup.

After Terraform deploys the Lambda function, the Slack Request URL
for each slash command must be updated to the Lambda Function URL
output by Terraform.

Example:

https://<lambda-function-id>.lambda-url.<region>.on.aws

This URL becomes the public HTTPS endpoint used by Slack to
invoke Bloodhound.

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
Slack handler (bloodhound.handlers.slack_handler)
  ↓
Slack command parser (bloodhound.slack_commands)
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

### Note:

Slack never performs AWS operations directly.

Slack only sends HTTPS requests to the Lambda Function URL.
All scanning, planning, and deletion logic runs entirely inside
the Bloodhound Lambda execution environment.

### Destructive behavior is gated by:

Destructive behavior is gated by multiple safety controls:

- confirmation token (`CONFIRM`) sent in the slash command
- environment configuration (APPLY_CHANGES, TEARDOWN_SIMULATE)
- Lambda safety rails that prevent destructive execution unless
  explicitly enabled

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

