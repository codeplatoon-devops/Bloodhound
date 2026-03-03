"""
bloodhound/whitelist.py

Whitelist (keep) logic for Bloodhound v2.

Kept resources are excluded from teardown planning/execution.
Primary rule is a single tag (configurable via KEEP_TAG_KEY/KEEP_TAG_VALUE).
"""

from __future__ import annotations

from bloodhound.config import WhitelistConfig
from bloodhound.types import ResourceRecord, resource_key


def is_whitelisted(record: ResourceRecord, cfg: WhitelistConfig) -> bool:
    # Explicit allowlist (IDs/ARNs) first.
    if record.id in cfg.keep_resource_ids:
        return True
    if record.arn and record.arn in cfg.keep_resource_ids:
        return True
    if resource_key(record) in cfg.keep_resource_ids:
        return True

    # Tag-based keep (minimal, default).
    val = record.tags.get(cfg.keep_tag_key)
    if val is None:
        return False
    # Normalize for "TRUE", "true", etc.
    return val.strip().lower() == cfg.keep_tag_value.strip().lower()


def filter_whitelisted(records: list[ResourceRecord], cfg: WhitelistConfig) -> tuple[list[ResourceRecord], list[ResourceRecord]]:
    kept: list[ResourceRecord] = []
    candidates: list[ResourceRecord] = []
    for r in records:
        if is_whitelisted(r, cfg):
            kept.append(r)
        else:
            candidates.append(r)
    return candidates, kept


