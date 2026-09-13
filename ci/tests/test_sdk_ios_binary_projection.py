"""iOS binary projection/composition, not elected-product or host acceptance."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_state_capture as capture_fixture
from products.inventory import regular_file_inventory, snapshot_regular_tree


IOS = {"product": "sdk", "component": "sdk-ios", "phase": "binary", "target": "ios",
       "buildKey": "sha256:" + "a" * 64}
JS = {"product": "sdk", "component": "javascript", "phase": "package", "target": "node",
      "buildKey": "sha256:" + "b" * 64}
PIN = "c" * 40


class SdkIosBinaryProjectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-projection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / "inputs"
        for name, data in {
            "product-resume-inputs/plan/impact-plan.json": b"exact original plan\n",
            "product-resume-inputs/release/signature.sig": b"original external signature\x00\xff",
            "product-resume-state/original-receipt.json": b"original receipt bytes\n",
            "runtime-state/reuse-wave-result.json": b"previous SDK state\n",
        }.items():
            path = self.inputs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.plan = self.inputs / "product-resume-inputs/plan/impact-plan.json"
        self.discovery = self.inputs / "product-resume-state"
        self.state = self.inputs / "runtime-state"
        self.destination = self.root / "collected"
        self.output = self.root / "github-output"

    def test_only_ios_binary_is_projected_and_default_js_route_is_unchanged(self):
        unrelated = [
            {**IOS, "phase": "package"}, {**IOS, "component": "sdk-core", "target": "common"},
            {**IOS, "phase": "validation", "target": "ios-arm64"},
            {**IOS, "product": "runtime", "component": "runtime-aggregate", "phase": "metadata", "target": "aggregate"},
        ]
        with patch.object(workflow.product_reuse, "inspect_products", return_value={"readyPlans": [*unrelated, JS, IOS]}):
            result = workflow.matrix(self.plan, self.discovery, self.state, self.output,
                                     repository_root=self.root, environ={}, ios_binary=True)
            self.assertEqual({"include": [{**IOS, "runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}]}, result)
            default = workflow.matrix(self.plan, self.discovery, self.state, self.root / "js-output",
                                      repository_root=self.root, environ={})
            self.assertEqual(["javascript"], [row["component"] for row in default["include"]])
            self.assertEqual("ubuntu-24.04", default["include"][0]["runner"])
        with patch.object(workflow.product_reuse, "inspect_products", return_value={"readyPlans": [JS, *unrelated]}):
            self.assertEqual({"include": []}, workflow.matrix(self.plan, self.discovery, self.state,
                self.root / "no-ios-output", repository_root=self.root, environ={}, ios_binary=True))
        self.assertIn("sdk_workers_required=false", (self.root / "no-ios-output").read_text())
        with patch.object(workflow.product_reuse, "inspect_products", return_value={
                "readyPlans": [{**IOS, "target": "ios-arm64"}]}), self.assertRaises(ValueError):
            workflow.matrix(self.plan, self.discovery, self.state, self.root / "malformed-output",
                            repository_root=self.root, environ={}, ios_binary=True)
        self.assertFalse((self.root / "malformed-output").exists())

    def test_invalid_projection_and_collection_scopes_fail_before_shared_work(self):
        for value in (1, "true", None):
            with self.subTest(value=value), patch.object(workflow.product_reuse, "inspect_products") as inspect, \
                    patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as capture:
                with self.assertRaisesRegex(ValueError, "boolean"):
                    workflow.matrix(self.plan, self.discovery, self.state, self.output, ios_binary=value)
                with self.assertRaisesRegex(ValueError, "boolean"):
                    workflow.capture(self.plan, self.destination, self.output, artifact_id=1,
                        artifact_sha256="sha256:" + "d" * 64, trusted_workflow_sha=PIN,
                        repository_root=self.root, environ={}, token="synthetic", ios_binary=value)
                inspect.assert_not_called()
                capture.assert_not_called()
        for wave, ios_binary in ((1, True), (2, True), (3, False), (True, True), (3, 1)):
            with self.subTest(wave=wave, ios_binary=ios_binary), \
                    patch.object(workflow.product_reuse, "collect_runtime_workers") as collect, \
                    self.assertRaisesRegex(ValueError, "wave"):
                workflow.collect(self.inputs, self.destination, self.output, wave=wave, ios_binary=ios_binary,
                    trusted_workflow_sha=PIN, repository_root=self.root, environ={}, token="synthetic")
            collect.assert_not_called()

    def test_capture_forwards_sdk_wave_three_and_replays_ios_projection_from_original_paths(self):
        destination = self.root / "captured"
        def capture(*args, **kwargs):
            snapshot_regular_tree(self.inputs, destination / "original")
        with patch.object(workflow.product_reuse, "capture_runtime_resume_upload", side_effect=capture) as captured, \
                patch.object(workflow.product_reuse, "inspect_products", return_value={"readyPlans": [IOS, JS]}) as inspect:
            result = workflow.capture(self.plan, destination, self.output, artifact_id=51,
                artifact_sha256="sha256:" + "d" * 64, trusted_workflow_sha=PIN, sdk_state_wave=3,
                repository_root=self.root, environ={}, token="synthetic", ios_binary=True)
        captured.assert_called_once_with(self.plan, destination, artifact_id=51,
            artifact_sha256="sha256:" + "d" * 64, trusted_workflow_sha=PIN, state_wave=0, sdk_state_wave=3,
            repository_root=self.root, environ={}, token="synthetic")
        original = destination / "original"
        inspect.assert_called_once_with(original / "product-resume-inputs/plan/impact-plan.json",
            original / "product-resume-state", original / "runtime-state", repository_root=self.root, environ={})
        self.assertEqual(original / "runtime-state", result["state_root"])
        self.assertEqual(["sdk-ios"], [row["component"] for row in result["matrix"]["include"]])
        self.assertEqual(regular_file_inventory(self.inputs), regular_file_inventory(original))

    def collect(self, *, failure=False, remaining=False):
        row = {**IOS, "result": "failure" if failure else "success",
               "shardDirectory": None if failure else "rows/sdk-ios-binary-ios/original/shard"}
        def collect(plan, discovery, state, destination, **kwargs):
            destination.mkdir(parents=True)
            (destination / "diagnostics.bin").write_bytes(b"original collected diagnostics\x00\xff")
            return {"rows": [row]}
        def advance(plan, discovery, state, shards, destination, output, **kwargs):
            destination.mkdir(parents=True)
            (destination / "reuse-wave-result.json").write_bytes(b"new SDK state\n")
            return {"synthetic": "advanced state boundary", "fullReuse": False}
        before = regular_file_inventory(self.inputs)
        with patch.object(workflow.product_reuse, "collect_runtime_workers", side_effect=collect) as collected, \
                patch.object(workflow.product_reuse, "advance_products", side_effect=advance) as advanced, \
                patch.object(workflow, "matrix", return_value={"include": [IOS] if remaining else []}) as matrix:
            if remaining:
                with self.assertRaisesRegex(ValueError, "remain after.*final"):
                    workflow.collect(self.inputs, self.destination, self.output, wave=3, ios_binary=True,
                        trusted_workflow_sha=PIN, repository_root=self.root, environ={}, token="synthetic")
            else:
                result = workflow.collect(self.inputs, self.destination, self.output, wave=3, ios_binary=True,
                    trusted_workflow_sha=PIN, repository_root=self.root, environ={}, token="synthetic")
                self.assertFalse(result["fullReuse"])
        collected.assert_called_once_with(self.plan, self.discovery, self.state, self.destination / "collection",
            trusted_workflow_sha=PIN, repository_root=self.root, environ={}, token="synthetic", sdk_ios_binary_only=True)
        failed = (workflow.PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"),) if failure else ()
        shards = [] if failure else [self.destination / "collection" / row["shardDirectory"]]
        advanced.assert_called_once_with(self.plan, self.discovery, self.state, shards,
            self.destination / "handoff/runtime-state", self.output, repository_root=self.root, environ={},
            failed_instances=failed, sdk_ios_binary_only=True)
        if failure:
            matrix.assert_not_called()
            self.assertIn("sdk_workers_required=false", self.output.read_text())
        else:
            matrix.assert_called_once_with(self.destination / "handoff/product-resume-inputs/plan/impact-plan.json",
                self.destination / "handoff/product-resume-state", self.destination / "handoff/runtime-state",
                self.output, repository_root=self.root, environ={}, ios_binary=True)
        self.assertEqual(before, regular_file_inventory(self.inputs))
        for name in ("product-resume-inputs", "product-resume-state"):
            self.assertEqual(regular_file_inventory(self.inputs / name),
                             regular_file_inventory(self.destination / "handoff" / name))
        self.assertEqual({"product-resume-inputs", "product-resume-state", "runtime-state"},
                         {path.name for path in (self.destination / "handoff").iterdir()})

    def test_collection_uses_only_ios_scope_and_preserves_original_handoff_roots(self):
        self.collect()

    def test_failure_keeps_diagnostics_and_suppresses_next_work_without_completion(self):
        self.collect(failure=True)

    def test_final_ios_wave_rejects_remaining_binary_work(self):
        self.collect(remaining=True)

    def test_sdk_wave_three_uses_actual_original_transport_parser(self):
        support = capture_fixture.SdkStateCaptureTest()
        support.setUp()
        self.addCleanup(support.doCleanups)
        support.job["name"] = "product-validation / sdk-collect-3"
        support.artifact["name"] = support.artifact["name"].replace("sdk-wave-1-state", "sdk-wave-3-state")
        result = support.capture(sdk_state_wave=3)
        self.assertEqual(3, result["sdkStateWave"])
        self.assertNotIn("stateWave", result)
        self.assertEqual(support.source.producer, result["captureProducer"])
        for name, raw in support.contents.items():
            self.assertEqual(raw, (support.destination / "original" / name).read_bytes())

    def test_workflow_cli_forwards_explicit_ios_projection_without_execution(self):
        with patch.object(workflow, "matrix", return_value={"include": []}) as matrix, \
                patch.object(workflow, "execute_ios_binary") as execute:
            self.assertEqual(0, workflow.main(["matrix", "--plan", str(self.plan),
                "--discovery-root", str(self.discovery), "--state-root", str(self.state),
                "--github-output", str(self.output), "--repository-root", str(self.root), "--ios-binary"]))
        self.assertIs(True, matrix.call_args.kwargs["ios_binary"])
        self.assertEqual(self.plan, matrix.call_args.kwargs["plan"])
        self.assertNotIn("token", matrix.call_args.kwargs)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
