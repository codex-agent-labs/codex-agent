from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ci.products.contract_attestation import (
    build_contract_attestation,
    main,
    materialize_contract_payload,
    validate_contract_attestation,
    verify_contract_attestation,
)
from ci.products.contract import build_contract_bundle
from ci.products.contract_model import verify_extracted_contract_directory
from ci.products.inventory import (
    canonical_json_bytes,
    public_key_fingerprint,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_bundle import _write_staging


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
    with tempfile.TemporaryDirectory(prefix="contract-attestation-payload-", dir=path.parent) as temporary:
        root = Path(temporary)
        staging = root / "staging"
        _write_staging(staging, target_hash_salt=marker.encode())
        built = root / path.name
        build_contract_bundle(staging, built, VERSION)
        shutil.copyfile(built, path)


def _receipt(path: Path, payload: Path, producer: dict[str, object], trust: str) -> None:
    inventory = [{
        "relativePath": "contract-input",
        "bytes": 1,
        "sha256": sha256_bytes(b"i"),
    }]
    inputs = {
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": VERSION,
        "upstreamArtifacts": [],
        "toolchainProfileDigest": sha256_bytes(b"toolchain"),
        "flagsDigest": sha256_bytes(b"flags"),
        "outputSchemaVersion": 1,
    }
    contents = payload.read_bytes()
    write_canonical_json(path, {
        "schemaVersion": 1,
        "product": "contract",
        "component": "contract",
        "phase": "metadata",
        "target": "common",
        "productVersion": VERSION,
        "buildKey": compute_build_key(
            product="contract", component="contract", phase="metadata", target="common", inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": [{
            "kind": "contract-bundle",
            "relativePath": f"outputs/{payload.name}",
            "bytes": len(contents),
            "sha256": sha256_bytes(contents),
        }],
        "producer": producer,
        "trustDomain": trust,
        "result": "success",
    })


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
        )
        stem = f"codex-agent-contract-{VERSION}.attestation"
        return output / f"{stem}.json", output / f"{stem}.sig", value

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
        attestation = directory / f"codex-agent-contract-{VERSION}.attestation.json"
        write_canonical_json(attestation, value)
        return attestation, sign_manifest(attestation, self.private_key, value["signing"])

    def test_builds_and_verifies_exact_detached_files(self) -> None:
        attestation, signature, value = self.build()
        self.assertEqual(value, self.verify(attestation, signature))
        self.assertEqual(
            {
                "schemaVersion", "product", "contractVersion", "payload", "manifestSha256",
                "metadataReceiptSha256", "signing",
            },
            set(value),
        )
        self.assertNotIn("producer", value)
        self.assertEqual(
            [attestation.name, signature.name], sorted(path.name for path in attestation.parent.iterdir()),
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
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.verify(attestation, signature)

    def test_release_and_development_use_the_same_verifier(self) -> None:
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
            keyring=keyring,
            keys_directory=keys,
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
