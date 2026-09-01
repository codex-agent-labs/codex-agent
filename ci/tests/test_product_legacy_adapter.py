from __future__ import annotations

import ast
import inspect
from pathlib import Path
import unittest

from ci.legacy_lanes import LANES
from ci.product_legacy import project_legacy_lanes
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId


def phase(product: str, component: str, name: str, target: str) -> PhaseInstanceId:
    return PhaseInstanceId(product, component, name, target)


class ProductLegacyAdapterTest(unittest.TestCase):
    def test_interface_accepts_only_unresolved_phase_instances(self) -> None:
        self.assertEqual(("unresolved",), tuple(inspect.signature(project_legacy_lanes).parameters))
        self.assertEqual((), project_legacy_lanes(()).actions)
        self.assertFalse(project_legacy_lanes(()).full)
        for invalid in ("path", ["path"], [PHASE_INSTANCE_IDS[0], PHASE_INSTANCE_IDS[0]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                project_legacy_lanes(invalid)

    def test_every_instance_has_actions_or_the_exact_29_instance_fallback(self) -> None:
        fallback = set()
        for instance in PHASE_INSTANCE_IDS:
            projection = project_legacy_lanes((instance,))
            self.assertTrue(projection.actions or projection.fallback_instances, instance)
            fallback.update(projection.fallback_instances)
        expected = {
            instance for instance in PHASE_INSTANCE_IDS
            if (
                instance.product == "runtime" and instance.phase == "metadata"
                or instance.product == "sdk" and instance.component == "sdk-core"
                or instance.product == "sdk"
                and instance.component in {*NATIVE_BINDINGS, "javascript"}
                and instance.phase == "metadata"
            )
        }
        self.assertEqual(29, len(expected))
        self.assertEqual(expected, fallback)

    def test_actions_are_valid_deterministic_sorted_and_deduplicated(self) -> None:
        projection = project_legacy_lanes(tuple(reversed(PHASE_INSTANCE_IDS)))
        self.assertEqual(len(projection.actions), len(set(projection.actions)))
        self.assertTrue(all(lane in LANES and action in {"build", "test", "metadata"} for lane, action in projection.actions))
        self.assertEqual(projection.actions, project_legacy_lanes(PHASE_INSTANCE_IDS).actions)

    def test_contract_and_android_phase_tables_are_exact(self) -> None:
        for product, component, lane, target in (
            ("contract", "contract", "contracts", "common"),
            ("sdk", "sdk-android", "android", "android"),
        ):
            expected = {"binary": "build", "package": "build", "validation": "test", "metadata": "metadata"}
            for name, action in expected.items():
                with self.subTest(component=component, phase=name):
                    self.assertEqual(((lane, action),), project_legacy_lanes((
                        phase(product, component, name, target),
                    )).actions)

    def test_native_runtime_is_target_exact_and_metadata_falls_back(self) -> None:
        for target in NATIVE_TARGETS:
            binary = project_legacy_lanes((phase("runtime", target, "binary", target),))
            self.assertEqual(((f"desktop-{target}", "build"),), binary.actions)
            self.assertFalse(binary.full)
            metadata = project_legacy_lanes((phase("runtime", target, "metadata", target),))
            self.assertTrue(metadata.full)
            self.assertEqual((), metadata.actions)

    def test_runtime_adapters_use_the_actual_legacy_producers(self) -> None:
        self.assertEqual((("portable", "build"),), project_legacy_lanes((
            phase("runtime", "jvm", "binary", "jvm"),
        )).actions)
        self.assertEqual((("node-js", "test"),), project_legacy_lanes((
            phase("runtime", "node-js", "validation", "node-js-binding"),
        )).actions)
        self.assertEqual((("desktop-linux-x64", "test"),), project_legacy_lanes((
            phase("runtime", "node-js", "validation", "linux-x64"),
        )).actions)
        self.assertEqual((("portable", "build"),), project_legacy_lanes((
            phase("runtime", "node-wasm", "package", "node-wasm"),
        )).actions)

    def test_ios_phases_map_only_to_the_existing_exact_execution_seams(self) -> None:
        binary = project_legacy_lanes((phase("sdk", "sdk-ios", "binary", "ios"),))
        self.assertEqual({
            ("ios-rust-device", "build"), ("ios-rust-simulator", "build"),
            ("ios-framework-device", "build"), ("ios-framework-simulator", "build"),
        }, set(binary.actions))
        device = project_legacy_lanes((
            phase("sdk", "sdk-ios", "validation", "ios-arm64"),
        ))
        self.assertEqual({
            ("ios-native-tests", "test"), ("ios-swift-tests", "test"),
            ("consumer-ios-device", "build"),
        }, set(device.actions))
        simulator = project_legacy_lanes((
            phase("sdk", "sdk-ios", "validation", "ios-simulator-arm64"),
        ))
        self.assertEqual({
            ("ios-native-tests", "test"), ("ios-kotlin-tests", "test"),
            ("ios-swift-build", "test"), ("ios-swift-tests", "test"),
            ("consumer-ios-simulator", "build"),
        }, set(simulator.actions))
        self.assertEqual((("ios-package", "build"),), project_legacy_lanes((
            phase("sdk", "sdk-ios", "package", "ios"),
        )).actions)

    def test_binding_broadening_is_explicit_and_javascript_stays_node_only(self) -> None:
        expected = {(f"desktop-{target}", action) for target in NATIVE_TARGETS for action in ("build", "test")}
        for language in NATIVE_BINDINGS:
            with self.subTest(language=language):
                projection = project_legacy_lanes((phase("sdk", language, "package", "desktop"),))
                self.assertEqual(expected, set(projection.actions))
                self.assertFalse(projection.full)
        self.assertEqual((("node-js", "build"),), project_legacy_lanes((
            phase("sdk", "javascript", "package", "node"),
        )).actions)
        self.assertTrue(project_legacy_lanes((
            phase("sdk", "javascript", "metadata", "node"),
        )).full)

    def test_sdk_core_never_claims_false_legacy_consumer_precision(self) -> None:
        core = [instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk" and instance.component == "sdk-core"]
        projection = project_legacy_lanes(core)
        self.assertTrue(projection.full)
        self.assertEqual((), projection.actions)
        self.assertEqual(tuple(sorted(core)), projection.fallback_instances)

    def test_product_modules_do_not_import_legacy_planners(self) -> None:
        root = Path(__file__).resolve().parents[1] / "products"
        forbidden = {"ci.impact", "ci.receipt", "ci.reuse", "ci.promote", "ci.validation_reuse"}
        found = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(alias.name for alias in node.names if alias.name in forbidden)
                elif isinstance(node, ast.ImportFrom) and node.module in forbidden:
                    found.add(node.module)
        self.assertEqual(set(), found)


if __name__ == "__main__":
    unittest.main()
