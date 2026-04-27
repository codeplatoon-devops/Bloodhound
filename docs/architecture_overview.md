# Bloodhound Architecture Overview

Bloodhound is a serverless automation system designed to detect and safely
remove unused AWS infrastructure.

The system is implemented as an AWS Lambda service with multiple execution
entry points.

---

## System Entry Points

Bloodhound can be triggered from several sources:

```text
| Source | Purpose |
|------|------|
Slack Commands | Interactive operations
GitHub Actions | CI/CD automation
Scheduled Events | Automatic scans
Validation Workflows | Safe teardown testing
```

All entry points eventually invoke the same internal pipeline.

---

## High-Level Execution Flow

```text
Slack / GitHub Actions / Scheduled Event
                │
                ▼
      AWS Lambda Function URL
                │
                ▼
           Event Router
      (handlers.lambda_function)
                │
                ▼
     Bloodhound Execution Pipeline
           (bloodhound.app)
                │
                ▼
  ┌─────────────────────────────────────┐
  │            Pipeline Stages          │
  │                                     │
  │ 1. Resource Scan                    │
  │    scanner/                         │
  │                                     │
  │ 2. Budget Evaluation                │
  │    budget_service                   │
  │                                     │
  │ 3. Teardown Planning                │
  │    teardown/planner                 │
  │                                     │
  │ 4. Execution (optional)             │
  │    teardown/executor                │
  │                                     │
  └─────────────────────────────────────┘
                │
                ▼
        Slack / Logs / Reports
```

## Safety Architecture

Bloodhound is designed to operate safely by default.

Destructive actions require multiple conditions:

APPLY_CHANGES=true
TEARDOWN_SIMULATE=false
CONFIRM token in Slack command

These guardrails ensure that infrastructure deletion cannot occur accidentally.

## Resource Scanning

The scanner layer currently supports:

EC2
ELBv2
RDS

## Future scanners may include:

EBS snapshots
unused AMIs
orphaned ENIs
S3 buckets
Deployment Model

Bloodhound is deployed as an AWS Lambda function using Terraform.

Deployment pipeline:

```text
scripts/build_lambda.sh
        │
        ▼
.build/lambda_pkg
        │
        ▼
archive_file
        │
        ▼
.build/bloodhound_lambda_v2.zip
        │
        ▼
AWS Lambda Deployment
```

## Key Design Principles

Bloodhound was designed around several core principles:

Safety-first infrastructure automation
Serverless operation
Slack-driven operations
Deterministic Lambda builds
Auditable infrastructure changes