"""
bloodhound/teardown/executor.py

Executes teardown actions produced by `planner.py`.

Supports simulate mode (TEARDOWN_SIMULATE):
- EC2-family actions use DryRun=True where supported
- non-DryRun services are treated as no-op in simulate mode (safest)
"""

from __future__ import annotations

from dataclasses import dataclass

from bloodhound.aws import AwsClients
from bloodhound.teardown.planner import PlannedAction


@dataclass(frozen=True)
class ExecutionResult:
    attempted: int
    succeeded: int
    failed: int
    simulated: int
    failures: list[str]


def execute_actions(clients: AwsClients, actions: list[PlannedAction], *, simulate: bool) -> ExecutionResult:
    """
    Executes planned actions. This is intentionally minimal and best-effort.
    Caller must gate this behind APPLY_CHANGES=true.
    If simulate=True, no destructive calls are performed:
    - For EC2 actions that support DryRun, we pass DryRun=True and treat DryRunOperation as success.
    - For actions that do not support DryRun (e.g., RDS delete, ELB delete), we no-op and count as simulated success.
    """
    attempted = 0
    succeeded = 0
    failed = 0
    simulated_count = 0
    failures: list[str] = []

    for a in actions:
        attempted += 1
        try:
            # simulate=True guarantees we do NOT destroy anything:
            # - EC2-family: validate permissions/shape with DryRun=True
            # - RDS/ELB deletes: no-op (safest)
            did_simulate = _execute_one(clients, a, simulate=simulate)
            if did_simulate:
                simulated_count += 1
            succeeded += 1
        except Exception as e:
            failed += 1
            failures.append(f"{a.service}/{a.region}/{a.resource_type}/{a.id} -> {a.action}: {e}")

    return ExecutionResult(
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        simulated=simulated_count,
        failures=failures,
    )


def _execute_one(clients: AwsClients, a: PlannedAction, *, simulate: bool) -> bool:
    # Map actions to boto3 service clients.
    if a.action in {"terminate_instances", "delete_volume", "release_address", "delete_nat_gateway"}:
        ec2 = clients.client("ec2", region=a.region)
        if simulate:
            params = dict(a.params)
            params["DryRun"] = True
            try:
                getattr(ec2, a.action)(**params)
            except Exception as e:
                if _is_dry_run_success(e):
                    return True
                raise
            # If the API actually performed the action, something is wrong; treat as error to be safe.
            raise RuntimeError("DryRun did not raise; refusing to continue in simulate mode")
        getattr(ec2, a.action)(**a.params)
        return False

    if a.action == "delete_db_instance":
        if simulate:
            # RDS delete does not support DryRun. No-op for safety.
            return True
        rds = clients.client("rds", region=a.region)
        getattr(rds, a.action)(**a.params)
        return False

    if a.action == "delete_load_balancer":
        if simulate:
            # ELBv2 delete does not support DryRun. No-op for safety.
            return True
        elb = clients.client("elbv2", region=a.region)
        getattr(elb, a.action)(**a.params)
        return False

    raise ValueError(f"Unsupported action: {a.action}")


def _is_dry_run_success(exc: Exception) -> bool:
    """
    boto3 typically raises botocore.exceptions.ClientError with error code DryRunOperation.
    We avoid importing botocore types here; we just pattern-match on known attributes.
    """
    resp = getattr(exc, "response", None)
    if not isinstance(resp, dict):
        return False
    err = resp.get("Error") or {}
    code = err.get("Code")
    return code == "DryRunOperation"


