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

It also describes future improvements such as Docker-based builds.

Note:

Some Lambda packaging failures may originate from dependency conflicts
during the pip installation step. Dependency management rules for the
Bloodhound Lambda environment are documented in:

`docs/lambda_packaging.md`

Engineers encountering dependency resolution errors should review the
packaging guide before modifying `requirements.txt`.

---

## Lambda Execution Routing (Important)

Bloodhound uses explicit event routing in the Lambda entrypoint to ensure
safe execution across different invocation types.

Execution model:

Event → Router → Handler → Pipeline

### Routing behavior

- Slack HTTP events → handled immediately by Slack handler
- Scheduled events → routed to `scheduled_handler`
- Default/manual events → routed to `run()`

### Scheduled execution (critical behavior)

Scheduled events do NOT pass through `run()`.

Instead they follow:

scheduled_handler → run_scheduled_scan() → execute_pipeline()

This separation prevents:

- recursive execution loops
- duplicate handler invocation
- unintended re-entry into routing logic

Engineers modifying Lambda execution must ensure scheduled events
remain isolated from the generic run() path.

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
```

ec2 = boto3.client("ec2")

This works even if boto3 is not included in requirements.txt.

Why boto3 Should NOT Be Bundled

AWS recommends not packaging boto3 unless you require a specific version.

There are several reasons for this.

Version Conflicts

The Lambda runtime includes a specific version of boto3 and botocore.

Example runtime versions:

boto3 1.34.x
botocore 1.34.x

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

boto3
└── botocore
    └── urllib3 (< 1.27)

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

## Build Environment vs Lambda Runtime

Lambda packaging happens in two separate environments.

### Build Environment (Local Machine)

Terraform builds the Lambda package locally using a `local-exec` provisioner.

Example command executed during packaging:
python3 -m pip install -r requirements.txt -t .build/lambda_pkg


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

```
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
Prepare build directories
.build/deps
.build/src
.build/lambda_pkg
        │
        ▼
Install runtime dependencies
(requirements.txt)
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

## Docker-Based Packaging (Optional)

Bloodhound supports building Lambda dependencies inside a Docker container
that matches the Lambda runtime environment.

This mode is optional and can be enabled when deterministic builds are required
or when dependencies include compiled libraries.

Example:

`terraform apply -var="use_docker_build=true"`

Docker builds use the AWS Lambda runtime container:

`public.ecr.aws/lambda/python:3.10`

When Docker mode is enabled, dependency installation runs inside the
container instead of the engineer's local Python environment.

This prevents dependency inconsistencies caused by engineers using different local Python versions.

Example Lambda runtime container:

`public.ecr.aws/lambda/python:3.10`


```text
terraform apply
        │
        ▼
Docker build container
(public.ecr.aws/lambda/python:3.10)
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

Bloodhound currently builds Lambda packages using the developer's local Python environment.

This works because the project dependencies are pure Python.

However, the recommended long-term approach is to package Lambda dependencies inside a Docker container that matches the Lambda runtime.

Benefits:

- deterministic builds
- consistent dependency resolution
- matching runtime environment
- reduced risk of packaging failures

## Lambda Build Directory Structure

The Bloodhound Lambda packaging process uses a structured build directory
to support dependency caching, deterministic builds, and reliable Terraform execution.

Directory layout:

.build/
  deps/        cached Python dependencies
  src/         copied application source
  lambda_pkg/  final Lambda deployment package

deps/

Contains runtime dependencies installed from requirements.txt.

Dependencies are installed into this directory using pip. Because dependency
installation is typically the slowest part of the Lambda packaging process,
this directory is cached between builds.

Dependencies are only reinstalled when requirements.txt changes.

This significantly reduces build time when engineers repeatedly run:

terraform apply

src/

Contains the application source copied from:

bloodhound/
handlers/

Separating the source layer from the dependency layer ensures that source
code changes do not require reinstalling dependencies.

When application code changes, only this directory is refreshed.

lambda_pkg/

This directory contains the final Lambda deployment package assembled from
both dependencies and application source.

The Terraform archive_file provider creates the Lambda deployment archive
from this directory.

Why this structure exists

This layered build design prevents several common Lambda packaging failures.

Prevents repeated dependency installs

Without dependency caching, every Terraform run would reinstall Python
dependencies. This can add 30–60 seconds to each build.

Caching dependencies allows Terraform to rebuild Lambda packages quickly
when only source code changes.

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

• faster rebuilds  
• deterministic packaging  
• safer Terraform execution  
• reduced dependency installation time

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

