"""Transport-only checks for an observed original iOS package upload.

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
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


capture = fixture.capture
JOB = "product-validation / sdk-sdk-ios-package-ios"


class SdkIosPackageUploadTest(unittest.TestCase):
    # Reuse only the compact synthetic official-API setup, not its test methods.
    api = fixture.RuntimeAggregateUploadTest.api
    archive = fixture.RuntimeAggregateUploadTest.archive

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = JOB
        stage = self.root / "original-stage"
        (stage / "outputs/apple").mkdir(parents=True)
        (stage / "outputs/apple/CodexAgentPackage-0.3.0.zip").write_bytes(
            b"opaque original iOS package bytes\x00\xff"
        )
        manifest = write_output_manifest(
            stage, "sdk", "sdk-ios", "package", "ios", "0.3.0",
            {"apple": "outputs/apple"},
        )
        selected = write_receipt(
            self.root / "selected-package-receipt.json",
            product="sdk", component="sdk-ios", phase="package", target="ios",
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
            "package-execution/events/00-toolchain-before-xcode/combined.bin": b"",
            # Transport capture does not independently interpret this descriptor.
            "apple-package-execution.json": b"opaque descriptor retained for later admission\n",
        }
        self.artifact["name"] = (
            "codex-agent-sdk-worker-sdk-ios-package-ios-"
            f"{selected['buildKey'].removeprefix('sha256:')}-{self.producer['tree']}-attempt-2"
        )
        self.original_plan = self.plan_path.read_bytes()
        self.archive()

    def call(self, **changes):
        arguments = {
            "package_receipt_path": self.receipt_path,
            "artifact_id": 701,
            "artifact_sha256": self.artifact["digest"],
            "trusted_workflow_sha": self.pin,
            "repository_root": self.root,
            "environ": {"GITHUB_RUN_ID": "unrelated-current-run"},
            "token": "synthetic-token",
            **changes,
        }
        with patch.object(capture, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return capture.capture_sdk_ios_package_upload(
                self.plan_path, self.output, **arguments,
            )

    def test_exact_original_archive_plan_shard_and_empty_streams_are_preserved(self):
        source_before = regular_file_inventory(self.root, allow_empty=True)
        result = self.call()
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.artifact, result["artifact"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(sha256_bytes(self.receipt_bytes), result["packageReceiptSha256"])
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
            if case == "job": self.jobs[0]["name"] = "product-validation / sdk-sdk-ios-binary-ios"
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

    def test_selected_and_uploaded_receipts_must_be_the_same_exact_package(self):
        changed = canonical_json_bytes({**json.loads(self.receipt_bytes), "trustDomain": "release"})
        self.receipt_path.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "selected original receipt"):
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


if __name__ == "__main__":
    unittest.main()
