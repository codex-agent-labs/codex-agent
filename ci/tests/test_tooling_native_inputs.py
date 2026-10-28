"""Consumer-only native staging copies; no product or signing acceptance."""
import errno
import importlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from ci import products as original_products

ROOT = Path(__file__).resolve().parents[2]
ALIASES = ROOT / ".github/actions/run-ci-lane/verified-consumers"
package = types.ModuleType("_tooling_native_input_checks")
package.__path__ = [str(ALIASES), str(Path(original_products.__file__).resolve().parent)]
sys.modules[package.__name__] = package
inv = importlib.import_module(package.__name__ + ".inventory")
native = inv
sdk = importlib.import_module(package.__name__ + ".sdk_inputs")


@unittest.skipUnless(sys.platform == "darwin", "Native clone checks require macOS/APFS")
class NativeConsumerCopyCheck(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="native-consumer-check-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        (self.source / "nested").mkdir(parents=True)
        (self.source / "empty-directory").mkdir()
        (self.source / "nested/file").write_bytes(b"original bytes\n" * 257)
        (self.source / "nested/file").chmod(0o751)
        (self.source / "nested").chmod(0o750)

    def assert_same(self, destination):
        self.assertEqual(inv.regular_file_inventory(self.source), inv.regular_file_inventory(destination))
        for relative in ("nested", "nested/file", "empty-directory"):
            a, b = (self.source / relative).stat(), (destination / relative).stat()
            self.assertEqual(stat.S_IMODE(a.st_mode), stat.S_IMODE(b.st_mode))
            self.assertNotEqual((a.st_dev, a.st_ino), (b.st_dev, b.st_ino))
            if stat.S_ISREG(b.st_mode):
                self.assertEqual(b.st_nlink, 1)
        (destination / "nested/file").write_bytes(b"private modification")
        self.assertTrue((self.source / "nested/file").read_bytes().startswith(b"original bytes"))

    def test_native_and_portable_snapshot_and_atomic_publish(self):
        expected = inv.regular_file_inventory(self.source)
        for enabled in (False, True):
            snapshot = self.root / f"snapshot-{enabled}"
            inv.snapshot_regular_tree(self.source, snapshot, native_clones=enabled)
            self.assert_same(snapshot)
            published = self.root / f"published-{enabled}"
            inv.publish_regular_tree(self.source, published, expected_inventory=expected,
                                     expected_modes={"nested/file": 0o751}, native_clones=enabled)
            self.assert_same(published)
            with self.assertRaises(ValueError):
                inv.publish_regular_tree(self.source, published, native_clones=enabled)

    def test_missing_clone_fails_closed_and_explicit_portable_still_works(self):
        with patch.object(native, "_native_clone_operation", side_effect=OSError(errno.ENOTSUP, "unsupported")):
            destination = self.root / "failed-native"
            with self.assertRaises(OSError):
                inv.publish_regular_tree(self.source, destination, native_clones=True, require_native_clones=True)
            self.assertFalse(destination.exists())
            inv.publish_regular_tree(self.source, self.root / "native-fallback", native_clones=True)
            self.assert_same(self.root / "native-fallback")
            inv.publish_regular_tree(self.source, self.root / "portable")
            self.assert_same(self.root / "portable")

    def test_unsupported_leaf_falls_back_but_permission_and_partial_fail_closed(self):
        source = self.source / "nested/file"
        for code in (errno.ENOTSUP, errno.EXDEV):
            target = self.root / f"fallback-{code}"
            with patch.object(native, "_native_clone_operation", side_effect=OSError(code, "unsupported")):
                sdk._copy_file(source, target, native_clones=True, creation_mode=0o644)
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
            self.assertNotEqual(source.stat().st_ino, target.stat().st_ino)
        with patch.object(native, "_native_clone_operation", side_effect=OSError(errno.EACCES, "denied")):
            with self.assertRaises(PermissionError):
                inv.publish_regular_tree(self.source, self.root / "denied", native_clones=True)
            self.assertFalse((self.root / "denied").exists())
        import ctypes
        def partial(_source, parent, name, _flags):
            leaf = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
            os.close(leaf)
            ctypes.set_errno(errno.ENOTSUP)
            return -1
        with patch.object(native, "_native_clone_operation", return_value=partial):
            with self.assertRaisesRegex(ValueError, "occupied destination"):
                sdk._copy_file(source, self.root / "partial", native_clones=True, creation_mode=0o644)
        self.assertEqual((self.root / "partial").stat().st_size, 0)

    def test_wrong_inventory_and_unsafe_source_or_destination_never_publish(self):
        expected = inv.regular_file_inventory(self.source)
        expected[0]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError):
            inv.publish_regular_tree(self.source, self.root / "wrong", expected_inventory=expected, native_clones=True)
        self.assertFalse((self.root / "wrong").exists())
        (self.root / "link").symlink_to(self.source, target_is_directory=True)
        for source, destination in ((self.root / "link", self.root / "bad-source"),
                                    (self.source, self.root / "link/output")):
            with self.assertRaises(ValueError):
                inv.publish_regular_tree(source, destination, native_clones=True)
        (self.source / "escape").symlink_to(self.source / "nested/file")
        with self.assertRaises(ValueError):
            inv.publish_regular_tree(self.source, self.root / "bad-member", native_clones=True)

    def test_leaf_and_sdk_copy_keep_size_source_lifetime_exclusive_mode(self):
        source = self.source / "nested/file"
        portable, cloned = self.root / "sdk-portable", self.root / "sdk-cloned"
        sdk._copy_file(source, portable)
        mode = stat.S_IMODE(portable.stat().st_mode)
        sdk._copy_file(source, cloned, native_clones=True, creation_mode=mode)
        self.assertEqual(portable.read_bytes(), cloned.read_bytes())
        self.assertEqual(stat.S_IMODE(cloned.stat().st_mode), mode)
        self.assertEqual(cloned.stat().st_nlink, 1)
        self.assertNotEqual(cloned.stat().st_ino, source.stat().st_ino)
        with self.assertRaises(FileExistsError):
            sdk._copy_file(source, cloned, native_clones=True, creation_mode=mode)
        with self.assertRaises(ValueError):
            sdk._copy_file(source, self.root / "too-large", native_clones=True, creation_mode=mode, max_bytes=1)
        real = native._native_clone_operation()
        before = source.stat()
        def change_after_clone(*args):
            result = real(*args)
            data = source.read_bytes()
            source.write_bytes(b"X" + data[1:])
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result
        with patch.object(native, "_native_clone_operation", return_value=change_after_clone):
            with self.assertRaisesRegex(ValueError, "source changed"):
                sdk._copy_file(source, self.root / "changed", native_clones=True, creation_mode=mode)

    def test_stage_calls_all_three_native_boundaries_without_changing_inventory(self):
        request = self.root / "request.json"
        request.write_text('{}\n')
        attestation = self.root / "authority/attestation.json"
        attestation.parent.mkdir()
        attestation.write_text('{"fixture":true}\n')
        closure = attestation.parent / sdk.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir()
        (closure / "original.json").write_text('{"original":true}\n')
        arguments = {"contract_attestation": attestation, "contract_payload": self.source / "nested/file",
                     "contract_keys_directory": None, "runtime_keys_directory": None}
        def load(path, **_kwargs):
            if Path(path) == request:
                return arguments
            value = json.loads(Path(path).read_bytes())
            return {"contract_attestation": Path(path).parent / value["contractAttestation"],
                    "contract_payload": Path(path).parent / value["contractPayload"]}
        def produce(*, output, **kwargs):
            self.assertEqual(kwargs["contract_payload"].read_bytes(), arguments["contract_payload"].read_bytes())
            value = {"fixtureOnly": True}
            output.write_bytes(inv.canonical_json_bytes(value))
            return value
        with patch.object(sdk, "load_sdk_compatibility_request", side_effect=load), \
             patch.object(sdk, "produce_sdk_compatibility", side_effect=produce), \
             patch.object(sdk, "snapshot_regular_tree", wraps=inv.snapshot_regular_tree) as snapshot, \
             patch.object(sdk, "publish_regular_tree", wraps=inv.publish_regular_tree) as publish:
            result = sdk.stage_sdk_inputs(request, self.root / "handoff")
            self.assertTrue(snapshot.call_args.kwargs["native_clones"])
            self.assertTrue(publish.call_args.kwargs["native_clones"])
        handoff = self.root / "handoff"
        records = result["inventory"]["files"]
        self.assertEqual(inv.regular_file_inventory(handoff, excluded_paths=(sdk.INVENTORY_NAME,)), records)
        mode = stat.S_IMODE((handoff / sdk.REQUEST_NAME).stat().st_mode)
        cloned = handoff / "inputs/contractPayload/file"
        self.assertEqual(stat.S_IMODE(cloned.stat().st_mode), mode)
        self.assertNotEqual(cloned.stat().st_ino, arguments["contract_payload"].stat().st_ino)
