/*
infra/locals.tf

Local paths and naming helpers.
These keep the build/archive + Lambda resources consistent and easy to tweak.
*/

locals {
  build_dir   = "${path.module}/../.build"
  pkg_dir     = "${local.build_dir}/lambda_pkg"
  zip_path    = "${local.build_dir}/bloodhound_lambda_v2.zip"
  name_prefix = var.name_prefix
}


