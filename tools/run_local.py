"""
tools/run_local.py

Local runner for Bloodhound v2.

Writes a markdown report under `reports/` and prints sections to stdout.
Set SLACK_ENABLED=true in .env to also post to Slack.
"""

from __future__ import annotations

import json
import os
import sys

from bloodhound.app import run


def main() -> int:
    # Default local run: dry-run, stdout only.
    os.environ.setdefault("APPLY_CHANGES", "false")
    os.environ.setdefault("TEARDOWN_SIMULATE", "true")
    os.environ.setdefault("TEARDOWN_ALLOW_ALL", "false")
    os.environ.setdefault("SLACK_ENABLED", "false")
    os.environ.setdefault("BLOODHOUND_PRINT_REPORTS", "true")
    os.environ.setdefault("BLOODHOUND_REPORT_FORMAT", "markdown")
    os.environ.setdefault("BLOODHOUND_REPORT_DIR", "reports")

    mode = (sys.argv[1] if len(sys.argv) > 1 else "seek").strip()
    event: dict = {}
    if mode in {"seek", "seek_cost", "whitelist", "seek_destroy"}:
        event = {"source": "slack_command", "mode": mode}

    result = run(event=event, context=None)
    print("\n=== JSON summary ===")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
