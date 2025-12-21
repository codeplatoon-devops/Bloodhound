"""
bloodhound/scanner/rds.py

RDS scanner. Collects DB instances and best-effort tags (requires list_tags_for_resource).
"""

from __future__ import annotations

from typing import Any

from bloodhound.aws import AwsClients
from bloodhound.types import ResourceRecord


def scan_rds_instances(clients: AwsClients, region: str, rds_final_snapshot: bool) -> list[ResourceRecord]:
    rds = clients.client("rds", region=region)
    paginator = rds.get_paginator("describe_db_instances")
    records: list[ResourceRecord] = []

    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            db_id = db.get("DBInstanceIdentifier")
            arn = db.get("DBInstanceArn")
            status = db.get("DBInstanceStatus") or "unknown"
            if not db_id:
                continue
            # Tags require a separate call; keep best-effort for now.
            tags = _tags_to_dict(_safe_list_tags(rds, arn))
            delete_params: dict[str, Any] = {
                "DBInstanceIdentifier": db_id,
                "SkipFinalSnapshot": not rds_final_snapshot,
            }
            records.append(
                ResourceRecord(
                    service="rds",
                    resource_type="db_instance",
                    region=region,
                    id=db_id,
                    arn=arn,
                    state=status,
                    tags=tags,
                    delete_supported=True,
                    delete_action="delete_db_instance",
                    delete_params=delete_params,
                )
            )

    return records


def _safe_list_tags(rds_client, arn: str | None) -> list[dict[str, str]]:
    if not arn:
        return []
    try:
        resp = rds_client.list_tags_for_resource(ResourceName=arn)
        return resp.get("TagList", []) or []
    except Exception:
        return []


def _tags_to_dict(tags: Any) -> dict[str, str]:
    if not tags:
        return {}
    out: dict[str, str] = {}
    for t in tags:
        k = t.get("Key")
        v = t.get("Value")
        if k is None or v is None:
            continue
        out[str(k)] = str(v)
    return out


