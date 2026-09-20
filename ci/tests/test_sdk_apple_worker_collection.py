"""Real worker shard/transport checks with explicit replay and Apple gate seams.

The signed-upload capture and full Apple admission are mocked here; this suite
proves collector routing/lifetime only, not signing, semantic or hosted proof.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_worker_collection as fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import load_canonical_json, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object, verify_phase_shard
from products import sdk_apple_validation_admission as admission
import sdk_apple_attestation_capture as capture


adapter, PhaseInstanceId, PIN = fixture.adapter, fixture.PhaseInstanceId, fixture.PIN
TARGETS = ("ios-arm64", "ios-simulator-arm64")


class AppleWorkerCollectionTest(unittest.TestCase):
    names = fixture.SdkWorkerCollectionTest.names
    state = fixture.SdkWorkerCollectionTest.state
    official_api = fixture.SdkWorkerCollectionTest.official_api

    def setUp(self):
        fixture.SdkWorkerCollectionTest.setUp(self)
        self.plan["validationCommit"] = self.producer["commit"]
        self.policy = {"synthetic": "caller authority mocked, not a real Apple policy"}
        self.originals = {}
        self.fail_admission = set()

    def shard(self, target, *, wrong_producer=False):
        self.counter += 1
        base = self.repository / f"build/original-apple-{self.counter}"
        stage = base / "stage"
        (stage / "outputs/validation").mkdir(parents=True)
        (stage / "outputs/validation/apple-validation.json").write_bytes(b'{"synthetic":"not semantic proof"}\n')
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", "validation", target, "0.3.0",
            {"apple-validation-content": "outputs/validation/apple-validation.json"})
        receipt = write_receipt(base / "fixture-receipt.json", product="sdk", component="sdk-ios",
            phase="validation", target=target, outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer})
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        producer = {**self.producer, "runAttempt": 3} if wrong_producer else self.producer
        shard = base / "shard"
        descriptor = finalize_phase_object(stage_root=stage, phase_plan=ready, producer=producer,
            product_version="0.3.0", trust_domain="development", destination=shard)
        files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                 for row in regular_file_inventory(shard)}
        files.update({"worker/gradle.log": b"", "worker/execution.json": b"synthetic diagnostics\n",
                      "originals/source.bin": b"exact original worker bytes\x00\xff"})
        instance = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
        self.originals[target] = (shard, descriptor, files)
        return instance, ready, archive(files)

    def signer(self, target, index):
        digest = self.originals[target][1]["receiptSha256"]
        name = (f"codex-agent-sdk-apple-validation-evidence-{target}-{digest.removeprefix('sha256:')}-"
                f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}")
        job = {"id": index, "name": f"product-validation / sdk-apple-validation-attestation-{target}",
               "run_id": self.producer["runId"], "head_sha": self.producer["commit"],
               "status": "completed", "conclusion": "success",
               "started_at": "2026-09-08T10:00:00Z", "completed_at": "2026-09-08T10:10:00Z"}
        artifact = {"id": index, "name": name, "digest": sha256_bytes(target.encode()), "expired": False,
                    "created_at": "2026-09-08T10:05:00Z",
                    "workflow_run": {"id": self.producer["runId"], "head_sha": self.producer["commit"]}}
        return job, artifact

    def captured(self, plan, destination, **kwargs):
        self.assertEqual(self.plan_path, plan)
        self.assertEqual(self.originals[kwargs["target"]][1]["receiptSha256"], kwargs["expected_receipt_sha256"])
        self.assertEqual(PIN, kwargs["trusted_workflow_sha"])
        self.assertEqual(self.repository, kwargs["repository_root"])
        self.assertIs(self.environment, kwargs["environ"])
        self.assertEqual("synthetic-token", kwargs["token"])
        destination = Path(destination)
        destination.mkdir(parents=True)
        (destination / "original-upload.zip").write_bytes(b"opaque complete signed controller upload\x00\xff")
        for directory in ("sdk-apple-validation-evidence", "preparation-transport", "validation-transport", "caller-policy"):
            path = destination / "original" / directory
            path.mkdir(parents=True)
            (path / "retained.bin").write_bytes(directory.encode())
        (destination / "original/caller.json").write_bytes(b"opaque caller provenance\n")
        (destination / "capture-transport.json").write_bytes(b"opaque transport observation\n")
        return {"synthetic": "capture seam only"}

    def admitted(self, shard, carrier, destination, **kwargs):
        target = kwargs["target"]
        self.assertEqual(self.repository, kwargs["repository"])
        self.assertEqual(self.producer["commit"], kwargs["policy_revision"])
        self.assertIs(self.policy, kwargs["policy"])
        actual = verify_phase_shard(shard, PhaseInstanceId("sdk", "sdk-ios", "validation", target))
        self.assertEqual(self.originals[target][1]["receiptBytes"], actual["receiptBytes"])
        self.assertEqual(("apple-attestation-upload", "original", "sdk-apple-validation-evidence"),
                         Path(carrier).parts[-3:])
        self.assertEqual(b"sdk-apple-validation-evidence", (Path(carrier) / "retained.bin").read_bytes())
        if target in self.fail_admission:
            raise ValueError("synthetic full Apple admission rejected")
        Path(destination).mkdir(parents=True)
        (Path(destination) / "admitted.bin").write_bytes(actual["receiptBytes"])
        return [{"receiptSha256": actual["receiptSha256"], "target": target}]

    @contextmanager
    def controls(self, ready, uploads, *, mutate=None, elected=None):
        signers = [self.signer(instance.target, index) for index, instance in enumerate(sorted(ready), 1901)]
        jobs, artifacts = [item[0] for item in signers], [item[1] for item in signers]
        if mutate is not None:
            mutate(jobs, artifacts)
        with patch.object(adapter, "_verified_product_state", return_value=self.state(ready if elected is None else elected)) as replay, \
                self.official_api(ready, uploads) as http, \
                patch.object(capture, "capture_apple_validation_attestation", side_effect=self.captured) as captured, \
                patch.object(admission, "stage_collected_apple_validation", side_effect=self.admitted) as admitted:
            listed = http[1]
            original_listing = listed.side_effect
            def listing(url, field, token):
                return [*original_listing(url, field, token), *(jobs if field == "jobs" else artifacts)]
            listed.side_effect = listing
            yield replay, listed, captured, admitted, artifacts

    def collect(self, destination):
        return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
            trusted_workflow_sha=PIN, repository_root=self.repository, environ=self.environment,
            token="synthetic-token", sdk_family="ios-validation", sdk_apple_validation_policy=self.policy)

    def test_both_targets_pair_real_original_shards_and_retain_separate_full_signed_upload(self):
        rows = [self.shard(target) for target in TARGETS]
        ready, uploads = {row[0]: row[1] for row in rows}, {row[0]: row[2] for row in rows}
        before = {target: regular_file_inventory(self.originals[target][0]) for target in TARGETS}
        destination = self.repository / "build/collected"
        with self.controls(ready, uploads) as (replay, listed, captured, admitted, artifacts):
            result = self.collect(destination)
            self.assertIs(self.policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
            self.assertEqual(1, sum(call.args[1] == "artifacts" for call in listed.call_args_list))
            self.assertEqual(2, captured.call_count)
            self.assertEqual(2, admitted.call_count)
            for call, artifact in zip(captured.call_args_list, artifacts):
                self.assertEqual(artifact["id"], call.kwargs["artifact_id"])
                self.assertEqual(artifact["digest"], call.kwargs["artifact_sha256"])
        self.assertEqual(result, load_canonical_json(destination / "collection.json"))
        for row in result["rows"]:
            target = row["target"]
            self.assertEqual("success", row["result"])
            shard = destination / row["shardDirectory"]
            self.assertEqual(before[target], regular_file_inventory(shard))
            self.assertEqual(before[target], regular_file_inventory(self.originals[target][0]))
            original = destination / row["originalDirectory"]
            self.assertEqual(self.originals[target][2], {item["relativePath"]: (original / item["relativePath"]).read_bytes()
                for item in regular_file_inventory(original, allow_empty=True)})
            retained = original.parent / "apple-attestation-upload"
            self.assertEqual(b"opaque complete signed controller upload\x00\xff", (retained / "original-upload.zip").read_bytes())
            self.assertEqual(b"opaque caller provenance\n", (retained / "original/caller.json").read_bytes())
            evidence = destination / row["sdkAppleValidationEvidenceDirectory"]
            self.assertEqual(original.parent / "sdk-apple-validation-evidence", evidence)
            self.assertEqual(self.originals[target][1]["receiptBytes"], (evidence / "admitted.bin").read_bytes())

    def test_running_signer_rejects_before_capture_or_publication(self):
        instance, ready, raw = self.shard(TARGETS[0])
        destination = self.repository / "build/running"
        with self.controls({instance: ready}, {instance: raw},
                mutate=lambda jobs, artifacts: jobs[0].update(status="in_progress")) as controls, \
                self.assertRaisesRegex(ValueError, "still running|finish|completed"):
            self.collect(destination)
        controls[2].assert_not_called()
        controls[3].assert_not_called()
        self.assertFalse(destination.exists())

    def test_missing_ambiguous_failed_signer_and_admission_failure_keep_sibling_and_diagnostics(self):
        rows = [self.shard(target) for target in TARGETS]
        ready, uploads = {row[0]: row[1] for row in rows}, {row[0]: row[2] for row in rows}
        for case in ("missing", "ambiguous", "wrong-receipt", "failed-job", "admission"):
            self.fail_admission = {TARGETS[0]} if case == "admission" else set()
            def mutate(jobs, artifacts):
                if case == "missing": artifacts.pop(0)
                elif case == "ambiguous": artifacts.append(deepcopy(artifacts[0]))
                elif case == "wrong-receipt": artifacts[0]["name"] = artifacts[0]["name"].replace(
                    self.originals[TARGETS[0]][1]["receiptSha256"].removeprefix("sha256:"), "d" * 64)
                elif case == "failed-job": jobs[0]["conclusion"] = "failure"
            destination = self.repository / f"build/failure-{case}"
            with self.subTest(case=case), self.controls(ready, uploads, mutate=mutate):
                result = self.collect(destination)
            collected = {row["target"]: row for row in result["rows"]}
            self.assertEqual("failure", collected[TARGETS[0]]["result"])
            self.assertIsNone(collected[TARGETS[0]]["shardDirectory"])
            self.assertNotIn("sdkAppleValidationEvidenceDirectory", collected[TARGETS[0]])
            original = destination / collected[TARGETS[0]]["originalDirectory"]
            self.assertEqual(b"", (original / "worker/gradle.log").read_bytes())
            if case == "admission":
                self.assertTrue((original.parent / "apple-attestation-upload/original/caller.json").is_file())
            self.assertEqual("success", collected[TARGETS[1]]["result"])

    def test_wrong_worker_producer_never_reaches_apple_capture_or_admission(self):
        instance, ready, raw = self.shard(TARGETS[0], wrong_producer=True)
        destination = self.repository / "build/wrong-worker"
        with self.controls({instance: ready}, {instance: raw}) as controls:
            result = self.collect(destination)
        controls[2].assert_not_called()
        controls[3].assert_not_called()
        row, = result["rows"]
        self.assertEqual("failure", row["result"])
        self.assertIn("elected plan and producer", row["reason"])
        self.assertTrue((destination / row["originalDirectory"] / "worker/gradle.log").is_file())

    def test_missing_caller_policy_fails_after_worker_diagnostics_before_capture(self):
        instance, ready, raw = self.shard(TARGETS[0])
        self.policy = None
        destination = self.repository / "build/no-policy"
        with self.controls({instance: ready}, {instance: raw}) as controls:
            result = self.collect(destination)
        controls[2].assert_not_called()
        controls[3].assert_not_called()
        row, = result["rows"]
        self.assertEqual("failure", row["result"])
        self.assertIn("independent caller admission policy", row["reason"])
        self.assertTrue((destination / row["originalDirectory"] / "worker/gradle.log").is_file())

    def test_admission_time_shard_or_signed_provenance_mutation_cannot_mark_success(self):
        rows = [self.shard(target) for target in TARGETS]
        ready, uploads = {row[0]: row[1] for row in rows}, {row[0]: row[2] for row in rows}
        for selected in ("shard", "provenance"):
            destination = self.repository / f"build/mutation-{selected}"
            def mutate(shard, carrier, output, **kwargs):
                result = self.admitted(shard, carrier, output, **kwargs)
                if kwargs["target"] == TARGETS[0]:
                    path = (Path(shard) / "phase-receipt.json" if selected == "shard" else
                            Path(carrier).parent / "caller.json")
                    path.write_bytes(path.read_bytes() + b"late mutation")
                return result
            with self.subTest(selected=selected), self.controls(ready, uploads) as controls:
                controls[3].side_effect = mutate
                result = self.collect(destination)
            collected = {row["target"]: row for row in result["rows"]}
            self.assertEqual("failure", collected[TARGETS[0]]["result"])
            self.assertIsNone(collected[TARGETS[0]]["shardDirectory"])
            self.assertNotIn("sdkAppleValidationEvidenceDirectory", collected[TARGETS[0]])
            self.assertEqual("success", collected[TARGETS[1]]["result"])

    def test_unrelated_ready_phases_do_not_request_apple_artifacts(self):
        unrelated = {PhaseInstanceId(*identity): {} for identity in (
            ("sdk", "sdk-ios", "package", "ios"), ("sdk", "javascript", "validation", "node"),
            ("sdk", "python", "validation", "linux-x64"), ("runtime", "jvm", "binary", "jvm"))}
        with patch.object(adapter, "_verified_product_state", return_value=self.state(unrelated)), \
                patch.object(adapter, "api_json") as query, patch.object(adapter, "paginated_items") as listing, \
                patch.object(capture, "capture_apple_validation_attestation") as captured, \
                patch.object(admission, "stage_collected_apple_validation") as admitted:
            result = self.collect(self.repository / "build/no-apple")
        self.assertEqual([], result["rows"])
        for seam in (query, listing, captured, admitted):
            seam.assert_not_called()


if __name__ == "__main__":
    unittest.main()
