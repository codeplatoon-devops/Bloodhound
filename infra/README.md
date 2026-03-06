## Bloodhound v2 Infrastructure (Terraform)

This directory provisions the AWS infrastructure for running Bloodhound v2 with Slack slash commands.

We use a **Lambda Function URL** (single endpoint) for `/seek` and `/seek_destroy`.

## First-Time Terraform Setup

If the AWS account already contains Bloodhound resources
(for example IAM roles or policies created manually or by
earlier deployments), Terraform must import them before the
first `terraform apply`.

Terraform cannot automatically adopt existing AWS resources.

To simplify this process, this repository includes a helper script:

```bash
cd infra
./bootstrap_imports.sh
```

The script will:

detect existing IAM role bloodhound-v2-role

detect existing IAM policy bloodhound-v2-policy

import them into Terraform state if necessary

After running the bootstrap script, proceed with deployment:

terraform init
terraform apply

This step is typically required only once when Terraform is
introduced into an AWS account that already contains Bloodhound
infrastructure.

### What Terraform creates

- Lambda function: `BloodhoundLambdaV2`
- Lambda Function URL (public, `authorization_type = NONE`)
- IAM role + policies for:
  - CloudWatch logs
  - scanning resources (EC2/RDS/ELBv2)
  - cost explorer (CE)
  - teardown actions (terminate/delete)
  - async self-invocation (so slash commands can return immediately)

### Deploy flow

1. Apply Terraform (from `Bloodhound/infra/`):

```bash
terraform init
terraform apply
```

Terraform will automatically prepare `../.build/lambda_pkg/` (dependencies + source) and build `../.build/bloodhound_lambda_v2.zip` as part of `terraform apply` (via `terraform_data` + the `archive_file` data source).

2. Configure Slack slash commands

In your Slack App settings, set the Request URL for `/seek` and `/seek_destroy` to the Terraform output:

- `lambda_function_url`

## Python Version Requirement for Lambda Packaging

The Lambda runtime for Bloodhound v2 is currently:

`python3.10`

During deployment, Terraform builds the Lambda package locally using pip before uploading it to AWS.

This step is executed by Terraform using:

`python3 -m pip install -r requirements.txt -t .build/lambda_pkg`

Because Python dependency resolution can vary across versions, the local Python version used during packaging should match the Lambda runtime version.

If your system default python3 is a newer version (for example Python 3.12 or Python 3.13), the packaging step may fail with dependency resolution errors during:

`terraform apply`

Example error:

`ERROR: Cannot install ... because these package versions have conflicting dependencies`

To avoid this issue, ensure that the Lambda package is built using Python 3.10.

Example:

`python3.10 -m pip install -r requirements.txt -t .build/lambda_pkg`

Your local development environment can still use newer Python versions (3.11+), but the Lambda packaging step should use the same version as the configured Lambda runtime.

Note: 
The Lambda runtime version is defined in lambda.tf. If the runtime is upgraded (for example to python3.11 or python3.12), the packaging Python version used in build.tf should be updated to match.

See `docs/lambda_packaging.md` for details about dependency management
and Docker-based packaging for Lambda.

### AWS Region Alignment

All components of the Bloodhound deployment must use the **same AWS region**.

Terraform deploys the Lambda function to the region defined in the Terraform provider configuration.

Example:

provider "aws" {
  region = "us-east-1"
}

Any external systems invoking the Lambda must use the **same region**, including:

- GitHub Actions workflows
- AWS CLI commands
- Manual testing scripts

For example, the GitHub workflow must use:

aws-region: us-east-1

and:

--region us-east-1

If the regions do not match, the workflow will fail because AWS will not find the Lambda function.

### Notes

- Terraform runs `python3 -m pip install ...` locally to build the zip, so you need `python3`, `pip`, `zip`, and `rsync` installed.
- Putting secrets in `var.lambda_env` stores them in Terraform state. Prefer setting secrets in the Lambda console (or a secrets manager).

## Environment Variables and Secrets

Bloodhound uses different configuration sources for **local development** and **AWS runtime**.

### Local Development

When running locally, configuration is loaded from the `.env` file:

.env

Example usage:

```bash
python -m tools.run_local
```

The .env file is only used for local development and should never be committed to Git.

AWS Runtime Configuration

When deployed to AWS Lambda, Bloodhound does not use .env.

Instead, configuration is provided through Lambda environment variables.

After Terraform creates the Lambda function, configure secrets in the AWS console:

AWS Console
→ Lambda
→ BloodhoundLambdaV2
→ Configuration
→ Environment Variables

Add the following values:

SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
SLACK_SCAN_CHANNEL_ID
SLACK_ALERT_CHANNEL_ID

The application reads these values at runtime using:

`os.getenv("VARIABLE_NAME")`

This works both locally (.env) and in AWS (Lambda environment variables).

Terraform-Managed Variables

Terraform may manage non-secret configuration variables, such as:

REGION_MODE
REGIONS
APPLY_CHANGES
TEARDOWN_SIMULATE
TEARDOWN_ALLOW_ALL
COHORT_START_YYYY_MM
COHORT_TOTAL_BUDGET_USD
lambda_alias_version_override

lambda_alias_version_override allows temporarily pinning the production alias to a specific Lambda version for rollback.

These values can safely live in:

terraform.tfvars

Terraform will inject them into the Lambda environment during deployment.

Secrets Policy

Secrets must not be stored in Terraform variables because they would be written into the Terraform state file.

This includes:

SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
SLACK_SCAN_CHANNEL_ID
SLACK_ALERT_CHANNEL_ID

Instead, secrets should be configured directly in the Lambda environment variables after deployment.

This prevents secrets from appearing in:

Git repositories

Terraform configuration files

Terraform state

## Lambda Versioning and Alias

Bloodhound uses **Lambda version publishing with a production alias** to enable safer deployments and easy rollback.

Each time Terraform deploys the Lambda function, AWS publishes a **new immutable version** of the function.

Example structure in AWS:


BloodhoundLambdaV2
├─ $LATEST
├─ Version 1
├─ Version 2
└─ Version 3
↑
alias: prod


Terraform automatically moves the `prod` alias to the newest published version during each deploy.

### Deployment Behavior

The deployment process works as follows:


terraform plan
↓
preview infrastructure changes

terraform apply
↓
publish new Lambda version
↓
update prod alias → newest version


The `publish = true` setting in `lambda.tf` ensures that every code change results in a new version being created.

The alias defined in `alias.tf` ensures that the production entry point always points to the most recently deployed version.

### Why This Is Used

Using Lambda versioning provides several operational benefits:

- **Immutable deployments** – each version represents a fixed snapshot of the code
- **Safe rollbacks** – the alias can be repointed to a previous version if a deployment fails
- **Deployment history** – all previous Lambda versions remain available for debugging

### Rollback Example

If a deployment introduces an issue, the production alias can be moved back to a previous version.

Example:

prod → Version 2

This immediately restores the previous working deployment without needing to redeploy code.

### Slack Integration

Slack continues to call the same **Lambda Function URL**.

Internally AWS routes the request to the alias:

Slack
↓
Lambda Function URL
↓
BloodhoundLambdaV2:prod
↓
Active Lambda version

Because of this, deployments and rollbacks do **not require changing the Slack configuration**.

### Viewing Lambda Versions

Lambda versions can be viewed in the AWS console.

Navigate to:

AWS Console  
→ Lambda  
→ BloodhoundLambdaV2  
→ Versions

You will see a list similar to:

$LATEST
Version 1
Version 2
Version 3

The production alias will indicate which version is currently active:

prod → Version 3

---

### Performing a Rollback

If a deployment introduces an issue, the production alias can be moved back to a previous version.

Navigate to:

AWS Console  
→ Lambda  
→ BloodhoundLambdaV2  
→ Aliases  
→ prod  
→ Edit

Then change the alias target to the previous version.

Example:

prod → Version 2

This immediately restores the previous working deployment without redeploying code.

---

### Important: Terraform Deploy Behavior

Terraform automatically moves the `prod` alias to the **latest published version** during each deployment.

Example deploy:

terraform apply
↓
publish Version 4
↓
prod → Version 4


Because of this behavior, a manual rollback performed in the AWS console is **temporary**.

Running `terraform apply` again will move the alias back to the newest deployed version.

If a rollback must remain active, the underlying issue should be fixed before the next Terraform deployment
------
### Permanent Rollback Using Terraform

Because Terraform manages the Lambda alias, a rollback performed in the AWS console is temporary.

To make a rollback permanent, Terraform provides a **version override variable** that allows the production alias to be pinned to a specific version.

This avoids editing infrastructure code during incidents.

---

### Step 1: Identify the Working Version

Find the version to roll back to in the AWS console:

AWS Console  
→ Lambda  
→ BloodhoundLambdaV2  
→ Versions

Example:

$LATEST  
Version 1  
Version 2  
Version 3

---

### Step 2: Apply Rollback Using Terraform

Use the override variable when running Terraform:

Syntax:
```bash
terraform apply -var="lambda_alias_version_override=<version_numb>"
```

Example:
```bash
terraform apply -var="lambda_alias_version_override=2"
```

Result:

prod → Version 2

The production alias will now permanently point to that version.

Step 3: Restore Normal Deploy Behavior

Once the issue is resolved, remove the override:

```bash
terraform apply -var="lambda_alias_version_override=null"
```

After this, Terraform deployments will again move the prod alias to the newest published version automatically.