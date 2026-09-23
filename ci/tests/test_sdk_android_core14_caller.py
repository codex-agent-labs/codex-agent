import tempfile
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ci import sdk_android_core14_caller as caller
from ci.products.inventory import canonical_json_bytes, sha256_file


class AndroidCore14CallerTest(unittest.TestCase):
    def test_preflight_and_execution_each_hold_concrete_core_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "android.tar.gz"
            archive.write_bytes(b"pinned Android archive")
            descriptor = root / "core-policy.json"
            policy = {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                "javaExecutable": "java", "toolingTrustDomain": "release",
                "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals",
                "records": [{"receiptSha256": "sha256:" + "a" * 64,
                    "captureRoot": "common"}], "policy": policy}))
            active = []
            admissions = []

            @contextmanager
            def held(*args, **kwargs):
                active.append(True)
                try:
                    yield descriptor
                finally:
                    active.pop()

            def verified(*args, **kwargs):
                self.assertTrue(active)
                admissions.append(kwargs["sdk_facade_metadata_admission"])
                return SimpleNamespace(prior_ready_plans={caller._BINARY: {"buildKey": "sha256:" + "b" * 64}},
                    plan={"validationCommit": "c" * 40})

            def execute(*args, **kwargs):
                self.assertTrue(active)
                self.assertIs(kwargs["sdk_facade_metadata_admission"], admissions[-1])
                return "executed"

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state", side_effect=verified),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]}),
                  patch.object(caller.sdk_maven_binary_workflow, "execute", side_effect=execute)):
                arguments = dict(plan=root / "plan", discovery=root / "discovery",
                    before_state=root / "before", after_state=root / "after",
                    metadata_receipt=root / "receipt", expected_build_key="sha256:" + "b" * 64,
                    expected_metadata_build_key="sha256:" + "d" * 64,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=root, android_runtime_archive=archive, token="token", environ={})
                self.assertEqual(caller.with_core14(**arguments)["buildKey"], arguments["expected_build_key"])
                self.assertFalse(active)
                self.assertEqual(caller.with_core14(**arguments, destination=root / "output"), "executed")
                self.assertFalse(active)
                self.assertEqual(len(admissions), 2)

    def test_wrong_android_election_fails_while_core_is_held(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "android.tar.gz"
            archive.write_bytes(b"archive")
            descriptor = root / "policy.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals", "records": [],
                "policy": {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                    "javaExecutable": "java", "toolingTrustDomain": "release",
                    "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}}))

            @contextmanager
            def held(*args, **kwargs):
                yield descriptor

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state",
                      return_value=SimpleNamespace(prior_ready_plans={})),
                  patch.object(caller.sdk_maven_binary_workflow, "execute") as execute):
                with self.assertRaisesRegex(ValueError, "Core-admitted election"):
                    caller.with_core14(root / "plan", root / "discovery", root / "before",
                        root / "after", root / "receipt", expected_build_key="sha256:" + "b" * 64,
                        expected_metadata_build_key="sha256:" + "d" * 64,
                        expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                        replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                        repository_root=root, android_runtime_archive=archive, token="token", environ={})
                execute.assert_not_called()

    def test_cli_preflight_emits_only_elected_android_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy, context, output = (root / name for name in
                ("replay.json", "context.json", "github-output"))
            policy.write_bytes(canonical_json_bytes({}))
            context.write_bytes(canonical_json_bytes({}))
            output.write_text("")
            argv = ["preflight", "--plan", str(root / "plan"),
                "--discovery-root", str(root / "discovery"),
                "--before-state-root", str(root / "before"),
                "--after-state-root", str(root / "after"),
                "--metadata-receipt", str(root / "receipt"),
                "--replay-policy", str(policy), "--original-context", str(context),
                "--repository-root", str(root), "--android-runtime-archive", str(root / "archive"),
                "--expected-build-key", "sha256:" + "a" * 64,
                "--expected-metadata-build-key", "sha256:" + "b" * 64,
                "--expected-metadata-receipt-sha256", "sha256:" + "c" * 64,
                "--trusted-workflow-sha", "d" * 40, "--github-output", str(output)]
            selected = {"product": "sdk", "component": "sdk-android", "phase": "binary",
                "target": "android", "buildKey": "sha256:" + "a" * 64}
            with (patch.object(caller, "with_core14", return_value=selected) as source,
                  patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"})):
                self.assertEqual(caller.main(argv), 0)
            self.assertEqual(source.call_args.kwargs["token"], "test-token")
            raw = output.read_text()
            self.assertIn('"runner":"ubuntu-24.04"', raw)
            self.assertIn("sdk_workers_required=true\n", raw)

    def test_package_replays_core_while_retaining_s858_and_original_binary_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "archive.tar.gz"
            archive.write_bytes(b"pinned")
            descriptor = root / "descriptor.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals", "records": [],
                "policy": {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                    "javaExecutable": "java", "toolingTrustDomain": "release",
                    "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}}))
            active = []

            @contextmanager
            def held(*args, **kwargs):
                active.append(True)
                try:
                    yield descriptor
                finally:
                    active.pop()

            def verified(*args, **kwargs):
                self.assertTrue(active)
                self.assertEqual(args[2], root / "wave15")
                return SimpleNamespace(prior_ready_plans={caller._PACKAGE: {
                    "product": "sdk", "component": "sdk-android", "phase": "package",
                    "target": "android", "buildKey": "sha256:" + "b" * 64}},
                    plan={"validationCommit": "c" * 40})

            def package(*args, **kwargs):
                self.assertTrue(active)
                self.assertIsNotNone(kwargs["sdk_facade_metadata_admission"])
                self.assertEqual(kwargs["sdk_inputs_artifact_id"], 71)
                self.assertEqual(kwargs["binary_artifact_id"], 72)
                self.assertEqual(kwargs["binary_contract_evidence"], {"original": "contract"})
                self.assertEqual(kwargs["binary_original_context"], {"original": "binary"})
                return "package executed"

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state", side_effect=verified),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]}),
                  patch.object(caller.sdk_maven_package_workflow, "execute", side_effect=package)):
                args = dict(plan=root / "plan", discovery=root / "discovery",
                    before_state=root / "wave13", after_state=root / "wave14",
                    selected_state=root / "wave15", metadata_receipt=root / "receipt",
                    expected_build_key="sha256:" + "b" * 64,
                    expected_metadata_build_key="sha256:" + "d" * 64,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=root, android_runtime_archive=archive, token="token", environ={},
                    phase="package", sdk_inputs_artifact_id=71,
                    sdk_inputs_artifact_sha256="sha256:" + "f" * 64,
                    binary_artifact_id=72, binary_artifact_sha256="sha256:" + "1" * 64,
                    binary_contract_evidence={"original": "contract"},
                    binary_original_context={"original": "binary"},
                    keyring=root / "keyring", keys_directory=root / "keys")
                self.assertEqual(caller.with_core14(**args)["phase"], "package")
                self.assertFalse(active)
                self.assertEqual(caller.with_core14(**args, destination=root / "output"),
                    "package executed")
                self.assertFalse(active)
                with self.assertRaisesRegex(ValueError, "independent S858 and binary inputs"):
                    caller.with_core14(**{**args, "binary_artifact_sha256": None})


if __name__ == "__main__":
    unittest.main()
