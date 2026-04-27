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
    records: list[ResourceRecord] = []

    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                state = (inst.get("State") or {}).get("Name") or "unknown"
                if state in {"stopped", "terminated", "shutting-down"}:
                    continue
                tags = _tags_to_dict(inst.get("Tags"))
                instance_id = inst.get("InstanceId")
                if not instance_id:
                    continue
                records.append(
                    ResourceRecord(
                        service="ec2",
                        resource_type="instance",
                        region=region,
                        id=instance_id,
                        arn=None,
                        state=state,
                        tags=tags,
                        delete_supported=True,
                        delete_action="terminate_instances",
                        delete_params={"InstanceIds": [instance_id]},
                    )
                )

    return records


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


