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

---

## UPDATE — full `mmc/main` merge completed (branch `merge-pr2-full`)

All of PR #2 was merged into our line. 5 conflicts resolved:

- `bloodhound/app.py`, `bloodhound/messages.py` → **kept ours (HEAD)**. The deployed
  entrypoint (`handlers.lambda_function.lambda_handler`, per `infra/lambda.tf`) calls our
  `bloodhound.app.run`, so our worker + our formatters are the canonical, working path.
- `bloodhound/slack_commands.py` → **union**. All commands preserved: `/seek`, `/seek_cost`,
  `/seek_whitelist`, `/seek_destroy` (+ `/v2_seek_destroy` alias), `/guard`, and
  `/v2_seek_destroy_plan` (maps to the non-destructive `seek` mode).
- `README.md` → kept our rewrite. `.gitignore` → union.

Verified: `guard.py`/`controls.py` intact; the deployed cold-start path imports cleanly;
`python -m compileall` passes; **every** module (incl. mmc's `handlers/` + `services/`) imports.

### Chose our (flat) architecture as canonical; mmc's handlers/services are present but UNWIRED

mmc's `bloodhound/handlers/*` and `bloodhound/services/*` landed as additive modules but are
**not** driven by our worker. To keep the tree import-clean, two formatters
(`format_status_message`, `format_whitelisted_resources_message`) + helpers `_fmt_kv` /
`_display_resource` were ported into our `messages.py` (used only by those services).

### Still deferred (NOT done by this merge — these are feature/architecture work, not conflicts)

- **`/v2_status`** is intentionally left unrouted in `slack_commands.py` — our worker has no
  `status` mode (that lives in mmc's `status_service`). Routing it now would silently run a
  full scan under the status name.
- **Scheduled path is broken.** `handlers/lambda_function.py` routes scheduled events to
  `bloodhound.handlers.scheduled_handler.handle_scheduled_event`, which lazily imports
  `run_scheduled_scan` from `bloodhound.app` — a name our `app.py` does **not** define. The
  module imports fine (lazy), but a real scheduled invoke would raise. The scheduled workflow
  (`invoke_lambda.yml`) is currently disabled, so no live impact. Fix = add a
  `run_scheduled_scan` entry to our `app.py` (or point the branch at our `run`).
- Adopting mmc's handlers/services architecture wholesale (and wiring `/v2_status`) remains a
  separate follow-up.
