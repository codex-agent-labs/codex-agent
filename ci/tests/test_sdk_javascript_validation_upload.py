"""JavaScript validation upload transport checks over a real phase shard.

Local plan replay and official HTTP responses are synthetic.  The existing
observer, job-window, ZIP and phase-shard verifiers run normally; this does not
grant JavaScript content or installed-consumer admission.
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
JOB = "product-validation / sdk-javascript-validation-node"


class SdkJavaScriptValidationUploadTest(unittest.TestCase):
    # Reuse only the compact synthetic official-API setup, not its tests.
    api = fixture.RuntimeAggregateUploadTest.api
    archive = fixture.RuntimeAggregateUploadTest.archive

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = JOB
        stage = self.root / "original-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/result.bin").write_bytes(b"synthetic JavaScript validation output\x00\xff")
        manifest = write_output_manifest(
            stage, "sdk", "javascript", "validation", "node", "0.3.0", {"evidence": "outputs"},
        )
        selected = write_receipt(
            self.root / "selected-validation-receipt.json",
            product="sdk", component="javascript", phase="validation", target="node",
            outputs=manifest["outputs"], upstream=[], version="0.3.0", version_identity="0.3.0",
            context={"producer": self.producer},
        )
        phase = {name: selected[name] for name in PHASE_PLAN_KEYS}
        shard = self.root / "original-shard"
        descriptor = finalize_phase_object(
            stage_root=stage, phase_plan=phase, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=shard,
        )
        self.receipt_path = shard / "phase-receipt.json"
        self.receipt_bytes = descriptor["receiptBytes"]
        self.execution = {
            "schemaVersion": 1,
            "producer": self.producer,
            "buildKey": selected["buildKey"],
            "command": [str(self.root / "gradlew"), "--offline", "ciProductPhase"],
            "returnCode": 0,
            "launchError": None,
            "elapsedNs": 17,
            "workingDirectory": self.root.as_posix(),
        }
        self.files = {
            **{
                f"shard/{row['relativePath']}": (shard / row["relativePath"]).read_bytes()
                for row in regular_file_inventory(shard)
            },
            "worker/execution.json": canonical_json_bytes(self.execution),
            "worker/gradle.log": b"",
            "inputs/original.bin": b"opaque retained input, not content admission\x00\xff",
        }
        self.artifact["name"] = (
            "codex-agent-sdk-worker-javascript-validation-node-"
            f"{selected['buildKey'].removeprefix('sha256:')}-{self.producer['tree']}-attempt-2"
        )
        self.original_plan = self.plan_path.read_bytes()
        self.archive()

    def call(self, **changes):
        arguments = {
            "validation_receipt_path": self.receipt_path,
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
            return capture.capture_sdk_javascript_validation_upload(
                self.plan_path, self.output, **arguments,
            )

    def test_exact_original_shard_archive_plan_and_consumer_directory_are_preserved(self):
        source_before = regular_file_inventory(self.root, allow_empty=True)
        result = self.call()
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.artifact, result["artifact"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(sha256_bytes(self.receipt_bytes), result["validationReceiptSha256"])
        self.assertEqual(
            (self.root / "codex-agent-sdk/build/npm/consumer").as_posix(),
            result["originalConsumerDirectory"],
        )
        self.assertEqual(result, json.loads((self.output / "capture-transport.json").read_bytes()))
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
        self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
        self.assertEqual(self.receipt_bytes, (self.output / "original/shard/phase-receipt.json").read_bytes())
        self.assertEqual(
            sorted(self.files),
            [row["relativePath"] for row in regular_file_inventory(self.output / "original", allow_empty=True)],
        )
        for name, raw in self.files.items():
            self.assertEqual(raw, (self.output / "original" / name).read_bytes(), name)
        self.assertEqual(source_before, regular_file_inventory(self.root, allow_empty=True))

    def test_execution_exact_fields_producer_key_success_command_and_cwd_are_required(self):
        baseline = deepcopy(self.execution)
        cases = (
            "extra", "missing-cwd", "producer", "key", "return", "boolean-return", "launch",
            "missing-task", "duplicate-task", "command-type", "elapsed", "relative-cwd",
            "nonnormal-cwd", "windows-cwd", "control-cwd",
        )
        for case in cases:
            record = deepcopy(baseline)
            if case == "extra": record["success"] = True
            elif case == "missing-cwd": del record["workingDirectory"]
            elif case == "producer": record["producer"]["runAttempt"] = 1
            elif case == "key": record["buildKey"] = "sha256:" + "d" * 64
            elif case == "return": record["returnCode"] = 1
            elif case == "boolean-return": record["returnCode"] = False
            elif case == "launch": record["launchError"] = "not launched"
            elif case == "missing-task": record["command"][-1] = "otherTask"
            elif case == "duplicate-task": record["command"].append("ciProductPhase")
            elif case == "command-type": record["command"] = "ciProductPhase"
            elif case == "elapsed": record["elapsedNs"] = -1
            elif case == "relative-cwd": record["workingDirectory"] = "checkout"
            elif case == "nonnormal-cwd": record["workingDirectory"] = "/checkout/../other"
            elif case == "windows-cwd": record["workingDirectory"] = "C:\\checkout"
            else: record["workingDirectory"] = "/checkout\nother"
            self.files["worker/execution.json"] = canonical_json_bytes(record)
            self.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_observed_job_attempt_artifact_and_upload_window_are_exact(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        for case in ("job", "job-failed", "attempt", "pin", "artifact-run", "artifact-head",
                     "name", "digest", "before", "after", "tree"):
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "job": self.jobs[0]["name"] = "product-validation / sdk-javascript-package-node"
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

    def test_wrong_uploaded_receipt_and_late_original_mutation_never_publish(self):
        crosspaired = {**json.loads(self.receipt_bytes), "trustDomain": "release"}
        self.receipt_path.write_bytes(canonical_json_bytes(crosspaired))
        with self.assertRaisesRegex(ValueError, "selected original receipt"):
            self.call()
        self.assertFalse(self.output.exists())
        self.receipt_path.write_bytes(self.receipt_bytes)

        selected = self.files["shard/phase-receipt.json"]
        self.files["shard/phase-receipt.json"] = canonical_json_bytes({**json.loads(selected), "result": "failure"})
        self.archive()
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())
        self.files["shard/phase-receipt.json"] = selected
        self.archive()

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

    def test_invalid_authority_and_overlapping_or_existing_outputs_reject_before_http(self):
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


if __name__ == "__main__":
    unittest.main()
