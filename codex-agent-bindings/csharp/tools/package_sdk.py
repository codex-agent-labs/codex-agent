"""Package the original C# binary twice; inspect it with authenticated tooling."""

from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET

import native_wrappers as native
from tooling_inspector import require_inspector


def _verify_normalized(extracted, packages, sdks, version, inspector):
    """Reuse normalization's extracted tree rather than unpacking the NuGet again."""
    require_inspector(inspector)
    native.select_packages(packages, "linux-x64", version, ("csharp",))
    leaves = native.files(extracted)
    expected = (sdks / "sdk-compatibility.json").read_bytes()
    root = sdks / "sdk-runtime-root.pub"
    expected_root = native.read_regular_file_bytes(root, max_bytes=4096, reject_symlink_parents=True)
    native.public_key_fingerprint(expected_root)
    compatibility = native.validate_sdk_compatibility(native.load_canonical_json_bytes(expected))
    if compatibility["sdkVersion"] != version:
        raise ValueError("embedded SDK compatibility version mismatch")
    required = extracted / "META-INF/codex-agent/sdk-compatibility.json"
    required_root = required.with_name("sdk-runtime-root.pub")
    assembly = extracted / "lib/net8.0/CodexAgent.dll"
    for name, path, data in (("sdk-compatibility.json", required, expected),
                             ("sdk-runtime-root.pub", required_root, expected_root)):
        if [leaf for leaf in leaves if leaf.name == name] != [path] or path.read_bytes() != data:
            raise ValueError("C# package embedded trust resource differs: " + name)
    if [leaf for leaf in leaves if leaf.name.lower() == "codexagent.dll"] != [assembly]:
        raise ValueError("C# package must contain only the expected CodexAgent.dll")
    inspector.verify_resources(assembly, required_root, required)

    nuspec_path = native.require_one(extracted, "*.nuspec")
    if nuspec_path != extracted / "CodexAgent.nuspec":
        raise ValueError("C# package nuspec identity mismatch")
    nuspec = ET.parse(nuspec_path).getroot()
    namespaces = ("", *(f"{{http://schemas.microsoft.com/packaging/{schema}/nuspec.xsd}}"
                       for schema in ("2010/07", "2011/08", "2011/10", "2012/06", "2013/01", "2013/05")))
    namespace = next((prefix for prefix in namespaces if nuspec.tag == prefix + "package"), None)
    if namespace is None:
        raise ValueError("C# package nuspec namespace mismatch")
    metadata = [item for item in nuspec if item.tag == namespace + "metadata"]
    if (len(metadata) != 1
            or [item.text for item in metadata[0] if item.tag == namespace + "id"] != ["CodexAgent"]
            or [item.text for item in metadata[0] if item.tag == namespace + "version"] != [version]):
        raise ValueError("C# package NuGet coordinate differs")
    native.reject_nuget_build_hooks(extracted)
    native.reject_raw_c_abi_proofs(extracted, "C#")
    expected_native = {f"{rid}/native/{Path(native.HOSTS[target][4]).name}"
                       for target, rid in native.PACKAGE_CLASSIFIERS.items()}
    if {path.relative_to(extracted / "runtimes").as_posix()
            for path in native.files(extracted / "runtimes")} != expected_native:
        raise ValueError("C# package native target inventory mismatch")
    for target, rid in native.PACKAGE_CLASSIFIERS.items():
        original = sdks / target / native.HOSTS[target][4]
        if native.sha256(extracted / "runtimes" / rid / "native" / original.name) != native.sha256(original):
            raise ValueError("C# package native library differs: " + target)


def _package_once(sources, sdks, output, version, binary, profile, inspector):
    require_inspector(inspector)
    native.verify_sdk_dotnet_toolchain(profile)
    native.clean_output(output)
    native.require_prepared_native_assets(sources, sdks, version, ("csharp",))
    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-package-") as temporary:
        work = Path(temporary).resolve()
        isolated_sources = work / "sources"
        isolated_sources.mkdir()
        shutil.copytree(sources / "csharp", isolated_sources / "csharp")
        native.set_source_sdk_version(isolated_sources, version, ("csharp",))
        source = isolated_sources / "csharp"
        native.require_csharp_binary(binary, source / "native/sdk-compatibility.json",
                                    source / "native/sdk-runtime-root.pub")
        project = source / "src/CodexAgent"
        feed = work / "empty-nuget-feed"
        feed.mkdir()
        native.run("dotnet", "restore", project / "CodexAgent.csproj", "--source", feed,
                   "-p:NuGetAudit=false", cwd=source)
        compiled = project / "bin/Release/net8.0"
        compiled.mkdir(parents=True)
        for name in sorted(native.CSHARP_BINARY_FILES - {"sdk-compatibility.json", "sdk-runtime-root.pub"}):
            shutil.copy2(binary / name, compiled / name)
        package_root = output / "csharp"
        package_root.mkdir()
        native.run("dotnet", "pack", "src/CodexAgent/CodexAgent.csproj", "--configuration", "Release",
                   "--no-build", "--no-restore", "--output", package_root, "-p:NuGetAudit=false",
                   f"-p:Version={version}", f"-p:PathMap={source}=/_/csharp", cwd=source)
        native.normalize_nupkg(native.require_one(package_root, f"CodexAgent.{version}.nupkg"), work)
        native.write_package_toolchains(output, ("csharp",))
        _verify_normalized(work / "csharp-nupkg", output, sdks, version, inspector)


def package_all(sources, sdks, output, sdk_version, languages=("csharp",),
                csharp_binary=None, dotnet_profile=None, *, csharp_inspector=None):
    """Keep the original two-pass recipe and fail closed on differing output bytes."""
    if languages != ("csharp",) or csharp_binary is None or dotnet_profile is None:
        raise ValueError("C# package requires its exact language, original binary and .NET profile")
    require_inspector(csharp_inspector)
    native.invalidate_output(output)
    try:
        version = native.require_semver(sdk_version, "SDK version")
        _package_once(sources, sdks, output, version, csharp_binary, dotnet_profile, csharp_inspector)
        with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-reproducibility-") as temporary:
            second = Path(temporary) / "packages"
            _package_once(sources, sdks, second, version, csharp_binary, dotnet_profile, csharp_inspector)
            if native.package_inventory(output) != native.package_inventory(second):
                raise ValueError("C# release packages are not reproducible")
    except Exception:
        native.invalidate_output(output)
        raise
