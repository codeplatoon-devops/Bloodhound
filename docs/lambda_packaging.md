# Lambda Dependency Management and Packaging Strategy

## Table of Contents

- [Why AWS Includes boto3 in Lambda](#why-aws-includes-boto3-in-lambda)
- [Why boto3 Should Not Be Bundled](#why-boto3-should-not-be-bundled)
- [Development Dependencies](#development-dependencies)
- [Build Environment vs Lambda Runtime](#build-environment-vs-lambda-runtime)
- [Common Packaging Failures](#common-packaging-failures)
- [Lambda Packaging Flow (Current Implementation)](#lambda-packaging-flow-current-implementation)
- [Future Packaging Flow (Docker-Based)](#future-packaging-flow-docker-based)
- [Recommended Build Best Practices](#recommended-build-best-practices)

This document explains how Bloodhound packages dependencies for AWS Lambda
and why certain libraries should not be bundled with the deployment package.

It also describes the Docker-based build system used to ensure
deterministic Lambda packaging and runtime compatibility.

Note:

Some Lambda packaging failures may originate from dependency conflicts
during the pip installation step. Dependency management rules for the
Bloodhound Lambda are documented in this guide.

Engineers encountering dependency resolution errors should review the
packaging guide before modifying `requirements.txt`.

---

## Lambda Execution Routing (Important)

Bloodhound uses explicit event routing in the Lambda entrypoint to ensure
safe execution across different invocation types.

Execution model:

`Event → Router → Handler → Pipeline`

### Routing behavior

- Slack HTTP events → handled immediately by Slack handler
- Scheduled events → routed to `scheduled_handler`
- Validation events → routed to the validation handler
- Default/manual events → routed to `run()`

### Scheduled execution (critical behavior)

Scheduled events do NOT pass through `run()`.

Instead they follow:

`scheduled_handler → run_scheduled_scan() → execute_pipeline()`

This separation prevents:

- recursive execution loops
- duplicate handler invocation
- unintended re-entry into routing logic

Engineers modifying Lambda execution must ensure scheduled events
remain isolated from the generic run() path.

---
## Bloodhound Application Architecture

The Bloodhound Lambda is organized using a layered architecture
to separate AWS event handling, orchestration logic, and AWS
resource scanning functionality.

Directory layout inside the Lambda package:

bloodhound/
    config/      runtime configuration and environment handling
    handlers/    internal request handlers
    scanner/     AWS resource discovery logic
    services/    orchestration and service layer logic
    teardown/    infrastructure cleanup planning and execution

Responsibilities:

handlers
    interpret events and route them into the service layer

services
    coordinate higher-level operations such as scanning,
    status checks, and teardown workflows

scanner
    interact with AWS APIs to discover infrastructure resources

teardown
    plan and execute resource cleanup actions

---

## Lambda Entry Point

AWS Lambda invokes the function defined in:

handlers/lambda_function.py

This file acts as the Lambda entrypoint and is responsible for receiving
AWS events and routing them into the Bloodhound execution pipeline.

Execution flow:

AWS Lambda
      │
      ▼
handlers/lambda_function.py
      │
      ▼
bloodhound.handlers.*
      │
      ▼
service layer

Separating the Lambda entrypoint from the application modules ensures
that AWS-specific logic remains isolated from the core Bloodhound
application code.

--- 

## Lambda Logging and Traceability

Bloodhound Lambda executions emit structured CloudWatch log markers:

[BLOODHOUND][EVENT_TYPE][request_id=...]

Examples:

[BLOODHOUND][SCHEDULED][request_id=...]
[BLOODHOUND][SCAN][request_id=...]
[BLOODHOUND][STATUS][request_id=...]

The request_id corresponds to the AWS Lambda invocation ID
(context.aws_request_id).

Including the request_id allows engineers to trace individual
executions across CloudWatch logs and GitHub Actions validation runs.

---

# Why AWS Includes boto3 in Lambda

AWS Lambda Python runtimes already include the AWS SDK libraries:

- boto3
- botocore
- s3transfer
- jmespath

Because these are included in the runtime environment, Lambda functions can
import them directly without bundling them in the deployment package.

Example:

```python
import boto3
ec2 = boto3.client("ec2")
```

This works even if boto3 is not included in requirements.txt.

# Why boto3 Should NOT Be Bundled

AWS recommends not packaging boto3 unless you require a specific version.

There are several reasons for this.

Version Conflicts

The Lambda runtime includes a specific version of boto3 and botocore.

Example runtime versions:

```text
boto3 1.34.x
botocore 1.34.x
```

If a deployment package includes different versions, Python may load
conflicting dependencies.

This can cause subtle runtime failures.

Larger Deployment Packages

Lambda deployment limits:

50 MB zipped
250 MB unzipped

The boto3 dependency chain is large.

Typical uncompressed size:

boto3 + botocore ≈ 70MB

Including it unnecessarily increases package size.

Dependency Resolution Problems

Packaging boto3 introduces additional dependencies.

Example chain:

```text
boto3
└── botocore
    └── urllib3 (< 1.27)
```

If a project forces a newer urllib3 version (for example urllib3==2.x)
pip will fail to resolve dependencies during packaging.

This can break Terraform deployments.

Recommended requirements.txt

Bloodhound should only package dependencies not included in Lambda.

Example:

slack-sdk==3.26.1
python-dotenv==1.0.0

Do NOT include:

boto3
botocore
urllib3
s3transfer

Lambda provides these automatically.

## Development Dependencies

Local development may require additional dependencies such as `boto3`
for testing AWS interactions.

These dependencies are defined in `requirements-dev.txt`.

Terraform packaging only uses `requirements.txt` to ensure that the
Lambda deployment package contains only the dependencies required
for runtime execution.

## Python Packaging Metadata

During dependency installation, pip may create additional metadata
directories inside the Lambda package.

Examples include:

*.dist-info
bin/

These directories are normal artifacts created by Python packaging
and contain metadata such as version information and package records.

They do not affect Lambda execution and are safe to include in the
deployment package.

## Build Environment vs Lambda Runtime

Lambda packaging happens in two separate environments.

### Build Environment (Local Machine)

Terraform builds the Lambda package locally using a `local-exec` provisioner.

Example command executed during packaging:

```bash
python3 -m pip install -r requirements.txt -t .build/lambda_pkg
```

The Python version used here is the Python version installed on the engineer's machine.

Example:

Local Python: 3.13

### Runtime Environment (AWS Lambda)

The Lambda function itself runs inside the runtime defined in Terraform:

`runtime = "python3.10"`

This means AWS executes the code in its own environment:

`AWS Lambda Runtime: Python 3.10`

These environments are independent.

Most of Bloodhound's dependencies are pure Python libraries, so builds created with 
Python 3.12 or 3.13 usually run correctly in the Python 3.10 Lambda runtime.

However, compiled libraries may fail if built using a different Python version. 
This is one of the main reasons Docker-based packaging is recommended.

## Common Packaging Failures

Lambda packaging may fail during `terraform apply` if pip cannot resolve dependency conflicts.

Example error:
`ResolutionImpossible`

A common cause is manually pinning a dependency that is managed by another library.

Example conflict:

`botocore requires urllib3 < 1.27`

If a project pins:

`urllib3==2.x`

pip cannot resolve the dependency tree and the packaging step fails.

Best practice:

Only specify top-level dependencies required by the Lambda function.

Example:

```text
slack-sdk
python-dotenv
```

Avoid pinning dependencies managed by other libraries such as:

```text
botocore
urllib3
s3transfer
```

Allow pip to resolve those automatically.

---

## Lambda Packaging Flow (Current Implementation)

Terraform only rebuilds the Lambda package when runtime code changes.

Source hashing is limited to:

bloodhound/
handlers/

Changes in other directories (docs, scripts, tests) will not trigger a
Lambda rebuild. This keeps Terraform deployments fast and avoids
unnecessary Lambda updates.

```text
terraform apply
        │
        ▼
terraform_data.build_lambda_pkg
        │
        ▼
scripts/build_lambda.sh
        │
        ▼
Select build mode
   ├─ Docker build (default)
   │     ↓
   │ Docker container
   │ public.ecr.aws/sam/build-python3.10
   │     ↓
   │ pip install dependencies
   │
   └─ Local build (--local)
         ↓
      python3 + pip
         ↓
      pip install dependencies
        │
        ▼
Copy application source
(bloodhound/, handlers/)
        │
        ▼
Construct Lambda package
.build/lambda_pkg
        │
        ▼
archive_file provider
        │
        ▼
.build/bloodhound_lambda_v2.zip
        │
        ▼
Lambda deployment
```

## Lambda Deployment Artifact

Terraform creates the Lambda deployment package by archiving:

.build/lambda_pkg

The resulting deployment artifact is:

.build/bloodhound_lambda_v2.zip

This ZIP file is the artifact uploaded to AWS Lambda.

Terraform's archive_file provider constructs this archive automatically
during `terraform apply`.

If this file is missing or empty, the Lambda build step likely failed
before the archive stage.


## Docker-Based Packaging (Optional)

Bloodhound supports building Lambda dependencies inside a Docker container
that matches the Lambda runtime build environment.

This mode is optional and can be enabled when deterministic builds are required
or when dependencies include compiled libraries.

Example:

`terraform apply -var="use_docker_build=true"`

Docker builds use the AWS Lambda runtime container:

`public.ecr.aws/sam/build-python3.10`

This container includes the correct Python runtime, pip, and build tools
required to install dependencies compatible with the AWS Lambda Python 3.10
runtime.

When Docker mode is enabled, dependency installation runs inside the
container instead of the engineer's local Python environment.

This prevents dependency inconsistencies caused by engineers using
different local Python versions.

The AWS Lambda runtime itself remains:

`public.ecr.aws/lambda/python:3.10`

However, Bloodhound packages dependencies using the SAM build container
so that dependency installation occurs in a build environment aligned
with the Lambda Python 3.10 runtime.


Example:

```text
terraform apply
        │
        ▼
Docker build container
(public.ecr.aws/sam/build-python3.10)
        │
        ▼
pip install runtime dependencies
        │
        ▼
.build/lambda_pkg
        │
        ▼
archive_file provider
        │
        ▼
bloodhound_lambda_v2.zip
        │
        ▼
Lambda deployment
```

## Recommended Build Best Practices

Bloodhound supports two Lambda packaging methods:

1) Docker-based build (recommended)
2) Local Python build (fallback)

Docker builds are the preferred method because they ensure the
build environment matches the AWS Lambda runtime.

Using Docker provides several advantages:

- deterministic builds
- consistent dependency resolution
- matching Lambda runtime environment
- reduced risk of packaging failures
- consistent builds across different developer machines

Docker builds use the AWS SAM build container:

public.ecr.aws/sam/build-python3.10

This container provides the same runtime environment used by AWS
Lambda for dependency compilation.

Example Docker-enabled build:

terraform apply -var="use_docker_build=true"

When Docker mode is disabled, Bloodhound falls back to using the
developer's local Python environment to install dependencies.

## Lambda Build Directory Structure

The Bloodhound Lambda packaging process uses a structured build directory
to support dependency caching, deterministic builds, and reliable Terraform execution.

Directory layout:

```text
.build/
  lambda_pkg/  prepared Lambda deployment package
   bloodhound_lambda_v2.zip    final Lambda deployment artifact
```

Runtime dependencies are installed directly into:

.build/lambda_pkg

The build script installs dependencies from `requirements.txt`
before copying the Bloodhound application source.

Lambda requires all modules to exist directly on the Python import path.

For this reason, dependencies are installed directly into the root
of the deployment package rather than inside a nested site-packages
directory.

Example structure:

.build/lambda_pkg/
    bloodhound/
    handlers/
    slack_sdk/
    slack/
    dotenv/

This flattened layout ensures Python can resolve imports correctly
during Lambda execution.


lambda_pkg/

This directory contains the final Lambda deployment package.

The build script installs runtime dependencies and then copies
the Bloodhound application source into this directory.

Terraform's `archive_file` provider creates the Lambda deployment
archive from this directory.

The Terraform archive_file provider creates the Lambda deployment archive
from this directory.

Why this structure exists

This layered build design prevents several common Lambda packaging failures.

Ensures deterministic Lambda packages

Each Terraform run rebuilds the deployment package from scratch,
ensuring no stale dependencies or files remain from previous builds.

This guarantees the Lambda deployment artifact always reflects
the current project state.

Prevents Terraform archive failures

Terraform's archive_file provider cannot create an archive from an empty
directory.

If the build process deletes the entire .build directory, Terraform may
attempt to archive a directory that does not yet exist.

By maintaining a stable directory structure and only refreshing specific
layers, Terraform can reliably evaluate the archive step.

Prevents inconsistent build environments

Separating dependency installation from source copying ensures the final
deployment package is constructed in a predictable order.

This improves build determinism and makes the packaging process easier
to debug.

Improves CI reliability

CI pipelines and concurrent Terraform runs are less likely to fail when
the build directory structure remains stable.

Deleting the entire .build directory can cause race conditions or
incomplete builds.

By refreshing only the necessary layers, the packaging process becomes
more robust and reproducible.

This layered build structure provides:

- faster rebuilds  
- deterministic packaging  
- safer Terraform execution  
- reduced dependency installation time

## Quick Troubleshooting

If Terraform fails during Lambda packaging or deployment, consult the
Terraform troubleshooting guide:

docs/troubleshooting_terraform_lambda.md

That document covers common deployment failures including:

- Lambda runtime import errors
- Terraform skipping the build step
- archive_file creation failures
- empty Lambda deployment packages
- `.build` directory inconsistencies

Most packaging issues can be diagnosed quickly by inspecting:

`.build/lambda_pkg`

If this directory is missing files or empty, Terraform likely skipped
the build step or the packaging script failed to run.

The troubleshooting guide provides recovery procedures such as forcing
Terraform to rebuild the package:

`terraform apply -replace=terraform_data.build_lambda_pkg`

