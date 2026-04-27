"""
bloodhound/messages.py

Slack message formatting for Bloodhound v2.

This file contains ONLY formatting/aggregation logic (no AWS calls).
It is used by `app.py` right before posting via `slack.py`.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from bloodhound.budget import BudgetSnapshot
from bloodhound.teardown.planner import PlannedAction
from bloodhound.types import ResourceRecord


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
    # Example: 4:24 PM ET
    return datetime.now(_ET).strftime("%-I:%M %p ET")


def _fmt_kv(key: str, value: str) -> str:
    return f"*{key}*: {value}"


def _fmt_counts_line(prefix: str, counts: dict[tuple[str, str], int]) -> str:
    parts = [f"{svc}.{rtype}={counts[(svc, rtype)]}" for svc, rtype in SCANNED_RESOURCE_TYPES_ORDER]
    return f"{prefix} {', '.join(parts)}"


def _display_resource(r: ResourceRecord) -> str:
    """
    Short, human-friendly one-liner for Slack.
    """
    name = r.tags.get("Name")
    name_part = f" (Name=`{name}`)" if name else ""
    return f"- `{r.region}` {r.service}.{r.resource_type} `{r.id}`{name_part}"


def format_scan_message(
    resources_by_region: dict[str, list[ResourceRecord]],
    whitelisted_by_region: dict[str, list[ResourceRecord]],
) -> str:
    lines: list[str] = []
    lines.append("*Bloodhound v2 — Scan Summary*")
    lines.append(_fmt_kv("time_et", _et_now_time_str()))

    total_found = 0
    total_whitelisted = 0

    # Totals by (service, resource_type) across all regions.
    totals_candidates: dict[tuple[str, str], int] = defaultdict(int)
    totals_kept: dict[tuple[str, str], int] = defaultdict(int)

    for region in sorted(resources_by_region.keys()):
        resources = resources_by_region[region]
        kept = whitelisted_by_region.get(region, [])

        total_found += len(resources)
        total_whitelisted += len(kept)

        type_counts = defaultdict(int)
        for r in resources:
            type_counts[(r.service, r.resource_type)] += 1
            totals_candidates[(r.service, r.resource_type)] += 1

        kept_type_counts = defaultdict(int)
        for r in kept:
            kept_type_counts[(r.service, r.resource_type)] += 1
            totals_kept[(r.service, r.resource_type)] += 1

        lines.append("")
        lines.append(f"*Region*: `{region}`")
        lines.append(f"*Counts*: candidates `{len(resources)}` | kept `{len(kept)}`")
        lines.append(f"- {_fmt_counts_line('Candidates:', type_counts)}")
        lines.append(f"- {_fmt_counts_line('Kept:', kept_type_counts)}")

    lines.append("")
    lines.append("*Totals*")
    lines.append(f"*Counts*: candidates `{total_found}` | kept `{total_whitelisted}`")
    lines.append(f"- {_fmt_counts_line('Candidates:', totals_candidates)}")
    lines.append(f"- {_fmt_counts_line('Kept:', totals_kept)}")
    return "\n".join(lines)


def format_whitelisted_resources_message(
    whitelisted_by_region: dict[str, list[ResourceRecord]],
    *,
    max_items: int = 50,
) -> str:
    """
    Separate report listing all whitelisted ("kept") resources.
    Capped to max_items to keep Slack readable.
    """
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


def format_budget_message(b: BudgetSnapshot) -> str:
    def usd(x: float) -> str:
        return f"${x:,.2f}"

    lines: list[str] = []
    lines.append("*Bloodhound v2 — Budget Summary*")
    lines.append(_fmt_kv("time_et", _et_now_time_str()))
    lines.append("")
    lines.append("*Cohort*")
    lines.append(f"- {_fmt_kv('start', f'`{b.cohort_start_yyyy_mm}`')}")
    lines.append(f"- {_fmt_kv('total_budget', f'`{usd(b.cohort_total_budget_usd)}` over `{b.cohort_length_months}` months')}")
    lines.append(f"- {_fmt_kv('to_date_spend', f'`{usd(b.cohort_to_date_spend_usd)}`')}")
    lines.append(f"- {_fmt_kv('remaining_budget', f'`{usd(b.remaining_cohort_budget_usd)}`')}")
    lines.append(f"- {_fmt_kv('remaining_months', f'`{b.remaining_months}`')}")
    lines.append(f"- {_fmt_kv('monthly_allowance', f'`{usd(b.dynamic_monthly_allowance_usd)}`')}")
    lines.append("")
    lines.append("*This month*")
    lines.append(f"- {_fmt_kv('month_to_date', f'`{usd(b.current_month_to_date_spend_usd)}`')}")
    lines.append(f"- {_fmt_kv('projected_month_end', f'`{usd(b.projected_month_end_spend_usd)}`')}")
    lines.append(f"- {_fmt_kv('over_budget_days_required', f'`{b.budget_over_days}`')}")
    lines.append(f"- {_fmt_kv('over_budget_threshold_met', f'`{str(b.over_budget_threshold_met).lower()}`')}")
    return "\n".join(lines)


def format_teardown_plan_message(
    actions: list[PlannedAction],
    apply_changes: bool,
    *,
    simulate: bool,
    targets_filter_count: int,
    allow_all: bool,
) -> str:
    # Determine execution mode for Slack output.
    # This ensures the Header and Slack messages clearly shows whether Bloodhound
    # is running in dry-run, simulation, or real deletion mode.
    if not apply_changes:
        header = "*Bloodhound v2 — Teardown Plan (DRY RUN)*"
        mode_text = "DRY RUN — No AWS resources will be deleted"

    elif simulate:
        header = "*Bloodhound v2 — Teardown Plan (SIMULATION)*"
        mode_text = "SIMULATION — Deletion calls are simulated"

    else:
        header = "*Bloodhound v2 — Teardown Plan (DESTRUCTIVE APPLY)*"
        mode_text = "APPLY (DESTRUCTIVE) — Resources WILL be deleted"

    # Slack message header
    #header = "*Bloodhound v2 — Teardown Plan*"

    # First lines of the Slack report
    lines = [
        header,
        _fmt_kv("mode", f"`{mode_text}`"),
        _fmt_kv("time_et", _et_now_time_str()),
        ""
    ]

    # Extra safety visibility for dry-run
    if not apply_changes:
        lines.append("🚨 *DRY RUN MODE* — No AWS resources will be deleted")

    targets_filter_active = targets_filter_count > 0
    lines.append(_fmt_kv("simulate", f"`{str(simulate).lower()}`"))
    lines.append(_fmt_kv("targets_filter_active", f"`{str(targets_filter_active).lower()}`"))
    if targets_filter_active:
        lines.append(_fmt_kv("targets_filter_count", f"`{targets_filter_count}`"))
    lines.append(_fmt_kv("allow_all_targets", f"`{str(allow_all).lower()}`"))
    lines.append("")

    # Visual divider between execution configuration and deletion summary
    lines.append("────────")
    lines.append("")

    if not actions:
        lines.append("No deletions planned.")
        return "\n".join(lines)

    # Total number of API operations Bloodhound plans to execute
    lines.append(_fmt_kv("planned_actions", f"`{len(actions)}`"))
    lines.append("")

    # Aggregate counts by AWS action, service, and region
    by_action = defaultdict(int)
    by_service = defaultdict(int)
    by_region = defaultdict(int)

    # Count how many planned actions belong to each service, API action, and region
    for a in actions:
        by_action[a.action] += 1
        by_service[a.service] += 1
        by_region[a.region] += 1

    # ------------------------------------------------------------
    # Regions most affected by the teardown plan
    # ------------------------------------------------------------
    lines.append("*Top Regions Affected*")

    # Sort regions by number of actions (largest first)
    for region, count in sorted(by_region.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- `{region}`: `{count}`")

    lines.append("")


    # ------------------------------------------------------------
    # Summary by AWS service (ec2, elbv2, rds, etc.) affected by the teardown plan.
    # ------------------------------------------------------------
    lines.append("*Services affected*")
    #lines.append("`" + ", ".join([f"{k}={by_service[k]}" for k in sorted(by_service.keys())]) + "`")
    # Render services vertically for easier Slack scanning
    for svc in sorted(by_service.keys()):
        lines.append(f"- `{svc}`: `{by_service[svc]}`")

    lines.append("")


    # ------------------------------------------------------------
    # Summary by AWS API action (terminate, delete, release, etc.)
    # ------------------------------------------------------------
    lines.append("*Planned Actions*")

    # Render each action count on its own line for easier Slack scanning
    for action in sorted(by_action.keys()):
        lines.append(f"- `{action}`: `{by_action[action]}`")

    # Keep Slack output short: show a small sample.
    sample = actions[:15]
    lines.append("")
    lines.append("*Sample (first 15)*")
    for a in sample:
        lines.append(f"- `{a.region}` {a.service}.{a.resource_type} `{a.id}` → `{a.action}`")
    if len(actions) > len(sample):
        lines.append(f"- ... and `{len(actions) - len(sample)}` more")

    return "\n".join(lines)


def format_teardown_result_message(attempted: int, succeeded: int, failed: int, simulated: int) -> str:
    lines: list[str] = []
    lines.append("*Bloodhound v2 — Teardown Results*")
    lines.append(_fmt_kv("time_et", _et_now_time_str()))
    lines.append("")
    lines.append(_fmt_kv("attempted", f"`{attempted}`"))
    lines.append(_fmt_kv("succeeded", f"`{succeeded}`"))
    lines.append(_fmt_kv("failed", f"`{failed}`"))
    lines.append(_fmt_kv("simulated", f"`{simulated}`"))
    return "\n".join(lines)

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
):
    """
    Format a Slack status report for the Bloodhound system.

    This message is used by the `/v2_status` Slack command to provide
    engineers with a quick operational overview of the system state.

    Args:
    health:
        System health indicator used by the operational dashboard.

        Possible values:
        🟢 healthy
        🟡 warning
        🔴 critical

        This value is computed in `app.py` based on destructive mode,
        deletion safety limits, and other operational signals.

    apply_changes:
        Whether Bloodhound is allowed to perform destructive operations.

    simulate:
        Whether teardown operations are currently simulated.

    max_delete_count:
        Maximum number of resources allowed to be deleted in a single run.

    expected_account_id:
        AWS account ID that Bloodhound expects to operate within.

    account_verified:
        Whether the runtime AWS account matches the expected account ID.

    last_scan_resource_total:
        Total number of resources discovered during the most recent scan.

    last_scan_whitelisted_total:
        Number of resources that were protected (whitelisted) during the scan.

    regions_scanned:
        Total number of AWS regions included in the most recent scan.

    Returns:
        Slack-formatted string representing the Bloodhound operational
        status dashboard used by the `/v2_status` command.
    """

    # ------------------------------------------------------------
    # Determine execution mode
    # ------------------------------------------------------------
    if not apply_changes:
        mode = "DRY RUN"
    elif simulate:
        mode = "SIMULATION"
    else:
        mode = "DESTRUCTIVE APPLY"

    candidate_for_deletion = last_scan_resource_total - last_scan_whitelisted_total

    lines: list[str] = []

    lines.append("*Bloodhound v2 — System Status*")
    lines.append(_fmt_kv("system_health", f"`{health}`"))
    lines.append(_fmt_kv("time_et", _et_now_time_str()))
    lines.append("")

    # ------------------------------------------------------------
    # System mode
    # ------------------------------------------------------------
    lines.append("*System Mode*")
    lines.append(_fmt_kv("mode", f"`{mode}`"))
    lines.append(_fmt_kv("apply_changes", f"`{str(apply_changes).lower()}`"))
    lines.append(_fmt_kv("simulate", f"`{str(simulate).lower()}`"))
    lines.append("")

    lines.append("────────")
    lines.append("")

    """
    # ------------------------------------------------------------
    # Last scan summary
    # ------------------------------------------------------------
    lines.append("*Last Scan Summary*")
    lines.append(_fmt_kv("regions_scanned", f"`{regions_scanned}`"))
    lines.append(_fmt_kv("resources_found", f"`{last_scan_resource_total}`"))
    lines.append(_fmt_kv("resources_whitelisted", f"`{last_scan_whitelisted_total}`"))
    lines.append(_fmt_kv("resources_candidate_for_deletion", f"`{candidate_for_deletion}`"))
    lines.append("")

    lines.append("────────")
    lines.append("")"""

    # ------------------------------------------------------------
    # Safety guards
    # ------------------------------------------------------------
    lines.append("*Safety Guards*")
    lines.append(_fmt_kv("max_deletion_limit", f"`{max_delete_count}`"))
    lines.append(_fmt_kv("expected_account_id", f"`{expected_account_id}`"))
    lines.append(_fmt_kv("account_verified", f"`{str(account_verified).lower()}`"))

    return "\n".join(lines)


