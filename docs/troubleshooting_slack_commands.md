# Slack Slash Command Troubleshooting

This guide explains how to diagnose and fix situations where the **Bloodhound Slack commands (such as `/v2_seek`, `/v2_seek_destroy_plan`, `/v2_seek_destroy`, or `/v2_status`) stop appearing or stop responding**.

These issues typically occur after infrastructure updates or configuration changes.

Note

Bloodhound v2 introduced new slash commands prefixed with `/v2_`.
Older documentation and logs may reference legacy commands such as
`/seek` or `/seek_destroy`.

---

# Common Causes

If a Slack slash command disappears or stops working, the most common reasons are:

1. **Slack lost the configured request URL**
2. **The Lambda Function URL changed**
3. **Terraform redeployed the Lambda**
4. **Slack app permissions were modified**
5. **Slack temporarily disabled the command due to endpoint failures**

During Terraform deployments you may see messages such as:

```
aws_lambda_function.bloodhound_v2: Modifying...
aws_lambda_alias.bloodhound_prod: Modifying...
```

If the Lambda endpoint changes during deployment, Slack may still point to the previous URL.

When Slack cannot reach the configured endpoint, it may **silently hide or disable the slash command**.

---

# Step 1 — Verify the Lambda Function URL

Run the following command:

```
aws lambda get-function-url-config \
  --function-name BloodhoundLambdaV2 \
  --region us-west-2
```

Expected output:

```
{
  "FunctionUrl": "https://xxxx.lambda-url.us-west-2.on.aws/",
  "FunctionArn": "arn:aws:lambda:us-west-2:ACCOUNT_ID:function:BloodhoundLambdaV2",
  "AuthType": "NONE"
}
```

Example from a working deployment:

```
https://kn5244cyenar6pzgexnrq5oh2m0ohyvb.lambda-url.us-west-2.on.aws/
```

Copy the **FunctionUrl** value.

---

# Step 2 — Verify the Slack Slash Command Configuration

Open the Slack developer console:

```
https://api.slack.com/apps
```

Navigate to:

```
Your App
→ Slash Commands
```

Select the command.

Legacy systems used:

/seek

Current Bloodhound v2 systems use:

/v2_seek

Verify the **Request URL** is set to:

```
https://<lambda-url>.lambda-url.us-west-2.on.aws/
```

If the URL does not match the Lambda Function URL retrieved in Step 1, update it.

Click:

```
Save
```

---

# Step 3 — Validate Lambda Endpoint Health

Before reconnecting Slack, confirm that the Lambda endpoint is reachable.

Run:

curl https://YOUR_LAMBDA_URL

Example:

curl https://kn5244cyenar6pzgexnrq5oh2m0ohyvb.lambda-url.us-west-2.on.aws/

A healthy response should return JSON similar to:

{
  "regions": ["us-east-1","us-east-2","us-west-1","us-west-2"],
  "scan": {
    "candidates_total": 41,
    "kept_total": 1
  },
  "ok": true,
  "teardown": {
    "planned_actions": 41,
    "execution": null,
    "targets_filter": null,
    "apply_changes": false,
    "simulate": true
  },
  "budget": {
    "over_budget_threshold_met": true,
    "projected_month_end_spend_usd": 3139.02,
    "dynamic_monthly_allowance_usd": 0.0
  }
}

The key indicator of a healthy endpoint is:

"ok": true

If the endpoint returns a valid JSON response and "ok": true, the Lambda function
is reachable and executing correctly.

This confirms that:

• the Lambda Function URL is valid  
• the Lambda function is running  
• AWS permissions are functioning  
• the infrastructure scan logic is executing  

If this test succeeds but the Slack command still fails, the issue is likely
related to Slack configuration or Slack command caching.

## Step 3.1 — Run Lambda Health Check

Bloodhound provides a lightweight health endpoint that verifies the Lambda
service is reachable without triggering a full scan.

Run:

curl https://YOUR_LAMBDA_URL/health

Example:

curl https://kn5244cyenar6pzgexnrq5oh2m0ohyvb.lambda-url.us-west-2.on.aws/health

Expected response:

{
  "ok": true,
  "service": "BloodhoundLambdaV2",
  "status": "healthy"
}

If this request succeeds, it confirms:

• the Lambda Function URL is valid  
• the Lambda runtime is working  
• the function is deployed and reachable

If the health check succeeds but Slack commands fail, the issue is likely
related to Slack configuration or caching.


---

# tep 4 — Reinstall the Slack App (If Commands Are Missing)

Sometimes Slack will stop showing a slash command if the app configuration changed or the endpoint failed repeatedly. Reinstalling the app refreshes the configuration.

Follow these steps.

4.1 Open the Slack App Management Page

From your Slack workspace (like the one shown in the screenshot):

Open the workspace in Slack.

In the left sidebar locate the Apps section.

Click the Bloodhound V2 - Seek & Destroy app (or the name of your Slack integration).

If the app does not appear in Slack, continue with the next step.

4.2 Open the Slack Developer Console

Open the Slack developer dashboard:

https://api.slack.com/apps

You will see a list of Slack apps associated with the workspace.

Select:

Bloodhound V2 - Seek & Destroy

4.3 Navigate to Install App

In the left sidebar of the Slack developer console, click:

Settings  
→ Install App

This will open the **Installed App Settings** page.

4.4 Reinstall the App

On the Installed App Settings page locate the button:

Reinstall to CodePlatoon

Click:

Reinstall to CodePlatoon

Slack will open an authorization screen.

Click:

Allow

This forces Slack to re-authorize the application and refresh the integration with the workspace.

This process refreshes:

• slash command registrations  
• OAuth permissions  
• bot connection to the workspace  
• request URL bindings

Note

Slack may stop showing slash commands if the configured endpoint fails repeatedly
or if infrastructure changes modify the Lambda Function URL.

Reinstalling the app forces Slack to resynchronize the command configuration
with the workspace.

4.5 Verify Slash Commands Were Restored

Return to Slack and test the command:

/v2_seek

or

/v2_seek_destroy_plan

or

/v2_seek_destroy

or

/v2_status

If the reinstall succeeded, Slack should now display the command and the Lambda endpoint should receive the request.

When Reinstallation Is Needed

Reinstalling the Slack app is often required after:

• Lambda endpoint URL changes
• Terraform redeploys the Slack integration
• Slack permissions are updated
• Slack temporarily disables a command after repeated endpoint failures

Reinstalling forces Slack to re-sync the application configuration with the workspace.

---

# Step 5 — Verify Channel Configuration

Bloodhound restricts command execution using environment variables.

Check your Lambda environment variables:

```
SLACK_SCAN_CHANNEL_ID
SLACK_ALERT_CHANNEL_ID
```

Example:

```
SLACK_SCAN_CHANNEL_ID=C0A4YLV0HNY
SLACK_ALERT_CHANNEL_ID=C0A4YLV0HNY
```

Ensure the Slack command is being executed in the correct channel.

---

# Step 6 — Perform a Direct Command Test

You can simulate a Slack command by sending a request to Lambda.

Example:

```
Legacy command test:

curl -X POST https://YOUR_LAMBDA_URL \
  -d "command=/seek"

Current Bloodhound v2 test:

curl -X POST https://YOUR_LAMBDA_URL \
  -d "command=/v2_seek"
```

If the Lambda returns JSON output, the endpoint is functioning correctly.

---

# Why This Happens

When Terraform redeploys Lambda, the following may occur:

```
aws_lambda_function.bloodhound_v2: Modifying
aws_lambda_alias.bloodhound_prod: Modifying
```

If the **Lambda Function URL changes**, Slack continues pointing to the previous URL.

Slack then attempts to call the endpoint, fails, and may temporarily hide or disable the command.

---

# Preventing This Issue

To prevent Slack command failures during deployments:

• ensure Terraform does not recreate the Lambda Function URL unnecessarily
• keep Slack request URLs synchronized with the deployed Lambda endpoint
• validate the Lambda endpoint using the smoke test script after deployments

---

Step 7 — Force Slack to Refresh Slash Commands

Sometimes Slack still has the old command configuration cached locally, even after the endpoint has been fixed.

Instead of reinstalling the entire Slack app, you can force Slack to refresh the command registration.

Method 1 — Edit and Re-Save the Slash Command

Open the Slack developer dashboard:

https://api.slack.com/apps

Select the app:

Bloodhound V2 - Seek & Destroy

Navigate to:

Slash Commands

Select the command.

Legacy command:

/seek

Current command:

/v2_seek

In the command configuration page:

Change the Request URL temporarily.

Example:

https://your-lambda-url.lambda-url.us-west-2.on.aws/

Change it to something like:

https://your-lambda-url.lambda-url.us-west-2.on.aws/?refresh=1

Click:

Save

Change the URL back to the original value.

Click:

Save

This forces Slack to refresh the command configuration and invalidate its cache.

Method 2 — Restart Slack Client

After editing the command, restart the Slack client.

On Mac:

Cmd + Q

Then reopen Slack.

On Windows:

Ctrl + Q

This ensures the Slack UI reloads the latest command definitions.

Method 3 — Refresh Slack Command Suggestions

Inside Slack, type:

/

Slack will reload the slash command list.

If either command appears in the suggestion list, the refresh worked:

/seek  (legacy)
/v2_seek  (current)

# Related Documentation

Infrastructure validation:

```
docs/run_validation.md
```

Teardown validation process:

```
docs/validate_teardown.md
```

System architecture and configuration:

```
docs/bloodhound_v2_plan.md
```

---

If you'd like, I can also help you add a **very useful small section to the main README** that says:

```
⚠ If Slack commands stop responding after deployment,
see docs/troubleshooting_slack_commands.md
```

This is something many infrastructure repos include so engineers can quickly find fixes.
