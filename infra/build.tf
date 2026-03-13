/*
infra/build.tf

Build pipeline for the Lambda zip (Terraform-managed).

How it works:
1) terraform_data.build_lambda_pkg prepares ../.build/lambda_pkg by:
   - pip installing dependencies into the package directory
   - copying our source code into the package directory
2) archive_file.lambda_zip zips that directory into ../.build/bloodhound_lambda_v2.zip

Notes:

• This build runs locally on the machine executing `terraform apply`.

• Required local tools:
  - python3
  - pip
  - rsync

• Dependency installation uses:

  python3 -m pip install --upgrade --no-cache-dir -r requirements.txt -t .build/lambda_pkg

  Flags explained:

  --upgrade
      Ensures the newest compatible versions of dependencies are installed.

  --no-cache-dir
      Prevents pip cache reuse which can cause corrupted or inconsistent
      dependency resolution across machines.

  -t .build/lambda_pkg
      Installs dependencies directly into the Lambda package directory.

• Only runtime dependencies listed in `requirements.txt` are packaged.

  Development-only dependencies live in `requirements-dev.txt`
  and are used only for local development/testing.
*/

resource "terraform_data" "build_lambda_pkg" {

  triggers_replace = {

  # -------------------------------------------------------------------
  # Rebuild Lambda when dependencies change
  # -------------------------------------------------------------------
  requirements_hash = filesha256("${path.module}/../requirements.txt")

  # -------------------------------------------------------------------
  # Rebuild if main handler changes
  # -------------------------------------------------------------------
  lambda_handler_hash = filesha256("${path.module}/../handlers/lambda_function.py")

  # -------------------------------------------------------------------
  # SAFETY TRIGGER
  #
  # Engineer note:
  # Terraform sometimes fails to rebuild the Lambda package when new
  # modules or directories are introduced.
  #
  # This trigger computes a combined hash across ALL Python files
  # in the repository (excluding build artifacts).
  #
  # If ANY .py file changes, Terraform automatically rebuilds
  # the Lambda package.
  #
  # This prevents stale deployments and eliminates the need for:
  #
  # terraform apply -replace=terraform_data.build_lambda_pkg
  #
  # -------------------------------------------------------------------
  python_sources_hash = sha256(join("", [
    for f in fileset("${path.module}/../", "**/*.py") :
    filesha256("${path.module}/../${f}")
  ]))
}

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = <<EOT
set -euo pipefail

# --------------------------------------------------------------------
# Clean previous build artifacts
# --------------------------------------------------------------------
rm -rf .build
mkdir -p .build/lambda_pkg

# --------------------------------------------------------------------
# Install runtime dependencies
# --------------------------------------------------------------------
python3 -m pip install --upgrade --no-cache-dir -r requirements.txt -t .build/lambda_pkg

# --------------------------------------------------------------------
# Copy application source code
# --------------------------------------------------------------------
# Engineer note:
# rsync preserves directory structure and ensures new modules
# such as bloodhound/aws.py or scanner/ are included automatically.
rsync -a --exclude "__pycache__" --exclude "*.pyc" bloodhound/ .build/lambda_pkg/bloodhound/
rsync -a --exclude "__pycache__" --exclude "*.pyc" handlers/ .build/lambda_pkg/handlers/

# --------------------------------------------------------------------
# Debug visibility (useful for troubleshooting Lambda import errors)
# --------------------------------------------------------------------
echo "Prepared package dir: .build/lambda_pkg"
echo "Lambda package contents:"
ls -R .build/lambda_pkg
EOT
    interpreter = ["/bin/bash", "-lc"]
  }
}

# Zip is created by the archive provider (no manual zip commands).
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = local.pkg_dir
  output_path = local.zip_path

  depends_on = [terraform_data.build_lambda_pkg]
}


