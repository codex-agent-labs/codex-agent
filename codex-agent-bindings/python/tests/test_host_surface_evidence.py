"""Compiler-free checks of the existing host-surface producer, not native proof."""
from __future__ import annotations

import os
import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import test_zzzz_host_ready_parity as host


class HostSurfaceEvidenceTest(unittest.TestCase):
    def test_original_source_object_and_lossless_diagnostics_survive_compiler(self):
        for compiler in ("cc", "clang", "cl"):
            with self.subTest(compiler=compiler), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence = root / "build/host-surface-evidence"

                def compile(command, **kwargs):
                    self.assertEqual(evidence, kwargs["cwd"])
                    self.assertEqual(subprocess.PIPE, kwargs["stdout"])
                    self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
                    self.assertNotIn("text", kwargs)
                    self.assertIn("/WX" if compiler == "cl" else "-Werror", command)
                    self.assertIn(f"/Fo{evidence / 'host_surface.o'}" if compiler == "cl"
                                  else str(evidence / "host_surface.o"), command)
                    self.assertIn("CODEX_AGENT_HOST_STATE_READY == 4", (evidence / "host_surface.c").read_text())
                    (evidence / "host_surface.o").write_bytes(b"synthetic object\x00")
                    return subprocess.CompletedProcess(command, 0, b"\xff\x00\r\n", b"")

                with patch.object(host, "ROOT", root), patch.object(host, "c_include_directory", return_value=root), \
                        patch.dict(os.environ, {"CC": compiler}), patch.object(host.subprocess, "run", side_effect=compile):
                    host._compile_host_surface()
                self.assertEqual(b"synthetic object\x00", (evidence / "host_surface.o").read_bytes())
                capture = json.loads((evidence / "compiler-execution.json").read_bytes())
                self.assertEqual(0, capture["exitCode"])
                self.assertEqual(b"\xff\x00\r\n", base64.b64decode(capture["outputBase64"], validate=True))

    def test_failure_or_success_without_new_object_never_accepts_stale_object(self):
        for status in (0, 7):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence = root / "build/host-surface-evidence"
                evidence.mkdir(parents=True)
                (evidence / "host_surface.o").write_bytes(b"stale")
                with patch.object(host, "ROOT", root), patch.object(host, "c_include_directory", return_value=root), \
                        patch.dict(os.environ, {"CC": "cc"}), patch.object(host.subprocess, "run", return_value=
                            subprocess.CompletedProcess([], status, b"\xfffailure\r\n")), \
                        self.assertRaises(AssertionError):
                    host._compile_host_surface()
                self.assertFalse((evidence / "host_surface.o").exists())
                self.assertTrue((evidence / "host_surface.c").is_file())
                capture = json.loads((evidence / "compiler-execution.json").read_bytes())
                self.assertEqual(status, capture["exitCode"])
                self.assertEqual(b"\xfffailure\r\n", base64.b64decode(capture["outputBase64"], validate=True))
