"""Real observer, bounded ZIP and shard checks with synthetic official HTTP.

Runner labels prove observed routing only, not hardware or compiler execution.
No network request or semantic admission occurs in these fixtures.
"""

from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_upload as fixture
from ci import sdk_facade_capture as facade
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.registry import SDK_FACADE_TARGETS
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


class FacadeCaptureTest(unittest.TestCase):
    component = "sdk-core"
    phase = "validation"
    capture_name = "capture_sdk_facade_validation_upload"
    targets = SDK_FACADE_TARGETS
    required_directories = ("worker", "context")
    api = fixture.RuntimeAggregateUploadTest.api
    archive = fixture.RuntimeAggregateUploadTest.archive

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.records = {}
        self.select(self.targets[0])
        self.original_plan = self.plan_path.read_bytes()

    def select(self, target):
        if target not in self.records:
            stage = self.root / f"original-stage-{target}"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/result.json").write_bytes(b'{"synthetic":"no content proof"}\n')
            manifest = write_output_manifest(stage, "sdk", self.component, self.phase, target, "0.8.0",
                                             {f"sdk-facade-{self.phase}-content": "outputs"})
            selected = write_receipt(self.root / f"selected-{target}.json", product="sdk", component=self.component,
                phase=self.phase, target=target, outputs=manifest["outputs"], upstream=[], version="0.8.0",
                version_identity="0.8.0", context={"producer": self.producer})
            shard = self.root / f"shard-{target}"
            descriptor = finalize_phase_object(stage_root=stage, phase_plan={key: selected[key] for key in PHASE_PLAN_KEYS},
                producer=self.producer, product_version="0.8.0", trust_domain="development", destination=shard)
            files = {f"shard/{row['relativePath']}": (shard / row["relativePath"]).read_bytes()
                     for row in regular_file_inventory(shard)}
            files.update({"worker/execution.json": b'{"opaque":"not interpreted"}\n', "worker/gradle.log": b"",
                "context/execution.json": b'{"opaque":"caller must authenticate"}\n',
                "retained-execution/process/stderr.bin": b"", "selection/phase.json": canonical_json_bytes(selected),
                "inputs/original.bin": b"full original bytes preserved\x00\xff",
                "originals/original.bin": b"opaque full original proof",
                **{directory + "/retained.bin": b"opaque retained proof" for directory in self.required_directories}})
            self.records[target] = (shard / "phase-receipt.json", descriptor["receiptBytes"], selected, files)
        self.receipt_path, self.receipt_bytes, self.receipt, self.files = deepcopy(self.records[target])
        self.jobs[0].update(name=f"product-validation / {self.component}-{self.phase}-{target}", runner_id=19,
                            labels=[facade._capture_route(self.receipt)[1]])
        self.artifact["name"] = (f"codex-agent-sdk-worker-{self.component}-{self.phase}-{target}-"
            f"{self.receipt['buildKey'].removeprefix('sha256:')}-{self.producer['tree']}-attempt-{self.producer['runAttempt']}")
        self.archive()

    def call(self, **changes):
        arguments = dict(artifact_id=701,
            artifact_sha256=self.artifact["digest"], trusted_workflow_sha=self.pin,
            repository_root=self.root, environ={"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "99"},
            token="synthetic-token")
        arguments["receipt_path" if self.capture_name == "capture_sdk_maven_upload" else
                  self.phase + "_receipt_path"] = self.receipt_path
        arguments.update(changes)
        with patch.object(facade.products, "_validate_plan", return_value=self.plan), \
             patch("reuse.api_request", side_effect=self.api):
            capture = getattr(facade, self.capture_name)
            return capture(self.plan_path, self.output, **arguments)

    def test_all_targets_retain_original_producer_complete_upload_and_official_observation(self):
        for target in self.targets:
            self.select(target)
            before = regular_file_inventory(self.root, allow_empty=True)
            with self.subTest(target=target):
                result = self.call()
                self.assertEqual(self.producer, result["captureProducer"])
                self.assertEqual(self.run, result["observed"][0]["run"])
                self.assertEqual(self.jobs[0]["labels"], result["observed"][0]["jobs"][0]["labels"])
                self.assertEqual(sha256_bytes(self.receipt_bytes), result[self.phase + "ReceiptSha256"])
                self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
                self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
                self.assertEqual(sorted(self.files), [row["relativePath"] for row in
                    regular_file_inventory(self.output / "original", allow_empty=True)])
                for name, raw in self.files.items():
                    self.assertEqual(raw, (self.output / "original" / name).read_bytes())
                self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
                facade.verify_retained_sdk_phase_upload(self.output, self.receipt_bytes)
                shutil.rmtree(self.output)

    def test_original_job_route_matches_declared_core_workflow_name(self):
        if self.component != "sdk-core":
            self.skipTest("Android worker jobs are not wired yet")
        workflow_name = (f"sdk-core-{self.phase}-validation.yml" if self.phase in ("binary", "package")
                         else "product-validation.yml")
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows" / workflow_name).read_text()
        target = "${{ matrix.target }}" if self.phase == "validation" else "common"
        self.assertIn(f"    name: sdk-core-{self.phase}-{target}\n", workflow)
        self.assertEqual(f"product-validation / sdk-core-{self.phase}-{self.targets[0]}",
                         facade._capture_route(self.receipt)[3])

    def test_fixed_job_attempt_source_pin_runner_and_window_are_mandatory(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        for case in ("job", "failed", "attempt", "pin", "tree", "runner", "missing-runner", "runner-id", "boolean-id", "window", "artifact"):
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "job": self.jobs[0]["name"] += "-other"
            elif case == "failed": self.jobs[0]["conclusion"] = "failure"
            elif case == "attempt": self.run["run_attempt"] += 1
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "tree": self.commit["tree"]["sha"] = "f" * 40
            elif case == "runner": self.jobs[0]["labels"] = ["unrelated-runner"]
            elif case == "missing-runner": self.jobs[0].pop("labels")
            elif case == "runner-id": self.jobs[0]["runner_id"] = 0
            elif case == "boolean-id": self.jobs[0]["runner_id"] = True
            elif case == "window": self.artifact["created_at"] = "2026-09-11T10:30:01Z"
            else: self.artifact["name"] += "-other"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_other_phase_receipt_cannot_select_a_different_capture_route(self):
        phase = "metadata" if self.phase == "validation" else "validation"
        capture = getattr(facade, "capture_sdk_facade_" + phase + "_upload")
        with patch.object(facade.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            capture(self.plan_path, self.output, **{phase + "_receipt_path": self.receipt_path},
                artifact_id=701, artifact_sha256=self.artifact["digest"], trusted_workflow_sha=self.pin,
                repository_root=self.root, environ={}, token="synthetic-token")
        observe.assert_not_called()

    def test_selected_receipt_and_retained_required_directories_cannot_be_substituted(self):
        self.receipt_path.write_bytes(canonical_json_bytes({**self.receipt, "trustDomain": "release"}))
        with self.assertRaisesRegex(ValueError, "selected original receipt"):
            self.call()
        self.receipt_path.write_bytes(self.receipt_bytes)
        original = deepcopy(self.files)
        for directory in self.required_directories:
            self.files = {name: raw for name, raw in original.items() if not name.startswith(directory + "/")}
            self.archive()
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_late_original_or_extracted_bytes_change_never_publish(self):
        window = facade.products._require_artifact_job_window
        for path in (self.plan_path, self.receipt_path):
            before = path.read_bytes()
            def mutate(*args):
                window(*args)
                path.write_bytes(before + b"changed\n")
            try:
                with patch.object(facade.products, "_require_artifact_job_window", side_effect=mutate), self.assertRaises(ValueError):
                    self.call()
                self.assertFalse(self.output.exists())
            finally:
                path.write_bytes(before)
        extract = facade.products.safe_extract
        def mutate_extraction(archive, destination, *args, **kwargs):
            extract(archive, destination, *args, **kwargs)
            (destination / "worker/gradle.log").write_bytes(b"changed after extraction")
        with patch.object(facade.products, "safe_extract", side_effect=mutate_extraction), self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())

    def test_invalid_authority_or_unsafe_destination_rejects_before_observation(self):
        for changes in ({"artifact_id": True}, {"artifact_sha256": "bad"}, {"token": ""},
                        {"environ": {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}}):
            with self.subTest(changes=changes), patch.object(facade.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()

        self.plan["remoteBuildAuthorized"] = False
        with patch.object(facade.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()
        self.plan["remoteBuildAuthorized"] = True
        for destination in (self.root / "build/capture", self.receipt_path):
            self.output = destination
            with self.subTest(destination=destination), patch.object(facade.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

    def test_retained_carrier_is_read_only_and_rejects_replacement(self):
        self.call()
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(facade.products, "_observe_ci_producer_jobs") as observe:
            facade.verify_retained_sdk_phase_upload(self.output, self.receipt_bytes)
        observe.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))
        path = self.output / "original/worker/gradle.log"
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "original archive"):
            facade.verify_retained_sdk_phase_upload(self.output, self.receipt_bytes)


class FacadeMetadataCaptureTest(FacadeCaptureTest):
    phase = "metadata"
    capture_name = "capture_sdk_facade_metadata_upload"
    targets = ("common",)
    required_directories = ("worker", "selection", "originals", "inputs")


class AndroidValidationCaptureTest(FacadeCaptureTest):
    component = "sdk-android"
    capture_name = "capture_sdk_android_validation_upload"
    targets = ("android",)
    required_directories = ("inputs", "originals", "stage")


class AndroidMetadataCaptureTest(AndroidValidationCaptureTest):
    phase = "metadata"
    capture_name = "capture_sdk_android_metadata_upload"
    required_directories = ("worker", "selection", "originals", "inputs")


class CoreBinaryCaptureTest(FacadeCaptureTest):
    phase = "binary"
    capture_name = "capture_sdk_maven_upload"
    targets = ("common",)
    required_directories = ("inputs", "worker", "selection")

    def test_paired_caller_pinned_child_route(self):
        if self.component != "sdk-core" or self.phase not in ("binary", "package"):
            self.skipTest("Only Core binary/package use child workflows")
        path = f".github/workflows/sdk-core-{self.phase}-validation.yml"
        job = f"product-validation / sdk-core-{self.phase}-wave / sdk-core-{self.phase}-common"
        self.run["referenced_workflows"][0]["path"] = (
            f"codex-agent-labs/codex-agent/{path}@{self.pin}")
        self.jobs[0]["name"] = job
        self.call(trusted_workflow_path=path, trusted_job_name=job)
        shutil.rmtree(self.output)
        with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
            self.call(trusted_workflow_path=".github/workflows/product-validation.yml",
                trusted_job_name=job)
        with self.assertRaisesRegex(ValueError, "pinned together"):
            self.call(trusted_workflow_path=path)
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.call(trusted_workflow_path=path, trusted_job_name=job + "-wrong")


class AndroidBinaryCaptureTest(CoreBinaryCaptureTest):
    component = "sdk-android"
    targets = ("android",)
    required_directories = (*CoreBinaryCaptureTest.required_directories, "android-original")


class CorePackageCaptureTest(CoreBinaryCaptureTest):
    phase = "package"
    required_directories = (*CoreBinaryCaptureTest.required_directories, "sdk-inputs-original", "binary-contract-original", "binary-original")


class AndroidPackageCaptureTest(CorePackageCaptureTest):
    component = "sdk-android"
    targets = ("android",)
