import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci import sdk_android_core14_fresh_inputs as fresh
from ci.products.inventory import canonical_json_bytes, sha256_bytes


class AndroidFreshCoreInputsTest(unittest.TestCase):
    def test_candidate_is_pinned_before_bootstrap_and_is_not_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            worker = root / "build/sdk-core-metadata-worker"
            receipt_path = worker / "shard/phase-receipt.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_bytes(canonical_json_bytes({"candidate": "untrusted"}))
            key = "sha256:" + "a" * 64
            digest = sha256_bytes(receipt_path.read_bytes())
            producer = {"original": "current"}
            context = {"repositoryRoot": "/original/core/checkout",
                "metadataRequest": "/original/core/private/metadata-request.json"}
            arguments = dict(plan=root / "plan", discovery=root / "discovery",
                before_state=root / "wave13", worker_root=worker,
                requests_root=root / "build/android-core-requests",
                destination=root.parent / "android-core-policy.json",
                expected_metadata_build_key=key,
                expected_metadata_receipt_sha256=digest,
                metadata_artifact_id=42,
                metadata_artifact_sha256="sha256:" + "b" * 64,
                metadata_original_context=context,
                sdk_inputs_artifact_id=7,
                sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                trusted_workflow_sha="d" * 40,
                sdk_validation_tooling=root.parent / "tooling.json",
                native_compiler_archives={}, keyring=root / "keyring",
                keys_directory=root / "keys", repository_root=root,
                environ={"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}, token="token")
            selected = {"product": "sdk", "component": "sdk-core", "phase": "metadata",
                "target": "common", "buildKey": key, "producer": producer}
            plan = {"remoteBuildAuthorized": True, "event": "pull_request"}
            with (patch.object(fresh.product_reuse, "_validate_plan", return_value=plan),
                  patch.object(fresh.product_reuse, "_consumer", return_value={"producer": producer}),
                  patch.object(fresh, "validate_phase_receipt", return_value=selected),
                  patch.object(fresh.sdk_core_metadata_bootstrap, "prepare") as bootstrap):
                result = fresh.prepare(**arguments)
                self.assertEqual(result["metadataReceipt"], str(receipt_path))
                self.assertEqual(result["originalContext"], context)
                self.assertEqual(result["metadataArtifactId"], 42)
                bootstrap.assert_called_once()
                self.assertEqual(bootstrap.call_args.args[:3],
                    (arguments["plan"], arguments["discovery"], arguments["before_state"]))

                bootstrap.reset_mock()
                for change, message in (
                    ({"expected_metadata_receipt_sha256": "sha256:" + "0" * 64}, "receipt"),
                    ({"expected_metadata_build_key": "sha256:" + "0" * 64}, "receipt"),
                    ({"metadata_original_context": {**context, "repositoryRoot": "relative/checkout"}}, "absolute original path"),
                ):
                    with self.subTest(change=change):
                        with self.assertRaisesRegex(ValueError, message):
                            fresh.prepare(**{**arguments, **change})
                        bootstrap.assert_not_called()

    def test_rejects_other_run_before_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            worker = root / "build/sdk-core-metadata-worker"
            receipt_path = worker / "shard/phase-receipt.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_bytes(canonical_json_bytes({"candidate": "untrusted"}))
            with (patch.object(fresh, "validate_phase_receipt", return_value={
                    "product": "sdk", "component": "sdk-core", "phase": "metadata",
                    "target": "common", "buildKey": "sha256:" + "a" * 64,
                    "producer": {"runId": 2}}),
                  patch.object(fresh.product_reuse, "_validate_plan", return_value={
                    "remoteBuildAuthorized": True, "event": "pull_request"}),
                  patch.object(fresh.product_reuse, "_consumer", return_value={
                    "producer": {"runId": 1}}),
                  patch.object(fresh.sdk_core_metadata_bootstrap, "prepare") as bootstrap):
                with self.assertRaisesRegex(ValueError, "current campaign"):
                    fresh.prepare(root / "plan", root / "discovery", root / "wave13", worker,
                        root / "build/requests", root.parent / "policy", expected_metadata_build_key="sha256:" + "a" * 64,
                        expected_metadata_receipt_sha256=sha256_bytes(receipt_path.read_bytes()),
                        metadata_artifact_id=1, metadata_artifact_sha256="sha256:" + "b" * 64,
                        metadata_original_context={"repositoryRoot": str(root), "metadataRequest": "/tmp/request"},
                        sdk_inputs_artifact_id=2, sdk_inputs_artifact_sha256="sha256:" + "c" * 64,
                        trusted_workflow_sha="d" * 40, sdk_validation_tooling=root.parent / "tooling",
                        native_compiler_archives={}, keyring=root / "keyring", keys_directory=root / "keys",
                        repository_root=root, environ={}, token="token")
                bootstrap.assert_not_called()


if __name__ == "__main__":
    unittest.main()
