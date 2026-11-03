"""Concrete Android metadata admission tests; hosted/native gates are mocked."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_original as original
from ci.products import sdk_android_metadata_admission as admission
from ci.products.inventory import canonical_json_bytes, sha256_bytes, snapshot_regular_tree
from ci.products.restore import PHASE_PLAN_KEYS, finalize_phase_object, verify_phase_shard
from ci.tests import test_sdk_android_metadata_original as fixtures


class AndroidMetadataAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.AndroidMetadataOriginalTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        validation_shard_root = self.root / "real-validation-shard"
        finalize_phase_object(
            stage_root=self.f.f.validation_stage,
            phase_plan={name: self.f.f.validation[name] for name in PHASE_PLAN_KEYS},
            producer=self.f.f.validation["producer"],
            product_version=self.f.f.version, trust_domain="development",
            destination=validation_shard_root)
        for target in (
                self.f.f.original_capture / "original/shard",
                self.f.worker / "originals/validation/original/shard",
                self.f.retained_capture / "original/originals/validation/original/shard"):
            shutil.rmtree(target)
            shutil.copytree(validation_shard_root, target)
        shard = verify_phase_shard(self.f.worker / "shard", admission._METADATA)
        self.metadata = {name: shard[name] for name in
                         ("receipt", "receiptBytes", "receiptSha256", "objectSha256")}
        validation_raw = self.f.f.validation_receipt.read_bytes()
        validation_shard = verify_phase_shard(
            validation_shard_root, admission._VALIDATION)
        self.validation = {
            "receipt": deepcopy(self.f.f.validation), "receiptBytes": validation_raw,
            "receiptSha256": sha256_bytes(validation_raw),
            "objectSha256": validation_shard["objectSha256"],
        }
        self.carrier = self.root / "metadata-evidence"
        relative = "originals/" + shard["receiptSha256"].removeprefix("sha256:")
        snapshot_regular_tree(self.f.retained_capture, self.carrier / relative, allow_empty=True)
        self.records = [{"receiptSha256": shard["receiptSha256"],
                         "captureRoot": relative}]
        self.policy = {
            "plan": str(self.f.recovery_plan),
            "validationCapture": str(self.f.f.original_capture),
            "packageStage": str(self.f.f.package_stage),
            "packageReceipt": str(self.f.f.package_receipt),
            "binaryStage": str(self.f.f.binary_stage),
            "binaryReceipt": str(self.f.f.binary_receipt),
            "compatibilityRequest": str(self.f.f.compatibility),
            "binaryContractEvidence": deepcopy(self.f.f.contract_evidence),
            "trustedSourceCommit": "e" * 40,
            "trustedSourceTree": "f" * 40,
            "originalContext": deepcopy(self.f.context),
            "toolingEvidence": str(self.f.f.tooling),
            "toolingPublicKey": str(self.f.f.tooling_key),
            "javaExecutable": str(self.f.f.java),
            "apkanalyzerExecutable": str(self.f.f.analyzer),
            "toolingTrustDomain": "development",
            "toolingKeyring": None,
            "toolingKeysDirectory": None,
        }
        self.enterContext(patch.object(
            admission, "_request_inventory",
            side_effect=lambda path: {Path(path): "fixture compatibility input"}))

    def make(self, **changes):
        values = {"root": self.carrier, "records": self.records,
                  "repository": self.root, "policy_revision": "1" * 40,
                  "policy": self.policy}
        values.update(changes)
        return admission.AndroidMetadataAdmission(**values)

    def test_exact_metadata_and_validation_run_full_retained_replay_each_time(self):
        gate = self.make()
        self.f.capture.reset_mock()
        self.assertIsNone(gate.verify_metadata(self.metadata, [self.validation]))
        self.assertIsNone(gate.verify_metadata(self.metadata, (self.validation,)))
        self.f.capture.assert_not_called()
        self.assertEqual(2, self.f.retained.call_count)
        self.assertEqual(2, self.f.held.call_count)

    def test_metadata_record_identity_and_object_are_exact(self):
        missing = self.make(records=[])
        with self.assertRaisesRegex(ValueError, "lacks the exact retained receipt"):
            missing.verify_metadata(self.metadata, [self.validation])
        changed = deepcopy(self.metadata)
        changed["objectSha256"] = "sha256:" + "8" * 64
        with self.assertRaisesRegex(ValueError, "retained shard differs"):
            self.make().verify_metadata(changed, [self.validation])
        with self.assertRaisesRegex(ValueError, "exact metadata envelope"):
            self.make().verify_metadata(self.validation, [self.validation])

    def test_exact_one_validation_predecessor_and_receipt_bytes_are_required(self):
        gate = self.make()
        for values in ([], [self.validation, self.validation], [self.metadata]):
            with self.subTest(count=len(values)), self.assertRaisesRegex(
                    ValueError, "exactly one|exact Android validation"):
                gate.verify_metadata(self.metadata, values)
        wrong_object = deepcopy(self.validation)
        wrong_object["objectSha256"] = "sha256:" + "6" * 64
        with self.assertRaisesRegex(ValueError, "validation capture differs"):
            gate.verify_metadata(self.metadata, [wrong_object])
        changed = deepcopy(self.validation)
        changed["receipt"]["producer"]["runId"] += 1
        changed["receiptBytes"] = canonical_json_bytes(changed["receipt"])
        changed["receiptSha256"] = sha256_bytes(changed["receiptBytes"])
        with self.assertRaisesRegex(ValueError, "validation capture differs"):
            gate.verify_metadata(self.metadata, [changed])

    def test_envelope_policy_and_carrier_lifetimes_are_rechecked(self):
        real = original.verified_retained_sdk_android_metadata

        @contextmanager
        def mutate_envelope(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                self.metadata["objectSha256"] = "sha256:" + "7" * 64

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_envelope), self.assertRaisesRegex(ValueError, "changed"):
            self.make().verify_metadata(self.metadata, [self.validation])
        self.metadata["objectSha256"] = verify_phase_shard(
            self.f.worker / "shard", admission._METADATA)["objectSha256"]

        @contextmanager
        def mutate_policy(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                self.policy["trustedSourceCommit"] = "9" * 40

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_policy), self.assertRaisesRegex(ValueError, "changed"):
            self.make().verify_metadata(self.metadata, [self.validation])
        self.policy["trustedSourceCommit"] = "e" * 40

        @contextmanager
        def mutate_carrier(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                carrier_log.write_bytes(b"late mutation")

        carrier_log = (self.carrier / self.records[0]["captureRoot"] /
                       "original/worker/gradle.log")
        carrier_log_bytes = carrier_log.read_bytes()
        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_carrier), self.assertRaisesRegex(ValueError, "changed"):
            self.make().verify_metadata(self.metadata, [self.validation])
        carrier_log.write_bytes(carrier_log_bytes)

        @contextmanager
        def mutate_validation_capture(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
            (self.f.f.original_capture / "late-mutation.bin").write_bytes(
                b"late external validation mutation")

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_validation_capture), self.assertRaisesRegex(
                              ValueError, "validation capture changed"):
            self.make().verify_metadata(self.metadata, [self.validation])

    def test_forwarded_arguments_predecessor_and_returned_mapping_are_guarded(self):
        real = original.verified_retained_sdk_android_metadata
        gate = self.make()

        @contextmanager
        def mutate_arguments(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                gate._arguments["trusted_source_commit"] = "9" * 40

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_arguments), self.assertRaisesRegex(ValueError, "changed"):
            gate.verify_metadata(self.metadata, [self.validation])

        predecessors = [self.validation]
        @contextmanager
        def replace_predecessor(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                predecessors[0] = self.metadata

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=replace_predecessor), self.assertRaisesRegex(ValueError, "changed"):
            self.make().verify_metadata(self.metadata, predecessors)

        @contextmanager
        def mutate_returned(*args, **kwargs):
            with real(*args, **kwargs) as value:
                yield value
                value["transport"]["observed"].append({"late": True})

        with patch.object(original, "verified_retained_sdk_android_metadata",
                          side_effect=mutate_returned), self.assertRaisesRegex(ValueError, "changed"):
            self.make().verify_metadata(self.metadata, [self.validation])

    def test_records_and_caller_policy_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "sorted and unique"):
            self.make(records=[self.records[0], self.records[0]])
        escaped = [{**self.records[0], "captureRoot": "../outside"}]
        with self.assertRaisesRegex(ValueError, "not normalized"):
            self.make(records=escaped)
        release = {**self.policy, "toolingTrustDomain": "release"}
        with self.assertRaisesRegex(ValueError, "keyring pair"):
            self.make(policy=release)
        extra = {**self.policy, "accepted": True}
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            self.make(policy=extra)


if __name__ == "__main__":
    unittest.main()
