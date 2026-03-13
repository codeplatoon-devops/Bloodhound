"""
Validation event handler.

Responsible for preparing the runtime environment for
validation harness executions.

This ensures validation runs:
- are only triggered by automation
- restrict deletion to explicit validation targets
"""

import os


def handle_validation_event(event):
    """
    Prepare environment for validation teardown runs.

    This function performs safety checks and sets environment
    overrides so the rest of the Bloodhound pipeline behaves
    exactly like a real destructive run — but restricted to
    validation resources.
    """


    # ------------------------------------------------------------
    # Validation invocation guard
    #
    # Ensure validation mode can ONLY be triggered by the
    # validation harness or CI workflow. Slack commands and
    # other invocation sources must never trigger validation.
    # ------------------------------------------------------------
    if event.get("source") != "validation":
        raise RuntimeError(
            "Validation events must originate from validation harness"
        )

    # ------------------------------------------------------------
    # Validate invocation mode
    # ------------------------------------------------------------
    if event.get("mode") != "seek_destroy_validation":
        raise RuntimeError(
            "Invalid validation invocation mode."
        )

    # ------------------------------------------------------------
    # Validation requires explicit resource targets
    # ------------------------------------------------------------
    target_ids = event.get("target_ids", [])

    if not target_ids:
        raise RuntimeError(
            "Validation mode requires target_ids"
        )

    # ------------------------------------------------------------
    # Override runtime configuration
    #
    # This forces Bloodhound into destructive execution mode
    # while restricting deletions to validation targets only.
    # ------------------------------------------------------------
    os.environ["APPLY_CHANGES"] = "true"
    os.environ["TEARDOWN_SIMULATE"] = "false"
    os.environ["TEARDOWN_ALLOW_ALL"] = "false"

    os.environ["TEARDOWN_TARGET_IDS"] = ",".join(target_ids)