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


