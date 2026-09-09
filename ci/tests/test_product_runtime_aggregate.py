from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ci.products.runtime_aggregate as runtime_aggregate_module
from ci.products.aggregate import (
    RUNTIME_MAVEN_COMPONENTS,
    RUNTIME_TARGETS,
    verify_runtime_aggregate_artifacts,
)
from ci.products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    regular_file_inventory,
    sha256_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.receipt import (
    compute_build_key,
    output_inventory_digest,
    write_output_manifest,
    write_phase_receipt,
)
from ci.products.runtime_aggregate import (
    build_runtime_aggregate_attestation,
    produce_runtime_aggregate,
    validate_runtime_aggregate_attestation,
    verify_runtime_aggregate_attestation,
    verify_runtime_aggregate_attestation_closure,
    verify_runtime_aggregate_presigning_content,
)
from ci.products.signatures import generate_development_key
from ci.tests.test_product_runtime_maven import runtime_maven_fixture
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
        # Actual KGP-shaped POM/GMM and complete checksums around explicitly
        # synthetic primaries; existing upstream verifier mocks remain unchanged.
        maven_records, maven_contents = runtime_maven_fixture(VERSION, "0.2.0")
        for record in maven_records:
            source = root / record["path"]
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(maven_contents[record["path"]])
            self.maven_inputs.append({
                **{key: record[key] for key in ("path", "role", "component")},
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
        for original in self.maven_inputs:
            destination = stage / "outputs" / original["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(original["file"]).read_bytes())
        write_output_manifest(
            stage, "runtime", "runtime-aggregate", "metadata", "aggregate", VERSION,
            {"runtime-aggregate": f"outputs/{manifest.name}", "maven": "outputs/maven"},
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
        ), patch.object(
            runtime_aggregate_module,
            "verify_runtime_aggregate_presigning_content",
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

    def test_runtime_maven_checksums_are_accepted_and_deterministic(self) -> None:
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
            checksums = [
                record for record in first["manifest"]["runtimeMavenFiles"]
                if record["role"] == "checksum"
            ]
            self.assertEqual(
                52 * len(CONTRACT_CHECKSUM_SUFFIXES),
                len(checksums),
            )
            self.assertEqual(260, len(first["manifest"]["runtimeMavenFiles"]))
            self.assertEqual(set(RUNTIME_MAVEN_COMPONENTS), {
                record["component"] for record in first["manifest"]["runtimeMavenFiles"]
            })
            for record in checksums:
                source = next(
                    value["file"] for value in fixture.maven_inputs
                    if value["path"] == record["path"]
                )
                self.assertEqual(sha256_file(source), record["sha256"])

    def test_exact_staged_maven_is_preserved_and_external_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            originals = {Path(record["file"]): Path(record["file"]).read_bytes() for record in fixture.maven_inputs}
            output = root / "staged"
            output.mkdir()
            rebound = []
            for record in fixture.maven_inputs:
                path = output / record["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(originals[Path(record["file"])])
                rebound.append({**record, "file": path})
            staged = {Path(record["file"]): Path(record["file"]).read_bytes() for record in rebound}
            # Equal external files do not authorize an already-populated output.
            with self.assertRaisesRegex(ValueError, "exact staged Maven inventory"):
                fixture.produce(output)
            self.assertEqual(staged, {path: path.read_bytes() for path in staged})
            fixture.maven_inputs = rebound
            result = fixture.produce(output)
            self.assertEqual(260, len(result["manifest"]["runtimeMavenFiles"]))
            self.assertEqual(staged, {path: path.read_bytes() for path in staged})
            self.assertEqual(originals, {path: path.read_bytes() for path in originals})
            before = result["manifestPath"].read_bytes()
            with self.assertRaisesRegex(ValueError, "must be empty"):
                fixture.produce(output)
            self.assertEqual(before, result["manifestPath"].read_bytes())

    def test_runtime_maven_checksum_is_owned_by_the_exact_publication_receipt(self) -> None:
        from ci.tests.test_product_runtime_integration import (
            RuntimeAggregateIntegrationTest,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            integration = RuntimeAggregateIntegrationTest()
            baseline = integration.fixture(root)
            self.assertEqual(baseline["aggregate"], integration.verify(baseline))

            for mode in ("moved", "duplicated"):
                fixture = copy.deepcopy(baseline)
                owner = fixture["aggregate_receipt"]
                sidecar_output = next(
                    value for value in owner["outputs"]
                    if value["kind"] == "maven" and value["relativePath"].startswith("outputs/maven/jvm/")
                    and value["relativePath"].endswith(".sha256")
                )
                wrong_owner = next(
                    receipt for receipt in fixture["adapter_receipt_values"]
                    if (receipt["component"], receipt["phase"], receipt["target"])
                    == ("node-js", "metadata", "node-js")
                )
                if mode == "moved":
                    owner["outputs"].remove(sidecar_output)
                wrong_owner["outputs"].append(copy.deepcopy(sidecar_output))
                wrong_owner["outputs"].sort(key=lambda value: value["relativePath"])
                upstream = next(
                    value for value in fixture["aggregate_receipt"]["inputs"]["upstreamArtifacts"]
                    if (value["component"], value["phase"], value["target"])
                    == (wrong_owner["component"], wrong_owner["phase"], wrong_owner["target"])
                )
                upstream["outputsDigest"] = output_inventory_digest(wrong_owner["outputs"])
                with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, "owned by exactly one",
                ):
                    integration.verify(fixture)

    def test_runtime_maven_sidecar_boundary_rejects_invalid_publications(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            primary = next(record for record in fixture.maven_inputs if record["role"] == "runtime-resolution")
            primary_bytes = Path(primary["file"]).read_bytes()
            sha256 = hashlib.sha256(primary_bytes).hexdigest().encode() + b"\n"
            files = root / "invalid-maven-inputs"
            files.mkdir()

            def record(label: str, path: str, role: str, component: str, contents: bytes) -> dict:
                source = files / label
                source.write_bytes(contents)
                return {
                    "path": path,
                    "role": role,
                    "component": component,
                    "file": source,
                }

            base = list(fixture.maven_inputs)
            sidecar_path = f"{primary['path']}.sha256"
            without_sidecar = [value for value in base if value["path"] != sidecar_path]
            cases = {
                "signature-role": (base + [record(
                    "signature-role", f"{primary['path']}.sig", "signature",
                    primary["component"], b"signature",
                )], "signatures and checksums"),
                "signature-laundering": (base + [record(
                    "signature-laundering", f"{primary['path']}.sig", "runtime-resolution",
                    primary["component"], b"signature",
                )], "signatures and checksums"),
                "asc": (base + [record(
                    "asc", f"{primary['path']}.asc", "runtime-resolution",
                    primary["component"], b"signature",
                )], "signatures and checksums"),
                "checksum-of-asc": (base + [record(
                    "checksum-of-asc", f"{primary['path']}.asc.sha256", "checksum",
                    primary["component"], sha256,
                )], "signatures and checksums"),
                "orphan": (base + [record(
                    "orphan", "maven/jvm/orphan.jar.sha256", "checksum",
                    primary["component"], sha256,
                )], "orphaned"),
                "wrong-component": (without_sidecar + [record(
                    "wrong-component", sidecar_path, "checksum", "linux-x64", sha256,
                )], "path does not match|component differs"),
                "wrong-content": (without_sidecar + [record(
                    "wrong-content", sidecar_path, "checksum",
                    primary["component"], b"0" * 64,
                )], "content is noncanonical"),
                "noncanonical-content": (without_sidecar + [record(
                    "noncanonical-content", sidecar_path, "checksum",
                    primary["component"], sha256.removesuffix(b"\n"),
                )], "content is noncanonical"),
                "duplicate": (base + [dict(primary)], "paths must be unique"),
                "unsupported-suffix": (base + [record(
                    "unsupported-suffix", f"{primary['path']}.sha384", "checksum",
                    primary["component"], hashlib.sha384(primary_bytes).hexdigest().encode(),
                )], "suffix is unsupported"),
                "sidecar-primary-role": (without_sidecar + [record(
                    "sidecar-primary-role", sidecar_path, "runtime-resolution",
                    primary["component"], sha256,
                )], "sidecar role is not canonical"),
                "publication-inventory": (base + [record(
                    "publication-inventory", "maven/jvm/publication-inventory.json",
                    "runtime-resolution", "jvm", b"{}\n",
                )], "publication inventories are forbidden"),
                "swapped-primary-component": ([
                    ({**value, "component": "linux-x64"} if value["path"] == primary["path"] else value)
                    for value in base
                ], "path does not match"),
                "incomplete-publication": (without_sidecar, "inventory is incomplete"),
            }
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
                side_effect=fixture.verify_variant,
            ):
                for label, (maven_inputs, message) in cases.items():
                    output = root / label
                    output.mkdir()
                    arguments = fixture.produce_arguments(output)
                    arguments["runtime_maven_files"] = maven_inputs
                    with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                        produce_runtime_aggregate(**arguments)

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
            missing_maven_receipt = root / "missing-maven.receipt.json"
            missing_maven = load_canonical_json_bytes(metadata.read_bytes())
            missing_maven["outputs"] = [record for record in missing_maven["outputs"]
                                       if record["kind"] != "maven"]
            write_canonical_json(missing_maven_receipt, missing_maven)
            bad_signature = root / signature.name
            bad_signature.write_bytes(signature.read_bytes() + b"tampered\n")
            _, wrong_public, _ = generate_development_key(root / "wrong-key")
            for replacement in (
                {"manifest": bad_manifest},
                {"metadata_receipt": bare_receipt},
                {"metadata_receipt": missing_maven_receipt},
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


class RuntimeAggregatePresigningContentTest(unittest.TestCase):
    """Full signed synthetic K/R inputs, not compiler or protected CI evidence."""

    @classmethod
    def setUpClass(cls):
        from ci.tests.test_product_native_chain import build_chain

        cls.temporary = tempfile.TemporaryDirectory(prefix="aggregate-presigning-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "original", 91)

    def inputs(self):
        chain = self.chain
        contract = chain["contract"]
        return {
            "contract_payload": contract["payload"], "contract_metadata_receipt": contract["receipt"],
            "contract_attestation": contract["attestation"], "contract_attestation_signature": contract["signature"],
            "contract_public_key": chain["context"]["public_key"],
            **{key: chain["variants"][key] for key in (
                "variant_bundles", "variant_phase_receipts", "variant_attestations",
                "variant_attestation_signatures", "variant_public_keys", "variant_validation_evidence",
            )},
            **{key: chain["adapters"][key] for key in (
                "adapter_receipts", "adapter_report_files", "runtime_maven_files", "adapter_evidence",
            )},
        }

    def presign(self, **changes):
        arguments = {"manifest": self.chain["aggregate"], "metadata_receipt": self.chain["aggregate_receipt"],
                     "required_trust_domain": "development", **self.inputs(), **changes}
        return verify_runtime_aggregate_presigning_content(**arguments)

    def signed(self):
        trust = self.chain["compatibility_args"]
        return verify_runtime_aggregate_artifacts(
            self.chain["aggregate"], aggregate_metadata_receipt=self.chain["aggregate_receipt"],
            aggregate_attestation=trust["runtime_attestation"],
            aggregate_attestation_signature=trust["runtime_attestation_signature"],
            aggregate_public_key=trust["runtime_public_key"], required_trust_domain="development", **self.inputs(),
        )

    def test_presign_matches_full_signed_gate_without_writing_any_original(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        with patch.object(runtime_aggregate_module, "sign_manifest", side_effect=AssertionError("pre-sign key access")):
            expected = self.signed()
            actual = self.presign()
        self.assertIs(type(actual), dict)
        self.assertEqual(expected, actual)
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_missing_aggregate_signature_never_grants_signed_admission(self):
        signature = self.chain["compatibility_args"]["runtime_attestation_signature"]
        hidden = signature.with_name(signature.name + ".hidden")
        signature.rename(hidden)
        try:
            with patch.object(runtime_aggregate_module, "verify_runtime_aggregate_attestation",
                              side_effect=AssertionError("pre-sign aggregate signature")), \
                    patch.object(runtime_aggregate_module, "sign_manifest", side_effect=AssertionError("signing")):
                self.assertIs(type(self.presign()), dict)
            with self.assertRaises((ValueError, OSError)):
                self.signed()
        finally:
            hidden.rename(signature)

    def test_full_contract_maven_report_projection_and_upstream_checks_run_before_signing(self):
        inputs = self.inputs()
        cases = {
            "contract-signature": inputs["contract_attestation_signature"],
            "variant-signature": inputs["variant_attestation_signatures"]["linux-x64"],
            "maven": Path(inputs["runtime_maven_files"][0]["file"]),
            "raw-report": inputs["adapter_report_files"]["jvm"]["linux-x64"],
            "projection": inputs["adapter_evidence"]["jvm"],
            "upstream": self.chain["aggregate_receipt"],
        }
        context = self.chain["context"]
        for name, path in cases.items():
            original, mode = path.read_bytes(), path.stat().st_mode
            destination = self.root / f"rejected-{name}"
            try:
                path.chmod(0o600)
                if name == "upstream":
                    receipt = load_canonical_json_bytes(original)
                    receipt["inputs"]["upstreamArtifacts"] = []
                    _rekey(receipt)
                    write_canonical_json(path, receipt)
                else:
                    path.write_bytes(original + b"invalid original\n")
                with self.subTest(name=name), \
                        patch.object(runtime_aggregate_module, "sign_manifest", side_effect=AssertionError("sign before full gate")), \
                        self.assertRaises((ValueError, OSError)):
                    build_runtime_aggregate_attestation(
                        self.chain["aggregate"], self.chain["aggregate_receipt"], **inputs,
                        signing_metadata=context["signing"], private_key=context["private_key"],
                        public_key=context["public_key"], output_directory=destination,
                        required_variant_trust_domain="development",
                    )
                self.assertFalse(destination.exists())
            finally:
                path.write_bytes(original)
                path.chmod(mode)


if __name__ == "__main__":
    unittest.main()
