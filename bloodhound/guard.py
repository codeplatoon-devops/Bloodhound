"""
bloodhound/guard.py

Cost-guard management — the "/guard" Slack command.

A *guardrail* is a named, two-layer spend control:
  - an Organizations **SCP** (e.g. `cp-org-spend-stop`) -> restricts member accounts
    under its target OUs/accounts
  - an IAM **managed policy attached to a group** (e.g. `cp-aico-echo-cost-guard` on
    `aico-echo-class`) -> restricts IAM users in the management account

Both layers historically carry the SAME deny list. `/guard` edits BOTH together so they
can never drift apart — drift is exactly what once left RDS blocked for IAM-user students
even after the SCP was loosened.

Subcommands
-----------
  list                          all guardrails: layers, attachments, denied services
  show <name>                   full detail for one guardrail
  members <name>                list users in the guardrail's group
  allow  <name> <service>       remove a service from the deny lists (unblock)   [mutation]
  deny   <name> <service>       add a service to the deny lists (block)          [mutation]
  enable <name>                 (re)attach the IAM policy to its group           [mutation]
  disable <name>                detach the IAM policy from its group             [mutation]
  add-student <name> <user>     add a user to the group                          [mutation]
  remove-student <name> <user>  remove a user from the group                     [mutation]

Safety
------
- Mutations require the caller to be in GUARD_ALLOWED_USER_IDS (falls back to
  SLACK_ALLOWED_USER_IDS). If neither is set, mutations are refused (fail-safe) — the
  command is reachable from a public Lambda Function URL.
- `allow` / `deny` only touch services in GUARD_TOGGLEABLE_SERVICES, so a Slack message
  can never toggle iam:* / organizations:* / ec2 instance-type caps, etc.

Tiers (phase 2)
---------------
Each guardrail carries a `tier` field. Today everything is one tier ("core"); adding
2-3 tiers later is config (GUARD_REGISTRY), not a rewrite.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass, field

from bloodhound.aws import AwsClients
from bloodhound.tables import md_table

# --- configuration (env-driven; self-contained like slack_commands.py) ----------------

_DEFAULT_REGISTRY = [
    {
        "name": "cost-guard",
        "tier": "core",
        "scp": "cp-org-spend-stop",
        "iam_policy": "cp-aico-echo-cost-guard",
        "group": "aico-echo-class",
    }
]

# Services that allow/deny may toggle. Deliberately excludes iam, organizations, ec2, etc.
_DEFAULT_TOGGLEABLE = [
    "rds", "redshift", "neptune-db", "dax", "memorydb",
    "sagemaker", "bedrock", "bedrock-runtime", "bedrock-agent-runtime",
    "eks", "elasticmapreduce", "es", "aoss", "q", "deepracer", "forecast",
    "frauddetector", "kendra", "comprehendmedical", "healthlake", "omics", "braket",
]

MUTATION_SUBCOMMANDS = {
    "allow", "deny", "enable", "disable", "add-student", "remove-student",
}

_ALIASES = {
    "": "help", "help": "help",
    "list": "list", "ls": "list",
    "show": "show",
    "members": "members", "who": "members",
    "allow": "allow", "unblock": "allow",
    "deny": "deny", "block": "deny",
    "enable": "enable",
    "disable": "disable",
    "add-student": "add-student", "add": "add-student",
    "remove-student": "remove-student", "remove": "remove-student", "rm": "remove-student",
}


def _split_csv(raw: str | None) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


@dataclass(frozen=True)
class GuardrailDef:
    name: str
    tier: str
    scp: str | None
    iam_policy: str | None
    group: str | None


def load_registry() -> list[GuardrailDef]:
    raw = os.environ.get("GUARD_REGISTRY", "").strip()
    entries = _DEFAULT_REGISTRY
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                entries = parsed
        except ValueError:
            pass
    out: list[GuardrailDef] = []
    for e in entries:
        out.append(
            GuardrailDef(
                name=e.get("name") or "guardrail",
                tier=e.get("tier") or "core",
                scp=e.get("scp"),
                iam_policy=e.get("iam_policy"),
                group=e.get("group"),
            )
        )
    return out


def toggleable_services() -> list[str]:
    override = _split_csv(os.environ.get("GUARD_TOGGLEABLE_SERVICES"))
    return override or list(_DEFAULT_TOGGLEABLE)


def parse_command(text: str) -> tuple[str, list[str]]:
    tokens = (text or "").strip().split()
    if not tokens:
        return "help", []
    sub = _ALIASES.get(tokens[0].lower(), tokens[0].lower())
    return sub, tokens[1:]


def user_allowed_to_mutate(user_id: str) -> bool:
    allowed = _split_csv(
        os.environ.get("GUARD_ALLOWED_USER_IDS") or os.environ.get("SLACK_ALLOWED_USER_IDS")
    )
    return bool(allowed) and user_id in allowed  # fail-safe: empty allowlist => no mutations


# --- low-level AWS helpers (best-effort; surface notes instead of crashing) ------------


def _org(clients: AwsClients):
    return clients.client("organizations", region="us-east-1")


def _iam(clients: AwsClients):
    return clients.client("iam")


def _find_scp_id(org, name: str | None) -> str | None:
    if not name:
        return None
    try:
        paginator = org.get_paginator("list_policies")
        for page in paginator.paginate(Filter="SERVICE_CONTROL_POLICY"):
            for p in page.get("Policies", []) or []:
                if p.get("Name") == name:
                    return p.get("Id")
    except Exception:  # noqa: BLE001
        return None
    return None


def _find_iam_policy_arn(iam, name: str | None) -> str | None:
    if not name:
        return None
    try:
        paginator = iam.get_paginator("list_policies")
        for page in paginator.paginate(Scope="Local"):
            for p in page.get("Policies", []) or []:
                if p.get("PolicyName") == name:
                    return p.get("Arn")
    except Exception:  # noqa: BLE001
        return None
    return None


def _scp_document(org, policy_id: str) -> dict:
    content = (org.describe_policy(PolicyId=policy_id).get("Policy") or {}).get("Content")
    return json.loads(content) if content else {"Version": "2012-10-17", "Statement": []}


def _iam_document(iam, arn: str) -> dict:
    ver = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
    doc = iam.get_policy_version(PolicyArn=arn, VersionId=ver)["PolicyVersion"]["Document"]
    if isinstance(doc, str):
        doc = json.loads(urllib.parse.unquote(doc))
    return doc


def _statements(doc: dict) -> list[dict]:
    stmts = doc.get("Statement")
    if isinstance(stmts, dict):
        return [stmts]
    return stmts or []


def _actions(stmt: dict) -> list[str]:
    acts = stmt.get("Action")
    if isinstance(acts, list):
        return acts
    return [acts] if acts else []


def _denied_services(doc: dict) -> list[str]:
    svcs: set[str] = set()
    for s in _statements(doc):
        if (s.get("Effect") or "").lower() != "deny":
            continue
        for a in _actions(s):
            if a:
                svcs.add(a.split(":")[0])
    return sorted(svcs)


def _remove_service(doc: dict, service: str) -> list[str]:
    """Strip every Deny action whose service prefix == `service`. Returns removed actions."""
    removed: list[str] = []
    for s in _statements(doc):
        if (s.get("Effect") or "").lower() != "deny":
            continue
        original = _actions(s)
        kept = []
        for a in original:
            if a and a.split(":")[0] == service:
                removed.append(a)
            else:
                kept.append(a)
        if len(kept) != len(original):
            s["Action"] = kept
    # Drop now-empty deny statements (keep everything else).
    doc["Statement"] = [
        s for s in _statements(doc)
        if (s.get("Effect") or "").lower() != "deny" or _actions(s)
    ]
    return removed


def _add_service(doc: dict, service: str) -> str | None:
    """Add `<service>:*` to a wildcard-resource Deny statement. Returns added action or None."""
    action = f"{service}:*"
    target = None
    for s in _statements(doc):
        if (s.get("Effect") or "").lower() == "deny" and s.get("Resource") in ("*", ["*"]):
            target = s
            break
    if target is None:
        target = {"Sid": "GuardManagedDenies", "Effect": "Deny", "Action": [], "Resource": "*"}
        doc.setdefault("Statement", []).append(target)
    acts = _actions(target)
    if any(a and a.split(":")[0] == service for a in acts):
        return None  # already covered
    acts.append(action)
    target["Action"] = acts
    return action


def _put_scp(org, policy_id: str, doc: dict) -> None:
    org.update_policy(PolicyId=policy_id, Content=json.dumps(doc))


def _put_iam(iam, arn: str, doc: dict) -> str:
    """Create + set-as-default a new policy version, pruning the oldest if at the 5-version cap."""
    versions = iam.list_policy_versions(PolicyArn=arn).get("Versions", [])
    if len(versions) >= 5:
        nondefault = sorted(
            (v for v in versions if not v.get("IsDefaultVersion")),
            key=lambda v: v.get("CreateDate"),
        )
        if nondefault:
            iam.delete_policy_version(PolicyArn=arn, VersionId=nondefault[0]["VersionId"])
    resp = iam.create_policy_version(
        PolicyArn=arn, PolicyDocument=json.dumps(doc), SetAsDefault=True
    )
    return resp["PolicyVersion"]["VersionId"]


def _scp_targets(org, policy_id: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    paginator = org.get_paginator("list_targets_for_policy")
    for page in paginator.paginate(PolicyId=policy_id):
        for t in page.get("Targets", []) or []:
            out.append((t.get("Type", ""), t.get("Name", t.get("TargetId", ""))))
    return out


def _group_has_policy(iam, group: str, arn: str) -> bool:
    paginator = iam.get_paginator("list_attached_group_policies")
    for page in paginator.paginate(GroupName=group):
        for p in page.get("AttachedPolicies", []) or []:
            if p.get("PolicyArn") == arn:
                return True
    return False


def _group_members(iam, group: str) -> list[str]:
    out: list[str] = []
    paginator = iam.get_paginator("get_group")
    for page in paginator.paginate(GroupName=group):
        out.extend(u.get("UserName") for u in page.get("Users", []) or [] if u.get("UserName"))
    return out


# --- engine ----------------------------------------------------------------------------


@dataclass
class GuardEngine:
    clients: AwsClients
    registry: list[GuardrailDef] = field(default_factory=load_registry)

    def run(self, sub: str, args: list[str]) -> str:
        try:
            if sub == "help":
                return _help()
            if sub == "list":
                return self.list_all()
            if sub == "show":
                return self.show(self._need_name(args))
            if sub == "members":
                return self.members(self._need_name(args))
            if sub == "allow":
                return self.toggle(self._need_name(args), self._need_arg(args, 1, "service"), block=False)
            if sub == "deny":
                return self.toggle(self._need_name(args), self._need_arg(args, 1, "service"), block=True)
            if sub == "enable":
                return self.set_enabled(self._need_name(args), enabled=True)
            if sub == "disable":
                return self.set_enabled(self._need_name(args), enabled=False)
            if sub == "add-student":
                return self.student(self._need_name(args), self._need_arg(args, 1, "user"), add=True)
            if sub == "remove-student":
                return self.student(self._need_name(args), self._need_arg(args, 1, "user"), add=False)
            return f"Unknown subcommand `{sub}`.\n\n" + _help()
        except _GuardError as exc:
            return f"⚠️ {exc}"

    # -- resolution --

    def _get_def(self, name: str) -> GuardrailDef:
        for d in self.registry:
            if d.name == name:
                return d
        names = ", ".join(f"`{d.name}`" for d in self.registry) or "(none configured)"
        raise _GuardError(f"No guardrail named `{name}`. Known: {names}")

    def _need_name(self, args: list[str]) -> str:
        if args:
            return args[0]
        if len(self.registry) == 1:
            return self.registry[0].name  # convenience: single guardrail is implied
        raise _GuardError("Specify a guardrail name. Try `/guard list`.")

    @staticmethod
    def _need_arg(args: list[str], idx: int, label: str) -> str:
        if len(args) > idx:
            return args[idx]
        raise _GuardError(f"Missing `<{label}>`.")

    # -- read ops --

    def list_all(self) -> str:
        org, iam = _org(self.clients), _iam(self.clients)
        rows: list[list[object]] = []
        for d in self.registry:
            scp_id = _find_scp_id(org, d.scp)
            iam_arn = _find_iam_policy_arn(iam, d.iam_policy)
            scp_denied = iam_denied = "—"
            attaches: list[str] = []
            if scp_id:
                try:
                    scp_denied = ", ".join(_denied_services(_scp_document(org, scp_id))) or "none"
                    n = len(_scp_targets(org, scp_id))
                    attaches.append(f"SCP→{n} OU/acct")
                except Exception:  # noqa: BLE001
                    scp_denied = "?"
            if iam_arn and d.group:
                try:
                    iam_denied = ", ".join(_denied_services(_iam_document(iam, iam_arn))) or "none"
                    on = "on" if _group_has_policy(iam, d.group, iam_arn) else "OFF"
                    attaches.append(f"IAM→{d.group} ({on})")
                except Exception:  # noqa: BLE001
                    iam_denied = "?"
            rows.append([d.name, d.tier, " ; ".join(attaches) or "—", scp_denied, iam_denied])
        body = md_table(
            ["Guardrail", "Tier", "Attached to", "SCP denies", "IAM denies"], rows
        )
        return _header("Guardrails") + body + (
            "\n\n_Two layers per guardrail: **SCP** gates member accounts, "
            "**IAM** policy gates IAM-user students in the mgmt account. "
            "`/guard show <name>` for detail._"
        )

    def show(self, name: str) -> str:
        d = self._get_def(name)
        org, iam = _org(self.clients), _iam(self.clients)
        out = [_header(f"Guardrail: {d.name}  (tier: {d.tier})")]

        scp_id = _find_scp_id(org, d.scp)
        if scp_id:
            doc = _scp_document(org, scp_id)
            targets = _scp_targets(org, scp_id)
            out.append(f"**SCP `{d.scp}`** (`{scp_id}`)")
            out.append("Applies to: " + (", ".join(f"{t}:{n}" for t, n in targets) or "—"))
            out.append("Denied: " + (", ".join(_denied_services(doc)) or "none"))
            out.append("")
        elif d.scp:
            out.append(f"**SCP `{d.scp}`** — not found.\n")

        iam_arn = _find_iam_policy_arn(iam, d.iam_policy)
        if iam_arn:
            doc = _iam_document(iam, iam_arn)
            on = _group_has_policy(iam, d.group, iam_arn) if d.group else False
            out.append(f"**IAM policy `{d.iam_policy}`** → group `{d.group}` "
                       f"({'attached/ON' if on else 'detached/OFF'})")
            out.append("Denied: " + (", ".join(_denied_services(doc)) or "none"))
            if d.group:
                members = _group_members(iam, d.group)
                out.append(f"Group members ({len(members)}): " + (", ".join(members) or "—"))
        elif d.iam_policy:
            out.append(f"**IAM policy `{d.iam_policy}`** — not found.")
        return "\n".join(out)

    def members(self, name: str) -> str:
        d = self._get_def(name)
        if not d.group:
            raise _GuardError(f"`{name}` has no group configured.")
        members = _group_members(_iam(self.clients), d.group)
        return _header(f"Members of `{d.group}` ({len(members)})") + (
            "\n".join(f"- {m}" for m in members) or "_No members._"
        )

    # -- mutations --

    def toggle(self, name: str, service: str, *, block: bool) -> str:
        d = self._get_def(name)
        service = service.lower().rstrip(":*")
        allowed = toggleable_services()
        if service not in allowed:
            raise _GuardError(
                f"`{service}` is not a toggleable service. Allowed: {', '.join(allowed)}"
            )
        org, iam = _org(self.clients), _iam(self.clients)
        verb = "deny" if block else "allow"
        lines = [_header(f"/guard {verb} {d.name} {service}")]

        scp_id = _find_scp_id(org, d.scp)
        if scp_id:
            doc = _scp_document(org, scp_id)
            changed = _add_service(doc, service) if block else _remove_service(doc, service)
            if changed:
                _put_scp(org, scp_id, doc)
                detail = changed if isinstance(changed, str) else ", ".join(changed)
                lines.append(f"- SCP `{d.scp}`: {'added' if block else 'removed'} {detail}")
            else:
                lines.append(f"- SCP `{d.scp}`: no change")

        iam_arn = _find_iam_policy_arn(iam, d.iam_policy)
        if iam_arn:
            doc = _iam_document(iam, iam_arn)
            changed = _add_service(doc, service) if block else _remove_service(doc, service)
            if changed:
                ver = _put_iam(iam, iam_arn, doc)
                detail = changed if isinstance(changed, str) else ", ".join(changed)
                lines.append(f"- IAM `{d.iam_policy}`: {'added' if block else 'removed'} {detail} (now {ver})")
            else:
                lines.append(f"- IAM `{d.iam_policy}`: no change")

        lines.append("")
        lines.append(
            f"{'🔒' if block else '✅'} `{service}` is now {'blocked' if block else 'allowed'} "
            f"across both layers of `{d.name}`."
        )
        return "\n".join(lines)

    def set_enabled(self, name: str, *, enabled: bool) -> str:
        d = self._get_def(name)
        if not (d.iam_policy and d.group):
            raise _GuardError(f"`{name}` has no IAM policy/group to enable/disable.")
        iam = _iam(self.clients)
        arn = _find_iam_policy_arn(iam, d.iam_policy)
        if not arn:
            raise _GuardError(f"IAM policy `{d.iam_policy}` not found.")
        if enabled:
            iam.attach_group_policy(GroupName=d.group, PolicyArn=arn)
            state = "attached to"
        else:
            iam.detach_group_policy(GroupName=d.group, PolicyArn=arn)
            state = "detached from"
        return _header(f"/guard {'enable' if enabled else 'disable'} {d.name}") + (
            f"IAM policy `{d.iam_policy}` {state} group `{d.group}`.\n\n"
            f"_Note: the SCP layer is governed by its AWS Budgets action, not toggled here._"
        )

    def student(self, name: str, user: str, *, add: bool) -> str:
        d = self._get_def(name)
        if not d.group:
            raise _GuardError(f"`{name}` has no group configured.")
        iam = _iam(self.clients)
        if add:
            iam.add_user_to_group(GroupName=d.group, UserName=user)
            msg = f"Added `{user}` to `{d.group}`."
        else:
            iam.remove_user_from_group(GroupName=d.group, UserName=user)
            msg = f"Removed `{user}` from `{d.group}`."
        return _header(f"/guard {'add-student' if add else 'remove-student'} {d.name} {user}") + msg


class _GuardError(Exception):
    pass


def _header(title: str) -> str:
    return f"**Bloodhound — {title}**\n\n"


def _help() -> str:
    return (
        "*`/guard` — cost-guard management*\n"
        "• `/guard list` — all guardrails + what they block\n"
        "• `/guard show <name>` — full detail\n"
        "• `/guard members <name>` — users in the group\n"
        "• `/guard allow <name> <service>` — unblock a service _(admin)_\n"
        "• `/guard deny <name> <service>` — block a service _(admin)_\n"
        "• `/guard enable|disable <name>` — attach/detach the IAM policy _(admin)_\n"
        "• `/guard add-student|remove-student <name> <user>` _(admin)_\n"
        "\n_With one guardrail configured, `<name>` can be omitted._"
    )
