"""
bloodhound/types.py

Shared data structures used across scanners/whitelist/teardown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    metadata: dict[str, Any] = field(default_factory=dict)

    delete_supported: bool = False
    delete_action: Optional[str] = None
    delete_params: Optional[dict[str, Any]] = None


def resource_key(r: ResourceRecord) -> str:
    if r.arn:
        return r.arn
    return f"{r.service}:{r.region}:{r.id}"


def resource_display_name(r: ResourceRecord) -> str:
    return r.tags.get("Name") or r.id
