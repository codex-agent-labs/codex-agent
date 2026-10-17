from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ci.products.contract import build_contract_bundle, validate_contract_package_stage
from ci.products.contract_attestation import (
    capture_contract_execution_closure, main, verify_contract_execution_closure,
)
from ci.products.inventory import (
    load_canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory,
    sha256_bytes, sha256_file, write_canonical_json,
)
from ci.products.plan import plan_phase
from ci.products.receipt import compute_build_key, output_inventory_digest, write_output_manifest, write_phase_receipt
from ci.products.registry import PhaseInstanceId
from ci.tests import test_contract_bundle as fixture


def execution_closure_fixture(root: Path, context: str = "first", *, producer=None,
                              trust_domain="development", target_hash_salt=b"", plan_factory=plan_phase):
    phases = fixture.ContractBundleTest()._product_phase_stages(
        root, execution_context=context, producer=producer, trust_domain=trust_domain,
        target_hash_salt=target_hash_salt,
        plan_factory=plan_factory,
    )
    version = fixture.VERSION
    validation = root / "validation-stage"
    shutil.copytree(phases["package_stage"] / "outputs", validation / "outputs")
    validate_contract_package_stage(
        phases["package_stage"], phases["package_receipt_path"], sha256_file(phases["package_receipt_path"]),
        phases["binary_receipt_path"], sha256_file(phases["binary_receipt_path"]),
        validation / "outputs/validation", version,
    )
    write_output_manifest(validation, "contract", "contract", "validation", "common", version, {
        "maven": "outputs/maven", "evidence": "outputs/evidence",
        "inventory": "outputs/inventories", "validation": "outputs/validation",
    })
    metadata = root / "metadata-stage"
    payload = metadata / "outputs" / fixture.ARCHIVE_NAME
    build_contract_bundle(phases["package_stage"] / "outputs", payload, version)
    write_output_manifest(metadata, "contract", "contract", "metadata", "common", version, {"contract-bundle": "outputs"})
    receipts = {phase: phases[f"{phase}_receipt_path"] for phase in ("binary", "package")}
    upstream = phases["package_receipt"]
    for index, (phase, stage) in enumerate((("validation", validation), ("metadata", metadata)), 2):
        plan = plan_factory(
            PhaseInstanceId("contract", "contract", phase, "common"),
            inventory=[{"relativePath": f"contract-{phase}", "bytes": 1, "sha256": sha256_bytes(b"p")}],
            versions={"contract": version, "runtime-release": version, "runtime-compatibility": version, "sdk": version},
            upstream_receipts=[upstream],
            toolchain_profile_digest=sha256_bytes(b"not-applicable-toolchain"),
            flags_digest=sha256_bytes(b"not-applicable-flags"),
        )
        phase_producer = producer if producer is not None else {
            **fixture.PRODUCER, "runId": index + 20, "commit": str(index) * 40, "tree": str(index + 1) * 40,
        }
        receipt_root = root / f"{phase}-receipt"
        receipt_root.mkdir()
        upstream = write_phase_receipt(
            stage, receipt_root, "contract", "contract", phase, "common", version,
            plan["buildKey"], plan["inputs"], phase_producer, trust_domain,
        )
        receipts[phase] = receipt_root / "phase-receipt.json"
    return payload, receipts, phases["binary_stage"] / "outputs/execution/contract-execution.zip"


class ContractExecutionClosureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="contract-execution-closure-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload, self.receipts, self.archive = execution_closure_fixture(self.root / "source")

    def capture(self, output: Path):
        return capture_contract_execution_closure(self.payload, self.receipts, self.archive, output)

    def test_captures_original_lineage_without_rebuilding_payload(self):
        before = regular_file_inventory(self.root / "source", allow_empty=True)
        output = self.root / "evidence"
        with mock.patch("ci.products.contract.build_contract_bundle", side_effect=AssertionError("payload rebuild")):
            value = self.capture(output)
            self.assertEqual(value, verify_contract_execution_closure(self.payload, output))
        self.assertEqual(before, regular_file_inventory(self.root / "source", allow_empty=True))
        self.assertEqual(5, len(value["files"]))
        self.assertEqual(6, len(regular_file_inventory(output)))
        for phase, path in self.receipts.items():
            self.assertEqual(path.read_bytes(), (output / f"receipts/{phase}.json").read_bytes())
        self.assertEqual(self.archive.read_bytes(), (output / "execution/contract-execution.zip").read_bytes())
        self.assertNotEqual(
            load_canonical_json_bytes(self.receipts["binary"].read_bytes())["producer"],
            load_canonical_json_bytes(self.receipts["metadata"].read_bytes())["producer"],
        )
        with self.assertRaises(ValueError):
            self.capture(output)

    def test_late_closure_mutation_fails_before_publication(self):
        output = self.root / "late-closure"

        def mutate_then_publish(source, destination, **kwargs):
            (Path(source) / "receipts/metadata.json").write_bytes(b"late mutation\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch("ci.products.contract_attestation.publish_regular_tree",
                        side_effect=mutate_then_publish), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture(output)
        self.assertFalse(output.exists())

    def test_closure_mutation_before_inventory_pin_is_not_baselined(self):
        output = self.root / "changed-before-pin"

        def write_then_mutate(path, value):
            write_canonical_json(path, value)
            if Path(path).name == "contract-execution-closure.json":
                (Path(path).parent / "receipts/metadata.json").write_bytes(b"changed before pin\n")

        with mock.patch("ci.products.contract_attestation.write_canonical_json",
                        side_effect=write_then_mutate), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.capture(output)
        self.assertFalse(output.exists())

    def test_run_only_changes_preserve_payload_but_keep_distinct_external_proof(self):
        other_payload, other_receipts, other_archive = execution_closure_fixture(self.root / "second", "other-run")
        first = self.capture(self.root / "first-proof")
        second = capture_contract_execution_closure(other_payload, other_receipts, other_archive, self.root / "second-proof")
        self.assertEqual(self.payload.read_bytes(), other_payload.read_bytes())
        self.assertEqual(first["payload"], second["payload"])
        self.assertNotEqual(first["files"], second["files"])
        self.assertEqual(second, verify_contract_execution_closure(self.payload, self.root / "second-proof"))
        with self.assertRaises(ValueError):
            capture_contract_execution_closure(self.payload, self.receipts, other_archive, self.root / "cross-paired")
        self.assertFalse((self.root / "cross-paired").exists())

    def test_rebound_receipt_mutations_fail_before_publication(self):
        for phase, field in (("validation", "upstream"), ("metadata", "upstream"), ("validation", "outputs"), ("binary", "repository")):
            with self.subTest(phase=phase, field=field):
                changed = load_canonical_json_bytes(self.receipts[phase].read_bytes())
                if field == "upstream":
                    changed["inputs"]["upstreamArtifacts"][0]["outputsDigest"] = sha256_bytes(b"wrong")
                    changed["buildKey"] = compute_build_key(
                        product="contract", component="contract", phase=phase, target="common", inputs=changed["inputs"],
                    )
                elif field == "outputs":
                    changed["outputs"][-1]["sha256"] = sha256_bytes(b"wrong")
                else:
                    changed["producer"]["repository"] = "unrelated/repository"
                path = self.root / f"{phase}-{field}.json"
                write_canonical_json(path, changed)
                receipts = {**self.receipts, phase: path}
                if field == "outputs":
                    metadata = load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
                    metadata["inputs"]["upstreamArtifacts"][0]["outputsDigest"] = output_inventory_digest(changed["outputs"])
                    metadata["buildKey"] = compute_build_key(
                        product="contract", component="contract", phase="metadata", target="common", inputs=metadata["inputs"],
                    )
                    metadata_path = self.root / "rebound-metadata.json"
                    write_canonical_json(metadata_path, metadata)
                    receipts["metadata"] = metadata_path
                output = self.root / f"rejected-{phase}-{field}"
                with self.assertRaises(ValueError):
                    capture_contract_execution_closure(self.payload, receipts, self.archive, output)
                self.assertFalse(output.exists())

    def test_cli_and_external_inventory_mutations_fail_closed(self):
        output = self.root / "evidence"
        arguments = ["capture-closure", "--payload", str(self.payload), "--execution-archive", str(self.archive), "--output-directory", str(output)]
        for phase, path in self.receipts.items():
            arguments += [f"--{phase}-receipt", str(path)]
        self.assertEqual(0, main(arguments))
        self.assertEqual(0, main(["verify-closure", "--payload", str(self.payload), "--evidence-directory", str(output)]))
        for mutation in ("extra", "missing", "tamper", "symlink", "schema-bool"):
            with self.subTest(mutation=mutation):
                target = self.root / mutation
                shutil.copytree(output, target)
                receipt = target / "receipts/binary.json"
                if mutation == "extra":
                    (target / "extra").write_bytes(b"extra")
                elif mutation == "missing":
                    receipt.unlink()
                elif mutation == "tamper":
                    receipt.write_bytes(b"{}\n")
                elif mutation == "symlink":
                    receipt.unlink()
                    receipt.symlink_to(self.receipts["binary"])
                else:
                    path = target / "contract-execution-closure.json"
                    value = load_canonical_json_bytes(path.read_bytes())
                    value["schemaVersion"] = True
                    write_canonical_json(path, value)
                with self.assertRaises(ValueError):
                    verify_contract_execution_closure(self.payload, target)


if __name__ == "__main__":
    unittest.main()
