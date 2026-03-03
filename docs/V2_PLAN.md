## Bloodhound v2 Plan (tracked implementation checklist)

This document is the shared plan for evolving Bloodhound from v1.0 → v2.x while keeping the project simple and readable.
It’s intentionally pragmatic: what’s **done** is marked with strikethrough, and what’s **next** stays short and actionable.

Repo: `https://github.com/codeplatoon-devops/Bloodhound.git`

---

## 0) Current reality (what v2 does today)

Bloodhound v2 is already deployed as a **new** Lambda (`BloodhoundLambdaV2`) so it does not touch v1.

### Invocation paths

- **Scheduled**: GitHub Actions can invoke `BloodhoundLambdaV2` on a cadence.
- **On-demand**: Slack slash commands (`/seek`, `/seek_destroy`) hit a **Lambda Function URL**.

### What it scans (per region)

- **EC2 instances** (skips stopped/terminated)
- **EBS volumes** (unattached/`available`)
- **Elastic IPs** (unassociated)
- **NAT Gateways** (active states)
- **RDS DB instances**
- **ELBv2 load balancers**

### What it produces (Slack)

- **Scan summary** (includes zero counts)
- **Whitelisted resources list** (separate message)
- **Budget summary** (7-month cohort, dynamic monthly allowance)
- **Teardown plan** (always produced)
- **Teardown results** (only when apply-mode executes)

### Teardown safety rails (v2)

- Default is **dry-run** (`APPLY_CHANGES=false`)
- Safe testing of apply-mode: **simulate** (`TEARDOWN_SIMULATE=true`)
- Strong safety rails:
  - Explicit allowlist: `TEARDOWN_TARGET_IDS=...`
  - Allow-all mode: `TEARDOWN_ALLOW_ALL=true` (dangerous; relies on whitelisting)
- Slash destroy requires:
  - Confirm token: `/seek_destroy CONFIRM` (configurable token)
  - Optional allowlists: user/channel IDs

---

## 1) v2 guiding principles (keep it minimal)

- **Configuration over code edits**
  - Anything that varies cohort-to-cohort (start month, channels, regions) must be env-configurable.
- **Safe rollout for destructive actions**
  - Default is dry-run.
  - Apply-mode is explicit and layered with safety rails.
- **Simple whitelist**
  - Primary mechanism is a single tag: `bloodhound:keep=true`.
  - Optional escape hatch: env allowlist for IDs/ARNs (keep list) and explicit teardown targets.
- **No unnecessary infrastructure**
  - Compute from AWS APIs each run when possible.
  - Avoid DB/state unless it materially simplifies the system.

---

## 2) v2 configuration (environment variables)

This is the canonical list; `env.example` should be treated as the “source of truth” for local runs.

### Slack

- **`SLACK_ENABLED`**: `true|false`
- **`SLACK_BOT_TOKEN`**: bot token used to post messages
- **`SLACK_SCAN_CHANNEL_ID`**: channel for scan summaries + whitelisted list
- **`SLACK_ALERT_CHANNEL_ID`**: channel for budget alerts + teardown plan/results
  - If unset, defaults to `SLACK_SCAN_CHANNEL_ID`

### Slack slash commands (Function URL)

- **`SLACK_SIGNING_SECRET`**: required for Slack signature verification
- **`SLACK_DESTROY_CONFIRM_TOKEN`**: required argument text for `/seek_destroy` (default `CONFIRM`)
- **`SLACK_ALLOWED_USER_IDS`** (optional): comma-separated list of Slack user IDs allowed to run destroy
- **`SLACK_ALLOWED_CHANNEL_IDS`** (optional): comma-separated list of Slack channel IDs allowed to run destroy

### Regions

- **`REGION_MODE`**: `explicit` or `discover`
  - `explicit`: use `REGIONS`
  - `discover`: discover regions dynamically
- **`REGIONS`**: comma-separated region list (only used in `explicit` mode)

### Whitelist

- **`KEEP_TAG_KEY`**: default `bloodhound:keep`
- **`KEEP_TAG_VALUE`**: default `true`
- **`KEEP_RESOURCE_IDS`** (optional): comma-separated IDs/ARNs always treated as kept

### Teardown controls

- **`APPLY_CHANGES`**: `true|false` (default `false`)
- **`TEARDOWN_SIMULATE`**: `true|false` (default `false` in config; we often use `true` for safe testing)
- **`TEARDOWN_TARGET_IDS`** (optional): comma-separated IDs/ARNs that are the only allowed targets
- **`TEARDOWN_ALLOW_ALL`**: `true|false` (dangerous; delete everything not whitelisted)
- **`RDS_FINAL_SNAPSHOT`**: `true|false` (default `false`)

### Budget (dynamic cohort)

- **`COHORT_START_YYYY_MM`**: e.g. `2026-01`
- **`COHORT_TOTAL_BUDGET_USD`**: default `3000`
- **`COHORT_LENGTH_MONTHS`**: default `7`
- **`BUDGET_OVER_DAYS`**: default `2`

---

## 3) Target architecture (what’s implemented)

### Code structure (current)

- `bloodhound/`
  - `app.py` (orchestrator)
  - `config.py` (env parsing + defaults + validation)
  - `scanner/` (`regions.py`, `scan_all.py`, `ec2.py`, `rds.py`, `elbv2.py`)
  - `whitelist.py`
  - `budget.py`
  - `teardown/` (`planner.py`, `executor.py`)
  - `messages.py` (Slack message formatting)
  - `slack.py` (Slack API)
  - `slack_commands.py` (Function URL entrypoint: verify + route)
  - `types.py` (resource record schema)
- `handlers/lambda_function.py` (Lambda handler)
- `tools/run_local.py` (local runner)
- `infra/` (Terraform: build zip, IAM, Lambda, Function URL)

### Logic flow (every run)

- **Scan**
  - Determine regions
  - Collect resources per region/service
  - Apply whitelist
  - Post scan summary + whitelisted list
- **Budget**
  - Use Cost Explorer to compute cohort-to-date spend + dynamic monthly allowance
  - Compute run-rate month-end projection and “over budget streak”
  - Post budget summary; post alert only when threshold is met
- **Teardown**
  - Build a plan (always)
  - If apply-mode: execute (or simulate) and post results

---

## 4) Resource record schema (current)

All scanners produce records with a shared shape (`bloodhound/types.py`):

- **Required**
  - `service`, `resource_type`, `region`, `id`, `state`, `tags`
- **Optional**
  - `delete_supported`, `delete_action`, `delete_params`

---

## 5) Resources to scan (status)

Phase 1 (high value, low complexity)

- ~~EC2 instances~~
- ~~RDS instances~~
- ~~Elastic IPs (unassociated)~~
- ~~NAT gateways~~
- ~~EBS volumes (unattached)~~
- ~~ELBv2 load balancers~~

Phase 2 (later; only if needed)

- EBS snapshots
- AMIs
- ElastiCache
- OpenSearch
- Redshift

---

## 6) Teardown delete policy (status)

Defaults (as implemented)

- ~~EC2: terminate~~
- ~~EBS: delete unattached volumes~~
- ~~EIP: release if unassociated~~
- ~~NAT gateway: delete~~
- ~~Load balancer: delete~~
- ~~RDS: delete without final snapshot by default (`RDS_FINAL_SNAPSHOT=false`)~~

---

## 7) Milestones (tracked checklist)

### v2.0 (refactor + config + deploy)

- ~~Archive v1.0 as runnable snapshot under `versions/v1_0/`~~
- ~~Modularize into package structure (`bloodhound/`, `handlers/`, `tools/`, `docs/`)~~
- ~~Env-driven Slack channels (scan vs alert)~~
- ~~Env-driven region configuration (explicit + discover mode)~~
- ~~Terraform deploy of a new Lambda (`BloodhoundLambdaV2`)~~
- ~~Slack message formatting improvements (human-readable, consistent, includes zeros)~~

### v2.1 (resource coverage)

- ~~EC2 instances~~
- ~~EBS unattached volumes~~
- ~~EIPs unassociated~~
- ~~NAT gateways~~
- ~~RDS instances~~
- ~~ELBv2~~

### v2.2 (whitelist)

- ~~Tag-based whitelist: `bloodhound:keep=true`~~
- ~~Optional keep list: `KEEP_RESOURCE_IDS`~~
- ~~Whitelisted resources posted as a separate list~~

### v2.3 (teardown dry-run)

- ~~Planner produces proposed actions~~
- ~~Plan posted to Slack~~
- ~~Full plan logged as JSON~~

### v2.4 (teardown apply-mode + safety rails)

- ~~Apply-mode gated by `APPLY_CHANGES=true`~~
- ~~Simulate mode available (`TEARDOWN_SIMULATE=true`)~~
- ~~Target filter safety rail (`TEARDOWN_TARGET_IDS`)~~
- ~~Allow-all mode (`TEARDOWN_ALLOW_ALL=true`)~~
- ~~Executor posts results to Slack~~

### v2.5 (budget + alerts)

- ~~Cost Explorer cohort-to-date + dynamic monthly allowance~~
- ~~Month-end run-rate projection~~
- ~~Alert on `BUDGET_OVER_DAYS` consecutive days over allowance~~

### v2.6 (slash commands)

- ~~Function URL entrypoint~~
- ~~Signature verification + replay protection~~
- ~~`/seek` (non-destructive)~~
- ~~`/seek_destroy CONFIRM` (destructive, guarded)~~
- ~~Optional allowlists for destroy (user/channel IDs)~~

---

## 8) Open questions / next improvements (optional)

- Separate scan vs teardown IAM roles (read-only vs write)
- Add more resource types if needed (snapshots/AMIs/etc.)
- Optional: separate scheduled scan runs from destructive runs via dedicated workflow/job