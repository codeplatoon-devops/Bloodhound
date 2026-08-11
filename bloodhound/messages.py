"""
bloodhound/messages.py

Report formatting for Bloodhound v2 (markdown-native; converted for Slack on post).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from bloodhound.budget import BudgetSnapshot
from bloodhound.config import WhitelistConfig
from bloodhound.controls import SpendingControlsSnapshot
from bloodhound.costs import MtdCostSnapshot, format_age, sum_forward_30d
from bloodhound.tables import md_table
from bloodhound.types import ResourceRecord, resource_display_name, resource_key
from bloodhound.whitelist import WhitelistMatch, format_whitelist_rules


SCANNED_RESOURCE_TYPES_ORDER: list[tuple[str, str]] = [
    ("ec2", "instance"),
    ("rds", "db_instance"),
    ("ec2", "elastic_ip"),
    ("ec2", "nat_gateway"),
    ("ec2", "ebs_volume"),
    ("elbv2", "load_balancer"),
]

_ET = ZoneInfo("America/New_York")


def _et_now_time_str() -> str:
    return datetime.now(_ET).strftime("%-I:%M %p ET")


def _header(title: str) -> list[str]:
    return [f"**{title}**", f"**time_et**: {_et_now_time_str()}", ""]


def _resource_type_label(r: ResourceRecord) -> str:
    return f"{r.service}.{r.resource_type}"


def _resource_detail(r: ResourceRecord) -> str:
    return str(
        r.metadata.get("instance_type")
        or r.metadata.get("instance_class")
        or r.metadata.get("size_gb")
        or ""
    )


def _resource_table_rows(
    records: list[ResourceRecord],
    *,
    extra_column: str | None = None,
    extra_value,
) -> list[list[object]]:
    rows: list[list[object]] = []
    for r in sorted(records, key=lambda x: (x.region, x.service, x.resource_type, x.id)):
        row = [
            r.region,
            _resource_type_label(r),
            r.id,
            resource_display_name(r),
            r.state or "",
            format_age(r.metadata),
            r.metadata.get("created_by") or "",
            _resource_detail(r),
        ]
        if extra_column:
            if callable(extra_value):
                row.append(extra_value(r))
            else:
                row.append(extra_value or "")
        rows.append(row)
    return rows


def format_cost_breakdown_message(
    mtd: MtdCostSnapshot,
    *,
    active_records: list[ResourceRecord] | None = None,
    candidate_records: list[ResourceRecord] | None = None,
    kept_records: list[ResourceRecord] | None = None,
) -> str:
    lines = _header("Bloodhound v2 — Cost Breakdown")

    lines.append(
        md_table(
            ["Field", "Value"],
            [
                ["Current month start", mtd.period_start.strftime("%Y-%m-%d")],
                ["Current month end", mtd.period_end_inclusive.strftime("%Y-%m-%d")],
                ["Period note", "MTD end date is today (inclusive); sourced from AWS Cost Explorer"],
            ],
        )
    )
    lines.append("")
    lines.append("**Current month — actual charges (MTD)**")
    lines.append("")
    lines.append(
        "Account-wide charges for the current calendar month to date. Includes deleted "
        "resources, VPC, data transfer, tax, and services Bloodhound does not scan."
    )
    lines.append("")

    if not mtd.by_service:
        lines.append("No Cost Explorer data returned.")
    else:
        total = mtd.total_usd
        rows: list[list[object]] = []
        for service, cost in mtd.by_service.items():
            if cost < 0.01:
                continue
            pct = (cost / total * 100) if total else 0
            rows.append([service, f"${cost:,.2f}", f"{pct:.0f}%"])
        rows.append(["**Total billed MTD**", f"**${total:,.2f}**", "**100%**"])
        lines.append(md_table(["Service", "MTD", "% of total"], rows))

    if active_records is not None:
        candidates = candidate_records or []
        kept = kept_records or []
        lines.append("")
        lines.append("**Forward rolling 30-day window (projected run-rate)**")
        lines.append("")
        lines.append(
            "Projected spend over the **next 30 days** if every resource Bloodhound found "
            "**live right now** stays running unchanged. Region-aware on-demand list prices "
            "(includes attached EBS) — excludes VPC, data transfer, tax, ELB LCUs, "
            "RIs/Savings Plans, and anything Bloodhound does not scan. **Not actual billing.**"
        )
        lines.append("")

        summary_rows: list[list[object]] = [
            [
                "All active scanned",
                len(active_records),
                f"~${sum_forward_30d(active_records):,.2f}/30d",
            ],
            [
                "Teardown candidates",
                len(candidates),
                f"~${sum_forward_30d(candidates):,.2f}/30d",
            ],
            [
                "Kept (whitelisted)",
                len(kept),
                f"~${sum_forward_30d(kept):,.2f}/30d",
            ],
        ]
        lines.append(md_table(["Group", "Resources", "Est. next 30d"], summary_rows))

        by_type: dict[tuple[str, str], list[ResourceRecord]] = defaultdict(list)
        for r in active_records:
            by_type[(r.service, r.resource_type)].append(r)

        type_rows: list[list[object]] = []
        for svc, rtype in SCANNED_RESOURCE_TYPES_ORDER:
            items = by_type.get((svc, rtype), [])
            if not items:
                continue
            type_rows.append([f"{svc}.{rtype}", len(items), f"~${sum_forward_30d(items):,.2f}/30d"])
        if type_rows:
            lines.append("")
            lines.append("**By resource type**")
            lines.append("")
            lines.append(md_table(["Type", "Resources", "Est. next 30d"], type_rows))

    return "\n".join(lines)


def format_scan_message(
    resources_by_region: dict[str, list[ResourceRecord]],
    whitelisted_by_region: dict[str, list[ResourceRecord]],
) -> str:
    lines = _header("Bloodhound v2 — Scan Summary")

    total_found = 0
    total_whitelisted = 0
    totals_candidates: dict[tuple[str, str], int] = defaultdict(int)
    totals_kept: dict[tuple[str, str], int] = defaultdict(int)

    region_rows: list[list[object]] = []
    for region in sorted(set(resources_by_region.keys()) | set(whitelisted_by_region.keys())):
        resources = resources_by_region.get(region, [])
        kept = whitelisted_by_region.get(region, [])
        total_found += len(resources)
        total_whitelisted += len(kept)
        for r in resources:
            totals_candidates[(r.service, r.resource_type)] += 1
        for r in kept:
            totals_kept[(r.service, r.resource_type)] += 1
        region_rows.append([region, len(resources), len(kept)])

    region_rows.append(["**Total**", f"**{total_found}**", f"**{total_whitelisted}**"])
    lines.append(md_table(["Region", "Teardown candidates", "Kept (whitelisted)"], region_rows))
    lines.append("")

    type_rows: list[list[object]] = []
    for svc, rtype in SCANNED_RESOURCE_TYPES_ORDER:
        c = totals_candidates.get((svc, rtype), 0)
        k = totals_kept.get((svc, rtype), 0)
        if c or k:
            type_rows.append([f"{svc}.{rtype}", c, k])
    if type_rows:
        lines.append("**By resource type**")
        lines.append("")
        lines.append(md_table(["Type", "Candidates", "Kept"], type_rows))

    return "\n".join(lines)


def format_resource_table_message(
    title: str,
    resources_by_region: dict[str, list[ResourceRecord]],
    *,
    extra_column: str | None = None,
    extra_value=None,
    match_reasons: dict[str, WhitelistMatch] | None = None,
) -> str:
    lines = _header(title)

    all_records = [r for region in sorted(resources_by_region) for r in resources_by_region[region]]
    if not all_records:
        lines.append("None.")
        return "\n".join(lines)

    if match_reasons and extra_column is None:
        extra_column = "Kept because"
        extra_value = lambda r: (match_reasons.get(resource_key(r)) or WhitelistMatch(True, "")).reason

    headers = ["Region", "Type", "ID", "Name", "State", "Age", "Created by", "Spec"]
    if extra_column:
        headers.append(extra_column)

    rows = _resource_table_rows(all_records, extra_column=extra_column, extra_value=extra_value)
    lines.append(f"**Count:** {len(all_records)}")
    lines.append("")
    lines.append(md_table(headers, rows))
    return "\n".join(lines)


def format_whitelist_config_message(cfg: WhitelistConfig) -> str:
    lines = _header("Bloodhound v2 — Whitelist Configuration")
    lines.append("Resources matching any rule below are **kept** and excluded from teardown.")
    lines.append("")

    rules = format_whitelist_rules(cfg)
    if rules:
        rule_rows = []
        for rule in rules:
            text = rule.lstrip("- ").strip()
            rule_rows.append([text])
        lines.append(md_table(["Rule"], rule_rows))
    else:
        lines.append("No whitelist rules configured.")

    lines.append("")
    lines.append("**Manage via Lambda env vars:** `KEEP_TAG_RULES`, `KEEP_NAME_PATTERNS`, `KEEP_RESOURCE_IDS`")
    return "\n".join(lines)


def format_spending_controls_message(snap: SpendingControlsSnapshot) -> str:
    """Prove spending limits are locked in place, and show for whom + what is blocked."""

    def usd(x: float) -> str:
        return f"${x:,.2f}"

    lines = _header("Bloodhound v2 — Spending Controls (proof of guardrails)")
    lines.append(f"**Account:** `{snap.account_id}`")
    lines.append("")

    # --- Verdict line: are limits actually locked? ---
    total_actions = len(snap.actions)
    locked = len(snap.locked_actions)
    active = sum(1 for a in snap.actions if a.active)
    if total_actions == 0:
        verdict = "⚠️ **No enforcement actions found — spending caps are alert-only, not locked.**"
    elif snap.all_locked:
        verdict = (
            f"✅ **All {total_actions} enforcement action(s) are AUTOMATIC (locked in place).** "
            f"{active} currently enforcing."
        )
    else:
        verdict = (
            f"⚠️ **{locked}/{total_actions} enforcement action(s) are AUTOMATIC (locked).** "
            f"The rest require manual approval to fire."
        )
    lines.append(verdict)
    lines.append("")

    # --- Spending caps ---
    lines.append("**Budget caps (spending limits)**")
    lines.append("")
    if not snap.caps:
        lines.append("No AWS Budgets configured.")
    else:
        rows: list[list[object]] = []
        for c in snap.caps:
            status = "🔴 OVER" if c.over else "🟢 within"
            rows.append(
                [
                    c.name,
                    f"{usd(c.limit_usd)}/{c.time_unit.lower()}",
                    usd(c.actual_usd),
                    f"{c.pct_used:.0f}%",
                    status,
                ]
            )
        lines.append(md_table(["Budget", "Limit", "Actual", "% used", "Status"], rows))
    lines.append("")

    # --- Enforcement (the lock) ---
    lines.append("**Enforcement — what is locked in place**")
    lines.append("")
    if not snap.actions:
        lines.append("No budget actions configured. Caps will alert but cannot block spend.")
    else:
        rows = []
        for a in snap.actions:
            lock = "🔒 AUTOMATIC" if a.locked else "🔓 manual"
            fired = "ENFORCING" if a.active else a.status
            thresh = (
                f"{a.threshold_value:.0f}%"
                if a.threshold_type.upper() == "PERCENTAGE"
                else usd(a.threshold_value)
            )
            rows.append(
                [
                    a.budget_name,
                    _action_type_label(a.action_type),
                    a.policy_name or a.policy_id or "—",
                    f"@ {thresh}",
                    lock,
                    fired,
                ]
            )
        lines.append(
            md_table(
                ["Budget", "Mechanism", "Policy", "Trips", "Approval", "State"],
                rows,
            )
        )

    # --- For what Groups / Users / OUs / Accounts ---
    lines.append("")
    lines.append("**Applies to (Groups, Users, OUs & Accounts)**")
    lines.append("")
    scope_rows: list[list[object]] = []
    for a in snap.actions:
        principals: list[str] = []
        if a.iam_groups:
            principals.append("groups: " + ", ".join(a.iam_groups))
        if a.iam_users:
            principals.append("users: " + ", ".join(a.iam_users))
        if a.iam_roles:
            principals.append("roles: " + ", ".join(a.iam_roles))
        if a.target_names:
            principals.append("scope: " + ", ".join(a.target_names))
        scope_rows.append([a.budget_name, a.policy_name or a.action_id, "; ".join(principals) or "—"])
    if scope_rows:
        lines.append(md_table(["Budget", "Policy", "Applies to"], scope_rows))
        lines.append("")
    if snap.iam_group_names:
        lines.append(
            f"_IAM principals subject to account/OU-scoped guardrails: "
            f"**{len(snap.iam_group_names)} groups** ({', '.join(snap.iam_group_names)}), "
            f"**{snap.iam_user_count} users**._"
        )
        lines.append("")

    # --- What is blocked ---
    lines.append("**What is blocked when a cap trips**")
    lines.append("")
    any_blocked = False
    for a in snap.actions:
        if not (a.denied_actions or a.ec2_allowed_instance_types):
            continue
        any_blocked = True
        header = f"_{a.policy_name or a.action_id}_"
        if a.policy_desc:
            header += f" — {a.policy_desc}"
        lines.append(header)
        if a.denied_actions:
            shown = a.denied_actions[:30]
            lines.append("- **Denied:** " + ", ".join(f"`{x}`" for x in shown))
            if len(a.denied_actions) > len(shown):
                lines.append(f"- _(+{len(a.denied_actions) - len(shown)} more denied actions)_")
        if a.ec2_allowed_instance_types:
            lines.append(
                "- **EC2 launches capped to:** "
                + ", ".join(f"`{x}`" for x in a.ec2_allowed_instance_types)
            )
        lines.append("")
    if not any_blocked:
        lines.append("No SCP/IAM deny rules resolved (insufficient Organizations/IAM read access, or none defined).")
        lines.append("")

    if snap.notes:
        lines.append("**Notes (degraded data)**")
        for n in snap.notes:
            lines.append(f"- {n}")

    return "\n".join(lines).rstrip()


def _action_type_label(action_type: str) -> str:
    return {
        "APPLY_SCP_POLICY": "SCP (org-wide)",
        "APPLY_IAM_POLICY": "IAM policy",
        "RUN_SSM_DOCUMENTS": "SSM (stop resources)",
    }.get(action_type, action_type)


def format_budget_message(b: BudgetSnapshot) -> str:
    def usd(x: float) -> str:
        return f"${x:,.2f}"

    lines = _header("Bloodhound v2 — Budget Summary")
    lines.append(
        md_table(
            ["Metric", "Value"],
            [
                ["Cohort start", b.cohort_start_yyyy_mm],
                ["Cohort budget", f"{usd(b.cohort_total_budget_usd)} over {b.cohort_length_months} months"],
                ["Remaining cohort budget", usd(b.remaining_cohort_budget_usd)],
                ["Dynamic monthly allowance", usd(b.dynamic_monthly_allowance_usd)],
                ["This month MTD", usd(b.current_month_to_date_spend_usd)],
                ["Projected month end", usd(b.projected_month_end_spend_usd)],
                ["Over budget threshold", str(b.over_budget_threshold_met).lower()],
            ],
        )
    )
    return "\n".join(lines)


def format_teardown_plan_message(
    candidates_by_region: dict[str, list[ResourceRecord]],
    apply_changes: bool,
    *,
    simulate: bool,
    targets_filter_count: int,
    allow_all: bool,
) -> str:
    header_title = (
        "Bloodhound v2 — Teardown Plan (APPLY MODE)"
        if apply_changes
        else "Bloodhound v2 — Teardown Plan (dry-run)"
    )
    all_candidates = [r for region in sorted(candidates_by_region) for r in candidates_by_region[region]]

    lines = _header(header_title)
    targets_filter_active = targets_filter_count > 0

    meta_rows = [
        ["Mode", "apply" if apply_changes else "dry-run"],
        ["Simulate deletes", str(simulate).lower()],
        ["Targets filter active", str(targets_filter_active).lower()],
        ["Allow all targets", str(allow_all).lower()],
    ]
    if targets_filter_active:
        meta_rows.append(["Targets filter count", str(targets_filter_count)])

    if not all_candidates:
        lines.extend(meta_rows[0:1])
        lines.append("")
        lines.append("No deletions planned.")
        return "\n".join(lines)

    by_action: dict[str, int] = defaultdict(int)
    by_service: dict[str, int] = defaultdict(int)
    for r in all_candidates:
        if r.delete_action:
            by_action[r.delete_action] += 1
        by_service[r.service] += 1

    meta_rows.extend(
        [
            ["Planned actions", str(len(all_candidates))],
            ["By service", ", ".join(f"{k}={by_service[k]}" for k in sorted(by_service))],
            ["By action", ", ".join(f"{k}={by_action[k]}" for k in sorted(by_action))],
        ]
    )
    lines.append(md_table(["Setting", "Value"], meta_rows))
    lines.append("")

    deletable = [r for r in all_candidates if r.delete_supported]
    manual = [r for r in all_candidates if not r.delete_supported]

    if deletable:
        by_region = {
            region: [r for r in candidates_by_region[region] if r.delete_supported]
            for region in sorted(candidates_by_region)
        }
        deletable_records = [r for region in sorted(by_region) for r in by_region[region]]
        lines.append("**Resources scheduled for teardown**")
        lines.append("")
        headers = ["Region", "Type", "ID", "Name", "State", "Age", "Created by", "Spec", "Action"]
        rows = _resource_table_rows(
            deletable_records,
            extra_column="Action",
            extra_value=lambda r: r.delete_action or "manual",
        )
        lines.append(md_table(headers, rows))

    if manual:
        lines.append("")
        lines.append(f"**Manual review required:** {len(manual)} resources without automated delete support")

    return "\n".join(lines).replace("\n\n\n", "\n\n").strip()


def format_teardown_result_message(attempted: int, succeeded: int, failed: int, simulated: int) -> str:
    lines = _header("Bloodhound v2 — Teardown Results")
    lines.append(
        md_table(
            ["Metric", "Count"],
            [
                ["Attempted", attempted],
                ["Succeeded", succeeded],
                ["Failed", failed],
                ["Simulated", simulated],
            ],
        )
    )
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Formatters ported from PR #2 (mmccla1n) so its services layer imports cleanly.
# These are used only by bloodhound/services/{status,scan}_service.py, which are
# NOT wired into the current worker (bloodhound.app.run). They are kept import-
# clean so the handlers/services architecture can be adopted later without a
# second merge. See docs/INTEGRATION_PR2_NOTES.md.
# ----------------------------------------------------------------------------

def _fmt_kv(key: str, value: str) -> str:
    return f"*{key}*: {value}"


def _display_resource(r: ResourceRecord) -> str:
    """Short, human-friendly one-liner for Slack."""
    name = r.tags.get("Name")
    name_part = f" (Name=`{name}`)" if name else ""
    return f"- `{r.region}` {r.service}.{r.resource_type} `{r.id}`{name_part}"


def format_whitelisted_resources_message(
    whitelisted_by_region: dict[str, list[ResourceRecord]],
    *,
    max_items: int = 50,
) -> str:
    """Separate report listing all whitelisted ("kept") resources, capped for Slack."""
    kept_all: list[ResourceRecord] = []
    for region in sorted(whitelisted_by_region.keys()):
        kept_all.extend(whitelisted_by_region.get(region, []))

    lines: list[str] = []
    lines.append("*Bloodhound v2 — Whitelisted Resources (Kept)*")
    lines.append(_fmt_kv("time_et", _et_now_time_str()))
    lines.append("")

    if not kept_all:
        lines.append("No whitelisted resources found.")
        return "\n".join(lines)

    lines.append(_fmt_kv("kept_total", f"`{len(kept_all)}`"))
    lines.append("")

    shown = 0
    for region in sorted(whitelisted_by_region.keys()):
        region_items = whitelisted_by_region.get(region, [])
        if not region_items:
            continue
        lines.append(f"*Region*: `{region}`")
        for r in region_items:
            if shown >= max_items:
                break
            lines.append(_display_resource(r))
            shown += 1
        if shown >= max_items:
            break
        lines.append("")

    if shown < len(kept_all):
        lines.append(f"... and `{len(kept_all) - shown}` more (increase max_items if needed)")

    return "\n".join(lines).rstrip()


def format_status_message(
    *,
    health: str,
    apply_changes: bool,
    simulate: bool,
    max_delete_count: int,
    expected_account_id: str,
    account_verified: bool,
    last_scan_resource_total: int,
    last_scan_whitelisted_total: int,
    regions_scanned: int,
) -> str:
    """Slack status dashboard used by PR #2's `/v2_status` command (not yet wired)."""
    if not apply_changes:
        mode = "DRY RUN"
    elif simulate:
        mode = "SIMULATION"
    else:
        mode = "DESTRUCTIVE APPLY"

    lines: list[str] = []
    lines.append("*Bloodhound v2 — System Status*")
    lines.append(_fmt_kv("system_health", f"`{health}`"))
    lines.append(_fmt_kv("time_et", _et_now_time_str()))
    lines.append("")
    lines.append("*System Mode*")
    lines.append(_fmt_kv("mode", f"`{mode}`"))
    lines.append(_fmt_kv("apply_changes", f"`{str(apply_changes).lower()}`"))
    lines.append(_fmt_kv("simulate", f"`{str(simulate).lower()}`"))
    lines.append("")
    lines.append("────────")
    lines.append("")
    lines.append("*Safety Guards*")
    lines.append(_fmt_kv("max_deletion_limit", f"`{max_delete_count}`"))
    lines.append(_fmt_kv("expected_account_id", f"`{expected_account_id}`"))
    lines.append(_fmt_kv("account_verified", f"`{str(account_verified).lower()}`"))

    return "\n".join(lines)
