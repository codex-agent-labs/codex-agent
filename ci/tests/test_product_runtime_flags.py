from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from ci.products.runtime_flags import (
    TARGETS,
    describe_all_runtime_binary_flags,
    describe_runtime_binary_flags,
    load_runtime_binary_flags,
    verify_runtime_binary_flags,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = REPOSITORY_ROOT / "codex-agent-runtime-desktop/native/c-api/binary-flags.json"


class ProductRuntimeFlagsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.value = load_canonical_json_bytes(AUTHORITY.read_bytes())
        self.path = self.root / "binary-flags.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, value: dict[str, object] | None = None) -> Path:
        self.path.write_bytes(canonical_json_bytes(self.value if value is None else value))
        return self.path

    def target(self, value: dict[str, object], target: str) -> dict[str, object]:
        return next(record for record in value["targets"] if record["target"] == target)

    def test_tracked_authority_matches_the_exact_product_controlled_options(self) -> None:
        loaded = load_runtime_binary_flags(AUTHORITY)
        self.assertEqual(TARGETS, tuple(loaded))
        self.assertTrue(all(not record.compiler_arguments for record in loaded.values()))
        for target in ("linux-arm64", "linux-x64", "macos-arm64", "macos-x64"):
            self.assertEqual(
                ("-std=c11", "-D_POSIX_C_SOURCE=200809L", "-O2", "-Wall", "-Wextra", "-Werror"),
                loaded[target].supervisor_compiler_arguments,
            )
        self.assertEqual(
            ("/nologo", "/O2", "/W4", "/WX"),
            loaded["windows-x64"].supervisor_compiler_arguments,
        )
        for target in ("linux-arm64", "linux-x64"):
            self.assertEqual(
                ("-Wl,--version-script,@role(exportPolicy)", "-Wl,-soname,libcodex_agent.so.1"),
                loaded[target].linker_arguments,
            )
        for target in ("macos-arm64", "macos-x64"):
            self.assertEqual(
                (
                    "-Wl,-exported_symbols_list,@role(exportPolicy)",
                    "-Wl,-install_name,@rpath/libcodex_agent.dylib",
                    "-Wl,-compatibility_version,1.0.0",
                    "-Wl,-current_version,1.13.0",
                ),
                loaded[target].linker_arguments,
            )
        windows = loaded["windows-x64"]
        self.assertEqual(
            (
                "-Wl,--exclude-all-symbols",
                "-Wl,--out-implib,@role(gnuImportLibraryOutput)",
                "@role(exportPolicy)",
            ),
            windows.linker_arguments,
        )
        self.assertEqual(
            (
                ("nologo", None),
                ("machine", "x64"),
                ("brepro", None),
                ("def", "@role(exportPolicy)"),
                ("out", "@role(msvcImportLibraryOutput)"),
            ),
            windows.msvc_import_library_options,
        )
        self.assertTrue(all(record.digest == sha256_bytes(record._canonical) for record in loaded.values()))
        self.assertEqual(5, len({record.digest for record in loaded.values()}))

    def test_describe_and_verify_cli_require_and_report_the_explicit_file(self) -> None:
        expected = verify_runtime_binary_flags(AUTHORITY)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(REPOSITORY_ROOT))
        verified = subprocess.run(
            [sys.executable, "-m", "ci.products.runtime_flags", "verify", "--file", str(AUTHORITY)],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(expected, json.loads(verified.stdout))
        described = subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products.runtime_flags",
                "describe",
                "--file",
                str(AUTHORITY),
                "--target",
                "windows-x64",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(describe_runtime_binary_flags(AUTHORITY, "windows-x64"), json.loads(described.stdout))
        described_all = subprocess.run(
            [
                sys.executable,
                "-m",
                "ci.products.runtime_flags",
                "describe-all",
                "--file",
                str(AUTHORITY),
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(describe_all_runtime_binary_flags(AUTHORITY), json.loads(described_all.stdout))

    def test_schema_target_role_argument_and_option_mutations_fail_closed(self) -> None:
        cases = []
        missing = copy.deepcopy(self.value); missing.pop("targets"); cases.append(missing)
        extra = copy.deepcopy(self.value); extra["profile"] = "mutable"; cases.append(extra)
        old = copy.deepcopy(self.value); old["schemaVersion"] = 0; cases.append(old)
        reversed_targets = copy.deepcopy(self.value); reversed_targets["targets"].reverse(); cases.append(reversed_targets)
        duplicate_target = copy.deepcopy(self.value); duplicate_target["targets"][1] = copy.deepcopy(duplicate_target["targets"][0]); cases.append(duplicate_target)
        unknown_target = copy.deepcopy(self.value); unknown_target["targets"][0]["target"] = "linux-riscv64"; cases.append(unknown_target)
        target_extra = copy.deepcopy(self.value); target_extra["targets"][0]["extra"] = True; cases.append(target_extra)
        duplicate_argument = copy.deepcopy(self.value); duplicate_argument["targets"][0]["linkerArguments"] *= 2; cases.append(duplicate_argument)
        non_string_argument = copy.deepcopy(self.value); non_string_argument["targets"][0]["compilerArguments"] = [1]; cases.append(non_string_argument)
        compiler_role = copy.deepcopy(self.value); compiler_role["targets"][0]["compilerArguments"] = ["@role(exportPolicy)"]; cases.append(compiler_role)
        supervisor_role = copy.deepcopy(self.value); supervisor_role["targets"][0]["supervisorCompilerArguments"] = ["@role(exportPolicy)"]; cases.append(supervisor_role)
        missing_role = copy.deepcopy(self.value); missing_role["targets"][0]["roles"] = []; cases.append(missing_role)
        unused_role = copy.deepcopy(self.value); unused_role["targets"][0]["linkerArguments"][0] = "-Wl,--version-script"; cases.append(unused_role)
        wrong_base = copy.deepcopy(self.value); wrong_base["targets"][0]["roles"][0]["base"] = "output"; cases.append(wrong_base)
        unsorted_roles = copy.deepcopy(self.value); unsorted_roles["targets"][-1]["roles"].reverse(); cases.append(unsorted_roles)
        duplicate_role = copy.deepcopy(self.value); duplicate_role["targets"][-1]["roles"].append(copy.deepcopy(duplicate_role["targets"][-1]["roles"][0])); cases.append(duplicate_role)
        msvc_on_linux = copy.deepcopy(self.value); msvc_on_linux["targets"][0]["msvcImportLibraryOptions"] = [{"name": "nologo", "value": None}]; cases.append(msvc_on_linux)
        no_windows_msvc = copy.deepcopy(self.value); no_windows_msvc["targets"][-1]["msvcImportLibraryOptions"] = []; cases.append(no_windows_msvc)
        duplicate_option = copy.deepcopy(self.value); duplicate_option["targets"][-1]["msvcImportLibraryOptions"].append({"name": "out", "value": "safe"}); cases.append(duplicate_option)
        bad_option_name = copy.deepcopy(self.value); bad_option_name["targets"][-1]["msvcImportLibraryOptions"][0]["name"] = "/nologo"; cases.append(bad_option_name)
        for index, value in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    load_runtime_binary_flags(self.write(value))

    def test_paths_and_unresolved_placeholders_are_rejected(self) -> None:
        unsafe_arguments = (
            "-Wl,-rpath,/tmp/runtime",
            "-Wl,-rpath,C:/Users/runner/runtime",
            "-Wl,-rpath,../runtime",
            "-Wl,-rpath,folder\\runtime",
            "-Wl,-rpath,$HOME/runtime",
            "-Wl,-rpath,{runtime}",
            "-Wl,-rpath,%TEMP%",
            "-Wl,-rpath,file:///tmp/runtime",
            "@role(unknownRole)",
            "@role(exportPolicy",
            "-Wl,-rpath,@unknown/runtime",
            "-Wl,-rpath,@rpath/runtime",
        )
        for argument in unsafe_arguments:
            value = copy.deepcopy(self.value)
            self.target(value, "linux-x64")["linkerArguments"].append(argument)
            with self.subTest(argument=argument), self.assertRaises(ValueError):
                load_runtime_binary_flags(self.write(value))

        for path in ("/tmp/policy", "../policy", "native\\policy", "C:/policy", "native//policy"):
            value = copy.deepcopy(self.value)
            self.target(value, "linux-x64")["roles"][0]["relativePath"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                load_runtime_binary_flags(self.write(value))

    def test_one_target_flag_change_changes_only_that_target_digest(self) -> None:
        before = load_runtime_binary_flags(AUTHORITY)
        value = copy.deepcopy(self.value)
        self.target(value, "linux-x64")["linkerArguments"].append("-Wl,--gc-sections")
        after = load_runtime_binary_flags(self.write(value))
        self.assertNotEqual(before["linux-x64"].digest, after["linux-x64"].digest)
        self.assertEqual(
            {target: before[target].digest for target in TARGETS if target != "linux-x64"},
            {target: after[target].digest for target in TARGETS if target != "linux-x64"},
        )

    def test_noncanonical_duplicate_key_and_symbolic_inputs_fail(self) -> None:
        self.path.write_text(json.dumps(self.value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            load_runtime_binary_flags(self.path)

        self.path.write_bytes(b'{"schemaVersion":1,"schemaVersion":1,"targets":[]}\n')
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            load_runtime_binary_flags(self.path)

        link = self.root / "linked-flags.json"
        try:
            link.symlink_to(AUTHORITY)
        except OSError:
            self.skipTest("symbolic links are unavailable")
        with self.assertRaises(ValueError):
            load_runtime_binary_flags(link)


if __name__ == "__main__":
    unittest.main()
