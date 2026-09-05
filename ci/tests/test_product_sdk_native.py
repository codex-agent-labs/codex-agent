"""Staging authentication with signed synthetic products, not hosted evidence."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products.c_abi import C_ABI_PACKAGE_MANIFEST, TARGET_SPECS, _json_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_json_bytes, regular_file_inventory, sha256_bytes,
    snapshot_regular_tree,
)
from ci.products.sdk_native import INDEX_NAME, verify_staged_native_sdk_inputs, verify_native_sdk_package_phase, _stage_native_capability_inputs
from ci.products.receipt import write_output_manifest
from ci.native_wrappers import HOSTS, PACKAGE_CLASSIFIERS
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request


def staged_sdks(chain: dict, output: Path) -> Path:
    output.mkdir()
    compatibility = chain["compatibility"].read_bytes()
    (output / "sdk-compatibility.json").write_bytes(compatibility)
    records = []
    for target, spec in sorted(TARGET_SPECS.items()):
        classifier = spec.classifier.removeprefix("c-abi-")
        raw = chain["variants"]["raw_sdks"][classifier]
        snapshot_regular_tree(raw["verified_sdk"], output / classifier)
        report = load_json_bytes(raw["evidence"].read_bytes())
        records.append({
            "target": target, "classifier": classifier, "archiveSha256": report["archiveSha256"],
            "evidenceSha256": sha256_bytes(raw["evidence"].read_bytes()).removeprefix("sha256:"),
            "libraryPath": spec.library_path, "librarySha256": report["librarySha256"],
            "manifestSha256": sha256_bytes((output / classifier / C_ABI_PACKAGE_MANIFEST).read_bytes()).removeprefix("sha256:"),
            "producerCommit": report["producerCommit"], "producerTree": report["producerTree"],
        })
    (output / INDEX_NAME).write_bytes(_json_bytes({
        "schemaVersion": 2, "libraryVersion": "0.2.0", "runtimeProductVersion": "0.2.7",
        "sdkVersion": "0.2.9", "sdkCompatibilitySha256": sha256_bytes(compatibility).removeprefix("sha256:"),
        # Explicitly synthetic staging consumer, distinct from original Runtime producer.
        "producerCommit": "9" * 40, "producerTree": "8" * 40, "targets": records,
    }))
    return output


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class NativeSdkInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-sdk-inputs-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "synthetic-products", 43)
        cls.request = cls.root / "request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.sdks = staged_sdks(cls.chain, cls.root / "sdks")

    def verify(self, sdks, runtime=None):
        return verify_staged_native_sdk_inputs(sdks, self.request, runtime or self.chain["variants"]["stages"])

    def test_exact_original_inputs_survive_different_staging_producer(self):
        before = regular_file_inventory(self.sdks)
        value = self.verify(self.sdks)
        self.assertEqual(value, load_json_bytes((self.sdks / INDEX_NAME).read_bytes()))
        self.assertTrue(all(record["producerCommit"] != value["producerCommit"] for record in value["targets"]))
        self.assertEqual(before, regular_file_inventory(self.sdks))

    def test_private_capability_handoff_retains_exact_original_evidence(self):
        # Explicit post-authentication copy fixture, not a valid native execution.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            runtime = root / "runtime"
            validation = runtime / "macos-arm64/validation"
            closure = validation / "outputs/c-abi-bootstrap"
            closure.mkdir(parents=True)
            required = ("original-runner/test.kexe", "original-runner/compiler-header/libcodex_agent_api.h",
                        "reference/codex_agent_c.def", "native-junit/TEST-capi.xml", "consumers/consumer",
                        "original-runner/source/nativeMain/source.kt", "original-runner/source/nativeTest/test.kt")
            for name in required:
                path = closure / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"explicit fixture\n")
            api, coverage = b"canonical API fixture\n", b"canonical coverage fixture\n"
            library = (self.sdks / "macos-arm64/lib/libcodex_agent.dylib").read_bytes()
            bootstrap = {"canonical": {"apiReportSha256": sha256_bytes(api)[7:],
                                       "coverageReceiptSha256": sha256_bytes(coverage)[7:]},
                         "artifacts": {"releaseLibrarySha256": sha256_bytes(library)[7:]}}
            (closure / "bootstrap-evidence.json").write_bytes(canonical_json_bytes(bootstrap))
            payload = root / "contract.zip"
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("evidence/canonical-api.json", api)
                archive.writestr("evidence/canonical-coverage.json", coverage)
            outputs = write_output_manifest(validation, "runtime", "macos-arm64", "validation", "macos-arm64",
                                            "0.2.7", {"c-abi-bootstrap": "outputs/c-abi-bootstrap"})["outputs"]
            receipt = root / "validation.json"
            write_receipt(receipt, product="runtime", component="macos-arm64", phase="validation",
                          target="macos-arm64", version="0.2.7", version_identity="0.2.0",
                          outputs=outputs, upstream=[], context=self.chain["context"])
            args = {"contract_payload": payload, "contract_metadata_receipt": receipt,
                    "variant_phase_receipts": {"macos-arm64": {"validation": receipt, "package": receipt}}}
            before = regular_file_inventory(runtime)
            raw = receipt.read_bytes()
            _stage_native_capability_inputs(args, runtime, self.sdks, root / "result")
            self.assertEqual(before, regular_file_inventory(runtime))
            self.assertEqual(raw, (root / "result/receipts/runtime-macos-arm64-validation.json").read_bytes())
            self.assertEqual(regular_file_inventory(closure), regular_file_inventory(root / "result/bootstrap"))
            for case in ("missing", "kind", "contract", "library"):
                changed = load_json_bytes(raw)
                if case == "missing":
                    changed["outputs"] = [item for item in outputs if not item["relativePath"].endswith("test.kexe")]
                elif case == "kind":
                    changed["outputs"][0]["kind"] = "native"
                else:
                    record = load_json_bytes((closure / "bootstrap-evidence.json").read_bytes())
                    if case == "contract":
                        record["canonical"]["apiReportSha256"] = "0" * 64
                    else:
                        record["artifacts"]["releaseLibrarySha256"] = "0" * 64
                    (closure / "bootstrap-evidence.json").write_bytes(canonical_json_bytes(record))
                receipt.write_bytes(canonical_json_bytes(changed))
                with self.subTest(case=case), self.assertRaises(ValueError):
                    _stage_native_capability_inputs(args, runtime, self.sdks, root / case)
                (closure / "bootstrap-evidence.json").write_bytes(canonical_json_bytes(bootstrap))
                receipt.write_bytes(raw)

    def test_index_rebinding_cannot_authenticate_tampered_staging(self):
        for case in ("header", "legal", "import", "library", "evidence", "archive", "missing", "extra", "symlink"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                staged = root / "sdks"
                snapshot_regular_tree(self.sdks, staged)
                index = load_json_bytes((staged / INDEX_NAME).read_bytes())
                linux = next(item for item in index["targets"] if item["classifier"] == "linux-x64")
                if case in {"header", "legal", "import"}:
                    path = {
                        "header": "linux-x64/include/codex_agent.h",
                        "legal": "linux-x64/THIRD_PARTY_NOTICES.md",
                        "import": "windows-x64/lib/codex_agent.lib",
                    }[case]
                    (staged / path).write_bytes(b"rebound tampering\n")
                elif case == "library":
                    path = staged / "linux-x64" / linux["libraryPath"]
                    path.write_bytes(b"changed native library\n")
                    linux["librarySha256"] = sha256_bytes(path.read_bytes()).removeprefix("sha256:")
                elif case == "evidence":
                    path = staged / "linux-x64/codex-agent-c-abi-evidence.json"
                    proof = load_json_bytes(path.read_bytes())
                    proof["producerCommit"] = linux["producerCommit"] = "7" * 40
                    path.write_bytes(_json_bytes(proof))
                    linux["evidenceSha256"] = sha256_bytes(path.read_bytes()).removeprefix("sha256:")
                elif case == "archive":
                    linux["archiveSha256"] = "1" * 64
                elif case == "missing":
                    (staged / "linux-x64/LICENSE.txt").unlink()
                elif case == "extra":
                    (staged / "unexpected.txt").write_bytes(b"unrequested\n")
                else:
                    path = staged / "linux-x64/LICENSE.txt"
                    path.unlink()
                    path.symlink_to(self.sdks / "linux-x64/LICENSE.txt")
                (staged / INDEX_NAME).write_bytes(_json_bytes(index))
                with self.assertRaises((OSError, ValueError)):
                    self.verify(staged)

    def test_runtime_reference_bytes_require_original_receipt_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary).resolve() / "runtime"
            snapshot_regular_tree(self.chain["variants"]["stages"], runtime)
            reference = runtime / "linux-x64/validation/outputs/c-abi-reference/include/codex_agent.h"
            reference.write_bytes(b"unreceipted reference header\n")
            with self.assertRaises(ValueError):
                self.verify(self.sdks, runtime)

    def test_captured_request_not_temporary_source_replacement(self):
        from ci.products.sdk_compatibility import load_sdk_compatibility_request
        original = self.request.read_bytes()
        def decode(captured, **kwargs):
            changed = load_json_bytes(original)
            changed["sdkVersion"] = "0.2.99"
            self.request.write_bytes(canonical_json_bytes(changed))
            try:
                return load_sdk_compatibility_request(captured, **kwargs)
            finally:
                self.request.write_bytes(original)
        with patch("ci.products.sdk_native.load_sdk_compatibility_request", side_effect=decode):
            self.assertEqual(self.verify(self.sdks)["sdkVersion"], "0.2.9")

    def package(self, root, *, tamper=False, evidence=None, kind="package"):
        stage = root / "stage"
        package = stage / "outputs/csharp"
        package.mkdir(parents=True)
        compatibility = self.chain["compatibility"].read_bytes()
        with zipfile.ZipFile(package / "CodexAgent.0.2.9.nupkg", "w") as archive:
            archive.writestr("CodexAgent.nuspec", "<package><metadata><version>0.2.9</version></metadata></package>")
            archive.writestr("META-INF/codex-agent/sdk-compatibility.json", compatibility)
            for classifier, destination in PACKAGE_CLASSIFIERS.items():
                path = self.sdks / classifier / HOSTS[classifier][4]
                archive.writestr(f"runtimes/{destination}/native/{path.name}",
                                 b"tampered" if tamper else path.read_bytes())
        (package / "codex-agent-csharp-package-toolchain.tsv").write_text("tool\tversion\ndotnet\tsynthetic-fixture\n")
        (stage / "outputs/evidence").mkdir()
        (stage / "outputs/evidence/sdk-compatibility.json").write_bytes(compatibility if evidence is None else evidence)
        outputs = write_output_manifest(
            stage, "sdk", "csharp", "package", "desktop", "0.2.9",
            {kind: "outputs/csharp", "evidence": "outputs/evidence"},
        )["outputs"]
        receipt = root / "receipt.json"
        write_receipt(receipt, product="sdk", component="csharp", phase="package", target="desktop",
                      version="0.2.9", version_identity="0.2.9", outputs=outputs, upstream=[],
                      context=self.chain["context"])
        # Deliberately no planned upstream proof: this tests stage semantics,
        # not the still-pending execution/admission gate.
        return stage, receipt

    def test_final_package_phase_checks_authenticated_assets_and_receipt_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stage, receipt = self.package(root)
            before = regular_file_inventory(root)
            result, raw = verify_native_sdk_package_phase(
                stage, receipt, self.request, self.chain["variants"]["stages"], self.sdks,
            )
            self.assertEqual(raw, receipt.read_bytes())
            self.assertEqual(result["productVersion"], "0.2.9")
            self.assertEqual(before, regular_file_inventory(root))
        for case, changes in (("archive", {"tamper": True}), ("evidence", {"evidence": b"wrong\n"}),
                              ("kind", {"kind": "maven"})):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                stage, receipt = self.package(root, **changes)
                before = regular_file_inventory(root)
                with self.assertRaises(ValueError):
                    verify_native_sdk_package_phase(
                        stage, receipt, self.request, self.chain["variants"]["stages"], self.sdks,
                    )
                self.assertEqual(before, regular_file_inventory(root))


if __name__ == "__main__":
    unittest.main()
