"""Prepared Runtime CLI routing only; the protected caller owns admission."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci import runtime_release
from ci.tests import test_runtime_aggregate_tooling_cli as fixtures


class RuntimePreparedReleaseCliTest(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.RuntimeAggregateToolingCliTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.preparation_id = 93
        self.preparation_digest = "sha256:" + "9" * 64

    def prepared_flags(self):
        return ["--preparation-artifact-id", str(self.preparation_id),
                "--preparation-artifact-sha256", self.preparation_digest]

    def test_native_and_aggregate_dispatch_exact_prepared_caller_arguments(self):
        for target in ("linux-x64", "aggregate"):
            with self.subTest(target=target):
                argv = self.case.argv.copy()
                argv[argv.index("--target") + 1] = target
                variants = ({name: Path("originals") / name for name in runtime_release.NATIVE_TARGETS}
                            if target == "aggregate" else {})
                variant_flags = [value for name, path in variants.items()
                                 for value in ("--variant-handoff", f"{name}={path}")]
                prepared = Mock()
                with patch.dict(runtime_release.os.environ, self.case.environment, clear=True), \
                        patch.dict("sys.modules", {"runtime_prepared_release": SimpleNamespace(
                            attest_prepared_runtime_ci=prepared)}), \
                        patch.object(runtime_release, "attest_runtime_state_ci") as legacy:
                    runtime_release.main([*argv, *variant_flags, *self.prepared_flags()])
                prepared.assert_called_once_with(
                    Path("trusted"), Path("candidate"), Path("plan.json"), Path("output"),
                    target=target, variant_handoffs=variants,
                    preparation_artifact_id=self.preparation_id,
                    preparation_artifact_sha256=self.preparation_digest,
                    expected_build_key=fixtures.fixture.KEY, artifact_id=42,
                    artifact_sha256="sha256:" + "c" * 64, state_wave=5,
                    trusted_source_sha="d" * 40, trusted_workflow_sha="e" * 40,
                    transport_producer={
                        "repository": "owner/repo", "workflowPath": ".github/workflows/ci.yml",
                        "commit": "a" * 40, "tree": "f" * 40, "event": "pull_request",
                        "runId": 12, "runAttempt": 2, "pullRequest": 31,
                    }, event_payload={"number": 31}, environment=runtime_release.os.environ,
                    token="synthetic")
                legacy.assert_not_called()

    def test_incomplete_or_conflicting_prepared_mode_rejects_before_event_or_policy_reads(self):
        cases = (
            ["--preparation-artifact-id", str(self.preparation_id)],
            ["--preparation-artifact-sha256", self.preparation_digest],
            [*self.prepared_flags(), "--prepare-only"],
            [*self.prepared_flags(), "--sdk-validation-tooling", str(self.case.policy_path)],
            ["--preparation-artifact-id", str(self.preparation_id),
             "--sdk-validation-tooling", str(self.case.policy_path)],
            [*self.prepared_flags(), "--release-handoff", "untrusted-override"],
        )
        for selected in cases:
            with self.subTest(selected=selected), redirect_stderr(StringIO()), \
                    patch.dict(runtime_release.os.environ, self.case.environment, clear=True), \
                    patch.object(runtime_release, "read_regular_file_bytes") as read, \
                    self.assertRaises(SystemExit) as error:
                runtime_release.main([*self.case.argv, *selected])
            self.assertEqual(2, error.exception.code)
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
