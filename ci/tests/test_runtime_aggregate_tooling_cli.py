"""Aggregate CLI routing only; the mocked protected caller owns all admission."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci.tests import test_runtime_workflow as fixture
from ci import runtime_release


class RuntimeAggregateToolingCliTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-tooling-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        event = self.root / "event.json"
        event.write_bytes(b'{"number":31}\n')
        self.environment = {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REPOSITORY": "owner/repo", "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_TOKEN": "synthetic"}
        self.policy = {"evidence": str(self.root / "evidence"), "publicKey": str(self.root / "public.pub"),
            "javaExecutable": str(self.root / "java"), "requiredTrustDomain": "release",
            "keyring": str(self.root / "keyring.json"), "keysDirectory": str(self.root / "keys")}
        self.policy_path = self.root / "policy.json"
        self.policy_path.write_bytes(fixture.workflow.canonical_json_bytes(self.policy))
        self.argv = [value for name, argument in {
            "repository-root": "trusted", "candidate-root": "candidate", "plan": "plan.json",
            "destination": "output", "target": "aggregate", "expected-build-key": fixture.KEY,
            "artifact-sha256": "sha256:" + "c" * 64, "artifact-id": "42", "state-wave": "5",
            "trusted-source-sha": "d" * 40, "trusted-workflow-sha": "e" * 40,
            "validation-tree": "f" * 40}.items() for value in ("--" + name, argument)]

    def test_canonical_policy_and_legacy_none_reach_fresh_and_retained_aggregate_caller(self):
        variants = {target: Path("originals") / target for target in runtime_release.NATIVE_TARGETS}
        for retained in (False, True):
            for supplied in (False, True):
                aggregate = Mock()
                handoffs = (["--release-handoff", "original-release"] if retained else
                    [value for target, path in variants.items() for value in ("--variant-handoff", f"{target}={path}")])
                with self.subTest(retained=retained, supplied=supplied), \
                        patch.dict(runtime_release.os.environ, self.environment, clear=True), \
                        patch.dict("sys.modules", {"runtime_aggregate_release": SimpleNamespace(
                            attest_runtime_aggregate_state_ci=aggregate)}), \
                        patch.object(runtime_release, "attest_runtime_state_ci") as native:
                    runtime_release.main(self.argv + handoffs + (
                        ["--sdk-validation-tooling", str(self.policy_path)] if supplied else []))
                    aggregate.assert_called_once_with(Path("trusted"), Path("candidate"), Path("plan.json"), Path("output"),
                        variant_handoffs={} if retained else variants, expected_build_key=fixture.KEY,
                        artifact_id=42, artifact_sha256="sha256:" + "c" * 64, state_wave=5,
                        trusted_source_sha="d" * 40, trusted_workflow_sha="e" * 40,
                        transport_producer={"repository": "owner/repo", "workflowPath": ".github/workflows/ci.yml",
                            "commit": "a" * 40, "tree": "f" * 40, "event": "pull_request",
                            "runId": 12, "runAttempt": 2, "pullRequest": 31},
                        event_payload={"number": 31}, environment=runtime_release.os.environ, token="synthetic",
                        release_handoffs=(Path("original-release"),) if retained else (),
                        sdk_validation_tooling=self.policy if supplied else None)
                    native.assert_not_called()
                self.assertEqual(fixture.workflow.canonical_json_bytes(self.policy), self.policy_path.read_bytes())

    def test_malformed_or_missing_policy_cannot_reach_any_protected_caller(self):
        for raw in (b"{", b"[]\n", b'{ "evidence": "value" }\n', b'{"a":1,"a":2}\n', None):
            if raw is not None:
                self.policy_path.write_bytes(raw)
            path = self.policy_path if raw is not None else self.root / "absent-policy.json"
            aggregate = Mock()
            with self.subTest(raw=raw), patch.dict(runtime_release.os.environ, self.environment, clear=True), \
                    patch.dict("sys.modules", {"runtime_aggregate_release": SimpleNamespace(
                        attest_runtime_aggregate_state_ci=aggregate)}), \
                    patch.object(runtime_release, "attest_runtime_state_ci") as native:
                with self.assertRaises((ValueError, OSError)):
                    runtime_release.main(self.argv + ["--sdk-validation-tooling", str(path)])
                aggregate.assert_not_called()
                native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
