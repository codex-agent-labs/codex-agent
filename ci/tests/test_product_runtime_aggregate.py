from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ci.products.runtime_aggregate as runtime_aggregate_module
from ci.products.aggregate import RUNTIME_MAVEN_COMPONENTS, RUNTIME_TARGETS
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, write_output_manifest, write_phase_receipt
from ci.products.runtime_aggregate import (
    build_runtime_aggregate_attestation,
    produce_runtime_aggregate,
    validate_runtime_aggregate_attestation,
    verify_runtime_aggregate_attestation,
    verify_runtime_aggregate_attestation_closure,
)
from ci.products.signatures import generate_development_key
from ci.tests.test_products import phase_receipt


VERSION = "0.2.2"
COMPATIBILITY = "0.2.0"
CONTRACT_DIGEST = sha256_bytes(b"contract")


def _rekey(receipt: dict) -> None:
    receipt["buildKey"] = compute_build_key(
        product=receipt["product"],
        component=receipt["component"],
        phase=receipt["phase"],
        target=receipt["target"],
        inputs=receipt["inputs"],
    )


def _adapter_identities() -> list[tuple[str, str, str]]:
    return sorted([
        *(("jvm", phase, "jvm") for phase in ("binary", "package", "metadata")),
        *(("jvm", "validation", target) for target in RUNTIME_TARGETS),
        *(("node-js", phase, "node-js") for phase in ("binary", "package", "metadata")),
        *(("node-js", "validation", target) for target in (*RUNTIME_TARGETS, "node-js-binding")),
        *(("node-wasm", phase, "node-wasm") for phase in ("binary", "package", "metadata")),
        *(("node-wasm", "validation", target) for target in RUNTIME_TARGETS),
    ])


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        self.private_key, self.public_key, self.signing = generate_development_key(
            root / "aggregate-key",
        )
        self.variant_bundles = {}
        self.variant_phase_receipts = {}
        self.variant_attestations = {}
        self.variant_signatures = {}
        self.variant_keys = {}
        self.validation_evidence = {}
        self.variant_manifests = {}
        for index, target in enumerate(RUNTIME_TARGETS, start=1):
            component_id = sha256_bytes(f"component-{target}".encode())
            bundle = root / f"variant-{target}.zip"
            bundle.write_bytes(f"bundle-{target}\n".encode())
            manifest = {
                "runtimeCompatibilityVersion": COMPATIBILITY,
                "target": target,
                "componentId": component_id,
                "contract": {
                    "digest": CONTRACT_DIGEST,
                    "componentDigest": sha256_bytes(f"contract-{target}".encode()),
                },
                "cAbi": {
                    "version": "1.13.0",
                    "minimumCompatibleVersion": "1.0.0",
                    "identitySchemaVersion": 1,
                    "headerSha256": sha256_bytes(b"header"),
                    "symbolSetSha256": sha256_bytes(b"symbols"),
                    "symbolCount": 778,
                },
                "appServer": {
                    "version": "0.149.0",
                    "releaseTag": "rust-v0.149.0",
                    "binarySha256": sha256_bytes(f"app-server-{target}".encode()),
                },
                "toolchainProfile": {
                    "id": target,
                    "digest": sha256_bytes(f"toolchain-{target}".encode()),
                },
            }
            receipts = {}
            receipt_paths = {}
            for phase_index, phase in enumerate(("binary", "package", "validation", "metadata")):
                receipt = phase_receipt("development")
                receipt.update({
                    "product": "runtime",
                    "component": target,
                    "phase": phase,
                    "target": target,
                    "productVersion": f"0.2.{phase_index + index}",
                })
                receipt["inputs"]["versionIdentity"] = COMPATIBILITY
                receipt["producer"]["runId"] = 100 * index + phase_index
                _rekey(receipt)
                path = root / f"{target}-{phase}.receipt.json"
                write_canonical_json(path, receipt)
                receipts[phase] = receipt
                receipt_paths[phase] = path
            attestation = {
                "target": target,
                "componentId": component_id,
                "payload": {
                    "fileName": bundle.name,
                    "bytes": bundle.stat().st_size,
                    "sha256": sha256_file(bundle),
                },
                "manifestSha256": sha256_bytes(f"manifest-{target}".encode()),
                "phaseReceipts": {
                    phase: sha256_file(path) for phase, path in receipt_paths.items()
                },
            }
            attestation_path = root / f"variant-{target}.attestation.json"
            write_canonical_json(attestation_path, attestation)
            signature = root / f"variant-{target}.attestation.sig"
            signature.write_bytes(b"fixture signature\n")
            validation = root / f"{target}-validation.json"
            validation.write_bytes(b"{}\n")
            self.variant_bundles[target] = bundle
            self.variant_phase_receipts[target] = receipt_paths
            self.variant_attestations[target] = attestation_path
            self.variant_signatures[target] = signature
            self.variant_keys[target] = self.public_key
            self.validation_evidence[target] = validation
            self.variant_manifests[target] = manifest

        self.maven_inputs = []
        for component in RUNTIME_MAVEN_COMPONENTS:
            source = root / "maven" / component / "artifact.jar"
            source.parent.mkdir(parents=True)
            source.write_bytes(f"maven-{component}\n".encode())
            self.maven_inputs.append({
                "path": f"maven/{component}/artifact.jar",
                "role": "runtime-resolution",
                "component": component,
                "file": source,
            })
        self.adapter_evidence = {}
        for target in ("jvm", "node-js", "node-wasm"):
            path = root / f"{target}-projection.json"
            write_canonical_json(path, {"component": target, "reports": []})
            self.adapter_evidence[target] = path
        self.adapter_receipts = []
        for index, (component, phase, target) in enumerate(_adapter_identities(), start=1):
            receipt = phase_receipt("release" if index % 2 else "development")
            receipt.update({
                "product": "runtime",
                "component": component,
                "phase": phase,
                "target": target,
                "productVersion": f"0.2.{index}",
            })
            receipt["inputs"]["versionIdentity"] = COMPATIBILITY
            receipt["producer"]["runId"] = 1000 + index
            _rekey(receipt)
            path = root / f"adapter-{index:02d}.receipt.json"
            write_canonical_json(path, receipt)
            self.adapter_receipts.append({
                "component": component,
                "phase": phase,
                "target": target,
                "receipt": path,
            })

    def verify_variant(self, bundle: Path, binary: Path, package: Path, validation: Path,
                       metadata: Path, attestation: Path, signature: Path, public_key: Path,
                       **_: object) -> tuple[dict, dict, dict]:
        target = next(
            target for target, path in self.variant_bundles.items() if Path(bundle) == path
        )
        value = load_canonical_json_bytes(Path(attestation).read_bytes())
        if value["target"] != target or value["payload"]["sha256"] != sha256_file(Path(bundle)):
            raise ValueError("Fixture variant cross-pair")
        paths = dict(zip(("binary", "package", "validation", "metadata"),
                         (binary, package, validation, metadata), strict=True))
        if value["phaseReceipts"] != {
            phase: sha256_file(Path(path)) for phase, path in paths.items()
        }:
            raise ValueError("Fixture variant receipt mismatch")
        return self.variant_manifests[target], {
            phase: load_canonical_json_bytes(Path(path).read_bytes())
            for phase, path in paths.items()
        }, value

    def produce_arguments(self, output: Path) -> dict:
        return {
            "runtime_version": VERSION,
            "contract_payload": self.root / "contract.zip",
            "contract_metadata_receipt": self.root / "contract.receipt.json",
            "contract_attestation": self.root / "contract.attestation.json",
            "contract_attestation_signature": self.root / "contract.attestation.sig",
            "contract_public_key": self.public_key,
            "required_trust_domain": "development",
            "variant_bundles": self.variant_bundles,
            "variant_phase_receipts": self.variant_phase_receipts,
            "variant_attestations": self.variant_attestations,
            "variant_attestation_signatures": self.variant_signatures,
            "variant_public_keys": self.variant_keys,
            "variant_validation_evidence": self.validation_evidence,
            "runtime_maven_files": self.maven_inputs,
            "adapter_evidence": self.adapter_evidence,
            "output_directory": output,
        }

    def produce(self, output: Path) -> dict:
        with patch.object(
            runtime_aggregate_module,
            "verify_contract_attestation",
            return_value=({
                "contractVersion": "0.2.0",
                "contractDigest": CONTRACT_DIGEST,
            }, {}, {}),
        ), patch.object(
            runtime_aggregate_module,
            "verify_runtime_variant_attestation",
            side_effect=self.verify_variant,
        ):
            return produce_runtime_aggregate(**self.produce_arguments(output))

    def metadata_receipt(self, manifest: Path) -> Path:
        stage = self.root / f"aggregate-stage-{len(list(self.root.glob('aggregate-stage-*')))}"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs" / manifest.name).write_bytes(manifest.read_bytes())
        write_output_manifest(
            stage, "runtime", "runtime-aggregate", "metadata", "aggregate", VERSION,
            {"runtime-aggregate": "outputs"},
        )
        receipt_root = self.root / f"aggregate-receipt-{len(list(self.root.glob('aggregate-receipt-*')))}"
        receipt_root.mkdir()
        inputs = phase_receipt()["inputs"]
        inputs["versionIdentity"] = VERSION
        key = compute_build_key(
            product="runtime", component="runtime-aggregate", phase="metadata",
            target="aggregate", inputs=inputs,
        )
        write_phase_receipt(
            stage, receipt_root, "runtime", "runtime-aggregate", "metadata", "aggregate",
            VERSION, key, inputs, phase_receipt()["producer"], "development",
        )
        return receipt_root / "phase-receipt.json"

    def build_attestation(self, manifest: Path, metadata_receipt: Path, output: Path,
                          *, private_key: Path | None = None, public_key: Path | None = None,
                          signing: dict | None = None) -> dict:
        with patch.object(
            runtime_aggregate_module,
            "verify_runtime_variant_attestation",
            side_effect=self.verify_variant,
        ), patch.object(
            runtime_aggregate_module,
            "verify_runtime_aggregate_artifacts",
            return_value={},
        ):
            return build_runtime_aggregate_attestation(
                manifest, metadata_receipt, self.variant_bundles,
                self.variant_phase_receipts, self.variant_attestations,
                self.variant_signatures, self.variant_keys, self.validation_evidence,
                self.adapter_receipts, signing or self.signing,
                private_key or self.private_key, public_key or self.public_key, output,
                required_variant_trust_domain="development",
                contract_payload=self.root / "contract.zip",
                contract_metadata_receipt=self.root / "contract.receipt.json",
                contract_attestation=self.root / "contract.attestation.json",
                contract_attestation_signature=self.root / "contract.attestation.sig",
                contract_public_key=self.public_key,
                adapter_report_files={},
                runtime_maven_files=self.maven_inputs,
                adapter_evidence=self.adapter_evidence,
            )


class RuntimeAggregateProducerTest(unittest.TestCase):
    def test_payload_is_deterministic_and_contains_only_release_content_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            first_output = root / "first"
            second_output = root / "second"
            first_output.mkdir()
            second_output.mkdir()
            first = fixture.produce(first_output)
            second = fixture.produce(second_output)
            self.assertEqual(first["manifestPath"].read_bytes(), second["manifestPath"].read_bytes())
            self.assertEqual({
                "schemaVersion", "product", "runtimeVersion", "runtimeCompatibilityVersion",
                "contract", "variants", "runtimeMavenFiles", "adapterEvidence", "compatibility",
            }, set(first["manifest"]))
            self.assertTrue(all(set(record) == {
                "target", "componentId", "bundleSha256", "manifestSha256",
            } for record in first["manifest"]["variants"]))
            forbidden = canonical_json_bytes(first["manifest"])
            for value in (b"signing", b"producer", b"sourceRuntimeVersion", b"receiptSha256",
                          b"phaseReceipts", b"reused", b"transport"):
                self.assertNotIn(value, forbidden)

            for target in RUNTIME_TARGETS:
                for phase, path in fixture.variant_phase_receipts[target].items():
                    receipt = load_canonical_json_bytes(path.read_bytes())
                    receipt["producer"]["runId"] += 9000
                    receipt["productVersion"] = "0.2.99"
                    write_canonical_json(path, receipt)
                    attestation = load_canonical_json_bytes(
                        fixture.variant_attestations[target].read_bytes(),
                    )
                    attestation["phaseReceipts"][phase] = sha256_file(path)
                    write_canonical_json(fixture.variant_attestations[target], attestation)
            third_output = root / "third"
            third_output.mkdir()
            third = fixture.produce(third_output)
            self.assertEqual(first["manifestPath"].read_bytes(), third["manifestPath"].read_bytes())

    def test_external_attestation_binds_payload_receipts_and_mixed_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            payload_output = root / "payload"
            payload_output.mkdir()
            manifest = fixture.produce(payload_output)["manifestPath"]
            metadata = fixture.metadata_receipt(manifest)
            output = root / "attestation"
            value = fixture.build_attestation(manifest, metadata, output)
            attestation = output / f"codex-agent-runtime-{VERSION}.attestation.json"
            signature = output / f"codex-agent-runtime-{VERSION}.attestation.sig"
            aggregate, receipt, verified = verify_runtime_aggregate_attestation(
                manifest, metadata, attestation, signature, fixture.public_key,
                required_trust_domain="development",
            )
            self.assertEqual(value, verified)
            self.assertEqual(VERSION, aggregate["runtimeVersion"])
            self.assertEqual(VERSION, receipt["productVersion"])
            self.assertEqual(25, len(value["adapterReceipts"]))
            self.assertEqual(list(RUNTIME_TARGETS), [record["target"] for record in value["variants"]])
            self.assertTrue(all(set(record) == {
                "target", "componentId", "bundleSha256", "manifestSha256",
                "variantAttestationSha256", "phaseReceipts",
            } for record in value["variants"]))
            with patch.object(
                runtime_aggregate_module,
                "verify_runtime_variant_attestation",
                side_effect=fixture.verify_variant,
            ):
                _, variant_receipts, adapter_receipts = \
                    verify_runtime_aggregate_attestation_closure(
                        aggregate, verified,
                        variant_bundles=fixture.variant_bundles,
                        variant_phase_receipts=fixture.variant_phase_receipts,
                        variant_attestations=fixture.variant_attestations,
                        variant_attestation_signatures=fixture.variant_signatures,
                        variant_public_keys=fixture.variant_keys,
                        adapter_receipts=fixture.adapter_receipts,
                        required_variant_trust_domain="development",
                        variant_validation_evidence=fixture.validation_evidence,
                    )
            self.assertEqual(5, len(variant_receipts))
            self.assertEqual(25, len(adapter_receipts))
            self.assertEqual({"development", "release"}, {
                receipt["trustDomain"] for receipt in adapter_receipts
            })
            invalid_membership = copy.deepcopy(value)
            invalid_membership["adapterReceipts"][0]["target"] = "wrong-target"
            with self.assertRaisesRegex(ValueError, "exact closure"):
                validate_runtime_aggregate_attestation(invalid_membership)

            other_private, other_public, other_signing = generate_development_key(root / "other-key")
            other_output = root / "other-attestation"
            other = fixture.build_attestation(
                manifest, metadata, other_output, private_key=other_private,
                public_key=other_public, signing=other_signing,
            )
            self.assertEqual(manifest.read_bytes(), payload_output.joinpath(manifest.name).read_bytes())
            self.assertNotEqual(value["signing"], other["signing"])
            self.assertEqual(value["payload"], other["payload"])

    def test_payload_receipt_attestation_signature_key_and_closure_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            payload_output = root / "payload"
            payload_output.mkdir()
            manifest = fixture.produce(payload_output)["manifestPath"]
            metadata = fixture.metadata_receipt(manifest)
            output = root / "attestation"
            fixture.build_attestation(manifest, metadata, output)
            attestation = output / f"codex-agent-runtime-{VERSION}.attestation.json"
            signature = output / f"codex-agent-runtime-{VERSION}.attestation.sig"

            bad_manifest = root / manifest.name
            bad_manifest.write_bytes(manifest.read_bytes() + b"tampered")
            bare_receipt = root / "bare.receipt.json"
            bare = load_canonical_json_bytes(metadata.read_bytes())
            bare["outputs"][0]["relativePath"] = manifest.name
            write_canonical_json(bare_receipt, bare)
            bad_signature = root / signature.name
            bad_signature.write_bytes(signature.read_bytes() + b"tampered\n")
            _, wrong_public, _ = generate_development_key(root / "wrong-key")
            for replacement in (
                {"manifest": bad_manifest},
                {"metadata_receipt": bare_receipt},
                {"signature": bad_signature},
                {"public_key": wrong_public},
            ):
                arguments = {
                    "manifest": manifest,
                    "metadata_receipt": metadata,
                    "attestation": attestation,
                    "signature": signature,
                    "public_key": fixture.public_key,
                }
                arguments.update(replacement)
                with self.subTest(field=next(iter(replacement))), self.assertRaises(ValueError):
                    verify_runtime_aggregate_attestation(
                        **arguments, required_trust_domain="development",
                    )

            aggregate, _, value = verify_runtime_aggregate_attestation(
                manifest, metadata, attestation, signature, fixture.public_key,
                required_trust_domain="development",
            )
            target = RUNTIME_TARGETS[0]
            original_variant = fixture.variant_attestations[target].read_bytes()
            fixture.variant_attestations[target].write_bytes(
                fixture.variant_attestations[RUNTIME_TARGETS[1]].read_bytes(),
            )
            with patch.object(
                runtime_aggregate_module,
                "verify_runtime_variant_attestation",
                side_effect=fixture.verify_variant,
            ), self.assertRaises(ValueError):
                verify_runtime_aggregate_attestation_closure(
                    aggregate, value,
                    variant_bundles=fixture.variant_bundles,
                    variant_phase_receipts=fixture.variant_phase_receipts,
                    variant_attestations=fixture.variant_attestations,
                    variant_attestation_signatures=fixture.variant_signatures,
                    variant_public_keys=fixture.variant_keys,
                    adapter_receipts=fixture.adapter_receipts,
                    required_variant_trust_domain="development",
                )
            fixture.variant_attestations[target].write_bytes(original_variant)

            adapter_path = Path(fixture.adapter_receipts[0]["receipt"])
            adapter = load_canonical_json_bytes(adapter_path.read_bytes())
            adapter["producer"]["runId"] += 1
            write_canonical_json(adapter_path, adapter)
            with patch.object(
                runtime_aggregate_module,
                "verify_runtime_variant_attestation",
                side_effect=fixture.verify_variant,
            ), self.assertRaisesRegex(ValueError, "closure differs"):
                verify_runtime_aggregate_attestation_closure(
                    aggregate, value,
                    variant_bundles=fixture.variant_bundles,
                    variant_phase_receipts=fixture.variant_phase_receipts,
                    variant_attestations=fixture.variant_attestations,
                    variant_attestation_signatures=fixture.variant_signatures,
                    variant_public_keys=fixture.variant_keys,
                    adapter_receipts=fixture.adapter_receipts,
                    required_variant_trust_domain="development",
                )

    def test_missing_extra_unsafe_and_immutable_outputs_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            output = root / "missing"
            output.mkdir()
            arguments = fixture.produce_arguments(output)
            arguments["variant_bundles"] = dict(fixture.variant_bundles)
            arguments["variant_bundles"].pop(RUNTIME_TARGETS[-1])
            with patch.object(
                runtime_aggregate_module, "verify_contract_attestation",
                return_value=({"contractVersion": "0.2.0", "contractDigest": CONTRACT_DIGEST}, {}, {}),
            ), self.assertRaises(ValueError):
                produce_runtime_aggregate(**arguments)
            self.assertFalse(any(output.iterdir()))

            occupied = root / "occupied"
            occupied.mkdir()
            sentinel = occupied / "sentinel"
            sentinel.write_bytes(b"preserve\n")
            with self.assertRaisesRegex(ValueError, "must be empty"):
                fixture.produce(occupied)
            self.assertEqual(b"preserve\n", sentinel.read_bytes())

            raced = root / "raced"
            raced.mkdir()
            publish = runtime_aggregate_module._publish_output

            def inject_race(expected: bytes, descriptor: int, parent: Path, name: str,
                            *, max_bytes: int) -> bool:
                (parent / name).write_bytes(b"concurrent\n")
                return publish(expected, descriptor, parent, name, max_bytes=max_bytes)

            with patch.object(
                runtime_aggregate_module, "_publish_output", side_effect=inject_race,
            ), self.assertRaises(ValueError):
                fixture.produce(raced)
            self.assertEqual(b"concurrent\n", next(raced.iterdir()).read_bytes())

            payload_output = root / "payload"
            payload_output.mkdir()
            manifest = fixture.produce(payload_output)["manifestPath"]
            metadata = fixture.metadata_receipt(manifest)
            attestation_output = root / "attestation"
            attestation_output.mkdir()
            attestation_sentinel = attestation_output / "sentinel"
            attestation_sentinel.write_bytes(b"preserve\n")
            with self.assertRaisesRegex(ValueError, "must not exist"):
                fixture.build_attestation(manifest, metadata, attestation_output)
            self.assertEqual(b"preserve\n", attestation_sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
