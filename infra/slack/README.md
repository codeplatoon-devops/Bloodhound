# Slack App Manifest — Bloodhound-V2

This directory contains the Slack App configuration for Bloodhound-V2.

## Source of Truth

Slack configuration is defined in:

infra/slack/bloodhound_v2_manifest.json

All Slack app settings must be applied from this manifest to ensure reproducibility and prevent configuration drift.

---

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

Defines supported commands:

- `/seek` — Non-destructive AWS scan.
- `/seek_destroy` — Destructive scan (gated by confirmation token and Lambda safety rails).

Important:
The `url` field is a placeholder during setup.
After Lambda deployment, it must be updated to the Lambda Function URL.

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

- Slack only triggers execution.
- All scanning and deletion logic lives inside AWS Lambda.
- Destructive behavior is gated by environment variables and confirmation tokens.
- Slack never performs deletion directly.

---

## Change Policy

Allowed changes without review:
- Display text updates
- Slash command descriptions

Changes requiring review:
- Adding scopes
- Enabling socket mode
- Enabling token rotation
- Enabling interactivity
- Adding new commands

---

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

Detect if the IAM role bloodhound-v2-role exists

Detect if the IAM policy bloodhound-v2-policy exists

Import them into Terraform state if necessary

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

