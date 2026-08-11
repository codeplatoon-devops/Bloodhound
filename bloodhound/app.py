"""
bloodhound/app.py

Orchestration entrypoint for Bloodhound v2.
"""

from __future__ import annotations

import json
import os
from typing import Any

from bloodhound.attribution import enrich_creators
from bloodhound.aws import create_clients
from bloodhound.budget import compute_budget_snapshot
from bloodhound.config import load_config, validate_config
from bloodhound.controls import get_spending_controls_snapshot
from bloodhound.costs import enrich_records, get_mtd_cost_snapshot
from bloodhound.messages import (
    format_budget_message,
    format_cost_breakdown_message,
    format_resource_table_message,
    format_scan_message,
    format_spending_controls_message,
    format_teardown_plan_message,
    format_teardown_result_message,
    format_whitelist_config_message,
)
from bloodhound.scanner.regions import discover_regions, select_regions
from bloodhound.scanner.scan_all import scan_all
from bloodhound.slack import SlackNotifier
from bloodhound.teardown.executor import execute_actions
from bloodhound.teardown.planner import plan_deletions
from bloodhound.report_format import LocalReportWriter, markdown_to_slack
from bloodhound.whitelist import filter_whitelisted


def run(event: Any, context: Any) -> dict[str, Any]:
    if isinstance(event, dict) and event.get("source") == "slack_command":
        mode = (event.get("mode") or "").strip()
        # Guardrail management is its own flow — it does not scan/teardown.
        if mode == "guard":
            return _run_guard(event)
        os.environ["BLOODHOUND_RUN_MODE"] = mode
        if mode == "seek":
            os.environ["APPLY_CHANGES"] = "false"
            os.environ["TEARDOWN_SIMULATE"] = "true"
            os.environ["TEARDOWN_ALLOW_ALL"] = "false"
        elif mode == "seek_destroy":
            os.environ["APPLY_CHANGES"] = "true"
            os.environ["TEARDOWN_SIMULATE"] = "false"
            os.environ["TEARDOWN_ALLOW_ALL"] = "true"
        elif mode in {"whitelist", "seek_cost"}:
            os.environ["APPLY_CHANGES"] = "false"
            os.environ["TEARDOWN_SIMULATE"] = "true"
            os.environ["TEARDOWN_ALLOW_ALL"] = "false"

    cfg = load_config()
    errors = validate_config(cfg)
    if errors:
        return {"ok": False, "errors": errors}

    run_mode = os.environ.get("BLOODHOUND_RUN_MODE", "seek")
    whitelist_only = run_mode == "whitelist"
    cost_only = run_mode == "seek_cost"
    print_reports = _env_bool("BLOODHOUND_PRINT_REPORTS", False)
    report_format = os.environ.get("BLOODHOUND_REPORT_FORMAT", "markdown").strip().lower()
    report_dir = os.environ.get("BLOODHOUND_REPORT_DIR", "reports")
    attribution_enabled = _env_bool("ATTRIBUTION_ENABLED", True)

    local_report = LocalReportWriter(
        enabled=print_reports,
        output_format=report_format,
        report_dir=report_dir,
        mode=run_mode,
    )

    def _done(result: dict[str, Any]) -> dict[str, Any]:
        report_path = local_report.flush()
        if report_path:
            result["report_path"] = str(report_path)
            print(f"\nReport written to: {report_path}")
        return result

    clients = create_clients(profile=cfg.aws.profile)
    slack = None
    if cfg.slack.enabled:
        slack = SlackNotifier.from_token(
            bot_token=cfg.slack.bot_token,
            scan_channel_id=cfg.slack.scan_channel_id,
            alert_channel_id=cfg.slack.alert_channel_id,
        )

    def emit(title: str, body: str, *, channel: str = "scan") -> None:
        if print_reports:
            print(local_report.add(title, body))
        if not slack:
            return
        slack_body = markdown_to_slack(body)
        if channel == "alert":
            slack.post_alert(slack_body)
        else:
            slack.post_scan(slack_body)

    discovered = None
    if cfg.regions.mode == "discover":
        discovered = discover_regions(clients)
    regions = select_regions(cfg.regions.mode, cfg.regions.regions, discovered_regions=discovered)

    raw_by_region = scan_all(clients, regions=regions, rds_final_snapshot=cfg.teardown.rds_final_snapshot)
    candidates_by_region: dict[str, list] = {}
    kept_by_region: dict[str, list] = {}
    kept_reasons = {}

    for region, records in raw_by_region.items():
        enriched = enrich_records(records)
        if attribution_enabled:
            enriched = enrich_creators(clients, enriched)
        candidates, kept, reasons = filter_whitelisted(enriched, cfg.whitelist)
        candidates_by_region[region] = candidates
        kept_by_region[region] = kept
        kept_reasons.update(reasons)

    all_candidates = [r for region in sorted(candidates_by_region) for r in candidates_by_region[region]]
    all_kept = [r for region in sorted(kept_by_region) for r in kept_by_region[region]]
    all_active = all_candidates + all_kept
    mtd_snapshot = get_mtd_cost_snapshot(clients)

    emit("Whitelist config", format_whitelist_config_message(cfg.whitelist))
    emit(
        "Cost breakdown",
        format_cost_breakdown_message(
            mtd_snapshot,
            active_records=all_active,
            candidate_records=all_candidates,
            kept_records=all_kept,
        ),
    )
    controls_snapshot = get_spending_controls_snapshot(clients)
    emit("Spending controls", format_spending_controls_message(controls_snapshot))

    if cost_only:
        budget_snapshot = compute_budget_snapshot(
            clients,
            cohort_start_yyyy_mm=cfg.budget.cohort_start_yyyy_mm,
            cohort_total_budget_usd=cfg.budget.cohort_total_budget_usd,
            cohort_length_months=cfg.budget.cohort_length_months,
            budget_over_days=cfg.budget.budget_over_days,
        )
        emit("Budget summary", format_budget_message(budget_snapshot), channel="alert")
        return _done(
            {
                "ok": True,
                "mode": "seek_cost",
                "scan": {
                    "candidates_total": len(all_candidates),
                    "kept_total": sum(len(v) for v in kept_by_region.values()),
                },
                "budget": {
                    "projected_month_end_spend_usd": budget_snapshot.projected_month_end_spend_usd,
                    "dynamic_monthly_allowance_usd": budget_snapshot.dynamic_monthly_allowance_usd,
                },
            }
        )

    emit("Scan summary", format_scan_message(candidates_by_region, kept_by_region))

    actions, _manual = plan_deletions(all_candidates)
    emit(
        "Teardown plan",
        format_teardown_plan_message(
            candidates_by_region,
            apply_changes=cfg.teardown.apply_changes,
            simulate=cfg.teardown.simulate,
            targets_filter_count=len(cfg.teardown.target_ids),
            allow_all=cfg.teardown.allow_all_targets,
        ),
        channel="alert",
    )
    emit(
        "Whitelisted resources",
        format_resource_table_message(
            "Bloodhound v2 — Whitelisted Resources (Kept)",
            kept_by_region,
            match_reasons=kept_reasons,
        ),
    )

    if whitelist_only:
        return _done(
            {
                "ok": True,
                "mode": "whitelist",
                "scan": {
                    "candidates_total": len(all_candidates),
                    "kept_total": sum(len(v) for v in kept_by_region.values()),
                },
            }
        )

    budget_snapshot = compute_budget_snapshot(
        clients,
        cohort_start_yyyy_mm=cfg.budget.cohort_start_yyyy_mm,
        cohort_total_budget_usd=cfg.budget.cohort_total_budget_usd,
        cohort_length_months=cfg.budget.cohort_length_months,
        budget_over_days=cfg.budget.budget_over_days,
    )
    emit("Budget summary", format_budget_message(budget_snapshot), channel="alert")

    exec_summary = None
    if cfg.teardown.apply_changes:
        actions_to_execute = actions
        if cfg.teardown.target_ids:
            targets = cfg.teardown.target_ids
            actions_to_execute = [
                a
                for a in actions
                if (a.id in targets) or (a.arn and a.arn in targets) or (_action_key(a) in targets)
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
        emit(
            "Teardown results",
            format_teardown_result_message(
                attempted=exec_result.attempted,
                succeeded=exec_result.succeeded,
                failed=exec_result.failed,
                simulated=exec_result.simulated,
            )
            + "\n"
            + json.dumps(exec_summary, indent=2),
            channel="alert",
        )

    return _done(
        {
            "ok": True,
            "mode": run_mode,
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
    )


def _run_guard(event: Any) -> dict[str, Any]:
    """Handle a `/guard` slash command: parse, execute against AWS, post result to Slack."""
    from bloodhound.guard import GuardEngine, parse_command

    cfg = load_config()
    clients = create_clients(profile=cfg.aws.profile)

    text = ((event.get("slack") or {}).get("text") or "").strip()
    sub, args = parse_command(text)
    result_md = GuardEngine(clients).run(sub, args)

    print(result_md)
    if cfg.slack.enabled and cfg.slack.bot_token:
        slack = SlackNotifier.from_token(
            bot_token=cfg.slack.bot_token,
            scan_channel_id=cfg.slack.scan_channel_id,
            alert_channel_id=cfg.slack.alert_channel_id,
        )
        slack.post_alert(markdown_to_slack(result_md))

    return {"ok": True, "mode": "guard", "subcommand": sub}


def _action_key(a) -> str:
    if a.arn:
        return a.arn
    return f"{a.service}:{a.region}:{a.id}"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
