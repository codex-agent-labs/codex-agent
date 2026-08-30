from __future__ import annotations

import ast
import hashlib
import io
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
    deterministic_tar,
    deterministic_zip,
    files,
    host_classifier,
    normalize_nupkg,
    normalize_python_sdist,
    package_all,
    safe_extract_tar,
    safe_extract_zip,
    stage_dart_release,
)


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
                output = Path(_arguments[-1])
                output.mkdir(parents=True)
                (output / "changed").write_text(str(calls), encoding="utf-8")
                if calls:
                    (output / "second-only").write_text("extra", encoding="utf-8")
                else:
                    (output / "first-only").write_text("extra", encoding="utf-8")
                calls += 1

            with patch("native_wrappers.package_once", side_effect=package_once):
                with self.assertRaisesRegex(ValueError, "(?s)changed.*second-only") as failure:
                    package_all(root, root, root, root / "packages")
            self.assertIn("first=missing", str(failure.exception))
            self.assertIn("second=missing", str(failure.exception))

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
            / "codex-agent-runtime-desktop/bindings/csharp/src/CodexAgent/CodexAgent.csproj"
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
