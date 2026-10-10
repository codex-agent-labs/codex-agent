"""Real artifact/trust producers over synthetic inputs; not hosted execution proof."""

from pathlib import Path
import os
import shutil
import tempfile
import unittest
import zipfile

from ci.products.contract import verify_contract_bundle
from ci.products.c_abi import C_ABI_PACKAGE_MANIFEST
from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import load_canonical_json_bytes, sha256_file
from ci.products.runtime_aggregate import produce_runtime_aggregate, build_runtime_aggregate_attestation
from ci.products.sdk_compatibility import produce_sdk_compatibility
from ci.products.signatures import generate_development_key
from ci.products.registry import PhaseInstanceId
from ci.products.receipt import write_output_manifest
from ci.tests.product_chain_support import output, reference, write_receipt
from ci.tests.product_chain_variants import build_variants
from ci.tests.product_chain_adapters import build_adapters
from ci.tests.test_contract_execution_closure import execution_closure_fixture
from ci.tests.test_product_runtime_maven import runtime_maven_fixture


def _stage_runtime_maven_publications(
    stage: Path, variants: dict, adapters: dict,
) -> list[dict]:
    original_primaries = {
        **{
            component: {name: path.read_bytes() for name, path in paths.items()}
            for component, paths in variants["publication_primaries"].items()
        },
        **{
            component: {name: path.read_bytes() for name, path in paths.items()}
            for component, paths in adapters["publication_primaries"].items()
        },
    }
    records, contents = runtime_maven_fixture(
        "0.2.7", "0.2.0", original_primaries=original_primaries,
    )
    files = []
    for record in records:
        destination = stage / "outputs" / record["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents[record["path"]])
        files.append({
            "path": record["path"],
            "role": record["role"],
            "component": record["component"],
            "file": destination,
        })
    return files


def build_chain(root: Path, run: int, *, variants: dict | None = None, include_bootstrap: bool = False,
                context: dict | None = None) -> dict:
    root.mkdir()
    if context is None:
        private_key, public_key, signing = generate_development_key(root / "keys")
        context = {
            "private_key": private_key, "public_key": public_key, "signing": signing,
            "producer": {
                "repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/product-validation.yml",
                "commit": f"{run:040x}", "tree": f"{run + 100:040x}",
                "event": "pull_request", "runId": run, "runAttempt": 1, "pullRequest": 31,
            },
        }
    private_key, public_key, signing = (context[key] for key in ("private_key", "public_key", "signing"))
    payload, receipts, execution_archive = execution_closure_fixture(
        root / "contract-source", context=f"producer-run-{run}", producer=context["producer"],
        **({"plan_factory": context["plan_factory"]} if "plan_factory" in context else {}),
    )
    if "plan_factory" in context:
        for phase, path in receipts.items():
            instance = PhaseInstanceId("contract", "contract", phase, "common")
            context["planned_receipts"][instance] = load_canonical_json_bytes(path.read_bytes())
            context["receipt_paths"][instance] = path
            context["phase_stages"][instance] = root / "contract-source" / f"{phase}-stage"
    manifest = verify_contract_bundle(payload)
    receipt = receipts["metadata"]
    execution_closure = root / "contract-execution-closure"
    capture_contract_execution_closure(payload, receipts, execution_archive, execution_closure)
    trust = root / "contract-trust"
    build_contract_attestation(
        payload, receipt, signing, private_key, public_key, trust,
        execution_closure=execution_closure,
    )
    contract = {
        "payload": payload, "manifest": manifest, "receipt": receipt,
        "attestation": trust / "codex-agent-contract-0.2.0.attestation.json",
        "signature": trust / "codex-agent-contract-0.2.0.attestation.sig",
        "execution_closure": trust / "execution-closure",
    }
    if "plan_factory" in context:
        context["contract"] = contract
    if variants is None:
        variants = build_variants(root / "variants", contract, context, include_bootstrap=include_bootstrap)
    adapters = build_adapters(root / "adapters", contract, variants, context)
    aggregate_stage = root / "aggregate-stage"
    runtime_maven_files = _stage_runtime_maven_publications(
        aggregate_stage, variants, adapters,
    )
    # Existing consumers use this key for the exact aggregate inputs. It no
    # longer denotes adapter-owned Maven outputs.
    adapters["runtime_maven_files"] = runtime_maven_files
    contract_args = {
        "contract_payload": payload, "contract_metadata_receipt": receipt,
        "contract_attestation": contract["attestation"],
        "contract_attestation_signature": contract["signature"], "contract_public_key": public_key,
    }
    variant_args = {key: variants[key] for key in (
        "variant_bundles", "variant_phase_receipts", "variant_attestations",
        "variant_attestation_signatures", "variant_public_keys", "variant_validation_evidence",
    )}
    aggregate_args = {
        **contract_args, **variant_args,
        "runtime_maven_files": runtime_maven_files,
        "adapter_evidence": adapters["adapter_evidence"],
    }
    aggregate = produce_runtime_aggregate(
        runtime_version="0.2.7", required_trust_domain="development",
        output_directory=aggregate_stage / "outputs", **aggregate_args,
    )
    aggregate_path = aggregate["manifestPath"]
    aggregate_receipt = root / "aggregate-receipt.json"
    aggregate_outputs = write_output_manifest(
        aggregate_stage, "runtime", "runtime-aggregate", "metadata", "aggregate", "0.2.7",
        {"runtime-aggregate": f"outputs/{aggregate_path.name}", "maven": "outputs/maven"},
    )["outputs"]
    if "plan_factory" in context:
        context["phase_stages"][PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")] = aggregate_stage
    metadata_receipts = [values["metadata"] for values in variants["variant_phase_receipts"].values()]
    metadata_receipts.extend(
        record["receipt"] for record in adapters["adapter_receipts"] if record["phase"] == "metadata"
    )
    write_receipt(
        aggregate_receipt, component="runtime-aggregate", phase="metadata", target="aggregate",
        version_identity="0.2.7", context=context,
        upstream=[reference(load_canonical_json_bytes(path.read_bytes())) for path in metadata_receipts],
        outputs=aggregate_outputs,
    )
    aggregate_trust = root / "aggregate-trust"
    build_runtime_aggregate_attestation(
        aggregate_path, aggregate_receipt, **aggregate_args,
        adapter_receipts=adapters["adapter_receipts"],
        adapter_report_files=adapters["adapter_report_files"],
        signing_metadata=signing, private_key=private_key, public_key=public_key,
        output_directory=aggregate_trust, required_variant_trust_domain="development",
    )
    compatibility_args = {
        **contract_args,
        **{key: value for key, value in variant_args.items() if key != "variant_validation_evidence"},
        "sdk_version": "0.2.9", "compatible_release_range": ">=0.2.0 <0.3.0",
        "compatible_runtime_compatibility_range": ">=0.2.0 <0.3.0",
        "runtime_manifest": aggregate_path, "runtime_metadata_receipt": aggregate_receipt,
        "runtime_attestation": aggregate_trust / "codex-agent-runtime-0.2.7.attestation.json",
        "runtime_attestation_signature": aggregate_trust / "codex-agent-runtime-0.2.7.attestation.sig",
        "runtime_public_key": public_key, "required_trust_domain": "development",
        "runtime_stage_root": variants["stages"],
    }
    compatibility = root / "sdk-compatibility.json"
    produce_sdk_compatibility(output=compatibility, **compatibility_args)
    return {
        "root": root, "context": context, "contract": contract, "variants": variants,
        "adapters": adapters,
        "aggregate": aggregate_path, "aggregate_receipt": aggregate_receipt,
        "compatibility": compatibility, "compatibility_args": compatibility_args,
    }


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ProductNativeChainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="s808-synthetic-chain-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.left = build_chain(cls.root / "left", 11)
        cls.right = build_chain(cls.root / "right", 22)

    def test_payloads_equal_across_producers_and_signing_keys(self) -> None:
        left, right = self.left, self.right
        pairs = [(left["contract"]["payload"], right["contract"]["payload"])]
        pairs.extend((left[key], right[key]) for key in ("aggregate", "compatibility"))
        for target, payload in left["variants"]["variant_bundles"].items():
            other = right["variants"]["variant_bundles"][target]
            pairs.append((payload, other))
            with zipfile.ZipFile(payload) as first, zipfile.ZipFile(other) as second:
                inner = [name for name in first.namelist() if name.startswith("c-abi/")]
                self.assertEqual(len(inner), 1)
                self.assertEqual(first.read(inner[0]), second.read(inner[0]))
            for phase, receipt in left["variants"]["variant_phase_receipts"][target].items():
                self.assertNotEqual(receipt.read_bytes(), right["variants"]["variant_phase_receipts"][target][phase].read_bytes())
                self.assertEqual(
                    load_canonical_json_bytes(receipt.read_bytes())["buildKey"],
                    load_canonical_json_bytes(right["variants"]["variant_phase_receipts"][target][phase].read_bytes())["buildKey"],
                )
            for key in ("variant_attestations", "variant_attestation_signatures"):
                self.assertNotEqual(left["variants"][key][target].read_bytes(), right["variants"][key][target].read_bytes())
            raw = left["variants"]["raw_sdks"][target]
            self.assertNotEqual(raw["evidence"].read_bytes(), right["variants"]["raw_sdks"][target]["evidence"].read_bytes())
            with zipfile.ZipFile(raw["archive"]) as archive:
                manifests = [name for name in archive.namelist() if name == C_ABI_PACKAGE_MANIFEST]
                self.assertEqual(len(manifests), 1)
                manifest = load_canonical_json_bytes(archive.read(manifests[0]))
                self.assertEqual(manifest["schemaVersion"], 2)
                self.assertNotIn("producerCommit", manifest)
                self.assertNotIn("producerTree", manifest)
        for first, second in pairs:
            with self.subTest(payload=first.name):
                self.assertEqual(first.read_bytes(), second.read_bytes())
        for key in ("receipt", "attestation", "signature"):
            self.assertNotEqual(left["contract"][key].read_bytes(), right["contract"][key].read_bytes())
        for path in ("contract-execution-closure.json", "execution/contract-execution.zip",
                     *(f"receipts/{phase}.json" for phase in ("binary", "package", "validation", "metadata"))):
            self.assertNotEqual(
                (left["contract"]["execution_closure"] / path).read_bytes(),
                (right["contract"]["execution_closure"] / path).read_bytes(),
            )
        self.assertNotEqual(left["context"]["public_key"].read_bytes(), right["context"]["public_key"].read_bytes())
        for key in ("runtime_attestation", "runtime_attestation_signature"):
            self.assertNotEqual(left["compatibility_args"][key].read_bytes(), right["compatibility_args"][key].read_bytes())
        for component, reports in left["adapters"]["adapter_report_files"].items():
            self.assertEqual(left["adapters"]["adapter_evidence"][component].read_bytes(), right["adapters"]["adapter_evidence"][component].read_bytes())
            for target, report in reports.items():
                self.assertNotEqual(report.read_bytes(), right["adapters"]["adapter_report_files"][component][target].read_bytes())

    def test_original_publications_and_final_maven_have_exact_receipt_owners(self) -> None:
        chain = self.left
        for target, receipts in chain["variants"]["receipts"].items():
            binary = receipts["binary"]
            package = receipts["package"]
            names = {
                Path(record["relativePath"]).name
                for record in binary["outputs"] if record["kind"] == "publication"
            }
            expected = {
                "main.klib", "sources.jar", "javadoc.jar",
                "cinterop-codexDesktop.klib", "cinterop-codexAgentC.klib",
            }
            if target in {"macos-arm64", "macos-x64"}:
                expected.add("metadata.jar")
            self.assertEqual(expected, names)
            self.assertFalse(any(record["kind"] == "maven" for record in package["outputs"]))

        adapter_receipts = {
            (record["component"], record["phase"], record["target"]):
                load_canonical_json_bytes(record["receipt"].read_bytes())
            for record in chain["adapters"]["adapter_receipts"]
        }
        for component in ("jvm", "node-js", "node-wasm"):
            expected = {"main.jar" if component == "jvm" else "main.klib",
                        "sources.jar", "javadoc.jar"}
            phase_outputs = []
            for phase in ("binary", "package"):
                outputs = adapter_receipts[(component, phase, component)]["outputs"]
                phase_outputs.append([
                    record for record in outputs if record["kind"] == "publication"
                ])
                self.assertEqual(expected, {
                    Path(record["relativePath"]).name for record in phase_outputs[-1]
                })
            self.assertEqual(phase_outputs[0], phase_outputs[1])
            self.assertEqual(
                {"adapter-evidence"},
                {record["kind"] for record in adapter_receipts[(component, "metadata", component)]["outputs"]},
            )

        aggregate_receipt = load_canonical_json_bytes(chain["aggregate_receipt"].read_bytes())
        aggregate_manifest = load_canonical_json_bytes(chain["aggregate"].read_bytes())
        maven_outputs = [
            record for record in aggregate_receipt["outputs"] if record["kind"] == "maven"
        ]
        self.assertEqual(260, len(maven_outputs))
        maven_inputs = {
            record["path"]: record for record in chain["adapters"]["runtime_maven_files"]
        }
        self.assertEqual(aggregate_manifest["runtimeMavenFiles"], [{
            "path": record["relativePath"].removeprefix("outputs/"),
            "role": maven_inputs[record["relativePath"].removeprefix("outputs/")]["role"],
            "component": maven_inputs[record["relativePath"].removeprefix("outputs/")]["component"],
            "bytes": record["bytes"],
            "sha256": record["sha256"],
        } for record in maven_outputs])
        self.assertEqual(
            [f"outputs/{chain['aggregate'].name}"],
            [record["relativePath"] for record in aggregate_receipt["outputs"]
             if record["kind"] == "runtime-aggregate"],
        )

    def test_mixed_original_producers_keep_content_and_original_receipts(self) -> None:
        sources = {
            target: (self.left, self.right)[index % 2]["variants"]
            for index, target in enumerate(sorted(self.left["variants"]["variant_bundles"]))
        }
        mixed = {
            key: {target: source[key][target] for target, source in sources.items()}
            for key in self.left["variants"] if key != "stages"
        }
        mixed["stages"] = self.root / "mixed-stages"
        for target, source in sources.items():
            shutil.copytree(source["stages"] / target, mixed["stages"] / target)
        original_receipts = {
            path: path.read_bytes() for phases in mixed["variant_phase_receipts"].values()
            for path in phases.values()
        }
        chain = build_chain(self.root / "mixed", 33, variants=mixed)
        for key in ("aggregate", "compatibility"):
            self.assertEqual(chain[key].read_bytes(), self.left[key].read_bytes())
        for path, contents in original_receipts.items():
            self.assertEqual(path.read_bytes(), contents)

    def test_authenticated_inputs_cannot_be_cross_paired(self) -> None:
        for key in ("contract_metadata_receipt", "contract_attestation_signature",
                    "runtime_metadata_receipt", "runtime_attestation_signature", "variant_phase_receipts",
                    "variant_attestations", "variant_attestation_signatures", "variant_public_keys"):
            destination = self.root / f"rejected-{key}" / "sdk-compatibility.json"
            destination.parent.mkdir()
            with self.subTest(input=key), self.assertRaises(ValueError):
                produce_sdk_compatibility(
                    output=destination,
                    **{**self.left["compatibility_args"], key: self.right["compatibility_args"][key]},
                )
            self.assertFalse(destination.exists())

    @unittest.skipUnless(os.environ.get("CODEX_AGENT_TEST_NATIVE_PACKAGES") == "1",
                         "real SDK packagers require explicit local opt-in")
    def test_actual_available_sdk_packages_equal_across_producers(self) -> None:
        from ci.tests.product_chain_sdk import build_sdk_packages, verify_cpp_consumer

        results = [build_sdk_packages(
            chain["root"] / "sdk-packages", chain["variants"],
            chain["compatibility"], chain["context"],
        ) for chain in (self.left, self.right)]
        self.assertTrue(results[0]["verified_languages"])
        self.assertEqual(results[0]["verified_languages"], results[1]["verified_languages"])
        self.assertTrue(results[0]["package_inventory"])
        for key in ("content_inventory", "package_inventory"):
            differing = {name for name in results[0][key].keys() | results[1][key].keys()
                         if results[0][key].get(name) != results[1][key].get(name)}
            self.assertFalse(differing, f"Cross-producer {key} differs: {sorted(differing)}")
        if "cpp" in results[0]["verified_languages"]:
            consumer = verify_cpp_consumer(results[0])
            self.assertFalse(consumer["executed"])
            print(f"Actual installed C++ loader compile/tamper proof: {consumer}")
        print(f"Actual local SDK packages: {results[0]['verified_languages']}; "
              f"unverified families: {results[0]['missing_tools']}")

    def test_content_mutation_rejected_and_original_evidence_preserved(self) -> None:
        args = self.left["compatibility_args"]
        paths = [args["contract_payload"], args["runtime_manifest"], *args["variant_bundles"].values()]
        paths.extend(path for path in self.left["contract"]["execution_closure"].rglob("*") if path.is_file())
        paths.extend(raw["evidence"] for raw in self.left["variants"]["raw_sdks"].values())
        paths.append(next(self.left["variants"]["stages"].glob("*/validation/output-manifest.json")))
        originals = {path: path.read_bytes() for path in self.left["root"].rglob("*")
                     if path.is_file() and ("receipt" in path.name or "attestation" in path.name or "c-abi-package" in path.name)}
        destination = self.root / "rejected-content" / "sdk-compatibility.json"
        destination.parent.mkdir()
        for path in paths:
            contents = path.read_bytes()
            mode = path.stat().st_mode
            with self.subTest(payload=path.name):
                try:
                    # Mutation is confined to this test's temporary product fixture.
                    path.chmod(0o644)
                    path.write_bytes(contents[:-1] + bytes([contents[-1] ^ 1]))
                    with self.assertRaises(ValueError):
                        produce_sdk_compatibility(output=destination, **args)
                    self.assertFalse(destination.exists())
                finally:
                    path.write_bytes(contents)
                    path.chmod(mode)
        for path, contents in originals.items():
            self.assertEqual(path.read_bytes(), contents)
        replay = self.root / "replay" / "sdk-compatibility.json"
        replay.parent.mkdir()
        produce_sdk_compatibility(output=replay, **args)
        self.assertEqual(sha256_file(replay), sha256_file(self.left["compatibility"]))


if __name__ == "__main__":
    unittest.main()
