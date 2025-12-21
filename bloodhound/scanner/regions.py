from __future__ import annotations

from typing import Optional

from bloodhound.aws import AwsClients


def discover_regions(clients: AwsClients, home_region: str = "us-east-1") -> list[str]:
    ec2 = clients.client("ec2", region=home_region)
    resp = ec2.describe_regions(AllRegions=True)
    regions = [r["RegionName"] for r in resp.get("Regions", []) if "RegionName" in r]
    regions.sort()
    return regions


def select_regions(mode: str, explicit_regions: list[str], discovered_regions: Optional[list[str]]) -> list[str]:
    if mode == "explicit":
        regions = list(explicit_regions)
        regions.sort()
        return regions
    if mode == "discover":
        regions = list(discovered_regions or [])
        regions.sort()
        return regions
    # Fallback: behave like explicit with whatever was provided.
    regions = list(explicit_regions)
    regions.sort()
    return regions


