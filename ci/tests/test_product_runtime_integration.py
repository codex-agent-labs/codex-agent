from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ci.products.aggregate as aggregate_module
import ci.products.runtime_aggregate as runtime_aggregate_module
from ci.products.aggregate import (
    RUNTIME_ADAPTERS,
    RUNTIME_EVIDENCE_TARGETS,
    RUNTIME_TARGETS,
    verify_runtime_aggregate_artifacts,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, output_inventory_digest
from ci.products.runtime_aggregate import build_runtime_aggregate_attestation
from ci.products.runtime_evidence import (
    derive_runtime_adapter_projection,
    jvm_evidence_filename,
    node_evidence_filename,
)
from ci.products.signatures import generate_development_key
from ci.tests.test_products import phase_receipt, runtime_aggregate
from ci.tests.test_product_runtime_maven import runtime_maven_fixture
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture


def _reference(receipt: dict) -> dict:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _output(kind: str, path: str, contents: bytes) -> dict:
    return {
        "kind": kind,
        "relativePath": path,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }


def _receipt(component: str, phase: str, target: str) -> dict:
    value = phase_receipt("development")
    value.update({
        "product": "runtime",
        "component": component,
        "phase": phase,
        "target": target,
        "productVersion": "0.2.7",
    })
    value["inputs"]["versionIdentity"] = "0.2.0"
    value["inputs"]["upstreamArtifacts"] = []
    value["outputs"] = []
    return value


class RuntimeAggregateIntegrationTest(unittest.TestCase):
    def fixture(self, root: Path) -> dict:
        evidence_fixture = RuntimeEvidenceFixture(root / "raw")
        raw_paths = {
            "jvm": evidence_fixture.write_jvm(),
            "node-js": evidence_fixture.write_node("js"),
            "node-wasm": evidence_fixture.write_node("wasm"),
        }
        report_files = {}
        projection_files = {}
        projections = {}
        for component in RUNTIME_ADAPTERS:
            reports_by_evidence_target = {
                load_canonical_json_bytes(path.read_bytes())["target"]: path
                for path in raw_paths[component]
            }
            report_files[component] = {
                target: reports_by_evidence_target[RUNTIME_EVIDENCE_TARGETS[target]]
                for target in RUNTIME_TARGETS
            }
            reports = [
                load_canonical_json_bytes(report_files[component][target].read_bytes())
                for target in RUNTIME_TARGETS
            ]
            projection = derive_runtime_adapter_projection(
                component, reports, evidence_fixture.commits,
            )
            path = root / f"{component}-projection.json"
            write_canonical_json(path, projection)
            projections[component] = projection
            projection_files[component] = path

        contract_receipt = phase_receipt("development")
        contract_receipt.update({
            "product": "contract", "component": "contract", "phase": "metadata",
            "target": "common", "productVersion": "0.2.0",
        })
        contract_receipt["inputs"]["versionIdentity"] = "0.2.0"
        contract_receipt["outputs"] = [_output(
            "contract-bundle",
            "outputs/codex-agent-contract-0.2.0.zip", b"contract",
        )]
        contract_receipt_path = root / "contract-receipt.json"
        write_canonical_json(contract_receipt_path, contract_receipt)
        contract_digest = sha256_bytes(b"contract-digest")
        contract = {
            "contractVersion": "0.2.0",
            "contractDigest": contract_digest,
            "components": {
                component: {"sha256": sha256_bytes(component.encode())}
                for component in (*RUNTIME_TARGETS, *RUNTIME_ADAPTERS)
            },
        }
        contract_attestation = {
            "payload": {
                "fileName": "codex-agent-contract-0.2.0.zip",
                "sha256": contract_receipt["outputs"][0]["sha256"],
            },
            "manifestSha256": sha256_bytes(b"contract-manifest"),
        }

        variant_receipts = {
            target: {
                phase: _receipt(target, phase, target)
                for phase in ("binary", "package", "validation", "metadata")
            }
            for target in RUNTIME_TARGETS
        }
        adapter_receipt_values = []
        receipt_map = {}
        for component in RUNTIME_ADAPTERS:
            identities = [
                *((phase, component) for phase in ("binary", "package", "metadata")),
                *(("validation", target) for target in RUNTIME_TARGETS),
            ]
            if component == "node-js":
                identities.append(("validation", "node-js-binding"))
            for phase, target in identities:
                receipt = _receipt(component, phase, target)
                receipt_map[(component, phase, target)] = receipt
                adapter_receipt_values.append(receipt)

        original_primaries = {}
        for component in (*RUNTIME_TARGETS, *RUNTIME_ADAPTERS):
            main = "main.jar" if component == "jvm" else "main.klib"
            contents = {
                main: f"synthetic {component} Runtime publication\n".encode(),
                "sources.jar": f"synthetic {component} sources publication\n".encode(),
                "javadoc.jar": f"synthetic {component} documentation publication\n".encode(),
            }
            if component in RUNTIME_TARGETS:
                contents.update({
                    "cinterop-codexDesktop.klib":
                        f"synthetic {component} desktop cinterop\n".encode(),
                    "cinterop-codexAgentC.klib":
                        f"synthetic {component} C ABI cinterop\n".encode(),
                })
                if component in {"macos-arm64", "macos-x64"}:
                    contents["metadata.jar"] = (
                        f"synthetic {component} metadata publication\n".encode()
                    )
                owner_phases = (variant_receipts[component]["binary"],)
            else:
                owner_phases = (
                    receipt_map[(component, "binary", component)],
                    receipt_map[(component, "package", component)],
                )
            original_primaries[component] = contents
            for owner in owner_phases:
                owner["outputs"].extend(
                    _output("publication", f"outputs/publication/{name}", value)
                    for name, value in contents.items()
                )
                owner["outputs"].sort(key=lambda value: value["relativePath"])

        maven_records, maven_contents = runtime_maven_fixture(
            runtime_aggregate()["runtimeVersion"], "0.2.0", original_primaries=original_primaries,
        )
        maven_files = []
        for record in maven_records:
            source = root / "aggregate" / record["path"]
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(maven_contents[record["path"]])
            maven_files.append({
                "path": record["path"], "role": record["role"],
                "component": record["component"], "file": source,
            })

        contract_bytes = contract_receipt_path.read_bytes()
        for component in RUNTIME_ADAPTERS:
            binary = receipt_map[(component, "binary", component)]
            package = receipt_map[(component, "package", component)]
            metadata = receipt_map[(component, "metadata", component)]
            binary["inputs"]["upstreamArtifacts"] = [{
                **_reference(contract_receipt),
                "contractProjection": {
                    "schemaVersion": 1,
                    "receiptSha256": sha256_bytes(contract_bytes),
                    "bundlePath": "outputs/codex-agent-contract-0.2.0.zip",
                    "bundleSha256": contract_attestation["payload"]["sha256"],
                    "manifestSha256": contract_attestation["manifestSha256"],
                    "contractVersion": "0.2.0",
                    "contractDigest": contract_digest,
                    "componentDigests": [{
                        "component": component,
                        "sha256": contract["components"][component]["sha256"],
                    }],
                },
            }]
            package["inputs"]["upstreamArtifacts"] = [_reference(binary)]
            semantic = sha256_bytes(canonical_json_bytes(projections[component]))
            metadata_upstreams = []
            for target in RUNTIME_TARGETS:
                validation = receipt_map[(component, "validation", target)]
                validation["producer"]["commit"] = evidence_fixture.commits[
                    RUNTIME_EVIDENCE_TARGETS[target]
                ]
                validation["inputs"]["upstreamArtifacts"] = sorted(
                    [_reference(package), _reference(variant_receipts[target]["package"])],
                    key=lambda value: (
                        value["product"], value["component"], value["phase"],
                        value["target"], value["buildKey"],
                    ),
                )
                report_bytes = report_files[component][target].read_bytes()
                evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
                if component == "jvm":
                    filename = jvm_evidence_filename(evidence_target)
                    kind = "jvm-evidence"
                    path = f"outputs/jvm-evidence/{filename}"
                else:
                    backend = "js" if component == "node-js" else "wasm"
                    filename = node_evidence_filename(evidence_target, backend)
                    kind = "node-evidence"
                    path = f"outputs/node-evidence/{filename}"
                validation["outputs"] = [_output(kind, path, report_bytes)]
                upstream = _reference(validation)
                upstream["semanticProjection"] = {
                    "schemaVersion": 1,
                    "kind": "runtime-validation-content",
                    "sha256": semantic,
                }
                metadata_upstreams.append(upstream)
            if component == "node-js":
                binding = receipt_map[(component, "validation", "node-js-binding")]
                binding["inputs"]["upstreamArtifacts"] = [_reference(package)]
                metadata_upstreams.append(_reference(binding))
            metadata["inputs"]["upstreamArtifacts"] = sorted(
                metadata_upstreams,
                key=lambda value: (
                    value["product"], value["component"], value["phase"],
                    value["target"], value["buildKey"],
                ),
            )
            projection_bytes = projection_files[component].read_bytes()
            metadata["outputs"].append(_output(
                "adapter-evidence",
                f"outputs/evidence/{component}.json", projection_bytes,
            ))

        for receipt in adapter_receipt_values:
            receipt["outputs"].sort(key=lambda output: output["relativePath"])

        aggregate = runtime_aggregate()
        aggregate["contract"] = {"version": "0.2.0", "digest": contract_digest}
        aggregate["runtimeMavenFiles"] = sorted(({
            "path": value["path"],
            "role": value["role"],
            "component": value["component"],
            "bytes": Path(value["file"]).stat().st_size,
            "sha256": sha256_bytes(Path(value["file"]).read_bytes()),
        } for value in maven_files), key=lambda value: value["path"])
        aggregate["adapterEvidence"] = sorted(({
            "path": f"evidence/{component}.json",
            "role": "adapter",
            "target": component,
            "bytes": projection_files[component].stat().st_size,
            "sha256": sha256_bytes(projection_files[component].read_bytes()),
        } for component in RUNTIME_ADAPTERS), key=lambda value: value["path"])
        aggregate_receipt = _receipt("runtime-aggregate", "metadata", "aggregate")
        aggregate_receipt["productVersion"] = aggregate["runtimeVersion"]
        aggregate_receipt["inputs"]["versionIdentity"] = aggregate["runtimeVersion"]
        aggregate_receipt["inputs"]["upstreamArtifacts"] = sorted([
            *(_reference(variant_receipts[target]["metadata"]) for target in RUNTIME_TARGETS),
            *(_reference(receipt_map[(component, "metadata", component)])
              for component in RUNTIME_ADAPTERS),
        ], key=lambda value: (
            value["product"], value["component"], value["phase"],
            value["target"], value["buildKey"],
        ))
        aggregate_receipt["outputs"] = [_output(
            "runtime-aggregate",
            f"outputs/codex-agent-runtime-{aggregate['runtimeVersion']}-manifest.json",
            canonical_json_bytes(aggregate),
        ), *(
            _output("maven", f"outputs/{record['path']}", maven_contents[record["path"]])
            for record in maven_records
        )]
        aggregate_receipt["outputs"].sort(key=lambda value: value["relativePath"])
        return {
            "aggregate": aggregate,
            "aggregate_receipt": aggregate_receipt,
            "contract": contract,
            "contract_receipt": contract_receipt,
            "contract_attestation": contract_attestation,
            "contract_receipt_path": contract_receipt_path,
            "variant_manifests": {
                target: {"contract": {"digest": contract_digest}}
                for target in RUNTIME_TARGETS
            },
            "variant_receipts": variant_receipts,
            "adapter_receipt_values": adapter_receipt_values,
            "maven_files": maven_files,
            "projection_files": projection_files,
            "report_files": report_files,
        }

    def verify(self, fixture: dict) -> dict:
        with patch.object(
            aggregate_module, "verify_contract_attestation",
            return_value=(fixture["contract"], fixture["contract_receipt"],
                          fixture["contract_attestation"]),
        ), patch.object(
            runtime_aggregate_module, "verify_runtime_aggregate_attestation",
            return_value=(fixture["aggregate"], fixture["aggregate_receipt"], {}),
        ), patch.object(
            runtime_aggregate_module, "verify_runtime_aggregate_attestation_closure",
            return_value=(fixture["variant_manifests"], fixture["variant_receipts"],
                          fixture["adapter_receipt_values"]),
        ):
            return verify_runtime_aggregate_artifacts(
                Path("aggregate.json"),
                aggregate_metadata_receipt=Path("aggregate-receipt.json"),
                aggregate_attestation=Path("aggregate-attestation.json"),
                aggregate_attestation_signature=Path("aggregate-attestation.sig"),
                aggregate_public_key=Path("aggregate.pub"),
                contract_payload=Path("contract.zip"),
                contract_metadata_receipt=fixture["contract_receipt_path"],
                contract_attestation=Path("contract-attestation.json"),
                contract_attestation_signature=Path("contract-attestation.sig"),
                contract_public_key=Path("contract.pub"),
                variant_bundles={},
                variant_phase_receipts={},
                variant_attestations={},
                variant_attestation_signatures={},
                variant_public_keys={},
                variant_validation_evidence={},
                adapter_receipts=[],
                adapter_report_files=fixture["report_files"],
                runtime_maven_files=fixture["maven_files"],
                adapter_evidence=fixture["projection_files"],
                required_trust_domain="development",
            )

    def build_attestation(self, root: Path, fixture: dict, output: Path) -> dict:
        manifest = root / f"codex-agent-runtime-{fixture['aggregate']['runtimeVersion']}-manifest.json"
        write_canonical_json(manifest, fixture["aggregate"])
        receipt = fixture["aggregate_receipt"]
        receipt["outputs"] = [
            *(value for value in receipt["outputs"] if value["kind"] == "maven"),
            _output("runtime-aggregate", f"outputs/{manifest.name}", manifest.read_bytes()),
        ]
        receipt["outputs"].sort(key=lambda value: value["relativePath"])
        receipt["buildKey"] = compute_build_key(
            product=receipt["product"], component=receipt["component"],
            phase=receipt["phase"], target=receipt["target"], inputs=receipt["inputs"],
        )
        receipt_path = root / "runtime-aggregate-receipt.json"
        write_canonical_json(receipt_path, receipt)
        private_key, public_key, signing = generate_development_key(root / "aggregate-key")
        variant_records = [{
            **record,
            "variantAttestationSha256": sha256_bytes(
                f"attestation-{record['target']}".encode(),
            ),
            "phaseReceipts": {
                phase: sha256_bytes(f"{record['target']}-{phase}".encode())
                for phase in ("binary", "package", "validation", "metadata")
            },
        } for record in fixture["aggregate"]["variants"]]
        adapter_records = sorted([{
            "component": receipt_value["component"],
            "phase": receipt_value["phase"],
            "target": receipt_value["target"],
            "receiptSha256": sha256_bytes(
                f"{receipt_value['component']}-{receipt_value['phase']}-"
                f"{receipt_value['target']}".encode(),
            ),
        } for receipt_value in fixture["adapter_receipt_values"]], key=lambda value: (
            value["component"], value["phase"], value["target"],
        ))
        with patch.object(
            runtime_aggregate_module, "_variant_inputs",
            return_value=(fixture["aggregate"]["variants"], variant_records, {}, {}),
        ), patch.object(
            runtime_aggregate_module, "_adapter_receipt_closure",
            return_value=(adapter_records, fixture["adapter_receipt_values"]),
        ), patch.object(
            aggregate_module, "verify_contract_attestation",
            return_value=(fixture["contract"], fixture["contract_receipt"],
                          fixture["contract_attestation"]),
        ), patch.object(
            runtime_aggregate_module, "verify_runtime_aggregate_attestation_closure",
            return_value=(fixture["variant_manifests"], fixture["variant_receipts"],
                          fixture["adapter_receipt_values"]),
        ):
            return build_runtime_aggregate_attestation(
                manifest, receipt_path, {}, {}, {}, {}, {}, {}, [], signing,
                private_key, public_key, output,
                required_variant_trust_domain="development",
                contract_payload=root / "contract.zip",
                contract_metadata_receipt=fixture["contract_receipt_path"],
                contract_attestation=root / "contract-attestation.json",
                contract_attestation_signature=root / "contract-attestation.sig",
                contract_public_key=public_key,
                adapter_report_files=fixture["report_files"],
                runtime_maven_files=fixture["maven_files"],
                adapter_evidence=fixture["projection_files"],
            )

    def test_composes_external_trust_with_exact_receipt_owned_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(Path(temporary).resolve())
            self.assertEqual(fixture["aggregate"], self.verify(fixture))

            def refresh_reference(parent: dict, receipt: dict) -> None:
                reference = next(
                    candidate for candidate in parent["inputs"]["upstreamArtifacts"]
                    if all(candidate[field] == receipt[field]
                           for field in ("product", "component", "phase", "target", "buildKey"))
                )
                reference["outputsDigest"] = output_inventory_digest(receipt["outputs"])

            missing_owner = copy.deepcopy(fixture)
            missing_owner["adapter_receipt_values"] = copy.deepcopy(
                fixture["adapter_receipt_values"],
            )
            receipt = next(
                value for value in missing_owner["adapter_receipt_values"]
                if (value["component"], value["phase"], value["target"])
                == ("jvm", "metadata", "jvm")
            )
            receipt["outputs"] = [
                output for output in receipt["outputs"]
                if output["relativePath"] != "outputs/evidence/jvm.json"
            ]
            next(
                upstream for upstream in missing_owner["aggregate_receipt"]
                ["inputs"]["upstreamArtifacts"]
                if (upstream["component"], upstream["phase"], upstream["target"])
                == ("jvm", "metadata", "jvm")
            )["outputsDigest"] = output_inventory_digest(receipt["outputs"])
            with self.assertRaisesRegex(ValueError, "owned by exactly one"):
                self.verify(missing_owner)

            wrong_projection = copy.deepcopy(fixture)
            receipt = next(
                value for value in wrong_projection["adapter_receipt_values"]
                if (value["component"], value["phase"], value["target"])
                == ("jvm", "metadata", "jvm")
            )
            receipt["inputs"]["upstreamArtifacts"][0]["semanticProjection"]["sha256"] = \
                sha256_bytes(b"wrong")
            with self.assertRaisesRegex(ValueError, "metadata receipt predecessor"):
                self.verify(wrong_projection)

            for field, value in (
                ("kind", "wrong"),
                ("relativePath", "outputs/evidence/wrong.json"),
            ):
                wrong_owner = copy.deepcopy(fixture)
                receipt = next(
                    candidate for candidate in wrong_owner["adapter_receipt_values"]
                    if (candidate["component"], candidate["phase"], candidate["target"])
                    == ("jvm", "metadata", "jvm")
                )
                output = next(
                    candidate for candidate in receipt["outputs"]
                    if candidate["relativePath"] == "outputs/evidence/jvm.json"
                )
                output[field] = value
                refresh_reference(wrong_owner["aggregate_receipt"], receipt)
                with self.subTest(owner_field=field), self.assertRaisesRegex(
                    ValueError, "owned by exactly one",
                ):
                    self.verify(wrong_owner)

            wrong_raw_kind = copy.deepcopy(fixture)
            receipt = next(
                candidate for candidate in wrong_raw_kind["adapter_receipt_values"]
                if (candidate["component"], candidate["phase"], candidate["target"])
                == ("node-js", "validation", "macos-arm64")
            )
            receipt["outputs"][0]["kind"] = "wrong"
            metadata = next(
                candidate for candidate in wrong_raw_kind["adapter_receipt_values"]
                if (candidate["component"], candidate["phase"], candidate["target"])
                == ("node-js", "metadata", "node-js")
            )
            refresh_reference(metadata, receipt)
            with self.assertRaisesRegex(ValueError, "not one exact validation output"):
                self.verify(wrong_raw_kind)

            wrong_maven_path = copy.deepcopy(fixture)
            receipt = wrong_maven_path["aggregate_receipt"]
            output = next(
                candidate for candidate in receipt["outputs"]
                if candidate["kind"] == "maven"
            )
            output["relativePath"] += ".wrong"
            receipt["outputs"].sort(key=lambda value: value["relativePath"])
            with self.assertRaisesRegex(ValueError, "owned by exactly one"):
                self.verify(wrong_maven_path)

    def test_adapter_maven_primary_requires_both_original_publication_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(Path(temporary).resolve())
            self.assertEqual(fixture["aggregate"], self.verify(fixture))
            for component in RUNTIME_ADAPTERS:
                primary = "main.jar" if component == "jvm" else "main.klib"
                relative = f"outputs/publication/{primary}"
                for phase in ("binary", "package"):
                    for mutation in ("missing", "mismatch"):
                        changed = copy.deepcopy(fixture)
                        receipt = next(
                            value for value in changed["adapter_receipt_values"]
                            if (value["component"], value["phase"], value["target"])
                            == (component, phase, component)
                        )
                        publication = next(
                            value for value in receipt["outputs"]
                            if value["relativePath"] == relative
                        )
                        if mutation == "missing":
                            receipt["outputs"].remove(publication)
                        else:
                            publication["sha256"] = sha256_bytes(b"different original publication")
                        with self.subTest(component=component, phase=phase, mutation=mutation), \
                                self.assertRaisesRegex(
                                    ValueError,
                                    f"Runtime {component} Maven runtime-resolution differs from "
                                    f"its original {phase} publication",
                                ):
                            self.verify(changed)

            for component in RUNTIME_TARGETS:
                for mutation in ("missing", "mismatch"):
                    changed = copy.deepcopy(fixture)
                    receipt = changed["variant_receipts"][component]["binary"]
                    publication = next(
                        value for value in receipt["outputs"]
                        if value["relativePath"] == "outputs/publication/main.klib"
                    )
                    if mutation == "missing":
                        receipt["outputs"].remove(publication)
                    else:
                        publication["sha256"] = sha256_bytes(
                            b"different original native publication",
                        )
                    with self.subTest(component=component, phase="binary", mutation=mutation), \
                            self.assertRaisesRegex(
                                ValueError,
                                f"Runtime {component} Maven runtime-resolution differs from "
                                "its original binary publication",
                            ):
                        self.verify(changed)

    def test_attestation_builder_rejects_unverified_aggregate_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = self.fixture(root)
            output = root / "attestation"
            value = self.build_attestation(root, fixture, output)
            self.assertEqual(fixture["aggregate"]["runtimeVersion"], value["runtimeVersion"])
            self.assertTrue(output.is_dir())

        mutations = ("projection", "maven", "predecessor")
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                fixture = self.fixture(root)
                if mutation == "projection":
                    path = fixture["projection_files"]["jvm"]
                    write_canonical_json(path, {"forged": True})
                    record = next(
                        value for value in fixture["aggregate"]["adapterEvidence"]
                        if value["target"] == "jvm"
                    )
                    record["bytes"] = path.stat().st_size
                    record["sha256"] = sha256_bytes(path.read_bytes())
                    expected = "differs from its raw reports"
                elif mutation == "maven":
                    source = Path(fixture["maven_files"][0]["file"])
                    source.write_bytes(b"forged Maven bytes\n")
                    record = next(
                        value for value in fixture["aggregate"]["runtimeMavenFiles"]
                        if value["path"] == fixture["maven_files"][0]["path"]
                    )
                    record["bytes"] = source.stat().st_size
                    record["sha256"] = sha256_bytes(source.read_bytes())
                    expected = "metadata receipt does not bind the exact payload"
                else:
                    fixture["aggregate_receipt"]["inputs"]["upstreamArtifacts"].pop()
                    expected = "predecessor closure mismatch"
                output = root / "attestation"
                with self.assertRaisesRegex(ValueError, expected):
                    self.build_attestation(root, fixture, output)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
