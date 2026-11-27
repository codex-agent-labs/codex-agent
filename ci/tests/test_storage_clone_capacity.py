"""Phase 9.1 storage controls: clone-first copies, fallback, retirement and headroom.

Clones and preflights are capacity controls only; every test checks that exact
bytes, modes and source/destination guards are unchanged by the chosen path.
"""
import errno
import io
import json
import os
from contextlib import nullcontext, redirect_stderr
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_reference_transport as transport
from runtime_reference_transport import _copy_exact, measured, count
from products import inventory, restore
from products.inventory import publish_regular_tree as byte_publish_regular_tree
from products.inventory import regular_file_inventory, sha256_bytes
from products.restore import (
    clone_publish_regular_tree as publish_regular_tree, clone_snapshot_regular_tree as snapshot_regular_tree,
)

CLONES = restore._native_clone_operation() is not None and transport.native_clone_capable(tempfile.gettempdir())


def _unsupported(*_args):
    raise OSError(errno.ENOTSUP, "fixture: clone unsupported")


def _counted(function, *args, **kwargs):
    """Run under one measurement and return its inclusive counters."""
    holder = {}

    @measured
    def operation():
        holder["result"] = function(*args, **kwargs)
        holder["counters"] = transport._MEASUREMENTS.get()[-1]

    with mock.patch.dict(os.environ, {"CODEX_AGENT_THROUGHPUT_TRACE": "1"}), redirect_stderr(io.StringIO()):
        operation()
    return holder["counters"]


class StorageTreeTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="storage-clone-test-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.source = self.root / "source"
        (self.source / "nested").mkdir(parents=True)
        (self.source / "large.bin").write_bytes(os.urandom(3 * 1024 * 1024 + 17))
        (self.source / "nested/tool").write_bytes(b"#!/bin/sh\n")
        (self.source / "nested/tool").chmod(0o755)
        (self.source / "nested/private").write_bytes(b"private")
        (self.source / "nested/private").chmod(0o600)

    def _modes(self, root):
        return {str(path.relative_to(root)): stat.S_IMODE(path.stat().st_mode)
                for path in sorted(root.rglob("*")) if path.is_file()}

    def _assert_independent(self, destination):
        self.assertEqual(regular_file_inventory(self.source), regular_file_inventory(destination))
        self.assertEqual(self._modes(self.source), self._modes(destination))
        for path in destination.rglob("*"):
            if path.is_file():
                original = self.source / path.relative_to(destination)
                self.assertEqual(1, path.stat().st_nlink)
                self.assertNotEqual(original.stat().st_ino, path.stat().st_ino)
        before = regular_file_inventory(self.source)
        target = destination / "large.bin"
        target.chmod(0o600)
        with target.open("r+b") as handle:
            handle.write(b"mutated")
        self.assertEqual(before, regular_file_inventory(self.source))

    @unittest.skipUnless(CLONES, "native clones unavailable on this volume")
    def test_snapshot_clones_from_creation_and_isolates_writes(self):
        destination = self.root / "snapshot"
        counters = _counted(snapshot_regular_tree, self.source, destination)
        self.assertEqual(3, counters.get("treeCloneFiles"))
        self.assertNotIn("treeCopyBytes", counters)
        self._assert_independent(destination)

    def test_unsupported_clone_uses_verified_byte_copy_with_same_result(self):
        destination = self.root / "fallback"
        with mock.patch.object(restore, "_native_clone_operation", return_value=_unsupported):
            counters = _counted(snapshot_regular_tree, self.source, destination)
        self.assertEqual(3, counters.get("treeCopyFiles"))
        self.assertEqual(3, counters.get("cloneFallbacks"))
        self.assertNotIn("treeCloneFiles", counters)
        self._assert_independent(destination)

    def test_platform_without_clones_uses_byte_copy(self):
        destination = self.root / "portable"
        with mock.patch.object(restore, "_native_clone_operation", return_value=None):
            counters = _counted(publish_regular_tree, self.source, destination,
                                expected_inventory=regular_file_inventory(self.source))
        # Delegates to the unchanged inventory byte-copy publisher.
        self.assertNotIn("treeCloneFiles", counters)
        self._assert_independent(destination)

    def test_clone_publication_equals_byte_publication(self):
        inventory_rows = regular_file_inventory(self.source)
        publish_regular_tree(self.source, self.root / "cloned", expected_inventory=inventory_rows)
        byte_publish_regular_tree(self.source, self.root / "copied", expected_inventory=inventory_rows)
        self.assertEqual(regular_file_inventory(self.root / "copied"), regular_file_inventory(self.root / "cloned"))
        self.assertEqual(self._modes(self.root / "copied"), self._modes(self.root / "cloned"))
        with self.assertRaisesRegex(ValueError, "must not exist"):
            publish_regular_tree(self.source, self.root / "cloned")
        with self.assertRaisesRegex(ValueError, "overlap"):
            publish_regular_tree(self.source, self.source / "inside")

    def test_integrity_and_permission_errors_are_not_fallbacks(self):
        for code in (errno.EIO, errno.EACCES, errno.ENOSPC, errno.EEXIST):
            def failing(*_args, code=code):
                raise OSError(code, "fixture failure")
            with self.subTest(code=code), \
                    mock.patch.object(restore, "_native_clone_operation", return_value=failing), \
                    self.assertRaises(OSError) as raised:
                snapshot_regular_tree(self.source, self.root / f"failed-{code}")
            self.assertEqual(code, raised.exception.errno)

    def test_aliasing_clone_is_rejected(self):
        def hardlink(source, parent, name, _mode):
            inode = os.fstat(source).st_ino
            path = next(path for path in self.source.rglob("*") if path.stat().st_ino == inode)
            os.link(path, name, dst_dir_fd=parent)
        with mock.patch.object(restore, "_native_clone_operation", return_value=hardlink), \
                self.assertRaisesRegex(ValueError, "not an independent regular file|source changed"):
            # A hardlink alias also bumps the source ctime; either guard must refuse it.
            snapshot_regular_tree(self.source, self.root / "aliased")
        # With an unchanged source identity the alias itself is still rejected.
        def same_identity_alias(source, parent, name, _mode):
            hardlink(source, parent, name, _mode)
        descriptor, metadata = inventory._open_regular_file(self.source / "large.bin", "fixture")
        parent = os.open(self.root, os.O_RDONLY)
        try:
            with mock.patch.object(restore, "_native_clone_operation", return_value=same_identity_alias), \
                    mock.patch.object(restore, "_stat_identity", return_value=(0,)), \
                    self.assertRaisesRegex(ValueError, "not an independent regular file"):
                restore._clone_regular_file(descriptor, metadata, parent, "alias.bin", 0o600)
        finally:
            os.close(parent)
            os.close(descriptor)

    @unittest.skipUnless(CLONES, "native clones unavailable on this volume")
    def test_source_mutation_during_clone_is_rejected(self):
        real = restore._native_clone_operation()

        def mutating(source, parent, name, mode):
            real(source, parent, name, mode)
            if name == "large.bin":
                with (self.source / "large.bin").open("ab") as handle:
                    handle.write(b"late")
        with mock.patch.object(restore, "_native_clone_operation", return_value=mutating), \
                self.assertRaisesRegex(ValueError, "changed"):
            snapshot_regular_tree(self.source, self.root / "mutated")

    def test_symlink_and_pinned_inventory_guards_remain(self):
        (self.source / "link").symlink_to("large.bin")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            snapshot_regular_tree(self.source, self.root / "symlinked")
        (self.source / "link").unlink()
        wrong = [dict(row, sha256=sha256_bytes(b"other")) if row["relativePath"] == "large.bin" else row
                 for row in regular_file_inventory(self.source)]
        with self.assertRaisesRegex(ValueError, "pinned inventory"):
            publish_regular_tree(self.source, self.root / "pinned", expected_inventory=wrong)
        self.assertFalse((self.root / "pinned").exists())

    def test_hardlinked_source_yields_independent_copy(self):
        os.link(self.source / "nested/private", self.root / "outside-alias")
        destination = self.root / "from-hardlink"
        snapshot_regular_tree(self.source, destination)
        self.assertEqual(1, (destination / "nested/private").stat().st_nlink)
        self.assertEqual(b"private", (destination / "nested/private").read_bytes())


class StorageFileTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="storage-file-test-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.payload = os.urandom(2 * 1024 * 1024 + 5)
        self.source = self.root / "source.bin"
        self.source.write_bytes(self.payload)
        self.record = {"bytes": len(self.payload), "sha256": sha256_bytes(self.payload)}

    def test_copy_exact_clone_and_fallback_are_identical(self):
        expected_mode = transport._created_file_mode()
        results = {}
        for name, operation in (("native", None), ("fallback", _unsupported)):
            target = self.root / name / "copy.bin"
            patcher = (mock.patch.object(restore, "_native_clone_operation", return_value=operation)
                       if operation is not None else nullcontext())
            with patcher:
                results[name] = _counted(_copy_exact, self.source, target, self.record)
            self.assertEqual(self.payload, target.read_bytes())
            self.assertEqual(expected_mode, stat.S_IMODE(target.stat().st_mode))
            self.assertEqual(1, target.stat().st_nlink)
            self.assertNotEqual(self.source.stat().st_ino, target.stat().st_ino)
        self.assertEqual(1, results["fallback"].get("verifiedCopies"))
        if CLONES:
            self.assertEqual({"verifiedCloneBytes": len(self.payload), "verifiedClones": 1}, results["native"])

    def test_copy_exact_directory_descriptor_mode_and_digest_gate(self):
        parent = self.root / "cache"
        parent.mkdir()
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            _copy_exact(self.source, parent / "member", self.record, destination_directory=descriptor)
            with self.assertRaisesRegex(ValueError, "digest differs"):
                _copy_exact(self.source, parent / "wrong", {**self.record, "sha256": sha256_bytes(b"x")},
                            destination_directory=descriptor)
            with self.assertRaises(FileExistsError):
                _copy_exact(self.source, parent / "member", self.record, destination_directory=descriptor)
        finally:
            os.close(descriptor)
        self.assertEqual(0o600, stat.S_IMODE((parent / "member").stat().st_mode))
        self.assertEqual(self.payload, (parent / "member").read_bytes())

    def test_inventory_module_is_unchanged_phase_input(self):
        # inventory.py is a phase input for 53 product phases: clone-first
        # storage must stay opt-in through products.restore only.
        self.assertFalse(hasattr(inventory, "_native_clone_operation"))
        self.assertFalse(hasattr(inventory, "_clone_regular_file"))

    def test_restore_object_snapshot_clone_and_fallback(self):
        for name, operation in (("native", None), ("fallback", _unsupported)):
            target = self.root / f"{name}.zip"
            if operation is None:
                identity = restore._snapshot_archive(self.source, target)
            else:
                with mock.patch.object(restore, "_native_clone_operation", return_value=operation):
                    identity = restore._snapshot_archive(self.source, target)
            self.assertEqual(self.record, identity)
            self.assertEqual(self.payload, target.read_bytes())
            self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))
            with self.assertRaises(FileExistsError):
                restore._snapshot_archive(self.source, target)


class HeadroomTest(unittest.TestCase):
    PACKAGE = 19_941_206_953  # authenticated P upload size in run 44833963449

    def test_budget_reproduces_observed_byte_copy_peak_and_covers_simulator(self):
        device_copy = transport.sdk_ios_worker_required_free_bytes(
            "ios-arm64", package_archive_bytes=self.PACKAGE, clones=False)
        # Without clones the measured budget exceeds the 88.47e9 free at the
        # failing context's start, so the worker would have refused up front.
        self.assertGreater(device_copy, 88_465_334_272)
        self.assertGreater(device_copy - transport._HEADROOM_RESERVE, 85_672_030_208)
        for target in ("ios-arm64", "ios-simulator-arm64"):
            cloned = transport.sdk_ios_worker_required_free_bytes(
                target, package_archive_bytes=self.PACKAGE, binary_archive_bytes=4 * 10**9, clones=True)
            copied = transport.sdk_ios_worker_required_free_bytes(
                target, package_archive_bytes=self.PACKAGE, binary_archive_bytes=4 * 10**9, clones=False)
            self.assertLess(cloned, copied)
        self.assertGreaterEqual(
            transport.sdk_ios_worker_required_free_bytes("ios-simulator-arm64", package_archive_bytes=self.PACKAGE,
                                                         binary_archive_bytes=8 * 10**9, clones=True),
            transport.sdk_ios_worker_required_free_bytes("ios-arm64", package_archive_bytes=self.PACKAGE,
                                                         binary_archive_bytes=8 * 10**9, clones=True))
        with self.assertRaisesRegex(ValueError, "exact iOS validation target"):
            transport.sdk_ios_worker_required_free_bytes("macos", package_archive_bytes=1, clones=True)

    def test_preflight_refuses_before_expensive_work_and_reports_measurement(self):
        expensive = mock.Mock()
        output = io.StringIO()
        usage = mock.Mock(free=2_793_304_064)
        with mock.patch.object(transport.shutil, "disk_usage", return_value=usage), redirect_stderr(output):
            with self.assertRaisesRegex(ValueError, "Insufficient free space for ios-validation.*Refusing"):
                transport.require_volume_headroom(tempfile.gettempdir(), 80 * 1024**3, stage="ios-validation")
                expensive()
        expensive.assert_not_called()
        record = json.loads(output.getvalue().strip().removeprefix("volume-headroom "))
        self.assertEqual({"stage": "ios-validation", "freeBytes": 2_793_304_064,
                          "requiredFreeBytes": 80 * 1024**3, "sufficient": False},
                         {key: record[key] for key in ("stage", "freeBytes", "requiredFreeBytes", "sufficient")})
        with mock.patch.object(transport.shutil, "disk_usage", return_value=mock.Mock(free=90 * 1024**3)), \
                redirect_stderr(io.StringIO()):
            self.assertEqual(90 * 1024**3, transport.require_volume_headroom(
                tempfile.gettempdir(), 80 * 1024**3, stage="ios-validation"))

    def test_worker_and_capture_preflights_choose_clone_or_copy_budget(self):
        roots = [tempfile.gettempdir(), tempfile.gettempdir()]
        seen = []

        def record(root, required, *, stage):
            seen.append((stage, required))
            return 1
        with mock.patch.object(transport, "require_volume_headroom", side_effect=record):
            with mock.patch.object(transport, "native_clone_capable", return_value=True):
                transport.sdk_ios_worker_preflight("ios-simulator-arm64", roots)
                transport.apple_capture_preflight(roots[0], roots[1], self.PACKAGE, phase="package")
            with mock.patch.object(transport, "native_clone_capable", return_value=False):
                transport.sdk_ios_worker_preflight("ios-simulator-arm64", roots)
                transport.apple_capture_preflight(roots[0], roots[1], self.PACKAGE, phase="package")
        self.assertEqual(["sdk-ios-validation-ios-simulator-arm64", "apple-package-capture",
                          "sdk-ios-validation-ios-simulator-arm64-byte-copy", "apple-package-capture-byte-copy"],
                         [stage for stage, _ in seen])
        self.assertLess(seen[0][1], seen[2][1])
        self.assertEqual(2 * self.PACKAGE + transport._HEADROOM_RESERVE, seen[1][1])
        self.assertEqual(4 * self.PACKAGE + transport._HEADROOM_RESERVE, seen[3][1])
        with self.assertRaisesRegex(ValueError, "existing workspace"):
            transport.sdk_ios_worker_preflight("ios-arm64", [Path(tempfile.gettempdir()) / "missing-p91"])

    def test_clone_probe_reports_unsupported_hosts(self):
        with mock.patch.object(restore, "_native_clone_operation", return_value=None):
            self.assertFalse(transport.native_clone_capable(tempfile.gettempdir()))
        with mock.patch.object(restore, "_native_clone_operation", return_value=_unsupported):
            self.assertFalse(transport.native_clone_capable(tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
