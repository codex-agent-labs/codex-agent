"""Synthetic structural projection tests, not Apple compiler/host acceptance."""

from copy import deepcopy
from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_file
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products import sdk_apple_validation_content as content_module
from ci.products.sdk_apple_validation_content import apple_validation_content, main, write_apple_validation_content
from ci.tests.test_products import sdk_compatibility


class AppleValidationContentTest(unittest.TestCase):
    def setUp(self):
        canonical = {"apiReportSha256": "a" * 64, "coverageReceiptSha256": "b" * 64}
        scenarios = sorted((
            "async-success", "async-failure", "cancellation", "state-current-value",
            "state-subsequent-value", "subscription-cancellation", "terminal-delivery",
            "structured-failure", "identity", "parent-child-ownership", "repeated-close-dispose",
            "nullability", "collection-immutability-ordering", "value-conversion",
        ))
        self.arguments = dict(
            target="ios-simulator-arm64", sdk_version="0.8.0",
            package_outputs_digest="sha256:" + "c" * 64, contract_digest="sha256:" + "d" * 64,
            expected_canonical=canonical, binding_receipts={},
        )
        for language in ("objective-c", "swift"):
            self.arguments["binding_receipts"][language] = {
                "schema": 4, "result": "passed", "phase": "M8", "language": language,
                "canonical": dict(canonical),
                "artifacts": [{"id": name, "sha256": "e" * 64} for name in (
                    "apple-binding-evidence", "apple-compiler-evidence", "apple-xctest-evidence",
                    "codex-agent-xcframework",
                )],
                "hostConsumerProofs": [], "testProgramSha256": "f" * 64,
                "testResultsSha256": "1" * 64, "publicSymbols": ["symbol-a", "symbol-b"],
                "tests": [{"id": "test-a", "status": "passed"}],
                "scenarios": [{"id": name, "testIds": ["test-a"]} for name in scenarios],
                "claims": [{"capabilityKey": "capability-a", "publicSymbols": ["symbol-a"],
                            "executedTests": ["test-a"], "sharedScenarios": ["identity"]}],
                "exclusions": [],
            }

    def test_exact_projection_and_independent_return_for_both_targets(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                arguments = deepcopy(self.arguments)
                arguments["target"] = target
                original = deepcopy(arguments)
                content = apple_validation_content(**arguments)
                self.assertEqual(set(content), {
                    "schemaVersion", "kind", "component", "target", "sdkVersion",
                    "packageOutputsDigest", "contractDigest", "canonical", "bindings",
                })
                self.assertEqual(content["schemaVersion"], 1)
                self.assertEqual(content["kind"], "sdk-apple-validation-content")
                self.assertEqual(content["component"], "sdk-ios")
                self.assertEqual(content["target"], target)
                self.assertEqual(content["sdkVersion"], "0.8.0")
                self.assertEqual(content["canonical"], arguments["expected_canonical"])
                for row in content["bindings"]:
                    self.assertEqual(set(row), {
                        "phase", "language", "publicSymbols", "tests", "scenarios", "claims", "exclusions",
                    })
                self.assertEqual([r["language"] for r in content["bindings"]], ["objective-c", "swift"])
                self.assertEqual(arguments, original)
                content["canonical"]["apiReportSha256"] = "9" * 64
                content["bindings"][0]["claims"].clear()
                self.assertEqual(arguments, original)

    def test_different_original_execution_hashes_have_identical_content(self):
        baseline = canonical_json_bytes(apple_validation_content(**self.arguments))
        for receipt in self.arguments["binding_receipts"].values():
            receipt["testResultsSha256"] = "3" * 64
            for artifact in receipt["artifacts"]:
                if artifact["id"] != "codex-agent-xcframework":
                    artifact["sha256"] = "4" * 64
        self.assertEqual(canonical_json_bytes(apple_validation_content(**self.arguments)), baseline)

    def test_contract_package_and_semantic_changes_change_content(self):
        baseline = canonical_json_bytes(apple_validation_content(**self.arguments))
        for field, value in (("contract_digest", "sha256:" + "5" * 64),
                             ("package_outputs_digest", "sha256:" + "6" * 64),
                             ("sdk_version", "0.8.1")):
            with self.subTest(field=field):
                arguments = deepcopy(self.arguments)
                arguments[field] = value
                self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)
        arguments = deepcopy(self.arguments)
        arguments["binding_receipts"]["swift"]["claims"][0]["publicSymbols"] = ["symbol-b"]
        self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)
        arguments = deepcopy(self.arguments)
        arguments["expected_canonical"]["apiReportSha256"] = "7" * 64
        for receipt in arguments["binding_receipts"].values():
            receipt["canonical"]["apiReportSha256"] = "7" * 64
        self.assertNotEqual(canonical_json_bytes(apple_validation_content(**arguments)), baseline)

    def test_both_receipts_must_match_independent_expected_canonical(self):
        for language in ("objective-c", "swift"):
            for field in ("apiReportSha256", "coverageReceiptSha256"):
                with self.subTest(language=language, field=field):
                    arguments = deepcopy(self.arguments)
                    arguments["binding_receipts"][language]["canonical"][field] = "8" * 64
                    with self.assertRaisesRegex(ValueError, "caller-owned canonical"):
                        apple_validation_content(**arguments)

    def test_unknown_missing_or_malformed_receipt_semantics_reject(self):
        mutations = (
            lambda r: r.update(schema=True), lambda r: r.update(schema=5),
            lambda r: r.update(result="failed"), lambda r: r.update(phase="M11"),
            lambda r: r.update(language="kotlin"), lambda r: r.update(extra="unknown"),
            lambda r: r.pop("claims"), lambda r: r.update(claims=[]),
            lambda r: r["canonical"].update(extra="unknown"),
            lambda r: r["artifacts"].pop(), lambda r: r["artifacts"][0].update(sha256="bad"),
            lambda r: r.update(testResultsSha256="sha256:" + "a" * 64),
            lambda r: r.update(hostConsumerProofs=[{}]), lambda r: r.update(exclusions=[{}]),
            lambda r: r["publicSymbols"].reverse(), lambda r: r["publicSymbols"].append("symbol-b"),
            lambda r: r["tests"][0].update(status="failed"),
            lambda r: r["tests"][0].update(extra="unknown"),
            lambda r: r["scenarios"].pop(), lambda r: r["scenarios"][0].update(testIds=["unknown"]),
            lambda r: r["claims"][0].update(executedTests=["unknown"]),
            lambda r: r["claims"][0].update(sharedScenarios=["unknown"]),
            lambda r: r["claims"][0].update(publicSymbols=["unknown"]),
            lambda r: r["claims"][0].update(capabilityKey="*"),
            lambda r: r["claims"][0].update(extra="unknown"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                arguments = deepcopy(self.arguments)
                mutate(arguments["binding_receipts"]["swift"])
                with self.assertRaises(ValueError):
                    apple_validation_content(**arguments)

    def test_caller_schema_and_identity_fail_closed(self):
        for field, value in (
            ("target", "macos-arm64"), ("sdk_version", "latest"), ("contract_digest", "bad"),
            ("package_outputs_digest", "a" * 64), ("expected_canonical", {}),
            ("expected_canonical", {"apiReportSha256": "A" * 64, "coverageReceiptSha256": "b" * 64}),
            ("binding_receipts", {}),
        ):
            with self.subTest(field=field, value=value):
                arguments = deepcopy(self.arguments)
                arguments[field] = value
                with self.assertRaises(ValueError):
                    apple_validation_content(**arguments)


class AppleValidationContentFileTest(unittest.TestCase):
    """Real structural files only; no semantic/signature/host acceptance claim."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-validation-content-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        fixture = AppleValidationContentTest()
        fixture.setUp()
        self.receipts = fixture.arguments["binding_receipts"]
        self.paths = {name: self.root / f"{name}.json" for name in (
            "sdk_compatibility", "canonical_api", "canonical_coverage", "swift_receipt", "objective_c_receipt")}
        self.paths["canonical_api"].write_bytes(b'{ "canonical": "API bytes, not semantic digest" }\n')
        self.paths["canonical_coverage"].write_bytes(b'{ "coverage": "original" }\n')
        self.canonical = {
            "apiReportSha256": sha256_file(self.paths["canonical_api"]).removeprefix("sha256:"),
            "coverageReceiptSha256": sha256_file(self.paths["canonical_coverage"]).removeprefix("sha256:"),
        }
        for language, name in (("swift", "swift_receipt"), ("objective-c", "objective_c_receipt")):
            self.receipts[language]["canonical"] = dict(self.canonical)
            self.paths[name].write_bytes(canonical_json_bytes(self.receipts[language]))
        self.compatibility = sdk_compatibility()
        self.compatibility["sdkVersion"] = "0.8.0"
        self.paths["sdk_compatibility"].write_bytes(canonical_json_bytes(self.compatibility))
        self.stage = self.root / "package"
        (self.stage / "outputs/apple").mkdir(parents=True)
        (self.stage / "outputs/apple/package.zip").write_bytes(b"synthetic package bytes\n")
        self.manifest = write_output_manifest(self.stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                                              {"apple": "outputs/apple"})
        self.output = self.root / "new/content.json"
        self.arguments = dict(target="ios-arm64", sdk_version="0.8.0", package_stage=self.stage,
                              output=self.output, **self.paths)

    def argv(self):
        return [argument for key, value in self.arguments.items()
                for argument in ("--" + key.replace("_", "-"), str(value))]

    def test_cli_writes_only_exact_canonical_content_using_original_digests(self):
        before = regular_file_inventory(self.root)
        self.assertEqual(0, main(self.argv()))
        content = load_canonical_json_bytes(self.output.read_bytes())
        self.assertEqual(self.canonical, content["canonical"])
        self.assertEqual(output_inventory_digest(self.manifest["outputs"]), content["packageOutputsDigest"])
        self.assertEqual(self.compatibility["contract"]["digest"], content["contractDigest"])
        self.assertEqual(canonical_json_bytes(content), self.output.read_bytes())
        after = regular_file_inventory(self.root)
        self.assertEqual(before, [row for row in after if row["relativePath"] != "new/content.json"])
        self.assertEqual(["content.json"], [path.name for path in self.output.parent.iterdir()])

    def test_invalid_identity_compatibility_and_receipt_never_publish(self):
        for key, value in (("target", "desktop"), ("sdk_version", "0.8.1")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                write_apple_validation_content(**{**self.arguments, key: value})
            self.assertFalse(self.output.exists())
        compatibility = self.paths["sdk_compatibility"]
        original = compatibility.read_bytes()
        for value in ({**self.compatibility, "sdkVersion": "0.8.1"},
                      {**self.compatibility, "unexpected": "field"}):
            compatibility.write_bytes(canonical_json_bytes(value))
            with self.assertRaises(ValueError):
                write_apple_validation_content(**self.arguments)
            self.assertFalse(self.output.exists())
        compatibility.write_bytes(original)
        swift = self.paths["swift_receipt"]
        original = swift.read_bytes()
        for raw in (original.replace(b'"schema":4', b'"schema":4,"schema":4'), b'\xff'):
            swift.write_bytes(raw)
            with self.assertRaises(ValueError):
                write_apple_validation_content(**self.arguments)
            self.assertFalse(self.output.exists())
        self.receipts["swift"]["canonical"]["apiReportSha256"] = "0" * 64
        swift.write_bytes(canonical_json_bytes(self.receipts["swift"]))
        with self.assertRaisesRegex(ValueError, "caller-owned canonical"):
            write_apple_validation_content(**self.arguments)
        self.assertFalse(self.output.exists())

    def test_package_inventory_tamper_rejects_before_projection(self):
        (self.stage / "outputs/apple/package.zip").write_bytes(b"tampered\n")
        with patch.object(content_module, "apple_validation_content", side_effect=AssertionError("early projection")), \
                self.assertRaises(ValueError):
            write_apple_validation_content(**self.arguments)
        self.assertFalse(self.output.exists())

    def test_overwrite_overlap_and_symlink_paths_reject_without_source_changes(self):
        existing = self.root / "existing.json"
        existing.write_bytes(b"user-owned\n")
        alias = self.root / "alias"
        alias.symlink_to(self.stage, target_is_directory=True)
        link = self.root / "output-link"
        link.symlink_to(existing)
        before = regular_file_inventory(self.stage)
        for output in (existing, link, self.stage / "new.json", self.paths["canonical_api"], alias / "new.json"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                write_apple_validation_content(**{**self.arguments, "output": output})
        self.assertEqual(b"user-owned\n", existing.read_bytes())
        self.assertEqual(before, regular_file_inventory(self.stage))
        with self.assertRaises(ValueError):
            write_apple_validation_content(**{**self.arguments, "canonical_api": link})
        self.assertFalse(self.output.exists())

    def test_mutation_during_projection_or_staging_prevents_publication(self):
        original_projection = content_module.apple_validation_content
        original_writer = content_module.write_canonical_json
        for seam in ("projection", "writer"):
            path = self.paths["canonical_coverage"]
            original = path.read_bytes()

            def project(**arguments):
                result = original_projection(**arguments)
                path.write_bytes(b"mutated original\n")
                return result

            def write(target, value):
                original_writer(target, value)
                path.write_bytes(b"mutated original\n")

            name, replacement = (("apple_validation_content", project) if seam == "projection"
                                 else ("write_canonical_json", write))
            with self.subTest(seam=seam), patch.object(content_module, name, side_effect=replacement), \
                    self.assertRaisesRegex(ValueError, "original inputs changed"):
                write_apple_validation_content(**self.arguments)
            self.assertFalse(self.output.exists())
            path.write_bytes(original)

    def test_cli_rejects_missing_abbreviated_and_override_flags_and_reports_errors(self):
        for arguments in ([], self.argv() + ["--command", "anything"],
                          ["--tar" if value == "--target" else value for value in self.argv()]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(arguments)
            self.assertEqual(2, error.exception.code)
        with patch.object(content_module, "write_apple_validation_content", side_effect=ValueError("mismatch")), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(self.argv())
        self.assertEqual(2, error.exception.code)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
