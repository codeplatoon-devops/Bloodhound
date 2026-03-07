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
    # This ensures the Slack message clearly shows whether Bloodhound
    # is running in dry-run, simulation, or real deletion mode.
    if not apply_changes:
        # Safe default: planning mode only
        mode_text = "DRY RUN — No resources will be deleted"
    elif simulate:
        # Executor enabled but destructive calls are simulated
        mode_text = "SIMULATION — Deletion calls are simulated"
    else:
        # True destructive execution mode
        mode_text = "APPLY (DESTRUCTIVE) — Resources WILL be deleted"

    # Slack message header
    header = "*Bloodhound v2 — Teardown Plan*"

    # First lines of the Slack report
    lines = [
        header,
        _fmt_kv("mode", f"`{mode_text}`"),
        _fmt_kv("time_et", _et_now_time_str()),
        ""
    ]

    targets_filter_active = targets_filter_count > 0
    lines.append(_fmt_kv("simulate", f"`{str(simulate).lower()}`"))
    lines.append(_fmt_kv("targets_filter_active", f"`{str(targets_filter_active).lower()}`"))
    if targets_filter_active:
        lines.append(_fmt_kv("targets_filter_count", f"`{targets_filter_count}`"))
    lines.append(_fmt_kv("allow_all_targets", f"`{str(allow_all).lower()}`"))
    lines.append("")

    if not actions:
        lines.append("No deletions planned.")
        return "\n".join(lines)

    lines.append(_fmt_kv("planned_actions", f"`{len(actions)}`"))

    by_action = defaultdict(int)
    by_service = defaultdict(int)
    for a in actions:
        by_action[a.action] += 1
        by_service[a.service] += 1
    lines.append(_fmt_kv("planned_by_service", "`" + ", ".join([f"{k}={by_service[k]}" for k in sorted(by_service.keys())]) + "`"))
    lines.append(_fmt_kv("planned_by_action", "`" + ", ".join([f"{k}={by_action[k]}" for k in sorted(by_action.keys())]) + "`"))

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


