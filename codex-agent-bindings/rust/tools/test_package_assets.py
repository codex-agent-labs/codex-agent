"""Compiler-free check of Cargo's package-verification marker and native members."""

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_KEY = ROOT.parents[1] / "gradle/release/keys/sdk-runtime-root.pub"
LIBRARIES = (
    "native/osx-arm64/libcodex_agent.dylib",
    "native/osx-x64/libcodex_agent.dylib",
    "native/linux-arm64/libcodex_agent.so",
    "native/linux-x64/libcodex_agent.so",
    "native/win-x64/codex_agent.dll",
)


class PackageAssetsTest(unittest.TestCase):
    def test_package_verification_rejects_missing_or_empty_runtime_assets(self) -> None:
        cargo = os.environ.get("CODEX_AGENT_TEST_CARGO") or shutil.which("cargo")
        rustc = Path(cargo).with_name("rustc") if cargo else None
        if rustc is None or not rustc.is_file():
            self.skipTest("local Rust compiler is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "build-script"
            subprocess.run([str(rustc), "--edition=2024", str(ROOT / "build.rs"), "-o", str(script)], check=True)
            (root / "Cargo.toml.orig").touch()
            output = root / "out"
            output.mkdir()
            environment = os.environ | {
                "CARGO_MANIFEST_DIR": str(root),
                "OUT_DIR": str(output),
                "CARGO_CFG_TARGET_OS": "macos",
                "CARGO_CFG_TARGET_ARCH": "aarch64",
            }

            def run_script() -> subprocess.CompletedProcess[str]:
                return subprocess.run([str(script)], cwd=root, env=environment, capture_output=True, text=True)

            self.assertNotEqual(run_script().returncode, 0)
            for name in ("native/sdk-compatibility.json", "native/sdk-runtime-root.pub", *LIBRARIES):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            self.assertEqual(run_script().returncode, 0)
            (root / "native/sdk-runtime-root.pub").write_bytes(b"")
            self.assertNotEqual(run_script().returncode, 0)
            (root / "native/sdk-runtime-root.pub").write_bytes(b"fixture")
            (root / LIBRARIES[0]).write_bytes(b"")
            self.assertNotEqual(run_script().returncode, 0)

    def test_cargo_lists_the_verification_marker_and_all_staged_runtime_libraries(self) -> None:
        cargo = os.environ.get("CODEX_AGENT_TEST_CARGO") or shutil.which("cargo")
        if cargo is None:
            self.skipTest("local Cargo is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "rust"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns("target", "__pycache__"))
            for name in LIBRARIES:
                path = source / name
                path.parent.mkdir(parents=True)
                path.write_bytes(b"fixture")
            shutil.copyfile(ROOT_KEY, source / "native/sdk-runtime-root.pub")
            result = subprocess.run(
                [cargo, "package", "--list", "--locked", "--offline", "--allow-dirty"],
                cwd=source, capture_output=True, text=True, check=True,
            )
            members = set(result.stdout.splitlines())
            self.assertIn("Cargo.toml.orig", members)
            self.assertIn("native/sdk-compatibility.json", members)
            self.assertIn("native/sdk-runtime-root.pub", members)
            self.assertTrue(set(LIBRARIES) <= members)

    def test_extracted_crate_rejects_tampered_default_and_unauthenticated_override(self) -> None:
        cargo = os.environ.get("CODEX_AGENT_TEST_CARGO") or shutil.which("cargo")
        if cargo is None:
            self.skipTest("local Cargo is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary).resolve()
            source = work / "rust"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns("target", "__pycache__"))
            for name in LIBRARIES:
                path = source / name
                path.parent.mkdir(parents=True)
                path.write_bytes(b"fixture")
            shutil.copyfile(ROOT_KEY, source / "native/sdk-runtime-root.pub")
            subprocess.run(
                [cargo, "package", "--no-verify", "--locked", "--offline", "--allow-dirty"],
                cwd=source, capture_output=True, text=True, check=True,
            )
            sdk_version = json.loads((source / "native/sdk-compatibility.json").read_bytes())["sdkVersion"]
            archive = source / f"target/package/codex-agent-{sdk_version}.crate"
            extracted = work / "installed"
            extracted.mkdir()
            with tarfile.open(archive, "r:gz") as package:
                names = package.getnames()
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(all(name.startswith(f"codex-agent-{sdk_version}/") and ".." not in Path(name).parts
                                    for name in names))
                self.assertTrue(all(member.isfile() or member.isdir() for member in package.getmembers()))
                package.extractall(extracted, filter="data")
            installed = extracted / f"codex-agent-{sdk_version}"
            compatibility = json.loads((installed / "native/sdk-compatibility.json").read_bytes())
            package = tomllib.loads((installed / "Cargo.toml").read_text())["package"]
            self.assertEqual("codex-agent", package["name"])
            self.assertEqual(compatibility["sdkVersion"], package["version"])
            self.assertEqual(f"codex-agent-{package['version']}", installed.name)
            self.assertEqual((installed / "native/sdk-runtime-root.pub").read_bytes(), ROOT_KEY.read_bytes())
            consumer = work / "consumer"
            (consumer / "src").mkdir(parents=True)
            (consumer / "Cargo.toml").write_text(
                '[package]\nname = "installed-rust-security-smoke"\nversion = "0.0.0"\n'
                f'edition = "2024"\n[dependencies]\ncodex-agent = {{ path = "../installed/codex-agent-{sdk_version}" }}\n'
            )
            (consumer / "src/main.rs").write_text(
                'fn main() {\n'
                '  let error = codex_agent::CodexNativeLibrary::load_default()\n'
                '    .err().expect("untrusted Runtime must reject");\n'
                '  let expected = if std::env::var_os("CODEX_AGENT_LIBRARY").is_some() {\n'
                '    "trusted release evidence"\n'
                '  } else {\n'
                '    "embedded Runtime library digest differs"\n'
                '  };\n'
                '  assert!(error.to_string().contains(expected), "{error}");\n'
                '  let path = std::env::args().nth(1).expect("library path");\n'
                '  let direct = codex_agent::CodexNativeLibrary::load(path).err().expect("must reject");\n'
                '  assert!(direct.to_string().contains("trusted release evidence"), "{direct}");\n'
                '}\n'
            )
            library = work / "unauthenticated.dylib"
            library.write_bytes(b"not a native library")
            environment = os.environ | {"RUSTC": str(Path(cargo).with_name("rustc"))}
            environment.pop("CODEX_AGENT_LIBRARY", None)
            if os.name != "nt":
                cargo_home = work / "cargo-home"
                (cargo_home / "registry").mkdir(parents=True)
                original_registry = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "registry"
                for name in ("cache", "index"):
                    (cargo_home / "registry" / name).symlink_to(original_registry / name, target_is_directory=True)
                environment["CARGO_HOME"] = str(cargo_home)
            for override in (False, True):
                if override:
                    environment["CODEX_AGENT_LIBRARY"] = str(library)
                result = subprocess.run(
                    [cargo, "run", "--offline", "--quiet", "--", str(library)],
                    cwd=consumer, env=environment,
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
