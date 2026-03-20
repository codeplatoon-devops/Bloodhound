""""
handlers/lambda_function.py

AWS Lambda entrypoint for Bloodhound v2.

This handler routes incoming events to explicit execution paths:

- Slack HTTP events (Function URL)
- Scheduled events (EventBridge or manual triggers)
- Default/manual invocations (scan, status, validation)

Each event type is routed to a dedicated handler or execution path
to ensure deterministic behavior and prevent recursive execution.

This file also standardizes CloudWatch logging, including:
- event type tagging (e.g., SCAN, STATUS, SCHEDULED)
- request ID tracing via context.aws_request_id

Terraform config points at:
- handlers.lambda_function.lambda_handler
"""

from __future__ import annotations

from bloodhound.app import run
from bloodhound.slack_commands import handle_slack_command_http, is_slack_http_event

def log_event(event_type, event, request_id=None):
    """
    Standardized CloudWatch log helper.

    Provides consistent log structure across all event types.
    Includes optional request_id so each Lambda invocation
    can be traced end-to-end in CloudWatch logs.

    Parameters
    ----------
    event_type : str
        Logical type of the event (e.g., "scan", "status", "scheduled", "slack")

    event : any
        Raw event payload received by the Lambda

    request_id : str, optional
        AWS Lambda request ID (context.aws_request_id) used for tracing
    """
    print("\n" + "=" * 60)

    # Include request_id if available for traceability
    if request_id:
        print("[BLOODHOUND][" + str(event_type).upper() + "][request_id=" + str(request_id) + "]")
    else:
        print("[BLOODHOUND][" + str(event_type).upper() + "]")

    print("=" * 60)
    print("Event received:", event)
    print("=" * 60 + "\n")


def lambda_handler(event, context):
    """
    AWS Lambda entrypoint for Bloodhound.

    Routes incoming events to the appropriate execution path:

    - Slack HTTP events → handled immediately
    - Scheduled events → routed to scheduled handler
    - Default events → processed through main pipeline (run)

    This routing ensures deterministic execution and prevents recursion.

    Parameters
    ----------
    event : dict
        Incoming Lambda event payload

        Examples:
            {"source": "scheduled"}
            {"detail-type": "Scheduled Event"}
            {"source": "scan"}

    context : object
        AWS Lambda context (used for request_id tracing)

        Example:
            context.aws_request_id -> "abc123-xyz"

    Returns
    -------
    dict
        Lambda response payload

        Example:
            {"ok": True, "scan": {...}, "budget": {...}}
    """


    # 1) Slack slash commands (HTTP events)
    #    Responds immediately; may trigger async follow-up work internally.
    if isinstance(event, dict) and is_slack_http_event(event):
        log_event("slack", event, context.aws_request_id)
        return handle_slack_command_http(event)
    
    # 2) Scheduled events (EventBridge or manual trigger).
    if isinstance(event, dict) and (event.get("detail-type") == "Scheduled Event" or event.get("source") == "scheduled"):
        from bloodhound.handlers.scheduled_handler import handle_scheduled_event
        log_event("scheduled", event, context.aws_request_id)
        return handle_scheduled_event(event, context)

    #3) Default invocation (manual CLI / GHA operations such as scan/status).
    # Determine event type for logging.
    # Most events include a "source" field (scan, status, etc.).
    # If missing or event is not a dict, label as "unknown".
    if isinstance(event, dict):
        event_type = event.get("source", "unknown")
    else:
        event_type = "unknown"

    log_event(event_type, event, context.aws_request_id)
    
    return run(event=event, context=context)


