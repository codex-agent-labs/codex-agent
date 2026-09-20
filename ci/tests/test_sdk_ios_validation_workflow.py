"""Selected caller orchestration only; mocked gates do not prove Apple acceptance."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
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
            expected_fixed={"versions": {"sdk": "0.8.0"}}, producer={"commit": "a" * 40, "tree": "d" * 40})
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
               "receiptPath": receipt, "receipt": self.receipt, "sdk": {"directory": self.root / "sdk",
                   "compatibility": {"contract": {"digest": "sha256:" + "3" * 64}}}}
        self.events.append("original-exit")
        if self.mutation == "context":
            raise ValueError("original context changed")
        if self.mutation == "archive":
            (self.root / "raw.zip").write_bytes(b"changed archive")

    @contextmanager
    def original_binary(self, plan, receipt, **arguments):
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.binary / "phase-receipt.json", receipt)
        self.assertEqual(18, arguments["artifact_id"])
        self.assertEqual("sha256:" + "5" * 64, arguments["artifact_sha256"])
        self.assertEqual("aarch64-apple-darwin", arguments["rust_host"])
        self.events.append("binary-enter")
        if self.mutation == "binary-gate":
            raise ValueError("binary native gate failed")
        if self.mutation == "binary-stage":
            (self.recovered_binary / "framework").write_bytes(b"different predecessor")
        yield {"stage": self.recovered_binary, "receiptBytes":
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
        archive = self.root / "raw.zip"
        archive.write_bytes(b"raw archive fixture")
        return {"evidenceArchive": archive, "evidenceSha256": workflow.sha256_file(archive)}

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
            ):
                stack.enter_context(patch.object(owner, name, **options))
            return workflow.execute(self.plan, self.root, self.root, self.destination,
                                    **{**self.arguments, **changes})

    def test_selected_original_lifetime_and_validation_sources(self):
        result = self.execute()
        self.assertEqual(self.root / "raw.zip", result["evidenceArchive"])
        self.assertEqual(workflow.sha256_file(result["evidenceArchive"]), result["evidenceSha256"])
        self.assertEqual(["original-enter", "binary-enter", "worker", "archive-enter", "complete-gate", "projection",
                          "archive-exit", "binary-exit", "original-exit"], self.events)
        self.assertEqual({"synthetic": "semantic projection"}, result["content"])
        self.assertFalse(self.sources.exists())
        self.assertFalse(self.destination.exists())

    def test_rejects_wrong_target_key_and_package_version_before_worker(self):
        for changes in ({"target": "ios"}, {"expected_build_key": "wrong"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.execute(**changes)
        self.receipt["productVersion"] = "0.8.1"
        with self.assertRaisesRegex(ValueError, "identity/version"):
            self.execute()
        self.assertEqual([], self.events)

    def test_failure_and_mutations_never_return_admission(self):
        for mutation in ("worker", "context", "source", "plan", "archive", "archive-context", "gate"):
            self.mutation = mutation
            self.plan.write_bytes(b"original plan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute()
            self.assertFalse(self.sources.exists())

    def test_binary_native_gate_and_exact_package_predecessor_are_required(self):
        for mutation in ("binary-gate", "binary-receipt", "binary-stage", "binary-exit"):
            self.mutation = mutation
            self.events.clear()
            (self.recovered_binary / "framework").write_bytes(b"exact binary predecessor")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.execute()
            if mutation != "binary-exit":
                self.assertNotIn("worker", self.events)


if __name__ == "__main__":
    unittest.main()
