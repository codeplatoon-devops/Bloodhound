# Validating Slack Slash Commands and Lambda Execution Logs

This document verifies that Slack slash commands are correctly wired to **BloodhoundLambdaV2** and that the Lambda execution can be observed in **CloudWatch Logs**.

Use this procedure after:
- `terraform apply` succeeds
- Slack slash command Request URLs are set to the Lambda Function URL
- `/v2_seek` is expected to produce Slack output

---

## Prerequisites

- You have access to the AWS account where Bloodhound V2 is deployed.
- You know the AWS region Bloodhound V2 is deployed in (currently `us-west-2`).
- The Slack app is installed in the target workspace and the slash commands exist:
  - `/v2_seek`
  - `/v2_seek_destroy`

---

## Part A — Open CloudWatch Logs (Set This Up First)

1. Log into the **AWS Console** (the same AWS account where Terraform deployed Bloodhound V2).

2. In the AWS console top-right region selector, set the region to:

   - `us-west-2`

   Important:
   If you are in the wrong region, the log group will not appear and you may see “Function not found” type errors.

3. In the AWS Console search bar, type:

   - `CloudWatch`

   Open **CloudWatch**.

4. In the left-side menu, navigate to:

   - **Logs**
     - **Log Management**
   - **Log groups**

5. In the Log groups search bar, type:

   - `/aws/lambda/BloodhoundLambdaV2`

6. Click the log group:

   - `/aws/lambda/BloodhoundLambdaV2`

7. Click **Latest log streams** (or click the most recent log stream listed).

   You should now be on a screen that shows log events.

8. Leave this page open. You are now “watching logs.”

---

## Part B — Trigger the Slash Command in Slack

9. Open Slack (the workspace where **Bloodhound V2** is installed).

10. Navigate to your admin/testing channel (example):

   - `bloodhound-seek-n-destroy-admin`

11. Run the slash command:

   - `/v2_seek`

12. Confirm Slack immediately responds with a short acknowledgement message like:

   - “BloodHound is on the hunt...please stand by.”

This message indicates that Slack successfully invoked the Lambda handler and the async worker path has started.

---

## Part C — Watch Logs Update in CloudWatch

13. Immediately switch back to the CloudWatch log stream page you opened in Part A.

14. Click the **Refresh** button (or refresh icon).

15. If you are viewing the **log streams list** (instead of a stream’s log events):

   - refresh the list
   - click the newest log stream (the one with the most recent timestamp)

16. If you are already inside a log stream viewing log events:

   - click refresh until you see new log lines appear

17. You should see log lines that correspond to the `/v2_seek` invocation.

---

## What You Should Look For in Logs

You are confirming these signals:

- A new log stream appears right after you run `/v2_seek`
- Log lines indicate the slash command request was received
- Log lines indicate region scanning activity
- Log lines indicate Slack message posting
- No errors occur

Common errors to watch for:

- Missing environment variables (Slack tokens, signing secret, etc.)
- Slack authentication errors
- Slack signature verification failures
- AWS permissions errors (AccessDenied)
- Region mismatch (scanning wrong regions)

---

## If You Do Not See Logs

### 1) Wrong AWS Region

You must use the same region where Terraform deployed the Lambda.
For Bloodhound V2 this is typically:

- `us-west-2`

Fix:
- Switch the AWS Console region to `us-west-2`
- Repeat the steps above

---

### 2) Wrong Log Group

The log group must be exactly:

- `/aws/lambda/BloodhoundLambdaV2`

Fix:
- Re-search log groups in CloudWatch
- Ensure you are clicking the correct group name

---

### 3) No New Log Stream Appears

If Slack shows no response and CloudWatch shows no activity, Lambda may not be invoked.

Check:

- Slack App → Slash Commands → Request URL is correct
- The Request URL matches the Terraform output Lambda Function URL
- The Lambda Function URL is still enabled
- Lambda Function URL permissions still exist
- Your Slack app is installed in the correct workspace

---

## Optional Fast Path (Sometimes Easier)

Instead of navigating CloudWatch manually:

1. AWS Console → **Lambda**
2. Click **BloodhoundLambdaV2**
3. Go to the **Monitor** tab
4. Click **View logs in CloudWatch**
5. Continue from Part A step 7

---

## Success Criteria

This validation is complete when:

- `/v2_seek` produces the expected Slack output (scan summary, budget summary, teardown plan)
- `/v2_seek_destroy` enforces its confirmation and allowlist protections
- CloudWatch logs show a corresponding invocation and execution path
- No destructive actions occur during validation (dry-run / simulate mode only)

## Validating `/v2_seek_destroy` Safety Controls

The `/v2_seek_destroy` command has multiple protection layers to prevent
accidental destructive actions.

During validation you should confirm these protections are functioning.

### Step 1 — Run destroy command without confirmation

In Slack run:


/v2_seek_destroy


Expected result:

Slack should return a message similar to:


Not allowed. Use /v2_seek_destroy CONFIRM (and ensure you are allowlisted).


This confirms the confirmation token protection is working.

---

### Step 2 — Run destroy command with confirmation

Run:

/v2_seek_destroy CONFIRM

The command may still be rejected if allowlists are configured.

Bloodhound validates the following environment variables:

- `SLACK_DESTROY_CONFIRM_TOKEN`
- `SLACK_ALLOWED_USER_IDS`
- `SLACK_ALLOWED_CHANNEL_IDS`

If allowlists are defined and the user/channel is not included,
the command will return the same **Not allowed** response.

---

### Expected behavior during validation

Even when the command succeeds, destructive actions should **not**
occur because runtime safety flags are enabled.

Relevant environment variables:

APPLY_CHANGES=false
TEARDOWN_SIMULATE=true

The full teardown safety model and configuration reference
is documented in:

`docs/bloodhound_v2_plan.md`

This forces Bloodhound to operate in **dry-run mode**, meaning it
will only generate a teardown plan and never call destructive AWS APIs.

---

### What successful validation looks like

You should observe:

1. `/v2_seek_destroy` without confirmation → rejected
2. `/v2_seek_destroy CONFIRM` → allowed only if allowlisted
3. Slack responses generated correctly
4. Lambda invocation visible in CloudWatch logs
5. No AWS resources are deleted

## Verify Lambda Environment Variables

If Slack commands behave unexpectedly, verify that the Lambda environment
variables were correctly deployed by Terraform.

NOTE: Ensure the AWS CLI region matches the Terraform deployment region
(us-west-2). Otherwise Lambda may appear "missing".

Run:

aws lambda get-function-configuration \
--region us-west-2 \
--function-name BloodhoundLambdaV2 \
--query 'Environment.Variables'

This command prints the runtime configuration currently applied to the Lambda.

Confirm that the expected variables appear, such as:

SLACK_ENABLED  
SLACK_SCAN_CHANNEL_ID  
SLACK_ALERT_CHANNEL_ID  
SLACK_SIGNING_SECRET  
APPLY_CHANGES  
TEARDOWN_SIMULATE  

If any variables are missing, Terraform may not have applied the latest
configuration.

To fix:

terraform plan  
terraform apply

---

## Watching Lambda Logs Live

Instead of refreshing CloudWatch in the console, you can stream Lambda
logs directly in your terminal. This is very useful when debugging
slash command behavior while triggering `/v2_seek` or `/v2_seek_destroy`.

### Command

```bash
aws logs tail /aws/lambda/BloodhoundLambdaV2 \
--region us-west-2 \
--follow
````

### What this does

This command:

```
connects to CloudWatch
↓
streams new Lambda log events
↓
prints them in your terminal
```

It behaves similarly to:

```
tail -f
```

for Lambda logs.

---

### Recommended workflow

Open **two terminals**.

#### Terminal 1 — watch logs

Run:

```bash
aws logs tail /aws/lambda/BloodhoundLambdaV2 \
--region us-west-2 \
--follow
```

Leave it running.

#### Terminal 2 — trigger Slack command

In Slack run:

```
/v2_seek
```

or

```
/v2_seek_destroy CONFIRM
```

---

### Expected output

When Lambda runs you should see logs similar to:

```
START RequestId: ...
Received Slack slash command
command=/v2_seek
Scanning region us-east-1
Scanning region us-west-2
Posting Slack summary
END RequestId: ...
REPORT Duration: 14110 ms
```

This confirms the full execution path from Slack → Lambda → AWS scan.

---

### Why this command is useful

It allows you to immediately see runtime errors such as:

```
Slack signature verification failed
Missing environment variable
AccessDenied
Invalid token
```

without navigating through the CloudWatch console.

---

### Optional improvements

Add timestamps:

```bash
aws logs tail /aws/lambda/BloodhoundLambdaV2 \
--region us-west-2 \
--follow \
--format short
```

Filter only errors:

```bash
aws logs tail /aws/lambda/BloodhoundLambdaV2 \
--region us-west-2 \
--follow \
--filter-pattern "ERROR"
```

## Common Failure Scenarios

This section lists common issues that may occur when validating
Slack commands or Lambda execution.

---

### 1. Slash command returns “Function not found”

Example error:

An error occurred (ResourceNotFoundException)
Function not found

Cause:

The AWS CLI or console is using the wrong region.

Bloodhound V2 is deployed in:

us-west-2

Fix:

Specify the region explicitly when using the CLI:

aws lambda get-function-configuration
--region us-west-2
--function-name BloodhoundLambdaV2


Or switch the AWS Console region to `us-west-2`.

---

### 2. Slack command produces no response

Possible causes:

- Slack Request URL is incorrect
- Lambda Function URL is disabled
- Lambda permissions were removed
- Slack app was not reinstalled after manifest changes

Fix:

Verify the Slack command configuration:


Slack App → Slash Commands


Ensure the Request URL matches the Terraform output:


Lambda Function URL


---

### 3. `/v2_seek_destroy` returns “Not allowed”

Example response:

Not allowed. Use /v2_seek_destroy CONFIRM (and ensure you are allowlisted).

This is expected behavior if safety checks fail.

Possible causes:

- Missing confirmation token
- User not in `SLACK_ALLOWED_USER_IDS`
- Channel not in `SLACK_ALLOWED_CHANNEL_IDS`

Verify the Lambda environment variables:

SLACK_DESTROY_CONFIRM_TOKEN
SLACK_ALLOWED_USER_IDS
SLACK_ALLOWED_CHANNEL_IDS

---

### 4. Slash command succeeds but no logs appear

Cause:

The CloudWatch log group may not exist yet if Lambda has never run.

Fix:

Run the command again:

/v2_seek

Lambda automatically creates the log group on first execution.

---

### 5. Terraform changes not reflected in Lambda

Cause:

Terraform may not have applied the latest configuration.

Fix:

Run:

terraform plan
terraform apply

Then verify Lambda environment variables:

aws lambda get-function-configuration
--region us-west-2
--function-name BloodhoundLambdaV2
--query 'Environment.Variables'

---

### 6. Unexpected teardown behavior

If `/v2_seek_destroy` appears to plan more resources than expected:

Check the whitelist configuration:

KEEP_TAG_KEY
KEEP_TAG_VALUE

Resources tagged with these values will be excluded from teardown.

Example:

bloodhound:keep=true

---

## When to Escalate

If validation fails after following the steps above:

1. Capture the Slack command output
2. Capture the CloudWatch logs
3. Capture the Lambda environment variables
4. Capture the Terraform plan output

These artifacts should be sufficient to diagnose most issues with the
Slack → Lambda → AWS execution pipeline.
