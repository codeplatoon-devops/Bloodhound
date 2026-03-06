# Validating Slack Slash Commands and Lambda Execution Logs

This document verifies that Slack slash commands are correctly wired to **BloodhoundLambdaV2** and that the Lambda execution can be observed in **CloudWatch Logs**.

Use this procedure after:
- `terraform apply` succeeds
- Slack slash command Request URLs are set to the Lambda Function URL
- `/seek` is expected to produce Slack output

---

## Prerequisites

- You have access to the AWS account where Bloodhound V2 is deployed.
- You know the AWS region Bloodhound V2 is deployed in (currently `us-west-2`).
- The Slack app is installed in the target workspace and the slash commands exist:
  - `/seek`
  - `/seek_destroy`

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

   - `/seek`

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

17. You should see log lines that correspond to the `/seek` invocation.

---

## What You Should Look For in Logs

You are confirming these signals:

- A new log stream appears right after you run `/seek`
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

- `/seek` produces the expected Slack output (scan summary, budget summary, teardown plan)
- CloudWatch logs show a corresponding invocation and execution path
- No destructive actions occur during validation (dry-run / simulate mode only)