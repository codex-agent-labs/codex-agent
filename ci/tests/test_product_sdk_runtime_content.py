"""Content-only fixtures: these tests do not claim actual native execution."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products.contract import build_contract_bundle
from ci.products.contract_model import _execution_tree_digest, _verify_extracted_contract_directory
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.sdk_runtime_content import (
    _bootstrap_content, _verify_bootstrap_handoff, bootstrap_content, verify_runtime_bootstrap_content,
)
from ci.tests.test_contract_bundle import ARCHIVE_NAME, VERSION, _write_staging


class BootstrapContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="bootstrap-content-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        staging = cls.root / "staging"
        _write_staging(staging)
        archive = cls.root / ARCHIVE_NAME
        build_contract_bundle(staging, archive, VERSION)
        cls.contract = cls.root / "contract"
        with zipfile.ZipFile(archive) as source:
            source.extractall(cls.contract)
        cls.verified = _verify_extracted_contract_directory(cls.contract, include_canonical_api_projection=True)

    def setUp(self):
        api = self.verified[1]
        keys = api["memberKeys"]
        self.raw = self.root / "bootstrap-evidence.json"
        self.report = {
            "schemaVersion": 1, "protocol": "codex-agent-c-abi-bootstrap-evidence-v1",
            "result": "observed", "milestone": "D104", "language": "c-abi",
            "canonical": {
                **api["canonical"], "nativeTargetSha256": api["targetSha256"]["native"],
                "capabilityCount": 556, "observedCapabilityCount": 556,
                "observedCapabilitySha256": sha256_bytes("".join(key + "\n" for key in keys).encode())[7:],
                "observedCapabilityKeys": keys, "missingCapabilityKeys": [],
            },
            "toolchain": {"clang": "/fixture/clang", "clangCpp": "/fixture/clang++",
                          "clangVersion": "fixture clang\nversion", "macosSdk": "/fixture/sdk"},
            "artifacts": {**{name: "1" * 64 for name in (
                "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
                "generatedHeaderSha256", "releaseLibrarySha256", "nativeTestExecutableSha256",
                "nativeMainSourcesSha256", "nativeTestSourcesSha256", "nativeTestResultsSha256",
            )}, "fileIdentity": "fixture dylib", "installName": "@rpath/libcodex_agent.dylib"},
            "compilerConsumers": [{"id": "fixture", "sourceSha256": "2" * 64,
                                   "artifactSha256": "3" * 64, "executed": True}],
            "linkedPublicSymbols": ["codex_agent_fixture"],
            "nativeTests": [{"testId": "fixture.passed", "status": "passed"}],
            "claims": [{"capabilityKey": key, "headerReferences": ["codex_agent_fixture"],
                        "consumerReferences": ["codex_agent_fixture"], "publicSymbols": ["codex_agent_fixture"],
                        "nativeTestIds": ["fixture.passed"]} for key in keys],
        }

    def project(self, report=None):
        self.raw.write_bytes(canonical_json_bytes(self.report if report is None else report))
        return bootstrap_content(self.raw, self.contract)

    def test_real_contract_verification_and_raw_preservation(self):
        value = self.project()
        self.assertEqual("runtime-c-abi-bootstrap-content", value["kind"])
        self.assertEqual(556, len(value["claims"]))
        self.assertEqual(self.verified[0]["canonicalCoverageDigest"], value["canonicalCoverageDigest"])
        self.assertEqual(canonical_json_bytes(self.report), self.raw.read_bytes())
        self.assertNotIn("producer", value)
        self.assertNotIn("signing", value)

    def test_execution_noise_is_external_but_product_and_source_mutations_are_not(self):
        # Mock only the previously independently verified Contract snapshot to
        # keep this paired model matrix cheap. Never a native acceptance proof.
        with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=self.verified):
            expected = canonical_json_bytes(self.project())
            changed = copy.deepcopy(self.report)
            changed["toolchain"] = {key: "different execution path" for key in changed["toolchain"]}
            for name in ("generatedHeaderSha256", "nativeTestExecutableSha256", "nativeTestResultsSha256"):
                changed["artifacts"][name] = "4" * 64
            changed["artifacts"]["fileIdentity"] = "different inspection output"
            changed["artifacts"]["installName"] = "different inspection display"
            changed["compilerConsumers"][0]["artifactSha256"] = "5" * 64
            self.assertEqual(expected, canonical_json_bytes(self.project(changed)))
            for name in ("reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
                         "releaseLibrarySha256", "nativeMainSourcesSha256", "nativeTestSourcesSha256"):
                with self.subTest(artifact=name):
                    changed = copy.deepcopy(self.report)
                    changed["artifacts"][name] = "6" * 64
                    self.assertNotEqual(expected, canonical_json_bytes(self.project(changed)))
            for name, value in (("sourceSha256", "7" * 64), ("executed", False)):
                changed = copy.deepcopy(self.report)
                changed["compilerConsumers"][0][name] = value
                self.assertNotEqual(expected, canonical_json_bytes(self.project(changed)))
            changed = copy.deepcopy(self.report)
            changed["claims"][0]["headerReferences"].append("new_reference")
            self.assertNotEqual(expected, canonical_json_bytes(self.project(changed)))

    def test_raw_contract_digests_cannot_be_substituted(self):
        with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=self.verified):
            for name in ("apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256"):
                with self.subTest(digest=name):
                    changed = copy.deepcopy(self.report)
                    changed["canonical"][name] = "9" * 64
                    with self.assertRaisesRegex(ValueError, "verified Contract"):
                        self.project(changed)

    def test_verified_contract_execution_identity_does_not_replace_content_identity(self):
        with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=self.verified):
            expected = canonical_json_bytes(self.project())
        manifest, api = copy.deepcopy(self.verified)
        for name in ("apiReportSha256", "coverageReceiptSha256"):
            api["canonical"][name] = "8" * 64
            self.report["canonical"][name] = "8" * 64
        api["targetSha256"]["native"] = "7" * 64
        self.report["canonical"]["nativeTargetSha256"] = "7" * 64
        # Models different already-authenticated raw evidence, not permission to
        # supply an arbitrary digest to production Contract verification.
        with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=(manifest, api)):
            self.assertEqual(expected, canonical_json_bytes(self.project()))
        for name in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest"):
            changed = copy.deepcopy(manifest)
            changed[name] = "sha256:" + "9" * 64
            with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=(changed, api)):
                self.assertNotEqual(expected, canonical_json_bytes(self.project()))

    def test_incomplete_failed_duplicate_unknown_and_unsafe_inputs_fail(self):
        with patch("ci.products.sdk_runtime_content._verify_extracted_contract_directory", return_value=self.verified):
            mutations = [
                lambda report: report.update(producer="unexpected"),
                lambda report: report.update(schemaVersion=True),
                lambda report: report["nativeTests"][0].update(status="skipped"),
                lambda report: report["nativeTests"].append(report["nativeTests"][0]),
                lambda report: report["claims"].pop(),
                lambda report: report["claims"][0].update(nativeTestIds=["absent"]),
                lambda report: report["claims"][0].update(publicSymbols=["absent"]),
                lambda report: report["claims"][0].update(publicSymbols=[]),
                lambda report: report["compilerConsumers"].append(report["compilerConsumers"][0]),
                lambda report: report["compilerConsumers"][0].update(executed="true"),
                lambda report: report["artifacts"].update(nativeTestResultsSha256="invalid"),
                lambda report: report["canonical"].update(missingCapabilityKeys=["missing"]),
            ]
            for index, mutate in enumerate(mutations):
                with self.subTest(index=index):
                    changed = copy.deepcopy(self.report)
                    mutate(changed)
                    with self.assertRaises(ValueError):
                        self.project(changed)
        self.project()
        linked = self.root / "symlink.json"
        linked.symlink_to(self.raw)
        with self.assertRaises(ValueError):
            bootstrap_content(linked, self.contract)
        self.raw.write_bytes(b'{"schemaVersion":1,"schemaVersion":1}\n')
        with self.assertRaises(ValueError):
            bootstrap_content(self.raw, self.contract)

    def _handoff(self, root):
        """Previously-authenticated-input model only, never native execution proof."""
        test_class = "io.github.codex_agent_labs.codexagent.capi.Fixture"
        test_id = f"macosArm64Test.{test_class}#passed[macosArm64]"
        self.report["nativeTests"] = [{"testId": test_id, "status": "passed"}]
        for claim in self.report["claims"]:
            claim["nativeTestIds"] = [test_id]
        files = {
            "bootstrap-reference/include/codex_agent.h": b"void codex_agent_fixture(void);\n",
            "bootstrap-reference/export-policy/macos.exports": b"_codex_agent_fixture\n",
            "bootstrap-reference/consumer/source.c": b"codex_agent_fixture();\n",
            "bootstrap/reference/codex_agent_c.def": b"headers = codex_agent.h\n",
            "bootstrap/original-runner/compiler-header/libcodex_agent_api.h": b"fixture generated header\n",
            "bootstrap/original-runner/test.kexe": b"fixture native runner\n",
            "bootstrap/original-runner/source/nativeMain/main.kt": b"fixture source\n",
            "bootstrap/original-runner/source/nativeTest/test.kt": b"fixture test source\n",
            "bootstrap/consumers/fixture": b"fixture compiled consumer\n",
            "sdks/macos-arm64/lib/libcodex_agent.dylib": b"fixture runtime library\n",
            f"bootstrap/native-junit/TEST-{test_class}.xml": (
                f'<testsuite><testcase classname="testImportedMacosArm64CAbi.{test_class}" '
                'name="passed[macosArm64]"/></testsuite>\n').encode(),
        }
        for name in ("canonical-api.json", "canonical-coverage.json"):
            files[f"contract/{name}"] = (self.contract / "evidence" / name).read_bytes()
        files["contract/contract-manifest.json"] = (self.contract / "contract-manifest.json").read_bytes()
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for field, name in {
            "reviewedHeaderSha256": "bootstrap-reference/include/codex_agent.h",
            "exportPolicySha256": "bootstrap-reference/export-policy/macos.exports",
            "cinteropDefinitionSha256": "bootstrap/reference/codex_agent_c.def",
            "generatedHeaderSha256": "bootstrap/original-runner/compiler-header/libcodex_agent_api.h",
            "releaseLibrarySha256": "sdks/macos-arm64/lib/libcodex_agent.dylib",
            "nativeTestExecutableSha256": "bootstrap/original-runner/test.kexe",
        }.items():
            self.report["artifacts"][field] = sha256_bytes(files[name])[7:]
        for field, name in {
            "nativeMainSourcesSha256": "bootstrap/original-runner/source/nativeMain",
            "nativeTestSourcesSha256": "bootstrap/original-runner/source/nativeTest",
            "nativeTestResultsSha256": "bootstrap/native-junit",
        }.items():
            self.report["artifacts"][field] = _execution_tree_digest(root / name)
        self.report["compilerConsumers"][0]["sourceSha256"] = sha256_bytes(files["bootstrap-reference/consumer/source.c"])[7:]
        self.report["compilerConsumers"][0]["artifactSha256"] = sha256_bytes(files["bootstrap/consumers/fixture"])[7:]
        self._rebind_content(root)

    def _rebind_content(self, root):
        raw = root / "bootstrap/bootstrap-evidence.json"
        raw.write_bytes(canonical_json_bytes(self.report))
        (root / "bootstrap/bootstrap-content.json").write_bytes(canonical_json_bytes(
            _bootstrap_content(raw, *self.verified)))

    def test_full_handoff_rehashes_every_raw_artifact_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._handoff(root)
            before = regular_file_inventory(root)
            _verify_bootstrap_handoff(root)
            self.assertEqual(before, regular_file_inventory(root))
            for record in before:
                if record["relativePath"].startswith("contract/"):
                    continue  # Contract authentication is the outer original-input gate.
                path = root / record["relativePath"]
                original = path.read_bytes()
                path.write_bytes(original + b"mutation")
                with self.subTest(path=record["relativePath"]), self.assertRaises(ValueError):
                    _verify_bootstrap_handoff(root)
                self.assertEqual(original + b"mutation", path.read_bytes())
                path.write_bytes(original)
            duplicate = root / "bootstrap-reference/consumer/duplicate.c"
            duplicate.write_bytes((root / "bootstrap-reference/consumer/source.c").read_bytes())
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                _verify_bootstrap_handoff(root)

    def test_runtime_only_paths_need_no_sdk_package_or_compatibility_declaration(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / "fixture-handoff"
            self._handoff(original)
            paths = []
            for source, destination in (
                ("bootstrap", "runtime-validation"), ("bootstrap-reference", "runtime-reference"),
                ("contract", "contract-evidence"), ("sdks/macos-arm64", "c-abi-runtime-payload"),
            ):
                path = root / destination
                (original / source).rename(path)  # Move only this isolated fixture's new directories.
                paths.append(path)
            before = [regular_file_inventory(path) for path in paths]
            value = verify_runtime_bootstrap_content(*paths)
            self.assertEqual((paths[0] / "bootstrap-content.json").read_bytes(), canonical_json_bytes(value))
            self.assertEqual(before, [regular_file_inventory(path) for path in paths])
            self.assertFalse(any("sdk" in key.lower() for key in value))
            with patch("ci.products.sdk_runtime_content.verify_runtime_bootstrap_content") as gate:
                _verify_bootstrap_handoff(root / "uncreated-private-handoff")
                gate.assert_called_once_with(*[root / "uncreated-private-handoff" / name for name in
                                               ("bootstrap", "bootstrap-reference", "contract", "sdks/macos-arm64")])
            library = paths[3] / "lib/libcodex_agent.dylib"
            library.write_bytes(b"tampered Runtime library")
            with self.assertRaisesRegex(ValueError, "releaseLibrarySha256"):
                verify_runtime_bootstrap_content(*paths)

    def test_handoff_rederives_junit_and_bounded_references_not_only_recorded_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._handoff(root)
            junit = next((root / "bootstrap/native-junit").iterdir())
            junit.write_bytes(junit.read_bytes().replace(b"passed[", b"other["))
            self.report["artifacts"]["nativeTestResultsSha256"] = _execution_tree_digest(junit.parent)
            self._rebind_content(root)
            with self.assertRaisesRegex(ValueError, "exact passed native test inventory"):
                _verify_bootstrap_handoff(root)
            junit.write_bytes(junit.read_bytes().replace(b"other[", b"passed["))
            self.report["artifacts"]["nativeTestResultsSha256"] = _execution_tree_digest(junit.parent)
            source = root / "bootstrap-reference/consumer/source.c"
            source.write_bytes(b"codex_agent_fixture_suffix();\n")
            self.report["compilerConsumers"][0]["sourceSha256"] = sha256_bytes(source.read_bytes())[7:]
            self._rebind_content(root)
            with self.assertRaisesRegex(ValueError, "authenticated consumerReferences"):
                _verify_bootstrap_handoff(root)

    def test_handoff_accepts_rebound_execution_bytes_without_changing_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._handoff(root)
            original = (root / "bootstrap/bootstrap-content.json").read_bytes()
            for name, field in (("original-runner/test.kexe", "nativeTestExecutableSha256"),
                                ("original-runner/compiler-header/libcodex_agent_api.h", "generatedHeaderSha256")):
                path = root / "bootstrap" / name
                path.write_bytes(path.read_bytes() + b"another compiler envelope\n")
                self.report["artifacts"][field] = sha256_bytes(path.read_bytes())[7:]
            artifact = root / "bootstrap/consumers/fixture"
            artifact.write_bytes(b"another consumer compiler envelope\n")
            self.report["compilerConsumers"][0]["artifactSha256"] = sha256_bytes(artifact.read_bytes())[7:]
            junit = next((root / "bootstrap/native-junit").iterdir())
            junit.write_bytes(junit.read_bytes().replace(b"<testsuite>", b'<testsuite timestamp="another-run">'))
            self.report["artifacts"]["nativeTestResultsSha256"] = _execution_tree_digest(junit.parent)
            self._rebind_content(root)
            self.assertEqual(original, (root / "bootstrap/bootstrap-content.json").read_bytes())
            _verify_bootstrap_handoff(root)

    def test_handoff_rejects_mixed_native_test_producer_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self._handoff(root)
            junit = next((root / "bootstrap/native-junit").iterdir())
            classname = "macosArm64Test.io.github.codex_agent_labs.codexagent.capi.Fixture"
            junit.write_bytes(junit.read_bytes().replace(b"</testsuite>",
                f'<testcase classname="{classname}" name="second[macosArm64]"/></testsuite>'.encode()))
            self.report["nativeTests"].append({"testId": classname + "#second[macosArm64]", "status": "passed"})
            self.report["artifacts"]["nativeTestResultsSha256"] = _execution_tree_digest(junit.parent)
            self._rebind_content(root)
            with self.assertRaisesRegex(ValueError, "exact passed native test inventory"):
                _verify_bootstrap_handoff(root)


if __name__ == "__main__":
    unittest.main()
