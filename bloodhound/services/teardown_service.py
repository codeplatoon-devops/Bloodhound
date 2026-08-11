"""
bloodhound/services/teardown_service.py

Teardown planning and execution service for Bloodhound v2.

Responsibilities:
- Perform validation safety checks
- Plan deletion actions
- Execute AWS resource teardown
- Post Slack teardown reports

This module contains logic extracted from execute_pipeline()
without altering behavior.

# ------------------------------------------------------------
# WARNING
#
# This module performs destructive AWS operations including
# permanent deletion of infrastructure resources.
#
# All safety guards MUST remain intact.
# ------------------------------------------------------------
"""

import json

from bloodhound.teardown.planner import plan_deletions
from bloodhound.teardown.executor import execute_actions
from bloodhound.messages import (
    format_teardown_plan_message,
    format_teardown_result_message,
)


def plan_teardown(cfg, event, all_candidates, slack):
    """
    Generate the teardown plan and enforce validation safety checks.

    This function validates teardown targets (when running in validation
    mode) and builds the list of resource deletion actions using the
    teardown planner.

    Args:
        cfg:
            Bloodhound configuration object produced by `load_config()`.
            Contains teardown safety parameters and target filters.

        event (dict):
            Invocation event used to determine execution mode
            (Slack command, validation harness, scheduled run).

        all_candidates (list):
            Flattened list of candidate resources returned by the scan
            phase. Each resource object must contain:

                id
                arn
                region
                tags

        slack:
            Optional SlackNotifier instance used to post the teardown
            plan summary.

    Returns:
        list:
            List of planned teardown action objects returned by
            `plan_deletions()`.

    Raises:
        RuntimeError:
            If validation safety checks fail or invalid teardown
            targets are detected.

    Side Effects:
        - Posts teardown plan summary to Slack alert channel
    """

    # ------------------------------------------------------------------
    # Validation Safety Guard
    #
    # When running validation mode, ensure that:
    #
    #   1. Target IDs exist in scan results
    #   2. Target IDs reference resources tagged for validation
    #
    # This prevents accidental deletion of unrelated infrastructure.
    # ------------------------------------------------------------------

    if isinstance(event, dict) and event.get("source") == "validation":

        validation_targets = set(cfg.teardown.target_ids)

        candidate_ids = {r.id for r in all_candidates}

        tagged_resources = {
            r.id
            for r in all_candidates
            if r.tags.get("bloodhound:test") == "true"
        }

        # Ensure targets exist in scan results
        if not validation_targets.issubset(candidate_ids):

            invalid_targets = validation_targets - candidate_ids

            raise RuntimeError(
                f"Validation safety check failed. "
                f"Targets not present in scan results: {sorted(invalid_targets)}"
            )

        # Ensure targets are validation-tagged resources
        if not validation_targets.issubset(tagged_resources):

            invalid_targets = validation_targets - tagged_resources

            raise RuntimeError(
                f"Validation safety check failed. "
                f"Targets missing validation tag: {sorted(invalid_targets)}"
            )

    actions, _manual = plan_deletions(all_candidates)

    if slack:
        slack.post_alert(
            format_teardown_plan_message(
                actions,
                apply_changes=cfg.teardown.apply_changes,
                simulate=cfg.teardown.simulate,
                targets_filter_count=len(cfg.teardown.target_ids),
                allow_all=cfg.teardown.allow_all_targets,
            )
        )

    return actions


def execute_teardown(cfg, event, clients, actions, slack, resource_key_from_action):
    """
    Execute planned teardown actions against AWS resources.

    This function applies deletion operations for resources selected
    by the teardown planner. Execution behavior is controlled by the
    configuration flags for simulation mode, validation mode, and
    explicit target filtering.

    Args:
        cfg:
            Bloodhound configuration object produced by `load_config()`.

        event (dict):
            Invocation event used to determine validation mode or
            Slack command execution mode.

        clients:
            AWS client container created by `create_clients()`.

        actions (list):
            List of teardown action objects produced by `plan_teardown()`.

        slack:
            Optional SlackNotifier instance used to post execution
            results to the alert channel.

        resource_key_from_action (callable):
            Helper function that converts an action object into the
            canonical resource key format used for target filtering.

    Returns:
        dict | None:

        dict
            Execution summary containing:

            attempted
            succeeded
            failed
            simulated
            failures
            targets_filter
            planned_actions_total
            executed_actions_total
            allow_all_targets

        None
            Returned when destructive execution is disabled.

    Raises:
        RuntimeError:
            If AWS deletion operations fail unexpectedly.

    Side Effects:
        - Calls AWS deletion APIs (EC2, RDS, etc.)
        - Permanently deletes AWS infrastructure
        - Posts execution summary to Slack alert channel

    
    """

    exec_summary = None

    if cfg.teardown.apply_changes:

        actions_to_execute = actions

        # ------------------------------------------------------------
        # Validation safety filter
        #
        # When validation mode is active, restrict deletion to resources
        # tagged specifically for validation runs.
        # ------------------------------------------------------------
        validation_mode = isinstance(event, dict) and event.get("validation") is True

        if validation_mode:
            actions_to_execute = [
                a for a in actions
                if getattr(a, "tags", {}).get("bloodhound:test") == "true"
            ]

        elif cfg.teardown.target_ids:

            targets = cfg.teardown.target_ids

            actions_to_execute = [
                a
                for a in actions
                if (
                    (a.id in targets)
                    or (a.arn and a.arn in targets)
                    or (resource_key_from_action(a) in targets)
                )
            ]

        exec_result = execute_actions(
            clients,
            actions_to_execute,
            simulate=cfg.teardown.simulate
        )

        exec_summary = {
            "attempted": exec_result.attempted,
            "succeeded": exec_result.succeeded,
            "failed": exec_result.failed,
            "simulated": exec_result.simulated,
            "failures": exec_result.failures[:20],
            "targets_filter": sorted(cfg.teardown.target_ids) if cfg.teardown.target_ids else None,
            "planned_actions_total": len(actions),
            "executed_actions_total": len(actions_to_execute),
            "allow_all_targets": cfg.teardown.allow_all_targets,
        }

        if slack:
            slack.post_alert(
                format_teardown_result_message(
                    attempted=exec_result.attempted,
                    succeeded=exec_result.succeeded,
                    failed=exec_result.failed,
                    simulated=exec_result.simulated,
                )
                + "\n"
                + json.dumps(exec_summary, indent=2)
            )

    return exec_summary