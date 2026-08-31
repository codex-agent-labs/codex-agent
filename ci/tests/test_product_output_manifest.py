from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json,
    sha256_bytes,
    snapshot_regular_tree,
)
from ci.products.receipt import (
    verify_output_manifest,
    verify_output_manifest_identity,
    write_output_manifest,
)


REPOSITORY = Path(__file__).resolve().parents[2]
SNAPSHOT_TEMP_ROOT = "/private/tmp" if sys.platform == "darwin" else None


class ProductOutputManifestTest(unittest.TestCase):
    def test_descriptor_snapshot_is_immutable_and_rejects_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            payload = self.write(source, "nested/payload.bin", b"original")
            destination = root / "snapshot"

            snapshot_regular_tree(source, destination)
            payload.write_bytes(b"changed")

            self.assertEqual(b"original", (destination / "nested/payload.bin").read_bytes())
            self.assertEqual(payload.stat().st_mode & 0o777, (destination / "nested/payload.bin").stat().st_mode & 0o777)
            with self.assertRaisesRegex(ValueError, "must not exist"):
                snapshot_regular_tree(source, destination)

    def test_descriptor_snapshot_never_replaces_a_racing_destination(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            destination = root / "snapshot"
            real_mkdir = os.mkdir
            raced = False

            def racing_mkdir(path: str | bytes, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
                nonlocal raced
                if path == destination.name and dir_fd is not None and not raced:
                    raced = True
                    real_mkdir(path, mode, dir_fd=dir_fd)
                    victim = os.open(
                        f"{destination.name}/victim",
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=dir_fd,
                    )
                    os.write(victim, b"must survive")
                    os.close(victim)
                real_mkdir(path, mode, dir_fd=dir_fd)

            with mock.patch("ci.products.inventory.os.mkdir", side_effect=racing_mkdir):
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    snapshot_regular_tree(source, destination)
            self.assertEqual(b"must survive", (destination / "victim").read_bytes())

    def test_descriptor_snapshot_rejects_racing_final_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            destination = root / "snapshot"
            victim = root / "victim"
            self.write(victim, "sentinel.bin", b"must survive")
            real_mkdir = os.mkdir
            raced = False

            def racing_mkdir(path: str | bytes, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
                nonlocal raced
                real_mkdir(path, mode, dir_fd=dir_fd)
                if path == destination.name and dir_fd is not None and not raced:
                    raced = True
                    os.rmdir(path, dir_fd=dir_fd)
                    os.symlink(victim, path, target_is_directory=True, dir_fd=dir_fd)

            with mock.patch("ci.products.inventory.os.mkdir", side_effect=racing_mkdir):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    snapshot_regular_tree(source, destination)
            self.assertEqual(b"must survive", (victim / "sentinel.bin").read_bytes())
            self.assertFalse((victim / "payload.bin").exists())

    def test_descriptor_snapshot_rejects_racing_nested_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "nested/payload.bin", b"payload")
            destination = root / "snapshot"
            victim = root / "victim"
            self.write(victim, "sentinel.bin", b"must survive")
            real_mkdir = os.mkdir
            raced = False

            def racing_mkdir(path: str | bytes, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
                nonlocal raced
                real_mkdir(path, mode, dir_fd=dir_fd)
                if path == "nested" and dir_fd is not None and not raced:
                    raced = True
                    os.rmdir(path, dir_fd=dir_fd)
                    os.symlink(victim, path, target_is_directory=True, dir_fd=dir_fd)

            with mock.patch("ci.products.inventory.os.mkdir", side_effect=racing_mkdir):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    snapshot_regular_tree(source, destination)
            self.assertEqual(b"must survive", (victim / "sentinel.bin").read_bytes())
            self.assertFalse((victim / "payload.bin").exists())

    def test_descriptor_snapshot_rejects_created_reparse_directories(self) -> None:
        for raced_name in ("snapshot", "nested"):
            with self.subTest(raced_name=raced_name), tempfile.TemporaryDirectory(
                dir=SNAPSHOT_TEMP_ROOT,
            ) as temporary:
                root = Path(temporary)
                source = root / "source"
                self.write(source, "nested/payload.bin", b"payload")
                destination = root / "snapshot"
                reparse_identities: set[tuple[int, int]] = set()
                real_mkdir = os.mkdir

                def marked_mkdir(path: str | bytes, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
                    real_mkdir(path, mode, dir_fd=dir_fd)
                    if path == raced_name and dir_fd is not None:
                        metadata = os.stat(path, dir_fd=dir_fd, follow_symlinks=False)
                        reparse_identities.add((metadata.st_dev, metadata.st_ino))

                def marked_reparse(value: os.stat_result) -> bool:
                    return (value.st_dev, value.st_ino) in reparse_identities

                with (
                    mock.patch("ci.products.inventory.os.mkdir", side_effect=marked_mkdir),
                    mock.patch("ci.products.inventory._is_reparse_point", side_effect=marked_reparse),
                ):
                    with self.assertRaisesRegex(ValueError, "unsafe"):
                        snapshot_regular_tree(source, destination)

    def test_descriptor_snapshot_rejects_symbolic_and_reparse_destination_ancestors(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            real_parent = root / "real-parent"
            real_parent.mkdir()
            symbolic_parent = root / "symbolic-parent"
            try:
                symbolic_parent.symlink_to(real_parent, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links are unavailable: {error}")
            with self.assertRaises(ValueError):
                snapshot_regular_tree(source, symbolic_parent / "snapshot")
            self.assertFalse((real_parent / "snapshot").exists())

            reparse_parent = root / "reparse-parent"
            reparse_parent.mkdir()
            identity = reparse_parent.stat().st_ino
            with mock.patch(
                "ci.products.inventory._is_reparse_point",
                side_effect=lambda value: value.st_ino == identity,
            ):
                with self.assertRaises(ValueError):
                    snapshot_regular_tree(source, reparse_parent / "snapshot")
            self.assertFalse((reparse_parent / "snapshot").exists())

    def test_descriptor_snapshot_rejects_symbolic_root_and_intermediate(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "nested/payload.bin", b"payload")
            symbolic_root = root / "symbolic-root"
            try:
                symbolic_root.symlink_to(source, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links are unavailable: {error}")
            with self.assertRaises(ValueError):
                snapshot_regular_tree(symbolic_root, root / "root-output")

            unsafe = root / "unsafe"
            unsafe.mkdir()
            (unsafe / "nested").symlink_to(source / "nested", target_is_directory=True)
            with self.assertRaises(ValueError):
                snapshot_regular_tree(unsafe, root / "nested-output")

    def test_descriptor_snapshot_rejects_overlap_and_membership_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                snapshot_regular_tree(source, source / "snapshot")

            real_listdir = os.listdir
            source_lists = 0

            def racing_listdir(path):
                nonlocal source_lists
                result = real_listdir(path)
                if isinstance(path, int):
                    source_lists += 1
                    if source_lists == 2:
                        self.write(source, "late.bin", b"late")
                return result

            with mock.patch("ci.products.inventory.os.listdir", side_effect=racing_listdir):
                with self.assertRaisesRegex(ValueError, "changed while copying"):
                    snapshot_regular_tree(source, root / "snapshot")

    def test_windows_snapshot_uses_no_descriptor_relative_api_and_publishes_atomically(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "nested/payload.bin", b"payload")
            destination = root / "snapshot"
            real_open = os.open
            real_rename = os.rename
            published = False

            def no_dir_fd_open(*args, **kwargs):
                self.assertIsNone(kwargs.get("dir_fd"))
                return real_open(*args, **kwargs)

            def observed_rename(staged, final, *args, **kwargs):
                nonlocal published
                self.assertFalse(destination.exists())
                self.assertEqual(b"payload", (Path(staged) / "nested/payload.bin").read_bytes())
                result = real_rename(staged, final, *args, **kwargs)
                published = True
                return result

            with (
                mock.patch("ci.products.inventory._is_windows", return_value=True),
                mock.patch("ci.products.inventory.os.open", side_effect=no_dir_fd_open),
                mock.patch("ci.products.inventory.os.rename", side_effect=observed_rename),
            ):
                snapshot_regular_tree(source, destination)
            self.assertTrue(published)
            self.assertEqual(b"payload", (destination / "nested/payload.bin").read_bytes())

    def test_windows_snapshot_source_mutation_leaves_no_destination_or_staging_residue(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            payload = self.write(source, "payload.bin", b"payload")
            destination = root / "snapshot"
            from ci.products import inventory
            real_copy = inventory._copy_windows_snapshot_file

            def mutating_copy(source_file, destination_file, expected):
                digest = real_copy(source_file, destination_file, expected)
                payload.write_bytes(b"changed")
                return digest

            with (
                mock.patch("ci.products.inventory._is_windows", return_value=True),
                mock.patch("ci.products.inventory._copy_windows_snapshot_file", side_effect=mutating_copy),
            ):
                with self.assertRaisesRegex(ValueError, "changed"):
                    snapshot_regular_tree(source, destination)
            self.assertFalse(destination.exists())
            self.assertEqual([], list(root.glob(".snapshot-snapshot-*")))

    def test_windows_snapshot_preserves_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            destination = root / "snapshot"
            self.write(destination, "sentinel.bin", b"must survive")
            with mock.patch("ci.products.inventory._is_windows", return_value=True):
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    snapshot_regular_tree(source, destination)
            self.assertEqual(b"must survive", (destination / "sentinel.bin").read_bytes())

    def test_windows_snapshot_rejects_overlap_and_reparse_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "payload.bin", b"payload")
            with mock.patch("ci.products.inventory._is_windows", return_value=True):
                with self.assertRaisesRegex(ValueError, "must not overlap"):
                    snapshot_regular_tree(source, source / "nested")

            identity = source.stat().st_ino
            with (
                mock.patch("ci.products.inventory._is_windows", return_value=True),
                mock.patch(
                    "ci.products.inventory._is_reparse_point",
                    side_effect=lambda value: value.st_ino == identity,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    snapshot_regular_tree(source, root / "snapshot")

    def test_private_resnapshot_requires_manifest_reverification_before_use(self) -> None:
        with tempfile.TemporaryDirectory(dir=SNAPSHOT_TEMP_ROOT) as temporary:
            root = Path(temporary)
            source = root / "source"
            self.write(source, "outputs/payload.bin", b"original")
            write_output_manifest(
                source,
                "runtime",
                "linux-x64",
                "package",
                "linux-x64",
                "1.2.3",
                {"payload": "outputs"},
            )
            outer = root / "outer"
            private = root / "private"
            snapshot_regular_tree(source, outer)
            (outer / "outputs/payload.bin").write_bytes(b"mutated")
            snapshot_regular_tree(outer, private)

            with self.assertRaises(ValueError):
                verify_output_manifest_identity(
                    private,
                    "runtime",
                    "linux-x64",
                    "package",
                    "linux-x64",
                    "1.2.3",
                )

    def test_imported_manifest_identity_and_tree_are_verified_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/binary/value.bin", b"value")
            expected = self.write_manifest(root, {"binary": "outputs/binary"})

            self.assertEqual(
                expected,
                verify_output_manifest_identity(
                    root, "runtime", "macos-arm64", "binary", "macos-arm64", "1.2.3",
                ),
            )
            original = (root / "output-manifest.json").read_bytes()
            with self.assertRaises(ValueError):
                verify_output_manifest_identity(
                    root, "runtime", "linux-x64", "binary", "macos-arm64", "1.2.3",
                )
            self.assertEqual(original, (root / "output-manifest.json").read_bytes())

    def test_direct_writer_emits_canonical_exact_tree_and_reverifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            library = self.write(root, "outputs/c-abi/libcodex_agent.dylib", b"library")
            supervisor = self.write(
                root,
                "outputs/supervisor/codex-process-supervisor",
                b"supervisor",
            )

            manifest = write_output_manifest(
                root,
                "runtime",
                "macos-arm64",
                "binary",
                "macos-arm64",
                "1.2.3",
                {
                    "c-abi-library": "outputs/c-abi",
                    "supervisor": "outputs/supervisor",
                },
            )
            expected = {
                "schemaVersion": 1,
                "product": "runtime",
                "component": "macos-arm64",
                "phase": "binary",
                "target": "macos-arm64",
                "productVersion": "1.2.3",
                "outputs": [
                    {
                        "kind": "c-abi-library",
                        "relativePath": "outputs/c-abi/libcodex_agent.dylib",
                        "bytes": library.stat().st_size,
                        "sha256": sha256_bytes(library.read_bytes()),
                    },
                    {
                        "kind": "supervisor",
                        "relativePath": "outputs/supervisor/codex-process-supervisor",
                        "bytes": supervisor.stat().st_size,
                        "sha256": sha256_bytes(supervisor.read_bytes()),
                    },
                ],
            }
            manifest_file = root / "output-manifest.json"
            self.assertEqual(expected, manifest)
            self.assertEqual(expected, load_canonical_json(manifest_file))
            self.assertEqual(canonical_json_bytes(expected), manifest_file.read_bytes())
            self.assertEqual(expected, verify_output_manifest(root, manifest))

            library.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_output_manifest(root, manifest)

    def test_direct_writer_rejects_missing_roots_and_no_outputs(self) -> None:
        cases = (
            ({}, None),
            ({"binary": "outputs/binary"}, None),
            ({"binary": "outputs/missing"}, ("outputs/other/value.bin", b"value")),
        )
        for output_roots, file_value in cases:
            with self.subTest(output_roots=output_roots), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                if file_value is not None:
                    self.write(root, *file_value)
                with self.assertRaises(ValueError):
                    self.write_manifest(root, output_roots)
                self.assertFalse((root / "output-manifest.json").exists())

    def test_direct_writer_rejects_duplicate_ambiguous_and_unsafe_roots(self) -> None:
        cases = (
            (
                {
                    "binary": "outputs/shared",
                    "library": "outputs/shared",
                },
                "outputs/shared/value.bin",
            ),
            (
                {
                    "binary": "outputs",
                    "library": "outputs/library",
                },
                "outputs/library/value.bin",
            ),
            (
                {
                    "binary": "outputs/library",
                    "library": "outputs",
                },
                "outputs/library/value.bin",
            ),
        )
        for output_roots, output_path in cases:
            with self.subTest(output_roots=output_roots), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write(root, output_path, b"value")
                with self.assertRaises(ValueError):
                    self.write_manifest(root, output_roots)
                self.assertFalse((root / "output-manifest.json").exists())

    def test_direct_writer_rejects_empty_symlinked_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/binary/value.bin", b"")
            with self.assertRaises(ValueError):
                self.write_manifest(root, {"binary": "outputs/binary"})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "stage"
            root.mkdir()
            target = self.write(Path(temporary), "target.bin", b"target")
            link = root / "outputs/binary/value.bin"
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links are unavailable: {error}")
            with self.assertRaises(ValueError):
                self.write_manifest(root, {"binary": "outputs/binary"})

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/binary/value.bin", b"value")
            self.write(root, "unexpected.txt", b"extra")
            with self.assertRaises(ValueError):
                self.write_manifest(root, {"binary": "outputs/binary"})

    def test_failure_removes_stale_manifest_and_successful_rerun_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/binary/value.bin", b"value")
            manifest_file = root / "output-manifest.json"
            manifest_file.write_text("stale success\n", encoding="utf-8")
            self.write(root, "outside.bin", b"unexpected")

            with self.assertRaises(ValueError):
                self.write_manifest(root, {"binary": "outputs/binary"})
            self.assertFalse(manifest_file.exists())

            (root / "outside.bin").unlink()
            first = self.write_manifest(root, {"binary": "outputs/binary"})
            first_bytes = manifest_file.read_bytes()
            second = self.write_manifest(root, {"binary": "outputs/binary"})
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, manifest_file.read_bytes())

    def test_symlinked_stage_root_fails_without_deleting_target_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            self.write(target, "outputs/binary/value.bin", b"value")
            manifest = target / "output-manifest.json"
            original = b"existing target manifest\n"
            manifest.write_bytes(original)
            stage = base / "stage"
            try:
                stage.symlink_to(target, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symbolic links are unavailable: {error}")

            with self.assertRaises(ValueError):
                self.write_manifest(stage, {"binary": "outputs/binary"})

            self.assertEqual(original, manifest.read_bytes())

    def test_cli_writes_and_reverifies_the_same_canonical_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/library/libcodex_agent.so", b"library")
            self.write(root, "outputs/header/codex_agent.h", b"header")

            result = self.run_cli(
                root,
                "--output-root", "c-abi-library=outputs/library",
                "--output-root", "c-abi-header=outputs/header",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            manifest = load_canonical_json(root / "output-manifest.json")
            self.assertEqual(manifest, verify_output_manifest(root, manifest))
            self.assertEqual(
                ["c-abi-header", "c-abi-library"],
                sorted(record["kind"] for record in manifest["outputs"]),
            )

    def test_cli_rejects_duplicate_kinds_and_removes_stale_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write(root, "outputs/first/value.bin", b"first")
            self.write(root, "outputs/second/value.bin", b"second")
            manifest_file = root / "output-manifest.json"
            manifest_file.write_text("stale success\n", encoding="utf-8")

            result = self.run_cli(
                root,
                "--output-root", "binary=outputs/first",
                "--output-root", "binary=outputs/second",
            )
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(manifest_file.exists())

    def write_manifest(self, root: Path, output_roots: dict[str, str]):
        return write_output_manifest(
            root,
            "runtime",
            "macos-arm64",
            "binary",
            "macos-arm64",
            "1.2.3",
            output_roots,
        )

    def run_cli(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products.receipt",
                "write-output-manifest",
                "--root", str(root),
                "--product", "runtime",
                "--component", "linux-x64",
                "--phase", "binary",
                "--target", "linux-x64",
                "--product-version", "1.2.3",
                *arguments,
            ],
            cwd=REPOSITORY,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    @staticmethod
    def write(root: Path, relative: str, contents: bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path


if __name__ == "__main__":
    unittest.main()
