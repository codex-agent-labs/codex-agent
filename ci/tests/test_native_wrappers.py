from __future__ import annotations

import ast
from contextlib import ExitStack
import hashlib
import io
import re
import shutil
import sys
import tarfile
import tempfile
import tomllib
import unittest
import venv
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT.parent))
sys.path.insert(0, str(CI_ROOT))

from ci.native_wrappers import verify_native_wrapper_sdk_packages  # noqa: E402
from native_wrappers import (  # noqa: E402
    DART_RELEASE_EXCLUDES,
    HOSTS,
    LANGUAGES,
    PACKAGE_CLASSIFIERS,
    PYTHON_TAGS,
    _consume,
    consume,
    consume_language,
    deterministic_tar,
    deterministic_zip,
    files,
    host_classifier,
    normalize_nupkg,
    normalize_python_sdist,
    package_python,
    reject_raw_c_abi_proofs,
    main,
    package_all,
    parse_args,
    require_embedded_native_assets,
    require_embedded_package_versions,
    require_embedded_sdk_compatibility,
    require_matching_compatibility,
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
    write_package_toolchains,
)
from products.inventory import canonical_json_bytes, load_canonical_json_bytes  # noqa: E402


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
    def test_cpp_source_package_records_packager_not_host_compiler(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cpp").mkdir()
            with patch("native_wrappers.version", return_value="cmake version fixture") as probe:
                write_package_toolchains(root, ("cpp",))
            probe.assert_called_once_with("cmake", "--version")
            self.assertEqual(
                (root / "cpp/codex-agent-cpp-package-toolchain.tsv").read_text(),
                "tool\tversion\ncmake\tcmake version fixture\n",
            )

    @unittest.skipIf(sys.platform == "win32", "stdlib venv symlink fixture is POSIX-specific")
    def test_installed_python_proof_scan_is_scoped_below_venv_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = Path(temporary) / "venv"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
            self.assertTrue(any(path.is_symlink() for path in (environment / "bin").iterdir()))

            package = environment / "synthetic/site-packages/codex_agent"
            python_library = package / "native/linux-x64/libcodex_agent.so"
            python_library.parent.mkdir(parents=True)
            python_library.write_bytes(b"library")
            self.assertEqual(package.resolve(), python_library.resolve().parents[2])
            reject_raw_c_abi_proofs(python_library.resolve().parents[2], "Python")

            forbidden = package / "codex-agent-c-abi-manifest.json"
            forbidden.write_bytes(b"forbidden")
            with self.assertRaisesRegex(ValueError, "forbidden raw C ABI proof"):
                reject_raw_c_abi_proofs(python_library.resolve().parents[2], "Python")
            forbidden.unlink()

            package_symlink = package / "native-link"
            package_symlink.symlink_to(python_library)
            with self.assertRaisesRegex(ValueError, "symbolic package input"):
                reject_raw_c_abi_proofs(python_library.resolve().parents[2], "Python")

    def test_installed_compatibility_must_exactly_match_the_staged_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "sdk-compatibility.json"
            expected.write_bytes(b"canonical\n")
            installed = root / "package/native/sdk-compatibility.json"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(expected.read_bytes())
            require_matching_compatibility(
                root / "package", "native/sdk-compatibility.json", expected, "fixture",
            )
            installed.write_bytes(b"changed\n")
            with self.assertRaisesRegex(ValueError, "does not match"):
                require_matching_compatibility(
                    root / "package", "native/sdk-compatibility.json", expected, "fixture",
                )

    def test_python_wheels_retain_compatibility_and_only_the_selected_native_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            native = source / "src/codex_agent/native"
            native.mkdir(parents=True)
            (native / "sdk-compatibility.json").write_bytes(b"compatibility\n")
            for classifier in HOSTS:
                target = native / classifier
                target.mkdir()
                (target / Path(HOSTS[classifier][4]).name).write_bytes(classifier.encode())
            output = root / "output"
            output.mkdir()
            work = root / "work"
            work.mkdir()

            def fake_run(*command: str | Path, cwd: Path, env: dict[str, str]) -> None:
                if "build" in command:
                    deterministic_tar(
                        cwd, output / "codex_agent-0.2.0.tar.gz", "codex_agent-0.2.0",
                    )
                    return
                tag = str(command[command.index("--plat-name") + 1])
                classifier = next(key for key, value in PYTHON_TAGS.items() if value == tag)
                wheel_native = cwd / "src/codex_agent/native"
                self.assertEqual(
                    {classifier, "sdk-compatibility.json"},
                    {path.name for path in wheel_native.iterdir()},
                )
                deterministic_zip(
                    cwd / "src",
                    output / f"codex_agent-0.2.0-py3-none-{tag}.whl",
                    "",
                )

            with patch("native_wrappers.run", side_effect=fake_run):
                package_python(source, output, work)

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

    def test_package_run_builds_only_the_selected_language_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls: list[tuple[str, ...]] = []

            def package_once(*arguments: object) -> None:
                output = Path(arguments[2])
                languages = arguments[4]
                self.assertIsInstance(languages, tuple)
                calls.append(languages)
                language = languages[0]
                output.joinpath(language).mkdir(parents=True)
                output.joinpath(language, "package").write_text("same", encoding="utf-8")

            with patch("native_wrappers.package_once", side_effect=package_once):
                package_all(root, root, root / "packages", "0.2.0", ("rust",))

            self.assertEqual([("rust",), ("rust",)], calls)
            self.assertEqual(["rust/package"], [
                path.relative_to(root / "packages").as_posix()
                for path in files(root / "packages")
            ])

    def test_release_archives_contain_the_exact_shared_compatibility_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdks = root / "sdks"
            sdks.mkdir()
            compatibility = (
                CI_ROOT.parent / "codex-agent-bindings/csharp/native/sdk-compatibility.json"
            ).read_bytes()
            (sdks / "sdk-compatibility.json").write_bytes(compatibility)
            package = root / "packages/csharp/CodexAgent.0.2.0.nupkg"
            write_zip_file(package, "META-INF/codex-agent/sdk-compatibility.json", compatibility.decode())

            require_embedded_sdk_compatibility(root / "packages", sdks, "0.2.0", ("csharp",))
            with self.assertRaisesRegex(ValueError, "compatibility version mismatch"):
                require_embedded_sdk_compatibility(root / "packages", sdks, "0.2.1", ("csharp",))

            write_zip_file(package, "META-INF/codex-agent/sdk-compatibility.json", "changed")
            with self.assertRaisesRegex(ValueError, "exact SDK compatibility"):
                require_embedded_sdk_compatibility(root / "packages", sdks, "0.2.0", ("csharp",))

            write_zip_file(package, "wrong/location/sdk-compatibility.json", compatibility.decode())
            with self.assertRaisesRegex(ValueError, "exact SDK compatibility"):
                require_embedded_sdk_compatibility(root / "packages", sdks, "0.2.0", ("csharp",))

    def test_public_native_package_verifier_is_read_only_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packages = root / "packages"
            sdks = root / "sdks"
            version = "0.2.0"
            compatibility = (
                CI_ROOT.parent / "codex-agent-bindings/csharp/native/sdk-compatibility.json"
            ).read_bytes()
            (sdks / "sdk-compatibility.json").parent.mkdir(parents=True)
            (sdks / "sdk-compatibility.json").write_bytes(compatibility)
            libraries: dict[str, bytes] = {}
            for classifier in HOSTS:
                library = sdks / classifier / HOSTS[classifier][4]
                library.parent.mkdir(parents=True)
                libraries[classifier] = f"library:{classifier}".encode()
                library.write_bytes(libraries[classifier])
            toolchain = packages / "csharp/codex-agent-csharp-package-toolchain.tsv"
            toolchain.parent.mkdir(parents=True)
            toolchain.write_text("tool\tversion\nfixture\t1\n", encoding="utf-8")
            archive = packages / f"csharp/CodexAgent.{version}.nupkg"

            def write_package(
                *,
                package_version: str = version,
                embedded_compatibility: bytes = compatibility,
                duplicate_compatibility: bool = False,
                tampered_classifier: str | None = None,
            ) -> None:
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(
                        "CodexAgent.nuspec",
                        f"<package><metadata><version>{package_version}</version></metadata></package>",
                    )
                    output.writestr(
                        "META-INF/codex-agent/sdk-compatibility.json",
                        embedded_compatibility,
                    )
                    if duplicate_compatibility:
                        output.writestr("other/sdk-compatibility.json", embedded_compatibility)
                    for classifier, package_classifier in PACKAGE_CLASSIFIERS.items():
                        contents = b"tampered" if classifier == tampered_classifier else libraries[classifier]
                        output.writestr(
                            f"runtimes/{package_classifier}/native/{Path(HOSTS[classifier][4]).name}",
                            contents,
                        )

            def snapshot() -> list[tuple[str, str]]:
                return [
                    (path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest())
                    for path in files(root)
                ]

            write_package()
            before = snapshot()
            verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")
            self.assertEqual(before, snapshot())

            with self.assertRaisesRegex(ValueError, "unsupported native wrapper language"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "javascript")
            with self.assertRaisesRegex(ValueError, "SDK product version"):
                verify_native_wrapper_sdk_packages(packages, sdks, "invalid", "csharp")
            with self.assertRaisesRegex(ValueError, "compatibility version mismatch"):
                verify_native_wrapper_sdk_packages(packages, sdks, "0.2.1", "csharp")

            (sdks / "sdk-compatibility.json").write_bytes(b" " + compatibility)
            with self.assertRaisesRegex(ValueError, "canonical"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")
            (sdks / "sdk-compatibility.json").write_bytes(compatibility)

            write_package(duplicate_compatibility=True)
            with self.assertRaisesRegex(ValueError, "exact SDK compatibility"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")
            write_package(package_version="0.2.1")
            with self.assertRaisesRegex(ValueError, "embeds SDK version"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")
            write_package(tampered_classifier="linux-x64")
            with self.assertRaisesRegex(ValueError, "native library differs"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")
            archive.unlink()
            with self.assertRaisesRegex(ValueError, "has no release archive"):
                verify_native_wrapper_sdk_packages(packages, sdks, version, "csharp")

    def test_release_archive_native_assets_match_the_staged_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdks = root / "sdks"
            package = root / "packages/csharp/CodexAgent.0.2.0.nupkg"
            package.parent.mkdir(parents=True)
            with zipfile.ZipFile(package, "w") as archive:
                for classifier, package_classifier in PACKAGE_CLASSIFIERS.items():
                    sdk = sdks / classifier
                    library = sdk / HOSTS[classifier][4]
                    library.parent.mkdir(parents=True)
                    library.write_bytes(f"library:{classifier}".encode())
                    archive.writestr(
                        f"runtimes/{package_classifier}/native/{library.name}",
                        library.read_bytes(),
                    )

            require_embedded_native_assets(root / "packages", sdks, "0.2.0", ("csharp",))
            with zipfile.ZipFile(package) as source:
                entries = {name: source.read(name) for name in source.namelist()}
            for proof in ("manifest", "evidence"):
                name = f"codex-agent-c-abi-{proof}.json"
                entries[f"unrelated/{name}"] = b"forbidden"
                with zipfile.ZipFile(package, "w") as archive:
                    for entry, contents in entries.items():
                        archive.writestr(entry, contents)
                with self.assertRaisesRegex(ValueError, "forbidden raw C ABI proof"):
                    require_embedded_native_assets(root / "packages", sdks, "0.2.0", ("csharp",))
                del entries[f"unrelated/{name}"]
            entries["runtimes/osx-arm64/native/codex_agent.dll"] = b"extra-target"
            with zipfile.ZipFile(package, "w") as archive:
                for name, contents in entries.items():
                    archive.writestr(name, contents)
            with self.assertRaisesRegex(ValueError, "target inventory mismatch"):
                require_embedded_native_assets(root / "packages", sdks, "0.2.0", ("csharp",))
            del entries["runtimes/osx-arm64/native/codex_agent.dll"]
            entries["runtimes/linux-x64/native/libcodex_agent.so"] = b"tampered"
            with zipfile.ZipFile(package, "w") as archive:
                for name, contents in entries.items():
                    archive.writestr(name, contents)
            with self.assertRaisesRegex(ValueError, "native library differs"):
                require_embedded_native_assets(root / "packages", sdks, "0.2.0", ("csharp",))

    def test_each_non_csharp_archive_rejects_native_tampering_or_extra_files(self) -> None:
        def prepare_sdks(root: Path) -> Path:
            sdks = root / "sdks"
            (sdks / "sdk-compatibility.json").parent.mkdir(parents=True)
            (sdks / "sdk-compatibility.json").write_text("compatibility\n", encoding="utf-8")
            for classifier in HOSTS:
                sdk = sdks / classifier
                members = {
                    "include/codex_agent.h": f"header:{classifier}".encode(),
                    HOSTS[classifier][4]: f"library:{classifier}".encode(),
                    "LICENSE.txt": b"license\n",
                    "THIRD_PARTY_NOTICES.md": b"notices\n",
                    "codex-agent-c-abi-manifest.json": f"manifest:{classifier}".encode(),
                    "codex-agent-c-abi-evidence.json": f"evidence:{classifier}".encode(),
                }
                if classifier.startswith("linux-"):
                    members["lib/libcodex_agent.so.1"] = f"soname:{classifier}".encode()
                elif classifier == "windows-x64":
                    members["lib/libcodex_agent.dll.a"] = b"gnu-import"
                    members["lib/codex_agent.lib"] = b"msvc-import"
                for relative, contents in members.items():
                    path = sdk / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents)
            return sdks

        def copy_target(sdks: Path, classifier: str, destination: Path) -> None:
            destination.mkdir(parents=True, exist_ok=True)
            sdk = sdks / classifier
            relative = HOSTS[classifier][4]
            (destination / Path(relative).name).write_bytes((sdk / relative).read_bytes())

        def build_language(root: Path, language: str, sdks: Path) -> Path:
            packages = root / "packages"
            compatibility = (sdks / "sdk-compatibility.json").read_bytes()
            if language == "python":
                source = root / "python-sdist"
                native = source / "src/codex_agent/native"
                native.mkdir(parents=True, exist_ok=True)
                (native / "sdk-compatibility.json").write_bytes(compatibility)
                for classifier in HOSTS:
                    copy_target(sdks, classifier, native / classifier)
                deterministic_tar(
                    source, packages / "python/codex_agent-0.2.0.tar.gz", "codex_agent-0.2.0",
                )
                for classifier, tag in PYTHON_TAGS.items():
                    wheel = root / f"python-wheel-{classifier}"
                    native = wheel / "codex_agent/native"
                    native.mkdir(parents=True, exist_ok=True)
                    (native / "sdk-compatibility.json").write_bytes(compatibility)
                    copy_target(sdks, classifier, native / classifier)
                    deterministic_zip(
                        wheel,
                        packages / f"python/codex_agent-0.2.0-py3-none-{tag}.whl",
                        "",
                    )
                return source / "src/codex_agent/native/macos-arm64"
            if language == "rust":
                source = root / "rust"
                native = source / "native"
                native.mkdir(parents=True, exist_ok=True)
                (native / "sdk-compatibility.json").write_bytes(compatibility)
                for classifier, package_classifier in PACKAGE_CLASSIFIERS.items():
                    copy_target(sdks, classifier, native / package_classifier)
                deterministic_tar(
                    source, packages / "rust/codex-agent-0.2.0.crate", "codex-agent-0.2.0",
                )
                return native / "osx-arm64"
            if language == "dart":
                source = root / "dart"
                native = source / "lib/src/native"
                native.mkdir(parents=True, exist_ok=True)
                (native / "README.md").write_text("native\n", encoding="utf-8")
                (native / "sdk-compatibility.json").write_bytes(compatibility)
                for classifier in HOSTS:
                    copy_target(sdks, classifier, native / classifier)
                deterministic_tar(
                    source, packages / "dart/codex-agent-dart-0.2.0.tar.gz", "codex_agent-0.2.0",
                )
                return native / "macos-arm64"
            if language == "cpp":
                for classifier in HOSTS:
                    source = root / f"cpp-{classifier}"
                    sdk = sdks / classifier
                    for relative in (
                        "include/codex_agent.h",
                        HOSTS[classifier][4],
                        *(
                            ("lib/libcodex_agent.so.1",)
                            if classifier.startswith("linux-") else
                            ("lib/libcodex_agent.dll.a", "lib/codex_agent.lib")
                            if classifier == "windows-x64" else ()
                        ),
                    ):
                        target = source / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes((sdk / relative).read_bytes())
                    metadata = source / "share/CodexAgent/native"
                    metadata.mkdir(parents=True, exist_ok=True)
                    (metadata / "sdk-compatibility.json").write_bytes(compatibility)
                    legal = source / "share/doc/CodexAgent/LICENSE.txt"
                    legal.parent.mkdir(parents=True, exist_ok=True)
                    legal.write_bytes((sdk / "LICENSE.txt").read_bytes())
                    (legal.parent / "README.md").write_text("C++ wrapper\n", encoding="utf-8")
                    loader = source / "share/CodexAgent/loader"
                    loader.mkdir(parents=True, exist_ok=True)
                    (loader / "native_loader.cpp").write_text("// loader\n", encoding="utf-8")
                    (loader / "generate_native_dispatch.py").write_text("# generator\n", encoding="utf-8")
                    deterministic_zip(
                        source,
                        packages / f"cpp/codex-agent-cpp-0.2.0-{classifier}.zip",
                        f"codex-agent-cpp-0.2.0-{classifier}",
                    )
                return root / "cpp-linux-x64/lib/libcodex_agent.so.1"
            raise AssertionError(language)

        for language in ("python", "rust", "dart", "cpp"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                sdks = prepare_sdks(root)
                mutation = build_language(root, language, sdks)
                require_embedded_native_assets(root / "packages", sdks, "0.2.0", (language,))
                if language == "cpp":
                    forbidden = root / "cpp-macos-arm64/share/CodexAgent/native/codex-agent-c-abi-evidence.json"
                else:
                    forbidden = mutation / "codex-agent-c-abi-evidence.json"
                forbidden.write_bytes(b"forbidden")
                build_language(root, language, sdks)
                with self.assertRaisesRegex(ValueError, "forbidden raw C ABI proof"):
                    require_embedded_native_assets(root / "packages", sdks, "0.2.0", (language,))
                forbidden.unlink()
                mutation = build_language(root, language, sdks)
                if language == "cpp":
                    host_loader = root / "cpp-macos-arm64/lib/libCodexAgentLoader.a"
                    host_loader.write_bytes(b"unverified host-built loader")
                    build_language(root, language, sdks)
                    with self.assertRaisesRegex(ValueError, "native target inventory mismatch"):
                        require_embedded_native_assets(root / "packages", sdks, "0.2.0", (language,))
                    host_loader.unlink()
                    build_language(root, language, sdks)
                    for classifier, relative, pattern in (
                        ("macos-arm64", "include/codex_agent.h", "native artifact differs"),
                        ("windows-x64", "lib/codex_agent.lib", "native artifact differs"),
                        ("macos-x64", "share/doc/CodexAgent/LICENSE.txt", "legal artifact differs"),
                    ):
                        with self.subTest(language=language, classifier=classifier, relative=relative):
                            (root / f"cpp-{classifier}" / relative).write_bytes(b"tampered")
                            deterministic_zip(
                                root / f"cpp-{classifier}",
                                root / f"packages/cpp/codex-agent-cpp-0.2.0-{classifier}.zip",
                                f"codex-agent-cpp-0.2.0-{classifier}",
                            )
                            with self.assertRaisesRegex(ValueError, pattern):
                                require_embedded_native_assets(
                                    root / "packages", sdks, "0.2.0", (language,),
                                )
                            build_language(root, language, sdks)
                    mutation.write_bytes(b"tampered")
                    classifier = "linux-x64"
                    deterministic_zip(
                        root / f"cpp-{classifier}",
                        root / f"packages/cpp/codex-agent-cpp-0.2.0-{classifier}.zip",
                        f"codex-agent-cpp-0.2.0-{classifier}",
                    )
                    pattern = "native artifact differs"
                else:
                    (mutation / "extra-native.bin").write_bytes(b"extra")
                    build_language(root, language, sdks)
                    pattern = "target inventory mismatch"
                with self.assertRaisesRegex(ValueError, pattern):
                    require_embedded_native_assets(root / "packages", sdks, "0.2.0", (language,))

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

            cpp_manifest = root / "cpp/CMakeLists.txt"
            cpp_manifest.write_text("project(CodexAgent VERSION 3.4.5 LANGUAGES NONE)\n", encoding="utf-8")
            set_source_sdk_version(root, "3.4.6", ("cpp",))
            self.assertEqual(cpp_manifest.read_text(encoding="utf-8"), "project(CodexAgent VERSION 3.4.6 LANGUAGES NONE)\n")

            shutil.rmtree(root / "python")
            shutil.rmtree(root / "csharp")
            shutil.rmtree(root / "cpp")
            shutil.rmtree(root / "dart")
            set_source_sdk_version(root, "4.5.6", ("rust",))
            require_source_sdk_version(root, "4.5.6", ("rust",))

            for relative, contents in manifests.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents.replace("0.2.0", "3.4.5"), encoding="utf-8")
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
                for relative, contents in {
                    "include/codex_agent.h": f"header:{classifier}".encode(),
                    "LICENSE.txt": b"license\n",
                    "THIRD_PARTY_NOTICES.md": b"notices\n",
                }.items():
                    path = sdk / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents)
                if classifier.startswith("linux-"):
                    soname = sdk / "lib/libcodex_agent.so.1"
                    soname.parent.mkdir(parents=True, exist_ok=True)
                    soname.write_bytes(f"soname:{classifier}".encode())
                elif classifier == "windows-x64":
                    for relative, contents in {
                        "lib/libcodex_agent.dll.a": b"gnu-import",
                        "lib/codex_agent.lib": b"msvc-import",
                    }.items():
                        path = sdk / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(contents)
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
                    language_roots[(language, classifier)] = destination
                shutil.copytree(sdk, sources / f"cpp/native/{classifier}")
                for proof in ("manifest", "evidence"):
                    (sources / f"cpp/native/{classifier}/codex-agent-c-abi-{proof}.json").unlink()
                language_roots[("C++", classifier)] = sources / f"cpp/native/{classifier}"

            product_digest = lambda value: "sha256:" + hashlib.sha256(value.encode()).hexdigest()
            contract_digest = product_digest("contract")
            compatibility = {
                "schemaVersion": 1,
                "sdkVersion": "0.2.0",
                "contract": {"version": "0.2.0", "digest": contract_digest},
                "runtime": {
                    "compatibleReleaseRange": ">=0.2.0 <0.3.0",
                    "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
                    "requiredIdentitySchema": 1,
                    "requiredContractDigest": contract_digest,
                    "requiredAbiMajor": 1,
                    "minimumAbiMinor": 13,
                    "defaultRuntimeVersion": "0.2.0",
                    "defaultManifestSha256": product_digest("aggregate"),
                    "embeddedVariants": [
                        {
                            "target": classifier,
                            "componentId": product_digest(f"component:{classifier}"),
                            "bundleSha256": product_digest(f"bundle:{classifier}"),
                            "manifestSha256": product_digest(f"manifest:{classifier}"),
                            "runtimeLibrarySha256": "sha256:" + hashlib.sha256(
                                (sdks / classifier / HOSTS[classifier][4]).read_bytes()
                            ).hexdigest(),
                        }
                        for classifier in sorted(HOSTS)
                    ],
                },
                "platformRuntime": {
                    "android": {"owner": "sdk", "desktopRuntimeApplicable": False},
                    "ios": {"owner": "sdk", "desktopRuntimeApplicable": False},
                },
            }
            compatibility_bytes = canonical_json_bytes(compatibility)
            (sdks / "sdk-compatibility.json").write_bytes(compatibility_bytes)
            for relative in (
                "python/src/codex_agent/native/sdk-compatibility.json",
                "csharp/native/sdk-compatibility.json",
                "rust/native/sdk-compatibility.json",
                "dart/lib/src/native/sdk-compatibility.json",
            ):
                (sources / relative).write_bytes(compatibility_bytes)
            for classifier in HOSTS:
                destination = sources / f"cpp/native/{classifier}/share/CodexAgent/native/sdk-compatibility.json"
                destination.parent.mkdir(parents=True)
                destination.write_bytes(compatibility_bytes)

            require_prepared_native_assets(sources, sdks, "0.2.0")
            with self.assertRaisesRegex(ValueError, "compatibility version mismatch"):
                require_prepared_native_assets(sources, sdks, "0.2.1")
            staged_proof = sdks / "linux-x64/codex-agent-c-abi-evidence.json"
            staged_proof_bytes = staged_proof.read_bytes()
            staged_proof.unlink()
            with self.assertRaisesRegex(ValueError, "staged raw C ABI proof"):
                require_prepared_native_assets(sources, sdks, "0.2.0")
            staged_proof.write_bytes(staged_proof_bytes)
            forbidden = sources / "python/src/codex_agent/native/linux-x64/codex-agent-c-abi-manifest.json"
            forbidden.write_bytes(b"forbidden")
            with self.assertRaisesRegex(ValueError, "forbidden raw C ABI proof"):
                require_prepared_native_assets(sources, sdks, "0.2.0")
            forbidden.unlink()
            for (language, classifier), destination in language_roots.items():
                target = next(path for path in destination.rglob("*") if path.is_file())
                original = target.read_bytes()
                target.write_bytes(b"tampered")
                with self.subTest(language=language, classifier=classifier), self.assertRaisesRegex(
                    ValueError, re.escape(language),
                ):
                    require_prepared_native_assets(sources, sdks, "0.2.0")
                target.write_bytes(original)

            extra = sources / "python/src/codex_agent/native/unexpected"
            extra.mkdir()
            with self.assertRaisesRegex(ValueError, "classifier inventory"):
                require_prepared_native_assets(sources, sdks, "0.2.0")
            extra.rmdir()

            missing = sources / "rust/native/linux-x64"
            hidden = sources / "rust/native/linux-x64-hidden"
            missing.rename(hidden)
            with self.assertRaisesRegex(ValueError, "classifier inventory"):
                require_prepared_native_assets(sources, sdks, "0.2.0")
            hidden.rename(missing)

            real = sources / "dart/lib/src/native/linux-x64"
            hidden = sources / "dart/lib/src/native/linux-x64-real"
            real.rename(hidden)
            real.symlink_to(hidden, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "classifier inventory|symbolic"):
                require_prepared_native_assets(sources, sdks, "0.2.0")
            real.unlink()
            hidden.rename(real)

            (sdks / "unexpected").mkdir()
            with self.assertRaisesRegex(ValueError, "SDK root inventory"):
                require_prepared_native_assets(sources, sdks, "0.2.0")

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
            python.mkdir()

            def write_wheel(tag: str, wheel_metadata: str | None = None) -> None:
                with zipfile.ZipFile(python / f"codex_agent-{version}-py3-none-{tag}.whl", "w") as archive:
                    archive.writestr(f"codex_agent-{version}.dist-info/METADATA", f"Metadata-Version: 2.1\nVersion: {version}\n")
                    archive.writestr(
                        f"codex_agent-{version}.dist-info/WHEEL",
                        wheel_metadata if wheel_metadata is not None else
                        f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: py3-none-{tag}\n",
                    )

            for tag in PYTHON_TAGS.values():
                write_wheel(tag)
            source_metadata = f"Metadata-Version: 2.1\nVersion: {version}\n"
            source_build = (
                '[build-system]\nrequires = ["setuptools>=68", "wheel==0.45.1"]\n'
                'build-backend = "setuptools.build_meta"\n'
                f'[project]\nversion = "{version}"\n'
            )
            source_records = {
                "PKG-INFO": source_metadata,
                "src/codex_agent.egg-info/PKG-INFO": source_metadata,
                "pyproject.toml": source_build,
            }

            def write_sdist(records: dict[str, str]) -> None:
                with tarfile.open(python / f"codex_agent-{version}.tar.gz", "w:gz") as archive:
                    for relative, contents in records.items():
                        payload = contents.encode()
                        member = tarfile.TarInfo(f"codex_agent-{version}/{relative}")
                        member.size = len(payload)
                        archive.addfile(member, io.BytesIO(payload))

            write_sdist(source_records)
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

            tag = next(iter(PYTHON_TAGS.values()))
            for wheel_metadata in (
                f"Root-Is-Purelib: false\nTag: cp313-cp313-{tag}\n",
                f"Root-Is-Purelib: true\nTag: py3-none-{tag}\n",
                f"Root-Is-Purelib: false\nTag: py3-none-{tag}\nTag: py3-none-{tag}\n",
                "Root-Is-Purelib: false\n",
            ):
                with self.subTest(wheel_metadata=wheel_metadata):
                    write_wheel(tag, wheel_metadata)
                    with self.assertRaisesRegex(ValueError, "Python wheel interpreter/ABI/platform"):
                        require_embedded_package_versions(packages, version)
            write_wheel(tag)

            for records in (
                {"PKG-INFO": source_metadata},
                {**source_records, "src/codex_agent.egg-info/PKG-INFO": "Version: 0.2.0\n"},
                {**source_records, "extra/PKG-INFO": source_metadata},
                {relative: "Metadata-Version: 2.1\nVersion: 0.2.0\n" for relative in source_records},
            ):
                with self.subTest(sdist_records=records):
                    write_sdist(records)
                    with self.assertRaisesRegex(ValueError, "Python sdist"):
                        require_embedded_package_versions(packages, version)
            write_sdist(source_records)

            for manifest in (
                None,
                source_build.replace(', "wheel==0.45.1"', ''),
                source_build.replace('wheel==0.45.1', 'wheel>=0.45'),
                source_build.replace('wheel==0.45.1', 'wheel==0.45.1", "unexpected'),
                source_build.replace('setuptools.build_meta', 'other.backend'),
                source_build.replace(version, '0.2.0'),
            ):
                with self.subTest(sdist_build_manifest=manifest):
                    records = {key: value for key, value in source_records.items() if key != "pyproject.toml"}
                    if manifest is not None:
                        records["pyproject.toml"] = manifest
                    write_sdist(records)
                    with self.assertRaisesRegex(ValueError, "Python sdist"):
                        require_embedded_package_versions(packages, version)
            write_sdist(source_records)

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
        consumer = ast.unparse(functions["_consume"])
        self.assertIn("normalize_python_sdist", calls["package_python"])
        self.assertIn("normalize_nupkg", calls["package_once"])
        self.assertIn("verify_native_wrapper_sdk_packages", calls["package_once"])
        self.assertIn("-p:PathMap=", ast.unparse(functions["package_once"]))
        self.assertNotIn("CodexAgentRequireNativeAssets", ast.unparse(functions["package_once"]))
        self.assertIn("work = Path(temporary).resolve()", ast.unparse(functions["package_once"]))
        self.assertIn("-DCODEX_AGENT_CPP_PACKAGE_ONLY=ON", ast.unparse(functions["package_once"]))
        self.assertIn("require_embedded_package_versions", calls["_consume"])
        python_manifest = tomllib.loads((CI_ROOT.parent / "codex-agent-bindings/python/pyproject.toml").read_text())
        self.assertIn("wheel==0.45.1", python_manifest["build-system"]["requires"])
        self.assertFalse(any(
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == "PATH"
            for node in ast.walk(functions["_consume"])
        ))
        self.assertIn("consumer_env.pop('CODEX_AGENT_LIBRARY', None)", consumer)
        self.assertIn(
            "reject_raw_c_abi_proofs(python_library.parents[2], 'Python')",
            consumer,
        )
        self.assertEqual(5, consumer.count("require_matching_compatibility("))
        self.assertEqual(5, consumer.count("reject_raw_c_abi_proofs("))
        for embedded, override in (
            (
                "run(python, python_smoke, cwd=work, env=consumer_env)",
                "run(python, python_smoke, python_library, cwd=work, env=consumer_env)",
            ),
            (
                "run(*rust_command, cwd=work, env=cargo_env)",
                "run(*rust_command, rust_library, cwd=work, env=cargo_env)",
            ),
            (
                "run(executable(cpp_build, 'codex_agent_host_smoke'), cwd=work, env=cpp_env)",
                "run(executable(cpp_build, 'codex_agent_host_smoke'), cpp_library, cwd=work, env=cpp_env)",
            ),
            (
                "run('dart', 'run', 'bin/host_smoke.dart', cwd=dart_consumer, env=consumer_env)",
                "run('dart', 'run', 'bin/host_smoke.dart', dart_library, cwd=dart_consumer, env=consumer_env)",
            ),
        ):
            self.assertIn(embedded, consumer)
            self.assertIn(override, consumer)
        self.assertIn("'--', cwd=work, env=consumer_env)", consumer)
        self.assertIn("'--', csharp_library, cwd=work, env=consumer_env)", consumer)
        self.assertFalse(any(
            "codex-agent-c-abi-" in item.get("Include", "")
            for item in csharp_project.findall(".//None")
        ))
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


class NativeWrapperSingleLanguageConsumerTest(unittest.TestCase):
    """Dispatch/evidence fixtures only: external tools and runtime execution are mocked."""

    def test_rust_lifecycle_runs_on_every_host_with_imported_contract_identity(self) -> None:
        for classifier in HOSTS:
            for fails in (False, True):
                with self.subTest(classifier=classifier, fails=fails), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                    root = Path(temporary).resolve()
                    repository, packages, sdks, library, selected = self.fixture(root, ("rust",))
                    native = sdks / classifier / HOSTS[classifier][4]
                    native.parent.mkdir(parents=True, exist_ok=True)
                    if native != library:
                        native.write_bytes(library.read_bytes())
                    probes = self.controls(stack, selected, native)
                    probes["host_classifier"].return_value = classifier
                    probes["platform.system"].return_value = HOSTS[classifier][0]
                    stack.enter_context(patch.dict("os.environ", {"CC": "explicit-cc", "CODEX_AGENT_TEST_CONTRACT_DIGEST": "stale"}))
                    compatibility = load_canonical_json_bytes((sdks / "sdk-compatibility.json").read_bytes())
                    if fails:
                        def fail_lifecycle(*command, **kwargs):
                            if "codex-agent-rust-lifecycle-smoke" in command:
                                raise ValueError("observed lifecycle failure")
                        probes["run"].side_effect = fail_lifecycle
                        with self.assertRaisesRegex(ValueError, "observed lifecycle failure"):
                            consume_language(repository, packages, sdks, root / "output", "0.2.0", "rust", offline=True)
                        self.assertFalse((root / "output").exists())
                    else:
                        consume_language(repository, packages, sdks, root / "output", "0.2.0", "rust", offline=True)
                    commands = [list(map(str, call.args)) for call in probes["run"].call_args_list]
                    compile_command = next(command for command in commands if command[0] == "explicit-cc")
                    self.assertIn(f'-DCODEX_AGENT_TEST_CONTRACT_DIGEST="{compatibility["runtime"]["requiredContractDigest"]}"', compile_command)
                    self.assertEqual(classifier != "windows-x64", "-pthread" in compile_command)
                    self.assertEqual(classifier != "windows-x64", "-fPIC" in compile_command)
                    self.assertIn("-dynamiclib" if classifier.startswith("macos-") else "-shared", compile_command)
                    lifecycle = next(command for command in commands if "codex-agent-rust-lifecycle-smoke" in command)
                    self.assertEqual(compile_command[-1], lifecycle[-1])
                    self.assertIn("--offline", lifecycle)
                    if not fails:
                        self.assertIn("rustFixtureCompiler\t", (root / f"output/evidence/rust/toolchain.tsv").read_text())

    def test_cpp_negative_outputs_are_separate_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            repository, packages, sdks, library, selected = self.fixture(root, ("cpp",))
            probes = self.controls(stack, selected, library)
            output, negatives = root / "output", root / "negatives"
            for directory in (output, negatives):
                directory.mkdir()
                (directory / "sentinel").write_text("preserve")
            link = root / "link"
            link.symlink_to(packages, target_is_directory=True)
            for invalid in (None, output, output / "nested", root, packages, sdks, link / "child"):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    consume_language(repository, packages, sdks, output, "0.2.0", "cpp",
                                     package_negative_evidence=invalid)
                self.assertEqual("preserve", (output / "sentinel").read_text())
                self.assertEqual("preserve", (negatives / "sentinel").read_text())
            probes["run"].assert_not_called()

            def fail_negatives(*command, **kwargs):
                if any(str(value).endswith("/tools/verify_imported_package.py") for value in command):
                    negatives.mkdir()
                    (negatives / "partial").write_text("not accepted")
                    raise ValueError("actual negative verifier failure")
            probes["run"].side_effect = fail_negatives
            with self.assertRaisesRegex(ValueError, "actual negative verifier failure"):
                consume_language(repository, packages, sdks, output, "0.2.0", "cpp",
                                 package_negative_evidence=negatives)
            self.assertFalse(output.exists())
            self.assertFalse(negatives.exists())
            self.assertTrue(selected["cpp"].is_file())

    def fixture(self, root: Path, languages: tuple[str, ...]):
        from ci.tests.test_products import sdk_compatibility

        repository, packages, sdks = root / "repository", root / "packages", root / "sdks"
        repository.mkdir()
        library = sdks / "linux-x64/lib/libcodex_agent.so"
        library.parent.mkdir(parents=True)
        library.write_bytes(b"synthetic unexecuted native input")
        (sdks / "sdk-compatibility.json").write_bytes(canonical_json_bytes(sdk_compatibility()))
        selected = {}
        for language in languages:
            source = repository / "codex-agent-bindings" / language
            source.mkdir(parents=True)
            package = packages / language / "package.fixture"
            package.parent.mkdir(parents=True)
            selected[language] = package
            if language == "csharp":
                consumer = source / "samples/CodexAgent.Consumer"
                consumer.mkdir(parents=True)
                (consumer / "CodexAgent.Consumer.csproj").write_text(
                    '<PackageReference Include="CodexAgent" Version="0.2.0" />\n',
                )
                package.write_bytes(b"synthetic uninstalled NuGet input")
            elif language == "rust":
                consumer = source / "consumer"
                consumer.mkdir()
                (consumer / "Cargo.toml").write_text('path = ".."\n')
                (consumer / "Cargo.lock").write_text('name = "codex-agent"\nversion = "0.2.0"\n')
                write_tar_file(package, "codex-agent-0.2.0/Cargo.toml", "fixture\n")
            elif language == "dart":
                consumer = source / "consumer"
                consumer.mkdir()
                (consumer / "pubspec.yaml").write_text("dependencies:\n  codex_agent:\n    path: ..\n")
                (consumer / "pubspec.lock").write_text(
                    '  codex_agent:\n    dependency: "direct main"\n    description:\n'
                    '      path: ".."\n      relative: true\n    source: path\n    version: "0.2.0"\n',
                )
                write_tar_file(package, "codex_agent-0.2.0/pubspec.yaml", "fixture\n")
            elif language == "cpp":
                write_zip_file(package, "codex-agent-cpp-0.2.0/fixture.txt", "fixture\n")
            else:
                package.write_bytes(b"synthetic uninstalled wheel input")
        return repository, packages, sdks, library, selected

    def controls(self, stack: ExitStack, selected: dict, library: Path):
        values = {}
        for name, options in {
            "host_classifier": {"return_value": "linux-x64"},
            "platform.system": {"return_value": "Linux"},
            "require_embedded_package_versions": {},
            "select_packages": {"return_value": selected},
            "require_matching_native": {"return_value": library},
            "require_matching_compatibility": {},
            "reject_raw_c_abi_proofs": {},
            "executable": {"side_effect": lambda build, name: build / name},
            "run": {}, "run_expect_failure": {},
            "version": {"return_value": "fixture tool identity"},
        }.items():
            values[name] = stack.enter_context(patch("native_wrappers." + name, **options))
        stack.enter_context(patch("native_wrappers.subprocess.run", side_effect=AssertionError("No external tools")))
        stack.enter_context(patch("native_wrappers.package_all", side_effect=AssertionError("No package rebuild")))
        return values

    def test_one_language_needs_no_sibling_sources_packages_or_tools(self) -> None:
        expected_tools = {
            "python": {Path(sys.executable).name}, "csharp": {"dotnet"},
            "rust": {"cargo", "rustc", "cc"}, "cpp": {"cmake", "c++"}, "dart": {"dart"},
        }
        for language in LANGUAGES:
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
                root = Path(temporary).resolve()
                repository, packages, sdks, library, selected = self.fixture(root, (language,))
                probes = self.controls(stack, selected, library)
                stack.enter_context(patch.dict("os.environ", {"CC": "cc", "CXX": "c++"}))
                output = root / "output"
                self.assertIsNone(consume_language(
                    repository, packages, sdks, output, "0.2.0", language, offline=True,
                    expected_classifier="linux-x64",
                    package_negative_evidence=root / "negatives" if language == "cpp" else None,
                ))
                self.assertEqual({language}, {path.name for path in (repository / "codex-agent-bindings").iterdir()})
                probes["require_embedded_package_versions"].assert_called_once_with(packages, "0.2.0", (language,))
                probes["select_packages"].assert_called_once_with(packages, "linux-x64", "0.2.0", (language,))
                self.assertEqual(1, probes["require_matching_native"].call_count)
                self.assertEqual(1, probes["require_matching_compatibility"].call_count)
                self.assertEqual(1, probes["reject_raw_c_abi_proofs"].call_count)
                self.assertEqual(3, probes["run_expect_failure"].call_count)
                observed_tools = {Path(call.args[0]).name for call in probes["version"].call_args_list}
                self.assertEqual(expected_tools[language], observed_tools)
                commands = [list(map(str, call.args)) for call in probes["run"].call_args_list]
                if language == "cpp":
                    negative = next(command for command in commands if any(
                        value.endswith("/tools/verify_imported_package.py") for value in command))
                    self.assertEqual(str(root / "negatives"), negative[negative.index("--output") + 1])
                    self.assertTrue(negative[negative.index("--package-root") + 1].endswith(
                        "/cpp-package/codex-agent-cpp-0.2.0"))
                    self.assertEqual("lib/libcodex_agent.so", negative[negative.index("--library") + 1])
                self.assertFalse(any("ci/receipt.py" in argument for command in commands for argument in command))
                for call in probes["run"].call_args_list + probes["run_expect_failure"].call_args_list:
                    if "env" in call.kwargs:
                        self.assertNotIn("CODEX_AGENT_LIBRARY", call.kwargs["env"])
                if language in {"rust", "dart"}:
                    command = next(command for command in commands if command[1:2] == ["fetch"] or
                                   command[1:3] == ["pub", "get"])
                    self.assertIn("--offline", command)
                    self.assertIn("--locked" if language == "rust" else "--enforce-lockfile", command)
                relative = [path.relative_to(output).as_posix() for path in files(output)]
                self.assertEqual([f"evidence/{language}/linux-x64.tsv", f"evidence/{language}/toolchain.tsv"], relative)
                report = (output / f"evidence/{language}/linux-x64.tsv").read_text()
                self.assertIn(f"{language}-package/{selected[language].name}", report)
                self.assertIn(hashlib.sha256(selected[language].read_bytes()).hexdigest(), report)
                self.assertIn(hashlib.sha256(library.read_bytes()).hexdigest(), report)
                self.assertIn(f"{language}-installed-host-lifecycle\tpassed\n", report)
                self.assertTrue((output / f"evidence/{language}/toolchain.tsv").read_text().startswith("tool\tversion\n"))

    def test_default_legacy_path_still_executes_all_languages_and_writes_its_lane_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            repository, packages, sdks, library, selected = self.fixture(root, LANGUAGES)
            probes = self.controls(stack, selected, library)
            consume(repository, packages, sdks, root / "plan.json", root / "output", "0.2.0")
            self.assertEqual(5, probes["require_matching_compatibility"].call_count)
            self.assertEqual(5, probes["reject_raw_c_abi_proofs"].call_count)
            self.assertEqual(15, probes["run_expect_failure"].call_count)
            command = list(map(str, probes["run"].call_args.args))
            self.assertIn(str(repository / "ci/receipt.py"), command)
            self.assertEqual(5, command.count("--artifact"))
            self.assertEqual(5, command.count("--evidence"))
            self.assertFalse(any(path.name == "toolchain.tsv" for path in files(root / "output")))

    def test_partial_language_cannot_emit_legacy_receipt_or_keep_failed_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            repository, packages, sdks, library, selected = self.fixture(root, ("python",))
            probes = self.controls(stack, selected, library)
            with self.assertRaisesRegex(ValueError, "all-language lane receipt"):
                _consume(repository, packages, sdks, root / "plan", root / "output", "0.2.0", languages=("python",))
            probes["run"].assert_not_called()
            probes["run"].side_effect = ValueError("simulated consumer failure")
            output = root / "output"
            output.mkdir()
            (output / "stale-success.tsv").write_text("stale\n")
            with self.assertRaisesRegex(ValueError, "simulated consumer failure"):
                consume_language(repository, packages, sdks, output, "0.2.0", "python")
            self.assertFalse(output.exists())

    def test_single_language_cli_has_no_legacy_plan_and_forwards_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version_file = root / "sdk.txt"
            version_file.write_text("0.2.0\n")
            command = ["native_wrappers.py", "consume-language", "--repository", str(root / "repository"),
                       "--packages", str(root / "packages"), "--sdks", str(root / "sdks"),
                       "--output", str(root / "output"), "--sdk-version-file", str(version_file),
                       "--language", "python", "--expected-classifier", "linux-x64", "--offline"]
            with patch.object(sys, "argv", command), patch("native_wrappers.consume_language") as consume_mock:
                main()
                consume_mock.assert_called_once_with(
                    root / "repository", root / "packages", root / "sdks", root / "output",
                    "0.2.0", "python", offline=True, expected_classifier="linux-x64",
                    package_negative_evidence=None,
                )
            with patch.object(sys, "argv", command + ["--plan", str(root / "plan")]), \
                    patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit):
                parse_args()

            without_classifier = command[:command.index("--expected-classifier")] + command[
                command.index("--expected-classifier") + 2:
            ]
            with patch.object(sys, "argv", without_classifier), patch("sys.stderr", io.StringIO()), \
                    self.assertRaises(SystemExit):
                parse_args()

    def test_expected_classifier_rejects_before_consumer_or_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "output"
            output.mkdir()
            (output / "stale.tsv").write_text("stale\n")
            with patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch("native_wrappers._consume") as consume_mock, \
                    self.assertRaisesRegex(
                        ValueError,
                        "host classifier mismatch: expected macos-arm64, found linux-x64",
                    ):
                consume_language(
                    root, root / "packages", root / "sdks", output, "0.2.0", "python",
                    expected_classifier="macos-arm64",
                )
            consume_mock.assert_not_called()
            self.assertFalse(output.exists())

            with patch("native_wrappers.host_classifier") as classifier_mock, \
                    patch("native_wrappers._consume") as consume_mock, \
                    self.assertRaisesRegex(ValueError, "unsupported expected host classifier: other"):
                consume_language(
                    root, root / "packages", root / "sdks", output, "0.2.0", "python",
                    expected_classifier="other",
                )
            classifier_mock.assert_not_called()
            consume_mock.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
