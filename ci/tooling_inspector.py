"""Build the fixed C# resource inspector as release tooling, never SDK output."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    load_json_bytes, read_regular_file_bytes, require_exact_keys, require_sha256,
    run_git, sha256_bytes,
)
from products.sdk_dotnet_toolchain import verify_sdk_dotnet_toolchain
from products.signing_isolation import require_no_signing_secret


_PROJECT = "codex-agent-bindings/csharp/tools/VerifySdkRuntimeRoot"
SOURCES = tuple(sorted(("ci/tooling_inspector.py", _PROJECT + "/Program.cs",
                        _PROJECT + "/VerifySdkRuntimeRoot.csproj")))
PROFILE = "gradle/release/toolchains/sdk/csharp.json"
FILES = ("VerifySdkRuntimeRoot.deps.json", "VerifySdkRuntimeRoot.dll",
         "VerifySdkRuntimeRoot.runtimeconfig.json")
_MANIFEST = "inspector-manifest.json"
_LIMITS = {FILES[0]: 64 * 1024, FILES[1]: 1024 * 1024, FILES[2]: 64 * 1024,
           _MANIFEST: 16 * 1024}


def verify(files: dict[str, bytes], source_files: list[dict], profile_sha256: str) -> dict:
    """Check bounded signed-file contents against caller-owned source pins; grant no authority."""
    require_exact_keys(files, {*FILES, _MANIFEST}, "C# inspector files")
    for name, raw in files.items():
        if type(raw) is not bytes or not 0 < len(raw) <= _LIMITS[name]:
            raise ValueError("C# inspector file has invalid size: " + name)
    require_sha256(profile_sha256, "C# inspector expected profile")
    if type(source_files) is not list or len(source_files) != len(SOURCES):
        raise ValueError("C# inspector requires its exact three source pins")
    for row, path in zip(source_files, SOURCES):
        require_exact_keys(row, {"path", "sha256"}, "C# inspector source")
        if row["path"] != path:
            raise ValueError("C# inspector source paths differ")
        require_sha256(row["sha256"], "C# inspector source digest")
    expected = {"schemaVersion": 1, "kind": "csharp-runtime-inspector",
        "toolchainProfileSha256": profile_sha256, "sourceFiles": source_files,
        "files": [{"relativePath": name, "bytes": len(files[name]), "sha256": sha256_bytes(files[name])}
                  for name in FILES]}
    manifest = load_canonical_json_bytes(files[_MANIFEST])
    if files[_MANIFEST] != canonical_json_bytes(expected):
        raise ValueError("C# inspector manifest differs from exact source/profile/output pins")
    framework = ".NETCoreApp,Version=v8.0"
    project = "VerifySdkRuntimeRoot/1.0.0"
    deps = {"runtimeTarget": {"name": framework, "signature": ""}, "compilationOptions": {},
        "targets": {framework: {project: {"runtime": {"VerifySdkRuntimeRoot.dll": {}}}}},
        "libraries": {project: {"type": "project", "serviceable": False, "sha512": ""}}}
    if canonical_json_bytes(load_json_bytes(files[FILES[0]])) != canonical_json_bytes(deps):
        raise ValueError("C# inspector dependencies differ from its sole net8 project")
    configuration = require_exact_keys(load_json_bytes(files[FILES[2]]), {"runtimeOptions"},
                                       "C# inspector runtime configuration")
    options = require_exact_keys(configuration["runtimeOptions"],
        {"tfm", "framework", "rollForward", "configProperties"}, "C# inspector runtime options")
    expected_options = {"tfm": "net8.0", "rollForward": "Major",
        "framework": {"name": "Microsoft.NETCore.App", "version": "8.0.0"},
        "configProperties": {
                "System.Reflection.Metadata.MetadataUpdater.IsSupported": False,
                "System.Runtime.Serialization.EnableUnsafeBinaryFormatterSerialization": False}}
    if canonical_json_bytes(options) != canonical_json_bytes(expected_options):
        raise ValueError("C# inspector runtime differs from its fixed net8 configuration")
    return manifest


def build(repository: Path, destination: Path) -> dict:
    """Compile the unchanged inspector once; publication/signing are caller-owned."""
    from product_reuse import _runtime_worker_checkout

    require_no_signing_secret(os.environ)
    root, destination = Path(repository), Path(destination)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("C# inspector repository must be normalized and absolute")
    if (not destination.is_absolute() or destination.resolve(strict=False) != destination
            or destination.exists() or destination.is_symlink() or destination == root
            or destination in root.parents):
        raise ValueError("C# inspector destination must be fresh, normalized and separate")
    producer = {"commit": run_git(root, "rev-parse", "HEAD").strip(),
                "tree": run_git(root, "rev-parse", "HEAD^{tree}").strip()}
    _runtime_worker_checkout(root, producer)
    sources = {path: git_regular_blob_bytes(root, producer["commit"], path, max_bytes=64 * 1024)
               for path in (*SOURCES, PROFILE)}
    if any(not raw for raw in sources.values()):
        raise ValueError("C# inspector source must be nonempty")
    if read_regular_file_bytes(Path(__file__), max_bytes=64 * 1024,
                               reject_symlink_parents=True) != sources["ci/tooling_inspector.py"]:
        raise ValueError("C# inspector executing module differs from the tracked source")

    def unchanged():
        require_no_signing_secret(os.environ)
        _runtime_worker_checkout(root, producer)
        if any(read_regular_file_bytes(root / path, max_bytes=64 * 1024,
                                       reject_symlink_parents=True) != raw for path, raw in sources.items()):
            raise ValueError("C# inspector tracked source changed")

    unchanged()
    profile = verify_sdk_dotnet_toolchain(root / PROFILE)
    if profile.digest != sha256_bytes(sources[PROFILE]):
        raise ValueError("C# inspector toolchain profile changed")
    source_files = [{"path": path, "sha256": sha256_bytes(sources[path])} for path in SOURCES]
    with tempfile.TemporaryDirectory(prefix="csharp-runtime-inspector-") as temporary:
        work = Path(temporary).resolve()
        project = work / "VerifySdkRuntimeRoot"
        project.mkdir()
        for name in ("Program.cs", "VerifySdkRuntimeRoot.csproj"):
            (project / name).write_bytes(sources[_PROJECT + "/" + name])
        (project / "global.json").write_bytes(canonical_json_bytes({"sdk": {
            "version": profile.dotnet_sdk, "rollForward": "disable", "allowPrerelease": False}}))
        feed = work / "empty-feed"
        feed.mkdir()
        environment = dict(os.environ, DOTNET_CLI_HOME=str(work / "dotnet-home"),
            NUGET_PACKAGES=str(work / "packages"), DOTNET_CLI_TELEMETRY_OPTOUT="1",
            DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1", DOTNET_NOLOGO="1")
        properties = ["/p:UseAppHost=false", "/p:ContinuousIntegrationBuild=true",
            f"/p:PathMap={project}=/_/tools/VerifySdkRuntimeRoot",
            "/p:ImportDirectoryBuildProps=false", "/p:ImportDirectoryBuildTargets=false"]
        try:
            subprocess.run(["dotnet", "restore", "VerifySdkRuntimeRoot.csproj", "--source", str(feed),
                            "-p:NuGetAudit=false", *properties], cwd=project, env=environment,
                           stdout=sys.stderr, stderr=subprocess.STDOUT, check=True, timeout=120)
            unchanged()
            subprocess.run(["dotnet", "build", "VerifySdkRuntimeRoot.csproj", "--configuration", "Release",
                            "--no-restore", *properties], cwd=project, env=environment,
                           stdout=sys.stderr, stderr=subprocess.STDOUT, check=True, timeout=120)
            output = project / "bin/Release/net8.0"
            if {path.name for path in output.iterdir()} - {*FILES, "VerifySdkRuntimeRoot.pdb"}:
                raise ValueError("C# inspector compiler emitted unexpected files")
            files = {name: read_regular_file_bytes(output / name, max_bytes=_LIMITS[name],
                                                   reject_symlink_parents=True) for name in FILES}
            manifest = {"schemaVersion": 1, "kind": "csharp-runtime-inspector",
                "toolchainProfileSha256": profile.digest, "sourceFiles": source_files,
                "files": [{"relativePath": name, "bytes": len(files[name]), "sha256": sha256_bytes(files[name])}
                          for name in FILES]}
            files[_MANIFEST] = canonical_json_bytes(manifest)
            verify(files, source_files, profile.digest)
        finally:
            unchanged()
    destination.mkdir(parents=True)
    try:
        for name, raw in files.items():
            with (destination / name).open("xb") as stream:
                stream.write(raw)
        unchanged()
    except BaseException:
        shutil.rmtree(destination)
        raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build",))
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    arguments = parser.parse_args(argv)
    print(canonical_json_bytes(build(arguments.repository, arguments.destination)).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
