"""Installed consumer path wiring, without loading or compiling a Runtime."""

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_agent._ffi import resolve_library_path  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "host_consumer_paths", ROOT / "consumer/host_smoke.py"
)
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


class HostConsumerPathsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-agent-host-path-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.library = self.root / "runtime"
        self.library.write_bytes(b"path fixture, not a native Runtime\n")

    def invoke(self, arguments, create_host):
        with patch.object(sys, "argv", ["host_smoke.py", *map(str, arguments)]), \
                patch.object(consumer, "CodexHost", side_effect=create_host) as factory, \
                patch("sys.stdout", new_callable=io.StringIO), \
                patch("sys.stderr", new_callable=io.StringIO):
            consumer.main()
        return factory

    def test_default_and_exact_override_preserve_host_checks(self):
        for arguments, expected in (([], None), ([self.library], self.library)):
            with self.subTest(arguments=arguments):
                close = AsyncMock()

                def host(*args, library_path):
                    self.assertEqual(library_path, expected)
                    if library_path is not None:
                        self.assertEqual(resolve_library_path(library_path), expected)
                    return SimpleNamespace(
                        state=SimpleNamespace(current=consumer.HostState(consumer.HostStateKind.NEW)),
                        aclose=close,
                    )

                self.invoke(arguments, host).assert_called_once()
                self.assertEqual(close.await_count, 2)

    def test_symlink_file_and_parent_reach_existing_loader_unchanged(self):
        file_link = self.root / "linked-runtime"
        file_link.symlink_to(self.library)
        parent_link = self.root / "linked-parent"
        parent_link.symlink_to(self.root, target_is_directory=True)
        for original in (file_link, parent_link / self.library.name):
            with self.subTest(original=original):
                observed = []

                def host(*args, library_path):
                    observed.append(library_path)
                    resolve_library_path(library_path)
                    self.fail("the existing loader accepted a symbolic Runtime path")

                with self.assertRaisesRegex(OSError, "symlinks or reparse points"):
                    self.invoke([original], host)
                self.assertEqual(observed, [original])
                self.assertEqual(self.library.read_bytes(), b"path fixture, not a native Runtime\n")

    def test_relative_extra_missing_and_directory_overrides_fail_before_host(self):
        for arguments in (["runtime"], [self.library, self.library],
                          [self.root / "missing"], [self.root]):
            with self.subTest(arguments=arguments):
                with self.assertRaises(SystemExit) as failure:
                    self.invoke(arguments, lambda *args, **kwargs: self.fail("Host was constructed"))
                self.assertEqual(failure.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
