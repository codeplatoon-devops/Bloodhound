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
  # Rebuild when requirements or source changes.
  triggers_replace = {
    requirements_hash   = filesha256("${path.module}/../requirements.txt")
    lambda_handler_hash = filesha256("${path.module}/../handlers/lambda_function.py")
    # Small codebase: hash all python files for rebuild trigger.
    source_tree_hash = sha256(join("", [
      for f in fileset("${path.module}/../bloodhound", "**/*.py") :
      filesha256("${path.module}/../bloodhound/${f}")
    ]))
    handlers_tree_hash = sha256(join("", [
      for f in fileset("${path.module}/../handlers", "**/*.py") :
      filesha256("${path.module}/../handlers/${f}")
    ]))
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = <<EOT
set -euo pipefail
rm -rf .build
mkdir -p .build/lambda_pkg
python3 -m pip install --upgrade --no-cache-dir -r requirements.txt -t .build/lambda_pkg
rsync -a bloodhound/ .build/lambda_pkg/bloodhound/
rsync -a handlers/ .build/lambda_pkg/handlers/
echo "Prepared package dir: .build/lambda_pkg"
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


