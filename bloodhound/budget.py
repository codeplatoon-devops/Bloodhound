from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from bloodhound.aws import AwsClients


@dataclass(frozen=True)
class BudgetSnapshot:
    cohort_start_yyyy_mm: str
    cohort_total_budget_usd: float
    cohort_length_months: int

    cohort_to_date_spend_usd: float
    remaining_cohort_budget_usd: float
    remaining_months: int
    dynamic_monthly_allowance_usd: float

    current_month_to_date_spend_usd: float
    projected_month_end_spend_usd: float

    budget_over_days: int
    over_budget_threshold_met: bool


def compute_budget_snapshot(
    clients: AwsClients,
    cohort_start_yyyy_mm: str,
    cohort_total_budget_usd: float,
    cohort_length_months: int,
    budget_over_days: int,
    today: date | None = None,
) -> BudgetSnapshot:
    today = today or date.today()

    start_year, start_month = _parse_yyyy_mm(cohort_start_yyyy_mm)
    cohort_start = date(start_year, start_month, 1)

    # Cost Explorer is effectively "global"; us-east-1 is the common choice.
    ce = clients.client("ce", region="us-east-1")

    # Cohort-to-date monthly spend
    cohort_to_date = _get_cost_monthly_total(ce, start=cohort_start, end=today + timedelta(days=1))

    # Current month daily spend for MTD + "over budget X days" streak computation
    month_start = date(today.year, today.month, 1)
    daily_costs = _get_cost_daily(ce, start=month_start, end=today + timedelta(days=1))
    mtd_spend = sum(daily_costs.values())

    remaining_budget = max(0.0, cohort_total_budget_usd - cohort_to_date)
    remaining_months = _remaining_months(cohort_start, cohort_length_months, today)
    allowance = remaining_budget / remaining_months if remaining_months > 0 else remaining_budget

    projected_month_end = _project_month_end(mtd_spend, today)
    over_met = _over_budget_threshold_met(
        daily_costs=daily_costs,
        days_in_month=calendar.monthrange(today.year, today.month)[1],
        monthly_allowance_usd=allowance,
        budget_over_days=budget_over_days,
    )

    return BudgetSnapshot(
        cohort_start_yyyy_mm=cohort_start_yyyy_mm,
        cohort_total_budget_usd=cohort_total_budget_usd,
        cohort_length_months=cohort_length_months,
        cohort_to_date_spend_usd=cohort_to_date,
        remaining_cohort_budget_usd=remaining_budget,
        remaining_months=remaining_months,
        dynamic_monthly_allowance_usd=allowance,
        current_month_to_date_spend_usd=mtd_spend,
        projected_month_end_spend_usd=projected_month_end,
        budget_over_days=budget_over_days,
        over_budget_threshold_met=over_met,
    )


def _parse_yyyy_mm(raw: str) -> tuple[int, int]:
    try:
        dt = datetime.strptime(raw, "%Y-%m")
        return dt.year, dt.month
    except ValueError:
        # Fall back to current month; validation should catch missing/invalid.
        today = date.today()
        return today.year, today.month


def _to_ce_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _get_cost_monthly_total(ce_client, start: date, end: date) -> float:
    """
    Returns the sum of monthly UnblendedCost between [start, end) dates.
    Cost Explorer end is exclusive.
    """
    resp = ce_client.get_cost_and_usage(
        TimePeriod={"Start": _to_ce_date(start), "End": _to_ce_date(end)},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    total = 0.0
    for r in resp.get("ResultsByTime", []) or []:
        amt = ((r.get("Total") or {}).get("UnblendedCost") or {}).get("Amount")
        if not amt:
            continue
        try:
            total += float(amt)
        except ValueError:
            continue
    return total


def _get_cost_daily(ce_client, start: date, end: date) -> dict[date, float]:
    """
    Returns a mapping of day -> UnblendedCost between [start, end).
    """
    resp = ce_client.get_cost_and_usage(
        TimePeriod={"Start": _to_ce_date(start), "End": _to_ce_date(end)},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    out: dict[date, float] = {}
    for r in resp.get("ResultsByTime", []) or []:
        start_str = (r.get("TimePeriod") or {}).get("Start")
        if not start_str:
            continue
        try:
            day = datetime.strptime(start_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        amt = ((r.get("Total") or {}).get("UnblendedCost") or {}).get("Amount")
        try:
            out[day] = float(amt) if amt is not None else 0.0
        except ValueError:
            out[day] = 0.0
    return out


def _remaining_months(cohort_start: date, cohort_length_months: int, today: date) -> int:
    """
    Remaining months INCLUDING current month, clamped to at least 1 while inside cohort.
    """
    months_elapsed = (today.year - cohort_start.year) * 12 + (today.month - cohort_start.month)
    remaining = cohort_length_months - months_elapsed
    return max(1, remaining)


def _project_month_end(mtd_spend_usd: float, today: date) -> float:
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_elapsed = max(1, today.day)
    return (mtd_spend_usd / days_elapsed) * days_in_month


def _over_budget_threshold_met(
    daily_costs: dict[date, float],
    days_in_month: int,
    monthly_allowance_usd: float,
    budget_over_days: int,
) -> bool:
    """
    Minimal, state-free approach:
    - Look at the last N days present in daily_costs.
    - For each day, compute what the month-end projection would be at that point.
    - If all N projections exceed monthly_allowance_usd, threshold is met.
    """
    if budget_over_days <= 0:
        return False
    if not daily_costs:
        return False

    days = sorted(daily_costs.keys())
    last_days = days[-budget_over_days:]
    if len(last_days) < budget_over_days:
        return False

    # cumulative spend up to each day (inclusive)
    cumulative = 0.0
    day_to_cumulative: dict[date, float] = {}
    for d in days:
        cumulative += daily_costs.get(d, 0.0)
        day_to_cumulative[d] = cumulative

    for d in last_days:
        days_elapsed = d.day
        if days_elapsed <= 0:
            return False
        projection = (day_to_cumulative[d] / days_elapsed) * days_in_month
        if projection <= monthly_allowance_usd:
            return False
    return True


