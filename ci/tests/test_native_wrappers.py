from __future__ import annotations

import ast
import hashlib
import io
import re
import shutil
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

from native_wrappers import (  # noqa: E402
    DART_RELEASE_EXCLUDES,
    HOSTS,
    LANGUAGES,
    PACKAGE_CLASSIFIERS,
    PYTHON_TAGS,
    deterministic_tar,
    deterministic_zip,
    files,
    host_classifier,
    normalize_nupkg,
    normalize_python_sdist,
    main,
    package_all,
    require_embedded_package_versions,
    require_prepared_native_assets,
    require_sdk_version_file,
    require_source_sdk_version,
    safe_extract_tar,
    safe_extract_zip,
    select_packages,
    set_consumer_sdk_version,
    set_dart_consumer_path,
    set_source_sdk_version,
    stage_dart_release,
)


def write_tar_file(path: Path, name: str, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as archive:
        payload = contents.encode()
        member = tarfile.TarInfo(name)
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))


def write_zip_file(path: Path, name: str, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(name, contents)


class NativeWrapperReleaseTest(unittest.TestCase):
    def test_python_sdist_normalization_removes_archive_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = []
            for index, timestamp in enumerate((1_000_000_000, 2_000_000_000)):
                archive = root / f"sdist-{index}.tar.gz"
                with archive.open("wb") as raw:
                    with tarfile.open(fileobj=raw, mode="w:gz") as output:
                        member = tarfile.TarInfo("codex_agent-0.2.0/value")
                        member.size = 7
                        member.mtime = timestamp
                        member.uid = member.gid = index + 1
                        output.addfile(member, io.BytesIO(b"payload"))
                normalize_python_sdist(archive, root / f"work-{index}")
                archives.append(archive.read_bytes())
            self.assertEqual(archives[0], archives[1])

    def test_nupkg_normalization_removes_opc_identity_and_zip_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archives = []
            core = b"<coreProperties><version>0.2.0</version></coreProperties>"
            for index, identity in enumerate(("1" * 32, "2" * 32)):
                archive = root / f"package-{index}.nupkg"
                relationship = (
                    '<Relationships><Relationship Type="http://schemas.openxmlformats.org/package/2006/'
                    f'relationships/metadata/core-properties" Target="/package/services/metadata/core-properties/'
                    f'{identity}.psmdcp" Id="R{identity[:16]}" /></Relationships>'
                )
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr("_rels/.rels", relationship)
                    output.writestr(f"package/services/metadata/core-properties/{identity}.psmdcp", core)
                    output.writestr("lib/net8.0/CodexAgent.dll", b"assembly")
                normalize_nupkg(archive, root / f"work-{index}")
                archives.append(archive.read_bytes())
            self.assertEqual(archives[0], archives[1])

    def test_normalizers_reject_malformed_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdist = root / "multiple-roots.tar.gz"
            with tarfile.open(sdist, "w:gz") as output:
                for name in ("first/value", "second/value"):
                    member = tarfile.TarInfo(name)
                    member.size = 7
                    output.addfile(member, io.BytesIO(b"payload"))
            with self.assertRaisesRegex(ValueError, "one package root"):
                normalize_python_sdist(sdist, root / "sdist-work")

            for count in (0, 2):
                package = root / f"relationships-{count}.nupkg"
                relationship = (
                    '<Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/'
                    'metadata/core-properties" Target="/package/services/metadata/core-properties/core.psmdcp" '
                    'Id="RCORE" />'
                )
                with zipfile.ZipFile(package, "w") as output:
                    output.writestr("_rels/.rels", f"<Relationships>{relationship * count}</Relationships>")
                    output.writestr("package/services/metadata/core-properties/core.psmdcp", b"core")
                with self.assertRaisesRegex(ValueError, "one core-properties relationship"):
                    normalize_nupkg(package, root / f"nupkg-work-{count}")

            unsafe = root / "unsafe.nupkg"
            with zipfile.ZipFile(unsafe, "w") as output:
                output.writestr("../escape", b"escape")
            with self.assertRaisesRegex(ValueError, "unsafe"):
                normalize_nupkg(unsafe, root / "unsafe-work")

    def test_package_reproducibility_failure_names_every_differing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = 0

            def package_once(*_arguments: object) -> None:
                nonlocal calls
                output = Path(_arguments[2])
                output.mkdir(parents=True)
                (output / "changed").write_text(str(calls), encoding="utf-8")
                if calls:
                    (output / "second-only").write_text("extra", encoding="utf-8")
                else:
                    (output / "first-only").write_text("extra", encoding="utf-8")
                calls += 1

            with patch("native_wrappers.package_once", side_effect=package_once):
                with self.assertRaisesRegex(ValueError, "(?s)changed.*second-only") as failure:
                    package_all(root, root, root / "packages", "0.2.0")
            self.assertIn("first=missing", str(failure.exception))
            self.assertIn("second=missing", str(failure.exception))
            self.assertFalse((root / "packages").exists())

    def test_failed_or_invalid_package_run_removes_stale_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "packages"
            output.mkdir()
            (output / "stale").write_text("stale", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SDK version"):
                package_all(root, root, output, "invalid")
            self.assertFalse(output.exists())

            output.mkdir()
            (output / "stale").write_text("stale", encoding="utf-8")
            version_file = root / "sdk.txt"
            version_file.write_text("invalid\n", encoding="utf-8")
            with patch.object(
                sys,
                "argv",
                [
                    "native_wrappers.py", "package", "--sources", str(root), "--sdks", str(root),
                    "--output", str(output), "--sdk-version-file", str(version_file),
                ],
            ), self.assertRaisesRegex(ValueError, "SDK version"):
                main()
            self.assertFalse(output.exists())

    def test_package_sources_must_match_the_declared_sdk_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifests = {
                "python/pyproject.toml": '[project]\nname = "codex-agent"\nversion = "0.2.0"\n',
                "csharp/src/CodexAgent/CodexAgent.csproj": (
                    "<Project><PropertyGroup><VersionPrefix>0.2.0</VersionPrefix>"
                    "</PropertyGroup></Project>\n"
                ),
                "rust/Cargo.toml": '[package]\nname = "codex-agent"\nversion = "0.2.0"\n',
                "rust/Cargo.lock": 'name = "codex-agent"\nversion = "0.2.0"\n',
                "cpp/CMakeLists.txt": "project(CodexAgent VERSION 0.2.0 LANGUAGES CXX)\n",
                "dart/pubspec.yaml": "name: codex_agent\nversion: 0.2.0\n",
            }
            for relative, contents in manifests.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")

            require_source_sdk_version(root, "0.2.0")
            with self.assertRaisesRegex(ValueError, "do not match 0.2.1"):
                require_source_sdk_version(root, "0.2.1")
            with self.assertRaisesRegex(ValueError, "SDK version"):
                require_source_sdk_version(root, "v0.2.0")

            set_source_sdk_version(root, "3.4.5")
            require_source_sdk_version(root, "3.4.5")
            self.assertIn('version = "3.4.5"', (root / "rust/Cargo.lock").read_text(encoding="utf-8"))

            with (root / "cpp/CMakeLists.txt").open("a", encoding="utf-8") as manifest:
                manifest.write("project(CodexAgent VERSION 3.4.5 LANGUAGES CXX)\n")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                set_source_sdk_version(root, "4.5.6")

            manifest = root / "python/pyproject.toml"
            manifest.unlink()
            with self.assertRaisesRegex(ValueError, "missing or symbolic"):
                require_source_sdk_version(root, "3.4.5")
            manifest.symlink_to(root / "rust/Cargo.toml")
            with self.assertRaisesRegex(ValueError, "missing or symbolic"):
                require_source_sdk_version(root, "3.4.5")

            version_file = root / "sdk.txt"
            version_file.write_bytes(b"0.2.0\n")
            self.assertEqual("0.2.0", require_sdk_version_file(version_file))
            version_file.write_bytes(b"0.2.0\n\n")
            with self.assertRaisesRegex(ValueError, "one final LF"):
                require_sdk_version_file(version_file)

    def test_prepared_native_assets_must_exactly_match_the_declared_sdks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources = root / "sources"
            sdks = root / "sdks"
            language_roots: dict[tuple[str, str], Path] = {}
            sdks.mkdir()
            (sdks / "codex-agent-native-wrapper-sdks.json").write_text("{}\n", encoding="utf-8")
            for metadata in ("csharp/native/README.md", "dart/lib/src/native/README.md"):
                path = sources / metadata
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("prepared native assets\n", encoding="utf-8")
            for classifier, host in HOSTS.items():
                sdk = sdks / classifier
                library = sdk / host[4]
                library.parent.mkdir(parents=True)
                library.write_bytes(f"library:{classifier}".encode())
                for proof in ("manifest", "evidence"):
                    (sdk / f"codex-agent-c-abi-{proof}.json").write_text(
                        f"{proof}:{classifier}\n", encoding="utf-8"
                    )
                roots = {
                    "Python": sources / f"python/src/codex_agent/native/{classifier}",
                    "C#": sources / f"csharp/native/{PACKAGE_CLASSIFIERS[classifier]}",
                    "Rust": sources / f"rust/native/{PACKAGE_CLASSIFIERS[classifier]}",
                    "Dart": sources / f"dart/lib/src/native/{classifier}",
                }
                for language, destination in roots.items():
                    destination.mkdir(parents=True)
                    shutil.copy2(library, destination / library.name)
                    for proof in ("manifest", "evidence"):
                        shutil.copy2(
                            sdk / f"codex-agent-c-abi-{proof}.json",
                            destination / f"codex-agent-c-abi-{proof}.json",
                        )
                    language_roots[(language, classifier)] = destination
                shutil.copytree(sdk, sources / f"cpp/native/{classifier}")
                language_roots[("C++", classifier)] = sources / f"cpp/native/{classifier}"

            require_prepared_native_assets(sources, sdks)
            for (language, classifier), destination in language_roots.items():
                target = next(path for path in destination.rglob("*") if path.is_file())
                original = target.read_bytes()
                target.write_bytes(b"tampered")
                with self.subTest(language=language, classifier=classifier), self.assertRaisesRegex(
                    ValueError, re.escape(language),
                ):
                    require_prepared_native_assets(sources, sdks)
                target.write_bytes(original)

            extra = sources / "python/src/codex_agent/native/unexpected"
            extra.mkdir()
            with self.assertRaisesRegex(ValueError, "classifier inventory"):
                require_prepared_native_assets(sources, sdks)
            extra.rmdir()

            missing = sources / "rust/native/linux-x64"
            hidden = sources / "rust/native/linux-x64-hidden"
            missing.rename(hidden)
            with self.assertRaisesRegex(ValueError, "classifier inventory"):
                require_prepared_native_assets(sources, sdks)
            hidden.rename(missing)

            real = sources / "dart/lib/src/native/linux-x64"
            hidden = sources / "dart/lib/src/native/linux-x64-real"
            real.rename(hidden)
            real.symlink_to(hidden, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "classifier inventory|symbolic"):
                require_prepared_native_assets(sources, sdks)
            real.unlink()
            hidden.rename(real)

            (sdks / "unexpected").mkdir()
            with self.assertRaisesRegex(ValueError, "SDK root inventory"):
                require_prepared_native_assets(sources, sdks)

    def test_package_selection_rejects_mixed_sdk_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary)
            version = "3.4.5"
            expected = {
                "python": {
                    f"codex_agent-{version}.tar.gz",
                    *(f"codex_agent-{version}-py3-none-{tag}.whl" for tag in PYTHON_TAGS.values()),
                    "codex-agent-python-package-toolchain.tsv",
                },
                "csharp": {f"CodexAgent.{version}.nupkg", "codex-agent-csharp-package-toolchain.tsv"},
                "rust": {f"codex-agent-{version}.crate", "codex-agent-rust-package-toolchain.tsv"},
                "cpp": {
                    *(f"codex-agent-cpp-{version}-{classifier}.zip" for classifier in HOSTS),
                    "codex-agent-cpp-package-toolchain.tsv",
                },
                "dart": {f"codex-agent-dart-{version}.tar.gz", "codex-agent-dart-package-toolchain.tsv"},
            }
            for language, names in expected.items():
                directory = packages / language
                directory.mkdir()
                for name in names:
                    (directory / name).write_bytes(b"package")

            selected = select_packages(packages, "linux-x64", version)
            self.assertEqual(f"codex-agent-{version}.crate", selected["rust"].name)
            (packages / "rust/codex-agent-0.2.0.crate").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "Rust|rust"):
                select_packages(packages, "linux-x64", version)

    def test_package_artifacts_embed_the_declared_sdk_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            packages = Path(temporary)
            version = "3.4.5"
            python = packages / "python"
            for tag in PYTHON_TAGS.values():
                write_zip_file(
                    python / f"codex_agent-{version}-py3-none-{tag}.whl",
                    f"codex_agent-{version}.dist-info/METADATA",
                    f"Metadata-Version: 2.1\nVersion: {version}\n",
                )
            write_tar_file(
                python / f"codex_agent-{version}.tar.gz",
                f"codex_agent-{version}/PKG-INFO",
                f"Metadata-Version: 2.1\nVersion: {version}\n",
            )
            write_zip_file(
                packages / f"csharp/CodexAgent.{version}.nupkg",
                "CodexAgent.nuspec",
                f"<package><metadata><version>{version}</version></metadata></package>",
            )
            write_tar_file(
                packages / f"rust/codex-agent-{version}.crate",
                f"codex-agent-{version}/Cargo.toml",
                f'[package]\nname = "codex-agent"\nversion = "{version}"\n',
            )
            for classifier in HOSTS:
                write_zip_file(
                    packages / f"cpp/codex-agent-cpp-{version}-{classifier}.zip",
                    f"codex-agent-cpp-{version}-{classifier}/lib/cmake/CodexAgent/"
                    "CodexAgentConfigVersion.cmake",
                    f'set(PACKAGE_VERSION "{version}")\n',
                )
            write_tar_file(
                packages / f"dart/codex-agent-dart-{version}.tar.gz",
                f"codex_agent-{version}/pubspec.yaml",
                f"name: codex_agent\nversion: {version}\n",
            )
            for language in LANGUAGES:
                toolchain = packages / language / f"codex-agent-{language}-package-toolchain.tsv"
                toolchain.parent.mkdir(parents=True, exist_ok=True)
                toolchain.write_text("tool\tversion\nfixture\t1\n", encoding="utf-8")

            require_embedded_package_versions(packages, version)

            write_tar_file(
                python / f"codex_agent-{version}.tar.gz",
                f"codex_agent-{version}/PKG-INFO",
                "Metadata-Version: 2.1\nVersion: 0.2.0\n",
            )
            with self.assertRaisesRegex(ValueError, "Python sdist"):
                require_embedded_package_versions(packages, version)
            write_tar_file(
                python / f"codex_agent-{version}.tar.gz",
                f"codex_agent-{version}/PKG-INFO",
                f"Metadata-Version: 2.1\nVersion: {version}\n",
            )

            classifier = next(iter(HOSTS))
            write_zip_file(
                packages / f"cpp/codex-agent-cpp-{version}-{classifier}.zip",
                f"codex-agent-cpp-{version}-{classifier}/lib/cmake/CodexAgent/"
                "CodexAgentConfigVersion.cmake",
                'set(PACKAGE_VERSION "0.2.0")\n',
            )
            with self.assertRaisesRegex(ValueError, r"C\+\+ package"):
                require_embedded_package_versions(packages, version)

    def test_installed_consumer_locks_follow_the_declared_sdk_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csharp = root / "csharp"
            rust = root / "rust"
            dart = root / "dart"
            for directory in (csharp, rust, dart):
                directory.mkdir()
            (csharp / "CodexAgent.Consumer.csproj").write_text(
                '<PackageReference Include="CodexAgent" Version="0.2.0" />\n', encoding="utf-8"
            )
            (rust / "Cargo.lock").write_text(
                'name = "codex-agent"\nversion = "0.2.0"\n', encoding="utf-8"
            )
            (dart / "pubspec.lock").write_text(
                "  codex_agent:\n"
                '    dependency: "direct main"\n'
                "    description:\n"
                '      path: ".."\n'
                "      relative: true\n"
                "    source: path\n"
                '    version: "0.2.0"\n',
                encoding="utf-8",
            )
            (dart / "pubspec.yaml").write_text(
                "dependencies:\n  codex_agent:\n    path: ..\n",
                encoding="utf-8",
            )

            set_consumer_sdk_version(csharp, rust, dart, "3.4.5")
            package = root / "dart-package/codex_agent-3.4.5"
            package.mkdir(parents=True)
            set_dart_consumer_path(dart, package)
            for path in (
                csharp / "CodexAgent.Consumer.csproj",
                rust / "Cargo.lock",
                dart / "pubspec.lock",
            ):
                self.assertIn("3.4.5", path.read_text(encoding="utf-8"))
                self.assertNotIn("0.2.0", path.read_text(encoding="utf-8"))
            relative = Path("../dart-package/codex_agent-3.4.5").as_posix()
            self.assertIn(f"    path: {relative}", (dart / "pubspec.yaml").read_text(encoding="utf-8"))
            self.assertIn(f'      path: "{relative}"', (dart / "pubspec.lock").read_text(encoding="utf-8"))

    def test_dart_release_excludes_repository_tests_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "lib").mkdir()
            (source / "lib/codex_agent.dart").write_text("library codex_agent;\n", encoding="utf-8")
            for relative in DART_RELEASE_EXCLUDES:
                path = source / relative
                if relative in {".dart_tool", "consumer", "parity", "test", "tool"}:
                    path.mkdir()
                    (path / "payload").write_text("excluded\n", encoding="utf-8")
                else:
                    path.write_text("excluded\n", encoding="utf-8")

            destination = root / "release"
            stage_dart_release(source, destination)

            self.assertEqual(
                ["lib/codex_agent.dart"],
                [path.relative_to(destination).as_posix() for path in files(destination)],
            )

    def test_release_inventory_is_exact(self) -> None:
        packaging = ast.parse((CI_ROOT / "native_wrappers.py").read_text(encoding="utf-8"))
        csharp_project = ET.parse(
            CI_ROOT.parent
            / "codex-agent-bindings/csharp/src/CodexAgent/CodexAgent.csproj"
        ).getroot()
        functions = {node.name: node for node in packaging.body if isinstance(node, ast.FunctionDef)}
        calls = {
            name: {
                node.func.id
                for node in ast.walk(function)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            for name, function in functions.items()
        }
        self.assertIn("normalize_python_sdist", calls["package_python"])
        self.assertIn("normalize_nupkg", calls["package_once"])
        self.assertIn("-p:PathMap=", ast.unparse(functions["package_once"]))
        self.assertEqual(
            [
                (f"../../native/**/codex-agent-c-abi-{proof}.json",
                 "runtimes/%(RecursiveDir)native/%(Filename)%(Extension)")
                for proof in ("manifest", "evidence")
            ],
            [
                (item.get("Include"), item.get("PackagePath"))
                for item in csharp_project.findall(".//None")
                if "codex-agent-c-abi-" in item.get("Include", "")
            ],
        )
        self.assertEqual(
            ["macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"],
            list(HOSTS),
        )
        self.assertEqual(("python", "csharp", "rust", "cpp", "dart"), LANGUAGES)
        self.assertEqual(
            {
                "macos-arm64": "lib/libcodex_agent.dylib",
                "macos-x64": "lib/libcodex_agent.dylib",
                "linux-arm64": "lib/libcodex_agent.so",
                "linux-x64": "lib/libcodex_agent.so",
                "windows-x64": "bin/codex_agent.dll",
            },
            {classifier: value[4] for classifier, value in HOSTS.items()},
        )

    def test_host_classifier_is_exact_and_fail_closed(self) -> None:
        for classifier, (system, architectures, *_rest) in HOSTS.items():
            with patch("platform.system", return_value=system), patch(
                "platform.machine", return_value=next(iter(architectures))
            ):
                self.assertEqual(classifier, host_classifier())
        with patch("platform.system", return_value="Linux"), patch(
            "platform.machine", return_value="riscv64"
        ):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                host_classifier()

    def test_release_archives_are_reproducible_and_safely_extractable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested/payload").write_bytes(b"payload")
            digests: list[tuple[str, str]] = []
            for index in range(2):
                zip_path = root / f"package-{index}.zip"
                tar_path = root / f"package-{index}.tar.gz"
                deterministic_zip(source, zip_path, "package")
                deterministic_tar(source, tar_path, "package")
                digests.append((
                    hashlib.sha256(zip_path.read_bytes()).hexdigest(),
                    hashlib.sha256(tar_path.read_bytes()).hexdigest(),
                ))
                safe_extract_zip(zip_path, root / f"zip-{index}")
                safe_extract_tar(tar_path, root / f"tar-{index}")
                self.assertEqual(b"payload", (root / f"zip-{index}/package/nested/payload").read_bytes())
                self.assertEqual(b"payload", (root / f"tar-{index}/package/nested/payload").read_bytes())
            self.assertEqual(digests[0], digests[1])

    def test_extractors_reject_cross_platform_escape_and_duplicate_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, name in enumerate(("../escape", "..\\escape", "C:\\escape")):
                archive = root / f"malicious-{index}.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(name, b"escape")
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    safe_extract_zip(archive, root / f"zip-output-{index}")
            duplicate_zip = root / "duplicate.zip"
            with zipfile.ZipFile(duplicate_zip, "w") as output:
                output.writestr("package/value", b"first")
                output.writestr("package/value", b"second")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                safe_extract_zip(duplicate_zip, root / "duplicate-zip-output")

            for index, name in enumerate(("../escape", "..\\escape", "C:\\escape")):
                archive = root / f"malicious-{index}.tar.gz"
                with tarfile.open(archive, "w:gz") as output:
                    member = tarfile.TarInfo(name)
                    member.size = 6
                    output.addfile(member, io.BytesIO(b"escape"))
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    safe_extract_tar(archive, root / f"tar-output-{index}")
            duplicate_tar = root / "duplicate.tar.gz"
            with tarfile.open(duplicate_tar, "w:gz") as output:
                for payload in (b"first", b"second"):
                    member = tarfile.TarInfo("package/value")
                    member.size = len(payload)
                    output.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                safe_extract_tar(duplicate_tar, root / "duplicate-tar-output")


if __name__ == "__main__":
    unittest.main()
