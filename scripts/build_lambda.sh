#!/usr/bin/env bash
set -euo pipefail

: <<'DOC'
scripts/build_lambda.sh

Builds the Bloodhound Lambda deployment package.

This script prepares the directory:

    .build/lambda_pkg

Terraform then archives that directory into:

    .build/bloodhound_lambda_v2.zip

using the archive_file provider.

---------------------------------------------------------------------

Build modes

Docker build (default)
    Installs dependencies using the official AWS Lambda runtime
    container to guarantee compatibility with the Lambda environment.

Local build
    Installs dependencies using your local Python environment.
    This is faster but may produce incompatible binaries.

---------------------------------------------------------------------

Usage

Show help

    ./scripts/build_lambda.sh -h

Docker build (default)

    ./scripts/build_lambda.sh

Force Docker build

    ./scripts/build_lambda.sh --docker

Force local build

    ./scripts/build_lambda.sh --local

---------------------------------------------------------------------

Required tools

Docker mode:
    docker

Local mode:
    python3
    pip
    rsync
DOC


# ------------------------------------------------------------
# Help helper
# ------------------------------------------------------------

show_help() {
  sed -n '/^DOC$/,/^DOC$/p' "$0" | sed '1d;$d'
  exit 0
}


# ------------------------------------------------------------
# Parse arguments
# ------------------------------------------------------------

BUILD_MODE="docker"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      ;;
    --docker)
      BUILD_MODE="docker"
      shift
      ;;
    --local)
      BUILD_MODE="local"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run with -h for usage."
      exit 1
      ;;
  esac
done

echo
echo "---------------------------------------------"
echo "Lambda build mode: $BUILD_MODE"
echo "---------------------------------------------"


# ------------------------------------------------------------
# Step 1 — Prepare clean build directory
#
# Lambda packages must be deterministic. We remove any
# previous build artifacts to prevent stale dependencies
# or leftover files from entering the deployment package.
# ------------------------------------------------------------

echo
echo "Preparing Lambda build directories..."

BUILD_DIR=".build"
PKG_DIR="$BUILD_DIR/lambda_pkg"

rm -rf "$BUILD_DIR"
mkdir -p "$PKG_DIR"


# ------------------------------------------------------------
# Step 2 — Install runtime dependencies
#
# Dependencies from requirements.txt are installed directly
# into the Lambda package directory so they are included in
# the final deployment package.
# ------------------------------------------------------------

echo
echo "Installing dependencies..."

if [[ "$BUILD_MODE" == "docker" ]]; then

  echo "Using Docker Lambda runtime (Amazon Linux)"

  docker run --rm \
    -v "$PWD":/var/task \
    public.ecr.aws/sam/build-python3.10 \
    pip install --upgrade --no-cache-dir -r requirements.txt -t .build/lambda_pkg

else

  echo "Using local Python environment"

  python3 -m pip install --upgrade --no-cache-dir -r requirements.txt -t .build/lambda_pkg

fi


# ------------------------------------------------------------
# Step 3 — Copy application source code
#
# The Lambda package must include the Bloodhound application
# modules and the Lambda handler entrypoint.
# rsync preserves directory structure and includes new modules.
# ------------------------------------------------------------

echo
echo "Copying application source..."

# Engineer note:
# rsync preserves directory structure and ensures new modules
# such as bloodhound/aws.py or scanner/ are included automatically.

rsync -a --exclude "__pycache__" --exclude "*.pyc" bloodhound/ .build/lambda_pkg/bloodhound/

rsync -a --exclude "__pycache__" --exclude "*.pyc" handlers/ .build/lambda_pkg/handlers/


# ------------------------------------------------------------
# Step 4 — Debug visibility
#
# Display the final Lambda package contents to confirm the
# correct files are included.
# Useful when diagnosing import or packaging issues.
# ------------------------------------------------------------

echo
echo "Prepared package dir: .build/lambda_pkg"
echo "Lambda package contents:"
ls -R .build/lambda_pkg

echo
echo "Package size:"
du -sh .build/lambda_pkg

echo
echo "Lambda package build complete."