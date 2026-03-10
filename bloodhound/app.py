"""
bloodhound/app.py

Orchestration entrypoint for Bloodhound v2.

Primary responsibilities:
- Load env config (via `config.py`)
- Scan resources (via `scanner/*`)
- Split candidates vs whitelisted/kept (via `whitelist.py`)
- Post Slack reports (via `messages.py` + `slack.py`)
- Optionally execute teardown actions (via `teardown/*`)

Used by:
- `lambda_function.lambda_handler` (AWS Lambda)
- `run_local.py` (local testing)
"""

from __future__ import annotations

import json
import os
from typing import Any

from bloodhound.aws import create_clients
from bloodhound.budget import compute_budget_snapshot
from bloodhound.config import load_config, validate_config
from bloodhound.messages import (
    format_budget_message,
    format_scan_message,
    format_teardown_plan_message,
    format_teardown_result_message,
    format_whitelisted_resources_message,
    format_status_message,
)
from bloodhound.scanner.regions import discover_regions, select_regions
from bloodhound.scanner.scan_all import scan_all
from bloodhound.slack import SlackNotifier
from bloodhound.teardown.executor import execute_actions
from bloodhound.teardown.planner import plan_deletions
from bloodhound.whitelist import filter_whitelisted
from bloodhound.types import resource_key

def compute_system_health(
    *,
    apply_changes: bool,
    allow_all_targets: bool,
    max_delete_count: int,
    budget_over_threshold: bool,
) -> str:
    """
    Compute a simple system health indicator for /v2_status.

    Args:
        apply_changes:
            Whether destructive mode is enabled.

        allow_all_targets:
            Whether teardown can target all resources.

        max_delete_count:
            Maximum number of deletions allowed per run.

        budget_over_threshold:
            Whether budget alert threshold has been triggered.

    Returns:
        str:
            Emoji indicator representing system health:
            🟢 healthy
            🟡 warning
            🔴 critical
    """

    if budget_over_threshold:
        return "🔴"

    if apply_changes and allow_all_targets:
        return "🔴"

    if apply_changes:
        return "🟡"

    if max_delete_count > 20:
        return "🟡"

    return "🟢"


def run(event: Any, context: Any) -> dict[str, Any]:
    """
    Main orchestration entrypoint for Lambda and local testing.
    Returns a small JSON-serializable summary for `aws lambda invoke`.
    """
    # Slack slash command worker mode:
    # apply teardown overrides FIRST, then load config so the same invocation uses the intended flags.
    if isinstance(event, dict) and event.get("source") == "slack_command":
        mode = (event.get("mode") or "").strip()
        # /seek = scan only (safe mode)
        # - performs resource scan
        # - generates teardown plan
        # - no deletion allowed
        if mode == "seek":
            os.environ["APPLY_CHANGES"] = "false"
            os.environ["TEARDOWN_SIMULATE"] = "true"
            os.environ["TEARDOWN_ALLOW_ALL"] = "false"

        # /seek_destroy_plan = preview teardown plan for all candidates
        # - still safe mode
        # - allows engineers to review what would be deleted
        elif mode == "seek_destroy_plan":
            os.environ["APPLY_CHANGES"] = "false"
            os.environ["TEARDOWN_SIMULATE"] = "true"
            os.environ["TEARDOWN_ALLOW_ALL"] = "true"

        # /seek_destroy_execute = destructive teardown execution
        # - executes real AWS deletion APIs
        # - deletes all non-whitelisted resources
        elif mode == "seek_destroy_execute":
            os.environ["APPLY_CHANGES"] = "true"
            os.environ["TEARDOWN_SIMULATE"] = "false"
            os.environ["TEARDOWN_ALLOW_ALL"] = "true"

    # Load configuration from env/.env and validate required fields.
    cfg = load_config()
    errors = validate_config(cfg)
    if errors:
        # Still return a structured error for Lambda invocations.
        return {"ok": False, "errors": errors}

    # AWS session/clients (Lambda uses its execution role; local can use AWS_PROFILE).
    clients = create_clients(profile=cfg.aws.profile)
    slack = None
    if cfg.slack.enabled:
        slack = SlackNotifier.from_token(
            bot_token=cfg.slack.bot_token,
            scan_channel_id=cfg.slack.scan_channel_id,
            alert_channel_id=cfg.slack.alert_channel_id,
        )

    # ------------------------------------------------------------
    # Status command (read-only system overview)
    # ------------------------------------------------------------
    if isinstance(event, dict) and event.get("source") == "slack_command":
        if event.get("mode") == "status":

            health = compute_system_health(
                apply_changes=cfg.teardown.apply_changes,
                allow_all_targets=cfg.teardown.allow_all_targets,
                max_delete_count=cfg.teardown.max_delete_count,
                budget_over_threshold=False,
            )

            status_msg = format_status_message(
                health=health,
                apply_changes=cfg.teardown.apply_changes,
                simulate=cfg.teardown.simulate,
                max_delete_count=cfg.teardown.max_delete_count,
                expected_account_id=getattr(cfg.aws, "expected_account_id", "not-configured"),
                account_verified=True,
                last_scan_resource_total=0,
                last_scan_whitelisted_total=0,
                regions_scanned=0,
            )

            if slack:
                slack.post_alert(status_msg)

            return {
                "ok": True,
                "mode": "status",
            }

    

    discovered = None
    if cfg.regions.mode == "discover":
        discovered = discover_regions(clients)
    regions = select_regions(cfg.regions.mode, cfg.regions.regions, discovered_regions=discovered)

    # 1) Scan
    raw_by_region = scan_all(clients, regions=regions, rds_final_snapshot=cfg.teardown.rds_final_snapshot)
    candidates_by_region: dict[str, list] = {}
    kept_by_region: dict[str, list] = {}

    for region, records in raw_by_region.items():
        # Whitelist is applied before teardown planning.
        candidates, kept = filter_whitelisted(records, cfg.whitelist)
        candidates_by_region[region] = candidates
        kept_by_region[region] = kept

    scan_msg = format_scan_message(candidates_by_region, kept_by_region)
    if slack:
        slack.post_scan(scan_msg)
        slack.post_scan(format_whitelisted_resources_message(kept_by_region))

    # 2) Budget
    budget_snapshot = compute_budget_snapshot(
        clients,
        cohort_start_yyyy_mm=cfg.budget.cohort_start_yyyy_mm,
        cohort_total_budget_usd=cfg.budget.cohort_total_budget_usd,
        cohort_length_months=cfg.budget.cohort_length_months,
        budget_over_days=cfg.budget.budget_over_days,
    )
    budget_msg = format_budget_message(budget_snapshot)
    # Always post budget summary to alert channel (keeps scan channel quieter).
    if slack:
        slack.post_alert(budget_msg)

    # 3) Teardown plan + optional apply
    all_candidates = [r for region in sorted(candidates_by_region.keys()) for r in candidates_by_region[region]]
    actions, _manual = plan_deletions(all_candidates)
    if slack:
        slack.post_alert(
            format_teardown_plan_message(
                actions,
                apply_changes=cfg.teardown.apply_changes,
                simulate=cfg.teardown.simulate,
                targets_filter_count=len(cfg.teardown.target_ids),
                allow_all=cfg.teardown.allow_all_targets,
            )
        )

    exec_summary = None
    if cfg.teardown.apply_changes:
        actions_to_execute = actions
        if cfg.teardown.target_ids:
            targets = cfg.teardown.target_ids
            actions_to_execute = [
                a
                for a in actions
                if (a.id in targets) or (a.arn and a.arn in targets) or (resource_key_from_action(a) in targets)
            ]

        exec_result = execute_actions(clients, actions_to_execute, simulate=cfg.teardown.simulate)
        exec_summary = {
            "attempted": exec_result.attempted,
            "succeeded": exec_result.succeeded,
            "failed": exec_result.failed,
            "simulated": exec_result.simulated,
            "failures": exec_result.failures[:20],
            "targets_filter": sorted(cfg.teardown.target_ids) if cfg.teardown.target_ids else None,
            "planned_actions_total": len(actions),
            "executed_actions_total": len(actions_to_execute),
            "allow_all_targets": cfg.teardown.allow_all_targets,
        }
        if slack:
            slack.post_alert(
                format_teardown_result_message(
                    attempted=exec_result.attempted,
                    succeeded=exec_result.succeeded,
                    failed=exec_result.failed,
                    simulated=exec_result.simulated,
                )
                + "\n"
                + json.dumps(exec_summary, indent=2)
            )

    # Return a compact summary to Lambda invoke callers.
    return {
        "ok": True,
        "regions": regions,
        "scan": {
            "candidates_total": sum(len(v) for v in candidates_by_region.values()),
            "kept_total": sum(len(v) for v in kept_by_region.values()),
        },
        "budget": {
            "projected_month_end_spend_usd": budget_snapshot.projected_month_end_spend_usd,
            "dynamic_monthly_allowance_usd": budget_snapshot.dynamic_monthly_allowance_usd,
            "over_budget_threshold_met": budget_snapshot.over_budget_threshold_met,
        },
        "teardown": {
            "apply_changes": cfg.teardown.apply_changes,
            "simulate": cfg.teardown.simulate,
            "targets_filter": sorted(cfg.teardown.target_ids) if cfg.teardown.target_ids else None,
            "planned_actions": len(actions),
            "execution": exec_summary,
        },
    }


def resource_key_from_action(a) -> str:
    if a.arn:
        return a.arn
    return f"{a.service}:{a.region}:{a.id}"


