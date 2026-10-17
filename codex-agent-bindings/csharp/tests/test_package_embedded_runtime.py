"""The public C# package cannot silently omit its embedded Runtime."""

import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1] / "src/CodexAgent/CodexAgent.csproj"
ROOT = Path(__file__).resolve().parents[3]
CONSUMER = Path(__file__).resolve().parents[1] / "samples/CodexAgent.Consumer"
ROOT_INSPECTOR = Path(__file__).resolve().parents[1] / "tools/VerifySdkRuntimeRoot/VerifySdkRuntimeRoot.csproj"
PINNED_ROOT = ROOT / "gradle/release/keys/sdk-runtime-root.pub"
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
            no_root = check()
            self.assertNotEqual(0, no_root.returncode)
            self.assertIn("Missing Codex Agent SDK Runtime trust root", no_root.stdout + no_root.stderr)

            (root / "native/sdk-runtime-root.pub").write_text("fixture\n")
            self.assertEqual(0, check().returncode)

            (root / "native" / MEMBERS[-1]).unlink()
            absent = check()
            self.assertNotEqual(0, absent.returncode)
            self.assertIn("Missing win-x64 Codex Agent C SDK library", absent.stdout + absent.stderr)

    def test_installed_fixture_rejects_tampered_default_and_unattested_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            source = work / "src/CodexAgent"
            shutil.copytree(PROJECT.parent, source, ignore=shutil.ignore_patterns("bin", "obj"))
            native = work / "native"
            native.mkdir()
            shutil.copyfile(ROOT / "codex-agent-bindings/csharp/native/sdk-compatibility.json",
                            native / "sdk-compatibility.json")
            shutil.copyfile(PINNED_ROOT, native / "sdk-runtime-root.pub")
            for member in MEMBERS:
                library = native / member
                library.parent.mkdir(parents=True, exist_ok=True)
                library.write_bytes(b"tampered Runtime fixture")
            feed = work / "feed"
            feed.mkdir()
            cache = Path(os.environ.get("NUGET_PACKAGES", Path.home() / ".nuget/packages"))
            for directory in (cache / "microsoft.netcore.app.ref", cache / "microsoft.aspnetcore.app.ref",
                              *cache.glob("microsoft.netcore.app.host.*")):
                for package in directory.glob("*/*.nupkg"):
                    shutil.copyfile(package, feed / package.name)
            environment = {**os.environ, "DOTNET_CLI_HOME": str(work / "dotnet-home"),
                           "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                           "NUGET_PACKAGES": str(work / "packages")}
            environment.pop("CODEX_AGENT_LIBRARY", None)
            (work / "dotnet-home").mkdir()

            def run(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(["dotnet", *args], cwd=work, env=environment,
                                      capture_output=True, text=True, check=False)

            project = str(source / "CodexAgent.csproj")
            restored = run("restore", project, "--source", str(feed), "-p:NuGetAudit=false")
            self.assertEqual(0, restored.returncode, restored.stdout + restored.stderr)
            packed = run("pack", project, "--configuration", "Release", "--no-restore", "--output", str(feed))
            self.assertEqual(0, packed.returncode, packed.stdout + packed.stderr)
            self.assertTrue((feed / "CodexAgent.0.8.0.nupkg").is_file())
            consumer = work / "consumer"
            shutil.copytree(CONSUMER, consumer, ignore=shutil.ignore_patterns("bin", "obj"))
            consumer_project = str(consumer / "CodexAgent.Consumer.csproj")
            restored = run("restore", consumer_project, "--source", str(feed), "-p:NuGetAudit=false")
            self.assertEqual(0, restored.returncode, restored.stdout + restored.stderr)
            self.assertTrue((work / "packages/codexagent/0.8.0/codexagent.0.8.0.nupkg").is_file())
            compiled = run("build", consumer_project, "--configuration", "Release", "--no-restore")
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)

            def consumer_result(*args: str) -> str:
                result = run("run", "--project", consumer_project, "--configuration", "Release",
                             "--no-build", "--no-restore", "--", *args)
                self.assertNotEqual(0, result.returncode, "fixture Runtime unexpectedly loaded")
                return result.stdout + result.stderr

            self.assertIn("Runtime library digest mismatch", consumer_result())
            external = work / "unattested-runtime"
            external.write_bytes(b"not a native library")
            self.assertIn("Runtime evidence", consumer_result(str(external)))

    @unittest.skipUnless(os.environ.get("CODEX_AGENT_CSHARP_NUPKG"), "staged C# package not supplied")
    def test_installed_package_pins_root_and_rejects_unattested_override(self) -> None:
        package = Path(os.environ["CODEX_AGENT_CSHARP_NUPKG"]).resolve(strict=True)
        self.assertEqual("CodexAgent.0.8.0.nupkg", package.name)
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            expected_compatibility = work / "expected-compatibility.json"
            with zipfile.ZipFile(package) as archive:
                name = "META-INF/codex-agent/sdk-compatibility.json"
                self.assertEqual(1, archive.namelist().count(name))
                expected_compatibility.write_bytes(archive.read(name))
            feed = work / "feed"
            feed.mkdir()
            shutil.copyfile(package, feed / package.name)
            config = work / "NuGet.Config"
            root = ET.Element("configuration")
            sources = ET.SubElement(root, "packageSources")
            ET.SubElement(sources, "clear")
            ET.SubElement(sources, "add", key="local", value=str(feed))
            config.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
            consumer = work / "consumer"
            shutil.copytree(CONSUMER, consumer, ignore=shutil.ignore_patterns("bin", "obj"))
            environment = {
                **os.environ,
                "DOTNET_CLI_HOME": str(work / "dotnet-home"),
                "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "NUGET_PACKAGES": str(work / "packages"),
            }
            environment.pop("CODEX_AGENT_LIBRARY", None)
            (work / "dotnet-home").mkdir()

            def run(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(["dotnet", *args], cwd=work, env=environment,
                                      capture_output=True, text=True, check=False)

            project = str(consumer / "CodexAgent.Consumer.csproj")
            restored = run("restore", project, "--configfile", str(config), "--packages",
                           str(work / "packages"), "--force", "--no-cache", "-p:NuGetAudit=false")
            self.assertEqual(0, restored.returncode, restored.stdout + restored.stderr)
            compiled = run("build", project, "--configuration", "Release", "--no-restore")
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)

            installed = work / "packages/codexagent/0.8.0/lib/net8.0/CodexAgent.dll"
            self.assertTrue(installed.is_file(), "the consumer did not install the package DLL")
            tool_restored = run("restore", str(ROOT_INSPECTOR), "--configfile", str(config),
                                "--packages", str(work / "packages"), "--force", "--no-cache",
                                "-p:NuGetAudit=false")
            self.assertEqual(0, tool_restored.returncode, tool_restored.stdout + tool_restored.stderr)
            inspected = run("run", "--project", str(ROOT_INSPECTOR), "--configuration", "Release",
                            "--no-restore", "--", str(installed), str(PINNED_ROOT),
                            str(expected_compatibility))
            self.assertEqual(0, inspected.returncode, inspected.stdout + inspected.stderr)

            invalid_library = work / "unattested-runtime"
            invalid_library.write_bytes(b"must fail before native loading")
            rejected = run("run", "--project", project, "--configuration", "Release",
                           "--no-build", "--no-restore", "--", str(invalid_library))
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("Runtime evidence", rejected.stdout + rejected.stderr)


if __name__ == "__main__":
    unittest.main()
