"""Wave-10 iOS metadata collection; the complete Apple gate is a mocked seam."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci.tests import test_sdk_apple_worker_collection as apple_fixture
from ci.tests import test_sdk_worker_collection as worker_fixture
from ci.tests import test_sdk_workflow as workflow_fixture
from ci.tests.product_chain_support import reference, write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from products import sdk_apple_validation_admission as apple_admission


adapter = worker_fixture.adapter
workflow = workflow_fixture.workflow
PIN = worker_fixture.PIN
TARGETS = apple_fixture.TARGETS
INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")


class SdkIosMetadataFamilyTest(unittest.TestCase):
    setUp = workflow_fixture.SdkWorkflowTest.setUp

    def test_matrix_selects_only_exact_metadata_key_on_declared_macos_arm64_route(self):
        keys = {instance: "sha256:" + f"{index:064x}" for index, instance in enumerate(PHASE_INSTANCE_IDS, 1)}
        self.inspect.return_value = {"readyPlans": [
            {**workflow.product_reuse._identity_record(instance), "buildKey": key}
            for instance, key in keys.items()]}
        value = workflow.matrix(self.plan, self.discovery, self.state, self.repository / "matrix-output",
            family="ios-metadata", repository_root=self.repository, environ={})
        self.assertEqual([{"product": "sdk", "component": "sdk-ios", "phase": "metadata", "target": "ios",
                           "buildKey": keys[INSTANCE], "runner": "macos-26",
                           "runnerOs": "macOS", "runnerArch": "ARM64"}], value["include"])
        # This is fixed routing only; no test fixture claims observed Apple host trust.

    def test_wave10_advances_only_admitted_shard_and_failure_never_claims_completion(self):
        source = self.repository / "metadata-input"
        for name in ("product-resume-inputs", "product-resume-state", "runtime-state"):
            (source / name).mkdir(parents=True)
            (source / name / "retained.bin").write_bytes(name.encode())
        policy = {"synthetic": "caller policy object"}
        for failure in (False, True):
            destination = self.repository / f"metadata-collection-{failure}"
            row = {**adapter._identity_record(INSTANCE), "result": "failure" if failure else "success",
                   "shardDirectory": None if failure else "rows/sdk-ios-metadata-ios/original/shard",
                   "originalDirectory": "rows/sdk-ios-metadata-ios/original"}

            def advance(*args, **kwargs):
                self.assertEqual("ios-metadata", kwargs["sdk_family"])
                self.assertIs(policy, kwargs["sdk_apple_validation_policy"])
                self.assertNotIn("sdk_apple_evidence_roots", kwargs)
                self.assertEqual((INSTANCE,) if failure else (), kwargs["failed_instances"])
                self.assertEqual([] if failure else
                    [destination / "collection/rows/sdk-ios-metadata-ios/original/shard"], args[3])
                args[4].mkdir(parents=True)
                return {"advanced": not failure}

            with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]}) as collect, \
                    patch.object(workflow.product_reuse, "advance_products", side_effect=advance), \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.collect(source, destination, self.repository / f"metadata-output-{failure}",
                    wave=10, family="ios-metadata", trusted_workflow_sha=PIN,
                    repository_root=self.repository, environ={}, token="synthetic-token",
                    sdk_apple_validation_policy=policy)
            self.assertEqual({"advanced": not failure}, result)
            self.assertEqual("ios-metadata", collect.call_args.kwargs["sdk_family"])
            self.assertIs(policy, collect.call_args.kwargs["sdk_apple_validation_policy"])
            self.assertEqual(not failure, matrix.called)
            for name in ("product-resume-inputs", "product-resume-state"):
                self.assertEqual(name.encode(), (destination / "handoff" / name / "retained.bin").read_bytes())
        with self.assertRaisesRegex(ValueError, "exact family wave"):
            workflow.collect(source, self.repository / "wrong-wave", self.repository / "unused-output",
                wave=9, family="ios-metadata", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ={}, token="synthetic-token",
                sdk_apple_validation_policy=policy)


class SdkIosMetadataCollectionTest(unittest.TestCase):
    names = worker_fixture.SdkWorkerCollectionTest.names
    official_api = worker_fixture.SdkWorkerCollectionTest.official_api

    def setUp(self):
        worker_fixture.SdkWorkerCollectionTest.setUp(self)
        self.plan["validationCommit"] = self.producer["commit"]
        self.policy = {"synthetic": "caller authority; concrete gate mocked"}
        self.originals = {}
        self.validation = {}
        for target in TARGETS:
            instance, ready, _ = apple_fixture.AppleWorkerCollectionTest.shard(self, target)
            shard, descriptor, _ = self.originals[target]
            self.validation[instance] = (ready, shard, descriptor)
        self.metadata_ready, self.metadata_descriptor, self.metadata_upload = self.metadata()
        self.external_records = []
        for target in TARGETS:
            descriptor = self.validation[PhaseInstanceId("sdk", "sdk-ios", "validation", target)][2]
            digest = descriptor["receiptSha256"]
            path = self.repository / f"existing-apple/{target}/originals/{digest.removeprefix('sha256:')}"
            path.mkdir(parents=True)
            (path / "proof.bin").write_bytes(("external " + target).encode())
            self.external_records.append({"receiptSha256": digest, "target": target,
                "evidenceRoot": path.relative_to(self.repository).as_posix()})
        self.external_records.sort(key=lambda row: row["receiptSha256"])
        self.external_before = {record["target"]: regular_file_inventory(
            self.repository / record["evidenceRoot"], allow_empty=True) for record in self.external_records}
        self.gate = SimpleNamespace(verify_metadata=Mock(side_effect=self.verify_metadata))
        self.fail_gate = False
        self.mutate_original = False

    def metadata(self):
        base = self.repository / "build/original-ios-metadata"
        stage = base / "stage"
        content = stage / "outputs/evidence/apple-metadata.json"
        content.parent.mkdir(parents=True)
        content.write_bytes(b'{"synthetic":"deterministic metadata fixture"}\n')
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", "metadata", "ios", "0.3.0",
                                         {"apple-metadata-content": "outputs/evidence"})
        receipt = write_receipt(base / "receipt.json", product="sdk", component="sdk-ios",
            phase="metadata", target="ios", version="0.3.0", version_identity="0.3.0",
            outputs=manifest["outputs"], upstream=[reference(value[2]["receipt"])
                for value in self.validation.values()],
            context={"producer": self.producer})
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        shard = base / "shard"
        descriptor = finalize_phase_object(stage_root=stage, phase_plan=ready, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=shard)
        files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                 for row in regular_file_inventory(shard)}
        files.update({"worker/gradle.log": b"", "worker/execution.json": b"metadata diagnostics\n",
                      "inputs/selected.bin": b"exact materialized predecessor bytes\x00\xff"})
        self.metadata_files = files
        return ready, descriptor, archive(files)

    def state(self, *, missing_target=None):
        value = worker_fixture.SdkWorkerCollectionTest.state(self, {INSTANCE: self.metadata_ready})
        value.plan = {**self.plan, "validationCommit": self.producer["commit"]}
        value.rebased_request = {"sdkAppleValidationEvidence": [self.external_records[0]]}
        value.sources, value.prior_carrier_phases = {}, {}
        for identity, (_, shard, descriptor) in self.validation.items():
            if identity.target == missing_target:
                continue
            value.sources[identity] = shard / descriptor["objectPath"]
            value.prior_carrier_phases[identity] = {**adapter._identity_record(identity),
                **{name: descriptor[name] for name in ("buildKey", "receiptSha256", "objectSha256")}}
        return value

    def verify_metadata(self, metadata, predecessors):
        self.assertEqual(self.metadata_descriptor["receiptBytes"], metadata["receiptBytes"])
        self.assertEqual(self.metadata_descriptor["receiptSha256"], metadata["receiptSha256"])
        self.assertEqual(TARGETS, tuple(value["receipt"]["target"] for value in predecessors))
        for value in predecessors:
            identity = PhaseInstanceId("sdk", "sdk-ios", "validation", value["receipt"]["target"])
            descriptor = self.validation[identity][2]
            self.assertEqual({name: descriptor[name] for name in
                ("receipt", "receiptBytes", "receiptSha256", "objectSha256")}, value)
        if self.fail_gate:
            raise ValueError("synthetic full Apple metadata gate rejected")
        if self.mutate_original:
            matches = list(self.repository.glob(
                "codex-agent-runtime-collection-*/collection/rows/sdk-ios-metadata-ios/original/worker/gradle.log"))
            self.assertEqual(1, len(matches))
            matches[0].write_bytes(b"late mutation")

    def collect(self, destination, *, policy=True, missing_target=None):
        state = self.state(missing_target=missing_target)
        retained = [record for record in self.external_records
                    if record not in state.rebased_request["sdkAppleValidationEvidence"]]
        with patch.object(adapter, "_verified_product_state", return_value=state), \
                self.official_api({INSTANCE: self.metadata_ready}, {INSTANCE: self.metadata_upload}), \
                patch.object(adapter, "_retained_apple_handoffs", return_value=retained), \
                patch.object(apple_admission, "AppleValidationAdmission", return_value=self.gate) as admission:
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository, environ=self.environment,
                token="synthetic-token", sdk_family="ios-metadata",
                **({"sdk_apple_validation_policy": self.policy} if policy else {}))
        return result, admission

    def test_exact_worker_job_upload_key_and_full_gate_precede_success(self):
        destination = self.repository / "build/collected-ios-metadata"
        result, admission = self.collect(destination)
        row, = result["rows"]
        self.assertEqual("success", row["result"])
        self.assertEqual(INSTANCE, adapter._identity(row))
        self.assertEqual(self.names(INSTANCE, self.metadata_ready["buildKey"]),
                         (row["jobName"], row["artifactName"]))
        self.assertEqual(self.metadata_descriptor["receiptBytes"],
                         (destination / row["shardDirectory"] / "phase-receipt.json").read_bytes())
        self.assertEqual(self.metadata_files, {record["relativePath"]:
            (destination / row["originalDirectory"] / record["relativePath"]).read_bytes()
            for record in regular_file_inventory(destination / row["originalDirectory"], allow_empty=True)})
        self.gate.verify_metadata.assert_called_once()
        admission.assert_called_once_with(self.repository, self.external_records, repository=self.repository,
            policy_revision=self.producer["commit"], policy=self.policy)
        self.assertNotIn("sdkAppleValidationEvidenceDirectory", row)
        for record in self.external_records:
            self.assertEqual(self.external_before[record["target"]], regular_file_inventory(
                self.repository / record["evidenceRoot"], allow_empty=True))

    def test_gate_failure_missing_policy_or_predecessor_and_late_mutation_retain_diagnostics_only(self):
        reasons = {
            "replay": "synthetic full Apple metadata gate rejected",
            "policy": "requires independent caller admission policy",
            "predecessor": "lacks both original validation predecessors",
            "mutation": "original shard or diagnostics changed",
        }
        for case in reasons:
            self.fail_gate, self.mutate_original = case == "replay", case == "mutation"
            destination = self.repository / f"build/metadata-{case}"
            result, admission = self.collect(destination, policy=case != "policy",
                missing_target="ios-simulator-arm64" if case == "predecessor" else None)
            row, = result["rows"]
            self.assertEqual("failure", row["result"])
            self.assertIsNone(row["shardDirectory"])
            self.assertIsNotNone(row["originalDirectory"])
            original = destination / row["originalDirectory"]
            self.assertTrue((original / "worker/execution.json").is_file())
            if case in ("policy", "predecessor"):
                self.gate.verify_metadata.assert_not_called()
            self.assertIn(reasons[case], row["reason"])
            for record in self.external_records:
                self.assertEqual(self.external_before[record["target"]], regular_file_inventory(
                    self.repository / record["evidenceRoot"], allow_empty=True))
            self.gate.verify_metadata.reset_mock()


if __name__ == "__main__":
    unittest.main()
