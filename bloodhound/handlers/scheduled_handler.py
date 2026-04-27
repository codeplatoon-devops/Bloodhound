"""
scheduled_handler.py

Handles scheduled scan events for Bloodhound.

This handler is triggered when the Lambda function is invoked
by a scheduler (GitHub Actions cron or future EventBridge rule).
"""

def handle_scheduled_event(event, context=None):
    """
    Executes a scheduled Bloodhound scan.

    This function currently acts as a simple pass-through
    to the main Bloodhound application runtime.

    Parameters
    ----------
    event : dict
        Lambda event payload
    context : object
        Lambda execution context

    Returns
    -------
    dict
        Result of scheduled scan execution
    """

    print("Scheduled Bloodhound scan triggered")
    print("Event payload:", event)

    # Import here to avoid circular imports
    from bloodhound.app import run_scheduled_scan

    # Execute scheduled scan directly (no generic run path)
    result = run_scheduled_scan()

    return {
        "status": "scheduled_scan_executed",
        "result": result
    }