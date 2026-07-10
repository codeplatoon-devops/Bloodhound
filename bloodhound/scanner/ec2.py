"""
bloodhound/scanner/ec2.py

EC2-family scanners (instances, EBS volumes, EIPs, NAT gateways).
These produce `ResourceRecord` items which are later whitelisted and optionally torn down.
"""

from __future__ import annotations

from typing import Any

from bloodhound.aws import AwsClients
from bloodhound.types import ResourceRecord


def scan_ec2_instances(clients: AwsClients, region: str) -> list[ResourceRecord]:
    ec2 = clients.client("ec2", region=region)
    paginator = ec2.get_paginator("describe_instances")

    # First pass: collect live instances and the EBS volume ids attached to each.
    pending: list[tuple[dict, str, dict[str, str], list[str]]] = []
    all_vol_ids: set[str] = set()
    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                state = (inst.get("State") or {}).get("Name") or "unknown"
                if state in {"stopped", "terminated", "shutting-down"}:
                    continue
                instance_id = inst.get("InstanceId")
                if not instance_id:
                    continue
                vol_ids = [
                    (m.get("Ebs") or {}).get("VolumeId")
                    for m in inst.get("BlockDeviceMappings", []) or []
                    if (m.get("Ebs") or {}).get("VolumeId")
                ]
                all_vol_ids.update(vol_ids)
                pending.append((inst, instance_id, _tags_to_dict(inst.get("Tags")), vol_ids))

    vol_specs = _describe_volume_specs(ec2, sorted(all_vol_ids))

    records: list[ResourceRecord] = []
    for inst, instance_id, tags, vol_ids in pending:
        attached_ebs = [vol_specs[v] for v in vol_ids if v in vol_specs]
        records.append(
            ResourceRecord(
                service="ec2",
                resource_type="instance",
                region=region,
                id=instance_id,
                arn=None,
                state=(inst.get("State") or {}).get("Name") or "unknown",
                tags=tags,
                metadata={
                    "instance_type": inst.get("InstanceType"),
                    "launch_time": (inst.get("LaunchTime").isoformat() if inst.get("LaunchTime") else None),
                    "attached_ebs": attached_ebs,
                    "attached_ebs_gb": sum(v["size_gb"] for v in attached_ebs),
                },
                delete_supported=True,
                delete_action="terminate_instances",
                delete_params={"InstanceIds": [instance_id]},
            )
        )

    return records


def _describe_volume_specs(ec2, vol_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Map volume id -> {size_gb, volume_type} for attached-EBS cost attribution."""
    specs: dict[str, dict[str, Any]] = {}
    if not vol_ids:
        return specs
    # Batch to stay well under request-size limits.
    for i in range(0, len(vol_ids), 200):
        batch = vol_ids[i : i + 200]
        try:
            resp = ec2.describe_volumes(VolumeIds=batch)
        except Exception:  # noqa: BLE001 — best effort; cost just omits attached EBS
            continue
        for vol in resp.get("Volumes", []) or []:
            vid = vol.get("VolumeId")
            if not vid:
                continue
            specs[vid] = {"size_gb": float(vol.get("Size") or 0), "volume_type": vol.get("VolumeType")}
    return specs


def scan_ebs_unattached_volumes(clients: AwsClients, region: str) -> list[ResourceRecord]:
    ec2 = clients.client("ec2", region=region)
    paginator = ec2.get_paginator("describe_volumes")
    records: list[ResourceRecord] = []

    for page in paginator.paginate(
        Filters=[
            {"Name": "status", "Values": ["available"]},
        ]
    ):
        for vol in page.get("Volumes", []):
            vol_id = vol.get("VolumeId")
            if not vol_id:
                continue
            state = vol.get("State") or "unknown"
            tags = _tags_to_dict(vol.get("Tags"))
            records.append(
                ResourceRecord(
                    service="ec2",
                    resource_type="ebs_volume",
                    region=region,
                    id=vol_id,
                    arn=None,
                    state=state,
                    tags=tags,
                    metadata={
                        "size_gb": vol.get("Size"),
                        "volume_type": vol.get("VolumeType"),
                        "created_at": vol.get("CreateTime").isoformat() if vol.get("CreateTime") else None,
                    },
                    delete_supported=True,
                    delete_action="delete_volume",
                    delete_params={"VolumeId": vol_id},
                )
            )
    return records


def scan_eips_unassociated(clients: AwsClients, region: str) -> list[ResourceRecord]:
    ec2 = clients.client("ec2", region=region)
    records: list[ResourceRecord] = []

    # Note: describe_addresses is not pageable.
    resp = ec2.describe_addresses()
    for addr in resp.get("Addresses", []):
        if addr.get("AssociationId") or addr.get("NetworkInterfaceId") or addr.get("InstanceId"):
            continue
        alloc_id = addr.get("AllocationId")
        public_ip = addr.get("PublicIp")
        # AllocationId is required to release in VPC; for classic, PublicIp can be used.
        rid = alloc_id or public_ip
        if not rid:
            continue
        tags = _tags_to_dict(addr.get("Tags"))
        delete_params: dict[str, Any]
        if alloc_id:
            delete_params = {"AllocationId": alloc_id}
        else:
            delete_params = {"PublicIp": public_ip}
        records.append(
            ResourceRecord(
                service="ec2",
                resource_type="elastic_ip",
                region=region,
                id=rid,
                arn=None,
                state="unassociated",
                tags=tags,
                metadata={"public_ip": public_ip},
                delete_supported=True,
                delete_action="release_address",
                delete_params=delete_params,
            )
        )

    return records


def scan_nat_gateways(clients: AwsClients, region: str) -> list[ResourceRecord]:
    ec2 = clients.client("ec2", region=region)
    paginator = ec2.get_paginator("describe_nat_gateways")
    records: list[ResourceRecord] = []

    for page in paginator.paginate():
        for nat in page.get("NatGateways", []):
            nat_id = nat.get("NatGatewayId")
            if not nat_id:
                continue
            state = nat.get("State") or "unknown"
            if state in {"deleted", "deleting"}:
                continue
            tags = _tags_to_dict(nat.get("Tags"))
            records.append(
                ResourceRecord(
                    service="ec2",
                    resource_type="nat_gateway",
                    region=region,
                    id=nat_id,
                    arn=None,
                    state=state,
                    tags=tags,
                    delete_supported=True,
                    delete_action="delete_nat_gateway",
                    delete_params={"NatGatewayId": nat_id},
                )
            )
    return records


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


