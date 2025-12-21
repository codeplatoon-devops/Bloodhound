"""
AWS Lambda entrypoint for Bloodhound v2.

Handler: lambda_function.lambda_handler
"""

from __future__ import annotations

from bloodhound.app import run


def lambda_handler(event, context):
    # Keep the handler extremely thin so the app remains testable locally.
    return run(event=event, context=context)


