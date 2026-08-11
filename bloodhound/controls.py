"""
bloodhound/controls.py

Spending-controls / guardrails inventory.

Answers: "are spending limits actually locked in place, and for which OUs,
accounts, Groups, and Users?" Pulls:

- AWS Budgets (the spending caps)
- AWS Budgets Actions (the enforcement that *blocks* spend, and whether it is
  AUTOMATIC = locked, or MANUAL = needs a human to approve)
- For SCP/IAM enforcement: what API actions are denied, and which OUs / accounts
  / IAM Groups / Users / Roles the guardrail applies to

Everything is best-effort: each AWS call is wrapped so a missing permission
degrades to a note instead of failing the whole run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bloodhound.aws import AwsClients

# Budget action statuses that mean the guardrail has actually fired / is enforcing.
ACTIVE_ACTION_STATUSES = {
    "PENDING",
    "EXECUTION_IN_PROGRESS",
    "EXECUTION_SUCCESS",
}


@dataclass(frozen=True)
class BudgetCap:
    name: str
    budget_type: str
    limit_usd: float
    actual_usd: float
    forecast_usd: float | None
    time_unit: str

    @property
    def pct_used(self) -> float:
        if self.limit_usd <= 0:
            return 0.0
        return round(self.actual_usd / self.limit_usd * 100, 1)

    @property
    def over(self) -> bool:
        return self.limit_usd > 0 and self.actual_usd > self.limit_usd


@dataclass(frozen=True)
class EnforcementAction:
    budget_name: str
    action_id: str
    action_type: str  # APPLY_SCP_POLICY | APPLY_IAM_POLICY | RUN_SSM_DOCUMENTS
    approval_model: str  # AUTOMATIC | MANUAL
    status: str
    threshold_value: float
    threshold_type: str  # PERCENTAGE | ABSOLUTE_VALUE
    policy_id: str | None = None
    policy_name: str | None = None
    policy_desc: str | None = None
    denied_actions: list[str] = field(default_factory=list)
    ec2_allowed_instance_types: list[str] = field(default_factory=list)
    target_ids: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=list)
    iam_groups: list[str] = field(default_factory=list)
    iam_users: list[str] = field(default_factory=list)
    iam_roles: list[str] = field(default_factory=list)

    @property
    def locked(self) -> bool:
        """AUTOMATIC enforcement fires with no human approval — i.e. locked in place."""
        return self.approval_model.upper() == "AUTOMATIC"

    @property
    def active(self) -> bool:
        """The guardrail has tripped and is currently enforcing."""
        return self.status.upper() in ACTIVE_ACTION_STATUSES


@dataclass(frozen=True)
class SpendingControlsSnapshot:
    account_id: str
    caps: list[BudgetCap]
    actions: list[EnforcementAction]
    iam_group_names: list[str]
    iam_user_count: int
    notes: list[str] = field(default_factory=list)

    @property
    def locked_actions(self) -> list[EnforcementAction]:
        return [a for a in self.actions if a.locked]

    @property
    def all_locked(self) -> bool:
        return bool(self.actions) and all(a.locked for a in self.actions)


def get_spending_controls_snapshot(clients: AwsClients, account_id: str | None = None) -> SpendingControlsSnapshot:
    notes: list[str] = []

    if not account_id:
        try:
            account_id = clients.client("sts").get_caller_identity()["Account"]
        except Exception as exc:  # noqa: BLE001
            account_id = "unknown"
            notes.append(f"Could not resolve account id: {exc}")

    # Budgets + budget actions live in the global (us-east-1) endpoint.
    budgets = clients.client("budgets", region="us-east-1")
    org = clients.client("organizations", region="us-east-1")
    iam = clients.client("iam")

    caps = _fetch_caps(budgets, account_id, notes)
    actions = _fetch_actions(budgets, org, account_id, notes)
    iam_group_names, iam_user_count = _fetch_iam_principals(iam, notes)

    return SpendingControlsSnapshot(
        account_id=account_id,
        caps=caps,
        actions=actions,
        iam_group_names=iam_group_names,
        iam_user_count=iam_user_count,
        notes=notes,
    )


def _fetch_caps(budgets, account_id: str, notes: list[str]) -> list[BudgetCap]:
    caps: list[BudgetCap] = []
    try:
        paginator = budgets.get_paginator("describe_budgets")
        pages = paginator.paginate(AccountId=account_id)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"describe_budgets unavailable: {exc}")
        return caps

    try:
        for page in pages:
            for b in page.get("Budgets", []) or []:
                calc = b.get("CalculatedSpend") or {}
                caps.append(
                    BudgetCap(
                        name=b.get("BudgetName") or "unnamed",
                        budget_type=b.get("BudgetType") or "unknown",
                        limit_usd=_amt((b.get("BudgetLimit") or {}).get("Amount")),
                        actual_usd=_amt((calc.get("ActualSpend") or {}).get("Amount")),
                        forecast_usd=_amt_opt((calc.get("ForecastedSpend") or {}).get("Amount")),
                        time_unit=b.get("TimeUnit") or "unknown",
                    )
                )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"describe_budgets error: {exc}")
    caps.sort(key=lambda c: -c.limit_usd)
    return caps


def _fetch_actions(budgets, org, account_id: str, notes: list[str]) -> list[EnforcementAction]:
    raw_actions: list[dict] = []
    try:
        paginator = budgets.get_paginator("describe_budget_actions_for_account")
        for page in paginator.paginate(AccountId=account_id):
            raw_actions.extend(page.get("Actions", []) or [])
    except Exception as exc:  # noqa: BLE001
        notes.append(f"describe_budget_actions_for_account unavailable: {exc}")
        return []

    actions: list[EnforcementAction] = []
    for a in raw_actions:
        threshold = a.get("ActionThreshold") or {}
        definition = a.get("Definition") or {}
        action_type = a.get("ActionType") or "unknown"

        policy_id = policy_name = policy_desc = None
        denied: list[str] = []
        ec2_allowed: list[str] = []
        target_ids: list[str] = []
        target_names: list[str] = []
        iam_groups: list[str] = []
        iam_users: list[str] = []
        iam_roles: list[str] = []

        scp = definition.get("ScpActionDefinition")
        iam_def = definition.get("IamActionDefinition")
        ssm = definition.get("SsmActionDefinition")

        if scp:
            policy_id = scp.get("PolicyId")
            target_ids = list(scp.get("TargetIds") or [])
            policy_name, policy_desc, denied, ec2_allowed = _describe_scp(org, policy_id, notes)
            target_names = _resolve_targets(org, target_ids, notes)
        elif iam_def:
            policy_id = iam_def.get("PolicyArn")
            policy_name = (policy_id or "").split("/")[-1] or policy_id
            iam_groups = list(iam_def.get("Groups") or [])
            iam_users = list(iam_def.get("Users") or [])
            iam_roles = list(iam_def.get("Roles") or [])
        elif ssm:
            policy_name = f"SSM {ssm.get('ActionSubType') or ''}".strip()
            target_ids = list(ssm.get("InstanceIds") or [])

        actions.append(
            EnforcementAction(
                budget_name=a.get("BudgetName") or "unknown",
                action_id=a.get("ActionId") or "unknown",
                action_type=action_type,
                approval_model=a.get("ApprovalModel") or "unknown",
                status=a.get("Status") or "unknown",
                threshold_value=_amt(threshold.get("ActionThresholdValue")),
                threshold_type=threshold.get("ActionThresholdType") or "unknown",
                policy_id=policy_id,
                policy_name=policy_name,
                policy_desc=policy_desc,
                denied_actions=denied,
                ec2_allowed_instance_types=ec2_allowed,
                target_ids=target_ids,
                target_names=target_names,
                iam_groups=iam_groups,
                iam_users=iam_users,
                iam_roles=iam_roles,
            )
        )
    return actions


def _describe_scp(org, policy_id: str | None, notes: list[str]) -> tuple[str | None, str | None, list[str], list[str]]:
    if not policy_id:
        return None, None, [], []
    try:
        resp = org.describe_policy(PolicyId=policy_id)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"describe_policy({policy_id}) unavailable: {exc}")
        return policy_id, None, [], []

    policy = resp.get("Policy") or {}
    summary = policy.get("PolicySummary") or {}
    name = summary.get("Name") or policy_id
    desc = summary.get("Description")
    denied, ec2_allowed = _parse_scp_content(policy.get("Content"))
    return name, desc, denied, ec2_allowed


def _parse_scp_content(content: str | None) -> tuple[list[str], list[str]]:
    """Pull denied actions and any EC2 instance-type allowlist out of an SCP document."""
    if not content:
        return [], []
    try:
        doc = json.loads(content)
    except (ValueError, TypeError):
        return [], []

    denied: list[str] = []
    ec2_allowed: list[str] = []
    statements = doc.get("Statement")
    if isinstance(statements, dict):
        statements = [statements]
    for stmt in statements or []:
        if (stmt.get("Effect") or "").lower() != "deny":
            continue
        actions = stmt.get("Action")
        if isinstance(actions, str):
            actions = [actions]
        for act in actions or []:
            if act not in denied:
                denied.append(act)
        cond = stmt.get("Condition") or {}
        for op_vals in cond.values():
            if not isinstance(op_vals, dict):
                continue
            for key, vals in op_vals.items():
                if "instancetype" in key.lower():
                    if isinstance(vals, str):
                        vals = [vals]
                    for v in vals:
                        if v not in ec2_allowed:
                            ec2_allowed.append(v)
    return denied, ec2_allowed


def _resolve_targets(org, target_ids: list[str], notes: list[str]) -> list[str]:
    names: list[str] = []
    for tid in target_ids:
        label = tid
        try:
            if tid.startswith("ou-"):
                resp = org.describe_organizational_unit(OrganizationalUnitId=tid)
                label = (resp.get("OrganizationalUnit") or {}).get("Name") or tid
            elif tid.isdigit():
                resp = org.describe_account(AccountId=tid)
                label = (resp.get("Account") or {}).get("Name") or tid
        except Exception:  # noqa: BLE001 — best effort; fall back to raw id
            label = tid
        names.append(label)
    return names


def _fetch_iam_principals(iam, notes: list[str]) -> tuple[list[str], int]:
    groups: list[str] = []
    user_count = 0
    try:
        for page in iam.get_paginator("list_groups").paginate():
            groups.extend(g.get("GroupName") for g in page.get("Groups", []) or [] if g.get("GroupName"))
    except Exception as exc:  # noqa: BLE001
        notes.append(f"list_groups unavailable: {exc}")
    try:
        for page in iam.get_paginator("list_users").paginate():
            user_count += len(page.get("Users", []) or [])
    except Exception as exc:  # noqa: BLE001
        notes.append(f"list_users unavailable: {exc}")
    return groups, user_count


def _amt(raw) -> float:
    try:
        return float(raw) if raw is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def _amt_opt(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None
