"""Discovery demand routing only; replay, catalog and signature seams are mocked."""

import unittest

from ci.tests import test_product_tooling_discovery as fixture
from products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS, PhaseInstanceId


CONSUMERS = (
    PhaseInstanceId("sdk", "sdk-ios", "package", "ios"),
    PhaseInstanceId("sdk", "javascript", "metadata", "node"),
)
MISS = {"schemaVersion": 1, "selected": None, "attempts": [], "toolingPolicy": None}


class SdkMetadataToolingDemandTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.ProductToolingDiscoveryTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_exact_ios_package_and_javascript_metadata_demand_original_tooling(self):
        for number, instance in enumerate(CONSUMERS):
            with self.subTest(instance=instance):
                self.assertIn(instance, PHASE_INSTANCE_IDS)
                result, _, events, discovery = self.case.run_discovery(
                    instance, report=MISS, destination_name=f"consumer-{number}")
                self.assertEqual("stop-after-tooling", result["reason"])
                self.assertEqual(["catalogs", "tooling", "capture"], events)
                discovery.assert_called_once()
                outputs = self.case.outputs()
                self.assertEqual(("true", "true"), (outputs["tooling_required"], outputs["tooling_miss"]))
                self.assertEqual(("", "", ""), tuple(outputs[name] for name in
                    ("tooling_artifact_id", "tooling_artifact_sha256", "tooling_transport_producer")))

    def test_non_consuming_phases_do_not_trigger_automatic_tooling(self):
        controls = (
            PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"),
            PhaseInstanceId("sdk", "javascript", "package", "node"),
            PhaseInstanceId("sdk", "javascript", "validation", "node"),
            PhaseInstanceId("sdk", "sdk-core", "binary", "common"),
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
            *(PhaseInstanceId("sdk", language, "package", "desktop") for language in NATIVE_BINDINGS),
        )
        for number, instance in enumerate(controls):
            with self.subTest(instance=instance):
                self.assertIn(instance, PHASE_INSTANCE_IDS)
                _, _, events, discovery = self.case.run_discovery(
                    instance, report=None, destination_name=f"control-{number}")
                self.assertEqual(["catalogs", "capture"], events)
                discovery.assert_not_called()
                outputs = self.case.outputs()
                self.assertEqual(("false", "false"), (outputs["tooling_required"], outputs["tooling_miss"]))

    def test_existing_native_validation_and_metadata_demand_is_preserved(self):
        for language in NATIVE_BINDINGS:
            for phase, target in (("validation", "linux-x64"), ("metadata", "desktop")):
                with self.subTest(language=language, phase=phase):
                    instance = PhaseInstanceId("sdk", language, phase, target)
                    self.assertIn(instance, PHASE_INSTANCE_IDS)
                    _, _, events, discovery = self.case.run_discovery(instance, report=MISS,
                        destination_name=f"native-{language}-{phase}")
                    discovery.assert_called_once()
                    self.assertEqual(["catalogs", "tooling", "capture"], events)
                    self.assertEqual("true", self.case.outputs()["tooling_required"])

    def test_authorization_and_automatic_opt_in_are_not_bypassed(self):
        for number, instance in enumerate(CONSUMERS):
            unauthorized = fixture.impact_plan(changed=["known.kt"])
            unauthorized["remoteBuildAuthorized"] = False
            with self.subTest(instance=instance, route="unauthorized"):
                result, _, events, discovery = self.case.run_discovery(instance, plan=unauthorized,
                    destination_name=f"unauthorized-{number}")
                self.assertEqual("remote-build-unauthorized", result["reason"])
                self.assertEqual([], events)
                discovery.assert_not_called()
                self.assertEqual("false", self.case.outputs()["tooling_required"])
            with self.subTest(instance=instance, route="automatic-disabled"):
                _, _, events, discovery = self.case.run_discovery(instance, automatic=False,
                    destination_name=f"manual-{number}")
                self.assertEqual(["catalogs", "capture"], events)
                discovery.assert_not_called()
                self.assertEqual("false", self.case.outputs()["tooling_required"])
            with self.subTest(instance=instance, route="missing-token"):
                _, _, events, discovery = self.case.run_discovery(instance, environment={},
                    destination_name=f"no-token-{number}")
                self.assertEqual(["catalogs", "capture"], events)
                discovery.assert_not_called()
                outputs = self.case.outputs()
                self.assertEqual(("true", "true"), (outputs["tooling_required"], outputs["tooling_miss"]))


if __name__ == "__main__":
    unittest.main()
