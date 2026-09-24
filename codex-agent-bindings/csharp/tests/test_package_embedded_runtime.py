"""The public C# package cannot silently omit its embedded Runtime."""

import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1] / "src/CodexAgent/CodexAgent.csproj"
MEMBERS = (
    "osx-arm64/libcodex_agent.dylib",
    "osx-x64/libcodex_agent.dylib",
    "linux-arm64/libcodex_agent.so",
    "linux-x64/libcodex_agent.so",
    "win-x64/codex_agent.dll",
)


@unittest.skipUnless(shutil.which("dotnet"), "dotnet is not installed")
class PackageEmbeddedRuntimeTest(unittest.TestCase):
    def test_native_assets_are_required_without_opt_in(self) -> None:
        target = next(item for item in ET.parse(PROJECT).getroot().iter("Target")
                      if item.get("Name") == "RequireCodexAgentNativeAssets")
        self.assertEqual("GenerateNuspec", target.get("BeforeTargets"))
        self.assertIsNone(target.get("Condition"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "src/CodexAgent/CodexAgent.csproj"
            project.parent.mkdir(parents=True)
            shutil.copyfile(PROJECT, project)
            command = ["dotnet", "msbuild", str(project),
                       "-target:RequireCodexAgentNativeAssets", "-verbosity:quiet", "-nologo"]

            def check() -> subprocess.CompletedProcess[str]:
                return subprocess.run(command, capture_output=True, text=True, check=False)

            missing = check()
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("Missing Codex Agent SDK compatibility declaration", missing.stdout + missing.stderr)

            declaration = root / "native/sdk-compatibility.json"
            declaration.parent.mkdir(parents=True)
            declaration.write_text("{}\n")
            for member in MEMBERS:
                path = root / "native" / member
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            self.assertEqual(0, check().returncode)

            (root / "native" / MEMBERS[-1]).unlink()
            absent = check()
            self.assertNotEqual(0, absent.returncode)
            self.assertIn("Missing win-x64 Codex Agent C SDK library", absent.stdout + absent.stderr)


if __name__ == "__main__":
    unittest.main()
