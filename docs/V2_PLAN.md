### Bloodhound v2 Plan (tracked implementation checklist)

This document is the shared plan for evolving Bloodhound from v1.0 to v2.x while keeping the project simple, readable, and student-friendly.

---

### 0) Current v1.0 baseline (what exists today)

- **What it does**

  - Scans a fixed list of AWS regions.
  - Collects **EC2** instance IDs (skipping stopped/terminated).
  - Collects **RDS** instance identifiers.
  - Formats one Slack message and posts it to a channel.

- **How it is invoked**

  - A GitHub Actions scheduled workflow calls:
    - `aws lambda invoke --function-name BloodhoundLambda ...`

- **Important constraints carried into v2**
  - Keep **GitHub Actions** as the scheduler (do not migrate to EventBridge).
  - Keep **Slack** as the only notification surface (no email).
  - Single AWS account only (no Organizations / cross-account roles for now).
  - Teardown should support **terminate/delete** (default). “Stop-only” is a later enhancement.

---

### 1) v2 guiding principles (to keep it minimal)

- **Configuration over code edits**

  - Anything that will vary cohort-to-cohort (start month, channels, regions) must be env-configurable.

- **Safe rollout for destructive actions**

  - Default is **dry-run** (report proposed deletions).
  - Apply-mode requires an explicit flag.

- **Simple whitelist**

  - Primary mechanism is a single tag: `bloodhound:keep=true`.
  - Optional escape hatch: env var allowlist for IDs/ARNs.

- **No unnecessary infrastructure**
  - Prefer “compute from AWS APIs each run” when it’s easy (e.g., budget streak calculation).
  - Add a database only if it materially simplifies or is required.

---

### 2) v2 configuration (environment variables)

#### Slack

- **`SLACK_BOT_TOKEN`**: Slack bot token used to post messages.
- **`SLACK_SCAN_CHANNEL_ID`**: Channel for “scan summary / what exists”.
- **`SLACK_ALERT_CHANNEL_ID`**: Channel for “budget alerts + teardown outcomes”.
  - If unset, default to `SLACK_SCAN_CHANNEL_ID`.

#### Regions

- **`REGION_MODE`**: `explicit` or `discover`
  - `explicit`: use `REGIONS`
  - `discover`: discover regions dynamically (then optionally filter)
- **`REGIONS`**: comma-separated region list (only used in `explicit` mode)

#### Whitelist (minimal)

- **`KEEP_TAG_KEY`**: default `bloodhound:keep`
- **`KEEP_TAG_VALUE`**: default `true`
- **`KEEP_RESOURCE_IDS`** (optional): comma-separated resource IDs/ARNs always excluded from teardown

#### Teardown controls

- **`APPLY_CHANGES`**: `true|false` (default `false`)
- **`TEARDOWN_SIMULATE`**: `true|false` (default `true` for safe testing)
- **`TEARDOWN_TARGET_IDS`**: optional safety rail, comma-separated IDs/ARNs
- **`TEARDOWN_ALLOW_ALL`**: if true, delete all non-whitelisted candidates
- **`RDS_FINAL_SNAPSHOT`**: `true|false` (default `false`)

#### Budget (dynamic cohort)

- **`COHORT_START_YYYY_MM`**: e.g. `2025-12` (set per cohort)
- **`COHORT_TOTAL_BUDGET_USD`**: default `3000`
- **`COHORT_LENGTH_MONTHS`**: default `7`
- **`BUDGET_OVER_DAYS`**: default `2`


