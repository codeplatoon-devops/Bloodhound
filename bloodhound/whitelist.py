"""
bloodhound/whitelist.py

Whitelist (keep) logic for Bloodhound v2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bloodhound.config import WhitelistConfig
from bloodhound.types import ResourceRecord, resource_display_name, resource_key


@dataclass(frozen=True)
class WhitelistMatch:
    reason: str


def _name_blob(record: ResourceRecord) -> str:
    parts = [record.id, resource_display_name(record)]
    parts.extend(record.tags.values())
    return " ".join(parts)


def match_whitelist(record: ResourceRecord, cfg: WhitelistConfig) -> WhitelistMatch | None:
    if record.id in cfg.keep_resource_ids:
        return WhitelistMatch(reason="KEEP_RESOURCE_IDS")
    if record.arn and record.arn in cfg.keep_resource_ids:
        return WhitelistMatch(reason="KEEP_RESOURCE_IDS")
    if resource_key(record) in cfg.keep_resource_ids:
        return WhitelistMatch(reason="KEEP_RESOURCE_IDS")

    for key, value in cfg.keep_tag_rules:
        tag_val = record.tags.get(key)
        if tag_val is not None and tag_val.strip().lower() == value.strip().lower():
            return WhitelistMatch(reason=f"tag `{key}={tag_val}`")

    blob = _name_blob(record)
    for pattern in cfg.keep_name_patterns:
        if re.search(pattern, blob, re.IGNORECASE):
            return WhitelistMatch(reason=f"name/tag matches `/{pattern}/i`")

    return None


def is_whitelisted(record: ResourceRecord, cfg: WhitelistConfig) -> bool:
    return match_whitelist(record, cfg) is not None


def filter_whitelisted(
    records: list[ResourceRecord], cfg: WhitelistConfig
) -> tuple[list[ResourceRecord], list[ResourceRecord], dict[str, WhitelistMatch]]:
    kept: list[ResourceRecord] = []
    candidates: list[ResourceRecord] = []
    reasons: dict[str, WhitelistMatch] = {}
    for r in records:
        match = match_whitelist(r, cfg)
        if match:
            kept.append(r)
            reasons[resource_key(r)] = match
        else:
            candidates.append(r)
    return candidates, kept, reasons


def format_whitelist_rules(cfg: WhitelistConfig) -> list[str]:
    lines: list[str] = []
    for key, value in cfg.keep_tag_rules:
        lines.append(f"- tag `{key}={value}`")
    for pattern in cfg.keep_name_patterns:
        lines.append(f"- name/tag regex `/{pattern}/i`")
    if cfg.keep_resource_ids:
        lines.append(f"- explicit IDs/ARNs: `{len(cfg.keep_resource_ids)}` configured")
    return lines
