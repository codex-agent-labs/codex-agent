from __future__ import annotations

import csv
import ctypes
import inspect
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import unittest
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import codex_agent  # noqa: E402
from codex_agent._errors import check  # noqa: E402
from codex_agent._ffi import Handle, HandlePointer, NativeLibrary  # noqa: E402
from codex_agent._mcp_native import read_owned_mcp_server  # noqa: E402
import test_enum_parity as enum_parity  # noqa: E402


OWNER_TYPES = {
    "AgentMcpEnvironmentVariable": "McpEnvironmentVariable",
    "AgentMcpOauthConfiguration": "McpOauthConfiguration",
    "AgentMcpServer": "McpServer",
    "AgentMcpServerConfiguration": "McpServerConfiguration",
    "AgentMcpToolConfiguration": "McpToolConfiguration",
    "AgentMcpTransport.Http": "McpHttpTransport",
    "AgentMcpTransport.Stdio": "McpStdioTransport",
}
OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"


def _owner(capability: str) -> str | None:
    return next(
        (
            owner
            for owner in OWNER_TYPES
            if capability.startswith(f"{OWNER_PREFIX}{owner}|")
        ),
        None,
    )


def _claims() -> list[list[str]]:
    with (ROOT / "parity" / "capability-claims.tsv").open(
        newline="", encoding="utf-8"
    ) as claims_file:
        reader = csv.reader(claims_file, delimiter="\t", strict=True)
        if tuple(next(reader)) != enum_parity.CLAIMS_HEADER:
            raise AssertionError("unexpected claims header")
        rows = list(reader)
    if not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("every claim must contain five nonempty columns")
    if [row[0] for row in rows] != sorted({row[0] for row in rows}):
        raise AssertionError("capability claims must be sorted and duplicate-free")
    for row in rows:
        for index, label in (
            (1, "publicSymbols"),
            (2, "executedTests"),
            (3, "compilerEvidenceIds"),
            (4, "sharedScenarios"),
        ):
            enum_parity._exact_list(row[index], label)
    return rows


def _validate_value_rows(rows: list[list[str]], canonical: set[str]) -> None:
    if len(rows) != 46:
        raise AssertionError("exactly 46 MCP immutable-value claims are required")
    if not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("each MCP claim must have five nonempty columns")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)):
        raise AssertionError("MCP claims must be sorted and duplicate-free")
    if not set(keys).issubset(canonical):
        raise AssertionError("MCP claims contain a stale capability")


def _verify_reference_row(
    row: list[str],
    bootstrap_claims: dict[str, dict[str, object]],
    passed_native_tests: set[str],
    header: str,
) -> tuple[str, ...]:
    capability = row[0]
    bootstrap_claim = bootstrap_claims.get(capability)
    if bootstrap_claim is None:
        raise AssertionError(f"missing C ABI bootstrap claim: {capability}")
    evidence = enum_parity._exact_list(row[3], "compilerEvidenceIds")
    expected_evidence = {
        *(f"c-header:{name}" for name in bootstrap_claim["headerReferences"]),
        *(f"cabi-fixture:{test}" for test in bootstrap_claim["nativeTestIds"]),
    }
    if set(evidence) != expected_evidence:
        raise AssertionError(f"inexact C ABI evidence for {capability}")
    for evidence_id in evidence:
        if evidence_id.startswith("c-header:"):
            name = evidence_id.removeprefix("c-header:")
            if re.search(rf"\b{re.escape(name)}\s*\(", header) is None:
                raise AssertionError(f"stale C-header evidence: {evidence_id}")
        elif evidence_id.startswith("cabi-fixture:"):
            if evidence_id.removeprefix("cabi-fixture:") not in passed_native_tests:
                raise AssertionError(f"stale C ABI fixture evidence: {evidence_id}")
        else:
            raise AssertionError(f"unknown evidence kind: {evidence_id}")
    return evidence


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    scenarios = {"value-conversion"}
    if "?" in capability:
        scenarios.add("nullability")
    if "kotlin.collections" in capability:
        scenarios.add("collection-immutability-ordering")
    return tuple(sorted(scenarios))


def _selected(graph: tuple[object, object, object], owner: str) -> object:
    rich, stdio, _ = graph
    if owner == "AgentMcpServer":
        return rich
    if owner == "AgentMcpServerConfiguration":
        return rich.configuration
    if owner == "AgentMcpTransport.Http":
        return rich.configuration.transport
    if owner == "AgentMcpTransport.Stdio":
        return stdio.configuration.transport
    if owner == "AgentMcpOauthConfiguration":
        return rich.configuration.oauth
    if owner == "AgentMcpToolConfiguration":
        return rich.configuration.tools["tool"]
    if owner == "AgentMcpEnvironmentVariable":
        return stdio.configuration.transport.forwarded_environment[0]
    raise AssertionError(f"unknown owner {owner}")


def _expected_graph() -> tuple[object, object, object]:
    http = codex_agent.McpHttpTransport(
        "https://example.com/mcp",
        "TOKEN_ENV",
        {"X-A": "one", "X-B": "two"},
        {"Authorization": "AUTH_HEADER"},
        "/usr/bin/headers-helper",
    )
    http_configuration = codex_agent.McpServerConfiguration(
        "server_1",
        http,
        codex_agent.McpAuthentication.OAUTH,
        "local",
        True,
        False,
        True,
        (
            codex_agent.McpToolExposureSurface.CODE_MODE,
            codex_agent.McpToolExposureSurface.DIRECT,
        ),
        1.5,
        2.5,
        codex_agent.McpToolApproval.WRITES,
        ("one", "one"),
        (),
        ("scope-a", "scope-a"),
        codex_agent.McpOauthConfiguration("", 65535),
        "",
        {"tool": codex_agent.McpToolConfiguration(codex_agent.McpToolApproval.PROMPT)},
    )
    stdio_transport = codex_agent.McpStdioTransport(
        "node",
        ("server.js", "--flag", "--flag"),
        "/workspace",
        {"A": "1", "B": "2"},
        (
            codex_agent.McpEnvironmentVariable(
                "REMOTE_TOKEN", codex_agent.McpEnvironmentSource.REMOTE
            ),
        ),
    )
    stdio_configuration = codex_agent.McpServerConfiguration(
        "server_1",
        stdio_transport,
        environment_id="local",
        is_enabled=False,
        is_required=True,
    )
    sparse_configuration = codex_agent.McpServerConfiguration(
        "server_1",
        codex_agent.McpHttpTransport("http://127.0.0.1:7777/mcp"),
        omit_tools_from=(),
        enabled_tools=(),
        disabled_tools=(),
        scopes=(),
    )
    return (
        codex_agent.McpServer(
            "server_1",
            "Server One",
            codex_agent.McpAuthStatus.OAUTH,
            http_configuration,
            codex_agent.ResourceOrigin.PLUGIN,
            True,
        ),
        codex_agent.McpServer(
            "server_1",
            "Server One",
            codex_agent.McpAuthStatus.UNKNOWN,
            stdio_configuration,
            codex_agent.ResourceOrigin.USER,
        ),
        codex_agent.McpServer(
            "server_1",
            "Server One",
            codex_agent.McpAuthStatus.UNKNOWN,
            sparse_configuration,
            codex_agent.ResourceOrigin.USER,
        ),
    )


def _sdk_path() -> Path:
    configured = os.environ.get("CODEX_AGENT_LIBRARY")
    if configured:
        result = Path(configured).expanduser().resolve()
    else:
        machine = platform.machine().lower()
        architecture = "Arm64" if machine in {"arm64", "aarch64"} else "X64"
        system = platform.system().lower()
        target = {"darwin": "macos", "linux": "linux"}.get(system)
        if target is None:
            raise AssertionError(f"real MCP value fixture is unsupported on {system}")
        name = "libcodex_agent.dylib" if system == "darwin" else "libcodex_agent.so"
        result = (
            ROOT.parents[1]
            / "build"
            / "bin"
            / f"{target}{architecture}"
            / "releaseShared"
            / name
        )
    if not result.is_file():
        raise AssertionError(f"real Codex Agent SDK is missing: {result}")
    return result


def _compile_fixture(sdk: Path) -> Path:
    directory = ROOT / "build" / "mcp-value-evidence"
    directory.mkdir(parents=True, exist_ok=True)
    system = platform.system().lower()
    output = directory / (
        "libcodex_agent_python_fixture.dylib"
        if system == "darwin"
        else "libcodex_agent_python_fixture.so"
    )
    command = [
        *shlex.split(os.environ.get("CC", "cc")),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-dynamiclib" if system == "darwin" else "-shared",
    ]
    if system != "darwin":
        command.append("-fPIC")
    command.extend(
        [
            "-I",
            str(ROOT.parents[1] / "native" / "c-api" / "include"),
            str(ROOT / "tests" / "real_mcp_value_fixture.c"),
            str(sdk),
            f"-Wl,-rpath,{sdk.parent}",
            "-o",
            str(output),
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(f"real MCP fixture compilation failed:\n{result.stderr}")
    return output


def _native_graph() -> tuple[object, object, object]:
    sdk = _sdk_path()
    native = NativeLibrary.load(sdk)
    fixture = ctypes.CDLL(str(_compile_fixture(sdk)))
    create = fixture.codex_agent_test_mcp_server_fixture
    create.argtypes = [
        Handle,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
        HandlePointer,
    ]
    create.restype = ctypes.c_int32
    context = Handle()
    native.call("codex_agent_context_create", ctypes.byref(context))
    try:
        servers: list[object] = []
        for variant in range(3):
            stage = ctypes.c_int32()
            server = Handle()
            check(
                int(
                    create(context, variant, ctypes.byref(stage), ctypes.byref(server))
                ),
                f"create real MCP fixture variant {variant} at stage {stage.value}",
            )
            servers.append(read_owned_mcp_server(native, context, server))
        return tuple(servers)  # type: ignore[return-value]
    finally:
        native.call("codex_agent_context_destroy", ctypes.byref(context))


class McpValueParityTests(unittest.TestCase):
    def test_malformed_duplicate_and_stale_value_evidence_fails_closed(self) -> None:
        rows = _claims()
        self.assertEqual(len(rows), 556)
        value_rows = [row for row in rows if _owner(row[0]) is not None]
        canonical = {row[0] for row in value_rows}
        with self.assertRaises(AssertionError):
            _validate_value_rows([*value_rows[:-1], value_rows[-1][:-1]], canonical)
        with self.assertRaises(AssertionError):
            _validate_value_rows([*value_rows[:-1], value_rows[-2]], canonical)
        stale = [*value_rows[-1]]
        stale[0] = "common|owner=removed/Stale|kind=property|abi=removed"
        with self.assertRaises(AssertionError):
            _validate_value_rows([*value_rows[:-1], stale], canonical)

        bootstrap = json.loads(
            (
                ROOT.parents[1]
                / "build"
                / "reports"
                / "cross-language-api"
                / "c-abi"
                / "bootstrap-evidence.json"
            ).read_text(encoding="utf-8")
        )
        passed = {
            test["testId"]
            for test in bootstrap["nativeTests"]
            if test["status"] == "passed"
        }
        bootstrap_claims = {
            claim["capabilityKey"]: claim for claim in bootstrap["claims"]
        }
        header = (
            ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
        ).read_text(encoding="utf-8")
        stale_fixture = [*value_rows[0]]
        stale_fixture[3] = stale_fixture[3].replace(
            next(
                item
                for item in stale_fixture[3].split(",")
                if item.startswith("cabi-fixture:")
            ),
            "cabi-fixture:removed.native.test#stale[macosArm64]",
        )
        with self.assertRaises(AssertionError):
            _verify_reference_row(stale_fixture, bootstrap_claims, passed, header)
        stale_header = [*value_rows[0]]
        stale_header[3] = stale_header[3].replace(
            next(
                item
                for item in stale_header[3].split(",")
                if item.startswith("c-header:")
            ),
            "c-header:codex_agent_removed_stale_symbol",
        )
        with self.assertRaises(AssertionError):
            _verify_reference_row(stale_header, bootstrap_claims, passed, header)

    def test_exact_mcp_value_parity_and_complete_evidence(self) -> None:
        enum_parity.OrdinaryEnumParityTests(
            "test_all_canonical_enum_entries_have_exact_python_and_c_header_evidence"
        ).test_all_canonical_enum_entries_have_exact_python_and_c_header_evidence()

        rows = _claims()
        enum_rows = [row for row in rows if "|kind=enum-entry|" in row[0]]
        value_rows = [row for row in rows if _owner(row[0]) is not None]
        self.assertEqual((len(rows), len(enum_rows), len(value_rows)), (556, 110, 46))

        canonical_report = json.loads(
            (
                ROOT.parents[2]
                / "codex-agent-core"
                / "build"
                / "reports"
                / "cross-language-api"
                / "canonical-api.json"
            ).read_text(encoding="utf-8")
        )
        canonical = {
            capability
            for owner in canonical_report["owners"]
            for capability in owner["capabilities"]
        }
        self.assertEqual(len(canonical), 556)
        _validate_value_rows(value_rows, canonical)
        self.assertTrue(
            {row[0] for row in enum_rows + value_rows}.issubset(
                {row[0] for row in rows}
            )
        )
        self.assertTrue({row[0] for row in rows}.issubset(canonical))

        bootstrap = json.loads(
            (
                ROOT.parents[1]
                / "build"
                / "reports"
                / "cross-language-api"
                / "c-abi"
                / "bootstrap-evidence.json"
            ).read_text(encoding="utf-8")
        )
        bootstrap_claims = {
            claim["capabilityKey"]: claim for claim in bootstrap["claims"]
        }
        passed_native_tests = {
            test["testId"]
            for test in bootstrap["nativeTests"]
            if test["status"] == "passed"
        }
        header = (
            ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
        ).read_text(encoding="utf-8")

        expected = _expected_graph()
        actual = _native_graph()
        self.assertEqual(actual, expected)
        sparse_configuration = actual[2].configuration
        self.assertEqual(sparse_configuration.omit_tools_from, ())
        self.assertEqual(sparse_configuration.enabled_tools, ())
        self.assertEqual(sparse_configuration.disabled_tools, ())
        self.assertEqual(sparse_configuration.scopes, ())
        self.assertIsNone(sparse_configuration.oauth)
        self.assertIsNone(sparse_configuration.oauth_resource)
        self.assertIsNone(sparse_configuration.transport.headers)

        executed_value_tests: set[str] = set()
        value_compiler_evidence: dict[str, set[str]] = defaultdict(set)
        for row in value_rows:
            capability, symbol_cell, test_cell, evidence_cell, scenario_cell = row
            owner = _owner(capability)
            self.assertIsNotNone(owner, capability)
            symbols = enum_parity._exact_list(symbol_cell, "publicSymbols")
            tests = enum_parity._exact_list(test_cell, "executedTests")
            evidence = _verify_reference_row(
                row, bootstrap_claims, passed_native_tests, header
            )
            self.assertEqual(len(symbols), 1, capability)
            self.assertEqual(len(tests), 1, capability)
            self.assertEqual(
                enum_parity._exact_list(scenario_cell, "sharedScenarios"),
                _expected_scenarios(capability),
                capability,
            )

            for evidence_id in evidence:
                value_compiler_evidence[evidence_id].add(symbols[0])

            type_name = OWNER_TYPES[owner]
            public_type = getattr(codex_agent, type_name)
            self.assertIn(type_name, codex_agent.__all__)
            actual_owner = _selected(actual, owner)
            expected_owner = _selected(expected, owner)
            if "|kind=constructor|" in capability:
                self.assertEqual(symbols[0], f"codex_agent.{type_name}", capability)
                self.assertTrue(callable(public_type), capability)
                self.assertGreater(
                    len(inspect.signature(public_type).parameters), 0, capability
                )
                self.assertIsInstance(actual_owner, public_type, capability)
            else:
                member = symbols[0].rsplit(".", 1)[1]
                self.assertEqual(
                    symbols[0], f"codex_agent.{type_name}.{member}", capability
                )
                self.assertTrue(hasattr(public_type, member), capability)
                self.assertEqual(
                    getattr(actual_owner, member),
                    getattr(expected_owner, member),
                    capability,
                )
            self.assertNotIn(tests[0], executed_value_tests, capability)
            executed_value_tests.add(tests[0])

        self.assertEqual(len(executed_value_tests), 46)
        self.assertEqual(executed_value_tests, {row[2] for row in value_rows})

        arguments = ["one"]
        environment = {"A": "1"}
        transport = codex_agent.McpStdioTransport(
            "node", arguments, environment=environment
        )
        arguments[0] = "changed"
        environment["A"] = "changed"
        self.assertEqual(transport.arguments, ("one",))
        self.assertEqual(dict(transport.environment), {"A": "1"})
        with self.assertRaises(TypeError):
            transport.environment["B"] = "2"
        with self.assertRaises(ValueError):
            codex_agent.McpHttpTransport("http://example.com")
        with self.assertRaises(ValueError):
            codex_agent.McpHttpTransport("http://localhost.evil.example/mcp")
        with self.assertRaises(ValueError):
            codex_agent.McpHttpTransport("https:///missing-host")
        with self.assertRaises(ValueError):
            codex_agent.McpHttpTransport("https://mcp.example.com:invalid")
        with self.assertRaises(ValueError):
            codex_agent.McpHttpTransport("https://%ZZ")
        codex_agent.McpHttpTransport("https://mcp.example.com:443/path")
        codex_agent.McpHttpTransport("http://[::1]:8080/mcp")
        with self.assertRaises(ValueError):
            codex_agent.McpOauthConfiguration(callback_port=0)

        compiler_rows: dict[str, str] = {}
        with (enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv").open(
            newline="", encoding="utf-8"
        ) as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows.update(reader)
        for evidence_id, symbols in value_compiler_evidence.items():
            self.assertNotIn(evidence_id, compiler_rows)
            compiler_rows[evidence_id] = ",".join(sorted(symbols))

        executed_tests: set[str] = set()
        with (enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv").open(
            newline="", encoding="utf-8"
        ) as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            for test_id, status in reader:
                self.assertEqual(status, "passed")
                executed_tests.add(test_id)
        executed_tests.update(executed_value_tests)

        proven_rows = enum_rows + value_rows
        claimed_evidence = {
            evidence_id
            for row in proven_rows
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds")
        }
        claimed_tests = {
            test_id
            for row in proven_rows
            for test_id in enum_parity._exact_list(row[2], "executedTests")
        }
        self.assertEqual(set(compiler_rows), claimed_evidence)
        self.assertEqual(executed_tests, claimed_tests)
        enum_parity._write_lf_tsv(
            enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv",
            ("compilerEvidenceId", "publicSymbols"),
            list(compiler_rows.items()),
        )
        enum_parity._write_lf_tsv(
            enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv",
            ("executedTestId", "status"),
            [(test, "passed") for test in executed_tests],
        )
        for path in (
            enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv",
            enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv",
        ):
            contents = path.read_bytes()
            self.assertNotIn(b"\r", contents)
            lines = contents.decode("utf-8").splitlines()[1:]
            self.assertEqual(lines, sorted(lines))


if __name__ == "__main__":
    unittest.main()
