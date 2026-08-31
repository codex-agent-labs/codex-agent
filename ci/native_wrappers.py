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

from products.inventory import require_semver


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


def require_matching_proofs(package_root: Path, sdk_root: Path, language: str) -> None:
    for name in ("codex-agent-c-abi-manifest.json", "codex-agent-c-abi-evidence.json"):
        package_file = package_root / name
        sdk_file = sdk_root / name
        if (not package_file.is_file() or package_file.is_symlink() or
                not sdk_file.is_file() or sdk_file.is_symlink() or
                sha256(package_file) != sha256(sdk_file)):
            raise ValueError(f"{language} installed package {name} does not match the verified SDK")


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
        "class BinaryDistribution(Distribution):\n"
        "    def has_ext_modules(self): return True\n"
        "setup(distclass=BinaryDistribution)\n"
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
            if child.name != classifier:
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
            native = {name.split("/native/", 1)[1].split("/", 1)[0]
                      for name in archive.namelist() if "/native/" in name}
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


def write_package_toolchains(output: Path) -> None:
    compiler = "cl" if os.name == "nt" else os.environ.get("CXX", "c++")
    cpp_version = (
        version(compiler, allowed_return_codes=(0, 2))
        if os.name == "nt"
        else version(compiler, "--version")
    )
    identities = {
        "python": {
            "build": version(sys.executable, "-m", "build", "--version"),
            "python": version(sys.executable, "--version"),
            "setuptools-wheel": version(
                sys.executable, "-c",
                "import importlib.metadata as m;print(m.version('setuptools')+';'+m.version('wheel'))",
            ),
        },
        "csharp": {"dotnet": version("dotnet", "--version")},
        "rust": {"cargo": version("cargo", "--version"), "rustc": version("rustc", "-vV")},
        "cpp": {"cmake": version("cmake", "--version").split(";", 1)[0], "cppCompiler": cpp_version},
        "dart": {"dart": version("dart", "--version")},
    }
    for language, tools in identities.items():
        (output / language / f"codex-agent-{language}-package-toolchain.tsv").write_text(
            "tool\tversion\n" + "".join(f"{name}\t{value}\n" for name, value in sorted(tools.items())),
            encoding="utf-8",
        )


def require_source_sdk_version(sources: Path, sdk_version: str) -> None:
    expected = require_semver(sdk_version, "SDK version")

    def regular(relative: str) -> Path:
        path = sources / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing or symbolic SDK package manifest: {relative}")
        return path

    rust_lock = regular("rust/Cargo.lock").read_text(encoding="utf-8")
    versions = {
        "python": tomllib.loads(regular("python/pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "csharp": ET.parse(regular("csharp/src/CodexAgent/CodexAgent.csproj")).findtext(".//VersionPrefix"),
        "rust": tomllib.loads(regular("rust/Cargo.toml").read_text(encoding="utf-8"))["package"]["version"],
        "rust-lock": require_match(
            re.search(r'(?m)^name = "codex-agent"\nversion = "([^"]+)"$', rust_lock),
            "Rust lockfile does not declare the package version",
        ).group(1),
        "cpp": require_match(
            re.search(
                r"(?m)^project\(CodexAgent VERSION ([^ ]+) LANGUAGES CXX\)$",
                regular("cpp/CMakeLists.txt").read_text(encoding="utf-8"),
            ),
            "C++ package manifest does not declare the CodexAgent project version",
        ).group(1),
        "dart": require_match(
            re.search(r"(?m)^version: (\S+)$", regular("dart/pubspec.yaml").read_text(encoding="utf-8")),
            "Dart package manifest does not declare one version",
        ).group(1),
    }
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


def set_source_sdk_version(sources: Path, sdk_version: str) -> None:
    version = require_semver(sdk_version, "SDK version")
    replace_once(
        sources / "python/pyproject.toml",
        r'^(version = ")[^"]+("\s*)$',
        rf"\g<1>{version}\g<2>",
        "Python manifest",
    )
    replace_once(
        sources / "csharp/src/CodexAgent/CodexAgent.csproj",
        r"(<VersionPrefix>)[^<]+(</VersionPrefix>)",
        rf"\g<1>{version}\g<2>",
        "C# manifest",
    )
    replace_once(
        sources / "rust/Cargo.toml",
        r'^(version = ")[^"]+("\s*)$',
        rf"\g<1>{version}\g<2>",
        "Rust manifest",
    )
    replace_once(
        sources / "rust/Cargo.lock",
        r'(?m)(^name = "codex-agent"\nversion = ")[^"]+("$)',
        rf"\g<1>{version}\g<2>",
        "Rust lockfile",
    )
    replace_once(
        sources / "cpp/CMakeLists.txt",
        r"^project\(CodexAgent VERSION \S+ LANGUAGES CXX\)$",
        f"project(CodexAgent VERSION {version} LANGUAGES CXX)",
        "C++ manifest",
    )
    replace_once(
        sources / "dart/pubspec.yaml",
        r"^version: \S+$",
        f"version: {version}",
        "Dart manifest",
    )
    require_source_sdk_version(sources, version)


def require_prepared_native_assets(sources: Path, sdks: Path) -> None:
    expected_sdk_entries = {*HOSTS, "codex-agent-native-wrapper-sdks.json"}
    if (
        not sdks.is_dir()
        or sdks.is_symlink()
        or {path.name for path in sdks.iterdir()} != expected_sdk_entries
        or not (sdks / "codex-agent-native-wrapper-sdks.json").is_file()
        or (sdks / "codex-agent-native-wrapper-sdks.json").is_symlink()
    ):
        raise ValueError("staged SDK root inventory mismatch")
    parent_specs = {
        sources / "python/src/codex_agent/native": (set(HOSTS), set()),
        sources / "csharp/native": (set(PACKAGE_CLASSIFIERS.values()), {"README.md"}),
        sources / "rust/native": (set(PACKAGE_CLASSIFIERS.values()), set()),
        sources / "cpp/native": (set(HOSTS), set()),
        sources / "dart/lib/src/native": (set(HOSTS), {"README.md"}),
    }
    for parent, (directories, regular_files) in parent_specs.items():
        if not parent.is_dir() or parent.is_symlink():
            raise ValueError(f"prepared native root is missing or symbolic: {parent}")
        entries = {path.name: path for path in parent.iterdir()}
        if set(entries) != directories | regular_files:
            raise ValueError(f"prepared native classifier inventory mismatch: {parent}")
        if any(not entries[name].is_dir() or entries[name].is_symlink() for name in directories):
            raise ValueError(f"prepared native classifier is missing or symbolic: {parent}")
        if any(not entries[name].is_file() or entries[name].is_symlink() for name in regular_files):
            raise ValueError(f"prepared native metadata is missing or symbolic: {parent}")
    for classifier, host in HOSTS.items():
        sdk = sdks / classifier
        if not sdk.is_dir() or sdk.is_symlink():
            raise ValueError(f"missing or symbolic staged SDK: {classifier}")
        library = sdk / host[4]
        if not library.is_file() or library.is_symlink():
            raise ValueError(f"missing staged native library: {classifier}")
        package_classifier = PACKAGE_CLASSIFIERS[classifier]
        roots = {
            "Python": sources / f"python/src/codex_agent/native/{classifier}",
            "C#": sources / f"csharp/native/{package_classifier}",
            "Rust": sources / f"rust/native/{package_classifier}",
            "Dart": sources / f"dart/lib/src/native/{classifier}",
        }
        expected = {
            library.name,
            "codex-agent-c-abi-manifest.json",
            "codex-agent-c-abi-evidence.json",
        }
        for language, root in roots.items():
            inventory = {path.relative_to(root).as_posix() for path in files(root)}
            if inventory != expected:
                raise ValueError(f"{language} prepared native inventory mismatch: {classifier}")
            require_matching_native(root, library.name, library, language)
            require_matching_proofs(root, sdk, language)
        cpp = sources / f"cpp/native/{classifier}"
        if package_inventory(cpp) != package_inventory(sdk):
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


def package_once(sources: Path, sdks: Path, output: Path, sdk_version: str) -> None:
    clean_output(output)
    require_prepared_native_assets(sources, sdks)
    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-package-") as temporary:
        work = Path(temporary)
        for language in LANGUAGES:
            if not (sources / language).is_dir():
                raise ValueError(f"missing prepared wrapper source: {language}")
        isolated_sources = work / "sources"
        shutil.copytree(sources, isolated_sources)
        sources = isolated_sources
        set_source_sdk_version(sources, sdk_version)

        python_output = output / "python"
        python_output.mkdir()
        package_python(sources / "python", python_output, work)

        csharp_source = sources / "csharp"
        csharp_output = output / "csharp"
        csharp_output.mkdir()
        run(
            "dotnet", "pack", "src/CodexAgent/CodexAgent.csproj", "--configuration", "Release",
            "--output", csharp_output, "-p:CodexAgentRequireNativeAssets=true",
            f"-p:Version={sdk_version}",
            f"-p:PathMap={csharp_source}=/_/csharp", cwd=csharp_source,
        )
        normalize_nupkg(require_one(csharp_output, f"CodexAgent.{sdk_version}.nupkg"), work)

        rust_source = sources / "rust"
        rust_target = work / "rust-target"
        run(
            "cargo", "package", "--locked", "--allow-dirty", "--offline",
            cwd=rust_source, env=os.environ | {"CARGO_TARGET_DIR": str(rust_target)},
        )
        rust_output = output / "rust"
        rust_output.mkdir()
        shutil.copy2(require_one(rust_target / "package", f"codex-agent-{sdk_version}.crate"), rust_output)

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
                "-DCODEX_AGENT_CPP_INSTALL_PACKAGE=ON", cwd=work,
            )
            run("cmake", "--install", build, "--prefix", install, "--config", "Release", cwd=work)
            deterministic_zip(
                install,
                cpp_output / f"codex-agent-cpp-{sdk_version}-{classifier}.zip",
                f"codex-agent-cpp-{sdk_version}-{classifier}",
            )
        write_package_toolchains(output)
        require_embedded_package_versions(output, sdk_version)


def package_all(sources: Path, sdks: Path, output: Path, sdk_version: str) -> None:
    invalidate_output(output)
    try:
        sdk_version = require_semver(sdk_version, "SDK version")
        package_once(sources, sdks, output, sdk_version)
        with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-reproducibility-") as temporary:
            second = Path(temporary) / "packages"
            package_once(sources, sdks, second, sdk_version)
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


def select_packages(packages: Path, classifier: str, sdk_version: str) -> dict[str, Path]:
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
    for language, names in expected.items():
        root = packages / language
        actual = {path.relative_to(root).as_posix() for path in files(root)}
        if actual != names:
            raise ValueError(f"{language} package inventory does not match SDK {version_value}")
    return {
        "python": packages / "python" / f"codex_agent-{version_value}-py3-none-{PYTHON_TAGS[classifier]}.whl",
        "csharp": packages / "csharp" / f"CodexAgent.{version_value}.nupkg",
        "rust": packages / "rust" / f"codex-agent-{version_value}.crate",
        "cpp": packages / "cpp" / f"codex-agent-cpp-{version_value}-{classifier}.zip",
        "dart": packages / "dart" / f"codex-agent-dart-{version_value}.tar.gz",
    }


def require_embedded_package_versions(packages: Path, sdk_version: str) -> None:
    version_value = require_semver(sdk_version, "SDK version")
    select_packages(packages, "linux-x64", version_value)

    def require_version(actual: str | None, label: str) -> None:
        if actual != version_value:
            raise ValueError(f"{label} embeds SDK version {actual!r}, expected {version_value}")

    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-version-") as temporary:
        work = Path(temporary)
        for index, wheel in enumerate(sorted((packages / "python").glob("*.whl"))):
            extracted = work / f"python-wheel-{index}"
            safe_extract_zip(wheel, extracted)
            metadata = require_one(extracted, "**/*.dist-info/METADATA").read_text(encoding="utf-8")
            versions = re.findall(r"(?m)^Version: (\S+)$", metadata)
            require_version(versions[0] if len(versions) == 1 else None, f"Python wheel {wheel.name}")

        python_sdist = packages / "python" / f"codex_agent-{version_value}.tar.gz"
        extracted = work / "python-sdist"
        safe_extract_tar(python_sdist, extracted)
        metadata = require_one(extracted, "**/PKG-INFO").read_text(encoding="utf-8")
        versions = re.findall(r"(?m)^Version: (\S+)$", metadata)
        require_version(versions[0] if len(versions) == 1 else None, "Python sdist")

        csharp = packages / "csharp" / f"CodexAgent.{version_value}.nupkg"
        extracted = work / "csharp"
        safe_extract_zip(csharp, extracted)
        nuspec = ET.parse(require_one(extracted, "*.nuspec")).getroot()
        versions = [
            element.text
            for element in nuspec.iter()
            if element.tag.rsplit("}", 1)[-1] == "version"
        ]
        require_version(versions[0] if len(versions) == 1 else None, "C# package")

        rust = packages / "rust" / f"codex-agent-{version_value}.crate"
        extracted = work / "rust"
        safe_extract_tar(rust, extracted)
        rust_manifest = tomllib.loads(require_one(extracted, "**/Cargo.toml").read_text(encoding="utf-8"))
        require_version(rust_manifest.get("package", {}).get("version"), "Rust package")

        for classifier in HOSTS:
            cpp = packages / "cpp" / f"codex-agent-cpp-{version_value}-{classifier}.zip"
            extracted = work / f"cpp-{classifier}"
            safe_extract_zip(cpp, extracted)
            contents = require_one(extracted, "**/CodexAgentConfigVersion.cmake").read_text(encoding="utf-8")
            versions = re.findall(r'(?m)^set\(PACKAGE_VERSION "([^"]+)"\)$', contents)
            require_version(versions[0] if len(versions) == 1 else None, f"C++ package {classifier}")

        dart = packages / "dart" / f"codex-agent-dart-{version_value}.tar.gz"
        extracted = work / "dart"
        safe_extract_tar(dart, extracted)
        contents = require_one(extracted, "**/pubspec.yaml").read_text(encoding="utf-8")
        versions = re.findall(r"(?m)^version: (\S+)$", contents)
        require_version(versions[0] if len(versions) == 1 else None, "Dart package")


def set_consumer_sdk_version(csharp: Path, rust: Path, dart: Path, sdk_version: str) -> None:
    version_value = require_semver(sdk_version, "SDK version")
    replace_once(
        csharp / "CodexAgent.Consumer.csproj",
        r'(<PackageReference Include="CodexAgent" Version=")[^"]+(" />)',
        rf"\g<1>{version_value}\g<2>",
        "C# consumer",
    )
    replace_once(
        rust / "Cargo.lock",
        r'(?m)(^name = "codex-agent"\nversion = ")[^"]+("$)',
        rf"\g<1>{version_value}\g<2>",
        "Rust consumer lockfile",
    )
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


def _consume(
    repository: Path,
    packages: Path,
    sdks: Path,
    plan: Path,
    output: Path,
    sdk_version: str,
) -> None:
    sdk_version = require_semver(sdk_version, "SDK version")
    classifier = host_classifier()
    sdk_library = (sdks / classifier / HOSTS[classifier][4]).resolve()
    if not sdk_library.is_file() or sdk_library.is_symlink():
        raise ValueError(f"missing matching-host SDK: {sdk_library}")
    clean_output(output)
    selected = select_packages(packages, classifier, sdk_version)
    with tempfile.TemporaryDirectory(prefix="codex-agent-native-wrapper-consumer-") as temporary:
        work = Path(temporary)
        csharp_consumer = work / "csharp-consumer"
        rust_consumer = work / "rust-consumer"
        dart_consumer = work / "dart-consumer"
        shutil.copytree(
            repository / "codex-agent-bindings/csharp/samples/CodexAgent.Consumer",
            csharp_consumer,
            ignore=shutil.ignore_patterns("bin", "obj"),
        )
        shutil.copytree(
            repository / "codex-agent-bindings/rust/consumer",
            rust_consumer,
            ignore=shutil.ignore_patterns("target"),
        )
        shutil.copytree(
            repository / "codex-agent-bindings/dart/consumer",
            dart_consumer,
            ignore=shutil.ignore_patterns(".dart_tool"),
        )
        set_consumer_sdk_version(csharp_consumer, rust_consumer, dart_consumer, sdk_version)

        venv = work / "python-venv"
        run(sys.executable, "-m", "venv", venv, cwd=repository)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(python, "-m", "pip", "install", "--no-deps", "--no-index", selected["python"], cwd=work)
        python_smoke = repository / "codex-agent-bindings/python/consumer/host_smoke.py"
        python_example = repository / "codex-agent-bindings/python/consumer/lifecycle_example.py"
        run(python, "-c", "import runpy,sys; runpy.run_path(sys.argv[1])", python_example, cwd=work)
        native_name = Path(HOSTS[classifier][4]).name
        python_library = require_matching_native(
            venv, f"**/codex_agent/native/{classifier}/{native_name}", sdk_library, "Python",
        )
        require_matching_proofs(python_library.parent, sdks / classifier, "Python")
        run(python, python_smoke, python_library, cwd=work)
        run_expect_failure(python, python_smoke, cwd=work)
        run_expect_failure(python, python_smoke, python_library, python_library, cwd=work)

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
        run("dotnet", "build", csharp_consumer / "CodexAgent.Consumer.csproj", "--configuration", "Release",
            "--no-restore", cwd=work)
        csharp_library = require_matching_native(
            cache,
            f"**/runtimes/{PACKAGE_CLASSIFIERS[classifier]}/native/{native_name}",
            sdk_library,
            "C#",
        )
        require_matching_proofs(csharp_library.parent, sdks / classifier, "C#")
        run("dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj", "--configuration",
            "Release", "--no-build", "--", csharp_library, "release-only", cwd=work)
        run_expect_failure(
            "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
            "--configuration", "Release", "--no-build", "--", cwd=work,
        )
        run_expect_failure(
            "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
            "--configuration", "Release", "--no-build", "--", csharp_library, "release-only", "extra",
            cwd=work,
        )

        rust_root = work / "rust-package"
        safe_extract_tar(selected["rust"], rust_root)
        rust_package = require_one(rust_root, "codex-agent-*/Cargo.toml").parent
        cargo_toml = rust_consumer / "Cargo.toml"
        cargo_toml.write_text(
            cargo_toml.read_text(encoding="utf-8").replace('path = ".."', f'path = "{rust_package.as_posix()}"'),
            encoding="utf-8",
        )
        cargo_env = os.environ | {"CARGO_TARGET_DIR": str(work / "rust-target")}
        run("cargo", "fetch", "--manifest-path", cargo_toml, "--locked", cwd=work, env=cargo_env)
        run("cargo", "metadata", "--manifest-path", cargo_toml, "--locked", "--offline", "--no-deps",
            cwd=work, env=cargo_env)
        run("cargo", "build", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
            "--bins", cwd=work, env=cargo_env)
        rust_library = require_matching_native(
            rust_package,
            f"native/{PACKAGE_CLASSIFIERS[classifier]}/{native_name}",
            sdk_library,
            "Rust",
        )
        require_matching_proofs(rust_library.parent, sdks / classifier, "Rust")
        rust_command = (
            "cargo", "run", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
            "--bin", "codex-agent-rust-host-smoke", "--",
        )
        run(*rust_command, rust_library, cwd=work, env=cargo_env)
        run_expect_failure(*rust_command, cwd=work, env=cargo_env)
        run_expect_failure(*rust_command, rust_library, rust_library, cwd=work, env=cargo_env)
        if platform.system() in {"Darwin", "Linux"}:
            fixture = work / ("libcodex_agent_rust_lifecycle.dylib" if platform.system() == "Darwin"
                              else "libcodex_agent_rust_lifecycle.so")
            compiler = shlex.split(os.environ.get("CC", "cc"))
            flags = ["-std=gnu11", "-fPIC", "-pthread", "-Wall", "-Wextra", "-Werror"]
            flags += ["-dynamiclib" if platform.system() == "Darwin" else "-shared"]
            run(
                *compiler,
                *flags,
                repository / "codex-agent-bindings/rust/tests/fixtures/mock_codex_agent.c",
                "-o", fixture,
                cwd=work,
            )
            run(
                "cargo", "run", "--manifest-path", cargo_toml, "--release", "--locked", "--offline",
                "--bin", "codex-agent-rust-lifecycle-smoke", "--", fixture,
                cwd=work, env=cargo_env,
            )

        cpp_root = work / "cpp-package"
        safe_extract_zip(selected["cpp"], cpp_root)
        cpp_prefix = next(path for path in cpp_root.iterdir() if path.is_dir())
        cpp_build = work / "cpp-consumer-build"
        run("cmake", "-S", repository / "codex-agent-bindings/cpp/consumer", "-B", cpp_build,
            f"-DCMAKE_PREFIX_PATH={cpp_prefix}", "-DCMAKE_BUILD_TYPE=Release", cwd=work)
        run("cmake", "--build", cpp_build, "--config", "Release", "--target", "codex_agent_host_smoke",
            cwd=work)
        run("cmake", "--build", cpp_build, "--config", "Release", "--target",
            "codex_agent_lifecycle_example", cwd=work)
        cpp_library = require_matching_native(
            cpp_prefix, HOSTS[classifier][4], sdk_library, "C++",
        )
        require_matching_proofs(
            cpp_prefix / "share/CodexAgent/native", sdks / classifier, "C++",
        )
        cpp_env = os.environ.copy()
        if os.name == "nt":
            cpp_env["PATH"] = f"{cpp_library.parent}{os.pathsep}{cpp_env.get('PATH', '')}"
        run(executable(cpp_build, "codex_agent_host_smoke"), cpp_library, cwd=work, env=cpp_env)
        run(executable(cpp_build, "codex_agent_lifecycle_example"), cwd=work, env=cpp_env)
        run_expect_failure(executable(cpp_build, "codex_agent_host_smoke"), cwd=work, env=cpp_env)
        run_expect_failure(
            executable(cpp_build, "codex_agent_host_smoke"), cpp_library, cpp_library,
            cwd=work, env=cpp_env,
        )

        dart_root = work / "dart-package"
        safe_extract_tar(selected["dart"], dart_root)
        dart_package = require_one(dart_root, "codex_agent-*/pubspec.yaml").parent
        set_dart_consumer_path(dart_consumer, dart_package)
        run("dart", "pub", "get", "--enforce-lockfile", cwd=dart_consumer)
        dart_library = require_matching_native(
            dart_package,
            f"lib/src/native/{classifier}/{native_name}",
            sdk_library,
            "Dart",
        )
        require_matching_proofs(dart_library.parent, sdks / classifier, "Dart")
        run("dart", "run", "bin/host_smoke.dart", dart_library, cwd=dart_consumer)
        run_expect_failure("dart", "run", "bin/host_smoke.dart", cwd=dart_consumer)
        run_expect_failure(
            "dart", "run", "bin/host_smoke.dart", dart_library, dart_library, cwd=dart_consumer,
        )

        wrong_library = work / f"wrong-{native_name}"
        wrong_library.write_bytes(b"not a native library")
        run_expect_failure(python, python_smoke, wrong_library, cwd=work)
        run_expect_failure(
            "dotnet", "run", "--project", csharp_consumer / "CodexAgent.Consumer.csproj",
            "--configuration", "Release", "--no-build", "--", wrong_library, "release-only", cwd=work,
        )
        run_expect_failure(*rust_command, wrong_library, cwd=work, env=cargo_env)
        run_expect_failure(
            executable(cpp_build, "codex_agent_host_smoke"), wrong_library, cwd=work, env=cpp_env,
        )
        run_expect_failure("dart", "run", "bin/host_smoke.dart", wrong_library, cwd=dart_consumer)

    evidence_arguments: list[str] = []
    artifact_arguments: list[str] = []
    for language, package in selected.items():
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

    compiler = "cl" if os.name == "nt" else os.environ.get("CXX", "c++")
    compiler_version = (
        version(compiler, allowed_return_codes=(0, 2))
        if os.name == "nt"
        else version(compiler, "--version")
    )
    tools = {
        "python": version(sys.executable, "--version"),
        "dotnet": version("dotnet", "--version"),
        "cargo": version("cargo", "--version"),
        "rustc": version("rustc", "-vV"),
        "cmake": version("cmake", "--version").split(";", 1)[0],
        "cppCompiler": compiler_version,
        "dart": version("dart", "--version"),
    }
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
    consumer = commands.add_parser("consume")
    consumer.add_argument("--repository", type=Path, required=True)
    consumer.add_argument("--packages", type=Path, required=True)
    consumer.add_argument("--sdks", type=Path, required=True)
    consumer.add_argument("--plan", type=Path, required=True)
    consumer.add_argument("--output", type=Path, required=True)
    consumer.add_argument("--sdk-version-file", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    output = arguments.output.resolve()
    invalidate_output(output)
    sdk_version = require_sdk_version_file(arguments.sdk_version_file.resolve())
    if arguments.command == "package":
        package_all(arguments.sources.resolve(), arguments.sdks.resolve(), output, sdk_version)
    else:
        consume(arguments.repository.resolve(), arguments.packages.resolve(), arguments.sdks.resolve(),
                arguments.plan.resolve(), output, sdk_version)


if __name__ == "__main__":
    main()
