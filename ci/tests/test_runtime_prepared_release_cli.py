"""Prepared Runtime CLI routing only; the protected caller owns admission."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci.tests import test_runtime_aggregate_tooling_cli as fixtures
from ci import runtime_release


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

    def test_apple_policy_rejects_legacy_and_prepared_signing_before_any_reads(self):
        for target in ("linux-x64", "aggregate"):
            argv = self.case.argv.copy()
            argv[argv.index("--target") + 1] = target
            for prepared in (False, True):
                with self.subTest(target=target, prepared=prepared), redirect_stderr(StringIO()), \
                        patch.dict(runtime_release.os.environ, self.case.environment, clear=True), \
                        patch.object(runtime_release, "read_regular_file_bytes") as read, \
                        patch("product_reuse._canonical_control") as policy_read, \
                        patch.object(runtime_release, "attest_runtime_state_ci") as native, \
                        self.assertRaises(SystemExit) as error:
                    runtime_release.main([*argv, *(self.prepared_flags() if prepared else []),
                        "--sdk-apple-validation-policy", str(self.case.root / "does-not-exist.json")])
                self.assertEqual(2, error.exception.code)
                read.assert_not_called()
                policy_read.assert_not_called()
                native.assert_not_called()

    def test_prepare_only_native_and_aggregate_forward_canonical_policy_and_preserve_omission(self):
        policy = {"callerApplePolicy": "canonical forwarding fixture; admission is mocked"}
        policy_path = self.case.root / "apple-policy.json"
        raw = fixtures.fixture.workflow.canonical_json_bytes(policy)
        policy_path.write_bytes(raw)
        for target in ("linux-x64", "aggregate"):
            argv = self.case.argv.copy()
            argv[argv.index("--target") + 1] = target
            for supplied in (False, True):
                prepare = Mock()
                with self.subTest(target=target, supplied=supplied), \
                        patch.dict(runtime_release.os.environ, self.case.environment, clear=True), \
                        patch.dict("sys.modules", {"runtime_signing_preparation": SimpleNamespace(
                            prepare_runtime_signing_inputs=prepare)}), \
                        patch.object(runtime_release, "attest_runtime_state_ci") as native:
                    runtime_release.main([*argv, "--prepare-only", *(
                        ["--sdk-apple-validation-policy", str(policy_path)] if supplied else [])])
                    prepare.assert_called_once_with(
                        Path("trusted"), Path("candidate"), Path("plan.json"), Path("output"), target=target,
                        expected_build_key=fixtures.fixture.KEY, artifact_id=42,
                        artifact_sha256="sha256:" + "c" * 64, state_wave=5,
                        trusted_source_sha="d" * 40, trusted_workflow_sha="e" * 40,
                        transport_producer={
                            "repository": "owner/repo", "workflowPath": ".github/workflows/ci.yml",
                            "commit": "a" * 40, "tree": "f" * 40, "event": "pull_request",
                            "runId": 12, "runAttempt": 2, "pullRequest": 31,
                        }, event_payload={"number": 31}, environment=runtime_release.os.environ,
                        token="synthetic", sdk_validation_tooling=None,
                        **({"sdk_apple_validation_policy": policy} if supplied else {}))
                    native.assert_not_called()
                self.assertEqual(raw, policy_path.read_bytes())

    def test_prepare_only_malformed_or_missing_apple_policy_never_calls_preparation(self):
        path = self.case.root / "bad-apple-policy.json"
        for raw in (b"{", b"[]\n", b'{ "policy": "noncanonical" }\n', b'{"a":1,"a":2}\n', None):
            if raw is not None:
                path.write_bytes(raw)
            selected = path if raw is not None else self.case.root / "missing-apple-policy.json"
            prepare = Mock()
            with self.subTest(raw=raw), patch.dict(runtime_release.os.environ, self.case.environment, clear=True), \
                    patch.dict("sys.modules", {"runtime_signing_preparation": SimpleNamespace(
                        prepare_runtime_signing_inputs=prepare)}), self.assertRaises((ValueError, OSError)):
                runtime_release.main([*self.case.argv, "--prepare-only", "--sdk-apple-validation-policy", str(selected)])
            prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
