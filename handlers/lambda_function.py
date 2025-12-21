"""
handlers/lambda_function.py

AWS Lambda entrypoint for Bloodhound v2.

This handler supports:
- Scheduled/manual invocations (runs full scan/report/optional teardown)
- Slack slash commands via Function URL (HTTP events)

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

    # 2) Normal invocation (CLI, schedule, async worker invocation).
    return run(event=event, context=context)


