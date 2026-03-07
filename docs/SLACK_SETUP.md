# Slack Setup (Bloodhound-V2)

This project uses a Slack App to post scan summaries, budget alerts, and handle slash commands.

The preferred setup method is **manifest-based configuration**, which ensures Slack app settings are version-controlled and reproducible.

---

## ✅ Recommended: Manifest-Based Setup (V2)

The canonical Slack configuration lives in:

`infra/slack/bloodhound_v2_manifest.json`

## Slack Manifest Design (Architecture Notes)

The Slack app configuration is managed via a JSON manifest to ensure reproducibility and version control.

### Design Principles

**Least privilege**
Only minimal bot scopes are requested:

- `chat:write` — post scan and budget messages  
- `commands` — enable `/v2_seek`, `/v2_seek_destroy`, `/v2_status`  
- `channels:read`, `groups:read`, `im:read`, `mpim:read` — read channel metadata

Note: Although the Slack commands are `/v2_seek` and `/v2_seek_destroy`,
the internal execution modes remain `seek` and `seek_destroy`.
This preserves compatibility with existing scripts, validation tools,
and documentation across the repository.

No admin or elevated scopes are requested.

## Slack Commands (Bloodhound V2)

The Slack interface exposes the following commands:

| Command | Description |
|-------|-------------|
| `/v2_seek` | Runs a non-destructive AWS scan and posts results |
| /v2_seek_destroy_plan | Generates a teardown preview of resources that would be deleted |
| /v2_seek_destroy CONFIRM | Executes destructive cleanup of non-whitelisted resources |
| /v2_status | Returns service status and health information |

Example usage:

/v2_seek

/v2_seek_destroy_plan

/v2_seek_destroy CONFIRM

/v2_status

## Internal Command Mapping

Although Slack commands are versioned (`/v2_*`), the internal Lambda
execution modes remain unchanged.

| Slack Command | Internal Mode |
|---------------|--------------|
| /v2_seek | seek |
| /v2_seek_destroy_plan | seek_destroy_plan |
| /v2_seek_destroy| seek_destroy |
| /v2_status | status |

## Teardown Safety Workflow

Bloodhound uses a two-step teardown workflow to prevent accidental
destructive operations.

Typical workflow:

1. /v2_seek
   Perform a scan and generate a teardown preview.

2. /v2_seek_destroy_plan
   Review the full deletion plan for non-whitelisted resources.

3. /v2_seek_destroy CONFIRM
   Execute the teardown plan and delete resources.



**Stateless HTTP integration**
- `socket_mode_enabled = false`
- Slash commands use a Lambda Function URL (HTTPS endpoint)

This keeps the architecture simple and serverless.

**Non-interactive design**
- No buttons, modals, or interactive components.
- All actions are explicit slash commands.

**Deployment flow**
The `url` fields in slash commands are placeholders during setup.

After deploying the infrastructure, retrieve the Lambda endpoint with:

terraform output bloodhound_lambda_url

Use this URL as the Request URL for all slash commands.

### 1. Create or Update the Slack App

1. Go to https://api.slack.com/apps
2. Click **Create New App**
3. Choose **From an app manifest**
4. Select your workspace
5. Paste the contents of:
   `infra/slack/bloodhound_v2_manifest.json`
6. Click **Create**

If the app already exists:
- Go to **App Manifest**
- Replace contents with the repo JSON
- Click **Save Changes**


### 2. Install the App

1. Go to **Install App**
2. Click **Install to Workspace**
3. Approve permissions

### 3. Retrieve Required Secrets (Manual Step)

After installation:

From **OAuth & Permissions**:
- Copy **Bot User OAuth Token** → `SLACK_BOT_TOKEN`

From **Basic Information**:
- Copy **Signing Secret** → `SLACK_SIGNING_SECRET`

Store securely.
Do NOT commit these to git.

### 4. Invite Bot to Channel

In Slack:

`/invite @bloodhoundv2`


### 5. Capture Channel IDs

Right-click channel → Copy link

Extract channel ID from URL.

Set:

```md
SLACK_SCAN_CHANNEL_ID=
SLACK_ALERT_CHANNEL_ID=

```

### 6. Validate

Run locally:

`tools/run_local.py`

Confirm Slack messages appear.

# ⚠️ Legacy Manual Slack Setup (Deprecated)

The steps below reflect the original manual Slack configuration
approach used prior to manifest-based setup.

Use only if manifest configuration is unavailable.

## Slack setup (from scratch)

This project’s main `README.md` assumes you already have:

- a Slack bot token (`SLACK_BOT_TOKEN`)
- Slack channel IDs for `SLACK_SCAN_CHANNEL_ID` and `SLACK_ALERT_CHANNEL_ID`

Use this guide only if you need to create/configure the Slack app/bot from scratch.

---

### 1) Create a Slack App

1. Go to [Slack API: Applications](https://api.slack.com/apps).
2. Click **Create New App**.
3. Choose **From scratch**.
4. Name the app and select the workspace.
5. Click **Create App**.

---

### 2) Add bot permissions

1. In your Slack app settings, go to **OAuth & Permissions**.
2. Under **Scopes**, add bot token scopes:
   - `chat:write`
   - `channels:read`
   - `groups:read`
3. Click **Install App to Workspace** and approve.
4. Copy the **Bot User OAuth Token** (this is your `SLACK_BOT_TOKEN`).

---

### 3) Get the Slack Channel ID

1. In Slack, open the channel.
2. Copy the channel ID from the channel details (or URL).
3. Set:
   - `SLACK_SCAN_CHANNEL_ID=<channel_id>`
   - `SLACK_ALERT_CHANNEL_ID=<channel_id>` (can be the same or different)

---

### 4) Invite the bot to the channel

In the channel, run:

- `/invite @your-bot-name`

---


## Planned Command: `/v2_status`

The `/v2_status` command will return operational status information such as:

- Lambda health
- scan configuration
- budget monitoring state
- last execution summary

Example:

/v2_status

Response example:

Bloodhound V2 Status

Service: healthy
Lambda: active
Budget monitor: enabled
Last scan: 2 minutes ago

## Validate Slack Command Endpoint

After deployment, confirm the Lambda endpoint is active.

Example:

curl $(terraform output -raw bloodhound_lambda_url)/health

Expected response:

{
  "ok": true,
  "service": "BloodhoundLambdaV2",
  "status": "healthy"
}

