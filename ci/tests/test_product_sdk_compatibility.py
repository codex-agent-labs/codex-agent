from __future__ import annotations

import contextlib
import copy
import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products.aggregate import (
    RUNTIME_MAVEN_COMPONENTS,
    RUNTIME_TARGETS,
    runtime_component_id,
    validate_sdk_compatibility,
)
from ci.products.c_abi import TARGET_SPECS
from ci.products.contract import build_contract_bundle
from ci.products.contract_attestation import build_contract_attestation
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    public_key_fingerprint,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key
from ci.products import sdk_compatibility as sdk_compatibility_module
from ci.products.sdk_compatibility import main, produce_sdk_compatibility
from ci.products.signatures import generate_development_key
from ci.tests.test_contract_bundle import _write_staging


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE = "89abcdef0123456789abcdef0123456789abcdef"
LIBRARY_PATHS = {
    spec.classifier.removeprefix("c-abi-"): spec.library_path
    for spec in TARGET_SPECS.values()
}


def _producer() -> dict:
    return {
        "repository": "codex-agent-labs/codex-agent",
        "workflowPath": ".github/workflows/product-validation.yml",
        "commit": COMMIT,
        "tree": TREE,
        "event": "pull_request",
        "runId": 7,
        "runAttempt": 1,
        "pullRequest": 31,
    }


def _artifact(
    path: str,
    *,
    role: str = "runtime-resolution",
    component: str | None = None,
    target: str | None = None,
    contents: bytes = b"x",
) -> dict:
    value = {
        "path": path,
        "role": role,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }
    if component is not None:
        value["component"] = component
    if target is not None:
        value["target"] = target
    return value


def _contract_receipt(path: Path, payload: Path, trust_domain: str) -> None:
    inventory = [{
        "relativePath": "contract-input",
        "bytes": 1,
        "sha256": sha256_bytes(b"i"),
    }]
    inputs = {
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": "0.2.0",
        "upstreamArtifacts": [],
        "toolchainProfileDigest": sha256_bytes(b"toolchain"),
        "flagsDigest": sha256_bytes(b"flags"),
        "outputSchemaVersion": 1,
    }
    payload_bytes = payload.read_bytes()
    write_canonical_json(path, {
        "schemaVersion": 1,
        "product": "contract",
        "component": "contract",
        "phase": "metadata",
        "target": "common",
        "productVersion": "0.2.0",
        "buildKey": compute_build_key(
            product="contract", component="contract", phase="metadata",
            target="common", inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": [{
            "kind": "contract-bundle",
            "relativePath": f"outputs/{payload.name}",
            "bytes": len(payload_bytes),
            "sha256": sha256_bytes(payload_bytes),
        }],
        "producer": _producer(),
        "trustDomain": trust_domain,
        "result": "success",
    })


def _zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, contents in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, contents)


class Fixture:
    def __init__(
        self,
        root: Path,
        *,
        runtime_version: str = "0.2.0",
        trust_domain: str = "development",
        producer_run_id: int = 7,
    ) -> None:
        self.root = root
        root.mkdir()
        self.private_key, self.public_key, development_signing = generate_development_key(
            root / "keys",
        )
        self.signing = {**development_signing, "trustDomain": trust_domain}
        contract_staging = root / "contract-staging"
        _write_staging(contract_staging)
        self.contract_payload = root / "codex-agent-contract-0.2.0.zip"
        self.contract = build_contract_bundle(contract_staging, self.contract_payload, "0.2.0")
        self.contract_metadata_receipt = root / "contract-metadata-receipt.json"
        _contract_receipt(self.contract_metadata_receipt, self.contract_payload, trust_domain)

        self.contract_keyring = None
        self.contract_keys_directory = None
        self.runtime_keyring = None
        self.runtime_keys_directory = None
        if trust_domain == "release":
            self.contract_keyring, self.contract_keys_directory = self._keyring("contract")
            self.runtime_keyring, self.runtime_keys_directory = self._keyring("runtime")
        contract_attestation_directory = root / "contract-attestation"
        build_contract_attestation(
            self.contract_payload,
            self.contract_metadata_receipt,
            self.signing,
            self.private_key,
            self.public_key,
            contract_attestation_directory,
            keyring=self.contract_keyring,
            keys_directory=self.contract_keys_directory,
        )
        self.contract_attestation = contract_attestation_directory / \
            "codex-agent-contract-0.2.0.attestation.json"
        self.contract_attestation_signature = contract_attestation_directory / \
            "codex-agent-contract-0.2.0.attestation.sig"

        self.variant_bundles: dict[str, Path] = {}
        self.variant_values: dict[str, dict] = {}
        self.variant_phase_receipts: dict[str, dict[str, Path]] = {}
        self.variant_attestations: dict[str, Path] = {}
        self.variant_attestation_signatures: dict[str, Path] = {}
        self.variant_public_keys: dict[str, Path] = {}
        self.variant_attestation_values: dict[str, dict] = {}
        aggregate_variants = []
        aggregate_attestation_variants = []
        compatibility = {
            "cAbiVersion": "1.13.0",
            "minimumCAbiVersion": "1.0.0",
            "identitySchema": 1,
            "headerSha256": DIGEST_A,
            "symbolSetSha256": DIGEST_B,
            "symbolCount": 778,
            "appServerVersion": "0.149.0",
            "appServerReleaseTag": "rust-v0.149.0",
            "toolchainProfileDigests": {target: DIGEST_A for target in RUNTIME_TARGETS},
        }
        for target in RUNTIME_TARGETS:
            library = f"runtime-library-{target}\n".encode()
            c_abi_path = root / f"c-abi-{target}.zip"
            _zip(c_abi_path, {
                "include/codex_agent.h": b"header\n",
                LIBRARY_PATHS[target]: library,
            })
            members = {
                "app-server/runtime.zip": f"app-server-{target}\n".encode(),
                "c-abi/runtime.zip": c_abi_path.read_bytes(),
                "evidence/binary-phase.json": b"binary\n",
                "evidence/package-phase.json": b"package\n",
                "evidence/provenance.json": b"provenance\n",
                "evidence/sbom.json": b"sbom\n",
                "evidence/validation-phase.json": b"validation phase\n",
                "evidence/validation.json": b"validation\n",
            }
            roles = {
                "app-server/runtime.zip": "app-server-archive",
                "c-abi/runtime.zip": "c-abi-archive",
                "evidence/binary-phase.json": "binary-phase-evidence",
                "evidence/package-phase.json": "package-phase-evidence",
                "evidence/provenance.json": "provenance",
                "evidence/sbom.json": "sbom",
                "evidence/validation-phase.json": "validation-phase-evidence",
                "evidence/validation.json": "validation",
            }
            variant = {
                "schemaVersion": 1,
                "product": "runtime",
                "componentId": "",
                "runtimeCompatibilityVersion": "0.2.0",
                "target": target,
                "contract": {
                    "digest": self.contract["contractDigest"],
                    "componentDigest": self.contract["components"][target]["sha256"],
                },
                "cAbi": {
                    "version": compatibility["cAbiVersion"],
                    "minimumCompatibleVersion": compatibility["minimumCAbiVersion"],
                    "identitySchemaVersion": compatibility["identitySchema"],
                    "headerSha256": compatibility["headerSha256"],
                    "symbolSetSha256": compatibility["symbolSetSha256"],
                    "symbolCount": compatibility["symbolCount"],
                },
                "appServer": {
                    "version": compatibility["appServerVersion"],
                    "releaseTag": compatibility["appServerReleaseTag"],
                    "binarySha256": DIGEST_C,
                },
                "inputs": {
                    "binaryBuildKey": sha256_bytes(f"build-{target}".encode()),
                    "binaryOutputInventoryDigest": DIGEST_B,
                },
                "innerArtifacts": [
                    _artifact(path, role=roles[path], contents=contents)
                    for path, contents in sorted(members.items())
                ],
                "toolchainProfile": {"id": target, "digest": DIGEST_A},
            }
            variant["componentId"] = runtime_component_id(variant)
            manifest_bytes = canonical_json_bytes(variant)
            bundle = root / (
                f"codex-agent-runtime-variant-{target}-"
                f"{variant['componentId'].removeprefix('sha256:')}.zip"
            )
            _zip(bundle, {**members, "runtime-variant-manifest.json": manifest_bytes})
            self.variant_bundles[target] = bundle
            self.variant_values[target] = variant
            self.variant_public_keys[target] = self.public_key
            self.variant_phase_receipts[target] = {}
            for phase in ("binary", "package", "validation", "metadata"):
                receipt = root / f"{target}-{phase}-receipt.json"
                receipt.write_text(
                    f"{target}:{phase}:producer-run-{producer_run_id}\n", encoding="utf-8",
                )
                self.variant_phase_receipts[target][phase] = receipt
            attestation = root / f"{target}.attestation.json"
            signature = root / f"{target}.attestation.sig"
            attestation.write_text(
                f"{target}:attestation:producer-run-{producer_run_id}\n", encoding="utf-8",
            )
            signature.write_text(f"{target}:signature\n", encoding="utf-8")
            self.variant_attestations[target] = attestation
            self.variant_attestation_signatures[target] = signature
            aggregate_record = {
                "target": target,
                "componentId": variant["componentId"],
                "bundleSha256": sha256_bytes(bundle.read_bytes()),
                "manifestSha256": sha256_bytes(manifest_bytes),
            }
            aggregate_variants.append(aggregate_record)
            variant_attestation = {
                "target": target,
                "payload": {"sha256": aggregate_record["bundleSha256"]},
                "manifestSha256": aggregate_record["manifestSha256"],
                "phaseReceipts": {
                    phase: sha256_bytes(path.read_bytes())
                    for phase, path in self.variant_phase_receipts[target].items()
                },
            }
            self.variant_attestation_values[target] = variant_attestation
            aggregate_attestation_variants.append({
                **aggregate_record,
                "variantAttestationSha256": sha256_bytes(attestation.read_bytes()),
                "phaseReceipts": dict(variant_attestation["phaseReceipts"]),
            })

        self.aggregate = {
            "schemaVersion": 1,
            "product": "runtime",
            "runtimeVersion": runtime_version,
            "runtimeCompatibilityVersion": "0.2.0",
            "contract": {
                "version": self.contract["contractVersion"],
                "digest": self.contract["contractDigest"],
            },
            "variants": aggregate_variants,
            "runtimeMavenFiles": [
                _artifact(f"maven/{component}/runtime.bin", component=component)
                for component in sorted(RUNTIME_MAVEN_COMPONENTS)
            ],
            "adapterEvidence": [
                _artifact("evidence/jvm.json", role="adapter", target="jvm"),
                _artifact("evidence/node-js.json", role="adapter", target="node-js"),
                _artifact("evidence/node-wasm.json", role="adapter", target="node-wasm"),
            ],
            "compatibility": compatibility,
        }
        self.runtime_manifest = root / f"codex-agent-runtime-{runtime_version}-manifest.json"
        write_canonical_json(self.runtime_manifest, self.aggregate)
        self.runtime_metadata_receipt = root / "runtime-metadata-receipt.json"
        self.runtime_attestation = root / "runtime.attestation.json"
        self.runtime_attestation_signature = root / "runtime.attestation.sig"
        self.runtime_metadata_receipt.write_text(
            f"aggregate-receipt:producer-run-{producer_run_id}\n", encoding="utf-8",
        )
        self.runtime_attestation.write_text(
            f"aggregate-attestation:producer-run-{producer_run_id}\n", encoding="utf-8",
        )
        self.runtime_attestation_signature.write_text("aggregate-signature\n", encoding="utf-8")
        self.aggregate_attestation = {"variants": aggregate_attestation_variants}

    def _keyring(self, owner: str) -> tuple[Path, Path]:
        directory = self.root / f"{owner}-release-keys"
        directory.mkdir()
        (directory / f"{self.signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        keyring = self.root / f"{owner}-keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "namespace": self.signing["namespace"],
            "algorithm": self.signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": self.signing["keyId"],
                "fingerprint": public_key_fingerprint(self.public_key.read_bytes()),
            },
            "retiredKeys": [],
        })
        return keyring, directory

    def arguments(self, output: Path) -> dict:
        return {
            "sdk_version": "0.2.0",
            "compatible_release_range": ">=0.2.0 <0.3.0",
            "compatible_runtime_compatibility_range": ">=0.2.0 <0.3.0",
            "contract_payload": self.contract_payload,
            "contract_metadata_receipt": self.contract_metadata_receipt,
            "contract_attestation": self.contract_attestation,
            "contract_attestation_signature": self.contract_attestation_signature,
            "contract_public_key": self.public_key,
            "runtime_manifest": self.runtime_manifest,
            "runtime_metadata_receipt": self.runtime_metadata_receipt,
            "runtime_attestation": self.runtime_attestation,
            "runtime_attestation_signature": self.runtime_attestation_signature,
            "runtime_public_key": self.public_key,
            "variant_bundles": self.variant_bundles,
            "variant_phase_receipts": self.variant_phase_receipts,
            "variant_attestations": self.variant_attestations,
            "variant_attestation_signatures": self.variant_attestation_signatures,
            "variant_public_keys": self.variant_public_keys,
            "required_trust_domain": self.signing["trustDomain"],
            "output": output,
            "contract_keyring": self.contract_keyring,
            "contract_keys_directory": self.contract_keys_directory,
            "runtime_keyring": self.runtime_keyring,
            "runtime_keys_directory": self.runtime_keys_directory,
        }

    def request(self) -> dict:
        request = {
            "schemaVersion": 1,
            "sdkVersion": "0.2.0",
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
            "contractPayload": str(self.contract_payload),
            "contractMetadataReceipt": str(self.contract_metadata_receipt),
            "contractAttestation": str(self.contract_attestation),
            "contractAttestationSignature": str(self.contract_attestation_signature),
            "contractPublicKey": str(self.public_key),
            "runtimeManifest": str(self.runtime_manifest),
            "runtimeMetadataReceipt": str(self.runtime_metadata_receipt),
            "runtimeAttestation": str(self.runtime_attestation),
            "runtimeAttestationSignature": str(self.runtime_attestation_signature),
            "runtimePublicKey": str(self.public_key),
            "variantBundles": {target: str(path) for target, path in self.variant_bundles.items()},
            "variantPhaseReceipts": {
                target: {phase: str(path) for phase, path in receipts.items()}
                for target, receipts in self.variant_phase_receipts.items()
            },
            "variantAttestations": {
                target: str(path) for target, path in self.variant_attestations.items()
            },
            "variantAttestationSignatures": {
                target: str(path) for target, path in self.variant_attestation_signatures.items()
            },
            "variantPublicKeys": {
                target: str(path) for target, path in self.variant_public_keys.items()
            },
            "requiredTrustDomain": self.signing["trustDomain"],
        }
        for name, path in (
            ("contractKeyring", self.contract_keyring),
            ("contractKeysDirectory", self.contract_keys_directory),
            ("runtimeKeyring", self.runtime_keyring),
            ("runtimeKeysDirectory", self.runtime_keys_directory),
        ):
            if path is not None:
                request[name] = str(path)
        return request

    def _verify_aggregate(self, *arguments: Path, **options: object) -> tuple[dict, dict, dict]:
        expected = (
            self.runtime_manifest,
            self.runtime_metadata_receipt,
            self.runtime_attestation,
            self.runtime_attestation_signature,
            self.public_key,
        )
        if tuple(map(Path, arguments)) != expected or options != {
            "required_trust_domain": self.signing["trustDomain"],
            "keyring": self.runtime_keyring,
            "keys_directory": self.runtime_keys_directory,
        }:
            raise ValueError("Runtime aggregate attestation inputs are cross-paired")
        return self.aggregate, {}, self.aggregate_attestation

    def _verify_variant(self, *arguments: Path, **options: object) -> tuple[dict, dict, dict]:
        bundle = Path(arguments[0])
        targets = [
            target for target, path in self.variant_bundles.items()
            if path.name == bundle.name
        ]
        if len(targets) != 1:
            raise ValueError("Runtime variant payload is not one selected target")
        target = targets[0]
        receipts = self.variant_phase_receipts[target]
        expected = (
            bundle,
            receipts["binary"], receipts["package"], receipts["validation"], receipts["metadata"],
            self.variant_attestations[target], self.variant_attestation_signatures[target],
            self.variant_public_keys[target],
        )
        if tuple(map(Path, arguments)) != expected or options != {
            "required_trust_domain": self.signing["trustDomain"],
            "keyring": self.runtime_keyring,
            "keys_directory": self.runtime_keys_directory,
        }:
            raise ValueError(f"Runtime variant attestation inputs are cross-paired: {target}")
        return self.variant_values[target], {}, self.variant_attestation_values[target]

    @contextlib.contextmanager
    def verifiers(self):
        with patch(
            "ci.products.sdk_compatibility.verify_runtime_aggregate_attestation",
            side_effect=self._verify_aggregate,
        ), patch(
            "ci.products.sdk_compatibility.verify_runtime_variant_attestation",
            side_effect=self._verify_variant,
        ):
            yield


class SdkCompatibilityProducerTest(unittest.TestCase):
    def produce(self, fixture: Fixture, output: Path, **changes: object) -> dict:
        arguments = fixture.arguments(output)
        arguments.update(changes)
        with fixture.verifiers():
            return produce_sdk_compatibility(**arguments)

    def test_produces_only_deterministic_authenticated_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            first = root / "first/sdk-compatibility.json"
            second = root / "second/sdk-compatibility.json"
            first.parent.mkdir()
            second.parent.mkdir()
            value = self.produce(fixture, first)
            repeated = self.produce(fixture, second)
            self.assertEqual(value, repeated)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(canonical_json_bytes(validate_sdk_compatibility(value)), first.read_bytes())
            self.assertEqual(
                sha256_bytes(fixture.runtime_manifest.read_bytes()),
                value["runtime"]["defaultManifestSha256"],
            )
            aggregates = {record["target"]: record for record in fixture.aggregate["variants"]}
            for record in value["runtime"]["embeddedVariants"]:
                expected = aggregates[record["target"]]
                self.assertEqual(expected["componentId"], record["componentId"])
                self.assertEqual(expected["bundleSha256"], record["bundleSha256"])
                self.assertEqual(expected["manifestSha256"], record["manifestSha256"])
                self.assertEqual(
                    sha256_bytes(f"runtime-library-{record['target']}\n".encode()),
                    record["runtimeLibrarySha256"],
                )

    def test_key_receipt_and_producer_changes_do_not_change_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            first_fixture = Fixture(root / "first-fixture", producer_run_id=7)
            second_fixture = Fixture(root / "second-fixture", producer_run_id=99)
            first = root / "first/sdk-compatibility.json"
            second = root / "second/sdk-compatibility.json"
            first.parent.mkdir()
            second.parent.mkdir()
            self.produce(first_fixture, first)
            self.produce(second_fixture, second)
            self.assertNotEqual(first_fixture.public_key.read_bytes(), second_fixture.public_key.read_bytes())
            self.assertNotEqual(
                first_fixture.runtime_metadata_receipt.read_bytes(),
                second_fixture.runtime_metadata_receipt.read_bytes(),
            )
            self.assertNotEqual(
                first_fixture.runtime_attestation.read_bytes(),
                second_fixture.runtime_attestation.read_bytes(),
            )
            self.assertNotEqual(
                first_fixture.variant_attestations["linux-x64"].read_bytes(),
                second_fixture.variant_attestations["linux-x64"].read_bytes(),
            )
            self.assertEqual(first_fixture.runtime_manifest.read_bytes(), second_fixture.runtime_manifest.read_bytes())
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_tamper_and_cross_paired_inputs_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            cases: list[dict[str, object]] = []

            bad_contract_signature = root / fixture.contract_attestation_signature.name
            bad_contract_signature.write_bytes(
                fixture.contract_attestation_signature.read_bytes()[:-1] + b"x",
            )
            cases.append({"contract_attestation_signature": bad_contract_signature})
            bad_contract_payload = root / "bad-contract" / fixture.contract_payload.name
            bad_contract_payload.parent.mkdir()
            bad_contract_payload.write_bytes(fixture.contract_payload.read_bytes() + b"x")
            cases.append({"contract_payload": bad_contract_payload})
            bad_contract_receipt = root / "bad-contract-receipt.json"
            receipt = load_canonical_json_bytes(fixture.contract_metadata_receipt.read_bytes())
            receipt["producer"]["runId"] += 1
            write_canonical_json(bad_contract_receipt, receipt)
            cases.append({"contract_metadata_receipt": bad_contract_receipt})
            cases.append({"runtime_metadata_receipt": fixture.variant_phase_receipts["linux-x64"]["metadata"]})

            swapped_bundles = dict(fixture.variant_bundles)
            swapped_bundles["macos-arm64"], swapped_bundles["macos-x64"] = (
                swapped_bundles["macos-x64"], swapped_bundles["macos-arm64"],
            )
            cases.append({"variant_bundles": swapped_bundles})
            swapped_attestations = dict(fixture.variant_attestations)
            swapped_attestations["macos-arm64"], swapped_attestations["macos-x64"] = (
                swapped_attestations["macos-x64"], swapped_attestations["macos-arm64"],
            )
            cases.append({"variant_attestations": swapped_attestations})
            swapped_receipts = copy.deepcopy(fixture.variant_phase_receipts)
            swapped_receipts["linux-arm64"]["package"] = \
                fixture.variant_phase_receipts["linux-x64"]["package"]
            cases.append({"variant_phase_receipts": swapped_receipts})
            swapped_signatures = dict(fixture.variant_attestation_signatures)
            swapped_signatures["macos-arm64"], swapped_signatures["macos-x64"] = (
                swapped_signatures["macos-x64"], swapped_signatures["macos-arm64"],
            )
            cases.append({"variant_attestation_signatures": swapped_signatures})
            cases.append({
                "runtime_attestation_signature":
                    fixture.variant_attestation_signatures["linux-x64"],
            })
            wrong_public_key = root / "wrong-runtime.pub"
            wrong_public_key.write_text("not an SSH public key\n", encoding="utf-8")
            cases.append({"runtime_public_key": wrong_public_key})
            wrong_variant_keys = dict(fixture.variant_public_keys)
            wrong_variant_keys["windows-x64"] = wrong_public_key
            cases.append({"variant_public_keys": wrong_variant_keys})
            cases.append({"compatible_runtime_compatibility_range": ">=0.3.0 <0.4.0"})

            target = "linux-x64"
            tampered_bundle = root / fixture.variant_bundles[target].name
            tampered_bundle.write_bytes(fixture.variant_bundles[target].read_bytes() + b"tampered")
            bundles = dict(fixture.variant_bundles)
            bundles[target] = tampered_bundle
            cases.append({"variant_bundles": bundles})

            for index, changes in enumerate(cases):
                output = root / f"rejected-{index}/sdk-compatibility.json"
                output.parent.mkdir()
                with self.subTest(index=index), self.assertRaises(ValueError):
                    self.produce(fixture, output, **changes)
                self.assertFalse(output.exists())

            aggregate_record = fixture.aggregate_attestation["variants"][0]
            original_receipt = aggregate_record["phaseReceipts"]["binary"]
            aggregate_record["phaseReceipts"]["binary"] = DIGEST_C
            output = root / "aggregate-cross-pair/sdk-compatibility.json"
            output.parent.mkdir()
            with self.assertRaisesRegex(ValueError, "aggregate attestation"):
                self.produce(fixture, output)
            self.assertFalse(output.exists())
            aggregate_record["phaseReceipts"]["binary"] = original_receipt

    def test_trust_keyring_inputs_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            release = Fixture(root / "release", trust_domain="release")
            output = root / "release-output/sdk-compatibility.json"
            output.parent.mkdir()
            self.assertEqual("0.2.0", self.produce(release, output)["contract"]["version"])

            for field in (
                "contract_keyring", "contract_keys_directory",
                "runtime_keyring", "runtime_keys_directory",
            ):
                rejected = root / f"missing-{field}/sdk-compatibility.json"
                rejected.parent.mkdir()
                with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "paired|requires",
                ):
                    self.produce(release, rejected, **{field: None})

            development = Fixture(root / "development")
            rejected = root / "development-keyring/sdk-compatibility.json"
            rejected.parent.mkdir()
            with self.assertRaisesRegex(ValueError, "rejects release keyring"):
                self.produce(
                    development,
                    rejected,
                    runtime_keyring=release.runtime_keyring,
                    runtime_keys_directory=release.runtime_keys_directory,
                )

    def test_concurrent_output_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            output = root / "output/sdk-compatibility.json"
            output.parent.mkdir()
            sentinel = b"concurrently published\n"
            publish = sdk_compatibility_module._publish_output

            def inject_race(
                expected: bytes, descriptor: int, parent: Path, name: str, *, max_bytes: int,
            ) -> bool:
                (parent / name).write_bytes(sentinel)
                return publish(expected, descriptor, parent, name, max_bytes=max_bytes)

            with patch.object(
                sdk_compatibility_module, "_publish_output", side_effect=inject_race,
            ) as publication, self.assertRaisesRegex(ValueError, "conflicts"):
                self.produce(fixture, output)
            publication.assert_called_once()
            self.assertEqual(sentinel, output.read_bytes())
            self.assertEqual([output.name], [path.name for path in output.parent.iterdir()])

    @unittest.skipIf(os.name == "nt", "POSIX descriptor-relative parent race")
    def test_concurrent_parent_swap_cannot_redirect_or_delete_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            output = root / "output/sdk-compatibility.json"
            output.parent.mkdir()
            original_parent = root / "original-output"
            external = b"external parent bytes\n"
            publish = sdk_compatibility_module._publish_output

            def swap_parent(
                expected: bytes, descriptor: int, parent: Path, name: str, *, max_bytes: int,
            ) -> bool:
                parent.rename(original_parent)
                parent.mkdir()
                (parent / name).write_bytes(external)
                return publish(expected, descriptor, parent, name, max_bytes=max_bytes)

            with patch.object(
                sdk_compatibility_module, "_publish_output", side_effect=swap_parent,
            ) as publication, self.assertRaisesRegex(ValueError, "parent changed"):
                self.produce(fixture, output)
            publication.assert_called_once()
            self.assertEqual([], list(original_parent.iterdir()))
            self.assertEqual(external, output.read_bytes())
            self.assertEqual([output.name], [path.name for path in output.parent.iterdir()])

    def test_selecting_a_new_embedded_default_changes_only_release_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture", runtime_version="0.2.0")
            old_output = root / "old/sdk-compatibility.json"
            unchanged_output = root / "unchanged/sdk-compatibility.json"
            new_output = root / "new/sdk-compatibility.json"
            for path in (old_output, unchanged_output, new_output):
                path.parent.mkdir()
            old = self.produce(fixture, old_output)
            self.produce(fixture, unchanged_output)

            fixture.aggregate["runtimeVersion"] = "0.2.1"
            fixture.runtime_manifest = fixture.root / "codex-agent-runtime-0.2.1-manifest.json"
            write_canonical_json(fixture.runtime_manifest, fixture.aggregate)
            new = self.produce(fixture, new_output)
            self.assertEqual(old_output.read_bytes(), unchanged_output.read_bytes())
            self.assertNotEqual(old_output.read_bytes(), new_output.read_bytes())
            self.assertEqual(old["runtime"]["embeddedVariants"], new["runtime"]["embeddedVariants"])
            self.assertEqual("0.2.0", old["runtime"]["defaultRuntimeVersion"])
            self.assertEqual("0.2.1", new["runtime"]["defaultRuntimeVersion"])

    def test_exact_request_schema_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            request = root / "request.json"
            output = root / "output/sdk-compatibility.json"
            output.parent.mkdir()
            write_canonical_json(request, fixture.request())
            with fixture.verifiers():
                self.assertEqual(0, main(["--request", str(request), "--output", str(output)]))
            self.assertEqual(
                canonical_json_bytes(validate_sdk_compatibility(
                    load_canonical_json_bytes(output.read_bytes()),
                )),
                output.read_bytes(),
            )

            valid = fixture.request()
            cases = {
                "unknown": {**valid, "unknown": "value"},
                "missing": {key: value for key, value in valid.items() if key != "runtimeAttestation"},
                "unsupported-schema": {**valid, "schemaVersion": 2},
                "non-string": {**valid, "sdkVersion": 2},
                "legacy-runtime-signature": {**valid, "runtimeSignature": "legacy.sig"},
                "legacy-contract-fields": {
                    **{
                        key: value for key, value in valid.items()
                        if key not in {
                            "contractPayload", "contractMetadataReceipt",
                            "contractAttestation", "contractAttestationSignature",
                        }
                    },
                    "contractManifest": "contract-manifest.json",
                    "contractSignature": "contract-manifest.sig",
                },
                "traversal": {**valid, "runtimeManifest": "../runtime.json"},
                "keyring-without-directory": {
                    **valid, "runtimeKeyring": str(fixture.runtime_metadata_receipt),
                },
                "missing-target": {
                    **valid,
                    "variantBundles": {
                        target: value for target, value in valid["variantBundles"].items()
                        if target != "windows-x64"
                    },
                },
                "missing-phase": {
                    **valid,
                    "variantPhaseReceipts": {
                        **valid["variantPhaseReceipts"],
                        "linux-x64": {
                            phase: value
                            for phase, value in valid["variantPhaseReceipts"]["linux-x64"].items()
                            if phase != "metadata"
                        },
                    },
                },
            }
            for name, value in cases.items():
                invalid = root / f"{name}.json"
                write_canonical_json(invalid, value)
                sentinel = root / f"{name}-output/sdk-compatibility.json"
                sentinel.parent.mkdir()
                sentinel.write_bytes(b"keep\n")
                with fixture.verifiers(), contextlib.redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as error:
                    main(["--request", str(invalid), "--output", str(sentinel)])
                self.assertEqual(2, error.exception.code)
                self.assertEqual(b"keep\n", sentinel.read_bytes())

            canonical_request = root / "canonical-request.json"
            write_canonical_json(canonical_request, valid)
            existing = root / "existing/sdk-compatibility.json"
            existing.parent.mkdir()
            existing.write_bytes(b"keep\n")
            with fixture.verifiers(), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(["--request", str(canonical_request), "--output", str(existing)])
            self.assertEqual(2, error.exception.code)
            self.assertEqual(b"keep\n", existing.read_bytes())

            noncanonical_request = root / "noncanonical-request.json"
            noncanonical_request.write_text("{\n  \"schemaVersion\": 1\n}\n", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(["--request", str(noncanonical_request), "--output", str(existing)])
            self.assertEqual(2, error.exception.code)
            self.assertEqual(b"keep\n", existing.read_bytes())

            request_link = root / "request-link.json"
            request_link.symlink_to(canonical_request)
            with contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(["--request", str(request_link), "--output", str(existing)])
            self.assertEqual(2, error.exception.code)
            self.assertEqual(b"keep\n", existing.read_bytes())

            with contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main([
                    "--request", str(canonical_request), "--output", str(existing), "--unknown",
                ])
            self.assertEqual(2, error.exception.code)
            self.assertEqual(b"keep\n", existing.read_bytes())


if __name__ == "__main__":
    unittest.main()
