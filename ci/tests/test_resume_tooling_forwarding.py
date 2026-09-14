"""Resumed matrix policy routing, not original product or signature admission."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_workflow as fixture
from ci.products.inventory import canonical_json_bytes


workflow = fixture.workflow


class ResumeToolingForwardingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="resume-tooling-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.paths = tuple(self.root / name for name in ("plan", "discovery", "state"))
        self.output = self.root / "github-output"
        self.policy_path = self.root / "caller-policy.json"
        self.policy = {"evidence": str(self.root / "evidence"), "publicKey": str(self.root / "public.pub"),
            "javaExecutable": str(self.root / "java"), "requiredTrustDomain": "release",
            "keyring": str(self.root / "keyring.json"), "keysDirectory": str(self.root / "keys")}
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.environment = {"GITHUB_RUN_ID": "7"}
        self.value = {"include": [fixture.row(fixture.JVM), fixture.row(fixture.SUPERVISOR)]}

    def argv(self):
        return ["matrix", *(value for key, path in zip(("plan", "discovery-root", "state-root", "github-output"),
            (*self.paths, self.output)) for value in ("--" + key, str(path)))]

    def test_optional_policy_reaches_existing_replay_unchanged_and_never_enters_matrix(self):
        before = deepcopy(self.policy)
        for supplied in (False, True):
            optional = {"sdk_validation_tooling": self.policy} if supplied else {}
            with self.subTest(supplied=supplied), \
                    patch.object(workflow.products, "runtime_worker_matrix", return_value=self.value) as replay:
                self.assertEqual(self.value, workflow.matrix(*self.paths, self.output,
                    repository_root=self.root, environ=self.environment, **optional))
                replay.assert_called_once_with(*self.paths, repository_root=self.root, environ=self.environment, **optional)
                if supplied:
                    self.assertIs(self.policy, replay.call_args.kwargs["sdk_validation_tooling"])
            outputs = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
            self.assertEqual({"runtime_matrix", "runtime_workers_required", "supervisor_key"}, set(outputs))
            self.assertEqual(canonical_json_bytes(self.value).decode().strip(), outputs["runtime_matrix"])
            self.assertEqual(fixture.KEY, outputs["supervisor_key"])
            self.assertNotIn(str(self.policy_path), self.output.read_text())
            self.assertEqual(before, self.policy)

    def test_cli_loads_canonical_policy_and_preserves_omitted_call_shape(self):
        for supplied in (False, True):
            with self.subTest(supplied=supplied), patch.object(workflow, "matrix") as matrix:
                argv = self.argv() + (["--sdk-validation-tooling", str(self.policy_path)] if supplied else [])
                self.assertEqual(0, workflow.main(argv))
                matrix.assert_called_once_with(*self.paths, self.output,
                    **({"sdk_validation_tooling": self.policy} if supplied else {}))
        for raw in (b"{", b"[]\n", b'{ "evidence": "value" }\n', b'{"a":1,"a":2}\n'):
            with self.subTest(raw=raw), patch.object(workflow, "matrix") as matrix:
                self.policy_path.write_bytes(raw)
                with self.assertRaises(SystemExit) as failure:
                    workflow.main(self.argv() + ["--sdk-validation-tooling", str(self.policy_path)])
                self.assertEqual(2, failure.exception.code)
                matrix.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_replay_failure_with_policy_never_exposes_worker_election(self):
        with patch.object(workflow.products, "runtime_worker_matrix", side_effect=ValueError("original replay rejected")) as replay:
            with self.assertRaisesRegex(ValueError, "original replay rejected"):
                workflow.matrix(*self.paths, self.output, sdk_validation_tooling=self.policy)
        self.assertIs(self.policy, replay.call_args.kwargs["sdk_validation_tooling"])
        self.assertFalse(self.output.exists())

    def test_capture_policy_is_replay_only_and_reaches_aggregate_continuation(self):
        aggregate = workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        for supplied in (False, True):
            for instance in (None, aggregate):
                optional = {"sdk_validation_tooling": self.policy} if supplied else {}
                destination = self.root / "capture"
                with self.subTest(supplied=supplied, instance=instance), \
                        patch.object(workflow.products, "capture_runtime_resume_upload") as transport, \
                        patch.object(workflow, "matrix", return_value={"include": []}) as matrix, \
                        patch.object(workflow, "continuation", return_value={"aggregate": {
                            "state": "ready", "buildKey": fixture.KEY}}) as continuation:
                    result = workflow.capture(self.paths[0], destination, self.output,
                        artifact_id=7, artifact_sha256=fixture.KEY, trusted_workflow_sha="a" * 40,
                        state_wave=4, instance=instance, expected_build_key=fixture.KEY if instance else None,
                        repository_root=self.root, environ=self.environment, token="synthetic", **optional)
                    transport.assert_called_once_with(self.paths[0], destination,
                        artifact_id=7, artifact_sha256=fixture.KEY, trusted_workflow_sha="a" * 40,
                        state_wave=4, repository_root=self.root, environ=self.environment, token="synthetic")
                    replay_args = (result["plan_path"], result["discovery_root"], result["state_root"], self.output)
                    replay_kwargs = {"repository_root": self.root, "environ": self.environment, **optional}
                    matrix.assert_called_once_with(*replay_args, **replay_kwargs)
                    if instance:
                        continuation.assert_called_once_with(*replay_args, **replay_kwargs)
                    else:
                        continuation.assert_not_called()
                    if supplied:
                        self.assertIs(self.policy, matrix.call_args.kwargs["sdk_validation_tooling"])
                        if instance:
                            self.assertIs(self.policy, continuation.call_args.kwargs["sdk_validation_tooling"])
                    self.assertNotIn("sdk_validation_tooling", result)

    def test_capture_cli_canonical_policy_and_malformed_rejection_before_transport(self):
        destination = self.root / "cli-capture"
        argv = ["capture", "--plan", str(self.paths[0]), "--destination", str(destination),
            "--github-output", str(self.output), "--artifact-id", "7", "--artifact-sha256", fixture.KEY,
            "--trusted-workflow-sha", "a" * 40, "--component", "runtime-aggregate",
            "--phase", "metadata", "--target", "aggregate", "--expected-build-key", fixture.KEY]
        for supplied in (False, True):
            with self.subTest(supplied=supplied), patch.object(workflow, "capture") as capture, \
                    patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "synthetic"}):
                self.assertEqual(0, workflow.main(argv + (
                    ["--sdk-validation-tooling", str(self.policy_path)] if supplied else [])))
                capture.assert_called_once_with(self.paths[0], destination, self.output,
                    artifact_id=7, artifact_sha256=fixture.KEY, trusted_workflow_sha="a" * 40, state_wave=0,
                    instance=workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
                    expected_build_key=fixture.KEY, token="synthetic",
                    **({"sdk_validation_tooling": self.policy} if supplied else {}))
        for raw in (b"{", b"[]\n", b'{ "evidence": "value" }\n', b'{"a":1,"a":2}\n'):
            with self.subTest(raw=raw), patch.object(workflow, "capture") as capture:
                self.policy_path.write_bytes(raw)
                with self.assertRaises(SystemExit) as failure:
                    workflow.main(argv + ["--sdk-validation-tooling", str(self.policy_path)])
                self.assertEqual(2, failure.exception.code)
                capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
