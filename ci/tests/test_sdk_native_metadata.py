"""Native metadata orchestration checks; mocked tooling is not full host evidence."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.plan import _upstream_record
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS
from ci.products.sdk_inputs import REQUEST_NAME
from ci.products.sdk_native_metadata import verify_sdk_native_metadata_content
from ci.products.sdk_package import native_metadata_content
from ci.tests.product_chain_support import write_receipt


class SdkNativeMetadataTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-metadata-test-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.counter = 0

    def fixture(self, component="python"):
        self.counter += 1
        self.root = self.base / str(self.counter)
        self.root.mkdir()
        self.context = {"producer": {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local", "runId": None,
            "runAttempt": None, "pullRequest": None}}
        self.component = component
        self.args = dict(repository=self.root, component=component, policy_revision="a" * 40,
            required_trust_domain="development", tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "public.pub", java_executable=self.root / "jdk/java",
            compatibility_request=self.root / "request.json", runtime_stages=self.root / "runtime",
            staged_sdks=self.root / "sdks", validation_stages=self.root / "validations",
            validation_receipts=self.root / "validation-receipts", metadata_stage=self.root / "metadata",
            metadata_receipt=self.root / "metadata.json", package_stage=self.root / "package",
            package_receipt=self.root / "package.json")
        for path in (self.args["java_executable"], self.args["compatibility_request"],
                     self.args["runtime_stages"] / "original", self.args["staged_sdks"] / "original"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic original bytes\n")
        self.request_source = self.root / "original-k-r"
        self.request_source.write_bytes(b"synthetic original K/R, not executed\n")
        self.package = self.phase("package", "desktop", self.args["package_stage"], self.args["package_receipt"])
        self.upstream = [_upstream_record(self.package)]
        contents = self.root / "host-contents"
        contents.mkdir()
        for target in sorted(NATIVE_TARGETS):
            receipt_path = self.args["validation_receipts"] / f"{target}.json"
            receipt = self.phase("validation", target, self.args["validation_stages"] / target, receipt_path)
            names = {"claims.tsv", "compiler-evidence.tsv", "executed-tests.tsv", "installed.tsv", "test-program-source"}
            if component == "cpp":
                names.add("package-negative-source.py")
            cases = [{"caseId": case, "expectedExit": "zero" if case == "baseline" else "nonzero", "result": "passed"}
                     for case in sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                                         "missing-sidecar", "missing-loader"))] if component == "cpp" else []
            host = {"schemaVersion": 2, "kind": "sdk-native-validation-content", "component": component,
                "target": target, "sdkVersion": "0.2.0", "packageOutputsDigest": output_inventory_digest(self.package["outputs"]),
                **{name: sha256_bytes(name.encode()) for name in ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")},
                "files": [{"relativePath": name, "bytes": 1, "sha256": sha256_bytes(name.encode())} for name in sorted(names)],
                "packageNegativeCases": cases}
            (contents / f"{target}.json").write_bytes(canonical_json_bytes(host))
            self.upstream.append(_upstream_record(receipt, semantic_projection={"schemaVersion": 1,
                "kind": "sdk-native-validation-content", "sha256": sha256_bytes(canonical_json_bytes(host)),
                "receiptSha256": sha256_bytes(receipt_path.read_bytes())}))
        self.content = canonical_json_bytes(native_metadata_content(contents, self.args["package_receipt"], component))
        output = self.args["metadata_stage"] / "outputs/evidence/native-metadata.json"
        output.parent.mkdir(parents=True)
        output.write_bytes(self.content)
        self.rewrite_metadata()
        self.calls = []
        self.mutate = lambda fields: None

    def phase(self, phase, target, stage, receipt):
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/original").write_bytes(f"synthetic {phase}/{target}\n".encode())
        manifest = write_output_manifest(stage, "sdk", self.component, phase, target, "0.2.0", {"evidence": "outputs"})
        return write_receipt(receipt, product="sdk", component=self.component, phase=phase, target=target,
            version="0.2.0", version_identity="0.2.0", upstream=[], context=self.context, outputs=manifest["outputs"])

    def rewrite_metadata(self, *, upstream=None, kind="native-wrapper-metadata"):
        manifest = write_output_manifest(self.args["metadata_stage"], "sdk", self.component, "metadata", "desktop",
                                         "0.2.0", {kind: "outputs/evidence"})
        return write_receipt(self.args["metadata_receipt"], product="sdk", component=self.component, phase="metadata",
            target="desktop", version="0.2.0", version_identity="0.2.0", context=self.context,
            upstream=self.upstream if upstream is None else upstream, outputs=manifest["outputs"])

    @contextmanager
    def tooling(self, evidence, repository, public_key, **policy):
        self.assertEqual(self.args["tooling_evidence"], evidence)
        self.assertEqual(self.args["policy_revision"], policy["policy_revision"])
        self.assertEqual("development", policy["required_trust_domain"])
        yield self.root / "synthetic-authenticated.jar"

    def capture_inputs(self, request, output, *, request_directory):
        self.assertNotEqual(request, self.args["compatibility_request"])
        self.assertEqual(self.args["compatibility_request"].read_bytes(), request.read_bytes())
        self.assertEqual(self.args["compatibility_request"].parent, request_directory)
        output.mkdir()
        (output / REQUEST_NAME).write_bytes(b"synthetic private request\n")
        (output / "original-diagnostics.bin").write_bytes(b"")

    def execute(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.args["java_executable"]), "-jar", str(self.root / "synthetic-authenticated.jar"),
                          "write-native-wrapper-metadata-content"], command[:4])
        fields = dict(zip(command[4::2], command[5::2]))
        self.assertEqual(self.component, fields.pop("--language"))
        self.assertEqual("0.2.0", fields.pop("--sdk-version"))
        fields = {name: Path(path) for name, path in fields.items()}
        for argument, original in (("package-stage", "package_stage"), ("package-receipt", "package_receipt"),
                ("runtime-stages", "runtime_stages"), ("staged-sdks", "staged_sdks"),
                ("validation-stages", "validation_stages"), ("validation-receipts", "validation_receipts")):
            self.assertNotEqual(self.args[original], fields[f"--{argument}"])
        self.assertEqual(sorted(NATIVE_TARGETS), sorted(path.name for path in fields["--validation-stages"].iterdir()))
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        self.mutate(fields)
        fields["--content-output"].write_bytes(self.content)
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **overrides):
        with patch("ci.products.sdk_native_metadata.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_native_metadata.stage_sdk_inputs", self.capture_inputs), \
                patch("ci.products.sdk_native_metadata._request_inventory", side_effect=lambda _: {
                    self.request_source: sha256_bytes(self.request_source.read_bytes())}), \
                patch("ci.products.sdk_native_metadata.subprocess.run", side_effect=self.execute):
            return verify_sdk_native_metadata_content(**{**self.args, **overrides})

    def test_all_five_languages_preserve_exact_original_receipts_and_bytes(self):
        for component in NATIVE_BINDINGS:
            with self.subTest(component=component):
                self.fixture(component)
                before = regular_file_inventory(self.root)
                receipt, original = self.verify()
                self.assertEqual(original, self.args["metadata_receipt"].read_bytes())
                self.assertEqual(receipt, load_canonical_json_bytes(original))
                self.assertEqual(before, regular_file_inventory(self.root))
                self.assertEqual(1, len(self.calls))

    def test_missing_and_extra_host_closure_reject_before_tooling(self):
        for extra in (False, True):
            self.fixture()
            if extra:
                (self.args["validation_receipts"] / "extra.json").write_bytes(b"extra")
            else:
                (self.args["validation_receipts"] / f"{NATIVE_TARGETS[0]}.json").unlink()
            with self.assertRaisesRegex(ValueError, "exactly five"):
                self.verify()
            self.assertEqual([], self.calls)

    def test_wrong_metadata_kind_extra_output_and_false_content_reject(self):
        for mutation in ("kind", "extra", "content"):
            self.fixture()
            if mutation == "extra":
                (self.args["metadata_stage"] / "outputs/evidence/extra.json").write_bytes(b"extra")
            if mutation == "content":
                (self.args["metadata_stage"] / "outputs/evidence/native-metadata.json").write_bytes(b"false content\n")
            self.rewrite_metadata(kind="evidence" if mutation == "kind" else "native-wrapper-metadata")
            before = regular_file_inventory(self.root)
            with self.assertRaises(ValueError):
                self.verify()
            self.assertEqual(before, regular_file_inventory(self.root))

    def test_original_package_host_and_semantic_upstream_binding_is_exact(self):
        for index, field in ((0, "outputsDigest"), (1, "outputsDigest"), (1, "receiptSha256"), (1, "sha256")):
            self.fixture()
            upstream = deepcopy(self.upstream)
            target = upstream[index]["semanticProjection"] if field in {"receiptSha256", "sha256"} else upstream[index]
            target[field] = "sha256:" + "f" * 64
            self.rewrite_metadata(upstream=upstream)
            with self.assertRaisesRegex(ValueError, "exact original package and five host"):
                self.verify()

    def test_full_matcher_failure_never_accepts_existing_content(self):
        self.fixture()
        def fail(_):
            raise subprocess.CalledProcessError(1, ["synthetic full matcher"], stderr=b"missing capability")
        self.mutate = fail
        before = regular_file_inventory(self.root)
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify()
        self.assertEqual(before, regular_file_inventory(self.root))

    def test_original_private_and_java_mutations_are_rejected(self):
        for which in ("original-runtime", "private-runtime", "receipt", "request", "compatibility", "java", "k-r"):
            self.fixture()
            def mutate(fields):
                path = {"original-runtime": self.args["runtime_stages"] / "original",
                    "private-runtime": fields["--runtime-stages"] / "original",
                    "receipt": fields["--package-receipt"], "request": self.args["compatibility_request"],
                    "compatibility": fields["--compatibility-request"], "java": self.args["java_executable"],
                    "k-r": self.request_source}[which]
                path.write_bytes(path.read_bytes() + b"changed")
            self.mutate = mutate
            with self.subTest(which=which), self.assertRaisesRegex(ValueError, "changed"):
                self.verify()

    def test_symbolic_parent_and_missing_policy_reject_before_execution(self):
        self.fixture()
        link = self.root / "link"
        link.symlink_to(self.args["runtime_stages"], target_is_directory=True)
        with self.assertRaises(ValueError):
            self.verify(runtime_stages=link)
        with self.assertRaises(ValueError):
            self.verify(policy_revision=None)
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()
