"""
bloodhound/slack_commands.py

Slack slash command HTTP handler for Bloodhound v2.

Why this exists:
- Slack needs a public HTTPS endpoint for slash commands (/seek, /seek_destroy)
- Slack requires a fast response; we return immediately and then self-invoke the Lambda

Deployed via:
- Lambda Function URL (recommended) or API Gateway
"""

from __future__ import annotations

import base64
#import cmd
import hashlib
import hmac
import os
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

import boto3


@dataclass(frozen=True)
class SlackCommand:
    command: str
    text: str
    user_id: str
    channel_id: str


def is_slack_http_event(event: dict[str, Any]) -> bool:
    # Lambda Function URL / API Gateway both provide headers + body for HTTP requests.
    return isinstance(event, dict) and "headers" in event and "body" in event


def handle_slack_command_http(event: dict[str, Any]) -> dict[str, Any]:
    """
    Handles Slack slash commands via an HTTP-triggered Lambda (Function URL or API Gateway).

    Responds immediately (Slack requires fast response), then asynchronously invokes the
    same Lambda function to run the scan/teardown and post the normal Slack reports.
    """

    # -------------------------------------------------------------
    # Lightweight health endpoint for infrastructure validation
    # Allows curl checks without requiring Slack signature headers
    # -------------------------------------------------------------
    raw_path = event.get("rawPath") or event.get("path") or ""
    if raw_path == "/health":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json_dumps({
                "ok": True,
                "service": "BloodhoundLambdaV2",
                "status": "healthy"
            }),
        }

    # Slack request verification (signature + timestamp) is mandatory.
    signing_secret = os.environ.get("SLACK_SIGNING_SECRET", "").strip()
    if not signing_secret:
        return _http_text(500, "Missing SLACK_SIGNING_SECRET")

    headers = _lowercase_headers(event.get("headers") or {})
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    if not _verify_signature(headers, raw_body, signing_secret):
        return _http_text(401, "Invalid Slack signature")

    form = urllib.parse.parse_qs(raw_body, keep_blank_values=True)
    cmd = SlackCommand(
        command=_first(form, "command"),
        text=_first(form, "text"),
        user_id=_first(form, "user_id"),
        channel_id=_first(form, "channel_id"),
    )

    allowed_channels = _split_csv(os.environ.get("SLACK_ALLOWED_CHANNEL_IDS", ""))
    if allowed_channels and cmd.channel_id not in allowed_channels:
        # Slack surfaces non-200 responses as "dispatch_failed", so return 200 with a helpful message.
        return _http_text(200, "Not allowed in this channel.")

    # Route based on Slack's `command` field.
    # Non-destructive scan command
    if cmd.command in ("/seek", "/v2_seek"):
        _invoke_worker(mode="seek", cmd=cmd)
        return _http_text(200, "BloodHound is on the hunt...please stand by.")
    
    # ------------------------------------------------------------
    # Preview teardown plan (safe)
    # ------------------------------------------------------------
    if cmd.command in ("/v2_seek_destroy_plan",):
        _invoke_worker(mode="seek", cmd=cmd)
        return _http_text(200, "Generating teardown preview...please stand by.")
    
    # ------------------------------------------------------------
    # System status command
    # ------------------------------------------------------------
    if cmd.command in ("/v2_status",):
        _invoke_worker(mode="status", cmd=cmd)
        return _http_text(200, "Fetching Bloodhound system status...")

    # Destructive teardown command
    if cmd.command in ("/seek_destroy", "/v2_seek_destroy"):
        if not _destroy_allowed(cmd):
            # Slack surfaces non-200 responses as "dispatch_failed", so return 200 with a helpful message.
            return _http_text(200, "Not allowed. Use `/seek_destroy CONFIRM` (and ensure you are allowlisted).")
        _invoke_worker(mode="seek_destroy", cmd=cmd)
        return _http_text(200, "Uh oh someone let the dog out ---> Seek & Destroy Underway friendly assets whitelisted...please stand by.")

    # Unknown command (still return 200 so Slack doesn't show dispatch_failed).
    return _http_text(200, f"Unknown command: {cmd.command}")


def _invoke_worker(mode: str, cmd: SlackCommand) -> None:
    """
    Asynchronously invoke THIS lambda so the HTTP response can return immediately.
    The worker invocation will run the normal scan/teardown and post to Slack.
    """
    # We invoke THIS lambda asynchronously so Slack isn't waiting on a long scan.
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if not function_name:
        # Local runs won't have this; just no-op.
        return

    payload = {
        "source": "slack_command",
        "mode": mode,
        "slack": {
            "command": cmd.command,
            "text": cmd.text,
            "user_id": cmd.user_id,
            "channel_id": cmd.channel_id,
        },
    }

    boto3.client("lambda").invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=str.encode(json_dumps(payload)),
    )


def _destroy_allowed(cmd: SlackCommand) -> bool:
    """
    Super-safe by default:
    - Require CONFIRM token
    - Require user allowlist if configured
    """
    # Minimal "are you sure?" gate.
    confirm_token = os.environ.get("SLACK_DESTROY_CONFIRM_TOKEN", "CONFIRM").strip()
    if cmd.text.strip() != confirm_token:
        return False

    allowed_users = _split_csv(os.environ.get("SLACK_ALLOWED_USER_IDS", ""))
    if allowed_users and cmd.user_id not in allowed_users:
        return False

    return True


def _verify_signature(headers: dict[str, str], body: str, signing_secret: str) -> bool:
    ts = headers.get("x-slack-request-timestamp", "")
    sig = headers.get("x-slack-signature", "")
    if not ts or not sig:
        return False

    try:
        ts_int = int(ts)
    except ValueError:
        return False

    # Reject old requests (replay protection).
    if abs(int(time.time()) - ts_int) > 60 * 5:
        return False

    base = f"v0:{ts}:{body}".encode("utf-8")
    digest = hmac.new(signing_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, sig)


def _http_text(status_code: int, text: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "text/plain; charset=utf-8"},
        "body": text,
    }


def _lowercase_headers(headers: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if k is None or v is None:
            continue
        out[str(k).lower()] = str(v)
    return out


def _first(form: dict[str, list[str]], key: str) -> str:
    vals = form.get(key) or []
    return vals[0] if vals else ""


def _split_csv(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def json_dumps(obj: Any) -> str:
    # Tiny local wrapper to avoid importing json at module import time.
    import json

    return json.dumps(obj)


