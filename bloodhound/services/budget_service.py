"""
bloodhound/services/budget_service.py

Budget monitoring service for Bloodhound v2.

Responsibilities:
- Compute budget snapshot
- Generate formatted Slack budget message
- Post budget alerts

This logic was previously embedded in the main pipeline and
has been extracted into a service module for clarity.
"""

from bloodhound.budget import compute_budget_snapshot
from bloodhound.messages import format_budget_message


def compute_budget(cfg, clients, slack):
    """
    Compute the current budget snapshot and optionally post a Slack notification.

    This function retrieves AWS billing data and calculates the projected
    monthly spend based on the configured cohort budget parameters.

    Args:
        cfg:
            Bloodhound configuration object produced by `load_config()`.
            Must contain the `budget` configuration section.

        clients:
            AWS client container created by `create_clients()`.
            Provides access to required AWS service clients such as
            Cost Explorer.

        slack:
            Optional SlackNotifier instance. If Slack integration is
            enabled, the formatted budget message will be posted to the
            configured alert channel.

    Returns:
        BudgetSnapshot:
            Snapshot object returned by `compute_budget_snapshot`
            containing:

            - projected_month_end_spend_usd
            - dynamic_monthly_allowance_usd
            - over_budget_threshold_met

    Raises:
        RuntimeError:
            If AWS billing APIs fail or return unexpected data.

    Side Effects:
        - Calls AWS Cost Explorer API
        - Posts a budget summary message to Slack alert channel
    
    """

    budget_snapshot = compute_budget_snapshot(
        clients,
        cohort_start_yyyy_mm=cfg.budget.cohort_start_yyyy_mm,
        cohort_total_budget_usd=cfg.budget.cohort_total_budget_usd,
        cohort_length_months=cfg.budget.cohort_length_months,
        budget_over_days=cfg.budget.budget_over_days,
    )

    budget_msg = format_budget_message(budget_snapshot)

    # Always post budget summary to alert channel (keeps scan channel quieter).
    if slack:
        slack.post_alert(budget_msg)

    return budget_snapshot