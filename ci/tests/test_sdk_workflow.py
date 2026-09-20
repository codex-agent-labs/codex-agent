"""SDK workflow composition only; mocked authenticated gates are not host evidence."""

from contextlib import ExitStack, nullcontext
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow


class SdkWorkflowTest(unittest.TestCase):
    def test_native_validation_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_validation_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-validation", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_native_metadata_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_metadata_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-metadata", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_verified_inputs_forwards_identical_caller_tooling_to_selection_not_imported_policy(self):
        caller_policy = {"evidence": self.root / "caller-tooling", "policyRevision": self.revision}
        imported_policy = {"evidence": self.root / "untrusted-transported-tooling", "policyRevision": "f" * 40}
        for policy in (caller_policy, None):
            self.inspect.reset_mock()
            captured = {}

            def capture(plan, destination, **kwargs):
                destination.mkdir()
                contract = destination / "contract.json"
                runtime = destination / "runtime.json"
                attestation = destination / "runtime.attestation.json"
                contract.write_bytes(b'{"synthetic":"original Contract receipt boundary"}\n')
                runtime.write_bytes(b'{"buildKey":"sha256:' + b"a" * 64 + b'"}\n')
                attestation.write_bytes(b"synthetic exact original attestation pairing\n")
                captured["sdk"] = {"arguments": {"contract_metadata_receipt": contract,
                    "runtime_metadata_receipt": runtime, "runtime_attestation": attestation,
                    "runtime_keyring": self.root / "captured-runtime-keyring",
                    "runtime_keys_directory": self.root / "captured-runtime-keys"},
                    "sdk_validation_tooling": imported_policy}
                captured["runtime"] = {"indexInputs": {"attestation": attestation}, "receiptBytes": {
                    workflow.PhaseInstanceId("contract", "contract", "metadata", "common"): contract.read_bytes(),
                    workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"): runtime.read_bytes()}}

            # The joined context stands for existing signed-content authority;
            # its exact original receipt pairing has separate full-fixture tests.
            with self.subTest(policy=policy), \
                    patch.object(workflow, "_selection", wraps=workflow._selection) as selected, \
                    patch.object(workflow.product_reuse, "capture_sdk_inputs_upload", side_effect=capture), \
                    patch.object(workflow, "verified_apple_original_inputs",
                                 side_effect=lambda *a, **k: nullcontext(captured)) as verified:
                optional = {"sdk_validation_tooling": policy} if policy is not None else {}
                with workflow.verified_inputs(self.plan, self.discovery, self.state, **self.arguments,
                        **self.upload_for_capture(), **optional) as inputs:
                    captured_path = inputs["capture"]
                    self.assertTrue(captured_path.exists())
                    self.assertIs(imported_policy, inputs["sdk"]["sdk_validation_tooling"])
                    self.assertIs(policy, selected.call_args.kwargs["sdk_validation_tooling"])
                    self.assertEqual(self.revision, verified.call_args.kwargs["selection_revision"])
                    self.assertEqual(self.arguments["keyring"], verified.call_args.kwargs["keyring"])
                    self.assertEqual(self.arguments["keys_directory"], verified.call_args.kwargs["keys_directory"])
                    expected = {"repository_root": self.repository, "environ": self.arguments["environ"],
                                "include_sdk_selection": True, **optional}
                    self.inspect.assert_called_once_with(self.plan, self.discovery, self.state, **expected)
                    if policy is not None:
                        self.assertIs(caller_policy, self.inspect.call_args.kwargs["sdk_validation_tooling"])
                self.assertFalse(captured_path.exists())

    def test_native_package_dispatch_preserves_exact_cli_tail_and_result(self):
        with patch("sdk_native_package_workflow.main", return_value=7) as execute:
            self.assertEqual(7, workflow.main(["native-package", "--plan", "original plan"]))
            execute.assert_called_once_with(["--plan", "original plan"])

    def test_matrix_uses_only_replayed_javascript_package_and_validation(self):
        identities = (("sdk", "javascript", "package", "node"), ("sdk", "javascript", "validation", "node"),
                      ("sdk", "javascript", "metadata", "node"), ("runtime", "jvm", "binary", "jvm"))
        plans = [dict(zip(("product", "component", "phase", "target"), identity), buildKey="sha256:" + "a" * 64)
                 for identity in identities]
        self.inspect.return_value = {"readyPlans": plans}
        output = self.repository / "matrix-output"
        result = workflow.matrix(self.plan, self.discovery, self.state, output,
                                 repository_root=self.repository, environ={})
        self.assertEqual(["package", "validation"], [row["phase"] for row in result["include"]])
        self.assertTrue(all(row["runner"] == "ubuntu-24.04" for row in result["include"]))
        self.assertIn("sdk_workers_required=true", output.read_text())
        self.inspect.return_value = {"readyPlans": []}
        self.assertEqual({"include": []}, workflow.matrix(self.plan, self.discovery, self.state,
            self.repository / "empty-matrix", repository_root=self.repository, environ={}))

    def test_sdk_state_capture_replays_before_exposing_paths(self):
        destination = self.repository / "capture"
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as captured, \
                patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
            result = workflow.capture(self.plan, destination, self.repository / "capture-output",
                **self.upload_for_capture(), sdk_state_wave=1, repository_root=self.repository, environ={}, token="fixture")
        self.assertEqual(1, captured.call_args.kwargs["sdk_state_wave"])
        self.assertEqual(destination / "original/runtime-state", result["state_root"])
        self.assertEqual(destination / "original/product-resume-state", result["discovery_root"])
        self.assertEqual(result["state_root"], matrix.call_args.args[2])
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload"), \
                patch.object(workflow, "matrix", side_effect=ValueError("invalid original state")):
            failed_output = self.repository / "failed-capture-output"
            with self.assertRaisesRegex(ValueError, "invalid original state"):
                workflow.capture(self.plan, destination, failed_output, **self.upload_for_capture(), token="fixture")
            self.assertFalse(failed_output.exists())

    def upload_for_capture(self):
        return {key: self.upload[key] for key in ("artifact_id", "artifact_sha256", "trusted_workflow_sha")}

    def test_collection_preserves_original_roots_and_uses_exact_sdk_partition(self):
        original = self.repository / "original"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            (original / name).mkdir(parents=True)
            (original / name / "original.bin").write_bytes(name.encode())
        identity = {"product": "sdk", "component": "javascript", "phase": "package", "target": "node"}
        for failure in (False, True):
            destination = self.repository / f"collected-{failure}"
            row = {**identity, "result": "failure" if failure else "success", "shardDirectory": "rows/js/original/shard"}

            def advance(*args, **kwargs):
                self.assertTrue(kwargs["sdk_javascript_only"])
                self.assertEqual((workflow.PhaseInstanceId(**identity),) if failure else (), kwargs["failed_instances"])
                self.assertEqual([] if failure else [destination / "collection/rows/js/original/shard"], args[3])
                args[4].mkdir(parents=True)
                return {"synthetic": "advanced"}

            with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]}) as collect, \
                    patch.object(workflow.product_reuse, "advance_products", side_effect=advance), \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.collect(original, destination, self.repository / f"collect-output-{failure}",
                    wave=1, trusted_workflow_sha="c" * 40, repository_root=self.repository, environ={}, token="fixture")
            self.assertTrue(collect.call_args.kwargs["sdk_javascript_only"])
            self.assertEqual({"synthetic": "advanced"}, result)
            self.assertEqual(not failure, matrix.called)
            for name in ("product-resume-inputs", "product-resume-state"):
                self.assertEqual(name.encode(), (destination / "handoff" / name / "original.bin").read_bytes())

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.repository / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"original plan bytes"}\n')
        self.discovery, self.state = self.repository / "discovery", self.repository / "state"
        self.destination = self.root / "fresh-output"
        self.revision = "b" * 40
        self.selection = {"source": "current-runtime", "sdkVersion": "0.8.0", "defaultRuntimeVersion": "0.8.1",
            "compatibleReleaseRange": ">=0.8.0 <0.9.0", "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0",
            "contractVersion": "0.8.0", "contractPayloadSha256": "sha256:" + "c" * 64, "consumers": [
                {"product": "sdk", "component": "python", "phase": "package", "target": "desktop"}]}
        self.arguments = {"keyring": self.root / "keyring.json", "keys_directory": self.root / "keys",
            "repository_root": self.repository, "environ": {"GITHUB_RUN_ID": "7"}, "token": "caller-token"}
        self.upload = {"trusted_workflow_sha": "d" * 40, "artifact_id": 42, "artifact_sha256": "sha256:" + "e" * 64,
            "expected_build_key": "sha256:" + "f" * 64, "expected_metadata_receipt_sha256": "sha256:" + "a" * 64}
        stack = self.enterContext(ExitStack())
        self.validate = stack.enter_context(patch.object(workflow.product_reuse, "_validate_plan",
                                                       return_value={"validationCommit": self.revision}))
        self.inspect = stack.enter_context(patch.object(workflow.product_reuse, "inspect_products",
                                                      return_value={"sdkInputSelection": self.selection}))
        self.released = stack.enter_context(patch.object(workflow.product_reuse, "materialize_sdk_default_inputs",
                                                       return_value={"synthetic": "released result"}))
        self.fresh = stack.enter_context(patch.object(workflow.sdk_handoff, "capture_sdk_handoff",
                                                    return_value={"synthetic": "fresh result"}))

    def stage(self, **changes):
        return workflow.stage(self.plan, self.discovery, self.state, self.destination, **{**self.arguments, **changes})

    def test_current_runtime_forwards_replayed_policy_contract_digest_and_exact_upload(self):
        before = deepcopy(self.selection)
        self.assertEqual({"synthetic": "fresh result"}, self.stage(**self.upload))
        self.validate.assert_called_once_with(self.plan, self.repository)
        self.inspect.assert_called_once_with(self.plan, self.discovery, self.state,
            repository_root=self.repository, environ=self.arguments["environ"], include_sdk_selection=True)
        self.fresh.assert_called_once_with(self.plan, self.destination, **self.upload,
            sdk_version=self.selection["sdkVersion"], compatible_release_range=self.selection["compatibleReleaseRange"],
            compatible_runtime_compatibility_range=self.selection["compatibleRuntimeCompatibilityRange"],
            expected_contract_payload_sha256=self.selection["contractPayloadSha256"],
            keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
            selection_repository_root=self.repository, selection_revision=self.revision,
            repository_root=self.repository, environ=self.arguments["environ"], token=self.arguments["token"])
        self.released.assert_not_called()
        self.assertEqual(before, self.selection)

    def test_released_default_uses_current_replay_materializer_without_upload_identity(self):
        self.selection["source"] = "released-default"
        self.destination = self.repository / "build/sdk-inputs"
        self.assertEqual({"synthetic": "released result"}, self.stage())
        self.released.assert_called_once_with(self.plan, self.discovery, self.state, self.destination,
            keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
            repository_root=self.repository, environ=self.arguments["environ"])
        self.fresh.assert_not_called()

    def test_missing_or_unknown_replayed_selection_never_dispatches(self):
        for selection in (None, "released-default", {}, {**self.selection, "source": "caller-choice"}):
            self.inspect.return_value = {"sdkInputSelection": selection}
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                self.stage(**self.upload)
            self.fresh.assert_not_called()
            self.released.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_current_runtime_requires_every_upload_identity_before_dispatch(self):
        for field in self.upload:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "complete authenticated upload identity"):
                self.stage(**{name: value for name, value in self.upload.items() if name != field})
            self.fresh.assert_not_called()
            self.released.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_changed_plan_and_delegated_failure_never_report_success(self):
        original = self.plan.read_bytes()
        def changed(*args, **kwargs):
            self.plan.write_bytes(original + b"changed\n")
            return {"sdkInputSelection": self.selection}
        self.inspect.side_effect = changed
        with self.assertRaisesRegex(ValueError, "changed during inspection"):
            self.stage(**self.upload)
        self.fresh.assert_not_called()
        self.released.assert_not_called()
        self.plan.write_bytes(original)
        self.inspect.side_effect = None
        for source, delegated in (("current-runtime", self.fresh), ("released-default", self.released)):
            self.selection["source"] = source
            delegated.side_effect = ValueError("original gate rejected")
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "original gate rejected"):
                self.stage(**self.upload)
            self.assertFalse(self.destination.exists())

    def test_cli_forwards_paths_upload_identity_and_environment_without_source_override(self):
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
                 "destination": self.destination, "keyring": self.arguments["keyring"],
                 "keys-directory": self.arguments["keys_directory"], "repository-root": self.repository}
        argv = [value for name, path in paths.items() for value in (f"--{name}", str(path))]
        for name, value in self.upload.items():
            argv.extend(("--" + name.replace("_", "-"), str(value)))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "workflow-token"}, clear=True), patch.object(workflow, "stage") as stage:
            self.assertEqual(0, workflow.main(argv))
            stage.assert_called_once_with(self.plan, self.discovery, self.state, self.destination,
                keyring=self.arguments["keyring"], keys_directory=self.arguments["keys_directory"],
                repository_root=self.repository, **self.upload, environ=os.environ, token="workflow-token")
        with patch.object(workflow, "stage") as stage, self.assertRaises(SystemExit):
            workflow.main([*argv, "--source", "released-default"])
        stage.assert_not_called()
        with patch.object(workflow, "stage", side_effect=ValueError("replay mismatch")), self.assertRaises(SystemExit) as failed:
            workflow.main(argv)
        self.assertEqual(2, failed.exception.code)


if __name__ == "__main__":
    unittest.main()
