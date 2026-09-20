"""Selected caller orchestration only; mocked gates do not prove Apple acceptance."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_ios_validation_workflow as workflow


class SdkIosValidationWorkflowTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"original plan")
        self.destination = self.root / "result"
        self.package = workflow.PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        self.instance = workflow.PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
        self.ready = {"buildKey": "sha256:" + "1" * 64}
        self.receipt = dict(product="sdk", component="sdk-ios", phase="package", target="ios", productVersion="0.8.0", outputs=[])
        self.verified = SimpleNamespace(prior_ready_plans={self.instance: self.ready},
            sources={self.package: self.root / "object"},
            prior_carrier_phases={self.package: dict(buildKey="key", receiptSha256="receipt", objectSha256="object")},
            expected_fixed={"versions": {"sdk": "0.8.0"}},
            producer={"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
                      "commit": "a" * 40, "tree": "d" * 40, "event": "pull_request",
                      "runId": 104, "runAttempt": 2, "pullRequest": 7})
        self.expected_producer = dict(self.verified.producer)
        canonical = self.root / "original/inputs/contract-contract-binary-common/stage/outputs/evidence"
        canonical.mkdir(parents=True)
        for name in ("canonical-api.json", "canonical-coverage.json"):
            (canonical / name).write_bytes(b"independent Contract fixture")
        self.binary = self.root / "original/inputs/sdk-sdk-ios-binary-ios"
        (self.binary / "stage").mkdir(parents=True)
        (self.binary / "stage/framework").write_bytes(b"exact binary predecessor")
        (self.binary / "phase-receipt.json").write_bytes(b"exact binary receipt")
        self.recovered_binary = self.root / "recovered-binary"
        self.recovered_binary.mkdir()
        (self.recovered_binary / "framework").write_bytes(b"exact binary predecessor")
        self.evidence = self.root / "raw-evidence"
        (self.evidence / "reports").mkdir(parents=True)
        for language in ("swift", "objective-c"):
            (self.evidence / f"reports/{language}-parity.json").write_bytes(b"{}")
        self.captures = {}
        for name in ("package", "sdk", "binary", "native"):
            directory = self.root / "captures" / name
            (directory / "original").mkdir(parents=True)
            (directory / "original/value.bin").write_bytes(f"exact {name} original\n".encode())
            (directory / "original/stdout.bin").write_bytes(b"")
            (directory / "transport.zip").write_bytes(f"exact {name} transport\n".encode())
            self.captures[name] = directory
        self.capture_inventories = {name: workflow.regular_file_inventory(path, allow_empty=True)
                                    for name, path in self.captures.items()}
        self.events = []
        self.mutation = None
        self.arguments = dict(target="ios-arm64", expected_build_key=self.ready["buildKey"],
            package_artifact_id=17, package_artifact_sha256="sha256:" + "2" * 64,
            binary_artifact_id=18, binary_artifact_sha256="sha256:" + "5" * 64,
            rust_host="aarch64-apple-darwin",
            trusted_workflow_sha="b" * 40, keyring=self.root / "keys.json", keys_directory=self.root / "keys",
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "public",
            java_executable=self.root / "java", policy_revision="c" * 40, required_trust_domain="release",
            repository_root=self.root, environ={"DEVELOPER_DIR": "/original/Xcode"}, token="test")

    def capture(self, root, revision, output):
        self.assertEqual(self.verified.producer["commit"], revision)
        output.mkdir()
        (output / "source.txt").write_bytes(b"validation source")
        self.sources = output
        return {}

    @contextmanager
    def originals(self, plan, receipt, **arguments):
        self.assertEqual(b"original receipt", receipt.read_bytes())
        self.assertEqual(17, arguments["artifact_id"])
        self.events.append("original-enter")
        yield {"original": self.root / "original", "stage": self.root / "package",
               "receiptPath": receipt, "receipt": self.receipt, "receiptBytes": b"original receipt",
               "packageCapture": self.captures["package"], "sdkCapture": self.captures["sdk"],
               "sdk": {"directory": self.root / "sdk",
                   "compatibility": {"contract": {"digest": "sha256:" + "3" * 64}}}}
        self.events.append("original-exit")
        if self.mutation == "context":
            raise ValueError("original context changed")
        if self.mutation == "archive":
            (self.root / "raw-execution/apple-validation-evidence.zip").write_bytes(b"changed archive")
        if self.mutation == "stage-exit":
            (self.root / "stage/outputs/validation/apple-validation.json").write_bytes(b"changed content")
        if self.mutation == "retained-exit":
            (self.destination / "originals/package/original/value.bin").write_bytes(b"changed retained original")
        if self.mutation == "retained-raw-exit":
            (self.destination / "execution/apple-validation-evidence.zip").write_bytes(b"changed retained raw")
        if self.mutation == "selection-exit":
            (self.destination / "selection/phase-plan.json").write_bytes(b"changed selection")
        if self.mutation == "execution-context-exit":
            (self.destination / "context/execution-context.json").write_bytes(b"changed context")
        if self.mutation == "worker-diagnostics-exit":
            (self.destination / "worker/execution.json").write_bytes(b"changed execution diagnostics")

    @contextmanager
    def original_binary(self, plan, receipt, **arguments):
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.binary / "phase-receipt.json", receipt)
        self.assertEqual(18, arguments["artifact_id"])
        self.assertEqual("sha256:" + "5" * 64, arguments["artifact_sha256"])
        self.assertEqual(self.arguments["rust_host"], arguments["rust_host"])
        self.events.append("binary-enter")
        if self.mutation == "binary-gate":
            raise ValueError("binary native gate failed")
        if self.mutation == "binary-stage":
            (self.recovered_binary / "framework").write_bytes(b"different predecessor")
        yield {"stage": self.recovered_binary, "binaryCapture": self.captures["binary"],
               "native": {"captureRoot": self.captures["native"]}, "receiptBytes":
               b"wrong receipt" if self.mutation == "binary-receipt" else b"exact binary receipt"}
        self.events.append("binary-exit")
        if self.mutation == "binary-exit":
            raise ValueError("binary context changed")

    @contextmanager
    def archive(self, archive, **arguments):
        self.assertEqual(workflow.sha256_file(archive), arguments["expected_sha256"])
        self.assertEqual(workflow._EVIDENCE_ROOTS, arguments["expected_roots"])
        self.events.append("archive-enter")
        yield self.evidence
        self.events.append("archive-exit")
        if self.mutation == "archive-context":
            raise ValueError("archive context failed")

    def gate(self, **arguments):
        self.events.append("complete-gate")
        self.assertEqual(self.evidence, arguments["evidence_root"])
        self.assertEqual(str(self.root / "codex-agent-runtime-ios"), arguments["original_working_directory"])
        self.assertEqual(self.verified.producer["commit"], arguments["source_revision"])
        self.assertEqual(self.root / "package/outputs/apple", arguments["product_directory"])
        self.assertEqual(self.root / "original/inputs/contract-contract-binary-common/stage/outputs/evidence/canonical-api.json",
                         arguments["canonical_api"])
        if self.mutation == "gate":
            raise ValueError("full gate failed")

    def projection(self, **arguments):
        self.events.append("projection")
        self.assertIn("complete-gate", self.events)
        self.assertEqual("sha256:" + "3" * 64, arguments["contract_digest"])
        return {"synthetic": "semantic projection"}

    def worker(self, ready, **arguments):
        self.events.append("worker")
        self.assertEqual(self.ready, ready)
        self.assertEqual(self.destination / "worker", arguments["destination"])
        arguments["destination"].mkdir(parents=True)
        (arguments["destination"] / "gradle.log").write_bytes(b"original worker diagnostics\n")
        (arguments["destination"] / "execution.json").write_bytes(b"original execution diagnostics\n")
        self.assertEqual(self.sources / "codex-agent-runtime-ios/apple/TestApp", arguments["test_application"])
        self.assertEqual(self.root / "original/inputs/contract-contract-binary-common/stage",
                         arguments["contract_binary_stage"]["stage"])
        self.assertEqual(self.root / "sdk/sdk-compatibility.json", arguments["sdk_compatibility"])
        if self.mutation == "plan":
            self.plan.write_bytes(b"changed")
        elif self.mutation == "source":
            (self.sources / "source.txt").write_bytes(b"changed")
        elif self.mutation == "worker":
            raise ValueError("worker failed")
        archive = self.root / "raw-execution/apple-validation-evidence.zip"
        archive.parent.mkdir(exist_ok=True)
        archive.write_bytes(b"raw archive fixture")
        stage = self.root / "stage"
        content = stage / "outputs/validation/apple-validation.json"
        content.parent.mkdir(parents=True, exist_ok=True)
        content.write_bytes(workflow.canonical_json_bytes(
            {"synthetic": "wrong" if self.mutation == "content" else "semantic projection"}))
        return {"evidenceArchive": archive, "evidenceSha256": workflow.sha256_file(archive),
                "stage": stage, "outputInventory": workflow.regular_file_inventory(stage),
                "diagnostics": arguments["destination"]}

    def checkout(self, root, producer):
        self.assertEqual("original-exit", self.events[-1])
        self.assertIn("binary-exit", self.events)
        self.assertIn("archive-exit", self.events)
        self.assertEqual(self.root, root)
        self.assertEqual(self.expected_producer, producer)
        self.events.append("checkout")
        if self.mutation == "late-checkout":
            raise ValueError("late checkout changed")

    def finalize(self, **arguments):
        self.assertEqual("checkout", self.events[-1])
        self.assertEqual({"stage_root": self.root / "stage", "phase_plan": self.ready,
                          "producer": self.verified.producer, "product_version": "0.8.0",
                          "trust_domain": "development" if self.verified.producer["event"] == "pull_request" else "release",
                          "destination": self.destination / "shard"}, arguments)
        for name, inventory in self.capture_inventories.items():
            self.assertEqual(inventory, workflow.regular_file_inventory(
                self.destination / "originals" / name, allow_empty=True))
        self.assertEqual(b"raw archive fixture", (self.destination / "execution/apple-validation-evidence.zip").read_bytes())
        self.assertEqual({"impact-plan.json", "phase-plan.json", "producer.json"},
                         {path.name for path in (self.destination / "selection").iterdir()})
        self.assertEqual(b"original plan", (self.destination / "selection/impact-plan.json").read_bytes())
        self.assertEqual(workflow.canonical_json_bytes(self.ready),
                         (self.destination / "selection/phase-plan.json").read_bytes())
        self.assertEqual(workflow.canonical_json_bytes(self.verified.producer),
                         (self.destination / "selection/producer.json").read_bytes())
        context = workflow.load_json_bytes((self.destination / "context/execution-context.json").read_bytes())
        self.assertEqual(self.verified.producer, context["producer"])
        self.assertEqual("ios-arm64", context["target"])
        self.assertEqual({"artifactId": 17, "artifactSha256": "sha256:" + "2" * 64}, context["packageArtifact"])
        self.assertEqual({"artifactId": 18, "artifactSha256": "sha256:" + "5" * 64}, context["binaryArtifact"])
        self.assertEqual("aarch64-apple-darwin", context["rustHost"])
        self.assertEqual(workflow.sha256_file(self.destination / "execution/apple-validation-evidence.zip"),
                         context["evidenceSha256"])
        self.events.append("finalize")
        if self.mutation == "finalizer":
            raise ValueError("finalizer rejected")
        arguments["destination"].mkdir()
        (arguments["destination"] / "fixture.json").write_bytes(b"mock finalized shard\n")
        return {"fixture": "finalized"}

    def reset_outputs(self):
        if self.destination.exists():
            shutil.rmtree(self.destination)
        self.events.clear()

    def execute(self, **changes):
        with ExitStack() as stack:
            for owner, name, options in (
                (workflow.product_reuse, "_product_materialization_paths", {"return_value": (self.root, self.root, self.destination)}),
                (workflow.product_reuse, "_verified_product_state", {"return_value": self.verified}),
                (workflow, "verify_object", {"return_value": {"receipt": self.receipt, "receiptBytes": b"original receipt"}}),
                (workflow, "capture_apple_validation_sources", {"side_effect": self.capture}),
                (workflow, "verified_original_ios_package", {"side_effect": self.originals}),
                (workflow, "verified_original_ios_binary", {"side_effect": self.original_binary}),
                (workflow.product_reuse, "_canonical_control", {"return_value": {"original": "contract"}}),
                (workflow.product_reuse, "validate_phase_receipt", {"side_effect": lambda value: value}),
                (workflow, "execute_validation", {"side_effect": self.worker}),
                (workflow, "verified_apple_validation_archive", {"side_effect": self.archive}),
                (workflow, "verify_apple_validation_execution", {"side_effect": self.gate}),
                (workflow, "apple_validation_content", {"side_effect": self.projection}),
                (workflow, "output_inventory_digest", {"return_value": "sha256:" + "4" * 64}),
                (workflow.product_reuse, "finalize_phase_object", {"side_effect": self.finalize}),
                (workflow.product_reuse, "_runtime_worker_checkout", {"side_effect": self.checkout}),
            ):
                stack.enter_context(patch.object(owner, name, **options))
            return workflow.execute(self.plan, self.root, self.root, self.destination,
                                    **{**self.arguments, **changes})

    def test_selected_original_lifetime_and_validation_sources(self):
        result = self.execute()
        self.assertEqual(self.destination / "execution/apple-validation-evidence.zip", result["evidenceArchive"])
        self.assertEqual(workflow.sha256_file(result["evidenceArchive"]), result["evidenceSha256"])
        self.assertEqual(["original-enter", "binary-enter", "worker", "archive-enter", "complete-gate", "projection",
                          "archive-exit", "binary-exit", "original-exit", "checkout", "finalize"], self.events)
        self.assertEqual({"synthetic": "semantic projection"}, result["content"])
        self.assertFalse(self.sources.exists())
        self.assertEqual({"fixture": "finalized"}, result["shard"])
        self.assertTrue((self.destination / "shard/fixture.json").is_file())
        self.assertEqual(b"original worker diagnostics\n", (self.destination / "worker/gradle.log").read_bytes())
        for name, inventory in self.capture_inventories.items():
            self.assertEqual(inventory, workflow.regular_file_inventory(self.captures[name], allow_empty=True))

    def test_rejects_wrong_target_key_and_package_version_before_worker(self):
        for changes in ({"target": "ios"}, {"expected_build_key": "wrong"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.execute(**changes)
        self.receipt["productVersion"] = "0.8.1"
        with self.assertRaisesRegex(ValueError, "identity/version"):
            self.execute()
        self.assertEqual([], self.events)

    def test_failure_and_mutations_never_return_admission(self):
        for mutation in ("worker", "context", "source", "plan", "archive", "archive-context", "gate",
                         "stage-exit", "content", "retained-exit", "retained-raw-exit", "selection-exit",
                         "execution-context-exit", "worker-diagnostics-exit"):
            self.reset_outputs()
            self.mutation = mutation
            self.plan.write_bytes(b"original plan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute()
            self.assertFalse(self.sources.exists())
            self.assertNotIn("finalize", self.events)
            self.assertFalse((self.destination / "shard").exists())

    def test_binary_native_gate_and_exact_package_predecessor_are_required(self):
        for mutation in ("binary-gate", "binary-receipt", "binary-stage", "binary-exit"):
            self.reset_outputs()
            self.mutation = mutation
            self.events.clear()
            (self.recovered_binary / "framework").write_bytes(b"exact binary predecessor")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute()
            if mutation != "binary-exit":
                self.assertNotIn("worker", self.events)
            self.assertNotIn("finalize", self.events)
            self.assertFalse((self.destination / "shard").exists())

    def test_non_pr_finalizer_uses_release_and_finalizer_failure_does_not_publish_shard(self):
        self.verified.producer["event"] = "merge_group"
        self.verified.producer["pullRequest"] = None
        self.expected_producer["event"] = "merge_group"
        self.expected_producer["pullRequest"] = None
        self.assertEqual({"fixture": "finalized"}, self.execute()["shard"])
        self.reset_outputs()
        self.mutation = "finalizer"
        with self.assertRaisesRegex(ValueError, "finalizer rejected"):
            self.execute()
        self.assertEqual("finalize", self.events[-1])
        self.assertFalse((self.destination / "shard").exists())

    def test_late_checkout_failure_after_original_exits_prevents_finalization(self):
        self.mutation = "late-checkout"
        with self.assertRaisesRegex(ValueError, "late checkout changed"):
            self.execute()
        self.assertEqual("checkout", self.events[-1])
        self.assertNotIn("finalize", self.events)
        self.assertFalse((self.destination / "shard").exists())

    def test_real_execution_context_rejects_wrong_rust_host_before_finalization(self):
        # The native authority seam is mocked; rejection must come from the real
        # context verifier after the successful worker and complete-gate seams.
        self.arguments["rust_host"] = "x86_64-unknown-linux-gnu"
        with self.assertRaisesRegex(ValueError, "fixed macOS ARM64 Rust host"):
            self.execute()
        self.assertIn("projection", self.events)
        self.assertNotIn("checkout", self.events)
        self.assertNotIn("finalize", self.events)
        self.assertFalse((self.destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()
