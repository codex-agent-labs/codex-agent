"""A captured supervisor upload must forward the exact authenticated ZIP members."""

from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products.inventory import publish_regular_tree, sha256_bytes
from ci.tests import test_runtime_supervisor_capture as supervisor_fixture


class RuntimeSupervisorUploadPinTest(unittest.TestCase):
    def setUp(self):
        self.fixture = supervisor_fixture.RuntimeSupervisorCaptureTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_late_original_member_mutation_cannot_publish(self):
        fixture = self.fixture
        self.assertEqual(fixture.artifact["digest"], sha256_bytes(fixture.raw))
        destination = fixture.root / "build/rejected-supervisor-late-copy"

        def mutate_before_copy(source, output, **kwargs):
            (Path(source) / "original/raw-evidence.txt").write_bytes(b"changed during copy\n")
            publish_regular_tree(source, output, **kwargs)

        with patch.object(supervisor_fixture.product_reuse, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            fixture.capture(destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
