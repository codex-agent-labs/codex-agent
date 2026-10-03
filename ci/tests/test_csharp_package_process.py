"""The real C# package command must reuse its compiled binary."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "codex-agent-bindings/csharp/src/CodexAgent"
NATIVE_FILES = (
    "osx-arm64/libcodex_agent.dylib", "osx-x64/libcodex_agent.dylib",
    "linux-arm64/libcodex_agent.so", "linux-x64/libcodex_agent.so",
    "win-x64/codex_agent.dll",
)


@unittest.skipUnless(shutil.which("dotnet"), ".NET SDK unavailable")
class CsharpPackageProcessTest(unittest.TestCase):
    def test_package_only_never_enters_compile_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="csharp-package-process-") as temporary:
            root = Path(temporary)
            project = root / "csharp/src/CodexAgent"
            shutil.copytree(PROJECT, project, ignore=shutil.ignore_patterns("bin", "obj"))
            native = root / "csharp/native"
            native.mkdir()
            (native / "sdk-compatibility.json").write_text("{}\n")
            (native / "sdk-runtime-root.pub").write_text("root\n")
            for name in NATIVE_FILES:
                path = native / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"local process fixture\n")
            feed = root / "empty-feed"
            feed.mkdir()
            base = ("dotnet",)
            subprocess.run((*base, "restore", str(project / "CodexAgent.csproj"),
                            "--source", str(feed), "-p:NuGetAudit=false"),
                           check=True, capture_output=True, text=True, timeout=120)
            subprocess.run((*base, "build", str(project / "CodexAgent.csproj"),
                            "--configuration", "Release", "--no-restore",
                            "-p:NuGetAudit=false"),
                           check=True, capture_output=True, text=True, timeout=120)
            guard = project / "Directory.Build.targets"
            guard.write_text("""<Project>
  <Target Name="RejectPackageCompilation" BeforeTargets="CoreCompile;Compile">
    <Error Text="package invoked compiler target" />
  </Target>
</Project>
""")
            output = root / "packages"
            subprocess.run((*base, "pack", str(project / "CodexAgent.csproj"),
                            "--configuration", "Release", "--no-build", "--no-restore",
                            "--output", str(output), "-p:NuGetAudit=false"),
                           check=True, capture_output=True, text=True, timeout=120)
            package = output / "CodexAgent.0.8.0.nupkg"
            self.assertTrue(package.is_file())
            with zipfile.ZipFile(package) as archive:
                self.assertIn("lib/net8.0/CodexAgent.dll", archive.namelist())
            probe = subprocess.run((*base, "build", str(project / "CodexAgent.csproj"),
                                    "--configuration", "Release", "--no-restore",
                                    "-t:Rebuild", "-p:NuGetAudit=false"),
                                   capture_output=True, text=True, timeout=120)
            self.assertNotEqual(0, probe.returncode)
            self.assertIn("package invoked compiler target", probe.stdout + probe.stderr)


if __name__ == "__main__":
    unittest.main()
