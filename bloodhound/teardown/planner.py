from __future__ import annotations

from dataclasses import dataclass

from bloodhound.types import ResourceRecord


@dataclass(frozen=True)
class PlannedAction:
    service: str
    region: str
    resource_type: str
    id: str
    arn: str | None
    action: str
    params: dict


def plan_deletions(records: list[ResourceRecord]) -> tuple[list[PlannedAction], list[ResourceRecord]]:
    """
    Returns (planned_actions, manual_resources).
    """
    actions: list[PlannedAction] = []
    manual: list[ResourceRecord] = []
    for r in records:
        if r.delete_supported and r.delete_action and r.delete_params:
            actions.append(
                PlannedAction(
                    service=r.service,
                    region=r.region,
                    resource_type=r.resource_type,
                    id=r.id,
                    arn=r.arn,
                    action=r.delete_action,
                    params=r.delete_params,
                )
            )
        else:
            manual.append(r)
    return actions, manual


