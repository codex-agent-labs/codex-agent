#!/usr/bin/env python3
"""Build and execute the five thin native-wrapper release packages."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

if __package__:
    from .products.aggregate import validate_sdk_compatibility
    from .products.inventory import load_canonical_json_bytes, public_key_fingerprint, require_semver
else:
    from products.aggregate import validate_sdk_compatibility
    from products.inventory import load_canonical_json_bytes, public_key_fingerprint, require_semver


HOSTS = {
    "macos-arm64": ("Darwin", {"arm64", "aarch64"}, "macOS", "ARM64", "lib/libcodex_agent.dylib"),
    "macos-x64": ("Darwin", {"x86_64", "amd64"}, "macOS", "X64", "lib/libcodex_agent.dylib"),
    "linux-arm64": ("Linux", {"arm64", "aarch64"}, "Linux", "ARM64", "lib/libcodex_agent.so"),
    "linux-x64": ("Linux", {"x86_64", "amd64"}, "Linux", "X64", "lib/libcodex_agent.so"),
    "windows-x64": ("Windows", {"amd64", "x86_64"}, "Windows", "X64", "bin/codex_agent.dll"),
}
PYTHON_TAGS = {
    "macos-arm64": "macosx_11_0_arm64",
    "macos-x64": "macosx_10_13_x86_64",
    "linux-arm64": "linux_aarch64",
    "linux-x64": "linux_x86_64",
    "windows-x64": "win_amd64",
}
LANGUAGES = ("python", "csharp", "rust", "cpp", "dart")
DART_RELEASE_EXCLUDES = (
    ".dart_tool",
    ".gitignore",
    ".pubignore",
    "consumer",
    "parity",
    "pubspec.lock",
    "test",
    "tool",
)
PACKAGE_CLASSIFIERS = {
    "macos-arm64": "osx-arm64",
    "macos-x64": "osx-x64",
    "linux-arm64": "linux-arm64",
    "linux-x64": "linux-x64",
    "windows-x64": "win-x64",
}
FIXED_TIME = 315532800
FORBIDDEN_C_ABI_PROOFS = {
    "codex-agent-c-abi-manifest.json",
    "codex-agent-c-abi-evidence.json",
}


def run(*command: str | Path, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run([str(value) for value in command], cwd=cwd, env=env, check=True)


def run_expect_failure(*command: str | Path, cwd: Path, env: dict[str, str] | None = None) -> None:
    result = subprocess.run([str(value) for value in command], cwd=cwd, env=env, check=False)
    if result.returncode == 0:
        raise ValueError(f"expected installed consumer failure: {command[0]}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"missing or symbolic directory: {root}")
    result: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"symbolic package input: {path}")
        if path.is_file():
            result.append(path)
    return sorted(result, key=lambda path: path.relative_to(root).as_posix())


def clean_output(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"unsafe output: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)


def deterministic_zip(source: Path, output: Path, prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files(source):
            relative = PurePosixPath(prefix) / path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(str(relative), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if os.access(path, os.X_OK) else 0o644) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def deterministic_tar(source: Path, output: Path, prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in files(source):
                info = archive.gettarinfo(str(path), arcname=f"{prefix}/{path.relative_to(source).as_posix()}")
                info.mtime = FIXED_TIME
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                with path.open("rb") as source_file:
                    archive.addfile(info, source_file)


def stage_dart_release(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    for relative in DART_RELEASE_EXCLUDES:
        path = destination / relative
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    seen: set[Path] = set()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if "\\" in member.filename or ":" in member.filename:
                raise ValueError(f"unsafe zip member: {member.filename}")
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or ".." in path.parts or
                    stat.S_ISLNK(member.external_attr >> 16) or member.is_dir()):
                if member.is_dir() and not path.is_absolute() and ".." not in path.parts:
                    continue
                raise ValueError(f"unsafe zip member: {member.filename}")
            target = destination.joinpath(*path.parts).resolve()
            if not target.is_relative_to(destination) or target in seen:
                raise ValueError(f"unsafe or duplicate zip member: {member.filename}")
            seen.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(member))


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination.resolve()
    seen: set[Path] = set()
    with tarfile.open(archive, "r:*") as source:
        for member in source.getmembers():
            if "\\" in member.name or ":" in member.name:
                raise ValueError(f"unsafe tar member: {member.name}")
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                if member.isdir() and not path.is_absolute() and ".." not in path.parts:
                    continue
                raise ValueError(f"unsafe tar member: {member.name}")
            extracted = source.extractfile(member)
            if extracted is None:
                raise ValueError(f"missing tar payload: {member.name}")
            target = destination.joinpath(*path.parts).resolve()
            if not target.is_relative_to(destination) or target in seen:
                raise ValueError(f"unsafe or duplicate tar member: {member.name}")
            seen.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(extracted.read())


def require_one(root: Path, pattern: str) -> Path:
    matches = sorted(path for path in root.glob(pattern) if path.is_file() and not path.is_symlink())
    if len(matches) != 1:
        raise ValueError(f"expected one {pattern} below {root}, found {len(matches)}")
    return matches[0]


def require_matching_native(root: Path, pattern: str, sdk_library: Path, language: str) -> Path:
    native = require_one(root, pattern)
    if native.is_symlink() or sha256(native) != sha256(sdk_library):
        raise ValueError(f"{language} installed package native library does not match the verified SDK")
    return native.resolve()


def reject_raw_c_abi_proofs(root: Path, language: str) -> None:
    forbidden = [path for path in files(root) if path.name in FORBIDDEN_C_ABI_PROOFS]
    if forbidden:
        raise ValueError(f"{language} package contains forbidden raw C ABI proof: {forbidden[0].name}")


def reject_nuget_build_hooks(root: Path) -> None:
    for path in files(root):
        relative = path.relative_to(root)
        if (relative.parts[0].casefold() in {"build", "buildtransitive", "buildmultitargeting", "tools"}
                or path.suffix.casefold() in {".props", ".targets"}):
            raise ValueError(f"C# package contains an unexpected NuGet build hook: {relative}")


def require_no_nuget_build_hooks(package: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-agent-nuget-preflight-") as temporary:
        extracted = Path(temporary)
        safe_extract_zip(package, extracted)
        reject_nuget_build_hooks(extracted)


def require_matching_compatibility(
    root: Path,
    pattern: str,
    expected: Path,
    language: str,
) -> None:
    declaration = require_one(root, pattern)
    if declaration.read_bytes() != expected.read_bytes():
        raise ValueError(f"{language} installed SDK file does not match the verified SDK")


def require_installed_zip_tree(
    archive: Path,
    archive_subdir: str,
    installed_root: Path,
    language: str,
    *,
    excluded: frozenset[str] = frozenset(),
) -> None:
    with tempfile.TemporaryDirectory(prefix="codex-agent-installed-code-") as temporary:
        extracted = Path(temporary)
        safe_extract_zip(archive, extracted)
        source = extracted / archive_subdir

        def inventory(root: Path, ignored: frozenset[str]) -> dict[str, bytes]:
            return {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in files(root)
                if not ignored.intersection(path.relative_to(root).parts)
            }

        expected = inventory(source, excluded)
        actual = inventory(installed_root, excluded)
        if not expected or actual != expected:
            raise ValueError(f"{language} installed binding code differs from the selected package archive")


def normalize_python_sdist(package: Path, work: Path) -> None:
    extracted = work / "python-sdist"
    safe_extract_tar(package, extracted)
    roots = list(extracted.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise ValueError("Python sdist must contain one package root")
    deterministic_tar(roots[0], package, roots[0].name)


def package_python(source: Path, output: Path, work: Path) -> None:
    setup = (
        "from setuptools import Distribution, setup\n"
        "from wheel.bdist_wheel import bdist_wheel\n"
        "class BinaryDistribution(Distribution):\n"
        "    def has_ext_modules(self): return True\n"
        "class PlatformWheel(bdist_wheel):\n"
        "    def get_tag(self):\n"
        "        return self.python_tag, 'none', super().get_tag()[2]\n"
        "setup(distclass=BinaryDistribution, cmdclass={'bdist_wheel': PlatformWheel})\n"
    )
    all_source = work / "python-all"
    shutil.copytree(source, all_source)
    (all_source / "setup.py").write_text(setup, encoding="utf-8")
    env = os.environ | {"SOURCE_DATE_EPOCH": str(FIXED_TIME), "PYTHONHASHSEED": "0"}
    run(sys.executable, "-m", "build", "--sdist", "--no-isolation", "--outdir", output, cwd=all_source, env=env)
    sdist = require_one(output, "*.tar.gz")
    normalize_python_sdist(sdist, work)
    for classifier, tag in PYTHON_TAGS.items():
        wheel_source = work / f"python-{classifier}"
        shutil.copytree(all_source, wheel_source)
        native = wheel_source / "src/codex_agent/native"
        for child in native.iterdir():
            if child.name not in {classifier, "sdk-compatibility.json", "sdk-runtime-root.pub"}:
                shutil.rmtree(child)
        run(
            sys.executable, "setup.py", "bdist_wheel", "--python-tag", "py3",
            "--plat-name", tag, "--dist-dir", output, cwd=wheel_source, env=env,
        )
    wheels = sorted(output.glob("*.whl"))
    if len(wheels) != 5 or len(list(output.glob("*.tar.gz"))) != 1:
        raise ValueError("Python release requires five platform wheels and one sdist")
    for classifier, tag in PYTHON_TAGS.items():
        wheel = require_one(output, f"*-{tag}.whl")
        with zipfile.ZipFile(wheel) as archive:
            native = {
                relative.split("/", 1)[0]
                for name in archive.namelist()
                if "/native/" in name
                and "/" in (relative := name.split("/native/", 1)[1])
            }
        if native != {classifier}:
            raise ValueError(f"Python wheel native inventory mismatch: {classifier}")


def package_inventory(root: Path) -> list[tuple[str, str]]:
    return [(path.relative_to(root).as_posix(), sha256(path)) for path in files(root)]


def normalize_nupkg(package: Path, work: Path) -> None:
    extracted = work / "csharp-nupkg"
    safe_extract_zip(package, extracted)
    core = require_one(extracted / "package/services/metadata/core-properties", "*.psmdcp")
    digest = sha256(core)
    relative = core.relative_to(extracted).as_posix()
    canonical_relative = f"package/services/metadata/core-properties/{digest[:32]}.psmdcp"
    relationships = extracted / "_rels/.rels"
    contents = relationships.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/'
        r'metadata/core-properties" Target="/)' + re.escape(relative) + r'(" Id=")[^"]+(" />)'
    )
    contents, count = pattern.subn(
        lambda match: f"{match.group(1)}{canonical_relative}{match.group(2)}R{digest[:16].upper()}{match.group(3)}",
        contents,
    )
    if count != 1:
        raise ValueError("NuGet package must contain one core-properties relationship")
    relationships.write_text(contents, encoding="utf-8")
    core.rename(extracted / canonical_relative)
    deterministic_zip(extracted, package, "")


def write_package_toolchains(output: Path, languages: tuple[str, ...] = LANGUAGES) -> None:
    identities: dict[str, dict[str, str]] = {}
    if "python" in languages:
        identities["python"] = {
            "build": version(sys.executable, "-m", "build", "--version"),
            "python": version(sys.executable, "--version"),
            "setuptools-wheel": version(
                sys.executable, "-c",
                "import importlib.metadata as m;print(m.version('setuptools')+';'+m.version('wheel'))",
            ),
        }
    if "csharp" in languages:
        identities["csharp"] = {"dotnet": version("dotnet", "--version")}
    if "rust" in languages:
        identities["rust"] = {"cargo": version("cargo", "--version"), "rustc": version("rustc", "-vV")}
    if "dart" in languages:
        identities["dart"] = {"dart": version("dart", "--version")}
    if "cpp" in languages:
        identities["cpp"] = {
            "cmake": version("cmake", "--version").split(";", 1)[0],
        }
    for language in languages:
        tools = identities[language]
        (output / language / f"codex-agent-{language}-package-toolchain.tsv").write_text(
            "tool\tversion\n" + "".join(f"{name}\t{value}\n" for name, value in sorted(tools.items())),
            encoding="utf-8",
        )


def require_source_sdk_version(
    sources: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    expected = require_semver(sdk_version, "SDK version")

    def regular(relative: str) -> Path:
        path = sources / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing or symbolic SDK package manifest: {relative}")
        return path

    versions: dict[str, str | None] = {}
    if "python" in languages:
        versions["python"] = tomllib.loads(
            regular("python/pyproject.toml").read_text(encoding="utf-8"),
        )["project"]["version"]
    if "csharp" in languages:
        versions["csharp"] = ET.parse(
            regular("csharp/src/CodexAgent/CodexAgent.csproj"),
        ).findtext(".//VersionPrefix")
    if "rust" in languages:
        versions["rust"] = tomllib.loads(
            regular("rust/Cargo.toml").read_text(encoding="utf-8"),
        )["package"]["version"]
        versions["rust-lock"] = require_match(
            re.search(
                r'(?m)^name = "codex-agent"\nversion = "([^"]+)"$',
                regular("rust/Cargo.lock").read_text(encoding="utf-8"),
            ),
            "Rust lockfile does not declare the package version",
        ).group(1)
    if "cpp" in languages:
        versions["cpp"] = require_match(
            re.search(
                r"(?m)^project\(CodexAgent VERSION ([^ ]+) LANGUAGES (?:CXX|NONE)\)$",
                regular("cpp/CMakeLists.txt").read_text(encoding="utf-8"),
            ),
            "C++ package manifest does not declare the CodexAgent project version",
        ).group(1)
    if "dart" in languages:
        versions["dart"] = require_match(
            re.search(r"(?m)^version: (\S+)$", regular("dart/pubspec.yaml").read_text(encoding="utf-8")),
            "Dart package manifest does not declare one version",
        ).group(1)
    mismatches = {language: version for language, version in versions.items() if version != expected}
    if mismatches:
        raise ValueError(f"SDK package manifest versions do not match {expected}: {mismatches}")


def replace_once(path: Path, pattern: str, replacement: str, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or symbolic SDK package manifest: {path}")
    contents = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, contents, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{label} must contain exactly one package version")
    path.write_text(updated, encoding="utf-8")


def set_source_sdk_version(
    sources: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    version = require_semver(sdk_version, "SDK version")
    replacements = {
        "python": ("python/pyproject.toml", r'^(version = ")[^"]+("\s*)$', rf"\g<1>{version}\g<2>", "Python manifest"),
        "csharp": ("csharp/src/CodexAgent/CodexAgent.csproj", r"(<VersionPrefix>)[^<]+(</VersionPrefix>)", rf"\g<1>{version}\g<2>", "C# manifest"),
        "cpp": ("cpp/CMakeLists.txt", r"^(project\(CodexAgent VERSION )\S+( LANGUAGES (?:CXX|NONE)\))$", rf"\g<1>{version}\g<2>", "C++ manifest"),
        "dart": ("dart/pubspec.yaml", r"^version: \S+$", f"version: {version}", "Dart manifest"),
    }
    for language in languages:
        if language == "rust":
            replace_once(sources / "rust/Cargo.toml", r'^(version = ")[^"]+("\s*)$', rf"\g<1>{version}\g<2>", "Rust manifest")
            replace_once(sources / "rust/Cargo.lock", r'(?m)(^name = "codex-agent"\nversion = ")[^"]+("$)', rf"\g<1>{version}\g<2>", "Rust lockfile")
        else:
            relative, pattern, replacement, label = replacements[language]
            replace_once(sources / relative, pattern, replacement, label)
    require_source_sdk_version(sources, version, languages)


def require_prepared_native_assets(
    sources: Path,
    sdks: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    version_value = require_semver(sdk_version, "SDK version")
    expected_sdk_entries = {*HOSTS, "codex-agent-native-wrapper-sdks.json",
                            "sdk-compatibility.json", "sdk-runtime-root.pub"}
    if (
        not sdks.is_dir()
        or sdks.is_symlink()
        or {path.name for path in sdks.iterdir()} != expected_sdk_entries
        or not (sdks / "codex-agent-native-wrapper-sdks.json").is_file()
        or (sdks / "codex-agent-native-wrapper-sdks.json").is_symlink()
    ):
        raise ValueError("staged SDK root inventory mismatch")
    compatibility_path = sdks / "sdk-compatibility.json"
    if not compatibility_path.is_file() or compatibility_path.is_symlink():
        raise ValueError("staged SDK compatibility declaration is missing or symbolic")
    compatibility_bytes = compatibility_path.read_bytes()
    runtime_root = sdks / "sdk-runtime-root.pub"
    if not runtime_root.is_file() or runtime_root.is_symlink() or runtime_root.stat().st_size > 4096:
        raise ValueError("staged SDK Runtime trust root is missing, symbolic, or oversized")
    root_bytes = runtime_root.read_bytes()
    public_key_fingerprint(root_bytes)
    compatibility = validate_sdk_compatibility(load_canonical_json_bytes(compatibility_bytes))
    if compatibility["sdkVersion"] != version_value:
        raise ValueError("prepared SDK compatibility version mismatch")
    embedded = {record["target"]: record for record in compatibility["runtime"]["embeddedVariants"]}
    if set(embedded) != set(HOSTS):
        raise ValueError("SDK compatibility target inventory mismatch")
    parent_specs = {
        "python": (sources / "python/src/codex_agent/native", set(HOSTS),
                   {"sdk-compatibility.json", "sdk-runtime-root.pub"}),
        "csharp": (sources / "csharp/native",
            set(PACKAGE_CLASSIFIERS.values()), {"README.md", "sdk-compatibility.json", "sdk-runtime-root.pub"},
        ),
        "rust": (sources / "rust/native", set(PACKAGE_CLASSIFIERS.values()),
                 {"sdk-compatibility.json", "sdk-runtime-root.pub"}),
        "cpp": (sources / "cpp/native", set(HOSTS), set()),
        "dart": (sources / "dart/lib/src/native", set(HOSTS),
                 {"README.md", "sdk-compatibility.json", "sdk-runtime-root.pub"}),
    }
    for language in languages:
        parent, directories, regular_files = parent_specs[language]
        if not parent.is_dir() or parent.is_symlink():
            raise ValueError(f"prepared native root is missing or symbolic: {parent}")
        entries = {path.name: path for path in parent.iterdir()}
        if set(entries) != directories | regular_files:
            raise ValueError(f"prepared native classifier inventory mismatch: {parent}")
        if any(not entries[name].is_dir() or entries[name].is_symlink() for name in directories):
            raise ValueError(f"prepared native classifier is missing or symbolic: {parent}")
        if any(not entries[name].is_file() or entries[name].is_symlink() for name in regular_files):
            raise ValueError(f"prepared native metadata is missing or symbolic: {parent}")
        if "sdk-compatibility.json" in regular_files and \
                entries["sdk-compatibility.json"].read_bytes() != compatibility_bytes:
            raise ValueError(f"prepared SDK compatibility bytes differ: {parent}")
        if "sdk-runtime-root.pub" in regular_files and \
                entries["sdk-runtime-root.pub"].read_bytes() != root_bytes:
            raise ValueError(f"prepared SDK Runtime trust root differs: {parent}")
        reject_raw_c_abi_proofs(parent, language)
    for classifier, host in HOSTS.items():
        sdk = sdks / classifier
        if not sdk.is_dir() or sdk.is_symlink():
            raise ValueError(f"missing or symbolic staged SDK: {classifier}")
        library = sdk / host[4]
        if not library.is_file() or library.is_symlink():
            raise ValueError(f"missing staged native library: {classifier}")
        if any(
            not (sdk / proof).is_file() or (sdk / proof).is_symlink()
            for proof in FORBIDDEN_C_ABI_PROOFS
        ):
            raise ValueError(f"missing or symbolic staged raw C ABI proof: {classifier}")
        if f"sha256:{sha256(library)}" != embedded[classifier]["runtimeLibrarySha256"]:
            raise ValueError(f"staged native library disagrees with SDK compatibility: {classifier}")
        package_classifier = PACKAGE_CLASSIFIERS[classifier]
        roots = {
            "Python": sources / f"python/src/codex_agent/native/{classifier}",
            "C#": sources / f"csharp/native/{package_classifier}",
            "Rust": sources / f"rust/native/{package_classifier}",
            "Dart": sources / f"dart/lib/src/native/{classifier}",
        }
        expected = {library.name}
        for language, root in roots.items():
            if language.lower().replace("#", "sharp") not in languages:
                continue
            inventory = {path.relative_to(root).as_posix() for path in files(root)}
            if inventory != expected:
                raise ValueError(f"{language} prepared native inventory mismatch: {classifier}")
            require_matching_native(root, library.name, library, language)
        if "cpp" not in languages:
            continue
        cpp = sources / f"cpp/native/{classifier}"
        cpp_compatibility = cpp / "share/CodexAgent/native/sdk-compatibility.json"
        if not cpp_compatibility.is_file() or cpp_compatibility.is_symlink() or \
                cpp_compatibility.read_bytes() != compatibility_bytes:
            raise ValueError(f"C++ SDK compatibility bytes differ: {classifier}")
        cpp_root = cpp_compatibility.parent / "sdk-runtime-root.pub"
        if not cpp_root.is_file() or cpp_root.is_symlink() or cpp_root.read_bytes() != root_bytes:
            raise ValueError(f"C++ SDK Runtime trust root differs: {classifier}")
        expected_cpp = {
            path: digest for path, digest in package_inventory(sdk)
            if Path(path).name not in FORBIDDEN_C_ABI_PROOFS
        }
        expected_cpp["share/CodexAgent/native/sdk-compatibility.json"] = sha256(cpp_compatibility)
        expected_cpp["share/CodexAgent/native/sdk-runtime-root.pub"] = sha256(cpp_root)
        if dict(package_inventory(cpp)) != expected_cpp:
            raise ValueError(f"C++ prepared native inventory mismatch: {classifier}")


def require_match(value: re.Match[str] | None, message: str) -> re.Match[str]:
    if value is None:
        raise ValueError(message)
    return value


def require_sdk_version_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or symbolic SDK version file: {path}")
    contents = path.read_bytes()
    try:
        value = contents.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("SDK version file must be ASCII") from error
    if not value.endswith("\n") or value.count("\n") != 1:
        raise ValueError("SDK version file must contain one SemVer and one final LF")
    version = require_semver(value[:-1], "SDK version")
    if contents != f"{version}\n".encode("ascii"):
        raise ValueError("SDK version file is not canonical")
    return version


def invalidate_output(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"unsafe output: {path}")
    shutil.rmtree(path)


def package_once(
    sources: Path,
    sdks: Path,
    output: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    if not languages or len(set(languages)) != len(languages) or any(language not in LANGUAGES for language in languages):
        raise ValueError(f"invalid native wrapper language selection: {languages}")
    clean_output(output)
    require_prepared_native_assets(sources, sdks, sdk_version, languages)
    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-package-") as temporary:
        work = Path(temporary).resolve()
        for language in languages:
            if not (sources / language).is_dir():
                raise ValueError(f"missing prepared wrapper source: {language}")
        isolated_sources = work / "sources"
        isolated_sources.mkdir()
        for language in languages:
            shutil.copytree(sources / language, isolated_sources / language)
        sources = isolated_sources
        set_source_sdk_version(sources, sdk_version, languages)

        if "python" in languages:
            python_output = output / "python"
            python_output.mkdir()
            package_python(sources / "python", python_output, work)

        if "csharp" in languages:
            csharp_source = sources / "csharp"
            csharp_output = output / "csharp"
            csharp_output.mkdir()
            run(
                "dotnet", "pack", "src/CodexAgent/CodexAgent.csproj", "--configuration", "Release",
                "--output", csharp_output,
                f"-p:Version={sdk_version}",
                f"-p:PathMap={csharp_source}=/_/csharp", cwd=csharp_source,
            )
            normalize_nupkg(require_one(csharp_output, f"CodexAgent.{sdk_version}.nupkg"), work)

        if "rust" in languages:
            rust_source = sources / "rust"
            rust_target = work / "rust-target"
            run(
                "cargo", "package", "--locked", "--allow-dirty", "--offline",
                cwd=rust_source, env=os.environ | {"CARGO_TARGET_DIR": str(rust_target)},
            )
            rust_output = output / "rust"
            rust_output.mkdir()
            shutil.copy2(require_one(rust_target / "package", f"codex-agent-{sdk_version}.crate"), rust_output)

        if "dart" in languages:
            dart_source = sources / "dart"
            run("dart", "pub", "get", "--enforce-lockfile", cwd=dart_source)
            run("dart", "pub", "publish", "--dry-run", cwd=dart_source)
            dart_release = work / "dart-release"
            stage_dart_release(dart_source, dart_release)
            deterministic_tar(
                dart_release,
                output / f"dart/codex-agent-dart-{sdk_version}.tar.gz",
                f"codex_agent-{sdk_version}",
            )

        if "cpp" in languages:
            cpp_source = sources / "cpp"
            cpp_output = output / "cpp"
            cpp_output.mkdir()
            for classifier in HOSTS:
                build = work / f"cpp-{classifier}"
                install = work / f"cpp-install-{classifier}"
                run(
                    "cmake", "-S", cpp_source, "-B", build,
                    f"-DCodexAgent_C_SDK_ROOT={cpp_source / 'native' / classifier}",
                    f"-DCodexAgent_NATIVE_CLASSIFIER={classifier}",
                    "-DCMAKE_BUILD_TYPE=Release", "-DCODEX_AGENT_CPP_BUILD_TESTS=OFF",
                    "-DCODEX_AGENT_CPP_PACKAGE_ONLY=ON",
                    "-DCODEX_AGENT_CPP_INSTALL_PACKAGE=ON", cwd=work,
                )
                run("cmake", "--install", build, "--prefix", install, "--config", "Release", cwd=work)
                deterministic_zip(
                    install,
                    cpp_output / f"codex-agent-cpp-{sdk_version}-{classifier}.zip",
                    f"codex-agent-cpp-{sdk_version}-{classifier}",
                )
        write_package_toolchains(output, languages)
        for language in languages:
            verify_native_wrapper_sdk_packages(output, sdks, sdk_version, language)


def package_all(
    sources: Path,
    sdks: Path,
    output: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    invalidate_output(output)
    try:
        sdk_version = require_semver(sdk_version, "SDK version")
        package_once(sources, sdks, output, sdk_version, languages)
        with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-reproducibility-") as temporary:
            second = Path(temporary) / "packages"
            package_once(sources, sdks, second, sdk_version, languages)
            first_inventory = dict(package_inventory(output))
            second_inventory = dict(package_inventory(second))
            if first_inventory != second_inventory:
                differences = sorted(first_inventory.keys() | second_inventory.keys())
                details = [
                    f"{path} (first={first_inventory.get(path, 'missing')}, "
                    f"second={second_inventory.get(path, 'missing')})"
                    for path in differences if first_inventory.get(path) != second_inventory.get(path)
                ]
                raise ValueError("native wrapper release packages are not reproducible:\n" + "\n".join(details))
    except Exception:
        invalidate_output(output)
        raise


def host_classifier() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    matches = [classifier for classifier, (expected, architectures, *_rest) in HOSTS.items()
               if system == expected and machine in architectures]
    if len(matches) != 1:
        raise ValueError(f"unsupported or ambiguous host: {system}/{machine}")
    return matches[0]


def executable(build: Path, name: str) -> Path:
    candidates = [build / name, build / f"{name}.exe", build / "Release" / f"{name}.exe"]
    matches = [path for path in candidates if path.is_file()]
    if len(matches) != 1:
        raise ValueError(f"missing consumer executable: {name}")
    return matches[0]


def version(*command: str, allowed_return_codes: tuple[int, ...] = (0,)) -> str:
    result = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode not in allowed_return_codes:
        raise subprocess.CalledProcessError(result.returncode, command, output=result.stdout)
    value = ";".join(line.strip() for line in result.stdout.splitlines() if line.strip())
    if not value or any(character in value for character in "\r\n\t*"):
        raise ValueError(f"invalid toolchain identity: {command[0]}")
    return value


def select_packages(
    packages: Path,
    classifier: str,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> dict[str, Path]:
    version_value = require_semver(sdk_version, "SDK version")
    expected = {
        "python": {
            f"codex_agent-{version_value}.tar.gz",
            *(f"codex_agent-{version_value}-py3-none-{tag}.whl" for tag in PYTHON_TAGS.values()),
            "codex-agent-python-package-toolchain.tsv",
        },
        "csharp": {f"CodexAgent.{version_value}.nupkg", "codex-agent-csharp-package-toolchain.tsv"},
        "rust": {f"codex-agent-{version_value}.crate", "codex-agent-rust-package-toolchain.tsv"},
        "cpp": {
            *(f"codex-agent-cpp-{version_value}-{target}.zip" for target in HOSTS),
            "codex-agent-cpp-package-toolchain.tsv",
        },
        "dart": {f"codex-agent-dart-{version_value}.tar.gz", "codex-agent-dart-package-toolchain.tsv"},
    }
    for language in languages:
        names = expected[language]
        root = packages / language
        actual = {path.relative_to(root).as_posix() for path in files(root)}
        if actual != names:
            raise ValueError(f"{language} package inventory does not match SDK {version_value}")
    selected = {
        "python": packages / "python" / f"codex_agent-{version_value}-py3-none-{PYTHON_TAGS[classifier]}.whl",
        "csharp": packages / "csharp" / f"CodexAgent.{version_value}.nupkg",
        "rust": packages / "rust" / f"codex-agent-{version_value}.crate",
        "cpp": packages / "cpp" / f"codex-agent-cpp-{version_value}-{classifier}.zip",
        "dart": packages / "dart" / f"codex-agent-dart-{version_value}.tar.gz",
    }
    return {language: selected[language] for language in languages}


def require_embedded_package_versions(
    packages: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    version_value = require_semver(sdk_version, "SDK version")
    select_packages(packages, "linux-x64", version_value, languages)

    def require_version(actual: str | None, label: str) -> None:
        if actual != version_value:
            raise ValueError(f"{label} embeds SDK version {actual!r}, expected {version_value}")

    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-version-") as temporary:
        work = Path(temporary)
        if "python" in languages:
            for index, wheel in enumerate(sorted((packages / "python").glob("*.whl"))):
                extracted = work / f"python-wheel-{index}"
                safe_extract_zip(wheel, extracted)
                dist_info = extracted / f"codex_agent-{version_value}.dist-info"
                metadata_path = require_one(extracted, "**/*.dist-info/METADATA")
                wheel_path = require_one(extracted, "**/*.dist-info/WHEEL")
                if metadata_path != dist_info / "METADATA" or wheel_path != dist_info / "WHEEL":
                    raise ValueError(f"Python wheel distribution identity mismatch: {wheel.name}")
                metadata = metadata_path.read_text(encoding="utf-8")
                if re.findall(r"(?m)^Name: (\S+)$", metadata) != ["codex-agent"]:
                    raise ValueError(f"Python wheel distribution name mismatch: {wheel.name}")
                versions = re.findall(r"(?m)^Version: (\S+)$", metadata)
                require_version(versions[0] if len(versions) == 1 else None, f"Python wheel {wheel.name}")
                wheel_metadata = wheel_path.read_text(encoding="utf-8")
                tag = wheel.name.removeprefix(f"codex_agent-{version_value}-").removesuffix(".whl")
                if (re.findall(r"(?m)^Tag: (\S+)$", wheel_metadata) != [tag] or
                        re.findall(r"(?m)^Root-Is-Purelib: (\S+)$", wheel_metadata) != ["false"]):
                    raise ValueError(f"Python wheel interpreter/ABI/platform metadata mismatch: {wheel.name}")

            python_sdist = packages / "python" / f"codex_agent-{version_value}.tar.gz"
            extracted = work / "python-sdist"
            safe_extract_tar(python_sdist, extracted)
            root_metadata = extracted / f"codex_agent-{version_value}/PKG-INFO"
            ancillary_metadata = extracted / f"codex_agent-{version_value}/src/codex_agent.egg-info/PKG-INFO"
            if (set(extracted.rglob("PKG-INFO")) != {root_metadata, ancillary_metadata} or
                    not root_metadata.is_file() or not ancillary_metadata.is_file()):
                raise ValueError("Python sdist requires its exact root and generated package metadata")
            if root_metadata.read_bytes() != ancillary_metadata.read_bytes():
                raise ValueError("Python sdist root and generated package metadata differ")
            metadata = root_metadata.read_text(encoding="utf-8")
            if re.findall(r"(?m)^Name: (\S+)$", metadata) != ["codex-agent"]:
                raise ValueError("Python sdist distribution name mismatch")
            versions = re.findall(r"(?m)^Version: (\S+)$", metadata)
            require_version(versions[0] if len(versions) == 1 else None, "Python sdist")
            source_manifest = root_metadata.parent / "pyproject.toml"
            if not source_manifest.is_file():
                raise ValueError("Python sdist requires its build manifest")
            source_project = tomllib.loads(source_manifest.read_text(encoding="utf-8"))
            if source_project.get("build-system") != {
                "requires": ["setuptools>=68", "wheel==0.45.1"],
                "build-backend": "setuptools.build_meta",
            }:
                raise ValueError("Python sdist build dependencies/backend mismatch")
            project = source_project.get("project")
            if not isinstance(project, dict) or project.get("name") != "codex-agent":
                raise ValueError("Python sdist manifest distribution name mismatch")
            require_version(project.get("version") if isinstance(project, dict) else None, "Python sdist manifest")

        if "csharp" in languages:
            csharp = packages / "csharp" / f"CodexAgent.{version_value}.nupkg"
            extracted = work / "csharp"
            safe_extract_zip(csharp, extracted)
            nuspec_path = require_one(extracted, "*.nuspec")
            if nuspec_path != extracted / "CodexAgent.nuspec":
                raise ValueError("C# package nuspec identity mismatch")
            nuspec = ET.parse(nuspec_path).getroot()
            official = "http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd"
            namespace = {"package": "", f"{{{official}}}package": f"{{{official}}}"}.get(nuspec.tag)
            if namespace is None:
                raise ValueError("C# package nuspec namespace mismatch")
            metadata = [item for item in nuspec if item.tag == f"{namespace}metadata"]
            if len(metadata) != 1:
                raise ValueError("C# package nuspec metadata mismatch")
            ids = [item.text for item in metadata[0] if item.tag == f"{namespace}id"]
            versions = [item.text for item in metadata[0] if item.tag == f"{namespace}version"]
            if ids != ["CodexAgent"]:
                raise ValueError("C# package NuGet ID mismatch")
            require_version(versions[0] if len(versions) == 1 else None, "C# package")

        if "rust" in languages:
            rust = packages / "rust" / f"codex-agent-{version_value}.crate"
            extracted = work / "rust"
            safe_extract_tar(rust, extracted)
            manifest_path = require_one(extracted, "**/Cargo.toml")
            if manifest_path != extracted / f"codex-agent-{version_value}/Cargo.toml":
                raise ValueError("Rust package archive root does not match its coordinate")
            rust_manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            package = rust_manifest.get("package")
            if not isinstance(package, dict) or package.get("name") != "codex-agent":
                raise ValueError("Rust package name does not match its coordinate")
            require_version(package.get("version"), "Rust package")

        if "cpp" in languages:
            for classifier in HOSTS:
                cpp = packages / "cpp" / f"codex-agent-cpp-{version_value}-{classifier}.zip"
                extracted = work / f"cpp-{classifier}"
                safe_extract_zip(cpp, extracted)
                config = extracted / (
                    f"codex-agent-cpp-{version_value}-{classifier}/lib/cmake/CodexAgent"
                )
                version_file = config / "CodexAgentConfigVersion.cmake"
                config_file = config / "CodexAgentConfig.cmake"
                if any(not path.is_file() or path.is_symlink() for path in (version_file, config_file)):
                    raise ValueError(f"C++ package {classifier} CMake coordinate is missing")
                contents = version_file.read_text(encoding="utf-8")
                versions = re.findall(r'(?m)^set\(PACKAGE_VERSION "([^"]+)"\)$', contents)
                require_version(versions[0] if len(versions) == 1 else None, f"C++ package {classifier}")

        if "dart" in languages:
            dart = packages / "dart" / f"codex-agent-dart-{version_value}.tar.gz"
            extracted = work / "dart"
            safe_extract_tar(dart, extracted)
            pubspec = require_one(extracted, "**/pubspec.yaml")
            if pubspec != extracted / f"codex_agent-{version_value}/pubspec.yaml":
                raise ValueError("Dart package archive root does not match its coordinate")
            contents = pubspec.read_text(encoding="utf-8")
            if re.findall(r"(?m)^name: (\S+)$", contents) != ["codex_agent"]:
                raise ValueError("Dart package name does not match its coordinate")
            versions = re.findall(r"(?m)^version: (\S+)$", contents)
            require_version(versions[0] if len(versions) == 1 else None, "Dart package")


def require_embedded_sdk_compatibility(
    packages: Path,
    sdks: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    expected = (sdks / "sdk-compatibility.json").read_bytes()
    root_path = sdks / "sdk-runtime-root.pub"
    if not root_path.is_file() or root_path.is_symlink() or root_path.stat().st_size > 4096:
        raise ValueError("staged SDK Runtime trust root is missing, symbolic, or oversized")
    expected_root = root_path.read_bytes()
    public_key_fingerprint(expected_root)
    compatibility = validate_sdk_compatibility(load_canonical_json_bytes(expected))
    if compatibility["sdkVersion"] != require_semver(sdk_version, "SDK version"):
        raise ValueError("embedded SDK compatibility version mismatch")

    def package_root(extracted: Path, archive: Path) -> Path:
        roots = list(extracted.iterdir())
        if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
            raise ValueError(f"{archive.name} must contain one package root")
        return roots[0]

    def expected_path(language: str, archive: Path, extracted: Path) -> Path:
        if language == "python":
            return (
                package_root(extracted, archive) / "src/codex_agent/native/sdk-compatibility.json"
                if archive.name.endswith(".tar.gz")
                else extracted / "codex_agent/native/sdk-compatibility.json"
            )
        if language == "csharp":
            return extracted / "META-INF/codex-agent/sdk-compatibility.json"
        root = package_root(extracted, archive)
        if language == "rust":
            return root / "native/sdk-compatibility.json"
        if language == "cpp":
            return root / "share/CodexAgent/native/sdk-compatibility.json"
        if language == "dart":
            return root / "lib/src/native/sdk-compatibility.json"
        raise ValueError(f"unsupported native wrapper language: {language}")

    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-compatibility-") as temporary:
        work = Path(temporary)
        csharp_inspector: Path | None = None
        for language in languages:
            archives = [
                path for path in files(packages / language)
                if path.name.endswith((".crate", ".nupkg", ".tar.gz", ".whl", ".zip"))
            ]
            if not archives:
                raise ValueError(f"{language} package has no release archive")
            for index, archive in enumerate(archives):
                extracted = work / f"{language}-{index}"
                if archive.name.endswith((".crate", ".tar.gz")):
                    safe_extract_tar(archive, extracted)
                else:
                    safe_extract_zip(archive, extracted)
                declarations = [
                    path for path in files(extracted)
                    if path.name == "sdk-compatibility.json"
                ]
                required = expected_path(language, archive, extracted)
                if declarations != [required] or required.read_bytes() != expected:
                    raise ValueError(
                        f"{language} package {archive.name} does not contain the exact SDK compatibility declaration",
                    )
                roots = [path for path in files(extracted) if path.name == "sdk-runtime-root.pub"]
                required_root = required.with_name("sdk-runtime-root.pub")
                if roots != [required_root] or required_root.read_bytes() != expected_root:
                    raise ValueError(
                        f"{language} package {archive.name} does not contain the exact SDK Runtime trust root",
                    )
                if language == "csharp":
                    assembly = extracted / "lib/net8.0/CodexAgent.dll"
                    assemblies = [path for path in files(extracted)
                                  if path.name.lower() == "codexagent.dll"]
                    if assemblies != [assembly]:
                        raise ValueError("C# package must contain only the expected CodexAgent.dll")
                    if csharp_inspector is None:
                        project = (Path(__file__).resolve().parents[1] /
                                   "codex-agent-bindings/csharp/tools/VerifySdkRuntimeRoot/"
                                   "VerifySdkRuntimeRoot.csproj")
                        tool_work = work / "csharp-inspector"
                        tool_work.mkdir()
                        properties = (
                            f"-p:BaseOutputPath={tool_work / 'bin'}/",
                            f"-p:BaseIntermediateOutputPath={tool_work / 'obj'}/",
                            f"-p:MSBuildProjectExtensionsPath={tool_work / 'obj'}/",
                        )
                        run("dotnet", "restore", project, "--source", tool_work,
                            *properties, cwd=tool_work)
                        run("dotnet", "build", project, "--no-restore", *properties,
                            cwd=tool_work)
                        csharp_inspector = tool_work / "bin/Debug/net8.0/VerifySdkRuntimeRoot.dll"
                    result = subprocess.run(
                        ["dotnet", str(csharp_inspector), str(assembly), str(required_root), str(required)],
                        capture_output=True, text=True, check=False, timeout=30,
                    )
                    if result.returncode != 0:
                        raise ValueError(f"C# package embedded SDK Runtime trust resources are invalid: {result.stderr.strip()}")


def require_embedded_native_assets(
    packages: Path,
    sdks: Path,
    sdk_version: str,
    languages: tuple[str, ...] = LANGUAGES,
) -> None:
    version_value = require_semver(sdk_version, "SDK version")

    def require_inventory(directory: Path, expected: set[str], language: str) -> None:
        actual = {path.relative_to(directory).as_posix() for path in files(directory)}
        if actual != expected:
            raise ValueError(f"{language} package native target inventory mismatch")

    def target_files(prefix: str, classifier: str) -> set[str]:
        return {f"{prefix}/{Path(HOSTS[classifier][4]).name}"}

    def root(extracted: Path, archive: Path) -> Path:
        roots = list(extracted.iterdir())
        if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
            raise ValueError(f"{archive.name} must contain one package root")
        return roots[0]

    def verify_target(
        package_target: Path,
        classifier: str,
        language: str,
    ) -> None:
        sdk = sdks / classifier
        sdk_library = sdk / HOSTS[classifier][4]
        packaged_library = package_target / sdk_library.name
        if (not packaged_library.is_file() or packaged_library.is_symlink() or
                sha256(packaged_library) != sha256(sdk_library)):
            raise ValueError(f"{language} package native library differs: {classifier}")

    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-assets-") as temporary:
        work = Path(temporary)
        if "python" in languages:
            python = packages / "python"
            sdist = python / f"codex_agent-{version_value}.tar.gz"
            extracted = work / "python-sdist"
            safe_extract_tar(sdist, extracted)
            reject_raw_c_abi_proofs(extracted, "Python")
            native = root(extracted, sdist) / "src/codex_agent/native"
            require_inventory(
                native,
                {"sdk-compatibility.json", "sdk-runtime-root.pub"} | {
                    path for classifier in HOSTS for path in target_files(classifier, classifier)
                },
                "Python",
            )
            for classifier in HOSTS:
                verify_target(native / classifier, classifier, "Python")
            for classifier, tag in PYTHON_TAGS.items():
                wheel = python / f"codex_agent-{version_value}-py3-none-{tag}.whl"
                extracted = work / f"python-{classifier}"
                safe_extract_zip(wheel, extracted)
                reject_raw_c_abi_proofs(extracted, "Python")
                native = extracted / "codex_agent/native"
                require_inventory(
                    native,
                    {"sdk-compatibility.json", "sdk-runtime-root.pub"} | target_files(classifier, classifier),
                    "Python",
                )
                verify_target(native / classifier, classifier, "Python")
        if "csharp" in languages:
            archive = packages / "csharp" / f"CodexAgent.{version_value}.nupkg"
            extracted = work / "csharp"
            safe_extract_zip(archive, extracted)
            reject_nuget_build_hooks(extracted)
            reject_raw_c_abi_proofs(extracted, "C#")
            require_inventory(
                extracted / "runtimes",
                {
                    path
                    for classifier, package_classifier in PACKAGE_CLASSIFIERS.items()
                    for path in target_files(f"{package_classifier}/native", classifier)
                },
                "C#",
            )
            for classifier, package_classifier in PACKAGE_CLASSIFIERS.items():
                verify_target(extracted / f"runtimes/{package_classifier}/native", classifier, "C#")
        if "rust" in languages:
            archive = packages / "rust" / f"codex-agent-{version_value}.crate"
            extracted = work / "rust"
            safe_extract_tar(archive, extracted)
            reject_raw_c_abi_proofs(extracted, "Rust")
            native = root(extracted, archive) / "native"
            require_inventory(
                native,
                {"sdk-compatibility.json", "sdk-runtime-root.pub"} | {
                    path
                    for classifier, package_classifier in PACKAGE_CLASSIFIERS.items()
                    for path in target_files(package_classifier, classifier)
                },
                "Rust",
            )
            for classifier, package_classifier in PACKAGE_CLASSIFIERS.items():
                verify_target(native / package_classifier, classifier, "Rust")
        if "dart" in languages:
            archive = packages / "dart" / f"codex-agent-dart-{version_value}.tar.gz"
            extracted = work / "dart"
            safe_extract_tar(archive, extracted)
            reject_raw_c_abi_proofs(extracted, "Dart")
            native = root(extracted, archive) / "lib/src/native"
            require_inventory(
                native,
                {"README.md", "sdk-compatibility.json", "sdk-runtime-root.pub"} | {
                    path for classifier in HOSTS for path in target_files(classifier, classifier)
                },
                "Dart",
            )
            for classifier in HOSTS:
                verify_target(native / classifier, classifier, "Dart")
        if "cpp" in languages:
            for classifier in HOSTS:
                archive = packages / "cpp" / f"codex-agent-cpp-{version_value}-{classifier}.zip"
                extracted = work / f"cpp-{classifier}"
                safe_extract_zip(archive, extracted)
                reject_raw_c_abi_proofs(extracted, "C++")
                package = root(extracted, archive)
                metadata_root = package / "share/CodexAgent/native"
                require_inventory(
                    metadata_root,
                    {"sdk-compatibility.json", "sdk-runtime-root.pub"},
                    "C++",
                )
                require_inventory(
                    package / "share/CodexAgent/loader",
                    {"native_loader.cpp", "generate_native_dispatch.py"},
                    "C++",
                )
                require_inventory(
                    package / "share/doc/CodexAgent",
                    {"README.md", "LICENSE.txt"},
                    "C++",
                )
                expected_native = {"include/codex_agent.h", HOSTS[classifier][4]}
                if classifier.startswith("linux-"):
                    expected_native.add("lib/libcodex_agent.so.1")
                elif classifier == "windows-x64":
                    expected_native.update({"lib/libcodex_agent.dll.a", "lib/codex_agent.lib"})
                actual_native = {
                    path.relative_to(package).as_posix()
                    for path in files(package)
                    if path.relative_to(package).as_posix() == "include/codex_agent.h"
                    or path.name.startswith("libcodex_agent.")
                    or path.name in {"codex_agent.dll", "codex_agent.lib"}
                    or path.suffix in {".a", ".lib", ".o", ".obj", ".dll", ".dylib", ".so"}
                }
                if actual_native != expected_native:
                    raise ValueError("C++ package native target inventory mismatch")
                for relative in expected_native:
                    packaged = package / relative
                    staged = sdks / classifier / relative
                    if (not packaged.is_file() or packaged.is_symlink() or not staged.is_file() or
                            staged.is_symlink() or sha256(packaged) != sha256(staged)):
                        raise ValueError(f"C++ package native artifact differs: {classifier}/{relative}")
                packaged_license = package / "share/doc/CodexAgent/LICENSE.txt"
                staged_license = sdks / classifier / "LICENSE.txt"
                if (not packaged_license.is_file() or packaged_license.is_symlink() or
                        not staged_license.is_file() or staged_license.is_symlink() or
                        sha256(packaged_license) != sha256(staged_license)):
                    raise ValueError(f"C++ package legal artifact differs: {classifier}/LICENSE.txt")


def verify_native_wrapper_sdk_packages(
    packages: Path,
    staged_sdks: Path,
    product_version: str,
    language: str,
) -> None:
    """Verify one final package family against supplied, unauthenticated staged SDK bytes."""
    if language not in LANGUAGES:
        raise ValueError(f"unsupported native wrapper language: {language}")
    version = require_semver(product_version, "SDK product version")
    selected = (language,)
    require_embedded_sdk_compatibility(packages, staged_sdks, version, selected)
    require_embedded_package_versions(packages, version, selected)
    require_embedded_native_assets(packages, staged_sdks, version, selected)


def set_consumer_sdk_version(
    csharp: Path, rust: Path, dart: Path, sdk_version: str, languages: tuple[str, ...] = LANGUAGES,
) -> None:
    version_value = require_semver(sdk_version, "SDK version")
    if "csharp" in languages:
        replace_once(
            csharp / "CodexAgent.Consumer.csproj",
            r'(<PackageReference Include="CodexAgent" Version=")[^"]+(" />)',
            rf"\g<1>{version_value}\g<2>",
            "C# consumer",
        )
    if "rust" in languages:
        replace_once(
            rust / "Cargo.lock",
            r'(?m)(^name = "codex-agent"\nversion = ")[^"]+("$)',
            rf"\g<1>{version_value}\g<2>",
            "Rust consumer lockfile",
        )
    if "dart" in languages:
        replace_once(
            dart / "pubspec.lock",
            r'(?m)(^  codex_agent:\n(?:.*\n){5}    version: ")[^"]+("$)',
            rf"\g<1>{version_value}\g<2>",
            "Dart consumer lockfile",
        )


def set_dart_consumer_path(consumer: Path, package: Path) -> None:
    relative = Path(os.path.relpath(package, consumer)).as_posix()
    replace_once(
        consumer / "pubspec.yaml",
        r"^(    path: )\S+$",
        rf"\g<1>{relative}",
        "Dart consumer manifest path",
    )
    replace_once(
        consumer / "pubspec.lock",
        r'(?m)(^  codex_agent:\n(?:.*\n){2}      path: ")[^"]+("$)',
        rf"\g<1>{relative}\g<2>",
        "Dart consumer lockfile path",
    )


def consume(
    repository: Path,
    packages: Path,
    sdks: Path,
    plan: Path,
    output: Path,
    sdk_version: str,
) -> None:
    invalidate_output(output)
    try:
        _consume(repository, packages, sdks, plan, output, sdk_version)
    except Exception:
        invalidate_output(output)
        raise


def consume_language(
    repository: Path,
    packages: Path,
    sdks: Path,
    output: Path,
    sdk_version: str,
    language: str,
    *,
    offline: bool = False,
    expected_classifier: str | None = None,
    package_negative_evidence: Path | None = None,
) -> None:
    """Execute one imported-package host consumer; never issue a legacy lane receipt.

    The caller authenticates the package and Runtime inputs. These raw host/tool
    reports do not replace compiler/parity evidence or confer release admission.
    """
    if language not in LANGUAGES:
        raise ValueError(f"unsupported native wrapper language: {language}")
    if (language == "cpp") != (package_negative_evidence is not None):
        raise ValueError("C++ requires a separate package negative evidence output")
    destinations = [output] + ([package_negative_evidence] if package_negative_evidence is not None else [])
    for destination in destinations:
        if any(path.is_symlink() or path.exists() and not path.is_dir()
               for path in (destination, *destination.parents)):
            raise ValueError("Unsafe installed consumer evidence output")
        resolved = destination.resolve()
        protected = (packages, sdks, repository / "ci", repository / "codex-agent-bindings")
        if (resolved == Path(resolved.anchor) or resolved in (Path.home().resolve(), repository.resolve()) or
                any(resolved.is_relative_to(path.resolve()) or path.resolve().is_relative_to(resolved)
                    for path in protected) or
                any(other != destination and (resolved.is_relative_to(other.resolve()) or
                    other.resolve().is_relative_to(resolved)) for other in destinations)):
            raise ValueError("Installed consumer evidence outputs overlap inputs or each other")
    if len({path.resolve() for path in destinations}) != len(destinations):
        raise ValueError("Installed consumer evidence outputs overlap each other")
    invalidate_output(output)
    if package_negative_evidence is not None:
        invalidate_output(package_negative_evidence)
    try:
        if expected_classifier is not None:
            if expected_classifier not in HOSTS:
                raise ValueError(f"unsupported expected host classifier: {expected_classifier}")
            actual_classifier = host_classifier()
            if actual_classifier != expected_classifier:
                raise ValueError(
                    "installed consumer host classifier mismatch: "
                    f"expected {expected_classifier}, found {actual_classifier}"
                )
        _consume(repository, packages, sdks, None, output, sdk_version,
                 languages=(language,), offline=offline, package_negative_evidence=package_negative_evidence)
    except Exception:
        invalidate_output(output)
        if package_negative_evidence is not None:
            invalidate_output(package_negative_evidence)
        raise


def _consume(
    repository: Path,
    packages: Path,
    sdks: Path,
    plan: Path | None,
    output: Path,
    sdk_version: str,
    *,
    languages: tuple[str, ...] = LANGUAGES,
    offline: bool = False,
    package_negative_evidence: Path | None = None,
) -> None:
    if (plan is None and (len(languages) != 1 or languages[0] not in LANGUAGES) or
            plan is not None and languages != LANGUAGES):
        raise ValueError("Partial installed consumers cannot issue an all-language lane receipt")
    sdk_version = require_semver(sdk_version, "SDK version")
    classifier = host_classifier()
    sdk_library = (sdks / classifier / HOSTS[classifier][4]).resolve()
    if not sdk_library.is_file() or sdk_library.is_symlink():
        raise ValueError(f"missing matching-host SDK: {sdk_library}")
    sdk_compatibility = sdks / "sdk-compatibility.json"
    if not sdk_compatibility.is_file() or sdk_compatibility.is_symlink():
        raise ValueError(f"missing SDK compatibility declaration: {sdk_compatibility}")
    compatibility = validate_sdk_compatibility(load_canonical_json_bytes(sdk_compatibility.read_bytes()))
    if compatibility["sdkVersion"] != sdk_version:
        raise ValueError("installed consumer SDK compatibility version mismatch")
    require_embedded_package_versions(packages, sdk_version, languages)
    clean_output(output)
    selected = select_packages(packages, classifier, sdk_version, languages)
    if "csharp" in languages:
        require_no_nuget_build_hooks(selected["csharp"])
    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-consumer-") as temporary:
        work = Path(temporary).resolve()
        consumer_env = os.environ.copy()
        consumer_env.pop("CODEX_AGENT_LIBRARY", None)
        csharp_consumer = work / "csharp-consumer"
        rust_consumer = work / "rust-consumer"
        dart_consumer = work / "dart-consumer"
        if "csharp" in languages:
            shutil.copytree(
                repository / "codex-agent-bindings/csharp/samples/CodexAgent.Consumer",
                csharp_consumer, ignore=shutil.ignore_patterns("bin", "obj"),
            )
        if "rust" in languages:
            shutil.copytree(
                repository / "codex-agent-bindings/rust/consumer",
                rust_consumer, ignore=shutil.ignore_patterns("target"),
            )
        if "dart" in languages:
            shutil.copytree(
                repository / "codex-agent-bindings/dart/consumer",
                dart_consumer, ignore=shutil.ignore_patterns(".dart_tool"),
            )
        set_consumer_sdk_version(csharp_consumer, rust_consumer, dart_consumer, sdk_version, languages)
        native_name = Path(HOSTS[classifier][4]).name

        if "python" in languages:
            venv = work / "python-venv"
            run(sys.executable, "-m", "venv", venv, cwd=repository)
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run(python, "-m", "pip", "install", "--no-deps", "--no-index", selected["python"], cwd=work)
            python_smoke = repository / "codex-agent-bindings/python/consumer/host_smoke.py"
            python_example = repository / "codex-agent-bindings/python/consumer/lifecycle_example.py"
            python_library = require_matching_native(
                venv, f"**/codex_agent/native/{classifier}/{native_name}", sdk_library, "Python",
            )
            require_matching_compatibility(
                venv, "**/codex_agent/native/sdk-compatibility.json", sdk_compatibility, "Python",
            )
            require_matching_compatibility(
                venv, "**/codex_agent/native/sdk-runtime-root.pub",
                sdks / "sdk-runtime-root.pub", "Python runtime root",
            )
            require_installed_zip_tree(
                selected["python"], "codex_agent", python_library.parents[2], "Python",
                excluded=frozenset({"native", "__pycache__"}),
            )
            reject_raw_c_abi_proofs(python_library.parents[2], "Python")
            run(
                python, "-c", "import runpy,sys; runpy.run_path(sys.argv[1])", python_example,
                cwd=work, env=consumer_env,
            )
            run(python, python_smoke, cwd=work, env=consumer_env)
            run(python, python_smoke, python_library, cwd=work, env=consumer_env)
            run_expect_failure(python, python_smoke, native_name, cwd=work, env=consumer_env)
            run_expect_failure(
                python, python_smoke, python_library, python_library, cwd=work, env=consumer_env,
            )

        if "csharp" in languages:
            nuget = work / "nuget"
            nuget.mkdir()
            shutil.copy2(selected["csharp"], nuget)
            config = work / "NuGet.Config"
            config.write_text(
                '<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear/>'
                f'<add key="local" value="{nuget.as_posix()}"/></packageSources></configuration>\n',
                encoding="utf-8",
            )
            cache = work / "nuget-cache"
            run("dotnet", "restore", csharp_consumer / "CodexAgent.Consumer.csproj", "--force", "--no-http-cache",
                "--packages", cache, "--configfile", config, cwd=work)
            csharp_library = require_matching_native(
                cache,
                f"**/runtimes/{PACKAGE_CLASSIFIERS[classifier]}/native/{native_name}",
                sdk_library,
                "C#",
            )
            require_matching_compatibility(
                cache, "**/META-INF/codex-agent/sdk-compatibility.json", sdk_compatibility, "C#",
            )
            assembly = require_one(cache, "**/lib/net8.0/CodexAgent.dll")
            require_installed_zip_tree(selected["csharp"], "lib/net8.0", assembly.parent, "C#")
            reject_raw_c_abi_proofs(cache, "C#")
            run("dotnet", "build", csharp_consumer / "CodexAgent.Consumer.csproj", "--configuration", "Release",
                "--no-restore", cwd=work)
            run(
                "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
                "--configuration", "Release", "--no-build", "--", cwd=work, env=consumer_env,
            )
            run(
                "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
                "--configuration", "Release", "--no-build", "--", csharp_library,
                cwd=work, env=consumer_env,
            )
            run_expect_failure(
                "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
                "--configuration", "Release", "--no-build", "--", native_name,
                cwd=work, env=consumer_env,
            )
            run_expect_failure(
                "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
                "--configuration", "Release", "--no-build", "--", csharp_library, "release-only", "extra",
                cwd=work, env=consumer_env,
            )

        if "rust" in languages:
            rust_root = work / "rust-package"
            safe_extract_tar(selected["rust"], rust_root)
            rust_package = require_one(rust_root, "codex-agent-*/Cargo.toml").parent
            cargo_toml = rust_consumer / "Cargo.toml"
            cargo_toml.write_text(
                cargo_toml.read_text(encoding="utf-8").replace('path = ".."', f'path = "{rust_package.as_posix()}"'),
                encoding="utf-8",
            )
            rust_library = require_matching_native(
                rust_package,
                f"native/{PACKAGE_CLASSIFIERS[classifier]}/{native_name}",
                sdk_library,
                "Rust",
            )
            require_matching_compatibility(
                rust_package, "native/sdk-compatibility.json", sdk_compatibility, "Rust",
            )
            reject_raw_c_abi_proofs(rust_package, "Rust")
            cargo_env = consumer_env | {"CARGO_TARGET_DIR": str(work / "rust-target")}
            run("cargo", "fetch", "--manifest-path", cargo_toml, "--locked",
                *(["--offline"] if offline else []), cwd=work, env=cargo_env)
            run("cargo", "metadata", "--manifest-path", cargo_toml, "--locked", "--offline", "--no-deps",
                cwd=work, env=cargo_env)
            run("cargo", "build", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
                "--bins", cwd=work, env=cargo_env)
            rust_command = (
                "cargo", "run", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
                "--bin", "codex-agent-rust-host-smoke", "--",
            )
            run(*rust_command, cwd=work, env=cargo_env)
            run(*rust_command, rust_library, cwd=work, env=cargo_env)
            run_expect_failure(*rust_command, native_name, cwd=work, env=cargo_env)
            run_expect_failure(*rust_command, rust_library, rust_library, cwd=work, env=cargo_env)
            fixture = work / ("rust-lifecycle-" + native_name)
            rust_fixture_compiler = shlex.split(os.environ.get("CC", "clang" if classifier == "windows-x64" else "cc"))
            flags = ["-std=gnu11", "-Wall", "-Wextra", "-Werror"]
            flags += ["-dynamiclib" if classifier.startswith("macos-") else "-shared"]
            if classifier != "windows-x64":
                flags += ["-fPIC", "-pthread"]
            flags += [f'-DCODEX_AGENT_TEST_CONTRACT_DIGEST="{compatibility["runtime"]["requiredContractDigest"]}"']
            run(
                *rust_fixture_compiler, *flags,
                repository / "codex-agent-bindings/rust/tests/fixtures/mock_codex_agent.c",
                "-o", fixture, cwd=work,
            )
            run(
                "cargo", "run", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
                "--bin", "codex-agent-rust-lifecycle-smoke", "--", fixture,
                cwd=work, env=cargo_env,
            )

        if "cpp" in languages:
            cpp_root = work / "cpp-package"
            safe_extract_zip(selected["cpp"], cpp_root)
            cpp_prefix = next(path for path in cpp_root.iterdir() if path.is_dir())
            cpp_library = require_matching_native(
                cpp_prefix, HOSTS[classifier][4], sdk_library, "C++",
            )
            require_matching_compatibility(
                cpp_prefix, "share/CodexAgent/native/sdk-compatibility.json", sdk_compatibility, "C++",
            )
            reject_raw_c_abi_proofs(cpp_prefix, "C++")
            cpp_build = work / "cpp-consumer-build"
            run("cmake", "-S", repository / "codex-agent-bindings/cpp/consumer", "-B", cpp_build,
                f"-DCMAKE_PREFIX_PATH={cpp_prefix}", "-DCMAKE_BUILD_TYPE=Release", cwd=work)
            run("cmake", "--build", cpp_build, "--config", "Release", "--target", "codex_agent_host_smoke",
                cwd=work)
            run("cmake", "--build", cpp_build, "--config", "Release", "--target",
                "codex_agent_lifecycle_example", cwd=work)
            if package_negative_evidence is not None:
                run(
                    sys.executable, repository / "codex-agent-bindings/cpp/tools/verify_imported_package.py",
                    "--package-root", cpp_prefix, "--output", package_negative_evidence,
                    "--cmake", "cmake", "--libdir", "lib", "--library", HOSTS[classifier][4],
                    cwd=work,
                )
            cpp_env = consumer_env.copy()
            run(executable(cpp_build, "codex_agent_host_smoke"), cwd=work, env=cpp_env)
            run(executable(cpp_build, "codex_agent_host_smoke"), cpp_library, cwd=work, env=cpp_env)
            run(executable(cpp_build, "codex_agent_lifecycle_example"), cwd=work, env=cpp_env)
            run_expect_failure(
                executable(cpp_build, "codex_agent_host_smoke"), native_name, cwd=work, env=cpp_env,
            )
            run_expect_failure(
                executable(cpp_build, "codex_agent_host_smoke"), cpp_library, cpp_library,
                cwd=work, env=cpp_env,
            )

        if "dart" in languages:
            dart_root = work / "dart-package"
            safe_extract_tar(selected["dart"], dart_root)
            dart_package = require_one(dart_root, "codex_agent-*/pubspec.yaml").parent
            set_dart_consumer_path(dart_consumer, dart_package)
            run("dart", "pub", "get", "--enforce-lockfile",
                *(["--offline"] if offline else []), cwd=dart_consumer)
            dart_library = require_matching_native(
                dart_package,
                f"lib/src/native/{classifier}/{native_name}",
                sdk_library,
                "Dart",
            )
            require_matching_compatibility(
                dart_package, "lib/src/native/sdk-compatibility.json", sdk_compatibility, "Dart",
            )
            reject_raw_c_abi_proofs(dart_package, "Dart")
            run("dart", "run", "bin/host_smoke.dart", cwd=dart_consumer, env=consumer_env)
            run(
                "dart", "run", "bin/host_smoke.dart", dart_library,
                cwd=dart_consumer, env=consumer_env,
            )
            run_expect_failure(
                "dart", "run", "bin/host_smoke.dart", native_name,
                cwd=dart_consumer, env=consumer_env,
            )
            run_expect_failure(
                "dart", "run", "bin/host_smoke.dart", dart_library, dart_library,
                cwd=dart_consumer, env=consumer_env,
            )

        wrong_library = work / f"wrong-{native_name}"
        wrong_library.write_bytes(b"not a native library")
        if "python" in languages:
            run_expect_failure(python, python_smoke, wrong_library, cwd=work, env=consumer_env)
        if "csharp" in languages:
            run_expect_failure(
                "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
                "--configuration", "Release", "--no-build", "--", wrong_library, "release-only",
                cwd=work, env=consumer_env,
            )
        if "rust" in languages:
            run_expect_failure(*rust_command, wrong_library, cwd=work, env=cargo_env)
        if "cpp" in languages:
            run_expect_failure(
                executable(cpp_build, "codex_agent_host_smoke"), wrong_library, cwd=work, env=cpp_env,
            )
        if "dart" in languages:
            run_expect_failure(
                "dart", "run", "bin/host_smoke.dart", wrong_library,
                cwd=dart_consumer, env=consumer_env,
            )

    evidence_arguments: list[str] = []
    artifact_arguments: list[str] = []
    for language, package in selected.items():
        if plan is not None:
            copied = output / "packages" / language / package.name
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(package, copied)
            artifact_arguments += ["--artifact", f"packages/{language}/{package.name}=native-wrapper-package"]
        evidence = output / "evidence" / language / f"{classifier}.tsv"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(
            "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus\n"
            f"{classifier}\t{language}-package/{package.name}\t{sha256(package)}\t{sha256(sdk_library)}\t"
            f"{language}-installed-host-lifecycle\tpassed\n",
            encoding="utf-8",
        )
        evidence_arguments += ["--evidence", f"evidence/{language}/{classifier}.tsv=cross-language-host-consumer"]

    tools = {}
    if "python" in languages:
        tools["python"] = version(sys.executable, "--version")
    if "csharp" in languages:
        tools["dotnet"] = version("dotnet", "--version")
    if "rust" in languages:
        tools.update(cargo=version("cargo", "--version"), rustc=version("rustc", "-vV"))
        tools["rustFixtureCompiler"] = version(*rust_fixture_compiler, "--version")
    if "cpp" in languages:
        compiler = "cl" if os.name == "nt" else os.environ.get("CXX", "c++")
        tools["cppCompiler"] = (version(compiler, allowed_return_codes=(0, 2)) if os.name == "nt"
                                else version(compiler, "--version"))
        tools["cmake"] = version("cmake", "--version").split(";", 1)[0]
    if "dart" in languages:
        tools["dart"] = version("dart", "--version")
    if plan is None:
        (output / "evidence" / languages[0] / "toolchain.tsv").write_text(
            "tool\tversion\n" + "".join(f"{name}\t{value}\n" for name, value in sorted(tools.items())),
            encoding="utf-8",
        )
        return
    runner_os, runner_arch = HOSTS[classifier][2:4]
    lane = f"desktop-{classifier}"
    tree = os.environ.get("CI_VALIDATION_TREE") or os.environ.get("GITHUB_SHA", "")
    artifact_name = f"codex-agent-ci-{lane}-{tree}-native-wrapper-host"
    command: list[str | Path] = [
        sys.executable, repository / "ci/receipt.py", "create", "--plan", plan, "--lane", lane,
        "--output", output, "--artifact-name", artifact_name,
        "--runner", f"os={runner_os}", "--runner", f"arch={runner_arch}",
        "--runner", f"image={os.environ.get('ImageOS', 'unavailable')}",
        "--runner", f"imageVersion={os.environ.get('ImageVersion', 'unavailable')}",
        "--toolchain", "validationActions=test",
    ]
    for name, value in sorted(tools.items()):
        command += ["--toolchain", f"{name}={value}"]
    command += artifact_arguments + evidence_arguments
    run(*command, cwd=repository)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    package = commands.add_parser("package")
    package.add_argument("--sources", type=Path, required=True)
    package.add_argument("--sdks", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--sdk-version-file", type=Path, required=True)
    package.add_argument("--language", choices=LANGUAGES, action="append")
    for name in ("consume", "consume-language"):
        consumer = commands.add_parser(name)
        consumer.add_argument("--repository", type=Path, required=True)
        consumer.add_argument("--packages", type=Path, required=True)
        consumer.add_argument("--sdks", type=Path, required=True)
        consumer.add_argument("--output", type=Path, required=True)
        consumer.add_argument("--sdk-version-file", type=Path, required=True)
        if name == "consume":
            consumer.add_argument("--plan", type=Path, required=True)
        else:
            consumer.add_argument("--language", choices=LANGUAGES, required=True)
            consumer.add_argument("--expected-classifier", choices=HOSTS, required=True)
            consumer.add_argument("--offline", action="store_true")
            consumer.add_argument("--package-negative-evidence", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    output = arguments.output.absolute()
    if arguments.command != "consume-language":
        invalidate_output(output)
    sdk_version = require_sdk_version_file(arguments.sdk_version_file.resolve())
    if arguments.command == "package":
        package_all(
            arguments.sources.resolve(), arguments.sdks.resolve(), output, sdk_version,
            tuple(arguments.language or LANGUAGES),
        )
    elif arguments.command == "consume-language":
        consume_language(
            arguments.repository.resolve(), arguments.packages.resolve(), arguments.sdks.resolve(),
            output, sdk_version, arguments.language, offline=arguments.offline,
            expected_classifier=arguments.expected_classifier,
            package_negative_evidence=arguments.package_negative_evidence,
        )
    else:
        consume(arguments.repository.resolve(), arguments.packages.resolve(), arguments.sdks.resolve(),
                arguments.plan.resolve(), output, sdk_version)


if __name__ == "__main__":
    main()
