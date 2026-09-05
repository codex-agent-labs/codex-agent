"""S808 whole-chain native SDK package production from verified Runtime variants."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from unittest.mock import patch


_REPOSITORY = Path(__file__).resolve().parents[2]
_CI_ROOT = _REPOSITORY / "ci"
if str(_CI_ROOT) not in sys.path:
    sys.path.insert(0, str(_CI_ROOT))

from native_wrappers import (  # noqa: E402
    FORBIDDEN_C_ABI_PROOFS,
    HOSTS,
    LANGUAGES,
    PACKAGE_CLASSIFIERS,
    files,
    host_classifier,
    package_inventory,
    package_once,
    safe_extract_tar,
    safe_extract_zip,
)
from ci.products.c_abi import (
    C_ABI_PACKAGE_MANIFEST,
    TARGET_SPECS,
    portable_verify_c_abi_package_evidence,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    sha256_bytes,
)


_LANGUAGE_IGNORES = {
    "python": ("build", "dist", "__pycache__", "*.egg-info"),
    "csharp": ("artifacts", "bin", "obj"),
    "rust": ("target", "__pycache__"),
    "cpp": ("build*", "__pycache__"),
    "dart": ("build", ".dart_tool", ".pub", "doc", "__pycache__"),
}


def _tool_selection() -> tuple[tuple[str, ...], dict[str, str]]:
    try:
        python_build = importlib.util.find_spec("build.__main__") is not None
    except (ImportError, ModuleNotFoundError):
        python_build = False
    available = {
        "python": python_build,
        "csharp": shutil.which("dotnet") is not None,
        "rust": shutil.which("cargo") is not None,
        "cpp": shutil.which("cmake") is not None and shutil.which("c++") is not None,
        "dart": False,
    }
    reasons = {
        "python": "current Python has no executable build.__main__ package",
        "csharp": "dotnet is unavailable",
        "rust": "cargo is unavailable",
        "cpp": "cmake or c++ is unavailable",
        "dart": "package_once has no offline Dart pub resolution option",
    }
    return (
        tuple(language for language in LANGUAGES if available[language]),
        {language: reasons[language] for language in LANGUAGES if not available[language]},
    )


def _stage_sdks(
    root: Path,
    variants: dict[str, Any],
    compatibility: Path,
    context: dict[str, Any],
) -> tuple[Path, str]:
    raw_sdks = variants["raw_sdks"]
    if type(raw_sdks) is not dict or set(raw_sdks) != set(HOSTS):
        raise ValueError("whole-chain Runtime variants must contain exactly five raw C SDKs")
    compatibility_bytes = Path(compatibility).read_bytes()
    compatibility_value = load_canonical_json_bytes(compatibility_bytes)
    sdk_version = compatibility_value["sdkVersion"]
    staged = root / "native-wrapper-sdks"
    if staged.exists() or staged.is_symlink():
        raise ValueError(f"whole-chain native SDK staging already exists: {staged}")
    staged.mkdir(parents=True)

    target_records = []
    library_versions = set()
    specs_by_classifier = {
        spec.classifier.removeprefix("c-abi-"): (target, spec)
        for target, spec in TARGET_SPECS.items()
    }
    for classifier in sorted(HOSTS):
        record = raw_sdks[classifier]
        required = {
            "archive", "evidence", "verified_sdk", "evidence_target", "reviewed_header",
            "export_policy", "license", "notice", "consumer_sources",
        }
        if type(record) is not dict or set(record) != required:
            raise ValueError(f"whole-chain raw C SDK schema mismatch: {classifier}")
        evidence_path = Path(record["evidence"])
        raw_evidence = load_json_bytes(evidence_path.read_bytes())
        library_version = raw_evidence["libraryVersion"]
        library_versions.add(library_version)
        evidence_target, spec = specs_by_classifier[classifier]
        if record["evidence_target"] != evidence_target:
            raise ValueError(f"whole-chain raw C SDK target mismatch: {classifier}")
        target_root = staged / classifier
        report = portable_verify_c_abi_package_evidence(
            evidence_target,
            library_version,
            raw_evidence["producerCommit"],
            raw_evidence["producerTree"],
            Path(record["archive"]),
            evidence_path,
            Path(record["reviewed_header"]),
            Path(record["license"]),
            Path(record["notice"]),
            Path(record["export_policy"]),
            [Path(path) for path in record["consumer_sources"]],
            target_root,
        )
        if package_inventory(target_root) != package_inventory(Path(record["verified_sdk"])):
            raise ValueError(f"whole-chain portable C SDK verification changed: {classifier}")
        manifest = target_root / C_ABI_PACKAGE_MANIFEST
        target_records.append({
            "target": evidence_target,
            "classifier": classifier,
            "archiveSha256": report["archiveSha256"],
            "evidenceSha256": sha256_bytes(evidence_path.read_bytes()).removeprefix("sha256:"),
            "libraryPath": spec.library_path,
            "librarySha256": report["librarySha256"],
            "manifestSha256": sha256_bytes(manifest.read_bytes()).removeprefix("sha256:"),
            "producerCommit": raw_evidence["producerCommit"],
            "producerTree": raw_evidence["producerTree"],
        })
    if len(library_versions) != 1:
        raise ValueError("whole-chain raw C SDK library versions differ")

    (staged / "sdk-compatibility.json").write_bytes(compatibility_bytes)
    producer = context["producer"]
    index = {
        "schemaVersion": 2,
        "libraryVersion": library_versions.pop(),
        "runtimeProductVersion": compatibility_value["runtime"]["defaultRuntimeVersion"],
        "sdkVersion": sdk_version,
        "sdkCompatibilitySha256": sha256_bytes(compatibility_bytes).removeprefix("sha256:"),
        "producerCommit": producer["commit"],
        "producerTree": producer["tree"],
        "targets": sorted(target_records, key=lambda value: value["target"]),
    }
    (staged / "codex-agent-native-wrapper-sdks.json").write_bytes(canonical_json_bytes(index))
    return staged, sdk_version


def _materialize_sources(root: Path, sdks: Path, languages: tuple[str, ...]) -> Path:
    sources = root / "native-wrapper-sources"
    if sources.exists() or sources.is_symlink():
        raise ValueError(f"whole-chain native wrapper sources already exist: {sources}")
    sources.mkdir(parents=True)
    for language in languages:
        shutil.copytree(
            _REPOSITORY / "codex-agent-bindings" / language,
            sources / language,
            ignore=shutil.ignore_patterns(*_LANGUAGE_IGNORES[language]),
        )
    if "csharp" in languages:
        (sources / "csharp/NuGet.Config").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            "<configuration><packageSources><clear /></packageSources></configuration>\n",
            encoding="utf-8",
        )

    native_roots = {
        "python": sources / "python/src/codex_agent/native",
        "csharp": sources / "csharp/native",
        "rust": sources / "rust/native",
        "cpp": sources / "cpp/native",
        "dart": sources / "dart/lib/src/native",
    }
    for language in languages:
        native = native_roots[language]
        if native.exists():
            shutil.rmtree(native)
        native.mkdir(parents=True)
        if language in {"csharp", "dart"}:
            original = _REPOSITORY / "codex-agent-bindings" / language / native.relative_to(
                sources / language,
            ) / "README.md"
            shutil.copy2(original, native / "README.md")

    compatibility = sdks / "sdk-compatibility.json"
    for classifier in HOSTS:
        sdk = sdks / classifier
        library = sdk / HOSTS[classifier][4]
        destinations = {
            "python": native_roots["python"] / classifier / library.name,
            "csharp": native_roots["csharp"] / PACKAGE_CLASSIFIERS[classifier] / library.name,
            "rust": native_roots["rust"] / PACKAGE_CLASSIFIERS[classifier] / library.name,
            "dart": native_roots["dart"] / classifier / library.name,
        }
        for language, destination in destinations.items():
            if language in languages:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(library, destination)
        if "cpp" in languages:
            cpp = native_roots["cpp"] / classifier
            for source in files(sdk):
                if source.name in FORBIDDEN_C_ABI_PROOFS:
                    continue
                destination = cpp / source.relative_to(sdk)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            cpp_compatibility = cpp / "share/CodexAgent/native/sdk-compatibility.json"
            cpp_compatibility.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(compatibility, cpp_compatibility)
    for language, relative in {
        "python": "sdk-compatibility.json",
        "csharp": "sdk-compatibility.json",
        "rust": "sdk-compatibility.json",
        "dart": "sdk-compatibility.json",
    }.items():
        if language in languages:
            shutil.copy2(compatibility, native_roots[language] / relative)
    return sources


def _content_inventory(packages: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-package-inventory-") as temporary:
        work = Path(temporary)
        archives = [
            path for path in files(packages)
            if path.name.endswith((".crate", ".nupkg", ".tar.gz", ".whl", ".zip"))
        ]
        for index, archive in enumerate(archives):
            extracted = work / str(index)
            if archive.name.endswith((".crate", ".tar.gz")):
                safe_extract_tar(archive, extracted)
            else:
                safe_extract_zip(archive, extracted)
            archive_name = archive.relative_to(packages).as_posix()
            for member in files(extracted):
                name = f"{archive_name}!/{member.relative_to(extracted).as_posix()}"
                inventory[name] = {
                    "bytes": member.stat().st_size,
                    "sha256": sha256_bytes(member.read_bytes()),
                }
    if any(Path(name).name in FORBIDDEN_C_ABI_PROOFS for name in inventory):
        raise ValueError("whole-chain native SDK package contains a forbidden raw C ABI proof")
    return dict(sorted(inventory.items()))


def build_sdk_packages(
    root: Path,
    variants: dict[str, Any],
    compatibility: Path,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build and verify every locally available genuine native-wrapper package family."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    languages, missing_tools = _tool_selection()
    if not languages:
        raise ValueError("no native SDK package toolchain is installed")
    sdks, sdk_version = _stage_sdks(root, variants, Path(compatibility), context)
    sources = _materialize_sources(root, sdks, languages)
    packages = root / "native-wrapper-packages"
    with patch.dict(os.environ, {
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "1",
        "DOTNET_NOLOGO": "1",
    }):
        package_once(sources, sdks, packages, sdk_version, languages)
    package_files = {
        path.relative_to(packages).as_posix(): path
        for path in files(packages)
    }
    return {
        "packages": packages,
        "package_files": dict(sorted(package_files.items())),
        "package_inventory": {
            name: {"bytes": path.stat().st_size, "sha256": sha256_bytes(path.read_bytes())}
            for name, path in sorted(package_files.items())
        },
        "content_inventory": _content_inventory(packages),
        "verified_languages": languages,
        "missing_tools": missing_tools,
        "sdk_version": sdk_version,
        "staged_sdks": sdks,
        "verification": (
            "portable C ABI package evidence",
            "embedded package version",
            "exact SDK compatibility",
            "exact native asset inventory",
        ),
        "evidence_scope": (
            "synthetic-input package/content integration only; not hosted compiler, "
            "reference, installed-consumer, or executed-behavior acceptance"
        ),
    }


def verify_cpp_consumer(package_result: dict[str, Any]) -> dict[str, Any]:
    """Compile and link the installed local-host C++ loader without executing Runtime code."""
    classifier = host_classifier()
    sdk_version = package_result["sdk_version"]
    archive_name = f"cpp/codex-agent-cpp-{sdk_version}-{classifier}.zip"
    archive = Path(package_result["package_files"][archive_name])
    work = Path(package_result["packages"]).parent / "cpp-consumer-verification"
    if work.exists() or work.is_symlink():
        raise ValueError(f"whole-chain C++ consumer verification already exists: {work}")
    extracted = work / "installed"
    safe_extract_zip(archive, extracted)
    roots = list(extracted.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise ValueError("whole-chain C++ package must contain one installed prefix")
    prefix = roots[0]
    source = work / "consumer"
    source.mkdir(parents=True)
    (source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.24)\n"
        "project(CodexAgentChainConsumer LANGUAGES CXX)\n"
        "find_package(CodexAgent CONFIG REQUIRED)\n"
        "add_executable(codex_agent_chain_probe main.cpp)\n"
        "target_link_libraries(codex_agent_chain_probe PRIVATE CodexAgent::CodexAgent)\n",
        encoding="utf-8",
    )
    (source / "main.cpp").write_text(
        "#include <codex_agent/native_dispatch.hpp>\n"
        "int main(int argc, char** argv) {\n"
        "    if (argc > 1000) codex_agent::CodexNativeLibrary::configure(argv[0]);\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    def invoke(*command: str | Path, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(value) for value in command],
            cwd=work,
            check=check,
            capture_output=True,
            text=True,
        )

    build = work / "build"
    configure_command = (
        "cmake", "-S", source, "-B", build,
        f"-DCMAKE_PREFIX_PATH={prefix}", "-DCMAKE_BUILD_TYPE=Release",
    )
    configured = invoke(*configure_command)
    build_command = (
        "cmake", "--build", build, "--config", "Release", "--target", "codex_agent_chain_probe",
    )
    compiled = invoke(*build_command)
    executable = build / ("Release/codex_agent_chain_probe.exe" if os.name == "nt"
                          else "codex_agent_chain_probe")
    if not executable.is_file() or executable.is_symlink():
        raise ValueError("whole-chain C++ consumer executable was not linked")
    compiler_paths = [
        line.split("=", 1)[1]
        for line in (build / "CMakeCache.txt").read_text(encoding="utf-8").splitlines()
        if line.startswith("CMAKE_CXX_COMPILER:FILEPATH=")
    ]
    if len(compiler_paths) != 1:
        raise ValueError("whole-chain C++ consumer compiler identity is missing")
    compiler_identity = invoke(compiler_paths[0], "--version")

    loader = prefix / "share/CodexAgent/loader/native_loader.cpp"
    original_loader = loader.read_bytes()
    tamper_build = work / "tamper-build"
    try:
        loader.write_bytes(original_loader + b"\n// tampered\n")
        rejected = invoke(
            "cmake", "-S", source, "-B", tamper_build,
            f"-DCMAKE_PREFIX_PATH={prefix}", "-DCMAKE_BUILD_TYPE=Release",
            check=False,
        )
    finally:
        loader.write_bytes(original_loader)
    rejection_output = rejected.stdout + rejected.stderr
    if (
        rejected.returncode == 0
        or "hash mismatch" not in rejection_output
        or "native_loader.cpp" not in rejection_output
    ):
        raise ValueError("whole-chain C++ consumer accepted a tampered installed loader source")
    if loader.read_bytes() != original_loader:
        raise ValueError("whole-chain C++ consumer did not restore the installed loader fixture")

    return {
        "classifier": classifier,
        "archive": archive,
        "package_root": prefix,
        "target": "CodexAgent::Loader",
        "executable": executable,
        "executable_sha256": sha256_bytes(executable.read_bytes()),
        "loader_source_sha256": sha256_bytes(original_loader),
        "compiler": compiler_paths[0],
        "compiler_identity_sha256": sha256_bytes(
            (compiler_identity.stdout + compiler_identity.stderr).encode("utf-8"),
        ),
        "configured": configured.returncode == 0,
        "compiled": compiled.returncode == 0,
        "linked": True,
        "executed": False,
        "tampered_loader_rejected": True,
        "configure_command": tuple(str(value) for value in configure_command),
        "build_command": tuple(str(value) for value in build_command),
        "tamper_return_code": rejected.returncode,
    }
