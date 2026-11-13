import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ci.products import inventory


class WindowsSnapshotIdentityTest(unittest.TestCase):
    def test_path_and_descriptor_ctime_disagree_without_changing_file_identity(self):
        stat = dict(st_dev=1, st_ino=2, st_size=3, st_mtime_ns=4, st_birthtime_ns=5)
        with patch.object(inventory, "_is_windows", return_value=True):
            by_path = inventory._stat_identity(SimpleNamespace(**stat, st_ctime_ns=5))
            by_descriptor = inventory._stat_identity(SimpleNamespace(**stat, st_ctime_ns=6))
            self.assertEqual(by_path, by_descriptor)
            self.assertNotEqual(by_path, inventory._stat_identity(
                SimpleNamespace(**(stat | {"st_mtime_ns": 7}), st_ctime_ns=6)))


if __name__ == "__main__":
    unittest.main()
