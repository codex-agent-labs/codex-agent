"""Local two-step Core14 trust handoff; hosted authority is not simulated."""

from pathlib import Path
from subprocess import run as unmocked_run
import unittest
from unittest.mock import patch

from ci import sdk_core_metadata_protected_handoff as handoff
from ci.sdk_core_metadata_history import verify_signed_original_core_context
from ci.tests.test_sdk_core_metadata_context_preparation import OriginalCoreContextPreparationTest
from ci.products.inventory import load_canonical_json_bytes, sha256_bytes, write_canonical_json


class ProtectedCoreHandoffTest(unittest.TestCase):
    def setUp(self):
        self.base = OriginalCoreContextPreparationTest(methodName="runTest")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.external = self.base.external
        self.fixture = self.base.fixture
        self.keyring = self.base.keyring
        self.keys = self.base.keys
        self.caller, _ = self.base.caller_policy()
        self.checkpoint_root = self.external / "protected-checkpoint"
        self.signed_root = self.external / "protected-signed"
        self.private = (self.external / "ephemeral/development-ed25519").read_text()

    def prepare(self, **changes):
        arguments = {"caller_policy": self.caller, "destination": self.checkpoint_root,
            "repository_root": self.base.arguments()["repository_root"],
            "trusted_workflow_sha": self.base.arguments()["trusted_workflow_sha"],
            "signing_keyring": self.keyring, "signing_keys_directory": self.keys,
            "environ": self.base.arguments()["environ"], "token": self.base.arguments()["token"]}
        return handoff.prepare_protected_core_context(**{**arguments, **changes})

    def sign(self, **changes):
        selected = self.base.arguments()
        arguments = {"checkpoint_directory": self.checkpoint_root,
            "metadata_receipt": self.fixture.receipt_path, "destination": self.signed_root,
            "expected_context_sha256": sha256_bytes(
                (self.checkpoint_root / "original-context.json").read_bytes()),
            "expected_build_key": selected["expected_build_key"],
            "expected_receipt_sha256": selected["expected_receipt_sha256"],
            "expected_artifact_id": selected["artifact_id"],
            "expected_artifact_sha256": selected["artifact_sha256"],
            "expected_public_key_sha256": sha256_bytes((self.keys / "fixture-release.pub").read_bytes()),
            "signing_keyring": self.keyring, "signing_keys_directory": self.keys,
            "private_key_text": self.private, "candidate_root": selected["repository_root"]}
        return handoff.sign_protected_core_context(**{**arguments, **changes})

    def test_exact_replay_then_sign_only_exact_bytes(self):
        checkpoint = self.prepare()
        self.assertEqual(checkpoint["contextSha256"], sha256_bytes(
            (self.checkpoint_root / "original-context.json").read_bytes()))
        with patch.object(handoff, "prepare_from_caller_policy", side_effect=AssertionError("replayed")), \
                patch("ci.products.signatures.subprocess.run", side_effect=unmocked_run):
            manifest, signature = self.sign()
        self.assertEqual((self.checkpoint_root / "original-context.json").read_bytes(),
                         manifest.read_bytes())
        self.assertTrue(signature.is_file())
        selected = self.base.arguments()
        with patch("ci.products.signatures.subprocess.run", side_effect=unmocked_run):
            self.assertEqual(self.fixture.context, verify_signed_original_core_context(
                manifest, signature, self.fixture.receipt_path,
                expected_build_key=selected["expected_build_key"],
                expected_receipt_sha256=selected["expected_receipt_sha256"],
                expected_artifact_id=selected["artifact_id"],
                expected_artifact_sha256=selected["artifact_sha256"],
                keyring_path=self.keyring, keys_directory=self.keys))

    def test_no_secret_in_replay_and_no_signing_on_mismatch(self):
        with self.assertRaisesRegex(ValueError, "signing-secret context"):
            self.prepare(environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": self.private})
        self.assertFalse(self.checkpoint_root.exists())
        self.prepare()
        cases = [
            {"expected_artifact_sha256": "sha256:" + "e" * 64},
            {"expected_receipt_sha256": "sha256:" + "e" * 64},
            {"expected_context_sha256": "sha256:" + "e" * 64},
            {"expected_public_key_sha256": "sha256:" + "e" * 64},
            {"candidate_root": self.checkpoint_root},
        ]
        for change in cases:
            with self.subTest(change=change), patch.object(handoff, "sign_manifest",
                    side_effect=AssertionError("sign before gate")):
                with self.assertRaises(ValueError):
                    self.sign(**change)
            self.assertFalse(self.signed_root.exists())

    def test_protected_entry_reconstructs_election_before_full_replay(self):
        selected = self.base.arguments()
        with patch.object(handoff, "prepare_original_core_caller_policy",
                return_value=self.caller) as elected:
            checkpoint = handoff.prepare_protected_core_context_from_election(
                selected["plan"], self.external / "discovery", self.external / "state",
                self.external / "bootstrap.json", self.fixture.receipt_path,
                self.checkpoint_root, expected_build_key=selected["expected_build_key"],
                expected_receipt_sha256=selected["expected_receipt_sha256"],
                metadata_artifact_id=selected["artifact_id"],
                metadata_artifact_sha256=selected["artifact_sha256"],
                original_context=selected["original_context"],
                trusted_workflow_sha=selected["trusted_workflow_sha"],
                repository_root=selected["repository_root"],
                signing_keyring=self.keyring, signing_keys_directory=self.keys,
                environ=selected["environ"], token=selected["token"])
        elected.assert_called_once()
        self.assertEqual(checkpoint["contextSha256"], sha256_bytes(
            (self.checkpoint_root / "original-context.json").read_bytes()))

    def test_checkpoint_and_active_key_mutations_reject_before_key_use(self):
        self.prepare()
        checkpoint_path = self.checkpoint_root / "replay-checkpoint.json"
        original = checkpoint_path.read_bytes()
        altered = {**load_canonical_json_bytes(original), "artifactId": 124}
        write_canonical_json(checkpoint_path, altered)
        with patch.object(handoff, "sign_manifest", side_effect=AssertionError("signed")):
            with self.assertRaises(ValueError):
                self.sign()
        checkpoint_path.write_bytes(original)
        keyring = load_canonical_json_bytes(self.keyring.read_bytes())
        write_canonical_json(self.keyring, {**keyring, "activeKey": None})
        with patch.object(handoff, "sign_manifest", side_effect=AssertionError("signed")):
            with self.assertRaises(ValueError):
                self.sign()
        self.assertFalse(self.signed_root.exists())


if __name__ == "__main__":
    unittest.main()
