"""Real resume/key/object recovery with synthetic bytes, not hosted acceptance."""

import shutil
import unittest
from unittest import mock

from ci.tests import test_product_resume_metadata_recovery as fixture
import sdk_ios_binary_recovery as recovery
from products.inventory import load_canonical_json, regular_file_inventory
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


adapter = fixture.adapter
IOS = adapter.PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class IosResumeRecoveryTest(unittest.TestCase):
    setUpClass = classmethod(fixture.ResumeMetadataRecoveryTest.setUpClass.__func__)
    setUp = fixture.ResumeMetadataRecoveryTest.setUp
    tearDown = fixture.ResumeMetadataRecoveryTest.tearDown
    control_seams = classmethod(fixture.ResumeMetadataRecoveryTest.control_seams.__func__)

    def test_original_binary_is_retained_replayed_and_never_reelected(self):
        ready = {}
        original_producer = {**self.producer, "runId": 6, "runAttempt": 1}
        actual_planner = adapter._plan_with_sdk_tooling
        original_bytes = []

        def planner(wave, *args, **kwargs):
            consumer = kwargs.get("build_plan_consumer")
            def remember(instance, plan):
                ready[instance] = plan
                if consumer is not None:
                    consumer(instance, plan)
            return actual_planner(wave, *args, **{**kwargs, "build_plan_consumer": remember})

        def capture(plan_path, plan, producer, key, destination, artifact_root, **policy):
            self.assertEqual(key, ready[IOS]["buildKey"])
            stage = self.scratch / "sdk-original-stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/fixture.bin").write_bytes(b"synthetic iOS bytes, not a real framework\n")
            write_output_manifest(stage, "sdk", "sdk-ios", "binary", "ios", "0.2.0",
                                  {"fixture": "outputs"})
            shard = destination / "sdk-ios/binary/ios/original/shard"
            finalize_phase_object(stage_root=stage,
                phase_plan={k: ready[IOS][k] for k in PHASE_PLAN_KEYS},
                producer=original_producer, product_version="0.2.0",
                trust_domain="development", destination=shard)
            original_bytes.append((shard / "phase-receipt.json").read_bytes())
            return [recovery._record(shard.parent.parent, artifact_root)]

        def replay(capture_root, artifact_root, **policy):
            # Acquisition/official observation seam only; real key/object/carrier
            # and initial-state replay below still run unchanged.
            return [recovery._record(capture_root / "sdk-ios/binary/ios", artifact_root)]

        destination = self.scratch / "sdk-resumed"
        environment = {**self.environment, "GITHUB_TOKEN": "fixture-observation-only"}
        with self.control_seams(), mock.patch.object(adapter, "_requested", return_value=(IOS,)), \
                mock.patch.object(adapter, "_plan_with_sdk_tooling", side_effect=planner), \
                mock.patch.object(adapter, "_prior_failed_pr_attempts", return_value=({},)), \
                mock.patch.object(recovery, "capture_prior_ios_binary", side_effect=capture) as acquire, \
                mock.patch.object(recovery, "replay_prior_ios_binary", side_effect=replay) as readmit:
            result = adapter.resume_products(self.plan_path, self.discovery, self.state, self.handoff,
                destination, self.scratch / "github-output", repository_root=self.repository,
                environ=environment, sdk_original_workflow_sha="e" * 40)
            self.assertTrue(result["fullReuse"])
            acquire.assert_called_once()
            before = regular_file_inventory(destination, allow_empty=True)
            verified = adapter._verified_product_state(self.plan_path, destination, destination,
                self.repository, environment, None, sdk_original_workflow_sha="e" * 40)
            readmit.assert_called_once()
            record = verified.prior_by_instance[IOS]
            self.assertEqual("retained", record["state"])
            original = adapter.verify_object(verified.sources[IOS], build_key=record["buildKey"],
                receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
            self.assertEqual(original_bytes[0], original["receiptBytes"])
            self.assertEqual(original_producer, original["receipt"]["producer"])
            self.assertNotIn(IOS, verified.prior_ready_plans)
            self.assertEqual(before, regular_file_inventory(destination, allow_empty=True))
            request = load_canonical_json(destination / "reuse-wave-request.json")
            self.assertIn(IOS, {adapter._identity(row) for row in request["availableObjects"]})


if __name__ == "__main__":
    unittest.main()
