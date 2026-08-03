# Integrating PR #2 (mmccla1n v2 CI/CD + docs) into the current v2 line

This branch (`integrate-pr2-cicd-docs`) salvages the **architecture-neutral, additive**
pieces of [PR #2](https://github.com/codeplatoon-devops/Bloodhound/pull/2) on top of the
current v2 line (flat `bloodhound/` layout with `/guard`). It is **work in progress** —
the coupled parts below still need decisions.

## Brought in (safe / additive)

- `scripts/build_lambda.sh` — rsyncs `bloodhound/` + `handlers/`; works with our flat layout as-is.
- `scripts/bootstrap_github_oidc.sh` — one-time GitHub OIDC role bootstrap for CI auth.
- `tools/smoke_test_lambda.sh` — pure AWS CLI checks against `BloodhoundLambdaV2`.
- `infra/slack/bloodhound_v2_manifest.json` + `infra/slack/README.md` — Slack app manifest.
- `.github/workflows/bloodhound_ops.yml` — manual ops workflow (see caveat).
- `docs/lambda_packaging.md`, `docs/troubleshooting_terraform_lambda.md`, `docs/safe_operations.md`.

## Outstanding — needs a decision (do NOT merge to main until resolved)

1. **OIDC role / Terraform.** `bloodhound_ops.yml` and the OIDC scripts assume an IAM role
   that PR #2's `infra/` creates (`account_guard.tf`, `iam.tf` changes, `variables.tf` +96 lines).
   Our `infra/` is tuned for our code. Adopting theirs is not a file-copy — it needs a
   `terraform plan` against the Code Platoon account and testing. **Not done here.**

2. **`validation` mode is broken on this branch.** `bloodhound_ops.yml` mode=`validation`
   calls `tools/run_validation_workflow.sh`, which depends on mmc's `validation_handler`
   (part of their `handlers/services` refactor we have NOT adopted). `scan` / `status`
   modes are architecture-neutral; `validation` will fail until the refactor question is settled.

3. **Command-specific docs not ported.** PR #2 docs `troubleshooting_slack_commands.md`,
   `slack_app_operations.md`, `quick_demo.md`, `run_validation.md`, `validate_teardown.md`,
   `slack_and_lambda_validation.md`, `architecture_overview.md` reference `/v2_seek*` /
   `/v2_status` and the handlers/services architecture. They need command-name reconciliation
   to our set (`/seek`, `/seek_cost`, `/seek_whitelist`, `/seek_destroy`, `/guard`) before use.

4. **The refactor decision (blocks 1–3).** PR #2 restructured into `handlers/` + `services/`.
   Our `/guard` lives in the flat layout. Either (a) keep flat and skip the refactor, or
   (b) migrate `/guard` + cost/whitelist commands into the services layout. Most of the
   coupled infra/docs work above hinges on this.

5. **Close PR #2** as superseded (with a comment crediting salvaged work) — only after the
   above lands.
