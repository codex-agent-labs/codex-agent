"""The Android evidence app resolves only a verified SDK Maven snapshot."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci.products import sdk_android_evidence_repository as evidence
from ci.products.inventory import canonical_json_bytes, regular_file_inventory


class AndroidEvidenceRepositoryTest(unittest.TestCase):
    def test_materializes_only_verified_package_and_matching_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stage = root / "package"
            maven = stage / "outputs/maven/io/github/codex-agent-labs/codex-agent-runtime-android/0.8.0"
            maven.mkdir(parents=True)
            (maven / "codex-agent-runtime-android-0.8.0.aar").write_bytes(b"selected AAR")
            binary = root / "binary"
            binary.mkdir()
            (binary / "binary.bin").write_bytes(b"original binary")
            files = {}
            for name in (
                "package_receipt", "binary_receipt", "compatibility_request",
                "binary_contract_evidence", "contract_payload", "contract_metadata_receipt",
                "contract_attestation", "contract_attestation_signature", "contract_public_key",
            ):
                files[name] = root / name
                files[name].write_bytes(canonical_json_bytes({}) if name ==
                    "binary_contract_evidence" else b"original\n")
            contract = {name: files[name] for name in (
                "contract_payload", "contract_metadata_receipt", "contract_attestation",
                "contract_attestation_signature", "contract_public_key",
            )}
            request = {**contract, "sdk_version": "0.8.0"}
            receipt = {"product": "sdk", "component": "sdk-android",
                       "phase": "package", "target": "android", "productVersion": "0.8.0"}
            options = {"repository": root, "package_stage": stage,
                       "binary_stage": binary, **files, "destination": root / "verified"}
            with patch.object(evidence, "load_sdk_compatibility_request", return_value=request), \
                 patch.object(evidence, "verify_sdk_package_inputs",
                              return_value=(receipt, files["package_receipt"].read_bytes())) as verify:
                self.assertEqual("0.8.0", evidence.materialize_android_evidence_repository(**options))
                self.assertEqual(regular_file_inventory(stage / "outputs/maven"),
                                 regular_file_inventory(root / "verified"))
                verify.assert_called_once()
                (root / "verified/io/github/codex-agent-labs/codex-agent-runtime-android/0.8.0/"
                    "codex-agent-runtime-android-0.8.0.aar").write_bytes(b"tampered")
                self.assertEqual(b"selected AAR", (maven /
                    "codex-agent-runtime-android-0.8.0.aar").read_bytes())
            options["destination"] = root / "wrong-contract"
            request["contract_payload"] = root / "different"
            with patch.object(evidence, "load_sdk_compatibility_request", return_value=request), \
                 patch.object(evidence, "verify_sdk_package_inputs") as verify:
                with self.assertRaisesRegex(ValueError, "settings-authenticated Contract"):
                    evidence.materialize_android_evidence_repository(**options)
                verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
