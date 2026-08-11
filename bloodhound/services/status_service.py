"""
bloodhound/services/status_service.py

Status command service for Bloodhound v2.

Responsibilities:
- Handle Slack /v2_status command
- Compute system health indicator
- Post formatted status message to Slack

This module intentionally contains only the logic previously
embedded inside the pipeline so that orchestration code remains
clean and maintainable.
"""

from bloodhound.messages import format_status_message


def handle_status_command(event, cfg, slack, compute_system_health):
    """
    Handle the Slack `/v2_status` command.

    This function generates a system status report describing the current
    operational state of the Bloodhound pipeline including safety flags
    and deletion controls.

    Args:
        event (dict):
            Lambda event payload representing the Slack command request.
            Must contain:
                source="slack_command"
                mode="status"

        cfg:
            Bloodhound configuration object produced by `load_config()`.

        slack:
            Optional SlackNotifier instance used to post the formatted
            status message to the alert channel.

        compute_system_health (callable):
            Function that evaluates system health based on operational
            flags such as teardown mode and budget thresholds.

    Returns:
        dict | None:

        dict
            Returned when a status command is processed:

            {
                "ok": True,
                "mode": "status"
            }

        None
            Returned when the incoming event is not a status command,
            allowing the main pipeline to continue execution.

    Raises:
        RuntimeError:
            If Slack message formatting fails.
    """

    # ------------------------------------------------------------
    # Status command (read-only system overview)
    # ------------------------------------------------------------
    if isinstance(event, dict) and event.get("source") == "slack_command":
        if event.get("mode") == "status":

            health = compute_system_health(
                apply_changes=cfg.teardown.apply_changes,
                allow_all_targets=cfg.teardown.allow_all_targets,
                max_delete_count=cfg.teardown.max_delete_count,
                budget_over_threshold=False,
            )

            status_msg = format_status_message(
                health=health,
                apply_changes=cfg.teardown.apply_changes,
                simulate=cfg.teardown.simulate,
                max_delete_count=cfg.teardown.max_delete_count,
                expected_account_id=getattr(cfg.aws, "expected_account_id", "not-configured"),
                account_verified=True,
                last_scan_resource_total=0,
                last_scan_whitelisted_total=0,
                regions_scanned=0,
            )

            if slack:
                slack.post_alert(status_msg)

            return {
                "ok": True,
                "mode": "status",
            }

    return None