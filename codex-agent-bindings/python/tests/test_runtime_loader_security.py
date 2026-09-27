from __future__ import annotations

import ctypes
import base64
import hashlib
import json
import os
import platform
import shlex
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
NATIVE_LOADER_TESTS = ("test_signed_external_runtime_loads_and_tampering_fails",
                       "test_real_missing_identity_and_abi_mismatch_above_floor_fail",
                       "test_noncanonical_native_identity_fails")
_native_loader_directory: Path | None = None
sys.path.insert(0, str(ROOT / "src"))

from codex_agent._ffi import (  # noqa: E402
    NativeLibrary,
    _library_name,
    _load_compatibility,
    _read_sdk_runtime_root,
    _read_runtime_identity,
    _snapshot_embedded_library,
    _validate_compatibility,
    _validate_runtime_identity,
    current_classifier,
    resolve_library_path,
)
from codex_agent._runtime_evidence import _json, _read  # noqa: E402
from codex_agent import _ffi  # noqa: E402
from runtime_signed_fixture import authorize  # noqa: E402


def digest(character: str) -> str:
    return "sha256:" + character * 64


def compatibility() -> dict[str, object]:
    targets = ["linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"]
    return {
        "schemaVersion": 1,
        "sdkVersion": "0.8.0",
        "contract": {"version": "0.8.0", "digest": digest("a")},
        "runtime": {
            "compatibleReleaseRange": ">=0.8.0 <0.9.0",
            "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0",
            "requiredIdentitySchema": 1,
            "requiredContractDigest": digest("a"),
            "requiredAbiMajor": 1,
            "minimumAbiMinor": 13,
            "defaultRuntimeVersion": "0.8.0",
            "defaultManifestSha256": digest("b"),
            "embeddedVariants": [
                {
                    "target": target,
                    "componentId": digest(str(index)),
                    "bundleSha256": digest("c"),
                    "manifestSha256": digest(str(index + 5)),
                    "runtimeLibrarySha256": digest("d"),
                }
                for index, target in enumerate(targets)
            ],
        },
        "platformRuntime": {
            "android": {"owner": "sdk", "desktopRuntimeApplicable": False},
            "ios": {"owner": "sdk", "desktopRuntimeApplicable": False},
        },
    }


def identity(target: str = "macos-arm64") -> dict[str, object]:
    component = {
        "linux-arm64": "0", "linux-x64": "1", "macos-arm64": "2",
        "macos-x64": "3", "windows-x64": "4",
    }[target]
    return {
        "appServerVersion": "0.149.0",
        "buildInputDigest": digest("e"),
        "cAbiVersion": "1.13.0",
        "componentId": digest(component),
        "contractComponentDigest": digest("f"),
        "contractDigest": digest("a"),
        "runtimeCompatibilityVersion": "0.8.0",
        "schemaVersion": 1,
        "target": target,
    }


def canonical(value: dict[str, object], final_lf: bool = True) -> bytes:
    result = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return result + (b"\n" if final_lf else b"")


def install_synthetic_wheel(directory: Path, root_public: bytes, embedded_library: Path | None = None) -> Path:
    package_data = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["codex_agent"]
    if "native/sdk-compatibility.json" not in package_data or "native/sdk-runtime-root.pub" not in package_data:
        raise AssertionError("Python wheel manifest omits an SDK trust resource")
    if embedded_library is not None and "native/*/*" not in package_data:
        raise AssertionError("Python wheel manifest omits embedded Runtime libraries")
    source = ROOT / "src/codex_agent"
    entries = {
        file.relative_to(ROOT / "src").as_posix(): file.read_bytes()
        for file in source.rglob("*")
        if file.is_file() and (file.suffix in {".py", ".pyi"} or file.name == "py.typed")
    }
    declaration = compatibility()
    if embedded_library is not None:
        target = current_classifier()
        variant = next(item for item in declaration["runtime"]["embeddedVariants"] if item["target"] == target)
        variant["runtimeLibrarySha256"] = "sha256:" + hashlib.sha256(embedded_library.read_bytes()).hexdigest()
        entries[f"codex_agent/native/{target}/{_library_name(target)}"] = embedded_library.read_bytes()
    entries["codex_agent/native/sdk-compatibility.json"] = canonical(declaration)
    entries["codex_agent/native/sdk-runtime-root.pub"] = root_public
    metadata = "codex_agent-0.8.0.dist-info"
    entries[f"{metadata}/METADATA"] = b"Metadata-Version: 2.1\nName: codex-agent\nVersion: 0.8.0\n"
    entries[f"{metadata}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: synthetic-loader-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = [f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()},{len(data)}"
              for name, data in sorted(entries.items())]
    entries[f"{metadata}/RECORD"] = ("\n".join([*record, f"{metadata}/RECORD,,"]) + "\n").encode()
    wheel = directory / "codex_agent-0.8.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    installed = directory / "installed"
    result = subprocess.run([sys.executable, "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
                             "--no-compile", "--disable-pip-version-check", "--target", str(installed), str(wheel)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise AssertionError(f"synthetic wheel installation failed:\n{result.stdout.decode(errors='replace')}")
    return installed


def write_execution(path: Path, result: subprocess.CompletedProcess) -> None:
    # Same lossless external execution envelope as the other language producers.
    path.write_bytes((json.dumps({"schemaVersion": 1, "exitCode": result.returncode,
        "outputBase64": base64.b64encode(result.stdout).decode("ascii")},
        sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))


def _run_native_loader_test(name: str) -> None:
    if name not in NATIVE_LOADER_TESTS:
        raise ValueError("Unsupported native loader child test")
    directory = ROOT / "build/loader-security-evidence" / name
    directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                             "--native-loader-child", name, str(directory)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    write_execution(directory / "child-execution.json", result)
    if result.returncode:
        raise AssertionError(f"Native loader security child failed:\n{result.stdout.decode('utf-8', errors='replace')}")


def compile_library(directory: Path, name: str, identity_json: bytes | None, abi: int) -> Path:
    system = platform.system()
    library = directory / (f"{name}.dll" if system == "Windows" else
                           f"lib{name}" + (".dylib" if system == "Darwin" else ".so"))
    library.unlink(missing_ok=True)
    source = directory / f"{name}.c"
    identity_function = ""
    if identity_json is not None:
        literal = json.dumps(identity_json.decode())
        identity_function = f"""
API int32_t codex_agent_runtime_identity(char *buffer, size_t *size) {{
    static const char identity[] = {literal};
    const size_t required = sizeof(identity);
    if (size == NULL) return 1;
    if (buffer == NULL || *size < required) {{ *size = required; return 9; }}
    memcpy(buffer, identity, required); *size = required; return 0;
}}
"""
    source.write_text(f"""
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#if defined(_WIN32)
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
API uint32_t codex_agent_abi_version(void) {{ return UINT32_C(0x{abi:08x}); }}
API int32_t codex_agent_abi_is_compatible(uint32_t requested) {{ return requested <= UINT32_C(0x{abi:08x}); }}
{identity_function}
""")
    compiler = shlex.split(os.environ.get("CC") or ("cl" if system == "Windows" else "cc"))
    if system == "Windows" and Path(compiler[0]).name.lower() in {"cl", "cl.exe"}:
        command = [*compiler, "/nologo", "/std:c11", "/W4", "/WX", "/LD", str(source),
                   f"/Fe:{library}", f"/Fo{directory / (name + '.obj')}"]
    else:
        command = [*compiler, "-std=c11", "-Wall", "-Wextra", "-Werror"]
        command += ["-dynamiclib"] if system == "Darwin" else ["-shared"]
        if system != "Windows":
            command.append("-fPIC")
        command += [str(source), "-o", str(library)]
    result = subprocess.run(command, cwd=directory, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_execution(directory / f"{name}-compiler-execution.json", result)
    if result.returncode:
        raise AssertionError(f"Runtime loader fixture compilation failed:\n{result.stdout.decode('utf-8', errors='replace')}")
    if not library.is_file() or not library.stat().st_size:
        raise AssertionError("Runtime loader fixture compiler did not produce its declared library")
    return library


class RuntimeLoaderSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compatibility = _validate_compatibility(canonical(compatibility()))

    def test_embedded_and_external_identity_rules(self) -> None:
        _validate_runtime_identity(identity(), self.compatibility, "macos-arm64", True)
        external = identity()
        external["componentId"] = digest("9")
        external["runtimeCompatibilityVersion"] = "0.8.5"
        _validate_runtime_identity(external, self.compatibility, "macos-arm64", False)
        with self.assertRaisesRegex(OSError, "component mismatch"):
            _validate_runtime_identity(external, self.compatibility, "macos-arm64", True)

    def test_runtime_identity_size_is_bounded_before_allocation(self) -> None:
        class OversizedIdentity:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, buffer: object, size: object) -> int:
                self.calls += 1
                ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t))[0] = 65537
                return 9

        function = OversizedIdentity()
        library = type("Library", (), {"codex_agent_runtime_identity": function})()
        with self.assertRaisesRegex(OSError, "size query failed"):
            _read_runtime_identity(library)
        self.assertEqual(function.calls, 1)

    def test_rejected_load_releases_verified_runtime_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / _library_name(current_classifier())
            library.write_bytes(b"verified but unloadable Runtime")
            policy = compatibility()
            variant = next(item for item in policy["runtime"]["embeddedVariants"]
                           if item["target"] == current_classifier())
            variant["runtimeLibrarySha256"] = "sha256:" + hashlib.sha256(library.read_bytes()).hexdigest()
            retained_before = len(_ffi._SNAPSHOT_DIRECTORIES)
            loaded_paths: list[Path] = []

            def reject(path: str) -> None:
                loaded_paths.append(Path(path))
                raise OSError("dynamic load failed")

            with patch.object(_ffi, "_load_compatibility", return_value=policy), \
                    patch.object(_ffi, "resolve_library_path", return_value=library), \
                    patch.object(_ffi.ctypes, "CDLL", side_effect=reject):
                with self.assertRaisesRegex(OSError, "dynamic load failed"):
                    NativeLibrary.load()

            self.assertEqual(len(loaded_paths), 1)
            self.assertFalse(loaded_paths[0].exists())
            self.assertFalse(loaded_paths[0].parent.exists())
            self.assertEqual(len(_ffi._SNAPSHOT_DIRECTORIES), retained_before)

    def test_windows_loaded_snapshot_is_retained_and_failed_cleanup_keeps_owner(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            library = Path(temporary) / "codex_agent.dll"
            library.write_bytes(b"verified Runtime")
            expected = "sha256:" + hashlib.sha256(library.read_bytes()).hexdigest()
            snapshot = _snapshot_embedded_library(library, expected)
            owner = next(item for item in _ffi._SNAPSHOT_DIRECTORIES if item.name == str(snapshot.parent))
            try:
                with patch.object(_ffi, "_load_compatibility", return_value=compatibility()), \
                        patch.object(_ffi, "resolve_library_path", return_value=library), \
                        patch.object(_ffi, "_snapshot_embedded_library", return_value=snapshot), \
                        patch.object(_ffi.ctypes, "CDLL", return_value=object()), \
                        patch.object(_ffi, "_read_runtime_identity", side_effect=OSError("identity rejected")), \
                        patch.object(_ffi.os, "name", "nt"):
                    with self.assertRaisesRegex(OSError, "identity rejected"):
                        NativeLibrary.load()
                self.assertTrue(snapshot.exists())
                self.assertIn(owner, _ffi._SNAPSHOT_DIRECTORIES)
                with patch.object(owner, "cleanup", side_effect=PermissionError("DLL remains loaded")):
                    _ffi._release_snapshot(snapshot)
                self.assertIn(owner, _ffi._SNAPSHOT_DIRECTORIES)
            finally:
                _ffi._release_snapshot(snapshot)
            self.assertFalse(snapshot.parent.exists())

    def test_identity_incompatibilities_fail_closed(self) -> None:
        changes = {
            "missing schema field": lambda value: value.pop("schemaVersion"),
            "boolean schema": lambda value: value.__setitem__("schemaVersion", True),
            "ABI 1.12": lambda value: value.__setitem__("cAbiVersion", "1.12.0"),
            "wrong ABI minor": lambda value: value.__setitem__("cAbiVersion", "1.0.0"),
            "wrong ABI major": lambda value: value.__setitem__("cAbiVersion", "2.13.0"),
            "ABI patch-width collision": lambda value: value.__setitem__("cAbiVersion", "1.13.65536"),
            "wrong Contract": lambda value: value.__setitem__("contractDigest", digest("9")),
            "malformed Contract component digest": lambda value: value.__setitem__(
                "contractComponentDigest", "sha256:invalid"
            ),
            "wrong target": lambda value: value.__setitem__("target", "linux-arm64"),
            "unsupported compatibility": lambda value: value.__setitem__("runtimeCompatibilityVersion", "0.9.0"),
        }
        for description, change in changes.items():
            with self.subTest(description):
                value = identity()
                change(value)
                with self.assertRaises(OSError):
                    _validate_runtime_identity(value, self.compatibility, "macos-arm64", False)

    def test_compatibility_requires_canonical_bytes_and_real_integers(self) -> None:
        value = compatibility()
        for field in ("schemaVersion",):
            changed = dict(value)
            changed[field] = True
            with self.assertRaises(OSError):
                _validate_compatibility(canonical(changed))
        for field in ("requiredIdentitySchema", "requiredAbiMajor", "minimumAbiMinor"):
            changed = json.loads(json.dumps(value))
            changed["runtime"][field] = True
            with self.assertRaises(OSError):
                _validate_compatibility(canonical(changed))
        with self.assertRaisesRegex(OSError, "canonical"):
            _validate_compatibility(json.dumps(value, indent=2).encode() + b"\n")
        with self.assertRaisesRegex(OSError, "canonical"):
            _validate_compatibility(canonical(value, False))

    def test_tampered_compatibility_policy_fails_closed(self) -> None:
        changes = {
            "Contract digest disagreement": lambda value: value["contract"].__setitem__("digest", digest("9")),
            "default Runtime outside release range": lambda value: value["runtime"].__setitem__("defaultRuntimeVersion", "0.9.0"),
            "duplicate component identity": lambda value: value["runtime"]["embeddedVariants"][1].__setitem__(
                "componentId", value["runtime"]["embeddedVariants"][0]["componentId"]
            ),
            "duplicate manifest identity": lambda value: value["runtime"]["embeddedVariants"][1].__setitem__(
                "manifestSha256", value["runtime"]["embeddedVariants"][0]["manifestSha256"]
            ),
            "Desktop Runtime assigned to Android": lambda value: value["platformRuntime"]["android"].__setitem__(
                "desktopRuntimeApplicable", True
            ),
        }
        for description, change in changes.items():
            with self.subTest(description):
                value = json.loads(json.dumps(compatibility()))
                change(value)
                with self.assertRaises(OSError):
                    _validate_compatibility(canonical(value))

    def test_missing_packaged_compatibility_declaration_fails_closed(self) -> None:
        with patch("codex_agent._ffi.files") as resources:
            resources.return_value.joinpath.return_value.open.side_effect = FileNotFoundError
            with self.assertRaisesRegex(OSError, "compatibility declaration is missing"):
                _load_compatibility()

    def test_packaged_policy_and_root_reads_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            native = root / "native"
            native.mkdir()
            (native / "sdk-compatibility.json").write_bytes(b"x" * (1024 * 1024 + 1))
            (native / "sdk-runtime-root.pub").write_bytes(b"x" * 4097)
            with patch("codex_agent._ffi.files", return_value=root):
                with self.assertRaisesRegex(OSError, "SDK compatibility declaration exceeds its size limit"):
                    _load_compatibility()
                with self.assertRaisesRegex(OSError, "SDK Runtime trust root exceeds its size limit"):
                    _read_sdk_runtime_root()

    def test_immutable_snapshot_survives_deterministic_source_swap(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "libcodex_agent.dylib"
            source.write_bytes(b"verified Runtime")
            expected = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            snapshot = _snapshot_embedded_library(source, expected)
            replacement = Path(directory) / "replacement"
            replacement.write_bytes(b"swapped Runtime")
            os.replace(replacement, source)
            self.assertEqual(snapshot.read_bytes(), b"verified Runtime")
            with self.assertRaisesRegex(OSError, "digest mismatch"):
                _snapshot_embedded_library(source, expected)

    def test_runtime_snapshot_rejects_oversized_or_growing_source(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            source = Path(directory) / "libcodex_agent.dylib"
            source.write_bytes(b"abc")
            expected = "sha256:" + hashlib.sha256(b"abc").hexdigest()
            metadata = source.stat()
            original_fstat = os.fstat

            def first_fstat_size(size: int):
                called = False

                def read(fd: int):
                    nonlocal called
                    if not called:
                        called = True
                        return os.stat_result((*metadata[:6], size, *metadata[7:]))
                    return original_fstat(fd)

                return read

            with patch("codex_agent._ffi.os.fstat", side_effect=first_fstat_size(512 * 1024 * 1024 + 1)):
                with self.assertRaisesRegex(OSError, "size is invalid"):
                    _snapshot_embedded_library(source, expected)
            with patch("codex_agent._ffi.os.fstat", side_effect=first_fstat_size(2)):
                with self.assertRaisesRegex(OSError, "changed while copying"):
                    _snapshot_embedded_library(source, expected)

    def test_tampered_embedded_library_digest_fails_before_dynamic_loading(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            library = Path(directory) / "libcodex_agent"
            library.write_bytes(b"tampered embedded Runtime")
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch("codex_agent._ffi.resolve_library_path", return_value=library), \
                    patch("codex_agent._ffi.ctypes.CDLL") as dynamic_loader:
                with self.assertRaisesRegex(OSError, "digest mismatch"):
                    NativeLibrary.load()
            dynamic_loader.assert_not_called()

    def test_missing_embedded_library_never_falls_back_to_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            system_candidate = Path(directory) / _library_name(current_classifier())
            system_candidate.write_bytes(b"arbitrary system Runtime")
            missing_package = Path(directory) / "missing-package"
            with patch("codex_agent._ffi.files", return_value=missing_package), \
                    patch.dict(os.environ, {"PATH": directory}, clear=False):
                with self.assertRaises(FileNotFoundError):
                    resolve_library_path()

    def test_explicit_paths_are_absolute_regular_and_link_free(self) -> None:
        with self.assertRaises(ValueError):
            resolve_library_path("")
        with self.assertRaises(ValueError):
            resolve_library_path("codex_agent")
        with patch.dict(os.environ, {"CODEX_AGENT_LIBRARY": "codex_agent", "PATH": tempfile.gettempdir()}, clear=False):
            with self.assertRaises(ValueError):
                resolve_library_path()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            library = root / "library"
            library.write_bytes(b"library")
            self.assertEqual(resolve_library_path(library), library)
            final_link = root / "final-link"
            final_link.symlink_to(library)
            with self.assertRaisesRegex(OSError, "symlinks"):
                resolve_library_path(final_link)
            real_parent = root / "real-parent"
            real_parent.mkdir()
            nested = real_parent / "library"
            nested.write_bytes(b"library")
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(OSError, "symlinks"):
                resolve_library_path(linked_parent / "library")

    def test_external_path_and_environment_require_evidence_before_loading(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            library = Path(directory) / _library_name(current_classifier())
            library.write_bytes(b"unverified Runtime")
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch("codex_agent._ffi.ctypes.CDLL") as dynamic_loader:
                with self.assertRaisesRegex(OSError, "release-attested evidence"):
                    NativeLibrary.load(library)
                with patch.dict(os.environ, {"CODEX_AGENT_LIBRARY": str(library)}):
                    with self.assertRaisesRegex(OSError, "release-attested evidence"):
                        NativeLibrary.load()
            dynamic_loader.assert_not_called()

    def test_evidence_json_rejects_floating_point_tokens(self) -> None:
        for raw in (b'{"schemaVersion":1.0}\n', b'{"nested":{"value":1e0}}\n'):
            with self.subTest(raw=raw), self.assertRaisesRegex(OSError, "floating-point"):
                _json(raw, "Runtime evidence")

    def test_evidence_reader_rechecks_swapped_file_size_on_open_descriptor(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            path = Path(temporary) / "evidence.json"
            replacement = Path(temporary) / "larger.json"
            path.write_bytes(b"ok")
            replacement.write_bytes(b"x" * 32)
            from codex_agent._ffi import _validate_absolute_regular_path

            def swap(checked: Path, description: str) -> Path:
                result = _validate_absolute_regular_path(checked, description)
                os.replace(replacement, path)
                return result

            with patch("codex_agent._runtime_evidence._validate_absolute_regular_path", side_effect=swap):
                with self.assertRaisesRegex(OSError, "size limit"):
                    _read(path, 8)
            small_metadata = os.stat_result((stat.S_IFREG, 0, 0, 0, 0, 0, 0, 0, 0, 0))
            with patch("codex_agent._runtime_evidence.os.fstat", return_value=small_metadata):
                with self.assertRaisesRegex(OSError, "size limit"):
                    _read(path, 8)

    def test_signed_external_runtime_loads_and_tampering_fails(self) -> None:
        if _native_loader_directory is None:
            _run_native_loader_test(self._testMethodName)
            return
        temporary = tempfile.TemporaryDirectory(dir=_native_loader_directory)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        target = current_classifier()
        runtime_identity = identity(target)
        library = compile_library(root, "signed_external", canonical(runtime_identity, False), 0x010D0000)
        evidence = Path(str(library) + ".evidence")
        root_public = authorize(library, runtime_identity, "0.8.5")
        release_public = (evidence / "keys/release.pub").read_bytes()
        authorization = evidence / "runtime-library-authorization.json"
        with patch("codex_agent._ffi._read_sdk_runtime_root", return_value=release_public), \
                patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                patch("codex_agent._ffi.ctypes.CDLL") as dynamic_loader:
            with self.assertRaises(OSError):
                NativeLibrary.load(library)
            dynamic_loader.assert_not_called()
        with patch("codex_agent._ffi._read_sdk_runtime_root", return_value=root_public), \
                patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                patch.object(NativeLibrary, "_declare_all", return_value=None):
            original_read_bytes = Path.read_bytes

            def reject_native_read_bytes(path: Path) -> bytes:
                if path.suffix in {".dll", ".dylib", ".so"}:
                    raise AssertionError("native library must be hashed without read_bytes")
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", reject_native_read_bytes):
                loaded = NativeLibrary.load(library)
            self.assertEqual(int(loaded.library.codex_agent_abi_version()), 0x010D0000)
            original = authorization.read_bytes()
            authorization.write_bytes(original + b"x")
            with patch("codex_agent._ffi.ctypes.CDLL") as dynamic_loader:
                with self.assertRaises(OSError):
                    NativeLibrary.load(library)
                dynamic_loader.assert_not_called()

    def test_signed_external_release_outside_sdk_range_fails_before_loading(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            runtime_identity = identity(current_classifier())
            library = compile_library(directory, "future_release", canonical(runtime_identity, False), 0x010D0000)
            pinned_root = authorize(library, runtime_identity, "0.9.0")
            with patch("codex_agent._ffi._read_sdk_runtime_root", return_value=pinned_root), \
                    patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch("codex_agent._ffi.ctypes.CDLL") as dynamic_loader:
                with self.assertRaisesRegex(OSError, "incompatible"):
                    NativeLibrary.load(library)
                dynamic_loader.assert_not_called()

    def test_delegated_release_key_rotation_keeps_sdk_root_unchanged(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            runtime_identity = identity(current_classifier())
            first = compile_library(directory, "first_release", canonical(runtime_identity, False), 0x010D0000)
            pinned_root = authorize(first, runtime_identity, "0.8.4")
            second = compile_library(directory, "rotated_release", canonical(runtime_identity, False), 0x010D0000)
            self.assertEqual(
                authorize(second, runtime_identity, "0.8.5",
                          root_private=directory / "root-key", release_key_id="rotated"),
                pinned_root,
            )
            first_evidence = Path(str(first) + ".evidence")
            second_evidence = Path(str(second) + ".evidence")
            self.assertNotEqual(
                (first_evidence / "release-keyring.json").read_bytes(),
                (second_evidence / "release-keyring.json").read_bytes(),
            )
            with patch("codex_agent._ffi._read_sdk_runtime_root", return_value=pinned_root), \
                    patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch.object(NativeLibrary, "_declare_all", return_value=None):
                for library in (first, second):
                    with self.subTest(library=library.name):
                        self.assertEqual(
                            int(NativeLibrary.load(library).library.codex_agent_abi_version()),
                            0x010D0000,
                        )

    def test_installed_wheel_uses_its_pinned_root_for_external_overrides(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            target = current_classifier()
            runtime_identity = identity(target)
            library = compile_library(directory, "wheel_external", canonical(runtime_identity, False), 0x010D0000)
            root_public = authorize(library, runtime_identity, "0.8.5")
            installed = install_synthetic_wheel(directory, root_public)
            resource = installed / "codex_agent/native/sdk-runtime-root.pub"
            self.assertEqual(resource.read_bytes(), root_public)

            child = """
import os
import sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from codex_agent import _ffi
mode, path = sys.argv[2:]
if mode == 'environment':
    os.environ['CODEX_AGENT_LIBRARY'] = path
with patch.object(_ffi.NativeLibrary, '_declare_all', return_value=None):
    if mode in {'explicit', 'environment'}:
        loaded = _ffi.NativeLibrary.load(path if mode == 'explicit' else None)
        assert loaded.library.codex_agent_abi_version() == 0x010D0000
    elif mode == 'missing_identity':
        try:
            _ffi.NativeLibrary.load(path)
        except AttributeError as error:
            assert 'codex_agent_runtime_identity' in str(error), str(error)
        else:
            raise AssertionError('signed Runtime without identity was accepted')
    else:
        with patch.object(_ffi.ctypes, 'CDLL', side_effect=AssertionError('dynamic load reached')) as dynamic_load:
            try:
                _ffi.NativeLibrary.load(path)
            except OSError as error:
                if mode == 'incompatible':
                    assert 'authorization is incompatible' in str(error), str(error)
                dynamic_load.assert_not_called()
            else:
                raise AssertionError('untrusted installed root was accepted')
"""

            def run(mode: str, candidate: Path = library) -> None:
                result = subprocess.run([sys.executable, "-I", "-B", "-c", child, str(installed), mode, str(candidate)],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))

            run("explicit")
            run("environment")
            no_identity = compile_library(directory, "missing_identity", None, 0x010D0000)
            self.assertEqual(authorize(no_identity, runtime_identity, "0.8.5",
                                       root_private=directory / "root-key",
                                       release_key_id="missing-identity"), root_public)
            run("missing_identity", no_identity)
            incompatible_directory = directory / "incompatible"
            incompatible_directory.mkdir()
            incompatible_identity = identity(target)
            incompatible_identity["contractDigest"] = digest("9")
            incompatible = compile_library(incompatible_directory, "wrong_contract",
                                           canonical(incompatible_identity, False), 0x010D0000)
            self.assertEqual(authorize(incompatible, incompatible_identity, "0.8.5",
                                       root_private=directory / "root-key"), root_public)
            run("incompatible", incompatible)
            for name, change, encoded_abi in (
                ("wrong_target", {"target": "windows-x64" if target != "windows-x64" else "linux-x64"}, 0x010D0000),
                ("old_abi", {"cAbiVersion": "1.12.0"}, 0x010C0000),
            ):
                incompatible_identity = identity(target)
                incompatible_identity.update(change)
                incompatible = compile_library(directory, name, canonical(incompatible_identity, False), encoded_abi)
                self.assertEqual(authorize(incompatible, incompatible_identity, "0.8.5",
                                           root_private=directory / "root-key",
                                           release_key_id=name.replace("_", "-")), root_public)
                run("incompatible", incompatible)
            resource.write_bytes((Path(str(library) + ".evidence") / "keys/release.pub").read_bytes())
            run("tampered")
            resource.unlink()
            run("missing")

    def test_installed_wheel_embedded_runtime_rejects_tampering_and_missing_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            directory = Path(temporary)
            target = current_classifier()
            library = compile_library(directory, "wheel_embedded", canonical(identity(target), False), 0x010D0000)
            installed = install_synthetic_wheel(directory, b"unused embedded root", library)
            packaged = installed / "codex_agent/native" / target / _library_name(target)

            child = """
import os
import sys
from unittest.mock import patch
os.environ.pop('CODEX_AGENT_LIBRARY', None)
sys.path.insert(0, sys.argv[1])
from codex_agent import _ffi
mode = sys.argv[2]
with patch.object(_ffi.NativeLibrary, '_declare_all', return_value=None):
    if mode == 'valid':
        assert _ffi.NativeLibrary.load().library.codex_agent_abi_version() == 0x010D0000
    else:
        with patch.object(_ffi.ctypes, 'CDLL', side_effect=AssertionError('dynamic load reached')) as dynamic_load:
            try:
                _ffi.NativeLibrary.load()
            except (OSError, FileNotFoundError):
                dynamic_load.assert_not_called()
            else:
                raise AssertionError('invalid embedded Runtime was accepted')
"""

            def run(mode: str) -> None:
                result = subprocess.run([sys.executable, "-I", "-B", "-c", child, str(installed), mode],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))

            run("valid")
            packaged.write_bytes(b"tampered embedded Runtime")
            run("tampered")
            packaged.unlink()
            run("missing")

    @patch("codex_agent._ffi._require_external_runtime_evidence", side_effect=lambda path, *_: (path, None))
    def test_real_missing_identity_and_abi_mismatch_above_floor_fail(self, _test_only_evidence_bypass: object) -> None:
        if _native_loader_directory is None:
            _run_native_loader_test(self._testMethodName)
            return
        root = _native_loader_directory
        if root is not None:
            missing = compile_library(root, "missing_identity", None, 0x010D0000)
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                with self.assertRaises(AttributeError):
                    NativeLibrary.load(missing)

            target = current_classifier()
            for description, abi_version, encoded_abi in (
                ("ABI 1.12", "1.12.0", 0x010C0000),
                ("wrong ABI major", "2.13.0", 0x020D0000),
            ):
                with self.subTest(description):
                    incompatible_abi_identity = identity(target)
                    incompatible_abi_identity["cAbiVersion"] = abi_version
                    incompatible_abi = compile_library(
                        root,
                        description.lower().replace(" ", "_"),
                        canonical(incompatible_abi_identity, False),
                        encoded_abi,
                    )
                    with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                        with self.assertRaisesRegex(OSError, "ABI is incompatible"):
                            NativeLibrary.load(incompatible_abi)

            mismatched_identity = identity(target)
            mismatch = compile_library(root, "abi_mismatch", canonical(mismatched_identity, False), 0x010E0000)
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                with self.assertRaisesRegex(OSError, "ABI disagrees"):
                    NativeLibrary.load(mismatch)

            overflowing_identity = identity(target)
            overflowing_identity["cAbiVersion"] = "1.13.65536"
            overflow = compile_library(
                root, "abi_width_collision", canonical(overflowing_identity, False), 0x010E0000
            )
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch.object(NativeLibrary, "_declare_all", return_value=None):
                with self.assertRaisesRegex(OSError, "packed ABI field widths"):
                    NativeLibrary.load(overflow)

            incompatible_identity = identity(target)
            incompatible_identity["contractDigest"] = digest("9")
            incompatible = compile_library(
                root, "incompatible_override", canonical(incompatible_identity, False), 0x010D0000
            )
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                with self.assertRaisesRegex(OSError, "Contract mismatch"):
                    NativeLibrary.load(incompatible)

            compatible_identity = identity(target)
            compatible_identity["componentId"] = digest("9")
            compatible_identity["runtimeCompatibilityVersion"] = "0.8.5"
            compatible = compile_library(
                root, "compatible_patch_override", canonical(compatible_identity, False), 0x010D0000
            )
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility), \
                    patch.object(NativeLibrary, "_declare_all", return_value=None):
                loaded = NativeLibrary.load(compatible)
            self.assertEqual(int(loaded.library.codex_agent_abi_version()), 0x010D0000)

            for description, field, value, error in (
                ("wrong_target", "target", "windows-x64" if target != "windows-x64" else "linux-x64", "target mismatch"),
                ("unsupported_compatibility", "runtimeCompatibilityVersion", "0.9.0", "unsupported"),
                ("malformed_component", "componentId", "sha256:invalid", "componentId"),
            ):
                with self.subTest(description):
                    incompatible_identity = identity(target)
                    incompatible_identity[field] = value
                    library = compile_library(
                        root, description, canonical(incompatible_identity, False), 0x010D0000
                    )
                    with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                        with self.assertRaisesRegex(OSError, error):
                            NativeLibrary.load(library)

    def test_noncanonical_native_identity_fails(self) -> None:
        if _native_loader_directory is None:
            _run_native_loader_test(self._testMethodName)
            return
        directory = _native_loader_directory
        if directory is not None:
            value = identity(current_classifier())
            noncanonical = json.dumps(value, indent=2).encode()
            library = compile_library(Path(directory), "noncanonical", noncanonical, 0x010D0000)
            with self.assertRaisesRegex(OSError, "canonical"):
                _read_runtime_identity(ctypes.CDLL(str(library)))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--native-loader-child"]:
        if len(sys.argv) != 4 or sys.argv[2] not in NATIVE_LOADER_TESTS:
            raise SystemExit("Invalid native loader child invocation")
        _native_loader_directory = ROOT / "build/loader-security-evidence" / sys.argv[2]
        if Path(sys.argv[3]) != _native_loader_directory or not _native_loader_directory.is_dir():
            raise SystemExit("Native loader child evidence directory mismatch")
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
            RuntimeLoaderSecurityTests(sys.argv[2]),
        ]))
        raise SystemExit(0 if result.wasSuccessful() and result.testsRun == 1 and not result.skipped else 1)
    unittest.main()
