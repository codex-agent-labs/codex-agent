from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from ci.products.contract import build_contract_bundle
from ci.products.contract_attestation import build_contract_attestation
from ci.products.contract_projection import (
    VerifiedContractProjection,
    verify_contract_component_projection,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json,
    public_key_fingerprint,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, write_output_manifest
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_bundle import PRODUCER, VERSION, _write_staging


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="contract-projection-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.private_key, self.public_key, self.signing = generate_development_key(
            self.root / "keys",
        )
        staging = self.root / "contract-staging"
        _write_staging(staging)
        self.bundle = self.root / "bundle" / f"codex-agent-contract-{VERSION}.zip"
        self.manifest = build_contract_bundle(staging, self.bundle, VERSION)
        self.stage = self.root / "stage"
        (self.stage / "outputs").mkdir(parents=True)
        shutil.copyfile(self.bundle, self.stage / "outputs" / self.bundle.name)
        self._refresh_output_manifest()
        self.receipt_path = self.root / "phase-receipt.json"
        self.receipt = self._receipt(PRODUCER)
        write_canonical_json(self.receipt_path, self.receipt)
        self.attestation_path, self.signature_path, self.attestation = self._attest(
            self.receipt_path,
            "attestation",
        )

    def _refresh_output_manifest(self) -> None:
        write_output_manifest(
            self.stage,
            "contract",
            "contract",
            "metadata",
            "common",
            VERSION,
            {"contract-bundle": "outputs"},
        )

    def _receipt(
        self,
        producer: dict[str, object],
        *,
        trust: str = "development",
    ) -> dict[str, object]:
        inventory = [{
            "relativePath": "source/Contract.kt",
            "bytes": 1,
            "sha256": sha256_bytes(b"a"),
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
        value = {
            "schemaVersion": 1,
            "product": "contract",
            "component": "contract",
            "phase": "metadata",
            "target": "common",
            "productVersion": VERSION,
            "buildKey": "",
            "inputs": inputs,
            "outputs": copy.deepcopy(
                load_canonical_json(self.stage / "output-manifest.json")["outputs"],
            ),
            "producer": copy.deepcopy(producer),
            "trustDomain": trust,
            "result": "success",
        }
        value["buildKey"] = compute_build_key(
            product="contract",
            component="contract",
            phase="metadata",
            target="common",
            inputs=inputs,
        )
        return value

    def _attest(
        self,
        receipt: Path,
        name: str,
    ) -> tuple[Path, Path, dict[str, object]]:
        output = self.root / name
        value = build_contract_attestation(
            self.stage / "outputs" / self.bundle.name,
            receipt,
            self.signing,
            self.private_key,
            self.public_key,
            output,
        )
        stem = f"codex-agent-contract-{VERSION}.attestation"
        return output / f"{stem}.json", output / f"{stem}.sig", value

    def _resign(
        self,
        value: dict[str, object],
        name: str,
    ) -> tuple[Path, Path]:
        output = self.root / name
        output.mkdir()
        path = output / f"codex-agent-contract-{VERSION}.attestation.json"
        write_canonical_json(path, value)
        return path, sign_manifest(path, self.private_key, value["signing"])

    def _verify(self, **changes):
        arguments = {
            "stage_root": self.stage,
            "phase_receipt": self.receipt_path,
            "attestation": self.attestation_path,
            "attestation_signature": self.signature_path,
            "public_key": self.public_key,
            "expected_trust_domain": "development",
            "expected_contract_version": VERSION,
            "required_components": ("jvm", "node-js"),
        }
        arguments.update(changes)
        return verify_contract_component_projection(**arguments)

    def test_derives_only_the_exact_authenticated_projection(self) -> None:
        projection = self._verify().receipt_value()
        with zipfile.ZipFile(self.bundle) as archive:
            manifest_bytes = archive.read("contract-manifest.json")
        self.assertEqual({
            "schemaVersion": 1,
            "receiptSha256": sha256_bytes(self.receipt_path.read_bytes()),
            "bundlePath": f"outputs/codex-agent-contract-{VERSION}.zip",
            "bundleSha256": self.receipt["outputs"][0]["sha256"],
            "manifestSha256": sha256_bytes(manifest_bytes),
            "contractVersion": VERSION,
            "contractDigest": self.manifest["contractDigest"],
            "componentDigests": [
                {"component": component, "sha256": self.manifest["components"][component]["sha256"]}
                for component in ("jvm", "node-js")
            ],
        }, projection)
        self.assertNotIn("producer", projection)
        self.assertEqual(
            projection,
            self._verify(phase_receipt=self.receipt_path.read_bytes()).receipt_value(),
        )
        self.assertEqual(
            projection,
            self._verify(required_components=("node-js", "jvm")).receipt_value(),
        )
        with self.assertRaises(TypeError):
            VerifiedContractProjection(projection, object())

    def test_rejects_wrong_payload_manifest_and_receipt_digests(self) -> None:
        mutations = (
            ("payload", lambda value: value["payload"].__setitem__(
                "sha256", sha256_bytes(b"wrong payload"),
            )),
            ("manifest", lambda value: value.__setitem__(
                "manifestSha256", sha256_bytes(b"wrong manifest"),
            )),
            ("receipt", lambda value: value.__setitem__(
                "metadataReceiptSha256", sha256_bytes(b"wrong receipt"),
            )),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                changed = copy.deepcopy(self.attestation)
                mutate(changed)
                path, signature = self._resign(changed, f"wrong-{name}")
                with self.assertRaises(ValueError):
                    self._verify(attestation=path, attestation_signature=signature)

    def test_rejects_receipt_producer_mutation_without_manifest_producer_coupling(self) -> None:
        changed = copy.deepcopy(self.receipt)
        changed["producer"]["runId"] = 8
        write_canonical_json(self.receipt_path, changed)
        with self.assertRaises(ValueError):
            self._verify()

    def test_rejects_wrong_trust_key_and_signature(self) -> None:
        with self.assertRaises(ValueError):
            self._verify(expected_trust_domain="release")

        _, wrong_key, _ = generate_development_key(self.root / "wrong-key")
        with self.assertRaises(ValueError):
            self._verify(public_key=wrong_key)

        damaged = self.root / "damaged" / self.signature_path.name
        damaged.parent.mkdir()
        damaged.write_bytes(self.signature_path.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            self._verify(attestation_signature=damaged)

    def test_delegates_release_keyring_verification_to_the_attestation(self) -> None:
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
        output = self.root / "release-attestation"
        build_contract_attestation(
            self.stage / "outputs" / self.bundle.name,
            self.receipt_path,
            release_signing,
            self.private_key,
            self.public_key,
            output,
            keyring=keyring,
            keys_directory=keys,
        )
        stem = f"codex-agent-contract-{VERSION}.attestation"
        projection = self._verify(
            attestation=output / f"{stem}.json",
            attestation_signature=output / f"{stem}.sig",
            expected_trust_domain="release",
            keyring=keyring,
            keys_directory=keys,
        ).receipt_value()
        self.assertEqual(VERSION, projection["contractVersion"])

    def test_rejects_cross_paired_coherent_receipt_and_attestation(self) -> None:
        original_receipt = self.root / "original-receipt.json"
        original_receipt.write_bytes(self.receipt_path.read_bytes())
        write_canonical_json(self.receipt_path, self._receipt({**PRODUCER, "runId": 8}))
        other_attestation, other_signature, _ = self._attest(self.receipt_path, "other-attestation")

        with self.assertRaises(ValueError):
            self._verify(
                phase_receipt=original_receipt,
                attestation=other_attestation,
                attestation_signature=other_signature,
            )

    def test_rejects_malformed_components_receipt_identity_and_stage_outputs(self) -> None:
        for components in ((), ("jvm", "jvm"), ("unknown",)):
            with self.subTest(components=components), self.assertRaises(ValueError):
                self._verify(required_components=components)

        wrong_identity = copy.deepcopy(self.receipt)
        wrong_identity["target"] = "jvm"
        wrong_identity["buildKey"] = compute_build_key(
            product="contract",
            component="contract",
            phase="metadata",
            target="jvm",
            inputs=wrong_identity["inputs"],
        )
        wrong_receipt = self.root / "wrong-identity.json"
        write_canonical_json(wrong_receipt, wrong_identity)
        with self.assertRaises(ValueError):
            self._verify(phase_receipt=wrong_receipt)

        duplicate = self.stage / "outputs" / "duplicate.zip"
        shutil.copyfile(self.stage / "outputs" / self.bundle.name, duplicate)
        self._refresh_output_manifest()
        with self.assertRaises(ValueError):
            self._verify()


if __name__ == "__main__":
    unittest.main()
