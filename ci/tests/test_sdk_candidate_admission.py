"""SDK candidate joins three separately verified Phase-10 byte sets."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_candidate_admission as candidate
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file
from ci.products.restore import object_relative_path
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


class SdkCandidateAdmissionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.promoted = self.root / "promoted"
        self.objects = self.root / "objects"
        self.maven = self.root / "maven"
        self.promoted.mkdir()
        (self.objects / "signed-campaign/signed-pair").mkdir(parents=True)
        (self.objects / "signed-campaign/replay-evidence/keys").mkdir(parents=True)
        (self.objects / "objects").mkdir()
        (self.maven / "custody/campaign/keys").mkdir(parents=True)
        self.entries = []
        self.rows = []
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            key = sha256_bytes(f"key {position}".encode())
            receipt = sha256_bytes(f"receipt {position}".encode())
            relative = object_relative_path(key, receipt)
            content = f"object {position}\n".encode()
            for root in (self.promoted, self.objects / "objects"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            self.rows.append({"product": instance.product, "component": instance.component,
                              "phase": instance.phase, "target": instance.target,
                              "buildKey": key, "receiptSha256": receipt,
                              "objectSha256": sha256_bytes(content), "relativePath": relative})
            self.entries.append({"product": instance.product, "component": instance.component,
                                 "phase": instance.phase, "target": instance.target,
                                 "buildKey": key, "receiptSha256": receipt,
                                 "productVersion": "0.8.0"})
        self.promoted_index = b"promoted signed index\n"
        self.promoted_signature = b"promoted signature\n"
        self.phase10_index = b"Phase-10 signed index\n"
        self.phase10_signature = b"Phase-10 signature\n"
        (self.promoted / "product-index.json").write_bytes(self.promoted_index)
        (self.promoted / "product-index.sig").write_bytes(self.promoted_signature)
        for relative, content in (("product-index.json", self.phase10_index),
                                  ("product-index.sig", self.phase10_signature)):
            (self.objects / "signed-campaign/signed-pair" / relative).write_bytes(content)
            (self.maven / "custody/campaign" / relative).write_bytes(content)
        self.keyring = self.objects / "signed-campaign/replay-evidence/product-signing-keys.json"
        self.keyring.write_bytes(b"keyring\n")
        (self.keyring.parent / "keys/release.pub").write_bytes(b"public key\n")
        (self.maven / "custody/campaign/product-signing-keys.json").write_bytes(
            self.keyring.read_bytes())
        (self.maven / "custody/campaign/keys/release.pub").write_bytes(
            (self.keyring.parent / "keys/release.pub").read_bytes())
        self.pin_file = self.objects / "object-pins.json"
        self.pin_file.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "signedIndexSha256": sha256_bytes(self.phase10_index), "objects": self.rows}))
        self.tree = "a" * 40
        self.pins = dict(
            expected_promoted_inventory_sha256=self._inventory(self.promoted),
            expected_promoted_index_sha256=sha256_bytes(self.promoted_index),
            expected_promoted_signature_sha256=sha256_bytes(self.promoted_signature),
            expected_phase10_index_sha256=sha256_bytes(self.phase10_index),
            expected_phase10_signature_sha256=sha256_bytes(self.phase10_signature),
            expected_keyring_sha256=sha256_file(self.keyring),
            expected_keys_inventory_sha256=self._inventory(self.keyring.parent / "keys"),
            expected_object_pins_sha256=sha256_file(self.pin_file),
            expected_maven_inventory_sha256=self._inventory(self.maven),
            expected_sdk_version="0.8.0", expected_validation_tree=self.tree,
        )

    @staticmethod
    def _inventory(path):
        return sha256_bytes(canonical_json_bytes(regular_file_inventory(path)))

    def _verify(self, *, original_entries=None, **changes):
        promoted = {"repository": candidate._REPOSITORY, "trustDomain": "release",
            "context": {"kind": "promoted-main", "tree": self.tree},
            "entries": self.entries}
        original = {**promoted, "context": {"kind": "pull-request", "tree": self.tree},
                    "entries": self.entries if original_entries is None else original_entries}
        with patch.object(candidate, "verify_release_product_index",
                          side_effect=[(promoted, self.promoted_index),
                                       (original, self.phase10_index)]) as signature, \
             patch.object(candidate, "verify_release_sdk_campaign_objects") as originals:
            result = candidate.verify_sdk_candidate_join(
                self.promoted, self.objects, self.maven, **{**self.pins, **changes})
        self.assertEqual(2, signature.call_count)
        originals.assert_called_once()
        return result

    def test_exact_62_originals_join_promoted_campaign_and_maven(self):
        self.assertEqual(62, self._verify()["originalObjectCount"])

    def test_independent_pin_and_original_mutations_reject(self):
        with self.assertRaisesRegex(ValueError, "independent S1048 inventory"):
            self._verify(expected_promoted_inventory_sha256=sha256_bytes(b"wrong"))
        object_path = self.objects / "objects" / self.rows[0]["relativePath"]
        object_path.write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "differs across releases"):
            self._verify()

    def test_different_maven_campaign_and_duplicate_object_pins_reject(self):
        (self.maven / "custody/campaign/product-index.sig").write_bytes(b"different\n")
        with self.assertRaisesRegex(ValueError, "different signed campaign"):
            self._verify(expected_maven_inventory_sha256=self._inventory(self.maven))
        (self.maven / "custody/campaign/product-index.sig").write_bytes(self.phase10_signature)
        rows = [*self.rows]
        rows[-1] = rows[0]
        self.pin_file.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "signedIndexSha256": sha256_bytes(self.phase10_index), "objects": rows}))
        with self.assertRaisesRegex(ValueError, "unknown or duplicate phase"):
            self._verify(expected_object_pins_sha256=sha256_file(self.pin_file))

    def test_maven_custody_cannot_swap_phase10_keyring_or_public_key(self):
        maven_keyring = self.maven / "custody/campaign/product-signing-keys.json"
        maven_keyring.write_bytes(b"different keyring\n")
        with self.assertRaisesRegex(ValueError, "custody public-key policy differs"):
            self._verify(expected_maven_inventory_sha256=self._inventory(self.maven))
        maven_keyring.write_bytes(self.keyring.read_bytes())
        (self.maven / "custody/campaign/keys/release.pub").write_bytes(b"different public key\n")
        with self.assertRaisesRegex(ValueError, "custody public-key policy differs"):
            self._verify(expected_maven_inventory_sha256=self._inventory(self.maven))

    def test_wrong_signed_source_tree_fails_before_original_verifier(self):
        with self.assertRaisesRegex(ValueError, "campaign differ"):
            self._verify(expected_validation_tree="b" * 40)
        changed = [dict(entry) for entry in self.entries]
        changed[0]["receiptSha256"] = sha256_bytes(b"other receipt")
        with self.assertRaisesRegex(ValueError, "campaign differ"):
            self._verify(original_entries=changed)

    def test_no_observation_or_signing_secret_enters_candidate_join(self):
        for name, message in (("GITHUB_API_TOKEN", "observation token"),
                              ("SIGNING_IN_MEMORY_KEY", "signing secret"),
                              ("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "signing")):
            with self.subTest(name=name), patch.dict(os.environ, {name: ""}):
                with self.assertRaisesRegex(ValueError, message):
                    self._verify()

    def test_direct_cli_can_import_without_pythonpath(self):
        source = Path(candidate.__file__).resolve()
        with patch.dict(os.environ, {"PYTHONPATH": ""}):
            result = subprocess.run([sys.executable, "-B", str(source), "--help"],
                cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--expected-object-pins-sha256", result.stdout)


if __name__ == "__main__":
    unittest.main()
