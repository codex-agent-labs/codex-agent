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


# Every runner variable that ``producer_scope.consumer_scope`` reads. A hosted pull_request
# job sets GITHUB_HEAD_REF/GITHUB_BASE_REF to the PR branches; left unpinned they leak into a
# merge_group fixture (the head ref is then parsed as a queue branch and rejected).
_SCOPE_VARIABLES = ("GITHUB_REPOSITORY", "GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_HEAD_REF", "GITHUB_BASE_REF")


def pin_runner_scope(case, runner=PR_31_RUNNER):
    """Pin ``os.environ``'s whole runner scope to ``runner`` for the rest of ``case``.

    Scope variables ``runner`` does not name are pinned empty, never inherited.
    """
    pinned = {name: "" for name in _SCOPE_VARIABLES}
    pinned.update(runner)
    case.enterContext(patch.dict(os.environ, pinned))
