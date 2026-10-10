from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.products import inventory as product_inventory
from ci.products.inventory import publish_regular_tree, regular_file_inventory


@unittest.skipIf(os.name == "nt", "POSIX directory publication race")
class ProductPublicationAtomicityTests(unittest.TestCase):
    def test_pinned_inventory_uses_global_file_path_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            (source / "a").mkdir(parents=True)
            (source / "a.txt").write_bytes(b"sibling")
            (source / "a" / "file").write_bytes(b"nested")
            destination = root / "published"

            expected = regular_file_inventory(source)
            publish_regular_tree(source, destination, expected_inventory=expected)

            self.assertEqual(expected, regular_file_inventory(destination))

    def test_pinned_inventory_allows_empty_files_only_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            (source / "empty").touch()
            destination = root / "published"
            expected = regular_file_inventory(source, allow_empty=True)

            with self.assertRaises(ValueError):
                publish_regular_tree(source, destination, expected_inventory=expected)
            self.assertFalse(destination.exists())
            publish_regular_tree(source, destination, allow_empty=True, expected_inventory=expected)
            self.assertEqual(expected, regular_file_inventory(destination, allow_empty=True))

    def test_pinned_modes_reject_identical_bytes_with_wrong_executable_bit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            script = source / "gradlew"
            script.write_bytes(b"#!/bin/sh\n")
            script.chmod(0o644)
            destination = root / "published"
            expected = regular_file_inventory(source)

            with self.assertRaisesRegex(ValueError, "pinned inventory"):
                publish_regular_tree(source, destination, expected_inventory=expected,
                                     expected_modes={"gradlew": 0o755})
            self.assertFalse(destination.exists())
            script.chmod(0o755)
            publish_regular_tree(source, destination, expected_inventory=expected,
                                 expected_modes={"gradlew": 0o755})
            self.assertEqual(0o755, destination.joinpath("gradlew").stat().st_mode & 0o777)

    def test_mode_pinned_publication_fails_closed_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "source"
            source.mkdir()
            (source / "gradlew").write_bytes(b"#!/bin/sh\n")
            destination = root / "published"
            with mock.patch.object(product_inventory, "_is_windows", return_value=True), \
                    self.assertRaisesRegex(ValueError, "unavailable on Windows"):
                publish_regular_tree(source, destination,
                                     expected_inventory=regular_file_inventory(source),
                                     expected_modes={"gradlew": 0o755})
            self.assertFalse(destination.exists())

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
