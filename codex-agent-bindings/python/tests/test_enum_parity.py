from __future__ import annotations

import csv
import json
import os
import shlex
import subprocess
import sys
import unittest
from enum import IntEnum
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
from artifact_inputs import canonical_api_report, c_include_directory  # noqa: E402


CLAIMS_HEADER = (
    "capabilityKey",
    "publicSymbols",
    "executedTests",
    "compilerEvidenceIds",
    "sharedScenarios",
)
EVIDENCE_DIRECTORY = ROOT / "build" / "cross-language-evidence"


def _exact_list(value: str, label: str) -> tuple[str, ...]:
    if not value:
        raise AssertionError(f"{label} must not be empty")
    entries = tuple(value.split(","))
    if any(not entry for entry in entries):
        raise AssertionError(f"{label} contains an empty entry")
    if list(entries) != sorted(set(entries)):
        raise AssertionError(f"{label} must be sorted and duplicate-free")
    return entries


def _validate_claim_rows(
    rows: list[list[str]], canonical_capabilities: set[str]
) -> tuple[list[str], list[str], list[str]]:
    if len(rows) != len(canonical_capabilities):
        raise AssertionError("claim count must equal the canonical capability count")
    if not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("every claim must contain five nonempty columns")
    capability_keys = [row[0] for row in rows]
    if capability_keys != sorted(set(capability_keys)):
        raise AssertionError("capability keys must be sorted and duplicate-free")
    if set(capability_keys) != canonical_capabilities:
        raise AssertionError("claims contain a stale or missing canonical capability")

    claimed_symbols = [
        symbol for row in rows for symbol in _exact_list(row[1], "publicSymbols")
    ]
    claimed_tests = [
        test for row in rows for test in _exact_list(row[2], "executedTests")
    ]
    claimed_compiler_evidence = [
        evidence
        for row in rows
        for evidence in _exact_list(row[3], "compilerEvidenceIds")
    ]
    for row in rows:
        if len(_exact_list(row[1], "publicSymbols")) != 1:
            raise AssertionError(f"{row[0]} must name one public enum symbol")
        if len(_exact_list(row[2], "executedTests")) != 1:
            raise AssertionError(f"{row[0]} must name one independently executed test")
        if len(_exact_list(row[3], "compilerEvidenceIds")) != 1:
            raise AssertionError(f"{row[0]} must name one compiler-evidence ID")
        if _exact_list(row[4], "sharedScenarios") != ("value-conversion",):
            raise AssertionError(f"{row[0]} must execute value-conversion")
    if len(set(claimed_symbols)) != len(rows):
        raise AssertionError("public symbols must be unique")
    if len(set(claimed_tests)) != len(rows):
        raise AssertionError("executed test IDs must be unique")
    if len(set(claimed_compiler_evidence)) != len(rows):
        raise AssertionError("compiler-evidence IDs must be unique")
    return claimed_symbols, claimed_tests, claimed_compiler_evidence


def _compile_header_values() -> list[int]:
    output_directory = ROOT / "build" / "enum-evidence"
    output_directory.mkdir(parents=True, exist_ok=True)
    executable = output_directory / (
        "codex-agent-enum-evidence.exe" if os.name == "nt" else "codex-agent-enum-evidence"
    )
    source = ROOT / "tests" / "enum_evidence.c"
    include = c_include_directory()
    compiler = shlex.split(os.environ.get("CC", "cl" if os.name == "nt" else "cc"))
    if Path(compiler[0]).name.lower() in {"cl", "cl.exe"}:
        command = [
            *compiler,
            "/nologo",
            "/std:c11",
            "/W4",
            "/WX",
            f"/I{include}",
            str(source),
            f"/Fe:{executable}",
        ]
    else:
        command = [
            *compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(include),
            str(source),
            "-o",
            str(executable),
        ]
    compile_result = subprocess.run(
        command,
        cwd=output_directory,
        check=False,
        capture_output=True,
        text=True,
    )
    if compile_result.returncode != 0:
        raise AssertionError(f"C-header enum evidence compilation failed:\n{compile_result.stderr}")
    run_result = subprocess.run(
        [executable],
        check=False,
        capture_output=True,
        text=True,
    )
    if run_result.returncode != 0:
        raise AssertionError(f"C-header enum evidence execution failed:\n{run_result.stderr}")
    try:
        return [int(value) for value in run_result.stdout.splitlines()]
    except ValueError as error:
        raise AssertionError("C-header enum evidence must contain only i32 values") from error


def _write_lf_tsv(path: Path, header: tuple[str, str], rows: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(sorted(rows))


class OrdinaryEnumParityTests(unittest.TestCase):
    def test_malformed_claims_fail_closed(self) -> None:
        with self.assertRaises(AssertionError):
            _validate_claim_rows(
                [["capability", "codex_agent.Type.VALUE", "test", "evidence"]],
                {"capability"},
            )
        with self.assertRaises(AssertionError):
            _exact_list("evidence,,other", "compilerEvidenceIds")

    def test_duplicate_claims_fail_closed(self) -> None:
        row = [
            "capability",
            "codex_agent.Type.VALUE",
            "python.enum.Type.VALUE",
            "c-header-enum:0",
            "value-conversion",
        ]
        with self.assertRaises(AssertionError):
            _validate_claim_rows([row, row], {"capability", "other"})

    def test_stale_claims_fail_closed(self) -> None:
        row = [
            "removed-capability",
            "codex_agent.Type.VALUE",
            "python.enum.Type.VALUE",
            "c-header-enum:0",
            "value-conversion",
        ]
        with self.assertRaises(AssertionError):
            _validate_claim_rows([row], {"current-capability"})

    def test_all_canonical_enum_entries_have_exact_python_and_c_header_evidence(self) -> None:
        compiler_output = EVIDENCE_DIRECTORY / "compiler-evidence.tsv"
        tests_output = EVIDENCE_DIRECTORY / "executed-tests.tsv"
        compiler_output.unlink(missing_ok=True)
        tests_output.unlink(missing_ok=True)

        canonical_report = json.loads(
            canonical_api_report().read_text(encoding="utf-8")
        )
        canonical_capabilities = [
            capability
            for owner in canonical_report["owners"]
            for capability in owner["capabilities"]
        ]
        self.assertEqual(len(canonical_capabilities), 556)
        canonical_enums = {
            capability
            for capability in canonical_capabilities
            if "|kind=enum-entry|" in capability
        }
        self.assertEqual(len(canonical_enums), 110)

        with (ROOT / "parity" / "capability-claims.tsv").open(
            newline="", encoding="utf-8"
        ) as claims_file:
            claims_reader = csv.reader(claims_file, delimiter="\t", strict=True)
            self.assertEqual(tuple(next(claims_reader)), CLAIMS_HEADER)
            rows = [
                row
                for row in claims_reader
                if "|kind=enum-entry|" in row[0]
            ]
        claimed_symbols, claimed_tests, claimed_compiler_evidence = _validate_claim_rows(
            rows, canonical_enums
        )

        claimed_types = {symbol.split(".")[1] for symbol in claimed_symbols}
        self.assertEqual(len(claimed_types), 30)
        discovered_symbols: set[str] = set()
        for type_name in claimed_types:
            enum_type = getattr(codex_agent, type_name, None)
            self.assertIsInstance(enum_type, type)
            self.assertTrue(issubclass(enum_type, IntEnum))
            self.assertIn(type_name, codex_agent.__all__)
            discovered_symbols.update(
                f"codex_agent.{type_name}.{member_name}"
                for member_name in enum_type.__members__
            )
        self.assertEqual(discovered_symbols, set(claimed_symbols))

        header_values = _compile_header_values()
        self.assertEqual(len(header_values), 110)
        executed_tests: set[str] = set()
        executed_compiler_evidence: dict[str, str] = {}
        executed_scenarios: set[tuple[str, str]] = set()
        for index, row in enumerate(rows):
            capability = row[0]
            symbols = _exact_list(row[1], "publicSymbols")
            tests = _exact_list(row[2], "executedTests")
            compiler_evidence = _exact_list(row[3], "compilerEvidenceIds")
            scenarios = _exact_list(row[4], "sharedScenarios")
            self.assertEqual(len(symbols), 1, capability)
            self.assertEqual(len(tests), 1, capability)
            self.assertEqual(compiler_evidence, (f"c-header-enum:{index}",), capability)
            self.assertEqual(scenarios, ("value-conversion",), capability)

            package_name, type_name, member_name = symbols[0].split(".")
            self.assertEqual(package_name, "codex_agent", capability)
            enum_type = getattr(codex_agent, type_name)
            self.assertIn(member_name, enum_type.__members__, capability)
            member = enum_type.__members__[member_name]
            self.assertEqual(member.name, member_name, f"{tests[0]}: aliases are not evidence")
            self.assertEqual(
                member.value,
                header_values[index],
                f"{tests[0]}: Python value differs from the exact public C-header constant",
            )
            self.assertNotIn(tests[0], executed_tests)
            executed_tests.add(tests[0])
            self.assertNotIn(compiler_evidence[0], executed_compiler_evidence)
            executed_compiler_evidence[compiler_evidence[0]] = symbols[0]
            self.assertNotIn((capability, scenarios[0]), executed_scenarios)
            executed_scenarios.add((capability, scenarios[0]))

        self.assertEqual(executed_tests, set(claimed_tests))
        self.assertEqual(set(executed_compiler_evidence), set(claimed_compiler_evidence))
        self.assertEqual(len(executed_scenarios), 110)

        _write_lf_tsv(
            compiler_output,
            ("compilerEvidenceId", "publicSymbols"),
            list(executed_compiler_evidence.items()),
        )
        _write_lf_tsv(
            tests_output,
            ("executedTestId", "status"),
            [(test, "passed") for test in executed_tests],
        )
        for output in (compiler_output, tests_output):
            self.assertNotIn(b"\r", output.read_bytes())
            data_lines = output.read_text(encoding="utf-8").splitlines()[1:]
            self.assertEqual(data_lines, sorted(data_lines))
            self.assertEqual(len(data_lines), 110)


if __name__ == "__main__":
    unittest.main()
