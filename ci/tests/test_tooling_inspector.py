"""Tooling producer controls with mocked Git/host/compiler; no real .NET build."""

from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import tooling_inspector as inspector
from products.inventory import canonical_json_bytes, sha256_bytes
from products.sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
import product_reuse


class ToolingInspectorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inspector-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "repository"
        self.root.mkdir()
        repository = Path(__file__).resolve().parents[2]
        self.sources = {path: (repository / path).read_bytes() for path in (*inspector.SOURCES, inspector.PROFILE)}
        for path, raw in self.sources.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.profile = load_sdk_dotnet_profile_bytes(self.sources[inspector.PROFILE])
        self.source_rows = [{"path": path, "sha256": sha256_bytes(self.sources[path])} for path in inspector.SOURCES]
        framework, project = ".NETCoreApp,Version=v8.0", "VerifySdkRuntimeRoot/1.0.0"
        self.payload = {
            "VerifySdkRuntimeRoot.dll": b"fixture bytes; not a compiled or verified PE assembly\n",
            "VerifySdkRuntimeRoot.deps.json": json.dumps({
                "runtimeTarget": {"name": framework, "signature": ""}, "compilationOptions": {},
                "targets": {framework: {project: {"runtime": {"VerifySdkRuntimeRoot.dll": {}}}}},
                "libraries": {project: {"type": "project", "serviceable": False, "sha512": ""}}}, indent=2).encode(),
            "VerifySdkRuntimeRoot.runtimeconfig.json": json.dumps({"runtimeOptions": {
                "tfm": "net8.0", "rollForward": "Major",
                "framework": {"name": "Microsoft.NETCore.App", "version": "8.0.0"},
                "configProperties": {"System.Reflection.Metadata.MetadataUpdater.IsSupported": False,
                    "System.Runtime.Serialization.EnableUnsafeBinaryFormatterSerialization": False}}}, indent=2).encode(),
        }
        self.commands = []
        self.failure = None

    def process(self, command, *, cwd, env, stdout, stderr, check, timeout):
        self.commands.append(command)
        self.assertEqual(["dotnet", command[1], "VerifySdkRuntimeRoot.csproj"], command[:3])
        self.assertTrue(check)
        self.assertEqual(120, timeout)
        self.assertEqual(subprocess.STDOUT, stderr)
        self.assertEqual(self.sources[inspector._PROJECT + "/Program.cs"], (cwd / "Program.cs").read_bytes())
        self.assertEqual(self.sources[inspector._PROJECT + "/VerifySdkRuntimeRoot.csproj"],
                         (cwd / "VerifySdkRuntimeRoot.csproj").read_bytes())
        self.assertEqual({"sdk": {"version": "8.0.419", "rollForward": "disable", "allowPrerelease": False}},
                         json.loads((cwd / "global.json").read_bytes()))
        self.assertIn("/p:UseAppHost=false", command)
        self.assertIn("/p:ContinuousIntegrationBuild=true", command)
        self.assertIn(f"/p:PathMap={cwd}=/_/tools/VerifySdkRuntimeRoot", command)
        self.assertIn("/p:ImportDirectoryBuildProps=false", command)
        self.assertIn("/p:ImportDirectoryBuildTargets=false", command)
        self.assertEqual(str(cwd.parent / "packages"), env["NUGET_PACKAGES"])
        if command[1] == "restore":
            self.assertEqual([], list(Path(command[command.index("--source") + 1]).iterdir()))
            self.assertIn("-p:NuGetAudit=false", command)
        else:
            self.assertEqual(["--configuration", "Release", "--no-restore"], command[3:6])
            if self.failure == "compile":
                raise subprocess.CalledProcessError(1, command)
            output = cwd / "bin/Release/net8.0"
            output.mkdir(parents=True)
            for name, raw in self.payload.items():
                if self.failure != "missing" or not name.endswith(".dll"):
                    (output / name).write_bytes(raw)
            (output / "VerifySdkRuntimeRoot.pdb").write_bytes(b"not part of the published tool")
            if self.failure == "extra": (output / "unexpected.dll").write_bytes(b"unselected dependency")
            if self.failure == "source": (self.root / inspector.SOURCES[1]).write_bytes(b"mutated source")
            if self.failure == "symbolic":
                dll = output / "VerifySdkRuntimeRoot.dll"
                dll.unlink()
                dll.symlink_to(self.root / inspector.SOURCES[1])
        return subprocess.CompletedProcess(command, 0)

    def guards(self):
        stack = ExitStack()
        stack.enter_context(patch.dict(os.environ, {}, clear=True))
        stack.enter_context(patch.object(inspector, "run_git", side_effect=lambda _root, *args:
                                        ("b" if args[-1] == "HEAD^{tree}" else "a") * 40 + "\n"))
        self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
        stack.enter_context(patch.object(inspector, "git_regular_blob_bytes", side_effect=
                                     lambda _root, _commit, path, **_: self.sources[path]))
        self.toolchain = stack.enter_context(patch.object(inspector, "verify_sdk_dotnet_toolchain", return_value=self.profile))
        stack.enter_context(patch.object(inspector.subprocess, "run", side_effect=self.process))
        return stack

    def manifest(self, payload):
        return canonical_json_bytes({"schemaVersion": 1, "kind": "csharp-runtime-inspector",
            "toolchainProfileSha256": self.profile.digest, "sourceFiles": self.source_rows,
            "files": [{"relativePath": name, "bytes": len(payload[name]), "sha256": sha256_bytes(payload[name])}
                      for name in inspector.FILES]})

    def test_build_stages_only_raw_tooling_with_stable_manifest_and_one_compile(self):
        snapshots = []
        for name in ("first", "second"):
            destination = self.root / "build" / name
            with self.guards():
                manifest = inspector.build(self.root, destination)
                self.toolchain.assert_called_once_with(self.root / inspector.PROFILE)
                self.assertGreaterEqual(self.checkout.call_count, 5)
            files = {p.name: p.read_bytes() for p in destination.iterdir()}
            self.assertEqual({*inspector.FILES, "inspector-manifest.json"}, set(files))
            self.assertEqual(self.payload, {key: files[key] for key in inspector.FILES})
            self.assertEqual(manifest, inspector.verify(files, self.source_rows, self.profile.digest))
            snapshots.append(files)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(["restore", "build", "restore", "build"], [cmd[1] for cmd in self.commands])
        self.assertEqual(self.sources, {p: (self.root / p).read_bytes() for p in self.sources})

    def test_build_failure_or_source_mutation_never_publishes(self):
        for failure in ("compile", "extra", "missing", "source", "symbolic"):
            with self.subTest(failure=failure):
                self.failure = failure
                destination = self.root / "build" / failure
                with self.guards(), self.assertRaises((ValueError, FileNotFoundError, subprocess.CalledProcessError)):
                    inspector.build(self.root, destination)
                self.assertFalse(destination.exists())
                for path, raw in self.sources.items(): (self.root / path).write_bytes(raw)

    def test_source_host_secret_and_destination_guards_precede_compiler(self):
        for kind in ("host", "tracked", "executing", "secret", "existing", "relative", "alias"):
            with self.subTest(kind=kind):
                self.commands.clear()
                destination = self.root / "build" / kind
                with self.guards():
                    if kind == "host": self.toolchain.side_effect = ValueError("wrong actual host/SDK")
                    if kind == "tracked": self.checkout.side_effect = ValueError("dirty checkout")
                    if kind == "executing": self.sources["ci/tooling_inspector.py"] = b"other executable source"
                    if kind == "secret": os.environ["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
                    if kind == "existing": destination.mkdir(parents=True)
                    if kind == "relative": destination = Path("relative")
                    if kind == "alias":
                        destination.parent.mkdir(exist_ok=True)
                        destination.symlink_to(self.root, target_is_directory=True)
                    with self.assertRaises(ValueError): inspector.build(self.root, destination)
                self.assertEqual([], self.commands)
                self.sources["ci/tooling_inspector.py"] = Path(inspector.__file__).read_bytes()

    def test_verify_rejects_file_manifest_source_and_dependency_mutations(self):
        for kind in ("missing", "extra", "empty", "oversize", "manifest-size", "noncanonical", "bytes",
                     "source", "profile", "dependency", "runtime", "schema-type", "runtime-type"):
            with self.subTest(kind=kind):
                files = dict(self.payload)
                files["inspector-manifest.json"] = self.manifest(files)
                source_rows, profile = self.source_rows, self.profile.digest
                if kind == "missing": del files[inspector.FILES[0]]
                if kind == "extra": files["other"] = b"unexpected"
                if kind == "empty": files[inspector.FILES[1]] = b""
                if kind == "oversize": files[inspector.FILES[1]] = b"x" * (1024 * 1024 + 1)
                if kind == "manifest-size": files["inspector-manifest.json"] = b"x" * (16 * 1024 + 1)
                if kind == "noncanonical": files["inspector-manifest.json"] += b" "
                if kind == "bytes": files[inspector.FILES[1]] += b"mutation"
                if kind == "source": source_rows = list(reversed(source_rows))
                if kind == "profile": profile = "sha256:" + "f" * 64
                if kind == "schema-type":
                    value = json.loads(files["inspector-manifest.json"]);value["schemaVersion"] = True
                    files["inspector-manifest.json"] = canonical_json_bytes(value)
                if kind in {"dependency", "runtime", "runtime-type"}:
                    key = inspector.FILES[0] if kind == "dependency" else inspector.FILES[2]
                    value = json.loads(files[key])
                    if kind == "dependency": value["libraries"]["unexpected/1.0.0"] = {}
                    elif kind == "runtime": value["runtimeOptions"]["framework"]["version"] = "9.0.0"
                    else: value["runtimeOptions"]["configProperties"]["System.Reflection.Metadata.MetadataUpdater.IsSupported"] = 0
                    files[key] = json.dumps(value).encode()
                    files["inspector-manifest.json"] = self.manifest(files)
                with self.assertRaises(ValueError): inspector.verify(files, source_rows, profile)


if __name__ == "__main__":
    unittest.main()
