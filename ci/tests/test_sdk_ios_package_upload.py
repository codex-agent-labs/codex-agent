"""Transport-only checks for observed original iOS package and binary uploads.

The local plan and official API responses are synthetic.  These tests exercise
the existing plan, observation, ZIP, and phase-shard gates, but deliberately do
not treat retained execution or descriptor bytes as package-content admission.
"""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import write_receipt
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, regular_file_inventory, sha256_bytes, snapshot_regular_tree,
)
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


capture = fixture.capture


class SdkIosPackageUploadTest(unittest.TestCase):
    # Reuse only the compact synthetic official-API setup, not its test methods.
    api = fixture.RuntimeAggregateUploadTest.api
    archive = fixture.RuntimeAggregateUploadTest.archive
    phase = "package"
    target = "ios"

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = f"product-validation / sdk-sdk-ios-{self.phase}-{self.target}"
        stage = self.root / f"original-{self.phase}-stage"
        if self.phase == "package":
            (stage / "outputs/apple").mkdir(parents=True)
            (stage / "outputs/apple/CodexAgentPackage-0.3.0.zip").write_bytes(
                b"opaque original iOS package bytes\x00\xff"
            )
            output_roots = {"apple": "outputs/apple"}
        elif self.phase == "validation":
            (stage / "outputs/validation").mkdir(parents=True)
            (stage / "outputs/validation/apple-validation.json").write_bytes(b"opaque semantic content\n")
            output_roots = {"apple-validation-content": "outputs/validation"}
        else:
            for target, contents in (
                ("ios-arm64", b"original device framework\x00\xff"),
                ("ios-simulator-arm64", b"original simulator framework\x00\xff"),
            ):
                framework = stage / f"outputs/apple-binary/{target}/CodexAgent.framework"
                framework.mkdir(parents=True)
                (framework / "CodexAgent").write_bytes(contents)
            output_roots = {"apple-binary": "outputs/apple-binary"}
        manifest = write_output_manifest(
            stage, "sdk", "sdk-ios", self.phase, self.target, "0.3.0", output_roots,
        )
        selected = write_receipt(
            self.root / f"selected-{self.phase}-receipt.json",
            product="sdk", component="sdk-ios", phase=self.phase, target=self.target,
            outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer},
        )
        phase = {name: selected[name] for name in PHASE_PLAN_KEYS}
        shard = self.root / "original-shard"
        descriptor = finalize_phase_object(
            stage_root=stage, phase_plan=phase, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=shard,
        )
        self.receipt_path = shard / "phase-receipt.json"
        self.receipt_bytes = descriptor["receiptBytes"]
        self.files = {
            **{
                f"shard/{row['relativePath']}": (shard / row["relativePath"]).read_bytes()
                for row in regular_file_inventory(shard)
            },
            "worker/gradle.log": b"",
            "worker/stdout.bin": b"",
            "worker/stderr.bin": b"original stderr bytes\x00\xff",
        }
        if self.phase == "package":
            self.files.update({
                "package-execution/events/00-toolchain-before-xcode/combined.bin": b"",
                # Transport capture does not independently interpret this descriptor.
                "apple-package-execution.json": b"opaque descriptor retained for later admission\n",
            })
        elif self.phase == "validation":
            self.files.update({
                "context/execution-context.json": b"opaque context for independent replay\n",
                "execution/apple-validation-evidence.zip": b"opaque original execution archive\x00\xff",
                "originals/package/transport.zip": b"original package upload",
            })
        else:
            self.files.update({
                "native-original/ios-rust-device/codex-agent-ios-arm64.a":
                    b"!<arch>\noriginal native archive\x00\xff",
                "native-original/ios-rust-device/stdout.bin": b"",
                "native-original/ios-rust-simulator/stderr.bin": b"",
            })
        self.artifact["name"] = (
            f"codex-agent-sdk-worker-sdk-ios-{self.phase}-{self.target}-"
            f"{selected['buildKey'].removeprefix('sha256:')}-{self.producer['tree']}-attempt-2"
        )
        self.receipt_hash_field = f"{self.phase}ReceiptSha256"
        self.original_plan = self.plan_path.read_bytes()
        self.archive()

    def call(self, **changes):
        arguments = {
            f"{self.phase}_receipt_path": self.receipt_path,
            "artifact_id": 701,
            "artifact_sha256": self.artifact["digest"],
            "trusted_workflow_sha": self.pin,
            "repository_root": self.root,
            "environ": {"GITHUB_RUN_ID": "unrelated-current-run"},
            "token": "synthetic-token",
            **changes,
        }
        with patch.object(capture, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=self.api), \
                patch.object(capture, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs:
                        Path(destination).write_bytes(self.raw)):
            return getattr(capture, f"capture_sdk_ios_{self.phase}_upload")(
                self.plan_path, self.output, **arguments,
            )

    def test_retained_upload_consistency_preserves_bytes_without_observation(self):
        self.call()
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(capture, "_observe_ci_producer_jobs", side_effect=AssertionError("network")), \
                patch.object(capture, "_download_contract_ci_upload", side_effect=AssertionError("network")):
            capture.verify_retained_sdk_ios_upload(self.output, self.receipt_bytes)
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))

    def test_retained_upload_rejects_archive_materialization_and_identity_mutations(self):
        self.call()
        for index, mutation in enumerate(("archive", "original", "plan-extra", "root-extra", "producer", "receipt", "name", "id")):
            copied = self.work / f"retained-upload-{index}"
            snapshot_regular_tree(self.output, copied, allow_empty=True)
            if mutation in {"archive", "original", "plan-extra", "root-extra"}:
                path = {"archive": "transport.zip", "original": "original/worker/gradle.log",
                        "plan-extra": "plan/extra", "root-extra": "extra"}[mutation]
                (copied / path).write_bytes(b"changed")
            else:
                path = copied / "capture-transport.json"
                value = json.loads(path.read_bytes())
                if mutation == "producer":
                    value["captureProducer"]["runAttempt"] += 1
                elif mutation == "receipt":
                    value[self.receipt_hash_field] = "sha256:" + "0" * 64
                elif mutation == "name":
                    value["artifact"]["name"] = "another-artifact"
                else:
                    value["artifact"]["id"] = False
                path.write_bytes(canonical_json_bytes(value))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                capture.verify_retained_sdk_ios_upload(copied, self.receipt_bytes)

    def test_exact_original_archive_plan_shard_and_empty_streams_are_preserved(self):
        source_before = regular_file_inventory(self.root, allow_empty=True)
        result = self.call()
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.artifact, result["artifact"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(sha256_bytes(self.receipt_bytes), result[self.receipt_hash_field])
        self.assertEqual(result, json.loads((self.output / "capture-transport.json").read_bytes()))
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
        self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
        self.assertEqual(
            sorted(self.files),
            [row["relativePath"] for row in regular_file_inventory(self.output / "original", allow_empty=True)],
        )
        for name, raw in self.files.items():
            self.assertEqual(raw, (self.output / "original" / name).read_bytes(), name)
        self.assertEqual(source_before, regular_file_inventory(self.root, allow_empty=True))

    def test_job_attempt_pin_window_digest_and_name_are_exact(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        for case in ("job", "job-failed", "attempt", "pin", "artifact-run", "artifact-head",
                     "name", "digest", "before", "after", "tree"):
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "job":
                other = "binary" if self.phase == "package" else "package"
                self.jobs[0]["name"] = f"product-validation / sdk-sdk-ios-{other}-ios"
            elif case == "job-failed": self.jobs[0]["conclusion"] = "failure"
            elif case == "attempt": self.run["run_attempt"] = 1
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "artifact-run": self.artifact["workflow_run"]["id"] = 72
            elif case == "artifact-head": self.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif case == "name": self.artifact["name"] += "-wrong"
            elif case == "digest": self.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "before": self.artifact["created_at"] = "2026-09-11T09:59:59Z"
            elif case == "after": self.artifact["created_at"] = "2026-09-11T10:30:01Z"
            else: self.commit["tree"]["sha"] = "e" * 40
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_selected_and_uploaded_receipts_must_be_the_same_exact_phase(self):
        changed = canonical_json_bytes({**json.loads(self.receipt_bytes), "trustDomain": "release"})
        self.receipt_path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "selected original"):
            self.call()
        self.assertFalse(self.output.exists())
        self.receipt_path.write_bytes(self.receipt_bytes)

        uploaded = self.files["shard/phase-receipt.json"]
        self.files["shard/phase-receipt.json"] = canonical_json_bytes(
            {**json.loads(uploaded), "result": "failure"}
        )
        self.archive()
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())

    def test_other_ios_phase_receipt_rejects_before_observation(self):
        other = "binary" if self.phase == "package" else "package"
        wrong_path = self.root / f"wrong-{other}-receipt.json"
        wrong = write_receipt(
            wrong_path, product="sdk", component="sdk-ios", phase=other, target="ios",
            outputs=json.loads(self.receipt_bytes)["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer},
        )
        original = self.receipt_path.read_bytes()
        self.receipt_path.write_bytes(wrong_path.read_bytes())
        try:
            with patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaisesRegex(ValueError, f"original {self.phase} receipt"):
                self.call()
            observe.assert_not_called()
            self.assertEqual(other, wrong["phase"])
            self.assertFalse(self.output.exists())
        finally:
            self.receipt_path.write_bytes(original)

    def test_phase_incompatible_target_rejects_before_observation(self):
        receipt = json.loads(self.receipt_bytes)
        receipt["target"] = "ios" if self.phase == "validation" else "ios-arm64"
        self.receipt_path.write_bytes(canonical_json_bytes(receipt))
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_late_plan_receipt_and_archive_mutations_never_publish(self):
        gate = capture._require_artifact_job_window
        for case in ("plan", "receipt"):
            def mutate(*arguments):
                gate(*arguments)
                path = {"plan": self.plan_path, "receipt": self.receipt_path}[case]
                path.write_bytes(path.read_bytes() + b"changed after initial verification\n")

            try:
                with self.subTest(case=case), patch.object(
                    capture, "_require_artifact_job_window", side_effect=mutate,
                ), self.assertRaises(ValueError):
                    self.call()
                self.assertFalse(self.output.exists())
            finally:
                self.plan_path.write_bytes(self.original_plan)
                self.receipt_path.write_bytes(self.receipt_bytes)
                self.archive()

        extract = capture.safe_extract

        def mutate_archive(archive, destination, *arguments, **keywords):
            result = extract(archive, destination, *arguments, **keywords)
            archive = Path(archive)
            archive.write_bytes(archive.read_bytes() + b"changed after extraction")
            return result

        with patch.object(capture, "safe_extract", side_effect=mutate_archive), self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())

    def test_late_original_member_mutation_rejects_before_publication(self):
        def mutate_before_copy(source, destination, **kwargs):
            member = source / "original/worker/gradle.log"
            member.write_bytes(b"late mutation\n")
            return publish_regular_tree(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_unauthorized_inputs_and_overlapping_or_existing_outputs_reject_before_http(self):
        for changes in ({"artifact_id": True}, {"artifact_sha256": "bad"}, {"token": ""}):
            with self.subTest(changes=changes), patch.object(
                capture, "_observe_ci_producer_jobs",
            ) as observe, self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()

        self.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()

        self.plan["remoteBuildAuthorized"] = True
        for destination in (self.root / "nested-output", self.receipt_path):
            self.output = destination
            with self.subTest(destination=destination), patch.object(
                capture, "_observe_ci_producer_jobs",
            ) as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

        self.output = self.work / "existing-output"
        self.output.mkdir()
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()


class SdkIosBinaryUploadTest(SdkIosPackageUploadTest):
    phase = "binary"


class SdkIosValidationUploadTest(SdkIosPackageUploadTest):
    phase = "validation"
    target = "ios-arm64"

    def test_other_validation_target_job_and_artifact_are_rejected(self):
        other = "ios-simulator-arm64" if self.target == "ios-arm64" else "ios-arm64"
        original_job = self.jobs[0]["name"]
        self.jobs[0]["name"] = f"product-validation / sdk-sdk-ios-validation-{other}"
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())
        self.jobs[0]["name"] = original_job
        self.artifact["name"] = self.artifact["name"].replace(f"validation-{self.target}-", f"validation-{other}-")
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())


class SdkIosSimulatorValidationUploadTest(SdkIosValidationUploadTest):
    target = "ios-simulator-arm64"


if __name__ == "__main__":
    unittest.main()
