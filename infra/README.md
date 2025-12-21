## Bloodhound v2 Infrastructure (Terraform)

This directory provisions the AWS infrastructure for running Bloodhound v2 with Slack slash commands.

We use a **Lambda Function URL** (single endpoint) for `/seek` and `/seek_destroy`.

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

### Notes

- Terraform runs `python3 -m pip install ...` locally to build the zip, so you need `python3`, `pip`, `zip`, and `rsync` installed.
- Putting secrets in `var.lambda_env` stores them in Terraform state. Prefer setting secrets in the Lambda console (or a secrets manager).
