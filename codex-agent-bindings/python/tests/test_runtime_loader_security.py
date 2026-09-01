from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_agent._ffi import (  # noqa: E402
    NativeLibrary,
    _read_runtime_identity,
    _snapshot_embedded_library,
    _validate_compatibility,
    _validate_runtime_identity,
    current_classifier,
    resolve_library_path,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


def compatibility() -> dict[str, object]:
    targets = ["linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"]
    return {
        "schemaVersion": 1,
        "sdkVersion": "0.2.0",
        "contract": {"version": "0.2.0", "digest": digest("a")},
        "runtime": {
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
            "requiredIdentitySchema": 1,
            "requiredContractDigest": digest("a"),
            "requiredAbiMajor": 1,
            "minimumAbiMinor": 13,
            "defaultRuntimeVersion": "0.2.0",
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
        "runtimeCompatibilityVersion": "0.2.0",
        "schemaVersion": 1,
        "target": target,
    }


def canonical(value: dict[str, object], final_lf: bool = True) -> bytes:
    result = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return result + (b"\n" if final_lf else b"")


def compile_library(directory: Path, name: str, identity_json: bytes | None, abi: int) -> Path:
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    library = directory / f"lib{name}{suffix}"
    source = directory / f"{name}.c"
    identity_function = ""
    if identity_json is not None:
        literal = json.dumps(identity_json.decode())
        identity_function = f"""
int32_t codex_agent_runtime_identity(char *buffer, size_t *size) {{
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
uint32_t codex_agent_abi_version(void) {{ return UINT32_C(0x{abi:08x}); }}
int32_t codex_agent_abi_is_compatible(uint32_t requested) {{ return requested <= UINT32_C(0x{abi:08x}); }}
{identity_function}
""")
    command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror"]
    command += ["-dynamiclib"] if platform.system() == "Darwin" else ["-shared", "-fPIC"]
    subprocess.run([*command, str(source), "-o", str(library)], check=True, capture_output=True)
    return library


class RuntimeLoaderSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compatibility = _validate_compatibility(canonical(compatibility()))

    def test_embedded_and_external_identity_rules(self) -> None:
        _validate_runtime_identity(identity(), self.compatibility, "macos-arm64", True)
        external = identity()
        external["componentId"] = digest("9")
        _validate_runtime_identity(external, self.compatibility, "macos-arm64", False)
        with self.assertRaisesRegex(OSError, "component mismatch"):
            _validate_runtime_identity(external, self.compatibility, "macos-arm64", True)

    def test_identity_incompatibilities_fail_closed(self) -> None:
        changes = {
            "missing schema field": lambda value: value.pop("schemaVersion"),
            "boolean schema": lambda value: value.__setitem__("schemaVersion", True),
            "ABI 1.12": lambda value: value.__setitem__("cAbiVersion", "1.12.0"),
            "wrong ABI major": lambda value: value.__setitem__("cAbiVersion", "2.13.0"),
            "wrong Contract": lambda value: value.__setitem__("contractDigest", digest("9")),
            "wrong target": lambda value: value.__setitem__("target", "linux-arm64"),
            "unsupported compatibility": lambda value: value.__setitem__("runtimeCompatibilityVersion", "0.3.0"),
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

    def test_real_missing_identity_and_abi_mismatch_above_floor_fail(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            missing = compile_library(root, "missing_identity", None, 0x010D0000)
            with self.assertRaises(AttributeError):
                _read_runtime_identity(ctypes.CDLL(str(missing)))

            target = current_classifier()
            mismatched_identity = identity(target)
            mismatch = compile_library(root, "abi_mismatch", canonical(mismatched_identity, False), 0x010E0000)
            with patch("codex_agent._ffi._load_compatibility", return_value=self.compatibility):
                with self.assertRaisesRegex(OSError, "ABI disagrees"):
                    NativeLibrary.load(mismatch)

    def test_noncanonical_native_identity_fails(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            value = identity(current_classifier())
            noncanonical = json.dumps(value, indent=2).encode()
            library = compile_library(Path(directory), "noncanonical", noncanonical, 0x010D0000)
            with self.assertRaisesRegex(OSError, "canonical"):
                _read_runtime_identity(ctypes.CDLL(str(library)))


if __name__ == "__main__":
    unittest.main()
