"""Apple collection composition with mocked admission/advance, not trust acceptance."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_ios_binary_projection as fixtures
from products.inventory import regular_file_inventory


DEVICE = {"product": "sdk", "component": "sdk-ios", "phase": "validation", "target": "ios-arm64",
          "buildKey": "sha256:" + "a" * 64}
SIMULATOR = {**DEVICE, "target": "ios-simulator-arm64", "buildKey": "sha256:" + "b" * 64}


class AppleCollectionForwardingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SdkIosBinaryProjectionTest(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_matrix_routes_only_both_validation_targets_to_macos_arm64(self):
        f = self.fixture
        unrelated = [fixtures.IOS, {**fixtures.IOS, "phase": "package"}, fixtures.JS,
                     {**DEVICE, "component": "rust", "target": "linux-x64"}]
        with patch.object(workflow.product_reuse, "inspect_products", return_value={
                "readyPlans": [*unrelated, DEVICE, SIMULATOR]}):
            result = workflow.matrix(f.plan, f.discovery, f.state, f.output,
                                     family="ios-validation", repository_root=f.root, environ={})
        self.assertEqual({"include": [{**row, "runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}
                                      for row in (DEVICE, SIMULATOR)]}, result)

    def test_successful_apple_carriers_only_forward_and_failed_siblings_remain_failed(self):
        f = self.fixture
        before = regular_file_inventory(f.inputs)
        caller_policy = {"sdk_validation_tooling": {"caller": "tooling"},
                         "sdk_apple_validation_policy": {"caller": "Apple policy"}}
        for index, (failed, policy) in enumerate(((False, {}), (False, caller_policy), (True, caller_policy))):
            destination = f.root / f"collection-{index}"
            output = f.root / f"collection-output-{index}"
            rows = [{**DEVICE, "result": "success", "shardDirectory": "rows/device/original/shard",
                     "sdkAppleValidationEvidenceDirectory": "rows/device/sdk-apple-validation-evidence"},
                    {**SIMULATOR, "result": "failure" if failed else "success"}]
            if not failed:
                rows[1].update(shardDirectory="rows/simulator/original/shard",
                              sdkAppleValidationEvidenceDirectory="rows/simulator/sdk-apple-validation-evidence")
            def collect(*args, **kwargs):
                args[3].mkdir(parents=True)
                (args[3] / "diagnostics.bin").write_bytes(b"original sibling diagnostics\x00\xff")
                return {"rows": rows}
            advanced_result = {"fullReuse": False, "synthetic": "advance boundary"}
            def advance(*args, **kwargs):
                args[4].mkdir(parents=True)
                (args[4] / "result.json").write_bytes(b"retained state")
                return advanced_result
            with self.subTest(failed=failed), \
                    patch.object(workflow.product_reuse, "collect_runtime_workers", side_effect=collect) as collected, \
                    patch.object(workflow.product_reuse, "advance_products", side_effect=advance) as advanced, \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.collect(f.inputs, destination, output, wave=9, family="ios-validation",
                    trusted_workflow_sha=fixtures.PIN, repository_root=f.root, environ={}, token="observer", **policy)
            self.assertIs(advanced_result, result)
            collected.assert_called_once_with(f.plan, f.discovery, f.state, destination / "collection",
                trusted_workflow_sha=fixtures.PIN, repository_root=f.root, environ={}, token="observer",
                sdk_family="ios-validation", **policy)
            successes = [row for row in rows if row["result"] == "success"]
            advanced.assert_called_once_with(f.plan, f.discovery, f.state,
                [destination / "collection" / row["shardDirectory"] for row in successes],
                destination / "handoff/runtime-state", output, repository_root=f.root, environ={},
                failed_instances=(workflow.PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-simulator-arm64"),)
                    if failed else (), sdk_family="ios-validation", **policy,
                sdk_original_workflow_sha=fixtures.PIN,
                sdk_apple_evidence_roots=tuple(destination / "collection" / row["sdkAppleValidationEvidenceDirectory"]
                                             for row in successes))
            self.assertNotIn("sdk_evidence_roots", advanced.call_args.kwargs)
            if failed:
                matrix.assert_not_called()
                self.assertIn("sdk_workers_required=false", output.read_text())
            else:
                matrix.assert_called_once_with(destination / "handoff/product-resume-inputs/plan/impact-plan.json",
                    destination / "handoff/product-resume-state", destination / "handoff/runtime-state", output,
                    repository_root=f.root, environ={}, trusted_workflow_sha=fixtures.PIN,
                    family="ios-validation", **policy)
            self.assertEqual(before, regular_file_inventory(f.inputs))
            for name in ("product-resume-inputs", "product-resume-state"):
                self.assertEqual(regular_file_inventory(f.inputs / name),
                                 regular_file_inventory(destination / "handoff" / name))
            self.assertEqual(b"original sibling diagnostics\x00\xff", (destination / "collection/diagnostics.bin").read_bytes())

    def test_missing_success_carrier_and_invalid_wave_do_not_advance(self):
        f = self.fixture
        for wave, family in ((8, "ios-validation"), (9, "native-validation"), (9, None), (True, "ios-validation")):
            with self.subTest(wave=wave, family=family), \
                    patch.object(workflow.product_reuse, "collect_runtime_workers") as collect, \
                    self.assertRaises(ValueError):
                workflow.collect(f.inputs, f.destination, f.output, wave=wave, family=family,
                    trusted_workflow_sha=fixtures.PIN, repository_root=f.root, environ={}, token="observer")
            collect.assert_not_called()
        with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [
                {**DEVICE, "result": "success", "shardDirectory": "rows/device/original/shard"}]}), \
                patch.object(workflow.product_reuse, "advance_products") as advance, self.assertRaises(KeyError):
            workflow.collect(f.inputs, f.destination, f.output, wave=9, family="ios-validation",
                trusted_workflow_sha=fixtures.PIN, repository_root=f.root, environ={}, token="observer")
        advance.assert_not_called()

    def test_final_wave_does_not_accept_remaining_validation_work(self):
        f = self.fixture
        with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": []}), \
                patch.object(workflow.product_reuse, "advance_products"), \
                patch.object(workflow, "matrix", return_value={"include": [DEVICE]}), \
                self.assertRaisesRegex(ValueError, "remain after their final"):
            workflow.collect(f.inputs, f.destination, f.output, wave=9, family="ios-validation",
                trusted_workflow_sha=fixtures.PIN, repository_root=f.root, environ={}, token="observer")

    def test_cli_accepts_only_new_collection_wave_and_forwards_captured_sdk_wave_nine(self):
        common = ["--destination", "/work/output", "--github-output", "/work/github-output",
                  "--trusted-workflow-sha", fixtures.PIN, "--family", "ios-validation"]
        with patch.object(workflow, "collect") as collect:
            workflow._workflow_main(["collect", *common, "--input-root", "/work/input", "--wave", "9"])
        self.assertEqual(9, collect.call_args.kwargs["wave"])
        self.assertEqual("ios-validation", collect.call_args.kwargs["family"])
        with patch.object(workflow, "capture") as capture:
            workflow._workflow_main(["capture", *common, "--plan", "/work/plan", "--artifact-id", "91",
                                    "--artifact-sha256", "sha256:" + "a" * 64, "--sdk-state-wave", "9"])
        self.assertEqual(9, capture.call_args.kwargs["sdk_state_wave"])
        with patch.object(workflow, "collect") as collect, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            workflow._workflow_main(["collect", *common, "--input-root", "/work/input", "--wave", "19"])
        collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
