"""Real resume/key/object recovery over synthetic products, never host execution."""

from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

from ci.tests import test_product_contract_resume as fixture
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture
from ci.products.inventory import load_canonical_json, regular_file_inventory
from ci.products.receipt import write_output_manifest
from ci.products.restore import PHASE_PLAN_KEYS, finalize_phase_object


adapter = fixture.adapter
METADATA = adapter.PhaseInstanceId("runtime", "jvm", "metadata", "jvm")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ResumeMetadataRecoveryTest(unittest.TestCase):
    setUp = fixture.ContractProductResumeTest.setUp
    tearDown = fixture.ContractProductResumeTest.tearDown
    control_seams = classmethod(fixture.ContractProductResumeTest.control_seams.__func__)

    @classmethod
    def setUpClass(cls):
        owner = fixture.fixture.ProductReuseAdapterTest
        original = owner.contract_repository

        def repository_with_native_authorities(helper):
            repository, commit, tree = original(helper)
            source = Path(__file__).resolve().parents[2]
            paths = [f"codex-agent-runtime-desktop/native/c-api/{name}" for name in (
                "abi-contract.json", "binary-flags.json", "include/codex_agent.h",
                "exports/macos.exports", "exports/linux.map", "exports/windows.def",
            )]
            paths.append("codex-agent-runtime-desktop/codex-app-server-distributions.json")
            paths.extend(f"gradle/release/toolchains/runtime/{target}.json"
                         for target in adapter.NATIVE_TARGETS)
            for relative in paths:
                destination = repository / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, destination)
            subprocess.run(["git", "add", *paths], cwd=repository, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "fixture planning authorities"],
                           cwd=repository, check=True, capture_output=True)
            return repository, commit, tree

        with mock.patch.object(owner, "contract_repository", repository_with_native_authorities):
            fixture.ContractProductResumeTest.setUpClass.__func__(cls)

    def test_recovered_validation_unlocks_metadata_and_preserves_original_on_replay(self):
        reports = RuntimeEvidenceFixture(self.scratch / "reports")
        reports.commits = {target: self.producer["commit"] for target in reports.commits}
        jvm_reports = {load_canonical_json(path)["target"]: path for path in reports.write_jvm()}
        original_producer = {**self.producer, "runId": 6, "runAttempt": 1}
        ready, originals, recoveries = {}, {}, []
        actual_planner = adapter._plan_with_sdk_tooling
        actual_prior_objects = adapter._prior_failed_runtime_objects

        def planner(wave, *args, **kwargs):
            consumer = kwargs.get("build_plan_consumer")

            def remember(instance, phase_plan):
                ready[instance] = phase_plan
                if consumer is not None:
                    consumer(instance, phase_plan)

            return actual_planner(wave, *args, **{**kwargs, "build_plan_consumer": remember})

        def recover(_plan, _producer, wanted, destination, **_policy):
            recoveries.append(set(wanted))
            for instance, key in wanted.items():
                identity = tuple(getattr(instance, field) for field in adapter._IDENTITY_KEYS)
                phase_plan = {field: ready[instance][field] for field in PHASE_PLAN_KEYS}
                self.assertEqual(key, phase_plan["buildKey"])
                stage = self.scratch / "original-stages" / "-".join(identity)
                outputs = stage / "outputs"
                outputs.mkdir(parents=True)
                kind = "fixture"
                if instance.component == "jvm" and instance.phase == "validation":
                    kind = "jvm-evidence"
                    report = jvm_reports[adapter.RUNTIME_EVIDENCE_TARGETS[instance.target]]
                    (outputs / kind).mkdir()
                    (outputs / kind / report.name).write_bytes(report.read_bytes())
                elif instance == METADATA:
                    kind = "adapter-evidence"
                    projection = next(destination.parent.glob(
                        "initial-runtime-validation-handoffs/jvm-jvm/projection.json"))
                    (outputs / "jvm.json").write_bytes(projection.read_bytes())
                else:
                    (outputs / "fixture.bin").write_bytes(b"synthetic product, not compiler evidence\n")
                write_output_manifest(stage, *identity, "0.2.0", {kind: "outputs"})
                original = self.scratch / "original-shards" / "-".join(identity)
                finalize_phase_object(stage_root=stage, phase_plan=phase_plan,
                    producer=original_producer, product_version="0.2.0", trust_domain="development",
                    destination=original)
                originals[instance] = original
                captured = destination / instance.component / instance.phase / instance.target / "phases" / instance.phase / "original/shard"
                shutil.copytree(original, captured)
            return {instance: {} for instance in wanted}

        destination = self.scratch / "resumed"
        environment = {**self.environment, "GITHUB_TOKEN": "fixture-observation-only"}
        with self.control_seams(), mock.patch.object(adapter, "_requested", return_value=(METADATA,)), \
                mock.patch.object(adapter, "_plan_with_sdk_tooling", side_effect=planner), \
                mock.patch.object(adapter, "_prior_failed_pr_attempts", return_value=({},)), \
                mock.patch.object(adapter, "capture_prior_failed_runtime_phases", side_effect=recover), \
                mock.patch.object(adapter, "_prior_failed_runtime_objects", side_effect=lambda capture, root, **_:
                                  actual_prior_objects(capture, root)):
            # Original CI acquisition is the sole remote seam. Real Contract
            # trust, phase keys, objects, evidence derivation and replay stay on.
            result = adapter.resume_products(self.plan_path, self.discovery, self.state, self.handoff,
                destination, self.scratch / "github-output", repository_root=self.repository,
                environ=environment, sdk_original_workflow_sha="e" * 40)
            self.assertTrue(result["fullReuse"])
            self.assertIn({METADATA}, recoveries)
            original_receipt = (originals[METADATA] / "phase-receipt.json").read_bytes()
            request = load_canonical_json(destination / "reuse-wave-request.json")
            self.assertEqual(1, len(request["runtimeValidationEvidence"]))
            before = regular_file_inventory(destination, allow_empty=True)
            verified = adapter._verified_product_state(self.plan_path, destination, destination,
                self.repository, environment, None, sdk_original_workflow_sha="e" * 40)
            metadata = adapter.verify_object(verified.sources[METADATA],
                build_key=verified.prior_by_instance[METADATA]["buildKey"],
                receipt_sha256=verified.prior_by_instance[METADATA]["receiptSha256"],
                object_sha256=verified.prior_by_instance[METADATA]["objectSha256"])
            self.assertEqual(original_receipt, metadata["receiptBytes"])
            self.assertEqual(original_producer, metadata["receipt"]["producer"])
            self.assertEqual(before, regular_file_inventory(destination, allow_empty=True))
            report_path = destination / request["runtimeValidationEvidence"][0]["reports"][0]
            report_path.write_bytes(report_path.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                adapter._verified_product_state(self.plan_path, destination, destination,
                    self.repository, environment, None, sdk_original_workflow_sha="e" * 40)


if __name__ == "__main__":
    unittest.main()
