"""Dart dependency provisioning is validation tooling, never shipped SDK input."""

import unittest

from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import classify_paths, phase_inventory_paths


class DartProvisionSelectionTest(unittest.TestCase):
    def assert_validation_only(self, path: str) -> None:
        result = classify_paths((path,))
        expected = {
            instance for instance in PHASE_INSTANCE_IDS
            if instance.product == "sdk" and instance.component == "dart"
            and instance.phase in {"validation", "metadata"}
        }
        self.assertEqual(expected, set(result.instances))
        self.assertEqual((path,), result.inventory_paths)
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual(
                (path,) if instance.product == "sdk" and instance.component == "dart"
                and instance.phase == "validation" else (),
                phase_inventory_paths((path,), instance),
            )

    def test_provisioner_is_not_owned_by_package_or_unrelated_products(self):
        self.assert_validation_only("codex-agent-bindings/dart/tool/provision_dependencies.py")

    def test_provisioner_unit_test_is_not_owned_by_package_or_unrelated_products(self):
        self.assert_validation_only("codex-agent-bindings/dart/tool/tests/test_provision_dependencies.py")


if __name__ == "__main__":
    unittest.main()
