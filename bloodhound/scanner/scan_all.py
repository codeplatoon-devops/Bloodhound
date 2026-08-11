"""
bloodhound/scanner/scan_all.py

Scan coordinator: runs all per-service scanners for each region and returns a region->records map.
"""

from __future__ import annotations

from dataclasses import dataclass

from bloodhound.aws import AwsClients
from bloodhound.scanner.ec2 import (
    scan_ec2_instances,
    scan_ebs_unattached_volumes,
    scan_eips_unassociated,
    scan_nat_gateways,
)
from bloodhound.scanner.elbv2 import scan_elbv2_load_balancers
from bloodhound.scanner.rds import scan_rds_instances
from bloodhound.types import ResourceRecord


@dataclass(frozen=True)
class ScanResult:
    region: str
    resources: list[ResourceRecord]


def scan_region(clients: AwsClients, region: str, rds_final_snapshot: bool) -> list[ResourceRecord]:
    resources: list[ResourceRecord] = []
    resources.extend(scan_ec2_instances(clients, region))
    resources.extend(scan_rds_instances(clients, region, rds_final_snapshot=rds_final_snapshot))
    resources.extend(scan_eips_unassociated(clients, region))
    resources.extend(scan_nat_gateways(clients, region))
    resources.extend(scan_ebs_unattached_volumes(clients, region))
    resources.extend(scan_elbv2_load_balancers(clients, region))
    return resources


def scan_all(clients: AwsClients, regions: list[str], rds_final_snapshot: bool) -> dict[str, list[ResourceRecord]]:
    out: dict[str, list[ResourceRecord]] = {}
    for region in regions:
        out[region] = scan_region(clients, region, rds_final_snapshot=rds_final_snapshot)
    return out


