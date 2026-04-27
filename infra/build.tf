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
    # Terraform cannot detect changes to application code when the
    # Lambda package is built locally via `local-exec`.
    #
    # We compute a fingerprint (hash) of all Python runtime files so that any change
    # to the Lambda source forces this resource to rebuild the package.
    #
    # Only runtime directories are included to avoid rebuilds caused by
    # unrelated files (.build, .venv, scripts, tests, etc).
    # -------------------------------------------------------------------
    python_sources_hash = sha256(join("", concat(

      # Hash all Python files inside the main application package
      [
        for f in fileset("${path.module}/../bloodhound", "**/*.py") :
        filesha256("${path.module}/../bloodhound/${f}")
      ],

      # Hash Lambda handler entrypoints
      [
        for f in fileset("${path.module}/../handlers", "**/*.py") :
        filesha256("${path.module}/../handlers/${f}")
      ]

    )))
  }
  # Build the Lambda package locally using a shell script
  provisioner "local-exec" {

    # --------------------------------------------------------------------
    # Build Lambda package via external build script
    #
    # The packaging logic has been moved to scripts/build_lambda.sh
    # so that:
    #
    #   • Terraform focuses only on infrastructure orchestration
    #   • build logic becomes easier to maintain
    #   • Docker-based builds can be supported
    #
    # The script prepares:
    #
    #   .build/lambda_pkg
    #
    # Terraform then archives that directory using archive_file.
    # --------------------------------------------------------------------

    working_dir = "${path.module}/.."

    command = "bash scripts/build_lambda.sh"

    environment = {
      USE_DOCKER_BUILD = var.use_docker_build
    }

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


