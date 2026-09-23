from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import publish_regular_tree


@unittest.skipIf(os.name == "nt", "POSIX directory publication race")
class ProductPublicationAtomicityTests(unittest.TestCase):
    def test_foreign_empty_destination_created_after_final_check_is_not_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            (source / "payload").write_bytes(b"owned")
            destination = root / "published"
            real_stat = os.stat
            checks = 0
            foreign_inode = None

            def inject_after_final_absence_check(path, *args, **kwargs):
                nonlocal checks, foreign_inode
                if path == destination.name and kwargs.get("dir_fd") is not None:
                    checks += 1
                    try:
                        return real_stat(path, *args, **kwargs)
                    except FileNotFoundError:
                        if checks == 2:
                            os.mkdir(path, dir_fd=kwargs["dir_fd"])
                            foreign_inode = real_stat(path, *args, **kwargs).st_ino
                        raise
                return real_stat(path, *args, **kwargs)

            failure = None
            with mock.patch.object(os, "stat", side_effect=inject_after_final_absence_check):
                try:
                    publish_regular_tree(source, destination)
                except ValueError as error:
                    failure = error

            self.assertGreaterEqual(checks, 2)
            self.assertIsNotNone(foreign_inode)
            self.assertEqual(foreign_inode, destination.stat().st_ino)
            self.assertEqual([], list(destination.iterdir()))
            self.assertIsNotNone(failure)


if __name__ == "__main__":
    unittest.main()
