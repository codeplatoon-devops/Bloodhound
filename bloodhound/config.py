"""
bloodhound/config.py

Configuration loader for Bloodhound v2.

Reads configuration from environment variables and (for local runs) a `.env` file.
All non-code “knobs” (channels, regions, whitelist tag, teardown flags, cohort config)
should live here so the rest of the code stays clean.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value != "" else default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "t", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _split_csv(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _parse_tag_rules(raw: Optional[str], legacy_key: str, legacy_value: str) -> list[tuple[str, str]]:
    rules: list[tuple[str, str]] = []
    for item in _split_csv(raw):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key, value = key.strip(), value.strip()
        if key and value:
            rules.append((key, value))
    if not rules:
        rules.append((legacy_key, legacy_value))
    return rules


def _split_patterns(raw: Optional[str]) -> list[str]:
    return [x.strip() for x in _split_csv(raw) if x.strip()]


@dataclass(frozen=True)
class SlackConfig:
    bot_token: str
    scan_channel_id: str
    alert_channel_id: str
    enabled: bool


@dataclass(frozen=True)
class RegionConfig:
    mode: str  # explicit | discover
    regions: list[str]


@dataclass(frozen=True)
class WhitelistConfig:
    keep_tag_rules: list[tuple[str, str]]
    keep_name_patterns: list[str]
    keep_resource_ids: set[str]


@dataclass(frozen=True)
class TeardownConfig:
    apply_changes: bool
    simulate: bool
    target_ids: set[str]
    allow_all_targets: bool
    teardown_mode: str  # delete (future: stop)
    rds_final_snapshot: bool


@dataclass(frozen=True)
class BudgetConfig:
    cohort_start_yyyy_mm: str
    cohort_total_budget_usd: float
    cohort_length_months: int
    budget_over_days: int


@dataclass(frozen=True)
class AwsConfig:
    # Optional local-only convenience; Lambda ignores this unless you explicitly set it.
    profile: Optional[str]


@dataclass(frozen=True)
class AppConfig:
    slack: SlackConfig
    regions: RegionConfig
    whitelist: WhitelistConfig
    teardown: TeardownConfig
    budget: BudgetConfig
    aws: AwsConfig


def load_config() -> AppConfig:
    # Load local .env for developer convenience. In Lambda, env vars are provided by the runtime.
    load_dotenv(override=False)

    slack_enabled = _env_bool("SLACK_ENABLED", True)
    slack_bot_token = _env("SLACK_BOT_TOKEN") or ""
    # Backwards compat with v1 env var:
    v1_channel_id = _env("CHANNEL_ID")
    scan_channel_id = _env("SLACK_SCAN_CHANNEL_ID") or v1_channel_id or ""
    alert_channel_id = _env("SLACK_ALERT_CHANNEL_ID") or scan_channel_id

    region_mode = (_env("REGION_MODE", "explicit") or "explicit").lower()
    regions = _split_csv(_env("REGIONS"))

    keep_tag_key = _env("KEEP_TAG_KEY", "bloodhound:keep") or "bloodhound:keep"
    keep_tag_value = _env("KEEP_TAG_VALUE", "true") or "true"
    keep_tag_rules = _parse_tag_rules(_env("KEEP_TAG_RULES"), keep_tag_key, keep_tag_value)
    keep_name_patterns = _split_patterns(
        _env(
            "KEEP_NAME_PATTERNS",
            "buffalo,fullstack,vetlaunch,dont-touch,do-not-touch,dont_touch",
        )
    )
    keep_resource_ids = set(_split_csv(_env("KEEP_RESOURCE_IDS")))

    apply_changes = _env_bool("APPLY_CHANGES", False)
    simulate = _env_bool("TEARDOWN_SIMULATE", False)
    target_ids = set(_split_csv(_env("TEARDOWN_TARGET_IDS")))
    allow_all_targets = _env_bool("TEARDOWN_ALLOW_ALL", False)
    teardown_mode = (_env("TEARDOWN_MODE", "delete") or "delete").lower()
    rds_final_snapshot = _env_bool("RDS_FINAL_SNAPSHOT", False)

    cohort_start_yyyy_mm = _env("COHORT_START_YYYY_MM", "") or ""
    cohort_total_budget_usd = _env_float("COHORT_TOTAL_BUDGET_USD", 3000.0)
    cohort_length_months = _env_int("COHORT_LENGTH_MONTHS", 7)
    budget_over_days = max(1, _env_int("BUDGET_OVER_DAYS", 2))

    profile = _env("AWS_PROFILE")

    return AppConfig(
        slack=SlackConfig(
            bot_token=slack_bot_token,
            scan_channel_id=scan_channel_id,
            alert_channel_id=alert_channel_id,
            enabled=slack_enabled,
        ),
        regions=RegionConfig(mode=region_mode, regions=regions),
        whitelist=WhitelistConfig(
            keep_tag_rules=keep_tag_rules,
            keep_name_patterns=keep_name_patterns,
            keep_resource_ids=keep_resource_ids,
        ),
        teardown=TeardownConfig(
            apply_changes=apply_changes,
            simulate=simulate,
            target_ids=target_ids,
            allow_all_targets=allow_all_targets,
            teardown_mode=teardown_mode,
            rds_final_snapshot=rds_final_snapshot,
        ),
        budget=BudgetConfig(
            cohort_start_yyyy_mm=cohort_start_yyyy_mm,
            cohort_total_budget_usd=cohort_total_budget_usd,
            cohort_length_months=cohort_length_months,
            budget_over_days=budget_over_days,
        ),
        aws=AwsConfig(profile=profile),
    )


def validate_config(cfg: AppConfig) -> list[str]:
    errors: list[str] = []

    if cfg.slack.enabled:
        if not cfg.slack.bot_token:
            errors.append("Missing SLACK_BOT_TOKEN")
        if not cfg.slack.scan_channel_id:
            errors.append("Missing SLACK_SCAN_CHANNEL_ID (or CHANNEL_ID for v1 compatibility)")

    if cfg.regions.mode not in {"explicit", "discover"}:
        errors.append("REGION_MODE must be 'explicit' or 'discover'")
    if cfg.regions.mode == "explicit" and not cfg.regions.regions:
        errors.append("REGION_MODE=explicit requires REGIONS to be set")

    if cfg.teardown.teardown_mode not in {"delete"}:
        errors.append("TEARDOWN_MODE currently supports only 'delete' in v2.0")

    if cfg.teardown.apply_changes and not cfg.teardown.simulate and not cfg.teardown.allow_all_targets:
        if not cfg.teardown.target_ids:
            errors.append(
                "APPLY_CHANGES=true requires TEARDOWN_TARGET_IDS to be set (comma-separated IDs/ARNs) "
                "unless TEARDOWN_ALLOW_ALL=true"
            )

    if not cfg.budget.cohort_start_yyyy_mm:
        errors.append("Missing COHORT_START_YYYY_MM (e.g. 2026-01)")
    if cfg.budget.cohort_length_months <= 0:
        errors.append("COHORT_LENGTH_MONTHS must be > 0")
    if cfg.budget.cohort_total_budget_usd <= 0:
        errors.append("COHORT_TOTAL_BUDGET_USD must be > 0")

    return errors


