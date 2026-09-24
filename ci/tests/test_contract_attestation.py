from __future__ import annotations

import copy
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci.products.contract_attestation import (
    build_contract_attestation,
    capture_contract_execution_closure,
    main,
    materialize_contract_payload,
    validate_contract_attestation,
    verify_contract_attestation,
)
from ci.products.contract_model import verify_extracted_contract_directory
from ci.products.inventory import (
    load_canonical_json,
    publish_regular_tree as actual_publish_regular_tree,
    public_key_fingerprint,
    regular_file_inventory,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_execution_closure import execution_closure_fixture


VERSION = "0.2.0"


def _producer(run_id: int) -> dict[str, object]:
    return {
        "repository": "codex-agent-labs/codex-agent",
        "workflowPath": ".github/workflows/ci.yml",
        "commit": f"{run_id % 10}" * 40,
        "tree": f"{(run_id + 1) % 10}" * 40,
        "event": "pull_request",
        "runId": run_id,
        "runAttempt": 1,
        "pullRequest": 31,
    }


def _payload(path: Path, marker: str = "payload") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.with_name(path.name + ".execution-source")
    if not source.exists():
        execution_closure_fixture(source, target_hash_salt=marker.encode())
    shutil.copyfile(source / "metadata-stage/outputs" / path.name, path)


def _receipt(path: Path, payload: Path, producer: dict[str, object], trust: str) -> None:
    source = payload.with_name(payload.name + ".execution-source")
    value = load_canonical_json(source / "metadata-receipt/phase-receipt.json")
    write_canonical_json(path, {**value, "producer": producer, "trustDomain": trust})


def _closure(payload: Path, receipt: Path, output: Path) -> Path:
    source = payload.with_name(payload.name + ".execution-source")
    receipts = {phase: source / f"{phase}-receipt/phase-receipt.json" for phase in ("binary", "package", "validation")}
    capture_contract_execution_closure(
        payload, {**receipts, "metadata": receipt},
        source / "binary-stage/outputs/execution/contract-execution.zip", output,
    )
    return output


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractAttestationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="contract-attestation-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = self.root / f"codex-agent-contract-{VERSION}.zip"
        _payload(self.payload)
        self.receipt = self.root / "phase-receipt.json"
        _receipt(self.receipt, self.payload, _producer(7), "development")
        self.private_key, self.public_key, self.signing = generate_development_key(
            self.root / "key",
        )

    def build(self, name: str = "output") -> tuple[Path, Path, dict[str, object]]:
        output = self.root / name
        value = build_contract_attestation(
            self.payload,
            self.receipt,
            self.signing,
            self.private_key,
            self.public_key,
            output,
            execution_closure=_closure(self.payload, self.receipt, self.root / (name + "-closure")),
        )
        stem = f"codex-agent-contract-{VERSION}.attestation"
        return output / f"{stem}.json", output / f"{stem}.sig", value

    def test_complete_handoff_is_atomic_relocatable_and_never_rebuilds_payload(self) -> None:
        closure = _closure(self.payload, self.receipt, self.root / "original-closure")
        before = regular_file_inventory(closure)
        originals = {path: path.read_bytes() for path in (self.payload, self.receipt, self.public_key)}
        output = self.root / "handoff"
        policy = self.root / "signing.json"
        write_canonical_json(policy, self.signing)
        with mock.patch("ci.products.contract.build_contract_bundle", side_effect=AssertionError("payload rebuild")):
            self.assertEqual(0, main(["build", "--complete-handoff", "--payload", str(self.payload),
                "--metadata-receipt", str(self.receipt), "--signing-metadata", str(policy),
                "--execution-closure", str(closure), "--private-key", str(self.private_key),
                "--public-key", str(self.public_key), "--output-directory", str(output)]))
        self.assertEqual(before, regular_file_inventory(closure))
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})
        self.assertEqual(originals[self.payload], (output / self.payload.name).read_bytes())
        self.assertEqual(originals[self.public_key], (output / "public-key.pub").read_bytes())
        self.assertEqual(originals[self.receipt], (output / "execution-closure/receipts/metadata.json").read_bytes())
        self.assertEqual(10, len(regular_file_inventory(output)))
        retained = regular_file_inventory(output)
        moved = self.root / "relocated"
        output.rename(moved)
        self.payload.rename(self.root / "hidden-payload")
        self.receipt.rename(self.root / "hidden-receipt")
        closure.rename(self.root / "hidden-closure")
        self.private_key.parent.rename(self.root / "hidden-keys")
        stem = f"codex-agent-contract-{VERSION}.attestation"
        value = verify_contract_attestation(moved / self.payload.name,
            moved / "execution-closure/receipts/metadata.json", moved / f"{stem}.json",
            moved / f"{stem}.sig", moved / "public-key.pub", required_trust_domain="development")[2]
        self.assertEqual(self.signing, value["signing"])
        self.assertEqual(retained, regular_file_inventory(moved))
        with self.assertRaisesRegex(ValueError, "destination must not exist"), \
                mock.patch("ci.products.contract_attestation.sign_manifest", side_effect=AssertionError("resign")):
            build_contract_attestation(self.payload, self.receipt, self.signing, self.private_key,
                self.public_key, moved, execution_closure=closure, complete_handoff=True)

    def test_complete_handoff_rejects_overlap_mutation_and_extra_bytes_before_publication(self) -> None:
        closure = _closure(self.payload, self.receipt, self.root / "original-closure")
        def build(output):
            return build_contract_attestation(self.payload, self.receipt, self.signing, self.private_key,
                self.public_key, output, execution_closure=closure, complete_handoff=True)
        for output in (closure / "nested", self.private_key / "nested", self.root):
            with self.subTest(output=output), self.assertRaises(ValueError), \
                    mock.patch("ci.products.contract_attestation.sign_manifest", side_effect=AssertionError("sign")):
                build(output)
        receipt_bytes = self.receipt.read_bytes()
        for case in ("extra", "payload", "original", "closure"):
            def mutate(manifest, key, metadata):
                signature = sign_manifest(manifest, key, metadata)
                if case == "extra":
                    (manifest.parent / "unexpected-private-file").write_bytes(b"must not be published")
                elif case == "payload":
                    (manifest.parent / self.payload.name).write_bytes(b"changed captured payload")
                elif case == "original":
                    self.receipt.write_bytes(b"changed original receipt")
                else:
                    (closure / "unexpected-original-file").write_bytes(b"changed original closure")
                return signature
            output = self.root / f"rejected-{case}"
            with self.subTest(case=case), mock.patch("ci.products.contract_attestation.sign_manifest", side_effect=mutate), \
                    self.assertRaises(ValueError):
                build(output)
            self.assertFalse(output.exists())
            self.receipt.write_bytes(receipt_bytes)
            (closure / "unexpected-original-file").unlink(missing_ok=True)

    def test_late_complete_handoff_mutation_fails_before_publication(self) -> None:
        closure = _closure(self.payload, self.receipt, self.root / "late-closure")
        output = self.root / "late-handoff"

        def mutate_then_publish(source, destination, **kwargs):
            (Path(source) / self.payload.name).write_bytes(b"late mutation\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch("ci.products.contract_attestation.publish_regular_tree",
                        side_effect=mutate_then_publish), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            build_contract_attestation(
                self.payload, self.receipt, self.signing, self.private_key,
                self.public_key, output, execution_closure=closure, complete_handoff=True,
            )
        self.assertFalse(output.exists())

    def verify(self, attestation: Path, signature: Path, **changes):
        arguments = {
            "payload": self.payload,
            "metadata_receipt": self.receipt,
            "attestation": attestation,
            "signature": signature,
            "public_key": self.public_key,
            "required_trust_domain": "development",
        }
        arguments.update(changes)
        return verify_contract_attestation(**arguments)[2]

    def resign(self, value: dict[str, object], name: str) -> tuple[Path, Path]:
        directory = self.root / name
        directory.mkdir()
        _closure(self.payload, self.receipt, directory / "execution-closure")
        attestation = directory / f"codex-agent-contract-{VERSION}.attestation.json"
        write_canonical_json(attestation, value)
        return attestation, sign_manifest(attestation, self.private_key, value["signing"])

    def test_builds_and_verifies_exact_detached_files(self) -> None:
        attestation, signature, value = self.build()
        self.assertEqual(value, self.verify(attestation, signature))
        self.assertEqual(
            {
                "schemaVersion", "product", "contractVersion", "payload", "manifestSha256",
                "metadataReceiptSha256", "executionClosureSha256", "signing",
            },
            set(value),
        )
        self.assertNotIn("producer", value)
        self.assertEqual(
            sorted([attestation.name, signature.name, "execution-closure"]), sorted(path.name for path in attestation.parent.iterdir()),
        )

    def test_materializes_only_the_exact_attested_payload(self) -> None:
        attestation, signature, _ = self.build()
        output = self.root / "materialized"
        manifest = materialize_contract_payload(
            self.payload,
            self.receipt,
            attestation,
            signature,
            self.public_key,
            output,
            required_trust_domain="development",
            expected_contract_version=VERSION,
            required_components=("common", "jvm"),
        )
        self.assertEqual(VERSION, manifest["contractVersion"])
        self.assertEqual(
            manifest,
            verify_extracted_contract_directory(
                output,
                expected_contract_version=VERSION,
                required_components=("common", "jvm"),
            ),
        )
        with self.assertRaisesRegex(ValueError, "version"):
            materialize_contract_payload(
                self.payload,
                self.receipt,
                attestation,
                signature,
                self.public_key,
                self.root / "wrong-version",
                required_trust_domain="development",
                expected_contract_version="0.2.1",
                required_components=("common",),
            )
        cli_output = self.root / "cli-materialized"
        self.assertEqual(0, main([
            "materialize",
            "--payload", str(self.payload),
            "--metadata-receipt", str(self.receipt),
            "--attestation", str(attestation),
            "--signature", str(signature),
            "--public-key", str(self.public_key),
            "--required-trust-domain", "development",
            "--expected-contract-version", VERSION,
            "--required-component", "common",
            "--output-directory", str(cli_output),
        ]))
        self.assertTrue((cli_output / "contract-manifest.json").is_file())
        self.assertEqual(0, main([
            "materialize",
            "--payload", str(self.payload),
            "--metadata-receipt", str(self.receipt),
            "--attestation", str(attestation),
            "--signature", str(signature),
            "--public-key", str(self.public_key),
            "--required-trust-domain", "development",
            "--expected-contract-version", VERSION,
            "--required-component", "common",
            "--output-directory", str(cli_output),
            "--reuse-output-directory",
        ]))
        (cli_output / "contract-manifest.json").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(ValueError, "differs"):
            materialize_contract_payload(
                self.payload,
                self.receipt,
                attestation,
                signature,
                self.public_key,
                cli_output,
                required_trust_domain="development",
                expected_contract_version=VERSION,
                required_components=("common",),
                reuse_output_directory=True,
            )

    def test_payload_manifest_receipt_signing_key_signature_and_trust_tampering_fails(self) -> None:
        attestation, signature, original = self.build()

        self.payload.write_bytes(self.payload.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            self.verify(attestation, signature)
        _payload(self.payload)

        changed_manifest = copy.deepcopy(original)
        changed_manifest["manifestSha256"] = sha256_bytes(b"wrong manifest")
        manifest_attestation, manifest_signature = self.resign(changed_manifest, "manifest")
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.verify(manifest_attestation, manifest_signature)

        changed_receipt = copy.deepcopy(original)
        changed_receipt["metadataReceiptSha256"] = sha256_bytes(b"wrong receipt")
        receipt_attestation, receipt_signature = self.resign(changed_receipt, "receipt")
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.verify(receipt_attestation, receipt_signature)

        changed_signer = copy.deepcopy(original)
        changed_signer["signing"]["keyId"] = "development-tampered"
        signing_directory = self.root / "signing"
        signing_directory.mkdir()
        shutil.copytree(attestation.parent / "execution-closure", signing_directory / "execution-closure")
        signing_attestation = signing_directory / attestation.name
        write_canonical_json(signing_attestation, changed_signer)
        with self.assertRaises(ValueError):
            self.verify(signing_attestation, signature)

        changed_signing = copy.deepcopy(original)
        changed_signing["signing"]["trustDomain"] = "release"
        trust_attestation, trust_signature = self.resign(changed_signing, "trust")
        with self.assertRaisesRegex(ValueError, "not development trust"):
            self.verify(trust_attestation, trust_signature)

        other_private, other_public, _ = generate_development_key(self.root / "other-key")
        del other_private
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            self.verify(attestation, signature, public_key=other_public)

        damaged_directory = self.root / "damaged-signature"
        damaged_directory.mkdir()
        damaged = damaged_directory / signature.name
        signature_bytes = bytearray(signature.read_bytes())
        position = signature_bytes.index(b"\n") + 1
        signature_bytes[position] = ord("A") if signature_bytes[position] != ord("A") else ord("B")
        damaged.write_bytes(signature_bytes)
        with self.assertRaises(ValueError):
            self.verify(attestation, damaged)

        _receipt(self.receipt, self.payload, _producer(8), "development")
        with self.assertRaisesRegex(ValueError, "differs from the supplied receipt"):
            self.verify(attestation, signature)

    def test_release_and_development_use_the_same_verifier(self) -> None:
        self._check_release_attestation()

    def test_complete_release_handoff_keeps_exact_payload_receipt_and_pinned_public_key(self) -> None:
        self._check_release_attestation(complete_handoff=True)
        output = self.root / "release-output"
        self.assertEqual(self.payload.read_bytes(), (output / self.payload.name).read_bytes())
        self.assertEqual(self.public_key.read_bytes(), (output / "public-key.pub").read_bytes())
        self.assertEqual(self.receipt.read_bytes(), (output / "execution-closure/receipts/metadata.json").read_bytes())
        self.assertEqual(10, len(regular_file_inventory(output)))

    def test_release_attestation_preserves_exact_local_payload_and_receipt(self) -> None:
        local = {**_producer(7), "event": "local", "workflowPath": None,
                 "runId": None, "runAttempt": None, "pullRequest": None}
        _receipt(self.receipt, self.payload, local, "development")
        original = (self.payload.read_bytes(), self.receipt.read_bytes())
        self._check_release_attestation()
        self.assertEqual(original, (self.payload.read_bytes(), self.receipt.read_bytes()))

    def _check_release_attestation(self, *, complete_handoff=False) -> None:
        release_signing = {**self.signing, "trustDomain": "release"}
        keys = self.root / "release-keys"
        keys.mkdir()
        (keys / f"{release_signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        keyring = self.root / "keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": release_signing["namespace"],
            "algorithm": release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": release_signing["keyId"],
                "fingerprint": public_key_fingerprint(self.public_key.read_bytes()),
            },
            "retiredKeys": [],
        })
        output = self.root / "release-output"
        value = build_contract_attestation(
            self.payload,
            self.receipt,
            release_signing,
            self.private_key,
            self.public_key,
            output,
            execution_closure=_closure(self.payload, self.receipt, self.root / "release-closure"),
            keyring=keyring,
            keys_directory=keys,
            complete_handoff=complete_handoff,
        )
        stem = f"codex-agent-contract-{VERSION}.attestation"
        verified = verify_contract_attestation(
            self.payload,
            self.receipt,
            output / f"{stem}.json",
            output / f"{stem}.sig",
            self.public_key,
            required_trust_domain="release",
            keyring=keyring,
            keys_directory=keys,
        )
        self.assertEqual(value, verified[2])
        with self.assertRaisesRegex(ValueError, "requires a keyring"):
            verify_contract_attestation(
                self.payload,
                self.receipt,
                output / f"{stem}.json",
                output / f"{stem}.sig",
                self.public_key,
                required_trust_domain="release",
            )

    def test_release_creation_requires_the_active_key(self) -> None:
        release_signing = {**self.signing, "trustDomain": "release"}
        _, active_public, active_signing = generate_development_key(self.root / "active-key")
        keys = self.root / "retired-keys"
        keys.mkdir()
        (keys / f"{active_signing['keyId']}.pub").write_bytes(active_public.read_bytes())
        (keys / f"{release_signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        keyring = self.root / "retired-keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": release_signing["namespace"],
            "algorithm": release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": active_signing["keyId"],
                "fingerprint": active_signing["fingerprint"],
            },
            "retiredKeys": [{
                "keyId": release_signing["keyId"],
                "fingerprint": release_signing["fingerprint"],
            }],
        })
        with self.assertRaisesRegex(ValueError, "allowed release key"):
            build_contract_attestation(
                self.payload,
                self.receipt,
                release_signing,
                self.private_key,
                self.public_key,
                self.root / "retired-output",
                execution_closure=self.root / "not-read-retired-closure",
                keyring=keyring,
                keys_directory=keys,
            )

    def test_release_verification_accepts_the_original_key_after_retirement(self) -> None:
        release_signing = {**self.signing, "trustDomain": "release"}
        keys = self.root / "rotated-keys"
        keys.mkdir()
        (keys / f"{release_signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        keyring = self.root / "rotated-keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": release_signing["namespace"],
            "algorithm": release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": release_signing["keyId"],
                "fingerprint": release_signing["fingerprint"],
            },
            "retiredKeys": [],
        })
        output = self.root / "rotated-output"
        build_contract_attestation(
            self.payload,
            self.receipt,
            release_signing,
            self.private_key,
            self.public_key,
            output,
            execution_closure=_closure(self.payload, self.receipt, self.root / "rotated-closure"),
            keyring=keyring,
            keys_directory=keys,
        )
        _, new_public, new_signing = generate_development_key(self.root / "new-key")
        (keys / f"{new_signing['keyId']}.pub").write_bytes(new_public.read_bytes())
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": release_signing["namespace"],
            "algorithm": release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": new_signing["keyId"],
                "fingerprint": new_signing["fingerprint"],
            },
            "retiredKeys": [{
                "keyId": release_signing["keyId"],
                "fingerprint": release_signing["fingerprint"],
            }],
        })
        stem = f"codex-agent-contract-{VERSION}.attestation"
        self.assertEqual(
            VERSION,
            verify_contract_attestation(
                self.payload,
                self.receipt,
                output / f"{stem}.json",
                output / f"{stem}.sig",
                self.public_key,
                required_trust_domain="release",
                keyring=keyring,
                keys_directory=keys,
            )[0]["contractVersion"],
        )

    def test_payload_is_snapshotted_once_before_digest_and_semantic_verification(self) -> None:
        attestation, signature, _ = self.build()
        original = self.payload.read_bytes()
        replacement = self.root / "replacement" / self.payload.name
        _payload(replacement, "replacement")
        replacement_bytes = replacement.read_bytes()
        from ci.products import contract_attestation as module

        read = module.read_regular_file_bytes

        def replace_after_read(path: Path, **kwargs) -> bytes:
            contents = read(path, **kwargs)
            if Path(path) == self.payload:
                self.payload.write_bytes(replacement_bytes)
            return contents

        try:
            with mock.patch.object(module, "read_regular_file_bytes", side_effect=replace_after_read):
                self.assertEqual(
                    VERSION,
                    verify_contract_attestation(
                        self.payload,
                        self.receipt,
                        attestation,
                        signature,
                        self.public_key,
                        required_trust_domain="development",
                    )[0]["contractVersion"],
                )
        finally:
            self.payload.write_bytes(original)

    def test_attestation_signature_and_key_are_verified_from_one_snapshot(self) -> None:
        attestation, signature, value = self.build()
        changed = copy.deepcopy(value)
        changed["manifestSha256"] = sha256_bytes(b"replacement")
        replacement_attestation, replacement_signature = self.resign(changed, "replacement-signed")
        replacement_attestation_bytes = replacement_attestation.read_bytes()
        replacement_signature_bytes = replacement_signature.read_bytes()
        original_attestation = attestation.read_bytes()
        original_signature = signature.read_bytes()
        from ci.products import contract_attestation as module

        read = module.read_regular_file_bytes

        def replace_after_read(path: Path, **kwargs) -> bytes:
            contents = read(path, **kwargs)
            if Path(path) == attestation:
                attestation.write_bytes(replacement_attestation_bytes)
                signature.write_bytes(replacement_signature_bytes)
            return contents

        try:
            with mock.patch.object(module, "read_regular_file_bytes", side_effect=replace_after_read):
                with self.assertRaisesRegex(ValueError, "verification failed"):
                    self.verify(attestation, signature)
        finally:
            attestation.write_bytes(original_attestation)
            signature.write_bytes(original_signature)

    def test_producer_changes_only_the_external_receipt_and_attestation(self) -> None:
        payload_bytes = self.payload.read_bytes()
        first_attestation, _, first = self.build("first")
        first_bytes = first_attestation.read_bytes()
        first_receipt = self.receipt.read_bytes()
        _receipt(self.receipt, self.payload, _producer(8), "development")
        second_attestation, second_signature, second = self.build("second")
        self.assertEqual(payload_bytes, self.payload.read_bytes())
        self.assertNotEqual(first_receipt, self.receipt.read_bytes())
        self.assertNotEqual(first["metadataReceiptSha256"], second["metadataReceiptSha256"])
        self.assertNotEqual(first_bytes, second_attestation.read_bytes())
        self.assertEqual(second, self.verify(second_attestation, second_signature))

    def test_schema_is_exact(self) -> None:
        _, _, value = self.build()
        changed = {**value, "producer": _producer(7)}
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            validate_contract_attestation(changed)
        with self.assertRaisesRegex(ValueError, "schemaVersion"):
            validate_contract_attestation({**value, "schemaVersion": 1})

    def test_signed_closure_is_mandatory_and_rebound_raw_evidence_is_rejected(self) -> None:
        attestation, signature, value = self.build()
        source = attestation.parent / "execution-closure"
        retained_receipts = {phase: (source / f"receipts/{phase}.json").read_bytes()
                             for phase in ("binary", "package", "validation", "metadata")}
        for mutation in ("missing", "digest", "rebound-receipt"):
            with self.subTest(mutation=mutation):
                output = self.root / mutation
                shutil.copytree(attestation.parent, output)
                closure = output / "execution-closure"
                changed = copy.deepcopy(value)
                if mutation == "missing":
                    (closure / "execution/contract-execution.zip").unlink()
                elif mutation == "digest":
                    changed["executionClosureSha256"] = sha256_bytes(b"wrong")
                else:
                    binary = closure / "receipts/binary.json"
                    receipt = load_canonical_json(binary)
                    receipt["outputs"][-1]["sha256"] = sha256_bytes(b"wrong")
                    write_canonical_json(binary, receipt)
                    manifest_path = closure / "contract-execution-closure.json"
                    manifest = load_canonical_json(manifest_path)
                    record = next(item for item in manifest["files"] if item["relativePath"] == "receipts/binary.json")
                    record.update(bytes=len(binary.read_bytes()), sha256=sha256_bytes(binary.read_bytes()))
                    write_canonical_json(manifest_path, manifest)
                    changed["executionClosureSha256"] = sha256_bytes(manifest_path.read_bytes())
                changed_attestation = output / attestation.name
                write_canonical_json(changed_attestation, changed)
                (output / signature.name).unlink()
                changed_signature = sign_manifest(changed_attestation, self.private_key, changed["signing"])
                with self.assertRaises(ValueError):
                    self.verify(changed_attestation, changed_signature)
                if mutation != "digest":
                    with mock.patch("ci.products.contract_attestation.sign_manifest") as signer:
                        with self.assertRaises(ValueError):
                            build_contract_attestation(
                                self.payload, self.receipt, self.signing, self.private_key, self.public_key,
                                self.root / (mutation + "-rejected"), execution_closure=closure,
                            )
                        signer.assert_not_called()
        self.assertEqual(retained_receipts, {phase: (source / f"receipts/{phase}.json").read_bytes()
                                            for phase in retained_receipts})

    def test_runtime_neutral_python_closure_materializes_and_rejects_missing_raw_proof(self) -> None:
        attestation, signature, _ = self.build()
        repository = Path(__file__).resolve().parents[2]
        runtime_fixture = repository / "runtime/build-logic/src/test/kotlin/RuntimeIsolationFixtureTest.kt"
        declaration = runtime_fixture.read_text().split("private val runtimePythonClosure = setOf(", 1)[1].split("\n    )", 1)[0]
        isolated = self.root / "isolated-runtime-python"
        for relative in re.findall(r'"([^"\n]+)"', declaration):
            target = isolated / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repository / relative, target)
        command = [sys.executable, "-m", "ci.products.contract_attestation", "materialize",
                   "--payload", str(self.payload), "--metadata-receipt", str(self.receipt),
                   "--attestation", str(attestation), "--signature", str(signature),
                   "--public-key", str(self.public_key), "--required-trust-domain", "development",
                   "--expected-contract-version", VERSION, "--required-component", "common",
                   "--output-directory", str(self.root / "isolated-materialized")]
        environment = {**os.environ, "PYTHONPATH": str(isolated), "PYTHONDONTWRITEBYTECODE": "1"}
        accepted = subprocess.run(command, cwd=isolated, env=environment, capture_output=True, text=True, timeout=60)
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        (attestation.parent / "execution-closure/execution/contract-execution.zip").unlink()
        command[-1] = str(self.root / "rejected-materialized")
        rejected = subprocess.run(command, cwd=isolated, env=environment, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(0, rejected.returncode)
        self.assertIn("inventory", rejected.stderr)
        self.assertFalse((self.root / "rejected-materialized").exists())
