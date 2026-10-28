"""Package-only C++ installation must not configure or run a compiler."""

from pathlib import Path
import os
import platform
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2]


class PackageOnlyProcessTest(unittest.TestCase):
    def test_install_with_no_host_compilers(self):
        cmake = shutil.which("cmake")
        if cmake is None:
            self.skipTest("CMake is unavailable")
        system = platform.system()
        machine = platform.machine().lower()
        host = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(system)
        arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
        if host is None or arch is None or (host == "windows" and arch != "x64"):
            self.skipTest("No supported C++ package classifier for this host")
        library = {"macos": "lib/libcodex_agent.dylib", "linux": "lib/libcodex_agent.so",
                   "windows": "bin/codex_agent.dll"}[host]
        with tempfile.TemporaryDirectory(prefix="cpp-package-only-") as temporary:
            root = Path(temporary)
            sdk = root / "sdk"
            for name in ("include/codex_agent.h", library,
                         "share/CodexAgent/native/sdk-compatibility.json",
                         "share/CodexAgent/native/sdk-runtime-root.pub", "LICENSE.txt",
                         *(["lib/libcodex_agent.so.1"] if host == "linux" else []),
                         *(["lib/libcodex_agent.dll.a", "lib/codex_agent.lib"] if host == "windows" else [])):
                member = sdk / name
                member.parent.mkdir(parents=True, exist_ok=True)
                member.write_bytes(name.encode())
            (sdk / "share/CodexAgent/native/sdk-runtime-root.pub").write_bytes(
                (SOURCE.parents[1] / "gradle/release/keys/sdk-runtime-root.pub").read_bytes())
            environment = {**os.environ, "CC": str(root / "missing-cc"),
                           "CXX": str(root / "missing-cxx")}
            build = root / "build"
            for command in ([cmake, "-S", str(SOURCE), "-B", str(build),
                             "-DCODEX_AGENT_CPP_PACKAGE_ONLY=ON",
                             f"-DCodexAgent_C_SDK_ROOT={sdk}",
                             f"-DCodexAgent_NATIVE_CLASSIFIER={host}-{arch}"],
                            [cmake, "--install", str(build), "--prefix", str(root / "installed")]):
                result = subprocess.run(command, capture_output=True, text=True, env=environment)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertFalse((build / "CMakeFiles/CMakeCXXCompiler.cmake").exists())
            self.assertFalse((build / "CMakeFiles/CodexAgentLoader.dir").exists())
            self.assertFalse(any(path.suffix in {".o", ".obj", ".a", ".lib"}
                                 for path in build.rglob("*")))
            self.assertTrue((root / "installed/include/codex_agent/codex_agent.hpp").is_file())


if __name__ == "__main__":
    unittest.main()
