"""
tools/run_local.py

Local runner for Bloodhound v2 (uses `.env` + your AWS_PROFILE).
This is the fastest way to validate config + Slack output before deploying to Lambda.
"""

from __future__ import annotations

import json

from bloodhound.app import run


if __name__ == "__main__":
    result = run(event={}, context=None)
    print(json.dumps(result, indent=2, sort_keys=True))


