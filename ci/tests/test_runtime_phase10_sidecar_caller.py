"""Caller composition fixtures; full signed-carrier and PGP proofs have separate tests."""

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase10_sidecar_caller as caller
from ci.tests.test_products import phase_receipt
from products.inventory import (
    canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes,
)
from products.receipt import compute_build_key


class RuntimePhase10SidecarCallerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "release-output"
        self.output.mkdir()
        receipt = phase_receipt("release")
        receipt.update(product="runtime", component="runtime-aggregate", phase="metadata",
                       target="aggregate")
        receipt["buildKey"] = compute_build_key(
            product="runtime", component="runtime-aggregate", phase="metadata",
            target="aggregate", inputs=receipt["inputs"],
        )
        self.receipt_bytes = canonical_json_bytes(receipt)
        self.digest = sha256_bytes(self.receipt_bytes)
        self.key = receipt["buildKey"]
        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"pinned policy\n")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.pgp_key = self.root / "pgp.asc"
        self.pgp_key.write_bytes(b"pinned PGP public key\n")
        self.signing_home = self.root / "gnupg"
        self.signing_home.mkdir()
        self.destination = self.root / "maven-sidecars"
        self._carrier(self.output)

    def _carrier(self, root):
        receipt = root / "aggregate-input/metadata-receipt.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(self.receipt_bytes)
        outputs = root / "selected-inputs/predecessors/runtime-runtime-aggregate-metadata-aggregate/stage/outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        (outputs / "codex-agent-runtime-0.2.0-manifest.json").write_bytes(b"original manifest\n")

    def _invoke(self, *, expected_digest=None):
        captured = {}

        @contextmanager
        def verified(root, *, keyring, keys_directory):
            captured["carrier"] = root
            self.assertEqual(self.keyring, keyring)
            self.assertEqual(self.keys, keys_directory)
            stage = root / "selected-inputs/predecessors/runtime-runtime-aggregate-metadata-aggregate/stage"
            manifest = stage / "outputs/codex-agent-runtime-0.2.0-manifest.json"
            yield {"originalPhases": {caller._METADATA: {"stage": stage}},
                   "indexInputs": {"manifest": manifest}}

        def sign(payload, manifest, destination, pgp_key, key_digest, home, fingerprint, passphrase):
            self.assertEqual(captured["carrier"] / "selected-inputs/predecessors/"
                             "runtime-runtime-aggregate-metadata-aggregate/stage/outputs", payload)
            self.assertEqual(payload / "codex-agent-runtime-0.2.0-manifest.json", manifest)
            self.assertEqual(self.pgp_key, pgp_key)
            self.assertEqual(sha256_bytes(self.pgp_key.read_bytes()), key_digest)
            self.assertEqual(self.signing_home, home)
            self.assertEqual("A" * 40, fingerprint)
            self.assertEqual("secret", passphrase)
            path = destination / "maven/runtime.asc"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"external signature\n")
            return {"sidecarFiles": regular_file_inventory(destination), "product": "runtime"}

        with patch.object(caller, "verified_runtime_aggregate_handoff", side_effect=verified) as proof, \
                patch.object(caller, "produce_runtime_phase10_maven_sidecars", side_effect=sign) as signer:
            result = caller.produce_authenticated_runtime_maven_sidecars(
                self.output, self.destination,
                expected_metadata_receipt_sha256=expected_digest or self.digest,
                expected_build_key=self.key, keyring=self.keyring, keys_directory=self.keys,
                pgp_public_key=self.pgp_key,
                expected_pgp_key_sha256=sha256_bytes(self.pgp_key.read_bytes()),
                signing_home=self.signing_home, signing_fingerprint="A" * 40,
                passphrase="secret",
            )
        proof.assert_called_once()
        signer.assert_called_once()
        self.assertEqual(result["sidecarFiles"], regular_file_inventory(self.destination))
        return captured["carrier"]

    def test_fresh_original_stage_is_selected_and_sidecars_stay_separate(self):
        carrier = self._invoke()
        self.assertEqual("protected-output", carrier.name)
        self.assertFalse((self.output / "maven-sidecars").exists())

    def test_changed_verified_sidecar_fails_before_publication(self):
        def mutate_before_copy(source, destination, *, expected_inventory):
            (source / "maven/runtime.asc").write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination, expected_inventory=expected_inventory)

        with patch.object(caller, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self._invoke()
        self.assertFalse(self.destination.exists())

    def test_retained_wrapper_uses_fixed_original_carrier_path(self):
        retained = self.output / "retained-release"
        retained.mkdir()
        for name in ("aggregate-input", "selected-inputs"):
            (self.output / name).rename(retained / name)
        (self.output / "trust").mkdir()
        (self.output / "caller.json").write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "target": "aggregate", "trustedSourceCommit": "a" * 40,
            "trustedSourceTree": "b" * 40, "trustedWorkflowSha": "c" * 40,
            "transportProducer": {}, "authorizationReason": "fixture", "event": {},
            "environment": {}, "metadataReceiptSha256": self.digest,
            "releaseDirectory": "retained-release",
        }))
        selection = self.output / "selected-inputs/selection.json"
        selection.parent.mkdir(parents=True)
        selection.write_bytes(canonical_json_bytes({"target": "aggregate", "metadata": {
            "buildKey": self.key, "receiptSha256": self.digest,
        }}))
        self.assertEqual("retained-release", self._invoke().name)

    def test_wrong_original_receipt_rejects_before_signer(self):
        with patch.object(caller, "produce_runtime_phase10_maven_sidecars") as signer:
            with self.assertRaisesRegex(ValueError, "selected original bytes"):
                caller.produce_authenticated_runtime_maven_sidecars(
                    self.output, self.destination,
                    expected_metadata_receipt_sha256=sha256_bytes(b"other"),
                    expected_build_key=self.key, keyring=self.keyring, keys_directory=self.keys,
                    pgp_public_key=self.pgp_key,
                    expected_pgp_key_sha256=sha256_bytes(self.pgp_key.read_bytes()),
                    signing_home=self.signing_home, signing_fingerprint="A" * 40,
                    passphrase="secret",
                )
            signer.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_transported_verifier_key_is_not_accepted_as_caller_policy(self):
        untrusted = self.output / "transported-keyring.json"
        untrusted.write_bytes(self.keyring.read_bytes())
        with patch.object(caller, "verified_runtime_aggregate_handoff") as proof, \
                patch.object(caller, "produce_runtime_phase10_maven_sidecars") as signer:
            with self.assertRaisesRegex(ValueError, "policy must be external"):
                caller.produce_authenticated_runtime_maven_sidecars(
                    self.output, self.destination,
                    expected_metadata_receipt_sha256=self.digest,
                    expected_build_key=self.key, keyring=untrusted,
                    keys_directory=self.keys, pgp_public_key=self.pgp_key,
                    expected_pgp_key_sha256=sha256_bytes(self.pgp_key.read_bytes()),
                    signing_home=self.signing_home, signing_fingerprint="A" * 40,
                    passphrase="secret",
                )
            proof.assert_not_called()
            signer.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_cli_help_without_pythonpath(self):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve().parents[1] /
                                        "runtime_phase10_sidecar_caller.py"), "--help"],
            cwd=self.root, env=environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--expected-metadata-receipt-sha256", result.stdout)


if __name__ == "__main__":
    unittest.main()
