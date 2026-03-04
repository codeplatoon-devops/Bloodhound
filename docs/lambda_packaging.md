# Lambda Dependency Management and Packaging Strategy

This document explains how Bloodhound packages dependencies for AWS Lambda
and why certain libraries should not be bundled with the deployment package.

It also describes future improvements such as Docker-based builds.

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

## Lambda Packaging Flow (Current Implementation)
terraform apply
        │
        ▼
local-exec provisioner (build.tf)
        │
        ▼
pip install runtime dependencies
(requirements.txt)
        │
        ▼
copy project source
(bloodhound/, handlers/)
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

## Future Packaging Flow (Docker-based)
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