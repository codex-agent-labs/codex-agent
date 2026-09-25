"""Package-only CMake must never emit a C++ SDK without its trust root."""

from pathlib import Path
import hashlib
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
        with tempfile.TemporaryDirectory(prefix="cpp-sdk-root-") as temporary:
            root = Path(temporary)
            sdk = root / "sdk"
            for member in (
                "include/codex_agent.h",
                "lib/libcodex_agent.dylib",
                "share/CodexAgent/native/sdk-compatibility.json",
                "LICENSE.txt",
            ):
                path = sdk / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(member.encode())
            command = [cmake, "-S", str(SOURCE), "-B", str(root / "build"),
                       "-DCODEX_AGENT_CPP_PACKAGE_ONLY=ON",
                       f"-DCodexAgent_C_SDK_ROOT={sdk}",
                       "-DCodexAgent_NATIVE_CLASSIFIER=macos-arm64"]
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


if __name__ == "__main__":
    unittest.main()
