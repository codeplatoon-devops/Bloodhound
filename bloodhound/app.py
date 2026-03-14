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
from bloodhound.handlers.slack_handler import handle_slack_event
from bloodhound.handlers.validation_handler import handle_validation_event
from bloodhound.handlers.scheduled_handler import handle_scheduled_event
from bloodhound.services.status_service import handle_status_command
from bloodhound.services.scan_service import scan_resources
from bloodhound.services.budget_service import compute_budget
from bloodhound.services.teardown_service import plan_teardown, execute_teardown

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

def resource_key_from_action(a) -> str:
    if a.arn:
        return a.arn
    return f"{a.service}:{a.region}:{a.id}"


def execute_pipeline(event):
    """
    Core Bloodhound operational pipeline.

    This function performs the full orchestration workflow:

        1. Load configuration
        2. Create AWS clients
        3. Scan resources across regions
        4. Apply whitelist filtering
        5. Generate Slack scan reports
        6. Compute budget projections
        7. Plan teardown actions
        8. Optionally execute deletion actions

    Separating this pipeline from the Lambda entrypoint keeps the
    application architecture maintainable as the system grows.
    """

    print("Bloodhound pipeline started")
    print("Event:", json.dumps(event))

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

    status_response = handle_status_command(event, cfg, slack, compute_system_health)
    if status_response:
        return status_response

    scan_result = scan_resources(cfg, clients, slack)

    budget_snapshot = compute_budget(cfg, clients, slack)

    actions = plan_teardown(cfg, event, scan_result["all_candidates"], slack)

    exec_summary = execute_teardown(
        cfg,
        event,
        clients,
        actions,
        slack,
        resource_key_from_action
    )

    result = {
        "ok": True,
        "regions": scan_result["regions"],
        "scan": {
            "candidates_total": sum(len(v) for v in scan_result["candidates_by_region"].values()),
            "kept_total": sum(len(v) for v in scan_result["kept_by_region"].values()),
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

    # ------------------------------------------------------------
    # DEBUG LOGGING
    # ------------------------------------------------------------
    print("Bloodhound pipeline completed")

    print("Scan summary:")
    print(
        json.dumps(
            {
                "candidates_total": result["scan"]["candidates_total"],
                "kept_total": result["scan"]["kept_total"],
            },
            indent=2,
        )
    )

    print("Budget summary:")
    print(
        json.dumps(
            {
                "projected_month_end_spend_usd": result["budget"]["projected_month_end_spend_usd"],
                "dynamic_monthly_allowance_usd": result["budget"]["dynamic_monthly_allowance_usd"],
                "over_budget_threshold_met": result["budget"]["over_budget_threshold_met"],
            },
            indent=2,
        )
    )

    print("Teardown summary:")
    print(
        json.dumps(
            {
                "apply_changes": result["teardown"]["apply_changes"],
                "simulate": result["teardown"]["simulate"],
                "planned_actions": result["teardown"]["planned_actions"],
            },
            indent=2,
        )
    )

    return result


def run(event, context):
    """
    Main orchestration entrypoint for Lambda and local testing.
    Returns a small JSON-serializable summary for `aws lambda invoke`.

    The run() function now acts as a thin orchestrator that prepares
    the runtime environment and then delegates execution to the
    Bloodhound pipeline.
    """

    # ------------------------------------------------------------
    # Prepare runtime environment based on invocation source
    #
    # Slack commands and validation harnesses modify environment
    # variables so the pipeline behaves in the correct mode.
    # ------------------------------------------------------------

    # Determine the event source safely.
    # If the event is not a dictionary (which can happen in some Lambda test cases),
    # we default the source to None so the routing logic below will simply skip.
    source = event.get("source") if isinstance(event, dict) else None

    # ------------------------------------------------------------
    # Route the event to the appropriate handler
    # ------------------------------------------------------------

    if source == "slack_command":
        handle_slack_event(event)

    elif source == "validation":
        handle_validation_event(event)

    elif source == "scheduled":
        handle_scheduled_event(event)

    # ------------------------------------------------------------
    # Execute the core Bloodhound pipeline
    # ------------------------------------------------------------

    return execute_pipeline(event)





