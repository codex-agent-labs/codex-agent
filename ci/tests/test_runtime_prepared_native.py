"""Exact native selection binding with real receipts/stages, not source admission.

The caller-authenticated original map is a fixture input. Detached Contract and
Runtime trust/full semantics remain the existing native signing leaf's gate.
"""

from copy import deepcopy
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_runtime_capture as fixture
from ci import runtime_prepared_native as verifier
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId


class RuntimePreparedNativeTest(unittest.TestCase):
    def test_package_import_without_fixture_pythonpath_preserves_registry_identity(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, "-B", "-c",
            "import ci.runtime_prepared_native as native; "
            "from products.registry import PhaseInstanceId; "
            "assert native.PhaseInstanceId is PhaseInstanceId; "
            "assert callable(native.verify_native_prepared_selection)"],
            cwd=Path(__file__).resolve().parents[2], env=environment, capture_output=True, text=True, check=False,
            timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="prepared-native-binding-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.root = self.work / "selected"
        self.original_root = self.work / "originals"
        self.target = "linux-x64"
        self.originals = {}
        for product, component, target in (("contract", "contract", "common"), ("runtime", self.target, self.target)):
            for phase in verifier._PHASES:
                identity = PhaseInstanceId(product, component, phase, target)
                relative = "-".join((product, component, phase, target))
                directory = self.original_root / relative
                stage = directory / "stage"
                (stage / "outputs").mkdir(parents=True)
                (stage / "outputs/original.bin").write_bytes((relative + " original\n").encode())
                kind = ("contract-bundle" if product == "contract" else "runtime-variant") if phase == "metadata" else "fixture"
                version = "0.2.0" if product == "contract" else "0.2.7"
                manifest = write_output_manifest(stage, product, component, phase, target, version, {kind: "outputs"})
                receipt_path = directory / "phase-receipt.json"
                receipt = fixture.write_receipt(receipt_path, product=product, component=component,
                    phase=phase, target=target, version=version, outputs=manifest["outputs"], upstream=[],
                    context={"producer": fixture.PRODUCER})
                self.originals[identity] = {"stage": stage, "receiptPath": receipt_path, "receipt": receipt,
                    "receiptBytes": receipt_path.read_bytes()}
                selected_stage = (self.root / "predecessors" / relative / "stage" if product == "contract"
                                  else self.root / "runtime" / target / phase)
                snapshot_regular_tree(stage, selected_stage)
                self.write(self.root / "predecessors" / relative / "phase-receipt.json", receipt_path.read_bytes())
                if product == "contract":
                    self.write(self.root / f"contract-input/execution-closure/receipts/{phase}.json", receipt_path.read_bytes())
        metadata = self.originals[PhaseInstanceId("runtime", self.target, "metadata", self.target)]
        contract = self.originals[PhaseInstanceId("contract", "contract", "metadata", "common")]
        self.key = metadata["receipt"]["buildKey"]
        stem = "codex-agent-contract-0.2.0"
        self.selection = {"schemaVersion": 1, "target": self.target, "producer": deepcopy(fixture.PRODUCER),
            "metadata": {"product": "runtime", "component": self.target, "phase": "metadata", "target": self.target,
                "buildKey": self.key, "state": "retained", "source": "same-pr", "transportSource": "same-pr",
                "receiptSha256": sha256_bytes(metadata["receiptBytes"]), "objectSha256": "sha256:" + "a" * 64,
                "misses": []}, "contractVersion": "0.2.0",
            "contract": {"stage": "predecessors/contract-contract-metadata-common/stage",
                "receipt": "predecessors/contract-contract-metadata-common/phase-receipt.json",
                "payload": f"contract-input/{stem}.zip", "attestation": f"contract-input/{stem}.attestation.json",
                "signature": f"contract-input/{stem}.attestation.sig", "public_key": "contract-input/public-key.pub"},
            "contractReceiptSha256": sha256_bytes(contract["receiptBytes"]),
            "receiptSha256s": {phase: sha256_bytes(self.originals[
                PhaseInstanceId("runtime", self.target, phase, self.target)]["receiptBytes"]) for phase in verifier._PHASES},
            "phaseReceipts": {phase: f"predecessors/runtime-{self.target}-{phase}-{self.target}/phase-receipt.json"
                for phase in verifier._PHASES}, "runtimeStageRoot": "runtime",
            "variantPayload": f"runtime/{self.target}/metadata/outputs/original.bin", "releaseHandoffs": []}
        for name, relative in self.selection["contract"].items():
            if name not in {"stage", "receipt"}:
                self.write(self.root / relative, ("synthetic detached " + name).encode())
        self.save()

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def save(self):
        self.write(self.root / "selection.json", canonical_json_bytes(self.selection))

    def verify(self, **changes):
        arguments = {"producer": fixture.PRODUCER, "target": self.target,
            "expected_build_key": self.key, "originals": self.originals}
        arguments.update(changes)
        return verifier.verify_native_prepared_selection(self.root, self.selection, **arguments)

    def test_exact_original_stage_receipt_and_leaf_argument_binding_without_rewrite(self):
        before = regular_file_inventory(self.work)
        result = self.verify()
        self.assertEqual({"runtime_stage_root", "phase_receipts", "variant_payload", "contract", "contract_version",
            "release_handoffs", "expected_receipt_sha256s", "expected_contract_receipt_sha256", "expected_build_key"}, set(result))
        self.assertEqual(self.root / "runtime", result["runtime_stage_root"])
        self.assertEqual(self.root / self.selection["variantPayload"], result["variant_payload"])
        self.assertEqual({name: self.root / relative for name, relative in self.selection["contract"].items()}, result["contract"])
        for phase, path in result["phase_receipts"].items():
            original = self.originals[PhaseInstanceId("runtime", self.target, phase, self.target)]
            self.assertEqual(original["receiptBytes"], path.read_bytes())
            self.assertEqual(sha256_bytes(path.read_bytes()), result["expected_receipt_sha256s"][phase])
        self.assertEqual(self.key, result["expected_build_key"])
        self.assertEqual("0.2.0", result["contract_version"])
        self.assertEqual((), result["release_handoffs"])
        self.assertEqual(before, regular_file_inventory(self.work))

    def test_fixed_retained_handoff_path_is_forwarded_without_new_signature_claim(self):
        relative = "retained-release-handoffs/" + "a" * 64
        self.write(self.root / relative / "original.sig", b"synthetic proof admitted later by leaf")
        self.selection["releaseHandoffs"] = [relative]
        self.save()
        self.assertEqual((self.root / relative,), self.verify()["release_handoffs"])
        for paths in ([relative, relative], ["../outside"], ["/absolute"], ["retained-release-handoffs/other"]):
            self.selection["releaseHandoffs"] = paths
            self.save()
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                self.verify()

    def test_selection_schema_identity_digest_and_path_substitutions_fail(self):
        original = deepcopy(self.selection)
        mutations = (lambda s: s.update(extra=True), lambda s: s.pop("releaseHandoffs"),
            lambda s: s.update(target="linux-arm64"), lambda s: s["producer"].update(runId=999),
            lambda s: s["metadata"].update(buildKey="sha256:" + "f" * 64),
            lambda s: s["receiptSha256s"].update(binary="sha256:" + "f" * 64),
            lambda s: s.update(contractVersion="0.2.1"),
            lambda s: s.update(contractReceiptSha256="sha256:" + "f" * 64),
            lambda s: s.update(runtimeStageRoot="runtime/../runtime"),
            lambda s: s["phaseReceipts"].update(binary=s["phaseReceipts"]["package"]),
            lambda s: s.update(variantPayload="/outside.zip"),
            lambda s: s["contract"].update(payload="elsewhere/codex-agent-contract-0.2.0.zip"))
        for index, mutate in enumerate(mutations):
            self.selection = deepcopy(original)
            mutate(self.selection)
            self.save()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.verify()
        self.selection = original
        self.save()
        self.selection["contractVersion"] = "0.2.1"
        with self.assertRaises(ValueError):
            self.verify()

    def test_changed_receipts_stages_and_symbolic_or_extra_runtime_members_fail(self):
        paths = [self.root / self.selection["phaseReceipts"]["binary"],
            self.root / "runtime/linux-x64/binary/outputs/original.bin",
            self.root / "predecessors/contract-contract-metadata-common/stage/outputs/original.bin",
            self.root / "contract-input/execution-closure/receipts/package.json",
            self.originals[PhaseInstanceId("runtime", self.target, "binary", self.target)]["receiptPath"]]
        for path in paths:
            raw = path.read_bytes()
            path.write_bytes(raw + b"tamper")
            try:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.verify()
            finally:
                path.write_bytes(raw)
        extra = self.root / "runtime/unrelated/original.bin"
        self.write(extra, b"unrelated stage")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        extra.symlink_to(paths[1])
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_or_mismatched_authenticated_original_and_late_mutation_fail(self):
        identity = PhaseInstanceId("runtime", self.target, "binary", self.target)
        missing = dict(self.originals)
        del missing[identity]
        with self.assertRaises(ValueError):
            self.verify(originals=missing)
        changed = deepcopy(self.originals)
        changed[identity]["receipt"]["producer"]["runId"] += 1
        with self.assertRaises(ValueError):
            self.verify(originals=changed)
        inventory = verifier.regular_file_inventory
        calls = 0
        def mutate(root, **kwargs):
            nonlocal calls
            result = inventory(root, **kwargs)
            if Path(root) == self.root:
                calls += 1
                if calls == 1:
                    self.write(self.root / "late-added.json", b"changed after initial inventory")
            return result
        with patch.object(verifier, "regular_file_inventory", side_effect=mutate), self.assertRaises(ValueError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
