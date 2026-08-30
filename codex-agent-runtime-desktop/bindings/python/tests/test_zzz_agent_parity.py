from __future__ import annotations

import csv
import ctypes
import inspect
import re
import unittest
from typing import get_type_hints

import codex_agent
from codex_agent._ffi import Handle, NativeLibrary, StringView
from codex_agent._errors import Status
import test_enum_parity as enum_parity
import test_ordinary_value_parity as ordinary_parity
from test_binding import _set_handle, _set_size
from test_z_leaf_service_parity import (
    MissingSymbolLibrary,
    _bootstrap,
    _expected_argtypes,
    _null_argument,
    _real_library_path,
)
from test_zz_conversation_parity import ConversationFakeLibrary


OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexAgent|"
SNAKE = {
    "integrationAuthorization": "integration_authorization",
    "mcpServers": "mcp_servers",
}
GETTERS = {
    "authentication": "codex_agent_agent_authentication",
    "connectors": "codex_agent_agent_connectors",
    "conversations": "codex_agent_agent_conversations",
    "hooks": "codex_agent_agent_hooks",
    "integrationAuthorization": "codex_agent_agent_integration_authorization",
    "interactions": "codex_agent_agent_interactions",
    "mcpServers": "codex_agent_agent_mcp_servers",
    "models": "codex_agent_agent_models",
    "plugins": "codex_agent_agent_plugins",
    "skills": "codex_agent_agent_skills",
    "workspace": "codex_agent_agent_workspace",
}


def _member(capability: str) -> str:
    marker = "|abi=io.github.codex_agent_labs.codexagent.agent/CodexAgent."
    if not capability.startswith(OWNER_PREFIX) or marker not in capability:
        raise AssertionError(f"not an Agent capability: {capability}")
    return capability.split(marker, 1)[1].split("|", 1)[0]


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if row[0].startswith(OWNER_PREFIX)]


def _public_symbol(capability: str) -> str:
    member = _member(capability)
    return f"codex_agent.CodexAgent.{SNAKE.get(member, member)}"


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    scenarios = {"parent-child-ownership", "value-conversion"}
    if _member(capability) != "workspace":
        scenarios.add("identity")
    return tuple(sorted(scenarios))


def _validate_rows(rows: list[list[str]]) -> None:
    bootstrap, passed, header = _bootstrap()
    canonical = {key for key in bootstrap if key.startswith(OWNER_PREFIX)}
    if len(rows) != 11 or not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("exactly 11 complete Agent claims are required")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError("Agent claims contain a stale, missing, or duplicate key")
    for index, row in enumerate(rows):
        capability, symbols, tests, evidence, scenarios = row
        claim = bootstrap[capability]
        if enum_parity._exact_list(symbols, "publicSymbols") != (
            _public_symbol(capability),
        ):
            raise AssertionError(f"stale Python projection: {capability}")
        if enum_parity._exact_list(tests, "executedTests") != (
            f"python.agent:{index:03d}",
        ):
            raise AssertionError(f"stale executed-test ID: {capability}")
        expected_evidence = tuple(
            sorted(
                [f"c-header:{name}" for name in claim["headerReferences"]]
                + [f"cabi-fixture:{test}" for test in claim["nativeTestIds"]]
                + [f"python-analyzer-agent:{index:03d}"]
            )
        )
        if (
            enum_parity._exact_list(evidence, "compilerEvidenceIds")
            != expected_evidence
        ):
            raise AssertionError(
                f"stale exact compiler/reference evidence: {capability}"
            )
        if enum_parity._exact_list(scenarios, "sharedScenarios") != _expected_scenarios(
            capability
        ):
            raise AssertionError(f"stale semantic scenarios: {capability}")
        for reference in claim["headerReferences"]:
            if not re.search(rf"\b{re.escape(reference)}\b", header):
                raise AssertionError(f"missing exact C header reference: {reference}")
        if not set(claim["nativeTestIds"]).issubset(passed):
            raise AssertionError(f"canonical C behavior did not pass: {capability}")


class AgentFakeLibrary(ConversationFakeLibrary):
    def invoke(self, name: str, *args: object) -> int:
        if name in GETTERS.values():
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if name == "codex_agent_workspace_destroy":
            self.calls.append(name)
            _set_handle(args[-1], None)
            return Status.OK
        if name in {
            "codex_agent_workspace_path_copy",
            "codex_agent_workspace_display_name_copy",
        }:
            self.calls.append(name)
            value = b"/workspace" if name.endswith("path_copy") else b"Workspace"
            buffer, capacity, required = args[-3:]
            _set_size(required, len(value))
            if len(value) > int(capacity):
                return Status.BUFFER_TOO_SMALL
            ctypes.memmove(buffer, value, len(value))
            return Status.OK
        return super().invoke(name, *args)


async def _exercise(capability: str) -> set[str]:
    fake = AgentFakeLibrary()
    host = codex_agent.CodexHost(
        "bundle",
        "data",
        codex_agent.ClientInfo("test", "Test", "1"),
        _native=NativeLibrary(fake),
    )
    await host.start()
    agent = host.state.current.agent
    assert agent is not None
    fake.calls.clear()
    member = _member(capability)
    public_name = SNAKE.get(member, member)
    try:
        projection = getattr(agent, public_name)
        if member == "workspace":
            unittest.TestCase().assertEqual(
                projection, codex_agent.Workspace("/workspace", "Workspace")
            )
            await agent.aclose()
            unittest.TestCase().assertEqual(projection.path, "/workspace")
        else:
            unittest.TestCase().assertIs(projection, getattr(agent, public_name))
            await agent.aclose()
            await projection.aclose()
            unittest.TestCase().assertFalse(projection._handle.value)
        return set(fake.calls)
    finally:
        await agent.aclose()
        await host.aclose()


class AgentParityTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_inventory_public_surface_and_reference_evidence(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        for capability, symbols, *_ in rows:
            projected = enum_parity._exact_list(symbols, "publicSymbols")[0].rsplit(
                ".", 1
            )[1]
            member = inspect.getattr_static(codex_agent.CodexAgent, projected)
            self.assertIsInstance(member, property)
            self.assertIn("return", get_type_hints(member.fget))

    async def test_each_capability_executes_exact_production_ctypes_calls(self) -> None:
        bootstrap, _, _ = _bootstrap()
        for row in _selected_rows(ordinary_parity._claims()):
            with self.subTest(capability=row[0]):
                calls = await _exercise(row[0])
                self.assertTrue(
                    set(bootstrap[row[0]]["headerReferences"]).issubset(calls)
                )

    def test_real_sdk_executes_every_exact_symbol_at_fail_closed_null_boundary(
        self,
    ) -> None:
        path = _real_library_path()
        self.assertTrue(path.is_file(), f"real release SDK is required: {path}")
        native = NativeLibrary(ctypes.CDLL(path))
        bootstrap, _, header = _bootstrap()
        executed: set[str] = set()
        for row in _selected_rows(ordinary_parity._claims()):
            for symbol in bootstrap[row[0]]["headerReferences"]:
                function = native.function(symbol)
                self.assertEqual(
                    tuple(function.argtypes), _expected_argtypes(header, symbol)
                )
                status = int(
                    function(*(_null_argument(arg) for arg in function.argtypes))
                )
                self.assertNotEqual(status, int(Status.OK), symbol)
                executed.add(symbol)
        self.assertEqual(executed, set(GETTERS.values()))

    async def test_stale_missing_and_disconnected_evidence_fail_closed(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        for candidate in (
            rows[:-1],
            [*rows[:-1], rows[-2]],
            [["removed", *rows[0][1:]], *rows[1:]],
        ):
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)
        for column, stale in (
            (1, "codex_agent.Fallback.local"),
            (2, "python.agent:999"),
            (3, "python-analyzer-agent:999"),
            (4, "value-conversion"),
        ):
            candidate = [row[:] for row in rows]
            candidate[0][column] = stale
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)
        bootstrap, _, _ = _bootstrap()
        calls = await _exercise(rows[0][0])
        calls.remove(bootstrap[rows[0][0]]["headerReferences"][0])
        self.assertFalse(set(bootstrap[rows[0][0]]["headerReferences"]).issubset(calls))
        with self.assertRaises(AttributeError):
            NativeLibrary(
                MissingSymbolLibrary(bootstrap[rows[0][0]]["headerReferences"][0])
            )

    async def test_z_complete_549_row_evidence_is_exact(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        bootstrap, _, _ = _bootstrap()
        compiler_additions: dict[str, set[str]] = {}
        executed_additions: set[str] = set()
        for row in rows:
            calls = await _exercise(row[0])
            self.assertTrue(set(bootstrap[row[0]]["headerReferences"]).issubset(calls))
            symbol = enum_parity._exact_list(row[1], "publicSymbols")[0]
            executed_additions.update(enum_parity._exact_list(row[2], "executedTests"))
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds"):
                compiler_additions.setdefault(evidence_id, set()).add(symbol)

        compiler_path = enum_parity.EVIDENCE_DIRECTORY / "compiler-evidence.tsv"
        with compiler_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["compilerEvidenceId", "publicSymbols"])
            compiler_rows = {
                evidence_id: set(symbols.split(",")) for evidence_id, symbols in reader
            }
        for evidence_id, symbols in compiler_additions.items():
            compiler_rows.setdefault(evidence_id, set()).update(symbols)

        tests_path = enum_parity.EVIDENCE_DIRECTORY / "executed-tests.tsv"
        with tests_path.open(newline="", encoding="utf-8") as evidence_file:
            reader = csv.reader(evidence_file, delimiter="\t", strict=True)
            self.assertEqual(next(reader), ["executedTestId", "status"])
            all_tests = {test for test, status in reader if status == "passed"}
        all_tests.update(executed_additions)

        all_rows = [
            row
            for row in ordinary_parity._claims()
            if not any(
                row[0].startswith(prefix)
                for prefix in (
                    "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHost|",
                    "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHostState.Ready|",
                )
            )
        ]
        claimed_evidence = {
            evidence_id
            for row in all_rows
            for evidence_id in enum_parity._exact_list(row[3], "compilerEvidenceIds")
        }
        claimed_tests = {
            test_id
            for row in all_rows
            for test_id in enum_parity._exact_list(row[2], "executedTests")
        }
        self.assertEqual((len(all_rows), len(claimed_tests)), (549, 549))
        self.assertEqual(set(compiler_rows), claimed_evidence)
        self.assertEqual(all_tests, claimed_tests)
        enum_parity._write_lf_tsv(
            compiler_path,
            ("compilerEvidenceId", "publicSymbols"),
            [
                (evidence_id, ",".join(sorted(symbols)))
                for evidence_id, symbols in compiler_rows.items()
            ],
        )
        enum_parity._write_lf_tsv(
            tests_path,
            ("executedTestId", "status"),
            [(test, "passed") for test in all_tests],
        )
        for path in (compiler_path, tests_path):
            self.assertNotIn(b"\r", path.read_bytes())
            lines = path.read_text(encoding="utf-8").splitlines()[1:]
            self.assertEqual(lines, sorted(lines))


if __name__ == "__main__":
    unittest.main()
