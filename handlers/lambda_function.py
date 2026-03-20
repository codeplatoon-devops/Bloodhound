"""
handlers/lambda_function.py

AWS Lambda entrypoint for Bloodhound v2.

This handler supports:
- Slack slash commands via Function URL (HTTP events)
- Scheduled/manual invocations routed to dedicated handlers

Scheduled events are handled outside the generic run() path
to prevent recursive execution.

Terraform config points at:
- handlers.lambda_function.lambda_handler
"""

from __future__ import annotations

from bloodhound.app import run
from bloodhound.slack_commands import handle_slack_command_http, is_slack_http_event


def lambda_handler(event, context):
    # 1) Slack slash commands (HTTP events) -> immediate response + async self-invoke.
    if isinstance(event, dict) and is_slack_http_event(event):
        return handle_slack_command_http(event)
    
    # 2) Scheduled events (EventBridge or manual trigger).
    if isinstance(event, dict) and (event.get("detail-type") == "Scheduled Event" or event.get("source") == "scheduled"):
        from bloodhound.handlers.scheduled_handler import handle_scheduled_event
        return handle_scheduled_event(event, context)

    # 2) Normal default invocation (CLI / fallbacj, schedule, async worker invocation).
    return run(event=event, context=context)


