# GitHub Actions Automation

This document describes the GitHub Actions workflows used by the
Bloodhound system to invoke the AWS Lambda scanner and perform
automated operational checks.

The workflows provide a safe and auditable mechanism for triggering
infrastructure scans and validation runs directly from the repository.

---

## Overview

The GitHub workflow invokes the Lambda function:

    BloodhoundLambdaV2

This version contains the V2 scanning logic and Slack-integrated
operational commands.

The Lambda determines its execution behavior based on the event payload:

    event["source"]

Example event payload:

    { "source": "scan" }

This allows the same Lambda function to support multiple operational
execution modes.

---
## Architecture

The GitHub workflow acts as an external trigger for the Bloodhound
Lambda scanner.

```text
Execution flow:

    GitHub Actions
        ↓
    AWS Lambda (BloodhoundLambdaV2)
        ↓
    Lambda event router
        ↓
    Execution handler (scan / status / scheduled)
        ↓
    AWS API scanning
        ↓
    Slack reporting
```

---

## Workflow Location

Bloodhound uses two GitHub Actions workflows.

Scheduled automation workflow:

    .github/workflows/invoke_lambda.yml

Manual operator workflow:

    .github/workflows/bloodhound_ops.yml

The scheduled workflow runs automated infrastructure scans,
while the manual workflow allows engineers to invoke specific
Bloodhound operations directly from the GitHub Actions UI.

## Workflow Triggers

The workflow supports two trigger types.

### Scheduled Runs

Bloodhound automatically runs scheduled scans twice per day.

Cron configuration:

    0 16,4 * * *

Schedule (UTC):

    16:00 UTC — 11:00 AM EST
    04:00 UTC — 11:00 PM EST

Scheduled runs allow Bloodhound to continuously monitor AWS
infrastructure for unused resources and cost anomalies.

---

### Manual Runs

Engineers can manually invoke the workflow from the GitHub Actions UI.

Location:

    Repository → Actions → Bloodhound Operations → Run workflow

Manual runs allow engineers to trigger specific execution modes.

Available modes:

    scan
    status
    validate_scheduler
    validation (currently disabled)

Notes:

- `validate_scheduler` simulates an EventBridge scheduled invocation using:
```json
      { "source": "scheduled" }
```

- The validation workflow exists but is currently disabled in CI while
  teardown validation infrastructure is being stabilized.

---

## Execution Modes

The selected mode is passed to Lambda as:

    { "source": "<mode>" }

Each mode triggers a different execution path.

### scan

Runs a full infrastructure scan across supported AWS regions.

Identifies unused resources and generates a teardown plan.

---

### validation

Runs a safe validation workflow that verifies:

- Lambda deployment
- scanner operation
- cost monitoring integration
- teardown safety logic

Validation workflows use disposable test resources.

---

### validate_scheduler

Simulates the scheduled execution path.

This mode sends the following payload to the Lambda:
```json
    { "source": "scheduled" }
```

This allows engineers to validate the scheduled execution path
without waiting for the production scheduler or cron execution.

---

### status

Runs a system health check that verifies:

- AWS API connectivity
- scanner configuration
- environment variables
- Slack integration status

---

## Lambda Invocation

The workflow invokes Lambda using the AWS CLI:

    aws lambda invoke

Invocation artifacts are stored in two files:

Response payload:

    output.json

Invocation metadata:

    lambda_meta.json

Metadata includes:

    StatusCode
    ExecutedVersion
    FunctionError
    LogResult

---

## CI Observability Improvements

The workflow includes several improvements to make CI runs easier
to debug and monitor.

---

### Structured CI Logs

GitHub log groups are used to create collapsible sections in the
workflow logs.

Example sections:

    Bloodhound Lambda Invocation
    Lambda Response Payload
    Lambda Invocation Metadata
    Lambda Error Check

This improves readability when analyzing CI runs.

---

### Automatic Failure Detection

The workflow performs explicit checks on the Lambda invocation metadata.

CI will fail if either condition occurs:

1. Lambda reports a runtime error

    FunctionError detected

2. Lambda invocation returns a non-200 status code

This prevents CI pipelines from silently succeeding when the Lambda
execution fails.

---

### Example Failure

If Lambda throws an exception:

    FunctionError: Unhandled

The GitHub workflow will terminate with:

    JOB FAILED

---

## CloudWatch Log Streaming

The workflow optionally retrieves recent Lambda logs directly from
CloudWatch and prints them into the GitHub workflow output.

This allows engineers to debug Lambda behavior without leaving the
GitHub Actions interface.

Log retrieval uses:

    aws logs describe-log-streams
    aws logs get-log-events

The workflow retrieves the most recent log stream from:

    /aws/lambda/BloodhoundLambdaV2

and prints recent log messages.

---

## Operational Benefits

The GitHub automation provides several operational advantages.

### Auditable Operations

All Lambda invocations are recorded in the repository's CI history.

Engineers can see:

- who triggered the workflow
- when it ran
- the resulting logs

---

### Safe Operational Control

Infrastructure scans and validation workflows can be executed
without requiring direct AWS CLI access.

Engineers can safely trigger operations through GitHub.

---

### Faster Debugging

CI logs now include:

- Lambda response payload
- invocation metadata
- runtime logs from CloudWatch

This significantly reduces time required to diagnose failures.

---


## Potential Enhancements

The current workflow already streams Lambda logs directly
into the GitHub Actions output for debugging.

Future enhancements may include:

- attaching Lambda logs as downloadable CI artifacts
- rendering scan summaries in GitHub workflow summaries
- automated cost anomaly alerts
- integration with security scanning pipelines

These additions would further improve observability and
operational reporting.