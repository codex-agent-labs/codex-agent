"""Android original-reader orchestration tests; official transport/tools are mocked."""

from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_workflow as metadata
from ci import sdk_android_original_validation as original
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
)
from ci.tests import test_sdk_android_metadata_workflow as fixture


class OriginalAndroidValidationTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.AndroidMetadataWorkflowTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        for identity in original.product_reuse._dependency_closure((original._INSTANCE,)):
            if identity == original._INSTANCE:
                continue
            name = "-".join((identity.product, identity.component,
                             identity.phase, identity.target))
            directory = self.f.original / "inputs" / name
            if directory.exists():
                continue
            payload = directory / "stage/outputs/mock.bin"
            payload.parent.mkdir(parents=True)
            payload.write_bytes((name + " mocked predecessor\n").encode())
            manifest = fixture.write_output_manifest(
                directory / "stage", identity.product, identity.component,
                identity.phase, identity.target, self.f.version,
                {"mocked-predecessor": "outputs"})
            fixture.write_receipt(
                directory / "phase-receipt.json", product=identity.product,
                component=identity.component, phase=identity.phase,
                target=identity.target, version=self.f.version,
                version_identity=self.f.version, outputs=manifest["outputs"],
                upstream=[], context={"producer": self.f.binary_producer})
        self.raw = self.f.validation_receipt.read_bytes()
        self.environment = {"GITHUB_RUN_ID": "41", "GITHUB_RUN_ATTEMPT": "8"}
        self.transport = {
            "artifact": {"id": 701, "name": "synthetic Android validation upload"},
            "captureProducer": deepcopy(self.f.validation_producer), "observed": [],
            "validationReceiptSha256": sha256_bytes(self.raw),
        }
        self.shard = {
            "receiptBytes": self.raw, "objectPath": "objects/object.zip",
            "buildKey": self.f.validation["buildKey"],
            "receiptSha256": sha256_file(self.f.validation_receipt),
            "objectSha256": "sha256:" + "0" * 64,
        }
        self.events = []
        self.arguments = dict(
            package_stage=self.f.package_stage, package_receipt=self.f.package_receipt,
            binary_stage=self.f.binary_stage, binary_receipt=self.f.binary_receipt,
            compatibility_request=self.f.compatibility,
            binary_contract_evidence=self.f.contract_evidence,
            trusted_source_commit="e" * 40, trusted_source_tree="f" * 40,
            tooling_evidence=self.f.tooling, tooling_public_key=self.f.tooling_key,
            java_executable=self.f.java, apkanalyzer_executable=self.f.analyzer,
            policy_revision="1" * 40, required_trust_domain="development",
            repository_root=self.f.root, environ=self.environment,
        )

    def capture(self, plan, destination, **kwargs):
        self.events.append("capture")
        self.assertEqual(self.f.plan, plan)
        self.assertEqual(self.raw, Path(kwargs["validation_receipt_path"]).read_bytes())
        if hasattr(self, "expected_route"):
            self.assertEqual(self.expected_route, (
                kwargs["trusted_workflow_path"], kwargs["trusted_job_name"]))
        destination.mkdir()
        shutil.copytree(self.f.original, destination / "original")
        (destination / "transport.zip").write_bytes(b"opaque official ZIP fixture")
        captured_plan = destination / "plan/impact-plan.json"
        captured_plan.parent.mkdir()
        captured_plan.write_bytes(self.f.plan.read_bytes())
        (destination / "capture-transport.json").write_bytes(
            canonical_json_bytes(self.transport))
        return deepcopy(self.transport)

    def restore(self, object_path, stage, **kwargs):
        self.events.append("restore")
        shutil.copytree(self.f.validation_stage, stage)
        return {"receiptBytes": self.raw}

    def compare(self, *args, **kwargs):
        self.events.append("compare")
        return self.compare_original(*args, **kwargs)

    def replan(self, repository, receipt, package):
        self.events.append("replan")
        self.assertEqual(self.f.root, repository)
        self.assertEqual(self.f.validation, receipt)
        self.assertEqual(self.f.package, package)

    def replay(self, **kwargs):
        self.events.append("full-replay")
        self.assertEqual(self.f.validation_producer, kwargs["expected_capture_producer"])
        self.assertEqual(self.f.binary_producer, kwargs["expected_original_producer"])
        shutil.copytree(self.f.validation_stage, kwargs["destination"])

    def context(self, *, retained=None, **changes):
        arguments = {**self.arguments, **changes}
        if retained is None:
            return original.verified_original_android_validation(
                self.f.plan, self.f.validation_receipt,
                artifact_id=701, artifact_sha256="sha256:" + "7" * 64,
                trusted_workflow_sha="8" * 40, token="synthetic-token", **arguments)
        return original.verified_retained_android_validation(
            self.f.plan, self.f.validation_receipt,
            validation_capture=retained, **arguments)

    def enter_reader(self, *, retained=None, replay=None, transport=None, **changes):
        self.compare_original = metadata._compare_original_inputs
        stack = self.enterContext
        stack(patch.object(original, "_request_inventory",
                           side_effect=lambda path: {Path(path): sha256_file(Path(path))}))
        stack(patch.object(metadata, "stage_sdk_inputs", side_effect=self.f.stage_inputs))
        stack(patch.object(original, "capture_sdk_android_validation_upload",
                           side_effect=self.capture if transport is None else transport))
        stack(patch.object(original, "verify_retained_sdk_phase_upload",
                           side_effect=lambda capture, raw: self.events.append("retained-transport")))
        stack(patch.object(original, "verify_phase_shard", return_value=self.shard))
        stack(patch.object(original, "restore_object", side_effect=self.restore))
        stack(patch.object(original, "_compare_original_inputs", side_effect=self.compare))
        stack(patch.object(original, "_replan", side_effect=self.replan))
        stack(patch.object(original.validation_phase, "produce_sdk_android_validation_phase",
                           side_effect=self.replay if replay is None else replay))
        return self.context(retained=retained, **changes)

    def test_official_capture_full_replay_and_context_lifetime(self):
        with self.enter_reader() as value:
            self.assertEqual(["capture", "restore", "compare", "replan", "full-replay"], self.events)
            self.assertEqual(self.raw, value["receiptBytes"])
            self.assertEqual(self.f.validation, value["receipt"])
            self.assertEqual(regular_file_inventory(self.f.validation_stage),
                             regular_file_inventory(value["stage"]))
            stage = value["stage"]
        self.assertFalse(stage.exists())

    def test_official_child_route_is_forwarded_as_a_pair(self):
        self.expected_route = (
            ".github/workflows/sdk-android-validation.yml",
            "product-validation / sdk-android-validation-result / sdk-android-validation-android",
        )
        with self.enter_reader(trusted_workflow_path=self.expected_route[0],
                               trusted_job_name=self.expected_route[1]):
            pass
        with self.assertRaisesRegex(ValueError, "pinned together"), self.enter_reader(
                trusted_workflow_path=self.expected_route[0]):
            pass

    def test_retained_carrier_is_checked_but_never_selects_policy(self):
        retained = self.f.root / "retained-validation"
        self.capture(self.f.plan, retained,
                     validation_receipt_path=self.f.validation_receipt)
        self.events.clear()
        with self.enter_reader(retained=retained) as value:
            self.assertEqual("development", self.arguments["required_trust_domain"])
            self.assertEqual(self.raw, value["receiptPath"].read_bytes())
        self.assertEqual("retained-transport", self.events[0])
        self.assertNotIn("capture", self.events)

    def test_transport_identity_is_mandatory(self):
        changed = deepcopy(self.transport)
        changed["captureProducer"]["runAttempt"] += 1
        def wrong_transport(plan, destination, **kwargs):
            self.capture(plan, destination, **kwargs)
            (destination / "capture-transport.json").write_bytes(canonical_json_bytes(changed))
            return changed
        with self.assertRaisesRegex(ValueError, "transport differs"), \
                self.enter_reader(transport=wrong_transport):
            pass

    def test_full_dependency_closure_layout_is_exact(self):
        dependencies = [value for value in
            original.product_reuse._dependency_closure((original._INSTANCE,))
            if value != original._INSTANCE]
        victim = next(value for value in dependencies if value.component not in {"sdk-android"})
        name = "-".join((victim.product, victim.component, victim.phase, victim.target))
        shutil.rmtree(self.f.original / "inputs" / name)
        with self.assertRaisesRegex(ValueError, "unexpected layout"), self.enter_reader():
            pass

    def test_extra_dependency_root_is_rejected(self):
        (self.f.original / "inputs/unrequested-predecessor").mkdir()
        with self.assertRaisesRegex(ValueError, "unexpected layout"), self.enter_reader():
            pass

    def test_full_replay_is_mandatory(self):
        with self.assertRaisesRegex(ValueError, "semantic replay failed"), \
                self.enter_reader(replay=ValueError("semantic replay failed")):
            pass

    def test_mutation_during_gate_is_rejected(self):
        def mutate(**kwargs):
            self.replay(**kwargs)
            self.f.tooling_key.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed during recovery"), \
                self.enter_reader(replay=mutate):
            pass

    def test_mutation_during_caller_use_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "changed during recovery"):
            with self.enter_reader() as value:
                (value["original"] / "originals/final/evidence").write_bytes(b"changed")

    def test_yielded_package_receipt_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValueError, "changed during recovery"):
            with self.enter_reader() as value:
                value["packageReceipt"]["producer"]["runAttempt"] += 1


if __name__ == "__main__":
    unittest.main()
