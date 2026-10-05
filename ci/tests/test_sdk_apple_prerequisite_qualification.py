"""Focused qualification composition tests; not genuine Apple execution evidence."""
from argparse import Namespace
from contextlib import ExitStack
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[2] / ".github/actions/run-ci-lane/sdk_native_qualification.py"
SPEC = importlib.util.spec_from_file_location("sdk_native_qualification_test", PATH)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class ApplePrerequisiteQualificationTest(unittest.TestCase):
    def test_complete_registered_inputs_and_test_inputs_are_required(self):
        inventory = [{"relativePath": "native/input", "bytes": 1, "sha256": "sha256:" + "1" * 64}]
        with patch.object(helper, "phase_git_inventory", return_value=inventory) as lookup:
            records = helper.compatible_source_inventories(Path("."), "a" * 40, "b" * 40,
                                                          "ios-native-tests")
            self.assertEqual(3, len(records))
            self.assertEqual(6, lookup.call_count)
            self.assertEqual({("binary", "ios"), ("validation", "ios-arm64"),
                              ("validation", "ios-simulator-arm64")},
                             {(x["phase"], x["target"]) for x in records})
        with patch.object(helper, "phase_git_inventory", side_effect=[inventory, []]):
            with self.assertRaisesRegex(ValueError, "byte-affecting"):
                helper.compatible_source_inventories(Path("."), "a" * 40, "b" * 40,
                                                     "ios-rust-simulator")

    def _qualify(self, *, fail_observer=False, change_source=False, retained_body=False,
                 corrupt_body=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        plan_path = root / "current-plan.json"
        plan_path.write_bytes(b"current plan\n")
        original_receipt = b'{"original":"receipt"}\n'
        producer = {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
                    "commit": "a" * 40, "tree": "c" * 40, "event": "pull_request",
                    "pullRequest": 31, "runId": 17, "runAttempt": 2}
        plan = {**producer, "validationCommit": "b" * 40, "validationTree": "d" * 40,
                "remoteBuildAuthorized": True}
        old = {**plan, "validationTree": producer["tree"]}
        body = b"original immutable upload"
        artifact = {"id": 7, "digest": helper.sha256_bytes(body), "expired": False,
                    "size_in_bytes": len(body),
                    "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/7/zip"}
        observation = {"run": {"id": 17}, "jobs": []}
        args = Namespace(plan=plan_path, lane="ios-rust-simulator", token="observation-token",
                         runner=["os=macOS"], toolchain=["rustc=pinned"])
        output = root / "qualified"
        def extract(archive, destination):
            destination.mkdir()
            if archive.name == "original-upload.zip":
                (destination / "lane-receipt.json").write_bytes(original_receipt)
            else:
                (destination / "impact-plan.json").write_bytes(b"original plan\n")
        def download(artifact, token, destination, **kwargs):
            destination.write_bytes(b"original immutable upload")
        with ExitStack() as stack:
            def mock(name, **kwargs):
                return stack.enter_context(patch.object(helper, name, **kwargs))
            def control(name, **kwargs):
                return stack.enter_context(patch.object(helper.product_reuse, name, **kwargs))
            control("_validate_plan", side_effect=[plan, old])
            control("api_json", side_effect=[artifact, observation["run"]])
            downloaded = control("download_artifact_to_file", side_effect=download)
            mock("_extract", side_effect=extract)
            mock("_receipt_producer", return_value=producer)
            control("_runtime_prior_workflow_sha", return_value="e" * 40)
            observe = control("_observe_ci_producer_jobs", return_value=[observation],
                **({"side_effect": ValueError("original job failed")} if fail_observer else {}))
            control("_contract_ci_upload_metadata", return_value=artifact)
            window = control("_require_artifact_job_window")
            control("paginated_items", return_value=[])
            mock("_original_upload", return_value=({"id": 8}, b"original plan archive"))
            mock("_private_original_repository", return_value=root)
            receipt_gate = mock("validate_receipt", return_value={})
            content_gate = mock("_native_lane_content", return_value=({}, producer))
            mock("compatible_source_inventories", return_value=[{"inventorySha256": "sha256:" + "2" * 64}],
                **({"side_effect": ValueError("source changed")} if change_source else {}))
            kwargs = {"archive_bytes": b"corrupt" if corrupt_body else body} if retained_body else {}
            if fail_observer or change_source or corrupt_body:
                with self.assertRaises(ValueError):
                    helper.qualify_candidate(args, artifact, trusted_workflow_sha="e" * 40,
                                             repository_root=root, output=output, **kwargs)
                self.assertFalse(output.exists())
                return
            result = helper.qualify_candidate(args, artifact, trusted_workflow_sha="e" * 40,
                                               repository_root=root, output=output, **kwargs)
            self.assertEqual(0 if retained_body else 1, downloaded.call_count)
            observe.assert_called_once()
            window.assert_called_once()
            receipt_gate.assert_called_once()
            self.assertEqual({"os": "macOS"}, receipt_gate.call_args.kwargs["runner"])
            self.assertEqual({"rustc": "pinned"}, receipt_gate.call_args.kwargs["toolchain"])
            content_gate.assert_called_once()
            self.assertIsNone(content_gate.call_args.args[4])
            self.assertEqual(original_receipt, (output / "lane/lane-receipt.json").read_bytes())
            self.assertEqual(b"original immutable upload", (output / "original-upload.zip").read_bytes())
            self.assertEqual(producer, result["originalProducer"])
            self.assertTrue(result["semanticAdmissionRequired"])
            self.assertNotIn("observation-token", (output / "qualification.json").read_text())

    def test_original_authentication_and_content_gates_preserve_originals(self):
        self._qualify()

    def test_failed_original_job_never_publishes(self):
        self._qualify(fail_observer=True)

    def test_changed_current_product_source_never_publishes(self):
        self._qualify(change_source=True)

    def test_live_authenticated_body_does_not_download_again(self):
        self._qualify(retained_body=True)

    def test_retained_body_must_match_fresh_official_digest(self):
        self._qualify(retained_body=True, corrupt_body=True)

    def test_original_sdk_authority_is_exact_and_separate(self):
        with patch.object(helper.product_reuse, "_runtime_prior_workflow_sha", return_value=None), \
                patch.object(helper.product_reuse, "_require_ci_workflow_reference") as gate:
            self.assertEqual(helper._ORIGINAL_SDK_WORKFLOW_SHA, helper._original_workflow({}, "f" * 40))
            gate.assert_called_once_with({},
                "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@"
                + helper._ORIGINAL_SDK_WORKFLOW_SHA, helper._ORIGINAL_SDK_WORKFLOW_SHA)


if __name__ == "__main__":
    unittest.main()
