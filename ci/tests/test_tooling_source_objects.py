"""Exact original Git object availability for retained tooling evidence."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import tooling_capture  # noqa: E402


COMMIT = "a" * 40
TREE = "b" * 40
HEAD = "c" * 40
REMOTE = "https://github.com/codex-agent-labs/codex-agent.git"


class ToolingSourceObjectsTest(unittest.TestCase):
    def setUp(self):
        self.repository = Path("/synthetic/repository")
        self.producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "merge_group",
            "runId": 71,
            "runAttempt": 2,
            "pullRequest": None,
        }

    def test_present_objects_are_verified_without_fetch(self):
        with mock.patch.object(tooling_capture, "run_git", side_effect=(
            HEAD, "", COMMIT, TREE, HEAD,
        )) as git:
            tooling_capture._ensure_original_source(self.repository, self.producer)
        self.assertEqual([
            mock.call(self.repository, "rev-parse", "HEAD"),
            mock.call(self.repository, "cat-file", "-e", f"{COMMIT}^{{commit}}"),
            mock.call(self.repository, "rev-parse", f"{COMMIT}^{{commit}}"),
            mock.call(self.repository, "rev-parse", f"{COMMIT}^{{tree}}"),
            mock.call(self.repository, "rev-parse", "HEAD"),
        ], git.call_args_list)

    def test_missing_commit_fetches_only_the_exact_fixed_source_then_checks_identity(self):
        missing = subprocess.CalledProcessError(1, ["git", "cat-file"])
        with mock.patch.object(tooling_capture, "run_git", side_effect=(
            HEAD, missing, "", COMMIT, TREE, HEAD,
        )) as git:
            tooling_capture._ensure_original_source(self.repository, self.producer)
        self.assertEqual(
            mock.call(
                self.repository, "fetch", "--no-tags", "--no-write-fetch-head",
                "--no-recurse-submodules", "--no-auto-maintenance", REMOTE, COMMIT,
            ),
            git.call_args_list[2],
        )
        self.assertEqual(mock.call(self.repository, "rev-parse", f"{COMMIT}^{{tree}}"),
                         git.call_args_list[4])
        self.assertFalse(any("checkout" in call.args for call in git.call_args_list))

    def test_wrong_source_identity_and_invalid_object_ids_reject_before_git(self):
        cases = (
            {**self.producer, "repository": "attacker/repository"},
            {**self.producer, "workflowPath": ".github/workflows/other.yml"},
            {**self.producer, "commit": "A" * 40},
        )
        for producer in cases:
            with self.subTest(producer=producer), \
                    mock.patch.object(tooling_capture, "run_git") as git, \
                    self.assertRaises(ValueError):
                tooling_capture._ensure_original_source(self.repository, producer)
            git.assert_not_called()

    def test_tree_mismatch_rejects(self):
        with mock.patch.object(tooling_capture, "run_git", side_effect=(
            HEAD, "", COMMIT, "d" * 40, HEAD,
        )):
            with self.assertRaisesRegex(ValueError, "source identity"):
                tooling_capture._ensure_original_source(self.repository, self.producer)

    def test_changed_caller_head_rejects(self):
        with mock.patch.object(tooling_capture, "run_git", side_effect=(
            HEAD, "", COMMIT, TREE, "d" * 40,
        )):
            with self.assertRaisesRegex(ValueError, "caller HEAD changed"):
                tooling_capture._ensure_original_source(self.repository, self.producer)


if __name__ == "__main__":
    unittest.main()
