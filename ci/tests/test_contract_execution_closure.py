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

    def test_session_reuses_exact_closure_bytes_across_paths_but_not_sessions(self):
        from ci.products import contract_attestation as verifier
        from ci.products.restore import verification_session

        output = self.root / "evidence"
        expected = self.capture(output)
        relocated = self.root / "relocated"
        shutil.copytree(output, relocated)
        moved_payload = self.root / "moved" / self.payload.name
        moved_payload.parent.mkdir()
        shutil.copyfile(self.payload, moved_payload)
        with mock.patch.object(verifier, "_verify_execution_closure_inputs",
                               wraps=verifier._verify_execution_closure_inputs) as replay:
            with verification_session():
                first = verify_contract_execution_closure(self.payload, output)
                first["files"].clear()
                self.assertEqual(expected, verify_contract_execution_closure(moved_payload, relocated))
                self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
                self.assertEqual(1, replay.call_count)
            with verification_session():
                self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
            self.assertEqual(2, replay.call_count)
            verify_contract_execution_closure(self.payload, output)
            self.assertEqual(3, replay.call_count)

    def test_session_hits_recheck_evidence_payload_and_original_lineage(self):
        from ci.products import contract_attestation as verifier
        from ci.products.restore import verification_session

        output = self.root / "evidence"
        self.capture(output)
        other_payload, other_receipts, other_archive = execution_closure_fixture(self.root / "other", "other-run")
        other = self.root / "other-evidence"
        other_value = capture_contract_execution_closure(other_payload, other_receipts, other_archive, other)
        self.assertEqual(self.payload.read_bytes(), other_payload.read_bytes())
        with verification_session(), mock.patch.object(verifier, "_verify_execution_closure_inputs",
                wraps=verifier._verify_execution_closure_inputs) as replay:
            verify_contract_execution_closure(self.payload, output)
            self.assertEqual(other_value, verify_contract_execution_closure(other_payload, other))
            self.assertEqual(2, replay.call_count)
            for mutation in ("extra", "missing", "tamper", "symlink", "rebound-archive"):
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
                        archive = target / "execution/contract-execution.zip"
                        archive.write_bytes(b"not a ZIP")
                        manifest = target / "contract-execution-closure.json"
                        value = load_canonical_json_bytes(manifest.read_bytes())
                        value["files"] = regular_file_inventory(target, excluded_paths=(manifest.name,))
                        write_canonical_json(manifest, value)
                    with self.assertRaises(ValueError):
                        verify_contract_execution_closure(self.payload, target)
            changed = self.root / "changed" / self.payload.name
            changed.parent.mkdir()
            changed.write_bytes(self.payload.read_bytes() + b"changed")
            with self.assertRaises(ValueError):
                verify_contract_execution_closure(changed, output)
            renamed = self.root / "wrong-name.zip"
            shutil.copyfile(self.payload, renamed)
            with self.assertRaises(ValueError):
                verify_contract_execution_closure(renamed, output)

    def test_session_failure_and_full_cache_keep_the_full_verifier(self):
        from ci.products import contract_attestation as verifier
        from ci.products.restore import verification_session

        output = self.root / "evidence"
        expected = self.capture(output)
        with verification_session() as session:
            with mock.patch.object(verifier, "_verify_execution_closure_inputs", side_effect=ValueError("failure")):
                with self.assertRaisesRegex(ValueError, "failure"):
                    verify_contract_execution_closure(self.payload, output)
            self.assertFalse(session.get("contractExecutionClosures"))
            with mock.patch.object(verifier, "_verify_execution_closure_inputs",
                                   wraps=verifier._verify_execution_closure_inputs) as replay:
                self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
                verify_contract_execution_closure(self.payload, output)
                self.assertEqual(1, replay.call_count)
        with verification_session() as session, mock.patch.object(verifier, "_verify_execution_closure_inputs",
                wraps=verifier._verify_execution_closure_inputs) as replay:
            session["contractExecutionClosures"] = {(str(i), "unused", "unused") for i in range(64)}
            for _ in range(2):
                self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
            self.assertEqual(2, replay.call_count)
            self.assertEqual(64, len(session["contractExecutionClosures"]))

    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
    def test_session_semantic_reuse_never_reuses_signature_or_trust_admission(self):
        from ci.products import contract_attestation as verifier
        from ci.products.restore import verification_session
        from ci.tests.test_contract_attestation import ContractAttestationTest

        signed = ContractAttestationTest()
        signed.setUp()
        self.addCleanup(signed.doCleanups)
        attestation, signature, expected = signed.build()
        with verification_session(), mock.patch.object(verifier, "_verify_execution_closure_inputs",
                wraps=verifier._verify_execution_closure_inputs) as replay, \
                mock.patch.object(verifier, "verify_manifest_signature",
                                  wraps=verifier.verify_manifest_signature) as authenticate:
            for _ in range(2):
                self.assertEqual(expected, signed.verify(attestation, signature))
            self.assertEqual(1, replay.call_count)
            self.assertEqual(2, authenticate.call_count)
            signature.write_bytes(b"invalid signature")
            with self.assertRaises(ValueError):
                signed.verify(attestation, signature)
            self.assertEqual(3, authenticate.call_count)
            with self.assertRaises(ValueError):
                signed.verify(attestation, signature, required_trust_domain="release")
            self.assertEqual(1, replay.call_count)

    def test_sdk_worker_scope_reuses_closure_and_restores_context_on_failure(self):
        from ci.products import contract_attestation as verifier
        from ci.products import sdk_validation as sdk

        output = self.root / "evidence"
        expected = self.capture(output)
        self.assertIsNone(verifier._EXECUTION_CLOSURE_SESSION.get())
        payload_writes = []
        write = Path.write_bytes
        def record_write(path, data):
            if path.name == self.payload.name and path.parent.name.startswith("contract-closure-verify-"):
                payload_writes.append(path)
            return write(path, data)
        with mock.patch.object(verifier, "_verify_execution_closure_inputs",
                               wraps=verifier._verify_execution_closure_inputs) as replay, \
                mock.patch.object(Path, "write_bytes", new=record_write):
            with sdk._byte_inventory_scope():
                cache = sdk._BYTE_INVENTORIES.get()
                self.assertIs(cache, verifier._EXECUTION_CLOSURE_SESSION.get())
                for _ in range(3):
                    with sdk._byte_inventory_scope():
                        self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
                self.assertEqual(1, replay.call_count)
                self.assertEqual(1, len(payload_writes))
                receipt = output / "receipts/binary.json"
                original = receipt.read_bytes()
                receipt.write_bytes(b"tampered\n")
                with self.assertRaises(ValueError):
                    verify_contract_execution_closure(self.payload, output)
                receipt.write_bytes(original)
            self.assertIsNone(verifier._EXECUTION_CLOSURE_SESSION.get())
            self.assertEqual({}, cache)
            with self.assertRaisesRegex(RuntimeError, "scope failure"):
                with sdk._byte_inventory_scope():
                    self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
                    self.assertEqual(2, replay.call_count)
                    raise RuntimeError("scope failure")
            self.assertIsNone(verifier._EXECUTION_CLOSURE_SESSION.get())
            self.assertIsNone(sdk._BYTE_INVENTORIES.get())
            self.assertEqual(expected, verify_contract_execution_closure(self.payload, output))
            self.assertEqual(3, replay.call_count)

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
