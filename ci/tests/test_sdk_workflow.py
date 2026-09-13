"""SDK workflow composition only; mocked authenticated gates are not host evidence."""

from contextlib import ExitStack
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow


class SdkWorkflowTest(unittest.TestCase):
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
