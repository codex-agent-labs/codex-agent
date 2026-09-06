"""Mocked command tests only; no compiler or five-host acceptance is inferred."""
from __future__ import annotations

import os
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_mcp_value_parity as mcp
import test_runtime_loader_security as loader


class NativeFixtureCommandsTest(unittest.TestCase):
    def test_mcp_uses_explicit_imports_and_exports_for_each_host_compiler(self):
        original = (mcp.ROOT / "tests/real_mcp_value_fixture.c").read_bytes()
        self.assertIn(b"#define FIXTURE_API __declspec(dllexport)", original)
        self.assertIn(b"FIXTURE_API codex_agent_status_t", original)
        for system, compiler in (("Darwin", "cc"), ("Linux", "cc"), ("Windows", "cl"), ("Windows", "clang")):
            with self.subTest(system=system, compiler=compiler), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "tests").mkdir()
                (root / "tests/real_mcp_value_fixture.c").write_bytes(original)
                sdk = root / "imported"
                (sdk / "lib").mkdir(parents=True)
                library = sdk / ("codex_agent.dll" if system == "Windows" else "libcodex_agent.so")
                library.write_bytes(b"original runtime")
                import_library = sdk / "lib/codex_agent.lib"
                import_library.write_bytes(b"original import library")

                def compile(command, **kwargs):
                    expected = import_library if system == "Windows" else library
                    self.assertIn(str(expected), command)
                    self.assertNotIn("-lcodex_agent", command)
                    self.assertEqual(root / "build/mcp-value-evidence", kwargs["cwd"])
                    if system == "Windows":
                        self.assertNotIn(str(library), command)
                        self.assertNotIn("-fPIC", command)
                        self.assertFalse(any("rpath" in str(item) for item in command))
                    if compiler == "cl":
                        self.assertIn("/WX", command)
                        output = Path(next(item[4:] for item in command if item.startswith("/Fe:")))
                    else:
                        self.assertIn("-Werror", command)
                        output = Path(command[command.index("-o") + 1])
                    self.assertEqual(".dll" if system == "Windows" else ".dylib" if system == "Darwin" else ".so", output.suffix)
                    output.write_bytes(b"synthetic fixture library")
                    return subprocess.CompletedProcess(command, 0, b"\x00\xff", b"")

                with patch.object(mcp, "ROOT", root), patch.object(mcp.platform, "system", return_value=system), \
                        patch.object(mcp, "c_sdk_root", return_value=sdk), \
                        patch.object(mcp, "c_include_directory", return_value=sdk), \
                        patch.dict(os.environ, {"CC": compiler}), patch.object(mcp.subprocess, "run", side_effect=compile):
                    mcp._compile_fixture(library)
                evidence = root / "build/mcp-value-evidence"
                self.assertEqual(original, (evidence / "real_mcp_value_fixture.c").read_bytes())
                capture = json.loads((evidence / "compiler-execution.json").read_bytes())
                self.assertEqual(b"\x00\xff", base64.b64decode(capture["outputBase64"], validate=True))
                self.assertEqual(b"original runtime", library.read_bytes())
                self.assertEqual(b"original import library", import_library.read_bytes())

    def test_windows_mcp_missing_import_library_never_invokes_compiler(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            (root / "tests/real_mcp_value_fixture.c").write_bytes(b"source")
            with patch.object(mcp, "ROOT", root), patch.object(mcp.platform, "system", return_value="Windows"), \
                    patch.object(mcp, "c_sdk_root", return_value=root), patch.object(mcp.subprocess, "run") as compiler, \
                    self.assertRaisesRegex(AssertionError, "link library"):
                mcp._compile_fixture(root / "codex_agent.dll")
            compiler.assert_not_called()

    def test_loader_fixture_exports_and_commands_preserve_identity_and_abi(self):
        for system, compiler in (("Darwin", "cc"), ("Linux", "cc"), ("Windows", "cl"), ("Windows", "clang")):
            with self.subTest(system=system, compiler=compiler), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)

                def compile(command, **kwargs):
                    self.assertEqual(root, kwargs["cwd"])
                    source = (root / "fixture.c").read_text()
                    self.assertIn("__declspec(dllexport)", source)
                    self.assertIn("API int32_t codex_agent_runtime_identity", source)
                    self.assertIn("UINT32_C(0x00010d00)", source)
                    if system == "Windows":
                        self.assertNotIn("-fPIC", command)
                    output = Path(next(item[4:] for item in command if item.startswith("/Fe:"))) if compiler == "cl" \
                        else Path(command[command.index("-o") + 1])
                    self.assertEqual(".dll" if system == "Windows" else ".dylib" if system == "Darwin" else ".so", output.suffix)
                    output.write_bytes(b"synthetic loader library")
                    return subprocess.CompletedProcess(command, 0, b"\xff\r\n")

                with patch.object(loader.platform, "system", return_value=system), \
                        patch.dict(os.environ, {"CC": compiler}), patch.object(loader.subprocess, "run", side_effect=compile):
                    loader.compile_library(root, "fixture", b'{"schemaVersion":1}\n', 0x00010D00)
                capture = json.loads((root / "fixture-compiler-execution.json").read_bytes())
                self.assertEqual(b"\xff\r\n", base64.b64decode(capture["outputBase64"], validate=True))

    def test_native_loader_assertions_run_in_child_with_lossless_retained_capture(self):
        for name in loader.NATIVE_LOADER_TESTS:
            for status, raw in ((0, b""), (3, b"\xffchild failure\x00\r\n")):
                with self.subTest(name=name, status=status), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    with patch.object(loader, "ROOT", root), patch.object(loader.subprocess, "run", return_value=
                            subprocess.CompletedProcess([], status, raw)) as run, \
                            patch.object(loader, "compile_library") as compiler, \
                            patch.object(loader.ctypes, "CDLL") as dynamic_loader:
                        if status:
                            with self.assertRaisesRegex(AssertionError, "child failed"):
                                loader._run_native_loader_test(name)
                        else:
                            loader._run_native_loader_test(name)
                        compiler.assert_not_called()
                        dynamic_loader.assert_not_called()
                    directory = root / "build/loader-security-evidence" / name
                    self.assertEqual(["--native-loader-child", name, str(directory)], run.call_args.args[0][-3:])
                    self.assertEqual(subprocess.STDOUT, run.call_args.kwargs["stderr"])
                    contents = (directory / "child-execution.json").read_bytes()
                    capture = json.loads(contents)
                    self.assertEqual(status, capture["exitCode"])
                    self.assertEqual(raw, base64.b64decode(capture["outputBase64"], validate=True))
                    self.assertEqual((json.dumps(capture, sort_keys=True, separators=(",", ":")) + "\n").encode(), contents)
