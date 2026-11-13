"""Real Git/planner/receipt replay with explicitly simulated Java tooling only."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, git_product_versions, regular_file_inventory
from ci.products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, _upstream_record, plan_phase
from ci.products.receipt import compute_build_key, write_output_manifest
from ci.products.registry import PhaseInstanceId
from ci.products.sdk_javascript_metadata import verify_sdk_javascript_metadata_content
from ci.products.sdk_javascript_metadata_admission import (
    _CONSUMER_FILES, verify_sdk_javascript_metadata_admission,
)
from ci.products.selection import phase_git_inventory
from ci.tests import test_sdk_javascript_metadata as content_fixture
from ci.tests.product_chain_support import write_receipt


_RUN = subprocess.run


class SdkJavaScriptMetadataAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.support = content_fixture.SdkJavaScriptMetadataTest()
        self.support.setUp()
        self.addCleanup(self.support.doCleanups)
        self.root = self.support.root
        self.repository = self.root / "repository"
        self.repository.mkdir()
        for name, version in (("contract", "0.2.0"), ("runtime", "0.2.8"), ("sdk", "0.3.0")):
            path = self.repository / f"gradle/release/versions/{name}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(version + "\n")
        program = self.support.stage_paths["validation"] / "outputs/test-program"
        for name in sorted(_CONSUMER_FILES):
            payload = f"synthetic original consumer:{name}\n".encode()
            (program / name).write_bytes(payload)
            path = self.repository / "codex-agent-bindings/javascript/consumer" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.source = self.repository / "gradle/build-logic/src/main/kotlin/CrossLanguageJavaScriptBindingEvidence.kt"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"// synthetic original matcher input\n")
        self.metadata_source = self.source.with_name("CrossLanguageJavaScriptStagedMetadata.kt")
        self.metadata_source.write_bytes(b"// synthetic original staged metadata input\n")
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic JavaScript Admission")
        self.git("config", "user.email", "sdk-admission@example.invalid")
        self.git("add", ".")
        self.git("commit", "-qm", "original validation inputs")
        self.validation_commit = self.git("rev-parse", "HEAD").strip()
        self.validation_tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.plans = {}
        self.replan("validation", self.validation_commit, self.validation_tree)
        self.metadata_source.write_bytes(b"// independently produced metadata source revision\n")
        self.git("add", ".")
        self.git("commit", "-qm", "original metadata inputs")
        self.metadata_commit = self.git("rev-parse", "HEAD").strip()
        self.metadata_tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.replan("metadata", self.metadata_commit, self.metadata_tree)
        self.support.args["repository"] = self.repository
        self.support.args["policy_revision"] = self.metadata_commit
        self.after_content = lambda arguments: None

    def git(self, *arguments):
        return _RUN(["git", *arguments], cwd=self.repository, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout

    def replan(self, phase, commit, tree):
        support = self.support
        stage = support.stage_paths[phase]
        roots = {record["relativePath"].split("/")[1]: "outputs/" + record["relativePath"].split("/")[1]
                 for record in regular_file_inventory(stage) if record["relativePath"].startswith("outputs/")}
        manifest = write_output_manifest(stage, "sdk", "javascript", phase, "node", "0.3.0", roots)
        identity = PhaseInstanceId("sdk", "javascript", phase, "node")
        upstream = ([support.receipts["validation"]] if phase == "metadata" else
                    [support.receipts["package"], support.receipts["runtime"]])
        projection = {}
        if phase == "metadata":
            from ci.products.sdk_javascript_validation_phase import verify_sdk_javascript_validation_projection

            raw = support.receipt_paths["validation"].read_bytes()
            with patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation",
                       return_value=(support.receipts["validation"], raw, support.content)):
                projection["sdk_javascript_validation_projection"] = verify_sdk_javascript_validation_projection()
        plan = plan_phase(identity, inventory=phase_git_inventory(self.repository, commit, identity),
            versions=git_product_versions(self.repository, commit), upstream_receipts=upstream,
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1, **projection)
        if phase == "metadata":
            # Explicit legacy fixture recipe, not an approved production source.
            plan["inputs"]["upstreamArtifacts"] = [_upstream_record(support.receipts["validation"])]
            plan["buildKey"] = compute_build_key(product="sdk", component="javascript", phase=phase,
                                                 target="node", inputs=plan["inputs"])
        self.assertTrue(plan["inputs"]["inventory"])
        if phase == "metadata":
            self.assertIn(self.metadata_source.relative_to(self.repository).as_posix(),
                          {record["relativePath"] for record in plan["inputs"]["inventory"]})
        context = {"producer": {**support.context["producer"], "commit": commit, "tree": tree},
                   "plan_factory": lambda _identity, _upstream: plan}
        support.receipts[phase] = write_receipt(support.receipt_paths[phase], product="sdk", component="javascript",
            phase=phase, target="node", outputs=manifest["outputs"], upstream=plan["inputs"]["upstreamArtifacts"],
            context=context, version="0.3.0", version_identity="0.3.0")
        self.plans[phase] = plan

    @contextmanager
    def tooling(self, evidence, repository, public_key, **arguments):
        self.assertEqual(repository, self.repository)
        self.assertEqual(arguments["policy_revision"], self.metadata_commit)
        self.assertEqual(arguments["required_trust_domain"], "development")
        yield self.support.jar

    def process(self, command, **arguments):
        if command[0] == "git":
            return _RUN(command, **arguments)
        return self.support.process(command, **arguments)

    def content(self, **arguments):
        result = verify_sdk_javascript_metadata_content(**arguments)
        self.after_content(arguments)
        return result

    def verify(self):
        with patch("ci.products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_javascript_validation_phase.subprocess.run", self.process), \
                patch("ci.products.sdk_javascript_validation_phase._verify_sdk_javascript_validation", self.support.synthetic_validation), \
                patch("ci.products.sdk_javascript_metadata.javascript_metadata_uses_raw_validation", return_value=True), \
                patch("ci.products.sdk_javascript_metadata_admission.javascript_metadata_uses_raw_validation", return_value=True), \
                patch("ci.products.sdk_javascript_metadata_admission.verify_sdk_javascript_metadata_content", self.content):
            return verify_sdk_javascript_metadata_admission(**self.support.args)

    def test_replays_each_original_commit_and_same_private_receipts_through_real_reader(self):
        before = regular_file_inventory(self.root)
        captures = []
        def capture(arguments):
            for name, original in self.support.args.items():
                if name.endswith(("_receipt", "_stage")):
                    self.assertNotEqual(original, arguments[name])
                    if name.endswith("_receipt"):
                        self.assertEqual(original.read_bytes(), arguments[name].read_bytes())
            captures.append(arguments["metadata_stage"])
        self.after_content = capture
        receipt, raw = self.verify()
        self.assertNotEqual(self.validation_commit, self.metadata_commit)
        self.assertEqual(receipt["producer"]["commit"], self.metadata_commit)
        self.assertEqual(receipt["inputs"], self.plans["metadata"]["inputs"])
        self.assertEqual(raw, self.support.receipt_paths["metadata"].read_bytes())
        self.assertEqual(before, regular_file_inventory(self.root))
        self.assertEqual(1, len(self.support.calls))
        self.assertFalse(captures[0].exists())

    def test_dirty_checkout_is_not_original_source_authority(self):
        self.source.write_bytes(b"dirty checkout source must not be read")
        (self.repository / "gradle/release/versions/sdk.txt").write_bytes(b"9.9.9\n")
        consumer = self.repository / "codex-agent-bindings/javascript/consumer/smoke.cjs"
        consumer.write_bytes(b"dirty current source")
        self.verify()

    def test_changed_validation_source_and_missing_inventory_reject_before_tooling(self):
        program = self.support.stage_paths["validation"] / "outputs/test-program"
        path = program / "smoke.cjs"
        original = path.read_bytes()
        path.write_bytes(b"different original source")
        with self.assertRaisesRegex(ValueError, "original validation Git source"):
            self.verify()
        path.write_bytes(original)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "source inventory"):
            self.verify()
        self.assertEqual(self.support.calls, [])

    def test_wrong_original_tree_or_source_plan_rejects_before_tooling(self):
        for phase in ("validation", "metadata"):
            path = self.support.receipt_paths[phase]
            original = path.read_bytes()
            value = deepcopy(self.support.receipts[phase])
            value["producer"]["tree"] = "f" * 40
            path.write_bytes(canonical_json_bytes(value))
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, "commit/tree"):
                self.verify()
            path.write_bytes(original)
        self.metadata_source.write_bytes(b"new committed source changes original input key\n")
        self.git("add", ".")
        self.git("commit", "-qm", "different source inventory")
        value = deepcopy(self.support.receipts["metadata"])
        value["producer"].update(commit=self.git("rev-parse", "HEAD").strip(), tree=self.git("rev-parse", "HEAD^{tree}").strip())
        self.support.receipt_paths["metadata"].write_bytes(canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "producer plan"):
            self.verify()
        self.assertEqual(self.support.calls, [])

    def test_late_captured_or_original_receipt_mutation_cannot_return(self):
        for private in (True, False):
            original_path = self.support.receipt_paths["metadata"]
            original = original_path.read_bytes()
            self.after_content = lambda arguments: (
                arguments["metadata_receipt"] if private else original_path).write_bytes(b"changed after full content gate")
            with self.subTest(private=private), self.assertRaisesRegex(ValueError, "receipt changed"):
                self.verify()
            original_path.write_bytes(original)

    def test_original_sdk_version_is_read_from_exact_producer_revision(self):
        version = self.repository / "gradle/release/versions/sdk.txt"
        version.write_bytes(b"0.3.1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "different original SDK version")
        value = deepcopy(self.support.receipts["metadata"])
        value["producer"].update(commit=self.git("rev-parse", "HEAD").strip(), tree=self.git("rev-parse", "HEAD^{tree}").strip())
        self.support.receipt_paths["metadata"].write_bytes(canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "producer Git version"):
            self.verify()
        self.assertEqual(self.support.calls, [])


if __name__ == "__main__":
    unittest.main()
