"""
bloodhound/attribution.py

Best-effort creator attribution via CloudTrail lookup_events.
Requires CloudTrail enabled in the account/region (management events).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bloodhound.aws import AwsClients
from bloodhound.types import ResourceRecord

CREATE_EVENTS: dict[tuple[str, str], list[str]] = {
    ("ec2", "instance"): ["RunInstances"],
    ("ec2", "ebs_volume"): ["CreateVolume"],
    ("ec2", "elastic_ip"): ["AllocateAddress"],
    ("ec2", "nat_gateway"): ["CreateNatGateway"],
    ("rds", "db_instance"): ["CreateDBInstance"],
    ("elbv2", "load_balancer"): ["CreateLoadBalancer"],
}


def _identity_from_user_identity(ui: dict) -> str:
    if ui.get("userName"):
        return str(ui["userName"])
    if ui.get("arn"):
        arn = str(ui["arn"])
        if "/" in arn:
            return arn.rsplit("/", 1)[-1]
        return arn
    if ui.get("type") == "AssumedRole" and ui.get("sessionContext"):
        session = ui["sessionContext"] or {}
        issuer = (session.get("sessionIssuer") or {}).get("userName")
        if issuer:
            return f"role:{issuer}"
    return "unknown"


def lookup_creator(clients: AwsClients, record: ResourceRecord, *, lookback_days: int = 90) -> str | None:
    ct = clients.client("cloudtrail", region=record.region)
    start = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    event_names = CREATE_EVENTS.get((record.service, record.resource_type), [])

    lookups: list[tuple[str, str]] = [("ResourceName", record.id)]
    if record.arn:
        lookups.append(("ResourceName", record.arn))

    for attr_key, attr_value in lookups:
        try:
            kwargs: dict = {
                "LookupAttributes": [{"AttributeKey": attr_key, "AttributeValue": attr_value}],
                "StartTime": start,
                "MaxResults": 10,
            }
            if event_names:
                # CloudTrail only supports one lookup attribute per call; filter client-side.
                resp = ct.lookup_events(**kwargs)
            else:
                resp = ct.lookup_events(**kwargs)

            events = resp.get("Events") or []
            if event_names:
                events = [e for e in events if e.get("EventName") in event_names] or events

            if not events:
                continue

            # Oldest matching create event ≈ creator.
            oldest = sorted(events, key=lambda e: e.get("EventTime") or datetime.now(timezone.utc))[0]
            import json

            detail = json.loads(oldest.get("CloudTrailEvent") or "{}")
            return _identity_from_user_identity(detail.get("userIdentity") or {})
        except Exception:
            continue
    return None


def enrich_creator(clients: AwsClients, record: ResourceRecord) -> ResourceRecord:
    creator = lookup_creator(clients, record)
    if not creator:
        return record
    meta = dict(record.metadata)
    meta["created_by"] = creator
    return ResourceRecord(
        service=record.service,
        resource_type=record.resource_type,
        region=record.region,
        id=record.id,
        arn=record.arn,
        state=record.state,
        tags=record.tags,
        metadata=meta,
        delete_supported=record.delete_supported,
        delete_action=record.delete_action,
        delete_params=record.delete_params,
    )


def enrich_creators(clients: AwsClients, records: list[ResourceRecord]) -> list[ResourceRecord]:
    return [enrich_creator(clients, r) for r in records]
