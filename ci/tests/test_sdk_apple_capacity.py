"""Control-only capacity ordering checks; no Apple/tool/product acceptance."""

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_content as content
from ci.products.inventory import regular_file_inventory
from ci.tests import test_sdk_apple_content as fixtures


class SdkAppleCapacityTest(unittest.TestCase):
    def test_guard_abort_then_success_and_default(self):
        fixture = fixtures.SdkAppleContentTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        order, private_roots = [], []

        @contextmanager
        def capture(*args, **kwargs):
            with fixture.capture(*args, **kwargs) as jar:
                order.append("authenticated-tooling")
                yield jar

        def execute(command, **kwargs):
            order.append("java")
            return fixture.execute(command, **kwargs)

        def guard(command_name, root):
            self.assertEqual("verify-transported-apple-sdk-package-closure", command_name)
            self.assertEqual(regular_file_inventory(fixture.product),
                             regular_file_inventory(root / "product"))
            self.assertEqual(fixture.compatibility.read_bytes(),
                             (root / "expected/sdk-compatibility.json").read_bytes())
            self.assertNotEqual(fixture.product, root / "product")
            self.assertFalse((root / "owned").exists())
            private_roots.append(root)
            order.append("guard")

        def reject(command_name, root):
            guard(command_name, root)
            raise ValueError("insufficient measured replay capacity")

        with patch.object(content, "verified_tooling_capture", capture), \
                patch.object(content.subprocess, "run", side_effect=execute):
            with self.assertRaisesRegex(ValueError, "insufficient measured"), \
                    content.apple_replay_capacity_guard(reject):
                content.verify_sdk_apple_package_content(**fixture.args)
            self.assertEqual(["authenticated-tooling", "guard"], order)
            self.assertEqual([], fixture.calls)
            self.assertFalse(private_roots[-1].exists())
            self.assertIsNone(content._REPLAY_CAPACITY_GUARD.get())
            order.clear()
            with content.apple_replay_capacity_guard(guard):
                actual = content.verify_sdk_apple_package_content(**fixture.args)
            self.assertEqual(["authenticated-tooling", "guard", "java"], order)
            self.assertEqual(regular_file_inventory(fixture.product), actual)
            self.assertFalse(private_roots[-1].exists())
            order.clear()
            content.verify_sdk_apple_package_content(**fixture.args)
            self.assertEqual(["authenticated-tooling", "java"], order)
            self.assertIsNone(content._REPLAY_CAPACITY_GUARD.get())


if __name__ == "__main__":
    unittest.main()
