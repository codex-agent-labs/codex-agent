"""Hermetic runner scope for tests that build or consume CompletedFrozenReuse.

The capability reads the consumer's admitted PR scope from the runner
environment. Hosted test jobs run under their own pull_request/merge_group
scope (for example PR 37), which must not leak into fixtures whose consumers
are the RA-pinned PR-31 issuer scope. ``pin_runner_scope`` pins the runner
environment for one test case and restores it afterwards.
"""
import os
from unittest.mock import patch

PR_31_RUNNER = {"GITHUB_REPOSITORY": "codex-agent-labs/codex-agent", "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_REF": "refs/pull/31/merge"}


def pin_runner_scope(case, runner=PR_31_RUNNER):
    """Pin ``os.environ``'s runner scope to ``runner`` for the rest of ``case``."""
    case.enterContext(patch.dict(os.environ, runner))
