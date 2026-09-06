"""Content-only fixtures: these tests do not claim actual native execution."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products.contract import build_contract_bundle
from ci.products.contract_model import _verify_extracted_contract_directory
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.sdk_runtime_content import bootstrap_content
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


if __name__ == "__main__":
    unittest.main()
