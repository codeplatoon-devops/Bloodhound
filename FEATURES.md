# Bloodhound V2 — Features

This document summarizes the major capabilities of the Bloodhound
cloud cost monitoring and automated cleanup system.

---

## Core Capabilities

Bloodhound scans AWS infrastructure to identify unused resources
and optionally remove them to control cloud costs.

Key capabilities include:

- multi-region AWS resource scanning
- cost monitoring using AWS Cost Explorer
- Slack-based reporting and operations
- automated teardown planning
- controlled resource deletion
- infrastructure validation workflows

---

## Resource Scanning

Bloodhound scans the following AWS resources:

- EC2 instances
- EBS volumes
- Elastic IPs
- NAT Gateways
- RDS instances
- ELBv2 load balancers

The scanner automatically evaluates multiple AWS regions.

---

## Cost Monitoring

Bloodhound integrates with AWS Cost Explorer to calculate:

- cohort-to-date spend
- projected monthly cost
- dynamic monthly allowance

Budget alerts can be sent to Slack when spending exceeds thresholds.

---

## Teardown Planning

Bloodhound generates a **teardown plan** showing resources that
could be deleted to reduce cost.

This plan is always generated before any destructive actions occur.

---

## Controlled Resource Deletion

Deletion is optional and disabled by default.

Multiple safety controls protect against accidental deletion:

- dry-run mode
- simulation mode
- explicit confirmation tokens
- optional allowlists
- resource tagging protection

---

## Slack Integration

Bloodhound supports the following Slack commands:

/v2_seek  
/v2_seek_destroy_plan  
/v2_seek_destroy CONFIRM  
/v2_status  

Slack provides operational visibility and safe control of teardown actions.

---

## GitHub Automation

Bloodhound includes GitHub Actions workflows that automate
infrastructure scanning and operational control.

Two workflows are included in the repository:

### Scheduled Scan Workflow

File:

.github/workflows/invoke_lambda.yml

This workflow runs automatically on a fixed schedule and performs
regular AWS infrastructure scans.

Schedule:

16:00 UTC → 11 AM EST  
04:00 UTC → 11 PM EST

Authentication and execution flow:

```text
GitHub Actions
      ↓
OIDC Authentication
      ↓
AWS STS AssumeRoleWithWebIdentity
      ↓
BloodhoundGitHubInvokeRole
      ↓
BloodhoundLambdaV2
      ↓
AWS Infrastructure Scan + Cleanup
```

The workflow:

- authenticates to AWS using GitHub OIDC
- assumes the `BloodhoundGitHubInvokeRole`
- invokes the `BloodhoundLambdaV2` function
- prints scan summaries and recent CloudWatch logs

The Lambda event payload used for scheduled scans is:

```json
{ "source": "scheduled" }
```

### Manual Operations Workflow

File:

`.github/workflows/bloodhound_ops.yml`

This workflow allows engineers to manually run Bloodhound
operations from the GitHub Actions UI.

Supported modes:
- scan — run an immediate infrastructure scan
- status — return system health information
- validation — implemented in the workflow but currently disabled in the GitHub Actions UI

Validation mode is currently disabled in CI but remains available
for local testing.


## Automated Validation Workflow

Bloodhound includes automated validation workflows that verify:

- Lambda deployment
- infrastructure scanning
- teardown logic
- controlled deletion behavior

Validation uses disposable test resources to ensure safe testing.

Validation can be executed locally using:

tools/run_validation_workflow.sh

This script orchestrates infrastructure smoke tests and controlled
teardown validation using disposable AWS resources.

---

## Safety Architecture

Bloodhound implements layered safety protections:

- destructive actions disabled by default
- explicit confirmation required
- resource whitelist tagging
- Terraform deployment guards
- Lambda version rollback capability

These safeguards ensure the system cannot accidentally delete
production resources.

---

## Deployment Architecture

Bloodhound runs as an AWS Lambda function deployed using Terraform.

Key components:

- AWS Lambda
- CloudWatch Logs
- Slack integration
- Terraform infrastructure management
- GitHub Actions automation
- GitHub OIDC authentication for AWS access
- validation automation scripts