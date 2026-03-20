# Terraform + Lambda Troubleshooting

## Table of Contents

- [Lambda Runtime Import Errors](#issue-lambda-runtime-import-errors)
- [pip Dependency Resolution Failure During Lambda Packaging](#issue-pip-dependency-resolution-failure-during-lambda-packaging)
- [Cause](#cause)
- [Diagnosis](#diagnosis)
- [Fix](#fix)
- [Additional Verification](#additional-verification)
- [When This Problem Commonly Appears](#when-this-problem-commonly-appears)
- [Best Practice](#best-practice)
- [Terraform Archive Creation Error](#issue-terraform-archive-creation-error)
- [AWS Rejects Lambda Deployment Zip](#issue-aws-rejects-lambda-deployment-zip)
- [.build Directory Issues](#issue-build-directory-behaving-inconsistently)
- [Validation Workflow Reminder](#validation-workflow-reminder)
- [Related Documentation](#related-documentation)

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

If the `.build` directory was deleted or corrupted, Terraform may attempt to deploy an empty Lambda package.

The correct recovery procedure is to **force Terraform to rebuild the Lambda package**.

From the `infra` directory run:

terraform apply -replace=terraform_data.build_lambda_pkg

This forces the packaging step to run again regardless of trigger hashes.

During execution Terraform should run the packaging script:

rm -rf .build
mkdir -p .build/lambda_pkg
pip install -r requirements.txt -t .build/lambda_pkg
rsync application source
create lambda zip
deploy updated Lambda

Expected Terraform output:

terraform_data.build_lambda_pkg: Provisioning with 'local-exec'
Prepared package dir: .build/lambda_pkg
Downloading dependencies
Installing slack_sdk
Creating deployment archive

If the `pip install` step does not appear in the output, the packaging script did not run.

After the rebuild completes, verify the package contents:

ls ../.build/lambda_pkg

Expected output should include the application and dependencies:

bloodhound/
handlers/
slack_sdk/
boto3/
requests/

You can also inspect the deployed archive:

unzip -l ../.build/bloodhound_lambda_v2.zip | head

The archive should contain the application code and dependencies at the root.

Post-Recovery Verification

After rebuilding the Lambda package, confirm that the deployment works correctly.

Step 1 — Smoke Test the Lambda

After Terraform completes successfully, you should see the Lambda Function URL in the outputs:

bloodhound_lambda_url = "https://<lambda-id>.lambda-url.us-west-2.on.aws/"

Run a quick test request:

curl https://<lambda-id>.lambda-url.us-west-2.on.aws/

Example successful response:

{
  "regions": ["us-east-1","us-east-2","us-west-1","us-west-2"],
  "scan": {
    "candidates_total": 56,
    "kept_total": 1
  },
  "ok": true,
  "teardown": {
    "planned_actions": 56,
    "execution": null,
    "targets_filter": null,
    "apply_changes": false,
    "simulate": true
  },
  "budget": {
    "over_budget_threshold_met": true,
    "projected_month_end_spend_usd": 2753.1269,
    "dynamic_monthly_allowance_usd": 0.0
  }
}

A response like this confirms:

• Lambda successfully executed
• Application modules loaded correctly
• Dependencies were packaged correctly
• Infrastructure scan logic is functioning

If the request fails with an import error, inspect the Lambda logs in CloudWatch.

Step 2 — Run the Validation Workflow

Once the Lambda smoke test succeeds, run the full validation workflow.

./tools/run_validation_workflow.sh

This workflow verifies:

• Lambda deployment
• infrastructure scanning
• teardown planning logic
• Slack command integrations

This step ensures the entire Bloodhound pipeline functions end-to-end after deployment.

Expected Outcome

If all steps succeed:

• Terraform deployment succeeds
• Lambda responds correctly
• Validation workflow completes without errors

At this point the infrastructure deployment can be considered healthy and operational.

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

## Issue: Terraform Archive Creation Error

Example error:

Error: Archive creation error
error creating archive: archive has not been created as it would be empty

This occurs during:

terraform plan

and originates from the Terraform archive_file data source used to build the Lambda deployment package.

Cause

Terraform attempts to archive the Lambda package directory:

.build/lambda_pkg

If the directory exists but contains no files, the archive_file provider refuses to create a zip archive.

This commonly occurs when:

• .build was manually deleted
• the repository was freshly cloned
• the build step has not executed yet

Example directory state:

.build/
  lambda_pkg/

Since the directory is empty, Terraform cannot create the archive.

Diagnosis

Check the contents of the package directory.

ls -a .build/lambda_pkg

If the output is only:

.
..

then the directory is empty.

Fix

Create a placeholder file so Terraform can archive the directory.

touch .build/lambda_pkg/.placeholder

Verify:

ls -a .build/lambda_pkg

Expected output:

.
..
.placeholder

Then rerun Terraform:

cd infra
terraform plan
Issue: AWS Rejects Lambda Deployment Zip

Example error:

InvalidParameterValueException:
Uploaded file must be a non-empty zip
Cause

Terraform created a zip archive from .build/lambda_pkg, but the directory contained only a placeholder file.

This happens when the Terraform build step was not triggered.

Diagnosis

Check the package contents:

ls .build/lambda_pkg

If you see only:

.placeholder

then the Lambda package was not built.

Fix

Force Terraform to rebuild the Lambda package.

terraform apply -replace=terraform_data.build_lambda_pkg

This reruns the packaging step:

pip install dependencies
rsync application source
build lambda package
create zip
deploy Lambda

After completion, verify:

ls .build/lambda_pkg

Expected contents:

bloodhound/
handlers/
requests/
boto3/
...

# Issue: pip Dependency Resolution Failure During Lambda Packaging

Example error during `terraform apply`:

```text
ERROR: Cannot install -r requirements.txt because these package versions have conflicting dependencies.
The conflict is caused by:
botocore 1.34.x depends on urllib3<1.27
The user requested urllib3==2.0.7

ERROR: ResolutionImpossible
```


This error occurs during the Lambda packaging step when Terraform runs:


pip install -r requirements.txt -t .build/lambda_pkg


The pip dependency resolver is unable to construct a valid dependency tree.

---

# Cause

A **transitive dependency** was manually pinned in `requirements.txt`.

Example problematic configuration:


boto3==1.34.x
botocore==1.34.x
urllib3==2.0.7


The AWS SDK dependency chain looks like this:


boto3
└── botocore
└── urllib3 (<1.27)


Because `urllib3` was forced to version `2.x`, pip could not satisfy
botocore's requirement.

This caused the dependency resolver to fail before the Lambda package
could be built.

---

# Diagnosis

If Terraform fails during the packaging step, inspect the output for pip
dependency resolution errors.

Typical indicators include:


ResolutionImpossible


or


conflicting dependencies


To reproduce locally, run:


pip install -r requirements.txt


If pip fails locally, Terraform will also fail during Lambda packaging.

---

# Fix

Remove the manually pinned transitive dependency.

Example corrected configuration:


slack-sdk==3.26.1
python-dotenv==1.0.0


Do **not manually pin** dependencies managed by other libraries.

Allow pip to resolve the dependency tree automatically.

---

# Best Practice

Only specify **top-level dependencies** required by the Lambda function.

Avoid pinning dependencies managed internally by other libraries.

Examples that should generally **not be pinned**:


botocore
urllib3
s3transfer
jmespath


These dependencies are automatically managed by the AWS SDK.

Additionally, AWS Lambda already provides the following libraries in the runtime:


boto3
botocore


Because of this, they usually **do not need to be included in `requirements.txt`.**

Refer to:


docs/lambda_packaging.md


for the dependency strategy used by the Bloodhound Lambda deployment.

---

# When This Problem Commonly Appears

This issue most often occurs when:

• adding new dependencies to `requirements.txt`  
• copying dependency lists from other projects  
• manually upgrading libraries without reviewing transitive dependencies  
• pinning versions to resolve security scanner warnings

Always verify dependency compatibility before committing changes to
`requirements.txt`.

---

## Issue: .build Directory Behaving Inconsistently

Rarely, the .build directory may appear to ignore newly created files.

Example symptom:

mkdir .build/lambda_pkg
ls -R .build

but the directory does not appear.

Cause

This can happen if the directory was deleted while the shell still had an open reference to it:

rm -rf .build
mkdir .build

The shell may still point to the old directory inode.

Fix

Open a fresh terminal session and recreate the directory.

rm -rf .build
mkdir -p .build/lambda_pkg
touch .build/lambda_pkg/.placeholder

Verify:

ls -R .build

Expected:

.build/
lambda_pkg/

.build/lambda_pkg/
.placeholder
Important Note

Terraform references this directory from the infra folder:

../.build/lambda_pkg

The correct path must therefore be:

Bloodhound/.build/lambda_pkg

### Best Practice

If the repository is freshly cloned and Terraform fails during plan
due to a missing build directory, initialize the structure with:

mkdir -p .build/lambda_pkg
touch .build/lambda_pkg/.placeholder

This ensures the archive_file provider can evaluate during terraform plan.

During terraform apply, the packaging script will populate the
directory with the correct contents.

The placeholder file is only required to allow Terraform to evaluate the
archive step during planning. It is replaced during the build process
when the packaging script constructs the final Lambda package.
Additional Improvement (Recommended)

To ensure Terraform automatically rebuilds the Lambda package when source code changes, add a source hash trigger to the build resource.

Example:

triggers_replace = {
  source_hash = sha256(join("", fileset("${path.module}/..", "**/*.py")))
}

This ensures the packaging step runs whenever Python source files change.

Key Takeaway

Most Lambda packaging failures fall into one of three categories:

Missing modules in the deployment package

Terraform skipping the build step

Terraform attempting to archive an empty directory

Verifying .build/lambda_pkg contents will quickly identify which condition occurred.

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

