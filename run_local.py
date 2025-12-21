"""
Local runner for Bloodhound v2.

Usage:
  cd Bloodhound
  python run_local.py
"""

from __future__ import annotations

import json

from bloodhound.app import run


if __name__ == "__main__":
    result = run(event={}, context=None)
    print(json.dumps(result, indent=2, sort_keys=True))


