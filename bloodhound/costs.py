"""
bloodhound/costs.py

Cost estimation for scanned resources and MTD service breakdown from Cost Explorer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from bloodhound.aws import AwsClients
from bloodhound.types import ResourceRecord


@dataclass(frozen=True)
class MtdCostSnapshot:
    """Actual account billing from Cost Explorer for the current calendar month."""

    period_start: date
    period_end_inclusive: date
    by_service: dict[str, float]

    @property
    def total_usd(self) -> float:
        return round(sum(self.by_service.values()), 2)


# Rough on-demand us-east-1 monthly estimates (USD). Intentionally conservative.
EC2_HOURLY: dict[str, float] = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
}

RDS_HOURLY: dict[str, float] = {
    "db.t3.micro": 0.018,
    "db.t3.small": 0.036,
    "db.t4g.micro": 0.016,
    "db.t4g.small": 0.032,
    "db.t3.medium": 0.072,
    "db.m5.large": 0.171,
}

# EBS $/GB-month by volume type (us-east-1 base). Provisioned IOPS/throughput excluded.
EBS_GB_RATE: dict[str, float] = {
    "gp3": 0.08,
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
}

# ELB base $/hour by type (us-east-1). LCU/data charges are excluded (no metrics here).
ELB_HOURLY: dict[str, float] = {
    "application": 0.0225,
    "network": 0.0225,
    "gateway": 0.0125,
}

# Per-region multiplier applied to us-east-1 base rates. Approximate — replace with the
# AWS Price List API for exact figures. US/standard regions ~1.0; others scaled up.
REGION_MULTIPLIER: dict[str, float] = {
    "us-east-1": 1.00,
    "us-east-2": 1.00,
    "us-west-2": 1.00,
    "us-west-1": 1.08,
    "ca-central-1": 1.05,
    "eu-west-1": 1.06,
    "eu-west-2": 1.07,
    "eu-central-1": 1.08,
    "ap-south-1": 0.95,
    "ap-southeast-1": 1.10,
    "ap-southeast-2": 1.12,
    "ap-northeast-1": 1.12,
    "sa-east-1": 1.40,
}
DEFAULT_REGION_MULTIPLIER = 1.10

HOURS_PER_MONTH = 730

# Forward-looking rolling window used for projections.
WINDOW_DAYS = 30
DAYS_PER_MONTH_AVG = 30.4375  # 365.25 / 12


def region_multiplier(region: str | None) -> float:
    return REGION_MULTIPLIER.get(region or "", DEFAULT_REGION_MULTIPLIER)


def _ebs_gb_rate(vol_type: str | None) -> float:
    return EBS_GB_RATE.get((vol_type or "gp3").lower(), 0.10)


def get_mtd_cost_snapshot(clients: AwsClients, today: date | None = None) -> MtdCostSnapshot:
    today = today or date.today()
    month_start = date(today.year, today.month, 1)
    ce = clients.client("ce", region="us-east-1")
    resp = ce.get_cost_and_usage(
        TimePeriod={
            "Start": month_start.strftime("%Y-%m-%d"),
            "End": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    out: dict[str, float] = {}
    for period in resp.get("ResultsByTime", []) or []:
        for group in period.get("Groups", []) or []:
            service = (group.get("Keys") or ["Unknown"])[0]
            amt = ((group.get("Metrics") or {}).get("UnblendedCost") or {}).get("Amount")
            try:
                out[service] = float(amt) if amt else 0.0
            except ValueError:
                out[service] = 0.0
    return MtdCostSnapshot(
        period_start=month_start,
        period_end_inclusive=today,
        by_service=dict(sorted(out.items(), key=lambda x: -x[1])),
    )


def get_mtd_cost_by_service(clients: AwsClients, today: date | None = None) -> dict[str, float]:
    return get_mtd_cost_snapshot(clients, today=today).by_service


def estimate_monthly_cost_usd(record: ResourceRecord) -> float:
    meta = record.metadata
    svc = record.service
    rtype = record.resource_type

    mult = region_multiplier(record.region)

    if svc == "ec2" and rtype == "instance":
        itype = str(meta.get("instance_type") or "t3.micro")
        hourly = EC2_HOURLY.get(itype, 0.05)
        compute = hourly * HOURS_PER_MONTH * mult
        # Include attached EBS — it is billed (and deleted) with the instance.
        ebs = 0.0
        for vol in meta.get("attached_ebs") or []:
            ebs += float(vol.get("size_gb") or 0) * _ebs_gb_rate(vol.get("volume_type")) * mult
        return round(compute + ebs, 2)

    if svc == "ec2" and rtype == "ebs_volume":
        size = float(meta.get("size_gb") or 8)
        return round(size * _ebs_gb_rate(meta.get("volume_type")) * mult, 2)

    if svc == "ec2" and rtype == "elastic_ip":
        return round(3.65 * mult, 2)

    if svc == "ec2" and rtype == "nat_gateway":
        # Base hourly only ($0.045/hr); per-GB data processing excluded.
        return round(0.045 * HOURS_PER_MONTH * mult, 2)

    if svc == "rds" and rtype == "db_instance":
        cls = str(meta.get("instance_class") or "db.t3.micro")
        storage = float(meta.get("allocated_storage_gb") or 20)
        hourly = RDS_HOURLY.get(cls, 0.02)
        az_factor = 2.0 if meta.get("multi_az") else 1.0
        compute = hourly * HOURS_PER_MONTH * az_factor * mult
        storage_cost = storage * 0.115 * az_factor * mult
        return round(compute + storage_cost, 2)

    if svc == "elbv2" and rtype == "load_balancer":
        lb_type = str(meta.get("type") or "application").lower()
        hourly = ELB_HOURLY.get(lb_type, 0.0225)
        return round(hourly * HOURS_PER_MONTH * mult, 2)

    return 0.0


def estimate_forward_window_usd(record: ResourceRecord, days: int = WINDOW_DAYS) -> float:
    """Projected cost over a rolling forward window, assuming the resource stays as-is.

    Built from the monthly run-rate and prorated to the window length, so a 30-day
    window answers: "if this stays live and unchanged, what does it cost over the next
    30 days?"
    """
    monthly = estimate_monthly_cost_usd(record)
    return round(monthly * days / DAYS_PER_MONTH_AVG, 2)


def enrich_record_cost(record: ResourceRecord) -> ResourceRecord:
    est = estimate_monthly_cost_usd(record)
    meta = dict(record.metadata)
    meta["est_monthly_usd"] = est
    meta["est_forward_30d_usd"] = estimate_forward_window_usd(record)
    return ResourceRecord(
        service=record.service,
        resource_type=record.resource_type,
        region=record.region,
        id=record.id,
        arn=record.arn,
        state=record.state,
        tags=record.tags,
        metadata=meta,
        delete_supported=record.delete_supported,
        delete_action=record.delete_action,
        delete_params=record.delete_params,
    )


def enrich_records(records: list[ResourceRecord]) -> list[ResourceRecord]:
    return [enrich_record_cost(r) for r in records]


def format_age(meta: dict) -> str:
    raw = meta.get("created_at") or meta.get("launch_time")
    if not raw:
        return "unknown"
    try:
        if isinstance(raw, datetime):
            created = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        else:
            created = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        days = max(0, (datetime.now(timezone.utc) - created).days)
        if days == 0:
            return "<1d"
        if days < 30:
            return f"{days}d"
        return f"{days // 30}mo {days % 30}d"
    except (ValueError, TypeError):
        return "unknown"


def sum_estimated_monthly(records: list[ResourceRecord]) -> float:
    return round(sum(float(r.metadata.get("est_monthly_usd") or 0) for r in records), 2)


def sum_forward_30d(records: list[ResourceRecord]) -> float:
    return round(sum(float(r.metadata.get("est_forward_30d_usd") or 0) for r in records), 2)
