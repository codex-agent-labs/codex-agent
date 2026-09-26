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
from ci import contract_phase10_record_signer as signer
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
                self.record_path, self.signature, self.repository,
                getattr(self, "validation_repository", self.repository), self.output,
                self.plan, **args,
            )
            official.assert_called_once()
            self.assertEqual(getattr(self, "validation_repository", self.repository),
                             official.call_args.args[1])
            deep.assert_called_once()
            self.assertEqual(getattr(self, "validation_repository", self.repository),
                             deep.call_args.kwargs["landed_repository"])
            self.assertEqual(self.pins, {
                key: value for key, value in deep.call_args.kwargs.items()
                if key.startswith("expected_")
            })
            return result

    def test_signed_record_binds_official_upload_and_exact_bytes(self):
        self.assertEqual(self.record, self.verify())
        (self.output / "extra").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "changed during record capture"):
            self.verify()

    def test_reviewed_source_and_validation_checkout_are_distinct(self):
        self.validation_repository = self.root / "validation-checkout"
        subprocess.run(["git", "clone", "-q", str(self.repository),
                        str(self.validation_repository)], check=True)
        (self.validation_repository / "validation-marker").write_text("PR tree\n")
        subprocess.run(["git", "add", "validation-marker"],
                       cwd=self.validation_repository, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "validation"],
                       cwd=self.validation_repository, check=True)
        validation_tree = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=self.validation_repository, text=True,
        ).strip()
        self.assertNotEqual(self.tree, validation_tree)
        self.upload["producer"]["tree"] = validation_tree
        self.pins["expected_validation_tree"] = validation_tree
        self.record["officialUpload"] = deepcopy(self.upload)
        self.sign()
        self.assertEqual(self.record, self.verify())
        with (patch.object(gate, "observe_contract_phase10_upload", return_value=self.upload) as official,
              patch.object(gate, "forward_verified_contract_phase10_bytes") as deep):
            gate.prepare_contract_phase10_output_record(
                self.plan, self.repository, self.validation_repository, self.output,
                self.root / "prepared-with-distinct-checkout", phase11_pins=self.pins,
                trusted_source_commit=self.commit, trusted_workflow_sha="b" * 40,
                trusted_workflow_path=self.upload["trustedWorkflowPath"],
                trusted_job_name=self.upload["trustedJobName"],
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                token="local-test-token", environ={},
            )
        self.assertEqual(self.validation_repository, official.call_args.args[1])
        self.assertEqual(self.validation_repository,
                         deep.call_args.kwargs["landed_repository"])

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
                    self.record_path, self.signature, self.repository,
                    self.repository, self.output,
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

    def test_three_stage_preparation_signing_and_publication(self):
        prepared = self.root / "prepared"
        with (patch.object(gate, "observe_contract_phase10_upload", return_value=self.upload),
              patch.object(gate, "forward_verified_contract_phase10_bytes")):
            selected = gate.prepare_contract_phase10_output_record(
                self.plan, self.repository, self.repository, self.output, prepared,
                phase11_pins=self.pins, trusted_source_commit=self.commit,
                trusted_workflow_sha="b" * 40,
                trusted_workflow_path=self.upload["trustedWorkflowPath"],
                trusted_job_name=self.upload["trustedJobName"],
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                token="local-test-token", environ={},
            )
        self.assertEqual(self.record, selected["record"])
        self.assertEqual(sha256_bytes((prepared / "record.json").read_bytes()),
                         selected["recordSha256"])
        with self.assertRaisesRegex(ValueError, "independent preparation"):
            signer.sign_prepared_contract_phase10_record(
                prepared / "record.json", self.repository,
                trusted_source_commit=self.commit,
                expected_record_sha256="sha256:" + "0" * 64,
                environ={signer._SECRET: self.private.read_text()},
            )
        self.assertFalse((prepared / "record.sig").exists())
        signed = signer.sign_prepared_contract_phase10_record(
            prepared / "record.json", self.repository,
            trusted_source_commit=self.commit,
            expected_record_sha256=selected["recordSha256"],
            environ={signer._SECRET: self.private.read_text()},
        )
        self.assertEqual(sha256_bytes((prepared / "record.sig").read_bytes()),
                         signed["signatureSha256"])
        published = self.root / "published"
        with (patch.object(gate, "observe_contract_phase10_upload", return_value=self.upload),
              patch.object(gate, "forward_verified_contract_phase10_bytes")):
            result = gate.publish_verified_contract_phase10_output_record(
                prepared / "record.json", prepared / "record.sig",
                self.repository, self.repository, self.output, self.plan, published,
                expected_record_sha256=selected["recordSha256"],
                expected_signature_sha256=signed["signatureSha256"],
                trusted_source_commit=self.commit,
                trusted_workflow_sha="b" * 40,
                trusted_workflow_path=self.upload["trustedWorkflowPath"],
                trusted_job_name=self.upload["trustedJobName"],
                expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                token="local-test-token", environ={},
            )
        self.assertEqual(selected["recordSha256"], result["recordSha256"])
        self.assertEqual({"record.json", "record.sig"},
                         {row["relativePath"] for row in result["publishedFiles"]})
        self.assertEqual((prepared / "record.json").read_bytes(),
                         (published / "record.json").read_bytes())

    def test_no_secret_is_available_to_preparer_or_final_verifier(self):
        with patch.dict("os.environ", {signer._SECRET: "not-a-key"}):
            with self.assertRaisesRegex(ValueError, "signing-secret context"):
                gate.prepare_contract_phase10_output_record(
                    self.plan, self.repository, self.repository, self.output,
                    self.root / "not-prepared",
                    phase11_pins=self.pins, trusted_source_commit=self.commit,
                    trusted_workflow_sha="b" * 40,
                    trusted_workflow_path=self.upload["trustedWorkflowPath"],
                    trusted_job_name=self.upload["trustedJobName"],
                    expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                    artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                    token="local-test-token", environ={},
                )
            with self.assertRaisesRegex(ValueError, "signing-secret context"):
                gate.publish_verified_contract_phase10_output_record(
                    self.record_path, self.signature, self.repository,
                    self.repository, self.output,
                    self.plan, self.root / "not-published",
                    expected_record_sha256=sha256_bytes(self.record_path.read_bytes()),
                    expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
                    trusted_source_commit=self.commit,
                    trusted_workflow_sha="b" * 40,
                    trusted_workflow_path=self.upload["trustedWorkflowPath"],
                    trusted_job_name=self.upload["trustedJobName"],
                    expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                    artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                    token="local-test-token", environ={},
                )

    def test_protected_signer_rejects_prepared_record_swap_before_signature_publish(self):
        prepared = self.root / "racy-prepared"
        prepared.mkdir()
        record = prepared / "record.json"
        record.write_bytes(self.record_path.read_bytes())
        pinned = sha256_bytes(record.read_bytes())
        real_sign = signer.sign_manifest

        def swap_after_snapshot(snapshot, private, metadata):
            signature = real_sign(snapshot, private, metadata)
            record.write_bytes(b"substituted after the verified snapshot\n")
            return signature

        with patch.object(signer, "sign_manifest", side_effect=swap_after_snapshot):
            with self.assertRaisesRegex(ValueError, "changed during protected signing"):
                signer.sign_prepared_contract_phase10_record(
                    record, self.repository, trusted_source_commit=self.commit,
                    expected_record_sha256=pinned,
                    environ={signer._SECRET: self.private.read_text()},
                )
        self.assertFalse((prepared / "record.sig").exists())

    def test_final_publication_uses_verified_private_pair_and_rejects_source_swap(self):
        destination = self.root / "racy-published"
        original_record = self.record_path.read_bytes()
        original_signature = self.signature.read_bytes()

        def swap_after_verification(record_path, signature_path, *_args, **_kwargs):
            self.assertNotEqual(self.record_path, record_path)
            self.assertNotEqual(self.signature, signature_path)
            self.assertEqual(original_record, record_path.read_bytes())
            self.assertEqual(original_signature, signature_path.read_bytes())
            self.record_path.write_bytes(b"substituted after private verification\n")
            return self.record

        with patch.object(gate, "verify_signed_contract_phase10_output_record",
                          side_effect=swap_after_verification):
            with self.assertRaisesRegex(ValueError, "input changed before publication"):
                gate.publish_verified_contract_phase10_output_record(
                    self.record_path, self.signature, self.repository,
                    self.repository, self.output,
                    self.plan, destination,
                    expected_record_sha256=sha256_bytes(original_record),
                    expected_signature_sha256=sha256_bytes(original_signature),
                    trusted_source_commit=self.commit,
                    trusted_workflow_sha="b" * 40,
                    trusted_workflow_path=self.upload["trustedWorkflowPath"],
                    trusted_job_name=self.upload["trustedJobName"],
                    expected_pgp_key_sha256=self.pins["expected_pgp_key_sha256"],
                    artifact_id=27, artifact_sha256=self.upload["artifactSha256"],
                    token="local-test-token", environ={},
                )
        self.assertFalse(destination.exists())

    def test_record_signature_verification_uses_one_private_byte_pair(self):
        alternate = self.root / "alternate.json"
        changed = deepcopy(self.record)
        changed["officialUpload"]["artifactId"] = 28
        write_canonical_json(alternate, changed)
        alternate_signature = sign_manifest(alternate, self.private, self.signing)
        original_record = self.record_path.read_bytes()
        original_signature = self.signature.read_bytes()
        real_verify = gate.verify_manifest_signature

        def swap_live_pair_during_verification(record, signature, public, metadata):
            self.assertNotEqual(self.record_path, record)
            self.assertNotEqual(self.signature, signature)
            self.assertEqual(original_record, record.read_bytes())
            self.assertEqual(original_signature, signature.read_bytes())
            self.record_path.write_bytes(alternate.read_bytes())
            self.signature.write_bytes(alternate_signature.read_bytes())
            try:
                real_verify(record, signature, public, metadata)
            finally:
                self.record_path.write_bytes(original_record)
                self.signature.write_bytes(original_signature)

        with patch.object(gate, "verify_manifest_signature",
                          side_effect=swap_live_pair_during_verification):
            self.assertEqual(self.record, self.verify())


if __name__ == "__main__":
    unittest.main()
