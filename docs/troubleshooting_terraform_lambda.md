# Terraform + Lambda Troubleshooting

This guide documents common issues encountered when deploying or validating the **Bloodhound Lambda infrastructure using Terraform**.

These problems typically occur during packaging, deployment, or validation workflows.

---

# Issue: Lambda Runtime Import Errors

Example error:

```
Runtime.ImportModuleError:
No module named 'bloodhound.aws'
```

or

```
Unable to import module 'handlers.lambda_function'
```

These errors occur when the Lambda runtime cannot locate Python modules inside the deployment package.

---

# Cause

The Lambda package (`.build/bloodhound_lambda_v2.zip`) did not include the full Bloodhound source tree.

Bloodhound uses Terraform to construct the Lambda package using:

```
infra/build.tf
```

This process performs the following steps:

```
rm -rf .build
mkdir -p .build/lambda_pkg
pip install dependencies
rsync application source
archive zip
deploy Lambda
```

If the packaging step fails or does not run, the Lambda runtime may deploy with **missing modules**.

---

# Diagnosis

Inspect the built package directory.

Run:

```
ls .build/lambda_pkg/bloodhound
```

Expected output:

```
app.py
aws.py
budget.py
config.py
messages.py
slack.py
handlers/
scanner/
teardown/
```

If files such as `aws.py`, `scanner/`, or `teardown/` are missing, the packaging step did not execute correctly.

---

# Root Cause: Terraform Build Step Was Not Triggered

Bloodhound uses this resource to build the Lambda package:

```
terraform_data.build_lambda_pkg
```

Terraform will **only rerun this step when its triggers change**.

If no triggers change, Terraform assumes the package is already up to date and **skips rebuilding the package**.

This can lead to situations where:

• the source code changed
• the package directory still contains an older build
• the deployed Lambda contains incomplete modules

You may see Terraform output like:

```
Plan: 0 to add, 0 to change, 1 to destroy
```

This indicates the packaging step did not run.

---

# Fix

Force Terraform to rebuild the Lambda package.

Run:

```
terraform apply -replace=terraform_data.build_lambda_pkg
```

Terraform will then execute the build script again:

```
rm -rf .build
pip install dependencies
rsync bloodhound source
create lambda zip
deploy updated Lambda
```

You should see output similar to:

```
terraform_data.build_lambda_pkg: Provisioning with 'local-exec'
Prepared package dir: .build/lambda_pkg
```

After the rebuild, verify the package:

```
ls .build/lambda_pkg/bloodhound
```

The full module tree should now be present.

---

# Additional Verification

You can inspect the Terraform build state using:

```
terraform state show terraform_data.build_lambda_pkg
```

Example:

```
resource "terraform_data" "build_lambda_pkg" {
  triggers_replace = {
    handlers_tree_hash
    lambda_handler_hash
    requirements_hash
    source_tree_hash
  }
}
```

These hashes determine when Terraform rebuilds the Lambda package.

---

# When This Problem Commonly Appears

This issue most frequently occurs after:

• adding new modules to the `bloodhound` package
• modifying handler imports
• switching branches in Git
• manual modifications to `.build/`
• Terraform caching the previous package build

---

# Best Practice

After modifying the application source tree, run:

```
terraform apply -replace=terraform_data.build_lambda_pkg
```

This ensures the Lambda package is rebuilt with the latest source.

---

# Validation Workflow Reminder

After rebuilding the package, rerun the validation workflow:

```
./tools/run_validation_workflow.sh
```

This will verify:

• Lambda deployment
• infrastructure scan
• controlled teardown logic

---

# Related Documentation

Infrastructure validation process:

```
docs/run_validation.md
```

Teardown validation workflow:

```
docs/validate_teardown.md
```

Slack command troubleshooting:

```
docs/troubleshooting_slack_commands.md
```

