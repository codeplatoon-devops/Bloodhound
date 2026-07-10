"""
bloodhound/scanner/elbv2.py

ELBv2 scanner (ALB/NLB). Collects load balancers and tags (in batches).
"""

from __future__ import annotations

from bloodhound.aws import AwsClients
from bloodhound.types import ResourceRecord


def scan_elbv2_load_balancers(clients: AwsClients, region: str) -> list[ResourceRecord]:
    elb = clients.client("elbv2", region=region)
    paginator = elb.get_paginator("describe_load_balancers")
    lbs: list[dict] = []
    for page in paginator.paginate():
        lbs.extend(page.get("LoadBalancers", []) or [])

    if not lbs:
        return []

    # Fetch tags in batches of 20 ARNs (API limit).
    arn_to_tags: dict[str, dict[str, str]] = {}
    arns = [lb.get("LoadBalancerArn") for lb in lbs if lb.get("LoadBalancerArn")]
    for i in range(0, len(arns), 20):
        batch = arns[i : i + 20]
        try:
            tag_resp = elb.describe_tags(ResourceArns=batch)
            for desc in tag_resp.get("TagDescriptions", []) or []:
                arn = desc.get("ResourceArn")
                if not arn:
                    continue
                arn_to_tags[arn] = {t.get("Key"): t.get("Value") for t in (desc.get("Tags") or []) if t.get("Key")}
        except Exception:
            # Best-effort: skip tags on failure.
            continue

    records: list[ResourceRecord] = []
    for lb in lbs:
        arn = lb.get("LoadBalancerArn")
        name = lb.get("LoadBalancerName")
        if not arn or not name:
            continue
        state = (lb.get("State") or {}).get("Code") or "unknown"
        if state in {"deleted", "deleting"}:
            continue
        records.append(
            ResourceRecord(
                service="elbv2",
                resource_type="load_balancer",
                region=region,
                id=name,
                arn=arn,
                state=state,
                tags=arn_to_tags.get(arn, {}),
                metadata={
                    "scheme": lb.get("Scheme"),
                    "type": lb.get("Type"),
                    "created_at": lb.get("CreatedTime").isoformat() if lb.get("CreatedTime") else None,
                },
                delete_supported=True,
                delete_action="delete_load_balancer",
                delete_params={"LoadBalancerArn": arn},
            )
        )
    return records


