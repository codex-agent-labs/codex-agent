"""Package-only CMake must never emit a C++ SDK without its trust root."""

from pathlib import Path
import hashlib
import platform
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2]


class PackageRootRequirementTest(unittest.TestCase):
    def test_root_is_required_and_pinned_in_installed_config(self):
        cmake = shutil.which("cmake")
        if cmake is None:
            self.skipTest("CMake is unavailable")
        system = platform.system()
        machine = platform.machine().lower()
        classifier = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(system)
        arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
        if classifier is None or arch is None or (classifier == "windows" and arch != "x64"):
            self.skipTest("No supported C++ package classifier for this host")
        classifier += "-" + arch
        library = {"macos": "lib/libcodex_agent.dylib", "linux": "lib/libcodex_agent.so",
                   "windows": "bin/codex_agent.dll"}[classifier.split("-")[0]]
        with tempfile.TemporaryDirectory(prefix="cpp-sdk-root-") as temporary:
            root = Path(temporary)
            sdk = root / "sdk"
            for member in (
                "include/codex_agent.h",
                library,
                "share/CodexAgent/native/sdk-compatibility.json",
                "LICENSE.txt",
                *(["lib/libcodex_agent.so.1"] if system == "Linux" else []),
                *(["lib/libcodex_agent.dll.a", "lib/codex_agent.lib"] if system == "Windows" else []),
            ):
                path = sdk / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(member.encode())
            command = [cmake, "-S", str(SOURCE), "-B", str(root / "build"),
                       "-DCODEX_AGENT_CPP_PACKAGE_ONLY=ON",
                       f"-DCodexAgent_C_SDK_ROOT={sdk}",
                       f"-DCodexAgent_NATIVE_CLASSIFIER={classifier}"]
            missing = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("sdk-runtime-root.pub", missing.stdout + missing.stderr)

            trusted_root = sdk / "share/CodexAgent/native/sdk-runtime-root.pub"
            root_bytes = (SOURCE.parents[1] / "gradle/release/keys/sdk-runtime-root.pub").read_bytes()
            trusted_root.write_bytes(root_bytes)
            present = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, present.returncode, present.stdout + present.stderr)
            config = (root / "build/CodexAgentConfig.cmake").read_text()
            self.assertIn(
                '"${CodexAgent_SDK_RUNTIME_ROOT}|' + hashlib.sha256(root_bytes).hexdigest() + '"',
                config,
            )
            installed = root / "installed"
            result = subprocess.run([cmake, "--install", str(root / "build"), "--prefix", str(installed)],
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            consumer = root / "consumer"
            consumer.mkdir()
            (consumer / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.24)\n"
                "project(CodexAgentHeaderTamper LANGUAGES CXX)\n"
                "find_package(CodexAgent REQUIRED CONFIG NO_DEFAULT_PATH)\n")

            def configure(name):
                return subprocess.run([cmake, "-S", str(consumer), "-B", str(root / name),
                                       f"-DCodexAgent_DIR={installed / 'lib/cmake/CodexAgent'}"],
                                      capture_output=True, text=True)

            baseline = configure("consumer-baseline")
            self.assertEqual(0, baseline.returncode, baseline.stdout + baseline.stderr)
            header = installed / "include/codex_agent/codex_agent.hpp"
            original_header = header.read_bytes()
            header.write_bytes(original_header + b"\n// tampered\n")
            tampered = configure("consumer-tampered")
            self.assertNotEqual(0, tampered.returncode)
            self.assertIn("verified package member hash mismatch", tampered.stdout + tampered.stderr)
            header.write_bytes(original_header)
            extra = header.parent / "unexpected.hpp"
            extra.write_bytes(b"// unexpected header\n")
            unexpected = configure("consumer-unexpected")
            self.assertNotEqual(0, unexpected.returncode)
            self.assertIn("wrapper header inventory differs", unexpected.stdout + unexpected.stderr)


if __name__ == "__main__":
    unittest.main()
