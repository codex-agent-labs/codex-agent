"""C# recipe controls with simulated NuGet/inspector processes, never product evidence."""

from contextlib import ExitStack
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import tooling_inspector
from products.inventory import load_canonical_json_bytes, sha256_bytes
from products.registry import PhaseInstanceId
from products.selection import _inventory_owners
from ci.tests import test_tooling_inspector

RECIPE = "codex-agent-bindings/csharp/tools/package_sdk.py"
spec = importlib.util.spec_from_file_location("csharp_recipe_test", ROOT / RECIPE)
recipe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe)


class CSharpPackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sources, self.sdks, self.binary = (self.root / name for name in ("sources", "sdks", "binary"))
        self.output = self.root / "output"
        for path in (self.sources / "csharp/native", self.sdks, self.binary):
            path.mkdir(parents=True)
        for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
            source = (ROOT / "gradle/release/keys" if name.endswith(".pub")
                      else ROOT / "codex-agent-bindings/csharp/native")
            data = (source / name).read_bytes()
            for directory in (self.sources / "csharp/native", self.sdks, self.binary):
                (directory / name).write_bytes(data)
        self.version = load_canonical_json_bytes((self.sdks / "sdk-compatibility.json").read_bytes())["sdkVersion"]
        project = self.sources / "csharp/src/CodexAgent"
        project.mkdir(parents=True)
        (project / "CodexAgent.csproj").write_text(
            f"<Project><PropertyGroup><VersionPrefix>{self.version}</VersionPrefix></PropertyGroup></Project>")
        for name in recipe.native.CSHARP_BINARY_FILES - {"sdk-compatibility.json", "sdk-runtime-root.pub"}:
            (self.binary / name).write_bytes(("original fixture " + name).encode())
        for target, host in recipe.native.HOSTS.items():
            path = self.sdks / target / host[4]
            path.parent.mkdir(parents=True)
            path.write_bytes(target.encode())
        fixture = test_tooling_inspector.ToolingInspectorTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.inspector_dir = self.root / "inspector"
        self.inspector_dir.mkdir()
        payload = {**fixture.payload, "inspector-manifest.json": fixture.manifest(fixture.payload)}
        for name, data in payload.items():
            (self.inspector_dir / name).write_bytes(data)
        self.inspector_sha = sha256_bytes(payload["inspector-manifest.json"])
        self.commands, self.packs = [], 0
        self.mutation = None

    def process(self, command, **options):
        command = list(map(str, command))
        self.commands.append(command)
        self.assertEqual("dotnet", command[0])
        if command[1] == "restore":
            self.assertEqual([], list(Path(command[command.index("--source") + 1]).iterdir()))
        elif command[1] == "pack":
            self.packs += 1
            self.assertIn("--no-build", command)
            self.assertIn("--no-restore", command)
            source = Path(options["cwd"])
            for name in recipe.native.CSHARP_BINARY_FILES - {"sdk-compatibility.json", "sdk-runtime-root.pub"}:
                self.assertEqual((self.binary / name).read_bytes(),
                                 (source / "src/CodexAgent/bin/Release/net8.0" / name).read_bytes())
            archive = Path(command[command.index("--output") + 1]) / f"CodexAgent.{self.version}.nupkg"
            core = f"package/services/metadata/core-properties/{self.packs}.psmdcp"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr(core, b"fixed fixture metadata")
                z.writestr("_rels/.rels", '<Relationships><Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="/' + core + f'" Id="random{self.packs}" /></Relationships>')
                z.writestr("CodexAgent.nuspec", f"<package><metadata><id>CodexAgent</id><version>{self.version}</version></metadata></package>")
                z.writestr("lib/net8.0/CodexAgent.dll", (self.binary / "CodexAgent.dll").read_bytes())
                for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
                    data = (self.sdks / name).read_bytes()
                    if self.mutation == "compatibility" and name == "sdk-compatibility.json":
                        data += b" "
                    z.writestr("META-INF/codex-agent/" + name, data)
                for target, rid in recipe.native.PACKAGE_CLASSIFIERS.items():
                    original = self.sdks / target / recipe.native.HOSTS[target][4]
                    z.writestr(f"runtimes/{rid}/native/{original.name}", original.read_bytes())
                if self.mutation == "reproducibility":
                    z.writestr("README.txt", str(self.packs))
        else:
            self.assertEqual(str(self.inspector_dir / "VerifySdkRuntimeRoot.dll"), command[1])
            self.assertEqual(30, options["timeout"])
        return subprocess.CompletedProcess(command, 0, "", "")

    def invoke(self):
        with ExitStack() as stack:
            inspector = stack.enter_context(tooling_inspector.borrowed_inspector(self.inspector_dir, self.inspector_sha))
            stack.enter_context(patch.object(recipe.native, "verify_sdk_dotnet_toolchain"))
            stack.enter_context(patch.object(recipe.native, "require_prepared_native_assets"))
            stack.enter_context(patch.object(recipe.native, "write_package_toolchains", side_effect=lambda output, _:
                (output / "csharp/codex-agent-csharp-package-toolchain.tsv").write_bytes(b"tool\tversion\ndotnet\tfixture\n")))
            stack.enter_context(patch.object(subprocess, "run", side_effect=self.process))
            recipe.package_all(self.sources, self.sdks, self.output, self.version,
                               csharp_binary=self.binary, dotnet_profile=self.root / "profile",
                               csharp_inspector=inspector)

    def test_only_csharp_package_owns_recipe(self):
        self.assertEqual(frozenset({PhaseInstanceId("sdk", "csharp", "package", "desktop")}),
                         _inventory_owners(RECIPE))
        self.assertEqual(frozenset(), _inventory_owners("ci/sdk_native_phase.py"))

    def test_two_pass_pack_uses_original_binary_and_signed_inspector_without_compiling(self):
        originals = recipe.native.package_inventory(self.sources) + recipe.native.package_inventory(self.binary)
        self.invoke()
        self.assertEqual(2, self.packs)
        self.assertEqual(["restore", "pack", str(self.inspector_dir / "VerifySdkRuntimeRoot.dll")] * 2,
                         [command[1] for command in self.commands])
        self.assertEqual(originals, recipe.native.package_inventory(self.sources) + recipe.native.package_inventory(self.binary))

    def test_compatibility_or_nondeterministic_output_invalidates_package(self):
        for mutation in ("compatibility", "reproducibility"):
            with self.subTest(mutation=mutation):
                self.mutation = mutation
                with self.assertRaisesRegex(ValueError, "trust resource differs|not reproducible"):
                    self.invoke()
                self.assertFalse(self.output.exists())

    def test_inspector_is_mandatory_before_any_command(self):
        with self.assertRaisesRegex(ValueError, "live private inspector"):
            recipe.package_all(self.sources, self.sdks, self.output, self.version,
                               csharp_binary=self.binary, dotnet_profile=self.root / "profile")
        self.assertEqual([], self.commands)


if __name__ == "__main__":
    unittest.main()
