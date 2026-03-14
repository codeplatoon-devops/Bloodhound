"""
bloodhound/services/scan_service.py

Resource scanning service for Bloodhound v2.

Responsibilities:
- Discover AWS regions
- Scan resources across regions
- Apply whitelist filtering
- Generate Slack scan reports
- Produce candidate resource list used for teardown planning

This module contains logic that previously existed inside
execute_pipeline() and has been extracted for maintainability.
"""

from bloodhound.scanner.regions import discover_regions, select_regions
from bloodhound.scanner.scan_all import scan_all
from bloodhound.whitelist import filter_whitelisted
from bloodhound.messages import (
    format_scan_message,
    format_whitelisted_resources_message,
)


def scan_resources(cfg, clients, slack):
    """
    Scan AWS resources across configured regions and apply whitelist filtering.

    This service performs the full resource discovery phase of the Bloodhound
    pipeline. It identifies candidate resources for teardown while separating
    whitelisted resources that must be preserved.

    Args:
        cfg:
            Bloodhound configuration object produced by `load_config()`.
            Contains region configuration, whitelist rules, and teardown
            parameters.

        clients:
            AWS client container created by `create_clients()`. Provides
            service clients required for scanning infrastructure resources.

        slack:
            Optional SlackNotifier instance used for sending scan reports
            and whitelist summaries.

    Returns:
        dict:
            Dictionary containing the scan results with the following keys:

            regions (list[str])
                Regions that were scanned.

            candidates_by_region (dict[str, list])
                Resources eligible for teardown grouped by AWS region.

            kept_by_region (dict[str, list])
                Resources preserved due to whitelist rules grouped by region.

            all_candidates (list)
                Flattened list of all candidate resources across regions.
                This list is used as the input for teardown planning.

    Raises:
        RuntimeError:
            If region discovery or resource scanning fails.

    Side Effects:
        - Calls AWS resource APIs across multiple regions
        - Posts scan summary to Slack scan channel
        - Posts whitelist report to Slack scan channel
    """

    discovered = None
    if cfg.regions.mode == "discover":
        discovered = discover_regions(clients)

    regions = select_regions(
        cfg.regions.mode,
        cfg.regions.regions,
        discovered_regions=discovered
    )

    # 1) Scan
    raw_by_region = scan_all(
        clients,
        regions=regions,
        rds_final_snapshot=cfg.teardown.rds_final_snapshot
    )

    candidates_by_region: dict[str, list] = {}
    kept_by_region: dict[str, list] = {}

    for region, records in raw_by_region.items():
        # Whitelist is applied before teardown planning.
        candidates, kept = filter_whitelisted(records, cfg.whitelist)
        candidates_by_region[region] = candidates
        kept_by_region[region] = kept

    scan_msg = format_scan_message(candidates_by_region, kept_by_region)

    if slack:
        slack.post_scan(scan_msg)
        slack.post_scan(format_whitelisted_resources_message(kept_by_region))

    # ------------------------------------------------------------
    # Build flattened candidate list for teardown planning
    # ------------------------------------------------------------
    # 3) Teardown plan + optional apply
    all_candidates = [
        r for region in sorted(candidates_by_region.keys())
        for r in candidates_by_region[region]
    ]

    return {
        "regions": regions,
        "candidates_by_region": candidates_by_region,
        "kept_by_region": kept_by_region,
        "all_candidates": all_candidates,
    }