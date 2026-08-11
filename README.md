# Bloodhound v2 — AWS cost-guard scanner, Slack control plane, and safe teardown

Bloodhound scans selected AWS regions for common cost-leak resources (EC2 / RDS / ELBv2),
posts results to Slack, manages spend **guardrails** (which services student groups may use),
and can optionally tear down resources that are **not** whitelisted.

You drive it entirely from **Slack slash commands** — start there.

- [Slack slash commands](#slack-slash-commands) ← the operator interface
- [Managing service access with `/guard`](#managing-service-access-with-guard) ← e.g. Bedrock for a student group
- [Deploy](#deploy)
- [Environment variables](#environment-variables)
- [Local setup + testing](#local-setup--testing)
- [Whitelisting](#whitelisting) · [Teardown controls](#teardown-controls)

![AWS Architecture Diagram (v2)](assets/bloodhound_lambda_architecture_v2.svg)

---

## Slack slash commands

All commands hit a single **Lambda Function URL**; routing is by Slack's `command` field.
Read-only commands anyone in an allowed channel can run; **mutating** commands require the
caller to be allowlisted (see [Permissions & safety](#permissions--safety)).

| Command | What it does | Mutates? |
|---|---|---|
| `/seek` | Run a scan and post the report to Slack | no |
| `/seek_cost` | Post AWS month-to-date cost breakdown + budget summary | no |
| `/seek_whitelist` | Post active whitelist rules + all currently protected resources | no |
| `/seek_destroy CONFIRM` | Destructive teardown of all non-whitelisted candidates (requires the confirm token) | **yes** |
| `/guard <subcommand>` | View and manage spend guardrails (service allow/deny, group membership) | some subcommands |

### `/guard` subcommands

A **guardrail** is a named, two-layer spend control that `/guard` edits as a unit so the two
layers can never drift apart:

- an Organizations **SCP** (e.g. `cp-org-spend-stop`) — restricts member accounts under its target OUs/accounts
- an IAM **managed policy attached to a group** (e.g. `cp-aico-echo-cost-guard` on group `aico-echo-class`) — restricts IAM users in the management account

| Subcommand | Alias | Effect | Mutates? |
|---|---|---|---|
| `/guard list` | `ls` | List all guardrails: layers, attachments, denied services | no |
| `/guard show <name>` | | Full detail for one guardrail | no |
| `/guard members <name>` | `who` | List users in the guardrail's IAM group | no |
| `/guard allow <name> <service>` | `unblock` | **Remove** a service from the deny lists (grant access) | **yes** |
| `/guard deny <name> <service>` | `block` | **Add** a service to the deny lists (block access) | **yes** |
| `/guard enable <name>` | | (Re)attach the IAM policy to its group | **yes** |
| `/guard disable <name>` | | Detach the IAM policy from its group | **yes** |
| `/guard add-student <name> <user>` | `add` | Add a user to the guardrail's group | **yes** |
| `/guard remove-student <name> <user>` | `remove`, `rm` | Remove a user from the guardrail's group | **yes** |

The default guardrail is named **`cost-guard`** (override the registry via `GUARD_REGISTRY`).

---

## Managing service access with `/guard`

This is the common case: a student group needs a normally-blocked service turned on (or off).

**Example — give a student group access to Amazon Bedrock:**

```
/guard allow cost-guard bedrock
```

That removes `bedrock` from the deny list on **both** the SCP and the IAM group policy at once.
Bedrock exposes three service prefixes — grant all three for the full runtime:

```
/guard allow cost-guard bedrock
/guard allow cost-guard bedrock-runtime
/guard allow cost-guard bedrock-agent-runtime
```

To block it again, swap `allow` for `deny`:

```
/guard deny cost-guard bedrock
```

### Which services can be toggled

`allow` / `deny` may only touch services in `GUARD_TOGGLEABLE_SERVICES`. This is deliberately
the expensive-compute / ML set and **excludes** `iam`, `organizations`, EC2 instance-type caps,
etc., so a Slack message can never loosen the core guardrails themselves. Defaults:

```
rds, redshift, neptune-db, dax, memorydb,
sagemaker, bedrock, bedrock-runtime, bedrock-agent-runtime,
eks, elasticmapreduce, es, aoss, q, deepracer, forecast,
frauddetector, kendra, comprehendmedical, healthlake, omics, braket
```

### Permissions & safety

- **Mutating** commands (`/guard allow|deny|enable|disable|add-student|remove-student`, and
  `/seek_destroy`) require the caller's Slack user ID to be in `GUARD_ALLOWED_USER_IDS`
  (falls back to `SLACK_ALLOWED_USER_IDS`). If neither is set, **all mutations are refused**
  (fail-safe) — the command endpoint is a public Lambda Function URL.
- `/seek_destroy` also requires the confirm token (`SLACK_DESTROY_CONFIRM_TOKEN`, default `CONFIRM`).
- Set `SLACK_SIGNING_SECRET` so the Lambda can verify requests genuinely come from Slack.

---

## Deploy

Bloodhound v2 deploys as its own Lambda (`BloodhoundLambdaV2`) so it never touches any v1 function.

### Option A — Terraform (recommended)

Terraform builds the deployment zip and provisions the Lambda, its Function URL, and IAM.

```bash
cd infra
terraform init
terraform apply
```

Terraform builds `../.build/bloodhound_lambda_v2.zip` automatically (via `terraform_data` +
`archive_file`), so you need `python3`, `pip`, `zip`, and `rsync` installed locally.
After apply, set the `lambda_function_url` output as the Request URL for your slash commands
in Slack. See [`infra/README.md`](infra/README.md) for details.

> Prefer setting secrets (Slack token, signing secret) in the Lambda console or a secrets
> manager rather than `var.lambda_env` — the latter stores them in Terraform state.

### Option B — manual Lambda console

- **Function name:** `BloodhoundLambdaV2`
- **Handler:** `handlers.lambda_function.lambda_handler`
- Build the zip (the `.build/` dir is not committed — Terraform builds it, or build it yourself),
  upload it, then set the [environment variables](#environment-variables) below.

Smoke-test the deployed function:

```bash
aws lambda invoke \
  --function-name BloodhoundLambdaV2 \
  --payload file://tools/test_event.json \
  output.txt \
  --region us-west-2

cat output.txt
```

### Wire up Slack

In your Slack app settings, register each slash command (`/seek`, `/seek_cost`,
`/seek_whitelist`, `/seek_destroy`, `/guard`) with the **Request URL** set to the Lambda
Function URL. Creating the Slack app from scratch is covered in [`docs/SLACK_SETUP.md`](docs/SLACK_SETUP.md).

---

## Environment variables

Set these on the Lambda (copy from your local `.env` — see [`env.example`](env.example)).

**Slack (required for slash commands)**

| Var | Purpose |
|---|---|
| `SLACK_BOT_TOKEN` | Bot token used to post reports |
| `SLACK_SCAN_CHANNEL_ID` / `SLACK_ALERT_CHANNEL_ID` | Where scan reports / alerts go |
| `SLACK_SIGNING_SECRET` | Verify inbound requests came from Slack |
| `SLACK_ALLOWED_USER_IDS` | (optional) allowlist for mutating commands (fallback for `/guard`) |
| `SLACK_ALLOWED_CHANNEL_IDS` | (optional) restrict which channels may invoke commands |
| `SLACK_DESTROY_CONFIRM_TOKEN` | Confirm token for `/seek_destroy` (default `CONFIRM`) |

**Guardrails (`/guard`)**

| Var | Purpose |
|---|---|
| `GUARD_ALLOWED_USER_IDS` | Allowlist of Slack user IDs permitted to run `/guard` mutations (falls back to `SLACK_ALLOWED_USER_IDS`) |
| `GUARD_TOGGLEABLE_SERVICES` | (optional) override the CSV of services `allow`/`deny` may touch |
| `GUARD_REGISTRY` | (optional) JSON overriding the guardrail registry (name, scp, iam_policy, group) |

**Scan / budget / teardown**

| Var | Purpose |
|---|---|
| `REGION_MODE`, `REGIONS` | Which regions to scan |
| `COHORT_START_YYYY_MM`, `COHORT_TOTAL_BUDGET_USD`, `COHORT_LENGTH_MONTHS`, `BUDGET_OVER_DAYS` | Budget summary math |
| `APPLY_CHANGES`, `TEARDOWN_SIMULATE`, `TEARDOWN_ALLOW_ALL`, `TEARDOWN_TARGET_IDS` | Teardown behavior (see below) |

---

## Local setup + testing

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cp env.example .env    # then fill it in — Bloodhound auto-loads .env for local runs

# Run against a chosen AWS profile:
AWS_PROFILE=geekstar .venv/bin/python tools/run_local.py
```

Requirements: Python 3.10+ (or match your Lambda runtime), AWS CLI configured
(`aws configure --profile <name>`; profiles live in `~/.aws/config` / `~/.aws/credentials`),
and a Slack bot token + channel IDs.

---

## Whitelisting

Resources are **kept (whitelisted)** when they match any rule:

| Rule type | Env var | Example |
|---|---|---|
| Tag | `KEEP_TAG_RULES` | `bloodhound:keep=true` |
| Name/tag regex | `KEEP_NAME_PATTERNS` | `buffalo,fullstack,vetlaunch,dont-touch` |
| Explicit ID/ARN | `KEEP_RESOURCE_IDS` | `arn:aws:rds:...:db:vetlaunch-dev-db` |

Legacy single-tag config still works via `KEEP_TAG_KEY` + `KEEP_TAG_VALUE`.
`/seek_whitelist` posts the active rules plus every currently protected resource.

---

## Teardown controls

By default Bloodhound posts a teardown **plan only** (`APPLY_CHANGES=false`). To actually
delete/terminate non-whitelisted resources, set `APPLY_CHANGES=true`. Safety rails:

- **simulate (no deletes):** `TEARDOWN_SIMULATE=true`
- **only delete explicit IDs/ARNs:** `TEARDOWN_TARGET_IDS=...`
- **delete everything not whitelisted:** `TEARDOWN_ALLOW_ALL=true`

---

## GitHub Actions

`.github/workflows/invoke_lambda.yml` invokes `BloodhoundLambdaV2` on a schedule (currently
disabled — enable it in the Actions tab when you want scheduled scans).

## Project docs

- v2 plan: [`docs/V2_PLAN.md`](docs/V2_PLAN.md)
- Slack app setup: [`docs/SLACK_SETUP.md`](docs/SLACK_SETUP.md)
- Infrastructure: [`infra/README.md`](infra/README.md)
