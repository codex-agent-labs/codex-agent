from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest

from ci.products.contract import build_contract_bundle
from ci.products.contract_projection import (
    VerifiedContractProjection,
    verify_contract_component_projection,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.plan import main as plan_main
from ci.products.receipt import compute_build_key, write_output_manifest
from ci.products.signatures import (
    ALGORITHM,
    NAMESPACE,
    generate_development_key,
    sign_manifest,
)
from ci.tests.test_contract_bundle import (
    PRODUCER,
    VERSION,
    _write_staging,
    _write_zip,
    _zip_entries,
)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.private_key, self.public_key, self.signing = generate_development_key(
            self.root / "keys",
        )
        staging = self.root / "contract-staging"
        _write_staging(staging)
        self.bundle = self.root / "bundle" / f"codex-agent-contract-{VERSION}.zip"
        self.manifest = build_contract_bundle(
            staging,
            self.bundle,
            VERSION,
            PRODUCER,
            self.private_key,
            self.public_key,
            self.signing,
        )
        self.stage = self.root / "stage"
        outputs = self.stage / "outputs"
        outputs.mkdir(parents=True)
        shutil.copyfile(self.bundle, outputs / self.bundle.name)
        self._refresh_manifest()
        self.receipt_path = self.root / "phase-receipt.json"
        self.receipt = self._receipt()
        write_canonical_json(self.receipt_path, self.receipt)
        self._signing_index = 0

    def _refresh_manifest(self) -> None:
        write_output_manifest(
            self.stage,
            "contract",
            "contract",
            "metadata",
            "common",
            VERSION,
            {"contract-bundle": "outputs"},
        )

    def _receipt(self, *, trust: str = "development") -> dict[str, object]:
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
            "producer": copy.deepcopy(PRODUCER),
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

    def _verify(self, **changes):
        arguments = {
            "stage_root": self.stage,
            "phase_receipt": self.receipt_path,
            "public_key": self.public_key,
            "expected_trust_domain": "development",
            "expected_contract_version": VERSION,
            "required_components": ("jvm", "node-js"),
        }
        arguments.update(changes)
        return verify_contract_component_projection(**arguments)

    def _refresh_receipt_outputs(self) -> None:
        self.receipt = self._receipt(trust=self.receipt["trustDomain"])
        write_canonical_json(self.receipt_path, self.receipt)

    def _resign_stage_bundle(self, manifest: dict[str, object]) -> None:
        archive = self.stage / "outputs" / self.bundle.name
        entries = _zip_entries(archive)
        self._signing_index += 1
        signing_root = self.root / f"resign-{self._signing_index}"
        signing_root.mkdir()
        manifest_path = signing_root / "contract-manifest.json"
        write_canonical_json(manifest_path, manifest)
        signature_path = sign_manifest(manifest_path, self.private_key, manifest["signing"])
        replacements = {
            "contract-manifest.json": manifest_path.read_bytes(),
            "contract-manifest.sig": signature_path.read_bytes(),
        }
        _write_zip(archive, [
            (name, replacements.get(name, contents), attributes)
            for name, contents, attributes in entries
        ])
        self._refresh_manifest()
        self._refresh_receipt_outputs()

    def test_derives_only_the_exact_authenticated_projection_from_path_or_bytes(self) -> None:
        verified = self._verify()
        projection = verified.receipt_value()
        expected_path = f"outputs/codex-agent-contract-{VERSION}.zip"
        self.assertEqual({
            "schemaVersion": 1,
            "receiptSha256": sha256_bytes(self.receipt_path.read_bytes()),
            "bundlePath": expected_path,
            "bundleSha256": self.receipt["outputs"][0]["sha256"],
            "manifestSha256": sha256_bytes(
                next(contents for name, contents, _ in _zip_entries(self.bundle)
                     if name == "contract-manifest.json"),
            ),
            "contractVersion": VERSION,
            "contractDigest": self.manifest["contractDigest"],
            "componentDigests": [
                {"component": name, "sha256": self.manifest["components"][name]["sha256"]}
                for name in ("jvm", "node-js")
            ],
        }, projection)
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

    def test_plan_cli_derives_projection_from_evidence_paths(self) -> None:
        request = self.root / "plan-request.json"
        output = self.root / "plan-output.json"
        inventory = [{
            "relativePath": "runtime/Runtime.kt",
            "bytes": 1,
            "sha256": sha256_bytes(b"r"),
        }]
        write_canonical_json(request, {
            "schemaVersion": 1,
            "product": "runtime",
            "component": "jvm",
            "phase": "binary",
            "target": "jvm",
            "inventory": inventory,
            "versions": {
                "contract": VERSION,
                "runtime-compatibility": VERSION,
                "runtime-release": VERSION,
                "sdk": VERSION,
            },
            "upstreamReceipts": [self.receipt],
            "contractEvidence": {
                "stageRoot": str(self.stage),
                "phaseReceipt": str(self.receipt_path),
                "publicKey": str(self.public_key),
                "expectedTrustDomain": "development",
                "keyring": None,
                "keysDirectory": None,
            },
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        })
        self.assertEqual(0, plan_main(["--request", str(request), "--output", str(output)]))
        result = load_canonical_json(output)
        self.assertEqual(
            ["jvm"],
            [
                record["component"]
                for record in result["inputs"]["upstreamArtifacts"][0]
                ["contractProjection"]["componentDigests"]
            ],
        )

    def test_rejects_malformed_component_requests_and_release_arguments(self) -> None:
        for components in ((), ("jvm", "jvm"), ("unknown",)):
            with self.subTest(components=components), self.assertRaises(ValueError):
                self._verify(required_components=components)
        with self.assertRaises(ValueError):
            self._verify(keyring=self.root / "unused")
        with self.assertRaises(ValueError):
            self._verify(expected_trust_domain="release")

    def test_rejects_receipt_output_identity_producer_and_bundle_mismatches(self) -> None:
        mutations = []
        wrong_identity = copy.deepcopy(self.receipt)
        wrong_identity["target"] = "jvm"
        wrong_identity["buildKey"] = compute_build_key(
            product="contract",
            component="contract",
            phase="metadata",
            target="jvm",
            inputs=wrong_identity["inputs"],
        )
        wrong_producer = copy.deepcopy(self.receipt)
        wrong_producer["producer"]["runId"] = 8
        wrong_output = copy.deepcopy(self.receipt)
        wrong_output["outputs"][0]["sha256"] = sha256_bytes(b"wrong")
        mutations.extend((wrong_identity, wrong_producer, wrong_output))
        for index, receipt in enumerate(mutations):
            path = self.root / f"receipt-{index}.json"
            write_canonical_json(path, receipt)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self._verify(phase_receipt=path)

        archive = self.stage / "outputs" / self.bundle.name
        archive.write_bytes(archive.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            self._verify()

    def test_rejects_a_resigned_manifest_with_malformed_components(self) -> None:
        malformed = copy.deepcopy(self.manifest)
        malformed["components"]["unexpected"] = copy.deepcopy(
            malformed["components"]["jvm"],
        )
        self._resign_stage_bundle(malformed)
        with self.assertRaises(ValueError):
            self._verify()

    def test_rejects_wrong_path_duplicate_bundle_key_and_signature(self) -> None:
        archive = self.stage / "outputs" / self.bundle.name
        wrong_path = self.stage / "outputs" / "wrong.zip"
        archive.rename(wrong_path)
        self._refresh_manifest()
        self._refresh_receipt_outputs()
        with self.assertRaises(ValueError):
            self._verify()

        wrong_path.rename(archive)
        (self.stage / "outputs" / "duplicate.zip").write_bytes(archive.read_bytes())
        self._refresh_manifest()
        self._refresh_receipt_outputs()
        with self.assertRaises(ValueError):
            self._verify()

        (self.stage / "outputs" / "duplicate.zip").unlink()
        _, wrong_key, _ = generate_development_key(self.root / "wrong-key")
        with self.assertRaises(ValueError):
            self._verify(public_key=wrong_key)

        entries = _zip_entries(archive)
        entries = [
            (name, contents + b"x" if name == "contract-manifest.sig" else contents, attributes)
            for name, contents, attributes in entries
        ]
        _write_zip(archive, entries)
        self._refresh_manifest()
        self._refresh_receipt_outputs()
        with self.assertRaises(ValueError):
            self._verify()

    def test_release_projection_requires_and_matches_the_tracked_key(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        release_signing = {
            "algorithm": ALGORITHM,
            "namespace": NAMESPACE,
            "trustDomain": "release",
            "keyId": "release-test",
            "fingerprint": self.signing["fingerprint"],
        }
        manifest["signing"] = release_signing
        self._resign_stage_bundle(manifest)
        self.receipt = self._receipt(trust="release")
        write_canonical_json(self.receipt_path, self.receipt)

        keys = self.root / "release-keys"
        keys.mkdir()
        (keys / "release-test.pub").write_bytes(self.public_key.read_bytes())
        keyring = self.root / "keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": NAMESPACE,
            "algorithm": ALGORITHM,
            "trustDomain": "release",
            "activeKey": {
                "keyId": "release-test",
                "fingerprint": self.signing["fingerprint"],
            },
            "retiredKeys": [],
        })
        projection = self._verify(
            expected_trust_domain="release",
            keyring=keyring,
            keys_directory=keys,
        ).receipt_value()
        self.assertEqual(VERSION, projection["contractVersion"])

        _, untracked_public, untracked_metadata = generate_development_key(
            self.root / "untracked-release",
        )
        (keys / "release-untracked.pub").write_bytes(untracked_public.read_bytes())
        untracked_keyring = self.root / "untracked-keyring.json"
        write_canonical_json(untracked_keyring, {
            "schemaVersion": 1,
            "namespace": NAMESPACE,
            "algorithm": ALGORITHM,
            "trustDomain": "release",
            "activeKey": {
                "keyId": "release-untracked",
                "fingerprint": untracked_metadata["fingerprint"],
            },
            "retiredKeys": [],
        })
        with self.assertRaises(ValueError):
            self._verify(
                expected_trust_domain="release",
                keyring=untracked_keyring,
                keys_directory=keys,
            )

        _, wrong_public, _ = generate_development_key(self.root / "wrong-release")
        with self.assertRaises(ValueError):
            self._verify(
                public_key=wrong_public,
                expected_trust_domain="release",
                keyring=keyring,
                keys_directory=keys,
            )


if __name__ == "__main__":
    unittest.main()
