"""
bloodhound/types.py

Shared data structures used across scanners/whitelist/teardown.
Keeping these centralized avoids “dict soup” across the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ResourceRecord:
    service: str
    resource_type: str
    region: str
    id: str
    arn: Optional[str]
    state: str
    tags: dict[str, str]

    delete_supported: bool = False
    delete_action: Optional[str] = None
    delete_params: Optional[dict[str, Any]] = None


def resource_key(r: ResourceRecord) -> str:
    # Prefer ARN when present; else fall back to service/region/id.
    if r.arn:
        return r.arn
    return f"{r.service}:{r.region}:{r.id}"


