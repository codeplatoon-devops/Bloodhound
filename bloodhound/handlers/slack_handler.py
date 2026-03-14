"""
Slack command handler.

Interprets Slack slash commands and configures runtime
environment flags so the Bloodhound pipeline executes
in the correct operational mode.
"""

import os


def handle_slack_event(event):
    """
    Apply Slack command overrides.

    Slack commands never directly execute infrastructure
    operations. They only modify runtime flags before
    the main pipeline runs.
    """

    mode = (event.get("mode") or "").strip()

    # ------------------------------------------------------------
    # /v2_seek
    #
    # Scan-only safe mode.
    # - performs resource scan
    # - generates teardown plan
    # - no deletion allowed
    # ------------------------------------------------------------
    if mode == "seek":

        os.environ["APPLY_CHANGES"] = "false"
        os.environ["TEARDOWN_SIMULATE"] = "true"
        os.environ["TEARDOWN_ALLOW_ALL"] = "false"

    # ------------------------------------------------------------
    # /v2_seek_destroy_plan
    #
    # Preview deletion(teardown) plan but do not execute.
    # - still safe mode
    # ------------------------------------------------------------
    elif mode == "seek_destroy_plan":

        os.environ["APPLY_CHANGES"] = "false"
        os.environ["TEARDOWN_SIMULATE"] = "true"
        os.environ["TEARDOWN_ALLOW_ALL"] = "true"

    # ------------------------------------------------------------
    # /v2_seek_destroy_execute
    #
    # Execute destructive teardown.
    # - executes real AWS deletion APIs
    # - deletes all non-whitelisted resources
    # ------------------------------------------------------------
    elif mode == "seek_destroy_execute":

        os.environ["APPLY_CHANGES"] = "true"
        os.environ["TEARDOWN_SIMULATE"] = "false"
        os.environ["TEARDOWN_ALLOW_ALL"] = "true"