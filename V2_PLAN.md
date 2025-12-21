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
- **`TEARDOWN_MODE`**: default `delete` (future: allow `stop`)
- **`RDS_FINAL_SNAPSHOT`**: `true|false` (default `false`)

#### Budget (dynamic cohort)

- **`COHORT_START_YYYY_MM`**: e.g. `2026-01` (set per cohort)
- **`COHORT_TOTAL_BUDGET_USD`**: default `3000`
- **`COHORT_LENGTH_MONTHS`**: default `7`
- **`BUDGET_OVER_DAYS`**: default `2` (consecutive days over budget before alerting)

---

### 3) Target v2 architecture (still simple)

#### Logical flow (every scheduled run)

- **Scan**

  - Determine regions to scan.
  - Collect resources per region/service.
  - Apply whitelist.
  - Produce:
    - Slack scan summary (scan channel)
    - Machine-readable report (JSON in logs; optional persisted store later)

- **Budget**

  - Use Cost Explorer to compute:
    - Cohort-to-date spend (from cohort start through today)
    - Remaining cohort budget
    - Remaining months
    - Dynamic monthly allowance (remaining_budget / remaining_months)
    - Current month projected month-end spend (simple run-rate)
  - Determine “over budget streak” for the last `BUDGET_OVER_DAYS` days using daily costs for the current month.
  - Post budget summary + alert (alert channel only when threshold reached).

- **Teardown**
  - Default: post “proposed actions” only (dry-run).
  - If `APPLY_CHANGES=true`: execute deletion/termination calls and post results.

#### Code structure (proposed)

- `Bloodhound/`
  - `bloodhound.py` (entrypoint; keep thin)
  - `bloodhound/`
    - `config.py` (env parsing, defaults, validation)
    - `scanner/`
      - `ec2.py`
      - `rds.py`
      - `eip.py`
      - `nat_gateway.py`
      - `ebs.py`
      - `elbv2.py`
      - `regions.py`
    - `whitelist.py` (tag filter + optional ID/ARN allowlist)
    - `budget.py` (Cost Explorer queries + projection logic)
    - `teardown/`
      - `planner.py` (dry-run action plan)
      - `executor.py` (apply-mode execution)
    - `slack.py` (posting + message formatting)
    - `types.py` (resource record schema)
    - `logging.py` (structured logs, consistent formatting)

This modularity is intentionally small: one folder, small files, no framework.

---

### 4) Resource record schema (simple + consistent)

All scanners should output a list of records with the same shape.

- **Required**

  - `service`: e.g. `ec2`, `rds`, `eip`, `nat`, `ebs`, `elbv2`
  - `resource_type`: e.g. `instance`, `db_instance`, `address`, `nat_gateway`, `volume`, `load_balancer`
  - `region`
  - `id`: service ID (InstanceId, VolumeId, etc.)
  - `arn`: include if easily available; else `null`
  - `state`: normalized string (e.g. `running`, `available`, `in-use`, `deleting`)
  - `tags`: dictionary of tags (best-effort)

- **Optional (useful for teardown)**
  - `delete_supported`: boolean
  - `delete_action`: string (e.g. `terminate_instances`, `delete_db_instance`, `release_address`)
  - `delete_params`: minimal params needed (ids, flags)

---

### 5) Resources to scan (priority order)

Goal: cover the most common and expensive student mistakes first.

#### Phase 1 (v2.1) — high value, low complexity

- **EC2 Instances** (existing)
- **RDS Instances** (existing)
- **Elastic IPs** (unassociated)
- **NAT Gateways**
- **EBS volumes** (unattached)
- **Load Balancers** (ALB/NLB)

#### Phase 2 (later; only if needed)

- EBS snapshots
- AMIs
- ElastiCache
- OpenSearch
- Redshift

---

### 6) Whitelist rules (minimal)

#### Rule A: tag-based keep (primary)

- If resource has tag:
  - key: `bloodhound:keep`
  - value: `true`
- Then:
  - Exclude from teardown
  - Optionally:
    - Exclude from scan counts (or mark as “kept”)

#### Rule B: env allowlist (optional)

- If resource `id` or `arn` is listed in `KEEP_RESOURCE_IDS`, exclude from teardown.

---

### 7) Teardown plan (terminate/delete with a safe rollout)

#### v2.3 (dry-run only)

- Build a “proposed action plan”:
  - For each resource:
    - If whitelisted: skip
    - Else if deletable: include action + minimal parameters
    - Else: include as “manual” (for visibility)
- Post to alert channel:
  - Counts by service/region
  - List of proposed actions (keep concise; link to logs for full JSON)

#### v2.4 (apply-mode)

- If `APPLY_CHANGES=true`:
  - Execute actions.
  - Post:
    - Success counts
    - Failure counts + top errors
  - Emit structured logs of every action attempted.

#### Delete policy defaults (as requested)

- **EC2**: terminate (not stop)
- **RDS**: delete without final snapshot (`RDS_FINAL_SNAPSHOT=false`)
- **EBS**: delete unattached
- **EIP**: release if unassociated
- **NAT Gateway**: delete
- **Load balancer**: delete

---

### 8) Budget/projections plan (7-month cohort, $3000, dynamic)

#### Definitions

- Cohort total budget: `COHORT_TOTAL_BUDGET_USD` (default 3000)
- Cohort length months: `COHORT_LENGTH_MONTHS` (default 7)
- Cohort start month: `COHORT_START_YYYY_MM`

#### Each run computes

- **Cohort-to-date spend**
  - Sum monthly spend from cohort start through current month-to-date.
- **Remaining cohort budget**
  - `remaining_budget = total_budget - cohort_to_date_spend`
- **Remaining months**
  - Based on cohort start and current date (clamped to at least 1).
- **Dynamic monthly allowance**
  - `monthly_allowance = remaining_budget / remaining_months`
- **Month-end projection**
  - Simple run-rate:
    - `projection = (month_to_date_spend / days_elapsed) * days_in_month`
  - (Optional later) use Cost Explorer forecast if desired.

#### Alerting logic (simple, no DB)

- For the current month:
  - Pull daily costs for the last `BUDGET_OVER_DAYS` days.
  - For each of those days, compute what the month-end projection would have been at that point.
  - If **all** of those daily projections exceed `monthly_allowance`, alert.

This yields “consecutive days over budget” behavior without storing state.

#### Slack message content (alert channel)

- Cohort start month
- Cohort-to-date spend
- Remaining cohort budget
- Remaining months
- Dynamic monthly allowance
- Current month-to-date spend
- Projected month-end spend
- Whether alert threshold was met (and for how many days)

---

### 9) GitHub Actions plan (keep it, extend it)

#### Current

- `invoke_lambda.yml` runs on schedule and calls Lambda.

#### v2 changes (still simple)

- Continue invoking the same Lambda.
- Optionally add a second workflow/job later for teardown apply-mode:
  - Example: weekly teardown run with `APPLY_CHANGES=true`
  - Keep scanning separate from destructive actions to reduce risk.

---

### 10) IAM permissions plan (least privilege)

#### Scan permissions (read)

- EC2 read for instances, volumes, addresses, regions, NAT gateways, load balancers.
- RDS read for db instances.
- Cost Explorer read for budget/projection.

#### Teardown permissions (write)

- EC2 terminate instances
- Delete volumes
- Release addresses
- Delete NAT gateways
- Delete load balancers
- Delete RDS instances

Recommendation: split into two Lambda roles later:

- `BloodhoundScanRole` (read-only)
- `BloodhoundTeardownRole` (write)

This is optional but strongly recommended once apply-mode is enabled.

---

### 11) Testing plan (minimal but real)

#### Local dry-run

- Run scan locally against a dev account/profile.
- Validate:
  - Region selection works
  - Resource counts look correct
  - Slack messages post to the intended channels

#### Lambda dry-run in AWS

- Invoke Lambda manually and via GitHub Actions.
- Validate CloudWatch logs and Slack outputs.

#### Apply-mode staged rollout

- Start with a “known safe” subset of resources (e.g., EIPs and unattached EBS volumes).
- Then add EC2 termination.
- Then add RDS deletion.

---

### 12) Milestones with checklists

#### v2.0 (refactor + config)

- [ ] Add env-driven Slack channels (scan vs alert)
- [ ] Add env-driven region configuration (`REGION_MODE`, `REGIONS`)
- [ ] Remove local-only AWS profile dependency in Lambda context
- [ ] Keep existing scan behavior and Slack scan summary working

#### v2.1 (more resources)

- [ ] Add scanners: EIP, NAT GW, EBS unattached, ELBv2
- [ ] Add pagination everywhere
- [ ] Normalize output into a shared resource schema
- [ ] Slack scan summary includes per-service counts

#### v2.2 (whitelist)

- [ ] Implement tag-based whitelist `bloodhound:keep=true`
- [ ] Optional: implement `KEEP_RESOURCE_IDS`
- [ ] Ensure whitelist affects teardown planning and apply-mode

#### v2.3 (teardown dry-run)

- [ ] Build “proposed deletions” plan
- [ ] Post proposed plan summary to alert channel
- [ ] Log full plan as JSON

#### v2.4 (teardown apply-mode)

- [ ] Guarded by `APPLY_CHANGES=true`
- [ ] Execute delete/terminate actions and post results
- [ ] Structured logs for every attempted action

#### v2.5 (budget + alerts)

- [ ] Cost Explorer cohort-to-date + dynamic monthly allowance
- [ ] Month-end run-rate projection
- [ ] Alert when over monthly allowance for `BUDGET_OVER_DAYS` consecutive days
- [ ] Post budget summary (and alert when triggered) to alert channel

---

### 13) Open questions (none required to proceed)

All previously open decisions are resolved with “simple defaults”, but these can be revisited later:

- Whether scan summaries should include whitelisted resources (counted vs hidden).
- Whether to split scan vs teardown into separate Lambdas/roles immediately or later.
