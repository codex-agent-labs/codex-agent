"""Signed Phase-10 Contract record cannot replace independent source/transport pins."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import contract_phase10_output_record as gate
from ci.products.inventory import (
    canonical_json_bytes, public_key_fingerprint, regular_file_inventory,
    sha256_bytes, write_canonical_json,
)
from ci.products.signatures import generate_development_key, sign_manifest


@unittest.skipUnless(shutil.which("git") and shutil.which("ssh-keygen"),
                     "Git and OpenSSH are required")
class ContractPhase10OutputRecordTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ct-phase10-record-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.private, public, development = generate_development_key(self.root / "key")
        self.signing = {**development, "trustDomain": "release", "keyId": "test-release"}
        keyring = self.repository / "gradle/release/product-signing-keys.json"
        keyring.parent.mkdir(parents=True)
        keys = self.repository / "gradle/release/keys"
        keys.mkdir()
        (keys / "test-release.pub").write_bytes(public.read_bytes())
        write_canonical_json(keyring, {
            "schemaVersion": 1, "namespace": self.signing["namespace"],
            "algorithm": self.signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": "test-release",
                          "fingerprint": public_key_fingerprint(public.read_bytes())},
            "retiredKeys": [],
        })
        for command in (["git", "init", "-q"],
                        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                         "commit", "-qm", "trust"]):
            if command[1] == "-c":
                subprocess.run(["git", "add", "."], cwd=self.repository, check=True)
            subprocess.run(command, cwd=self.repository, check=True)
        self.commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repository, text=True,
        ).strip()
        self.tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=self.repository, text=True,
        ).strip()
        self.output = self.root / "phase10"
        self.output.mkdir()
        (self.output / "sidecar-selection.json").write_bytes(b"selected\n")
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.record_path = self.root / "record.json"
        self.upload = {
            "artifactId": 27, "artifactSha256": "sha256:" + "a" * 64,
            "artifactName": "contract-upload", "inventorySha256": sha256_bytes(
                canonical_json_bytes(regular_file_inventory(self.output))),
            "producer": {"tree": self.tree},
            "trustedWorkflowPath": ".github/workflows/product-validation.yml",
            "trustedWorkflowSha": "b" * 40,
            "trustedJobName": "product-validation / contract-phase10-maven",
        }
        source_keys = regular_file_inventory(keys)
        self.pins = {
            "expected_inventory_sha256": self.upload["inventorySha256"],
            "expected_contract_version": "0.8.0",
            "expected_payload_sha256": "sha256:" + "c" * 64,
            "expected_metadata_build_key": "sha256:" + "d" * 64,
            "expected_source_commit": self.commit,
            "expected_source_tree": self.tree,
            "expected_validation_tree": self.tree,
            "expected_workflow_sha": "b" * 40,
            "expected_caller_sha256": "sha256:" + "e" * 64,
            "expected_keyring_sha256": sha256_bytes(keyring.read_bytes()),
            "expected_keys_inventory_sha256": sha256_bytes(canonical_json_bytes(source_keys)),
            "expected_pgp_key_sha256": "sha256:" + "f" * 64,
        }
        self.record = {
            "schemaVersion": 1, "product": "contract", "signing": self.signing,
            "trustedSourceCommit": self.commit, "officialUpload": deepcopy(self.upload),
            "phase11Pins": self.pins, "outputFiles": regular_file_inventory(self.output),
        }
        self.sign()

    def sign(self):
        if self.record_path.exists():
            self.record_path.unlink()
        signature = self.record_path.with_suffix(".sig")
        if signature.exists():
            signature.unlink()
        write_canonical_json(self.record_path, self.record)
        self.signature = sign_manifest(self.record_path, self.private, self.signing)

    def verify(self, **overrides):
        args = dict(
            trusted_source_commit=self.commit, trusted_workflow_sha="b" * 40,
            trusted_workflow_path=self.upload["trustedWorkflowPath"],
            trusted_job_name=self.upload["trustedJobName"],
            expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
            artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
            token="local-test-token", environ={},
        )
        args.update(overrides)
        with (patch.object(gate, "observe_contract_phase10_upload", return_value=self.upload) as official,
              patch.object(gate, "forward_verified_contract_phase10_bytes") as deep):
            result = gate.verify_signed_contract_phase10_output_record(
                self.record_path, self.signature, self.repository, self.output,
                self.plan, **args,
            )
            official.assert_called_once()
            deep.assert_called_once()
            self.assertEqual(self.pins, {
                key: value for key, value in deep.call_args.kwargs.items()
                if key.startswith("expected_")
            })
            return result

    def test_signed_record_binds_official_upload_and_exact_bytes(self):
        self.assertEqual(self.record, self.verify())
        (self.output / "extra").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "uploaded bytes"):
            self.verify()

    def test_independent_source_workflow_and_pgp_pins(self):
        for override in ({"trusted_source_commit": "0" * 40},
                         {"trusted_workflow_sha": "0" * 40},
                         {"expected_pgp_key_sha256": "sha256:" + "0" * 64}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.verify(**override)
        self.record["phase11Pins"]["expected_source_tree"] = "0" * 40
        self.sign()
        with self.assertRaisesRegex(ValueError, "source tree differs"):
            self.verify()

    def test_official_upload_or_signature_mutation_fails(self):
        self.record["officialUpload"]["artifactId"] = 28
        self.sign()
        with self.assertRaisesRegex(ValueError, "official upload"):
            self.verify()
        self.record["officialUpload"] = deepcopy(self.upload)
        self.record["officialUpload"]["trustedWorkflowPath"] = ".github/workflows/wrong.yml"
        self.sign()
        with self.assertRaisesRegex(ValueError, "official upload"):
            self.verify()
        self.signature.write_bytes(b"not a signature\n")
        with self.assertRaises(ValueError):
            self.verify()

    def test_real_deep_verifier_rejects_plausible_signed_but_incomplete_tree(self):
        # The unit record is structurally valid and genuinely signed, but its
        # one-file tree has no Contract receipt, release attestation or PGP
        # sidecars. A transport/signature-only gate must not accept it.
        with patch.object(gate, "observe_contract_phase10_upload", return_value=self.upload):
            with self.assertRaises((ValueError, OSError)):
                gate.verify_signed_contract_phase10_output_record(
                    self.record_path, self.signature, self.repository, self.output,
                    self.plan, trusted_source_commit=self.commit,
                    trusted_workflow_sha="b" * 40,
                    trusted_workflow_path=self.upload["trustedWorkflowPath"],
                    trusted_job_name=self.upload["trustedJobName"],
                    expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                    artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                    token="local-test-token", environ={},
                )

    def test_unsigned_or_extra_record_field_fails_closed(self):
        self.record["unexpected"] = True
        self.sign()
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
