# Bloodhound v2 (AWS resource scanner + Slack alerts + optional teardown)

## 📌 Quick Overview

New to the project?

Start here:

👉 [FEATURES.md](FEATURES.md) — high-level overview of what Bloodhound does.

For deeper engineering documentation:

📚 [docs/](docs/)

## Table of Contents

- [Stop — Read This Before Running Bloodhound](#️-stop--read-this-before-running-bloodhound)
- [Documentation](#documentation)
- [Requirements](#requirements)
- [Local Setup and Testing](#local-setup--testing)
- [Dependency Management](#dependency-management)
- [Configure .env](#configure-env)
- [Run Locally](#run-locally)
- [Whitelisting](#whitelisting)
- [Teardown Controls](#teardown-controls-important)
- [Build the Lambda Deployment Zip](#build-the-lambda-deployment-zip-v2)
- [Deploy to AWS Lambda](#deploy-to-aws-lambda-v2)
- [Terraform Deployment Workflow](#terraform-deployment-workflow)
- [Slack Slash Commands](#slack-slash-commands-v2)
- [Validation Scripts](#validation-scripts)
- [GitHub Automation](#️-github-automation)
  - [Scheduled Scan Workflow](#scheduled-scan-workflow)
  - [Manual Operations Workflow](#manual-operations-workflow)
- [GitHub OIDC Authentication Bootstrap](#github-oidc-authentication-bootstrap)
- [Bootstrap Script](#bootstrap-script)
- [Run the bootstrap script](#run-the-bootstrap-script)
- [Trust Policy](#trust-policy)
- [Security Notes](#security-notes)

Bloodhound v2 scans selected AWS regions for common cost-leak resources, posts results to Slack, and can optionally delete resources that are **not** whitelisted.


- Clone this repo
- Configure `.env` for local testing
- Rebuild the deployment zip locally (the `.build/` dir is not committed)
- Configure Lambda env vars to match your `.env`

If you need to create a Slack bot from scratch, see `docs/SLACK_SETUP.md`.

Project docs:

- v2 plan: `docs/bloodhound_v2_plan.md`

![AWS Architecture Diagram (v2)](assets/bloodhound_lambda_architecture_v2.svg)

## ⚠️ Safety Notice — Read Before Running Bloodhound

Bloodhound can delete AWS infrastructure when `APPLY_CHANGES=true`.

Before running validation scripts or enabling destructive mode, review:

📘 [Bloodhound v2 Configuration Guide](docs/configuration_system.md)

This document explains:

- teardown mode configuration
- deletion safety limits
- AWS account validation guards
- Terraform deployment protections
- Bloodhound safety architecture

---

## Documentation

Configuration and safety model:

📘 [docs/configuration_system.md](docs/configuration_system.md)

Slack command validation:

📘 [docs/slack_and_lambda_validation.md](docs/slack_and_lambda_validation.md)

Controlled teardown validation:

📘 [docs/validate_teardown.md](docs/validate_teardown.md)

System architecture:

📘 [docs/bloodhound_v2_plan.md](docs/bloodhound_v2_plan.md)

---

## Requirements

- Python 3.10+ for local dev (or match your Lambda runtime)
- AWS CLI configured (use `AWS_PROFILE=...` as needed). To set it up the first time: `aws configure --profile <name>` (or `aws configure` for the default profile). To see what profiles you have: `aws configure list-profiles`; your local config/creds live in `~/.aws/config` and `~/.aws/credentials` (view with `cat ~/.aws/config` and `cat ~/.aws/credentials`).
- Slack bot token and channel IDs

---

## Local setup + testing

### Create a venv and install dependencies

From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip

# Runtime dependencies (used by Lambda)
.venv/bin/python -m pip install -r requirements.txt

# Development dependencies (used for local testing)
.venv/bin/python -m pip install -r requirements-dev.txt
```
### Dependency Management

Bloodhound separates Lambda runtime dependencies from local development
dependencies. This keeps the Lambda deployment package small and avoids
dependency conflicts during Terraform builds.

Dependency files:

```md

File                    Purpose
---------------------   --------------------------------------------------------
requirements.txt        Dependencies packaged into the Lambda deployment.

requirements-dev.txt    Dependencies used only for local development and
                        testing. These are not included in the Lambda package.
```

AWS Lambda already provides several AWS SDK libraries in the runtime
environment (including boto3 and botocore). Because of this, these libraries
are not bundled into the Lambda deployment package.

For a detailed explanation of the packaging strategy, see:

`docs/lambda_packaging.md`

AWS Lambda already includes several AWS SDK libraries in the runtime environment, including:

boto3

botocore

s3transfer

jmespath

Because of this, these libraries are not included in the Lambda deployment package, but they may still be installed locally through requirements-dev.txt.

This keeps the Lambda package smaller and avoids dependency conflicts during Terraform builds.

See docs/lambda_packaging.md for a deeper explanation of the packaging strategy.

### Configure `.env`

Create `.env` from `env.example` and fill it in:

```bash
cp env.example .env
```

Then edit `.env` and replace the placeholder values.

At minimum you must configure the following values:

Variable	Source
- SLACK_BOT_TOKEN	Slack App → OAuth & Permissions → Bot User OAuth Token
- SLACK_SIGNING_SECRET	Slack App → Basic Information → Signing Secret
- SLACK_SCAN_CHANNEL_ID	Slack channel ID where scan summaries will post
- SLACK_ALERT_CHANNEL_ID	Slack channel ID where alerts/teardown notices will post

Example Slack channel link:

https://workspace.slack.com/archives/C000Y0V0HNY

Channel ID:

C000Y0V0HNY

Bloodhound v2 automatically loads .env for local runs.

When deploying to AWS Lambda, these same variables must be configured in:

Lambda → Configuration → Environment Variables
If you need to create or configure the Slack app, see
`docs/SLACK_SETUP.md` for the full setup guide.
### Environment loading
Bloodhound v2 automatically loads `.env` for local runs.

### Run locally

From the repository root.

**Recommended (module execution):**

```bash
AWS_PROFILE=<your_profile> python -m tools.run_local
```

If your virtual environment is activated:

`AWS_PROFILE=geekstar python -m tools.run_local`

If you prefer using the virtual environment interpreter explicitly:

`AWS_PROFILE=<your_profile> .venv/bin/python -m tools.run_local`

Note:
The runner must be executed as a module (python -m tools.run_local).
Running python tools/run_local.py may fail with ModuleNotFoundError
because the project uses package-relative imports (from bloodhound...).

**Legacy script execution (may work in some environments):**

```bash
# Choose the AWS profile you want to test with:
AWS_PROFILE=<your_profile> .venv/bin/python tools/run_local
AWS_PROFILE=geekstar .venv/bin/python tools/run_local.py
```

AWS Credentials

Bloodhound uses boto3, which follows the standard AWS credential resolution chain.

If AWS_PROFILE is not specified, boto3 will automatically use the default profile from:

`~/.aws/credentials`

You can verify which AWS account your local run will use with:

`aws sts get-caller-identity`

Example output:
```json
{
  "UserId": "...",
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/..."
}
```

This helps confirm you are scanning the expected AWS account before running Bloodhound.
---

## Whitelisting

Resources tagged with:

- key: `bloodhound:keep`
- value: `true`

are treated as **kept (whitelisted)** and are excluded from teardown.

---

## Teardown controls (important)

By default, Bloodhound runs in **dry-run mode** and only posts
a teardown plan:

- `APPLY_CHANGES=false`

To allow Bloodhound to delete resources:

- `APPLY_CHANGES=true`

### Deletion safety limit

Bloodhound includes a protection that limits how many resources can
be deleted in a single run.

Environment variable:

TEARDOWN_MAX_DELETE_COUNT

Default value:

10

If a teardown plan contains more resources than this limit,
Bloodhound will abort execution and refuse to delete anything.

Example:

Plan: 25 resources  
Limit: 10  

Result:

Teardown aborted.

This protection prevents unexpected scanning behavior or configuration
errors from deleting large amounts of infrastructure in a single run.

### Runtime Safety Guards

Bloodhound includes several runtime safeguards:

- **simulate (no deletes)**: `TEARDOWN_SIMULATE=true`
- **only delete explicit IDs/ARNs**: set `TEARDOWN_TARGET_IDS=...`
- **delete everything not whitelisted**: `TEARDOWN_ALLOW_ALL=true`


### Infrastructure safety guard

Terraform includes an additional **deployment safety guard**.

If the environment variable contains:


APPLY_CHANGES=true


Terraform will **block the deployment** unless the engineer
explicitly confirms destructive mode.

Example error:


Deployment blocked: APPLY_CHANGES=true requires -var allow_apply_mode=true


To intentionally deploy Bloodhound with destructive mode enabled:


terraform apply -var allow_apply_mode=true


This prevents accidental infrastructure deletion caused by
misconfigured environment variables or commits.

---

## Build the Lambda deployment zip (v2)

The `.build/` directory is intentionally not committed. Terraform will build the zip automatically (see `infra/README.md`).

---

## Deploy to AWS Lambda (v2)

Deploy to a new function name so you do not touch your existing v1 Lambda:

- Function name: `BloodhoundLambdaV2`

Handler: `handlers.lambda_function.lambda_handler`

The Lambda handler delegates execution to the Bloodhound
orchestration entrypoint:

`bloodhound.app.run()`

The `run()` function prepares the runtime environment based on the
invocation source (Slack command, validation harness, or scheduled run)
and then executes the core pipeline.

Execution flow:

Lambda handler
   ↓
bloodhound.app.run()
   ↓
event routing (Slack / validation / scheduled)
   ↓
execute_pipeline()
   ↓
scan → budget → teardown → reporting


### Configure Lambda environment variables

In Lambda Console → **Configuration → Environment variables**, copy the values from your local `.env`.

At minimum:

- Slack: `SLACK_BOT_TOKEN`, `SLACK_SCAN_CHANNEL_ID`, `SLACK_ALERT_CHANNEL_ID`
- Regions: `REGION_MODE`, `REGIONS`
- Budget: `COHORT_START_YYYY_MM`, `COHORT_TOTAL_BUDGET_USD`, `COHORT_LENGTH_MONTHS`, `BUDGET_OVER_DAYS`
- Teardown: `APPLY_CHANGES`, `TEARDOWN_SIMULATE`, `TEARDOWN_ALLOW_ALL`, `TEARDOWN_TARGET_IDS`

### Test the Lambda via AWS CLI

```bash
aws lambda invoke \
  --function-name BloodhoundLambdaV2 \
  --payload file://tools/test_event.json \
  output.txt \
  --region us-west-2

cat output.txt
```

Note:

The AWS region used for CLI invocation must match the region
where Terraform deployed the Lambda function.

The default deployment region used by the Terraform configuration is:

us-west-2

If this region changes in Terraform, the CLI commands and GitHub
workflow configuration must also be updated.

---
## Terraform Deployment Workflow

Bloodhound v2 infrastructure is deployed using Terraform.

Run Terraform from the `infra/` directory.

### Step 1 — Bootstrap Existing Resources (first run only)

If the AWS account already contains Bloodhound IAM resources
(for example from a previous manual deployment), Terraform must
import them into state before the first apply.

This repository includes a helper script to automate this process.

```bash
cd infra
./bootstrap_imports.sh
```

The script will:

detect existing IAM role bloodhound-v2-role

detect existing IAM policy bloodhound-v2-policy

import them into Terraform state if they already exist

This step only needs to be performed once when introducing Terraform
into an existing AWS account.

### Step 2 — Deploy Infrastructure

```bash
cd infra
terraform init
terraform apply
```

Terraform will automatically:

Build the Lambda deployment package locally

Install runtime dependencies from requirements.txt

Create or update IAM roles and policies

Deploy the Lambda function

Create the Lambda Function URL

After deployment Terraform will output the Lambda URL used by Slack commands.

Example output:

`lambda_function_url = https://xxxxx.lambda-url.us-west-2.on.aws/`


## GitHub Actions (invoke v2)

This repo includes a separate workflow for v2:

- `.github/workflows/invoke_lambda_v2.yml`

It invokes:

- `BloodhoundLambdaV2`

---

```md
## ⚙️ GitHub Automation

Bloodhound includes **two GitHub Actions workflows**:

1. **Scheduled infrastructure scans**
2. **Manual operator workflows**

---

## Scheduled Scan Workflow

Workflow file:

`.github/workflows/invoke_lambda.yml`

This workflow runs automatically on a fixed schedule and performs the
regular Bloodhound infrastructure scan.

Schedule:
16:00 UTC → 11 AM EST
04:00 UTC → 11 PM EST
The workflow:

• authenticates to AWS using GitHub OIDC  
• invokes the `BloodhoundLambdaV2` Lambda  
• runs the full scan pipeline  
• prints the Lambda response and CloudWatch logs  

The Lambda event payload used for scheduled runs is:

```json
{ "source": "scheduled" }
```
This ensures the Lambda pipeline executes in scheduled scan mode.
 
## Manual Operations Workflow

Workflow file:
`.github/workflows/bloodhound_ops.yml`
This workflow allows engineers to manually run Bloodhound tasks from the
GitHub Actions UI.

Available operations:

```text
| Mode | Description |
|------|-------------|
| scan | Run an immediate infrastructure scan |
| status | Return system health information |
| validation | Reserved for teardown validation workflow (currently disabled in CI) |
```

Example usage:
GitHub → Actions → Bloodhound Operations → Run Workflow
The workflow will:

• authenticate to AWS using GitHub OIDC
• invoke BloodhoundLambdaV2
• print the Lambda response
• display structured scan results
• stream recent CloudWatch logs
 
## Validation Workflow Status

The validation workflow is temporarily disabled in GitHub Actions.

The validation pipeline provisions disposable Terraform infrastructure
and performs controlled teardown tests.

This workflow runs correctly in local environments but requires
additional CI hardening before being enabled in GitHub Actions.

Validation testing can still be executed locally using:
`tools/run_validation_workflow.sh`
---


---

### GitHub OIDC Authentication Bootstrap

The GitHub workflow authenticates to AWS using **OIDC role assumption**.

This avoids storing long-lived AWS credentials in GitHub secrets.

Instead, GitHub obtains **temporary AWS credentials** during workflow execution.

Authentication flow:

GitHub Actions
↓
OIDC identity token
↓
AWS STS AssumeRoleWithWebIdentity
↓
BloodhoundGitHubInvokeRole
↓
Temporary AWS credentials
↓
Invoke BloodhoundLambdaV2

### Bootstrap Script

The repository includes a helper script that configures the AWS IAM
resources required for **GitHub Actions OIDC authentication**.

Script:

`scripts/bootstrap_github_oidc.sh`

This script prepares the AWS account so GitHub Actions workflows
can securely invoke the Bloodhound Lambda using OIDC role
assumption instead of long-lived AWS access keys.

After running the script, GitHub workflows will assume the role:

BloodhoundGitHubInvokeRole

This role allows GitHub Actions to invoke:

BloodhoundLambdaV2


This script performs the following tasks:

1. Detects the GitHub OIDC identity provider
2. Creates it if missing
3. Creates the IAM role `BloodhoundGitHubInvokeRole`
4. Configures the trust policy for the repository
5. Attaches Lambda invocation permissions
6. Tags IAM resources for governance and auditing

Temporary Policy Artifacts

The bootstrap script generates temporary JSON files during execution:

trust-policy.json
lambda-policy.json

These files are required by the AWS CLI when creating IAM roles and attaching policies.

They are temporary artifacts only and are automatically removed when the script exits.

This cleanup behavior is implemented using a Bash trap:

trap "rm -f trust-policy.json lambda-policy.json" EXIT

This ensures that:

temporary policy files are never accidentally committed to the repository

local workspaces remain clean after script execution

CI environments do not accumulate artifacts

These files should not be added to Git.

If they appear locally (for example if the script is interrupted), they can safely be deleted.

---

### Run the bootstrap script

Run once when setting up CI access for a new AWS account.

chmod +x scripts/bootstrap_github_oidc.sh
./scripts/bootstrap_github_oidc.sh


The script will output the IAM role ARN used by the GitHub workflow.

Example:


arn:aws:iam::<ACCOUNT_ID>:role/BloodhoundGitHubInvokeRole


---

### Trust Policy

The IAM role restricts access to workflows originating from the
official repository:


repo:codeplatoon-devops/Bloodhound:*


This allows engineers to run workflows from **any branch** within the
repository, enabling CI testing for feature branches while still
preventing external repositories from assuming the role.

---

### Security Notes

This architecture provides several advantages:

• no AWS access keys stored in GitHub  
• temporary credentials issued per workflow run  
• access restricted to a specific repository  
• IAM role tagged for governance and auditing

---

## Slack slash commands (v2)

Slash commands require a publicly reachable HTTPS endpoint. For v2 we recommend a **Lambda Function URL** (one endpoint) and route based on the Slack `command` field.

- `/v2_seek` runs scan + reports (non-destructive)
- `/v2_seek_destroy_plan` previews the teardown plan
- `/v2_seek_destroy CONFIRM` runs destructive cleanup (deletes all non-whitelisted candidates)
- `/v2_status` shows the current Bloodhound system status

To enable slash commands you must set these env vars in Lambda:

- `SLACK_SIGNING_SECRET`
- `SLACK_ALLOWED_USER_IDS` (optional)
- `SLACK_ALLOWED_CHANNEL_IDS` (optional)
- `SLACK_DESTROY_CONFIRM_TOKEN` (default `CONFIRM`)

## Validation Scripts

Bloodhound includes automation scripts that help engineers quickly
verify the infrastructure deployment and teardown pipeline.

These scripts are located in:

tools/

### Validation Workflow

Bloodhound also provides an automated validation workflow that runs the
available validation tools in the correct order.

Run:

tools/run_validation_workflow.sh

This script orchestrates the following validation stages:

1. Lambda infrastructure smoke test
2. Controlled teardown validation

The workflow verifies that:

- the Lambda deployment is healthy
- environment variables match the expected configuration
- Slack commands are correctly routed to Lambda
- the teardown pipeline can safely delete resources

This provides a fast way to confirm that the full Bloodhound deployment
is functioning correctly after infrastructure changes.

Typical usage after deploying infrastructure:

terraform apply
tools/run_validation_workflow.sh

### Smoke Test

Script:

tools/smoke_test_lambda.sh

This script performs a quick health check of the deployed Lambda.

It verifies:

Lambda function exists

environment variables are present

CloudWatch log group exists

Lambda Function URL is configured

This script is useful immediately after running:

terraform apply

It detects most deployment problems within seconds.

### Controlled Teardown Validation

Script:

tools/validate_teardown.sh

This script automates the teardown validation procedure described in:

docs/validate_teardown.md

The script:

creates a disposable EC2 instance

captures the instance ID

prompts the engineer to run the scan command

Legacy:

/seek

Current:

/v2_seek

Then prompts the engineer to run the teardown command

Legacy:

/seek_destroy CONFIRM

Current:

/v2_seek_destroy CONFIRM

verifies that the instance was deleted

restores Bloodhound to safe mode

This test confirms the full teardown pipeline:

Execution path for destructive operations:

Operator workflow:
Slack → Lambda → AWS API → resource deletion

Validation workflow:
Validation script → Lambda → AWS API → resource deletion

Optional Log Streaming

During validation, Lambda execution logs can be streamed live using:

aws logs tail /aws/lambda/BloodhoundLambdaV2 \
--region us-west-2 \
--follow

This allows engineers to observe the execution path of:

Legacy commands:

/seek
/seek_destroy

Current commands:

/v2_seek
/v2_seek_destroy

in real time.

Environment configuration validation

The smoke test also verifies that critical Lambda environment variables
match the local `.env` configuration.

This prevents common deployment mistakes such as:

- Terraform not applied after `.env` changes
- Lambda environment variables edited manually
- CI/CD deploying outdated configuration

If a mismatch is detected, the script will stop immediately and
display the conflicting values.

5. Example Failure Output

Example when Terraform is stale:

Checking Lambda environment variables...

Comparing critical environment variables with .env...

ERROR: Environment variable mismatch

Variable: APPLY_CHANGES
Expected: false
Actual:   true

Terraform deployment may be out of sync.

If Slack commands stop responding after deployment, see:

`docs/troubleshooting_slack_commands.md`
