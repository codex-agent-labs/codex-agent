"""Exact Core/Android SDK family routing; no host or product evidence claim."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse
import sdk_workflow
from products.registry import PHASE_INSTANCE_IDS, SDK_FACADE_TARGETS, PhaseInstanceId
from ci.tests import test_sdk_family_actions as action_harness


WAVES = {
    "core-binary": (11, "binary", ("common",)),
    "core-package": (12, "package", ("common",)),
    "core-validation": (13, "validation", SDK_FACADE_TARGETS),
    "core-metadata": (14, "metadata", ("common",)),
    "android-binary": (15, "binary", ("android",)),
    "android-package": (16, "package", ("android",)),
    "android-validation": (17, "validation", ("android",)),
    "android-metadata": (18, "metadata", ("android",)),
}


class CoreAndroidFamilySelectionTest(unittest.TestCase):
    def test_exact_eighteen_instances_and_no_siblings(self):
        selected = set()
        for family, (_, phase, targets) in WAVES.items():
            component = "sdk-core" if family.startswith("core-") else "sdk-android"
            expected = {PhaseInstanceId("sdk", component, phase, target) for target in targets}
            self.assertEqual(expected, {instance for instance in PHASE_INSTANCE_IDS
                if product_reuse._sdk_family_worker_instance(instance, family)})
            self.assertFalse(selected & expected)
            selected.update(expected)
        self.assertEqual(18, len(selected))

    def test_matrix_elects_exact_core_targets_and_android_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            ready = [{**product_reuse._identity_record(instance), "buildKey": "sha256:" + "a" * 64}
                     for instance in PHASE_INSTANCE_IDS]
            for family, (_, _, targets) in WAVES.items():
                with self.subTest(family=family), patch.object(product_reuse, "inspect_products",
                        return_value={"readyPlans": ready}):
                    rows = sdk_workflow.matrix(root / "plan", root / "discovery", root / "state",
                        root / "output", family=family, repository_root=root, environ={})["include"]
                self.assertEqual(len(targets), len(rows))
                self.assertEqual(set(targets), {row["target"] for row in rows})
                self.assertTrue(all(product_reuse._sdk_family_worker_instance(
                    product_reuse._identity(row), family) for row in rows))
                self.assertTrue(all(row["runner"] for row in rows))
                if family != "core-validation":
                    expected_host = (("macos-26", "macOS", "ARM64") if family == "core-binary"
                                     else ("ubuntu-24.04", "Linux", "X64"))
                    self.assertEqual({expected_host},
                        {(row["runner"], row["runnerOs"], row["runnerArch"]) for row in rows})

    def test_collection_rejects_wrong_wave_before_state_access(self):
        for family, (wave, _, _) in WAVES.items():
            with self.subTest(family=family), self.assertRaisesRegex(ValueError, "exact wave"):
                sdk_workflow.collect(Path("missing"), Path("missing-out"), Path("missing-output"),
                    wave=wave - 1, family=family, trusted_workflow_sha="a" * 40, token="")

    def test_capture_and_collect_composites_forward_every_new_family(self):
        harness = action_harness.SdkFamilyActionsTest(methodName="runTest")
        harness.setUp()
        for family, (wave, _, _) in WAVES.items():
            with self.subTest(family=family):
                result, args, _, output = harness.run_action("capture", STATE_PRODUCT="sdk",
                    SDK_FAMILY=family, SDK_STATE_WAVE=str(wave - 1))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(harness.capture_arguments(output,
                    ["--sdk-state-wave", str(wave - 1), "--family", family], sdk=True), args)
                result, args, _, output = harness.run_action("collect", PRODUCT="sdk",
                    SDK_FAMILY=family, WAVE=str(wave))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(harness.collect_arguments(output, ["--family", family],
                    sdk=True, wave=str(wave)), args)

    def test_collect_forwards_caller_metadata_descriptors_to_capture_and_replay(self):
        harness = action_harness.SdkFamilyActionsTest(methodName="runTest")
        harness.setUp()
        action = harness.collect
        self.assertIn("sdk-facade-metadata-policy: ${{ inputs.sdk-facade-metadata-policy }}", action)
        self.assertIn("sdk-android-metadata-policy: ${{ inputs.sdk-android-metadata-policy }}", action)
        result, args, _, output = harness.run_action("collect", PRODUCT="sdk",
            SDK_FAMILY="android-metadata", WAVE="18",
            SDK_FACADE_METADATA_POLICY="/caller/core.json",
            SDK_ANDROID_METADATA_POLICY="/caller/android.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(harness.collect_arguments(output, ["--family", "android-metadata",
            "--sdk-facade-metadata-policy", "/caller/core.json",
            "--sdk-android-metadata-policy", "/caller/android.json"], sdk=True, wave="18"), args)
        result, args, _, _ = harness.run_action("collect", PRODUCT="runtime",
            SDK_FACADE_METADATA_POLICY="/caller/core.json")
        self.assertNotEqual(0, result.returncode)
        self.assertIsNone(args)


if __name__ == "__main__":
    unittest.main()
