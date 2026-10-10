"""Reader orchestration only: tooling/process mocks do not establish JS parity.

The separate real standalone JAR tests exercise the full matcher. Here real
receipt/manifest readers and private captures bind those invocation arguments.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory
from ci.products.plan import _upstream_record
from ci.products.receipt import write_output_manifest
from ci.products.sdk_javascript_metadata import (
    javascript_metadata_uses_raw_validation, verify_sdk_javascript_metadata_content,
)
from ci.tests.product_chain_support import write_receipt


class SdkJavaScriptMetadataTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="javascript-metadata-reader-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.content = b'{"syntheticFullToolingOutput":true}\n'
        self.context = {"producer": {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local", "runId": None,
            "runAttempt": None, "pullRequest": None}}
        self.args = dict(repository=self.root, tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "tooling.pub", java_executable=self.root / "jdk/java",
            policy_revision="a" * 40, required_trust_domain="development",
            original_consumer_directory=Path("/authenticated/original/codex-agent-sdk/build/npm/consumer"))
        self.args["java_executable"].parent.mkdir()
        self.args["java_executable"].write_bytes(b"synthetic trusted Java boundary")
        self.args["tooling_evidence"].mkdir()
        self.args["tooling_public_key"].write_bytes(b"synthetic tooling policy boundary")
        self.jar = self.root / "captured-tooling.jar"
        self.jar.write_bytes(b"synthetic JAR boundary")
        self.receipts = {}
        self.stage_paths = {}
        self.receipt_paths = {}
        self.phase("contract", ("contract", "contract", "binary", "common"), "0.2.0", [],
                   {"evidence/canonical-api.json": b"original API", "evidence/canonical-coverage.json": b"original coverage"})
        self.phase("runtime", ("runtime", "node-js", "validation", "node-js-binding"), "0.2.7", [],
                   {"test-program/program.mjs": b"original compiled Runtime program",
                    "test-report/TEST-jsNodeTest.CodexNodeApiTest.xml": b"original Runtime JUnit"})
        self.phase("package", ("sdk", "javascript", "package", "node"), "0.3.0", [],
                   {"package/codex-agent-0.3.0.tgz": b"original archive"})
        self.phase("validation", ("sdk", "javascript", "validation", "node"), "0.3.0",
                   [_upstream_record(self.receipts[name]) for name in ("package", "runtime")],
                   {"binding-evidence/javascript-typescript-parity.json": self.content,
                    "compiler-evidence/public-api.json": b"original compiler report",
                    "test-program/smoke.cjs": b"original consumer source",
                    "test-report/packed-tests.xml": b"original SDK JUnit",
                    "execution/typescript-execution.json": canonical_json_bytes({"stdoutBase64": "/wANCg==", "stderrBase64": ""}),
                    "execution/packed-consumer-execution.json": canonical_json_bytes({"stdoutBase64": "", "stderrBase64": ""})})
        self.phase("metadata", ("sdk", "javascript", "metadata", "node"), "0.3.0",
                   [_upstream_record(self.receipts["validation"])],
                   {"binding-evidence/javascript-typescript-parity.json": self.content})
        for name in self.stage_paths:
            argument = "runtime_validation" if name == "runtime" else name
            self.args[f"{argument}_stage"] = self.stage_paths[name]
            self.args[f"{argument}_receipt"] = self.receipt_paths[name]
        self.calls = []
        self.mutate = lambda fields: None
        self.exit_hook = lambda: None

    def phase(self, name, identity, version, upstream, files):
        stage = self.root / name
        for relative, content in files.items():
            target = stage / "outputs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        roots = {relative.split("/")[0]: f"outputs/{relative.split('/')[0]}" for relative in files}
        manifest = write_output_manifest(stage, *identity, version, roots)
        receipt_path = self.root / "receipts" / f"{name}.json"
        receipt = write_receipt(receipt_path, product=identity[0], component=identity[1],
            phase=identity[2], target=identity[3], outputs=manifest["outputs"], upstream=upstream, context=self.context,
            version=version, version_identity="0.2.0" if name == "runtime" else version)
        self.receipts[name], self.stage_paths[name], self.receipt_paths[name] = receipt, stage, receipt_path

    def rewrite(self, name, *, upstream=None, version=None, outputs=None):
        receipt = self.receipts[name]
        identity = tuple(receipt[field] for field in ("product", "component", "phase", "target"))
        self.receipts[name] = write_receipt(self.receipt_paths[name], product=identity[0], component=identity[1],
            phase=identity[2], target=identity[3], outputs=receipt["outputs"] if outputs is None else outputs,
            upstream=receipt["inputs"]["upstreamArtifacts"] if upstream is None else upstream, context=self.context,
            version=version or receipt["productVersion"],
            version_identity=receipt["inputs"]["versionIdentity"] if version is None else version)

    @contextmanager
    def tooling(self, evidence, repository, key, **kwargs):
        self.assertEqual((evidence, repository, key),
                         (self.args["tooling_evidence"], self.root, self.args["tooling_public_key"]))
        self.assertEqual(kwargs, dict(required_trust_domain="development", keyring=None,
            keys_directory=None, policy_revision="a" * 40))
        yield self.jar
        self.exit_hook()

    def process(self, command, **kwargs):
        self.assertEqual(command[:4], [str(self.args["java_executable"]), "-jar", str(self.jar),
                                     "write-javascript-metadata-content"])
        fields = dict(zip(command[4::2], command[5::2]))
        self.calls.append(fields)
        self.assertEqual(fields["--original-consumer-directory"], str(self.args["original_consumer_directory"]))
        self.assertEqual((fields["--contract-version"], fields["--sdk-version"], fields["--runtime-version"]),
                         ("0.2.0", "0.3.0", "0.2.7"))
        private = kwargs["cwd"]
        self.assertNotEqual(private, self.root)
        self.assertTrue(kwargs["check"])
        self.assertEqual((kwargs["stdout"], kwargs["stderr"]), (subprocess.PIPE, subprocess.PIPE))
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        for name, flag in (("contract", "contract-stage"), ("package", "package-stage"),
                           ("validation", "validation-stage"), ("runtime", "runtime-validation-stage")):
            captured = Path(fields[f"--{flag}"])
            self.assertEqual(captured.parent, private)
            self.assertEqual(regular_file_inventory(captured), regular_file_inventory(self.stage_paths[name]))
        for name, path in self.projected_receipts.items():
            self.assertEqual(path.read_bytes(), self.receipt_paths[name].read_bytes())
        Path(fields["--content-output"]).write_bytes(self.content)
        self.mutate(fields)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def verify(self, *, fixture_legacy=True, **overrides):
        with patch("ci.products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_javascript_validation_phase.subprocess.run", self.process), \
                patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation", self.synthetic_validation), \
                patch("ci.products.sdk_javascript_metadata.javascript_metadata_uses_raw_validation", return_value=fixture_legacy):
            return verify_sdk_javascript_metadata_content(**{**self.args, **overrides})

    def test_semantic_metadata_edge_requires_opaque_original_validation_view(self):
        from ci.products.sdk_javascript_validation_phase import verify_sdk_javascript_validation_projection

        raw = self.receipt_paths["validation"].read_bytes()
        with patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation",
                   return_value=(self.receipts["validation"], raw, self.content)):
            proof = verify_sdk_javascript_validation_projection()
        with self.assertRaisesRegex(ValueError, "authenticated validation view"):
            self.verify(fixture_legacy=False)
        self.rewrite("metadata", upstream=[proof.upstream_record(self.receipts["validation"])])
        receipt, original = self.verify(fixture_legacy=False)
        self.assertEqual(original, self.receipt_paths["metadata"].read_bytes())
        self.assertEqual(receipt["inputs"]["upstreamArtifacts"], [proof.upstream_record(self.receipts["validation"])])

    def test_legacy_recipe_is_limited_to_exact_preserved_reviewed_source(self):
        receipt = deepcopy(self.receipts["metadata"])
        self.assertFalse(javascript_metadata_uses_raw_validation(receipt))
        receipt["productVersion"] = "0.8.0"
        receipt["producer"].update(repository="codex-agent-labs/codex-agent",
            commit="e5746e17f5fd2354cbdab9c0e6f27731ed68a6b7", tree="945047e23f5cb6371f36a85f7d41808d7c880944")
        self.assertTrue(javascript_metadata_uses_raw_validation(receipt))
        receipt["producer"]["tree"] = "f" * 40
        self.assertFalse(javascript_metadata_uses_raw_validation(receipt))

    def synthetic_validation(self, **arguments):
        """Mock full-verifier boundary only; never genuine projection evidence."""
        from ci.products import sdk_javascript_validation_phase as verifier

        fields = {name: arguments[f"{name}_stage"] for name in ("contract", "package", "validation")}
        fields["runtime"] = arguments["runtime_validation_stage"]
        self.projected_receipts = {name: arguments[f"{name}_receipt"]
                                  for name in ("contract", "package", "validation")}
        self.projected_receipts["runtime"] = arguments["runtime_validation_receipt"]
        before = {name: regular_file_inventory(path) for name, path in fields.items()}
        raw = {name: path.read_bytes() for name, path in self.projected_receipts.items()}
        private = arguments["validation_stage"].parent
        output = private / "replayed.json"
        with verifier.verified_tooling_capture(arguments["tooling_evidence"], arguments["repository"],
                arguments["tooling_public_key"], required_trust_domain=arguments["required_trust_domain"],
                keyring=arguments.get("tooling_keyring"), keys_directory=arguments.get("tooling_keys_directory"),
                policy_revision=arguments["policy_revision"]) as jar:
            options = {"contract-stage": fields["contract"], "package-stage": fields["package"],
                "validation-stage": fields["validation"], "runtime-validation-stage": fields["runtime"],
                "original-consumer-directory": arguments["original_consumer_directory"],
                "contract-version": "0.2.0", "sdk-version": "0.3.0", "runtime-version": "0.2.7",
                "content-output": output}
            command = [str(arguments["java_executable"]), "-jar", str(jar), "write-javascript-metadata-content"]
            command += [part for name, value in options.items() for part in (f"--{name}", str(value))]
            verifier.subprocess.run(command, cwd=private, env={}, check=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if (any(regular_file_inventory(path) != before[name] for name, path in fields.items())
                or any(path.read_bytes() != raw[name] for name, path in self.projected_receipts.items())):
            raise ValueError("Synthetic verifier inputs changed during replay")
        content = output.read_bytes()
        if content != (fields["validation"] / "outputs/binding-evidence/javascript-typescript-parity.json").read_bytes():
            raise ValueError("JavaScript validation differs from the full authenticated replay")
        return load_canonical_json_bytes(raw["validation"]), raw["validation"], content

    def test_exact_original_receipts_private_stages_versions_and_raw_bytes(self):
        before = regular_file_inventory(self.root)
        with patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "not forwarded"}):
            receipt, raw = self.verify()
        self.assertEqual(receipt, self.receipts["metadata"])
        self.assertEqual(raw, self.receipt_paths["metadata"].read_bytes())
        self.assertEqual(before, regular_file_inventory(self.root))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(Path(self.calls[0]["--contract-stage"]).exists())

    def test_exact_dependency_records_are_required_before_tooling(self):
        for name in ("metadata", "validation"):
            original = self.receipt_paths[name].read_bytes()
            original_value = deepcopy(self.receipts[name])
            upstream = deepcopy(original_value["inputs"]["upstreamArtifacts"])
            upstream[0]["outputsDigest"] = "sha256:" + "f" * 64
            self.rewrite(name, upstream=upstream)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "does not bind"):
                self.verify()
            self.receipt_paths[name].write_bytes(original)
            self.receipts[name] = original_value
        self.assertEqual(self.calls, [])

    def test_inventory_semantic_output_and_identity_fail_closed(self):
        path = self.stage_paths["metadata"] / "outputs/binding-evidence/javascript-typescript-parity.json"
        original = path.read_bytes()
        path.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.verify()
        path.write_bytes(original)
        self.mutate = lambda fields: Path(fields["--content-output"]).write_bytes(b"wrong replay")
        with self.assertRaisesRegex(ValueError, "differs from the full"):
            self.verify()

    def test_metadata_requires_exact_sole_output_kind_and_common_sdk_version(self):
        stage = self.stage_paths["metadata"]
        manifest_path = stage / "output-manifest.json"
        original_manifest = manifest_path.read_bytes()
        original_receipt = self.receipt_paths["metadata"].read_bytes()
        original_value = deepcopy(self.receipts["metadata"])
        extra = stage / "outputs/binding-evidence/extra.json"
        for case in ("kind", "extra", "version"):
            with self.subTest(case=case):
                if case == "extra":
                    extra.write_bytes(b"extra product")
                version = "0.3.1" if case == "version" else "0.3.0"
                kind = "unexpected" if case == "kind" else "binding-evidence"
                manifest = write_output_manifest(stage, "sdk", "javascript", "metadata", "node", version,
                                                 {kind: "outputs/binding-evidence"})
                self.rewrite("metadata", outputs=manifest["outputs"], version=version)
                with self.assertRaisesRegex(ValueError, "sole exact|SDK versions differ"):
                    self.verify()
                extra.unlink(missing_ok=True)
                manifest_path.write_bytes(original_manifest)
                self.receipt_paths["metadata"].write_bytes(original_receipt)
                self.receipts["metadata"] = deepcopy(original_value)
        self.assertEqual(self.calls, [])

    def test_original_private_receipt_stage_and_java_mutations_fail(self):
        mutations = (
            lambda fields: (Path(fields["--contract-stage"]) / "outputs/evidence/canonical-api.json").write_bytes(b"mutated"),
            lambda fields: self.stage_paths["runtime"].joinpath("outputs/test-program/program.mjs").write_bytes(b"mutated"),
            lambda fields: self.receipt_paths["package"].write_bytes(b"mutated"),
            lambda fields: (Path(fields["--content-output"]).parent / "receipts/metadata.json").write_bytes(b"mutated"),
            lambda fields: self.args["java_executable"].write_bytes(b"mutated"),
        )
        for mutation in mutations:
            originals = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
            self.mutate = mutation
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.verify()
            for path, data in originals.items():
                path.write_bytes(data)

    def test_tooling_context_exit_mutation_and_process_failure_do_not_return(self):
        self.exit_hook = lambda: self.receipt_paths["contract"].write_bytes(b"late mutation")
        with self.assertRaisesRegex(ValueError, "receipt changed"):
            self.verify()
        self.exit_hook = lambda: None
        self.receipt_paths["contract"].write_bytes(canonical_json_bytes(self.receipts["contract"]))
        with patch("ci.products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_javascript_validation_phase.subprocess.run", side_effect=subprocess.CalledProcessError(1, "java")), \
                patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation", self.synthetic_validation), \
                patch("ci.products.sdk_javascript_metadata.javascript_metadata_uses_raw_validation", return_value=True):
            with self.assertRaises(subprocess.CalledProcessError):
                verify_sdk_javascript_metadata_content(**self.args)

    def test_caller_paths_policy_and_missing_original_are_rejected(self):
        for overrides in ({"original_consumer_directory": Path("relative")},
                          {"policy_revision": "main"}, {"java_executable": Path("java")},
                          {"validation_stage": self.stage_paths["package"]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.verify(**overrides)
        self.stage_paths["validation"].joinpath("outputs/execution/typescript-execution.json").unlink()
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
