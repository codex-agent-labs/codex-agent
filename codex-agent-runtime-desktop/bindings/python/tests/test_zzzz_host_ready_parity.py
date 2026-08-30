from __future__ import annotations

import asyncio
import csv
import ctypes
import inspect
import os
import re
import runpy
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import get_type_hints

import codex_agent
from codex_agent._errors import ClosedError, NativeStatusError, OperationError, Status
from codex_agent._ffi import (
    Handle,
    HandlePointer,
    HostOptionsStruct,
    NativeLibrary,
    OperationCallback,
    PathWorkspaceSelectionStruct,
    StateCallback,
)
import test_enum_parity as enum_parity
import test_ordinary_value_parity as ordinary_parity
from test_binding import _set_handle, _set_i32
from test_z_leaf_service_parity import (
    MissingSymbolLibrary,
    _bootstrap,
    _expected_argtypes,
    _null_argument,
    _real_library_path,
)
from test_zzz_agent_parity import AgentFakeLibrary


ROOT = Path(__file__).resolve().parents[1]
HOST_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHost|"
READY_PREFIX = (
    "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHostState.Ready|"
)
PUBLIC = {
    "CodexHostState.Ready.<init>": "codex_agent.HostStateReady",
    "CodexHostState.Ready.agent": "codex_agent.HostStateReady.agent",
    "CodexHost.<init>": "codex_agent.CodexHost",
    "CodexHost.close": "codex_agent.CodexHost.aclose",
    "CodexHost.selectWorkspace": "codex_agent.CodexHost.select_workspace",
    "CodexHost.start": "codex_agent.CodexHost.start",
    "CodexHost.lifecycleState": "codex_agent.CodexHost.state",
}
SCENARIOS = {
    "CodexHostState.Ready.<init>": (
        "identity",
        "parent-child-ownership",
        "value-conversion",
    ),
    "CodexHostState.Ready.agent": (
        "identity",
        "parent-child-ownership",
        "value-conversion",
    ),
    "CodexHost.<init>": ("parent-child-ownership", "value-conversion"),
    "CodexHost.close": (
        "async-failure",
        "async-success",
        "cancellation",
        "parent-child-ownership",
        "repeated-close-dispose",
        "structured-failure",
        "value-conversion",
    ),
    "CodexHost.selectWorkspace": (
        "async-failure",
        "async-success",
        "cancellation",
        "parent-child-ownership",
        "structured-failure",
        "value-conversion",
    ),
    "CodexHost.start": (
        "async-failure",
        "async-success",
        "cancellation",
        "parent-child-ownership",
        "structured-failure",
        "value-conversion",
    ),
    "CodexHost.lifecycleState": (
        "identity",
        "parent-child-ownership",
        "state-current-value",
        "state-subsequent-value",
        "subscription-cancellation",
        "terminal-delivery",
        "value-conversion",
    ),
}


def _member(capability: str) -> str:
    marker = "|abi=io.github.codex_agent_labs.codexagent.agent/"
    if (
        not capability.startswith((HOST_PREFIX, READY_PREFIX))
        or marker not in capability
    ):
        raise AssertionError(f"not a Host/Ready capability: {capability}")
    return capability.split(marker, 1)[1].split("|", 1)[0]


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if row[0].startswith((HOST_PREFIX, READY_PREFIX))]


def _function_references(header: str, references: list[str]) -> set[str]:
    return {
        reference
        for reference in references
        if re.search(rf"\b{re.escape(reference)}\s*\(", header)
    }


def _validate_rows(rows: list[list[str]]) -> None:
    bootstrap, passed, header = _bootstrap()
    canonical = {
        key for key in bootstrap if key.startswith((HOST_PREFIX, READY_PREFIX))
    }
    if len(rows) != 7 or not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("exactly seven complete Host/Ready claims are required")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError(
            "Host/Ready claims contain a stale, missing, or duplicate key"
        )
    for index, row in enumerate(rows):
        capability, symbols, tests, evidence, scenarios = row
        member = _member(capability)
        claim = bootstrap[capability]
        if enum_parity._exact_list(symbols, "publicSymbols") != (PUBLIC[member],):
            raise AssertionError(f"stale Python projection: {capability}")
        if enum_parity._exact_list(tests, "executedTests") != (
            f"python.host:{index:03d}",
        ):
            raise AssertionError(f"stale executed-test ID: {capability}")
        expected_evidence = tuple(
            sorted(
                [f"c-header:{name}" for name in claim["headerReferences"]]
                + [f"cabi-fixture:{test}" for test in claim["nativeTestIds"]]
                + [f"python-analyzer-host:{index:03d}"]
            )
        )
        if (
            enum_parity._exact_list(evidence, "compilerEvidenceIds")
            != expected_evidence
        ):
            raise AssertionError(
                f"stale exact compiler/reference evidence: {capability}"
            )
        if enum_parity._exact_list(scenarios, "sharedScenarios") != SCENARIOS[member]:
            raise AssertionError(f"stale semantic scenarios: {capability}")
        for reference in claim["headerReferences"]:
            if not re.search(rf"\b{re.escape(reference)}\b", header):
                raise AssertionError(f"missing exact C header reference: {reference}")
        if not set(claim["nativeTestIds"]).issubset(passed):
            raise AssertionError(f"canonical C behavior did not pass: {capability}")


def _view(value: object) -> str:
    if not value.data or not value.size:
        return ""
    return ctypes.string_at(value.data, value.size).decode("utf-8")


class HostReadyFake(AgentFakeLibrary):
    expected_options = ("bundle", "data", "test", "Test", "1")

    def __init__(self) -> None:
        super().__init__()
        self.copied_options: list[tuple[str, str, str, str, str]] = []
        self.copied_selections: list[str] = []
        self.expected_selection = "/workspace/exact"
        self.snapshot_kinds: dict[int, codex_agent.HostStateKind] = {}
        self.host_state_terminal = True
        self.last_state_callback: tuple[object, object, Handle] | None = None

    def _snapshot(self, kind: codex_agent.HostStateKind) -> Handle:
        self.handle_seed += 1
        self.snapshot_kinds[self.handle_seed] = kind
        return Handle(self.handle_seed)

    def invoke(self, name: str, *args: object) -> int:
        if name == "codex_agent_host_create":
            self.calls.append(name)
            options = ctypes.cast(args[1], ctypes.POINTER(HostOptionsStruct)).contents
            copied = (
                _view(options.bundle_directory),
                _view(options.data_directory),
                _view(options.client_info.name),
                _view(options.client_info.title),
                _view(options.client_info.version),
            )
            self.copied_options.append(copied)
            if copied != self.expected_options:
                return Status.INVALID_ARGUMENT
            self._fresh(args[2])
            return Status.OK
        if name == "codex_agent_host_state_get":
            self.calls.append(name)
            snapshot = self._snapshot(codex_agent.HostStateKind.NEW)
            _set_handle(args[-1], snapshot.value)
            return Status.OK
        if name == "codex_agent_host_state_subscribe":
            self.calls.append(name)
            callback, user_data, out = args[-3:]
            self._fresh(out)
            subscription = Handle(self.handle_seed)
            self.last_state_callback = (callback, user_data, subscription)
            ready = self._snapshot(codex_agent.HostStateKind.READY)
            callback(Handle(1), subscription, Status.OK, ready, 0, user_data)
            if self.host_state_terminal:
                closed = self._snapshot(codex_agent.HostStateKind.CLOSED)
                callback(Handle(1), subscription, Status.OK, closed, 1, user_data)
            return Status.OK
        if name == "codex_agent_host_state_kind":
            self.calls.append(name)
            _set_i32(args[-1], int(self.snapshot_kinds[int(args[1].value)]))
            return Status.OK
        if name == "codex_agent_host_state_has_workspace":
            self.calls.append(name)
            _set_i32(args[-1], 0)
            return Status.OK
        if name == "codex_agent_host_state_agent":
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if name in {
            "codex_agent_host_start",
            "codex_agent_host_select_workspace",
            "codex_agent_host_close",
        }:
            self.calls.append(name)
            if name == "codex_agent_host_select_workspace":
                selection = ctypes.cast(
                    args[2], ctypes.POINTER(PathWorkspaceSelectionStruct)
                ).contents
                copied = _view(selection.path)
                self.copied_selections.append(copied)
                if copied != self.expected_selection:
                    return Status.INVALID_ARGUMENT
            callback, user_data, out = args[-3:]
            self._fresh(out)
            if self.delay_operation:
                self.delayed_callback = (callback, user_data)
            else:
                callback(Handle(1), Handle(self.handle_seed), user_data)
            return Status.OK
        return super().invoke(name, *args)

    def emit_after_cancel(self) -> None:
        assert self.last_state_callback is not None
        callback, user_data, subscription = self.last_state_callback
        ready = self._snapshot(codex_agent.HostStateKind.READY)
        callback(Handle(1), subscription, Status.OK, ready, 0, user_data)


def _host(
    fake: HostReadyFake | None = None,
) -> tuple[codex_agent.CodexHost, HostReadyFake]:
    library = fake or HostReadyFake()
    host = codex_agent.CodexHost(
        "bundle",
        "data",
        codex_agent.ClientInfo("test", "Test", "1"),
        _native=NativeLibrary(library),
    )
    return host, library


async def _operation_semantics(
    host: codex_agent.CodexHost,
    fake: HostReadyFake,
    action: object,
) -> None:
    fake.next_operation_result = Status.OPERATION_FAILED
    with unittest.TestCase().assertRaises(OperationError) as raised:
        await action()
    unittest.TestCase().assertEqual(raised.exception.status, Status.OPERATION_FAILED)
    unittest.TestCase().assertEqual(raised.exception.failure.code, "fixture")
    unittest.TestCase().assertEqual(raised.exception.failure.message, "fixture")
    unittest.TestCase().assertTrue(raised.exception.failure.is_recoverable)

    fake.next_operation_result = Status.OK
    fake.delay_operation = True
    fake.operation_cancelled = False
    task = asyncio.create_task(action())
    await asyncio.sleep(0)
    task.cancel()
    with unittest.TestCase().assertRaises(asyncio.CancelledError):
        await task
    unittest.TestCase().assertTrue(fake.operation_cancelled)
    fake.complete_delayed()
    await asyncio.sleep(0.01)

    fake.delay_operation = False
    await action()


async def _ready_state(host: codex_agent.CodexHost) -> codex_agent.HostStateReady:
    subscription = host.state.subscribe()
    state = await anext(subscription)
    unittest.TestCase().assertIsInstance(state, codex_agent.HostStateReady)
    return state


async def _exercise(capability: str) -> set[str]:
    member = _member(capability)
    if member == "CodexHost.<init>":
        host, fake = _host()
        unittest.TestCase().assertEqual(fake.copied_options, [fake.expected_options])
        for copied in (
            ("wrong-bundle", "data", "test", "Test", "1"),
            ("bundle", "wrong-data", "test", "Test", "1"),
            ("bundle", "data", "wrong-name", "Test", "1"),
            ("bundle", "data", "test", "Wrong title", "1"),
            ("bundle", "data", "test", "Test", "wrong-version"),
        ):
            rejected = HostReadyFake()
            with unittest.TestCase().assertRaises(NativeStatusError):
                codex_agent.CodexHost(
                    copied[0],
                    copied[1],
                    codex_agent.ClientInfo(*copied[2:]),
                    _native=NativeLibrary(rejected),
                )
            unittest.TestCase().assertEqual(rejected.copied_options, [copied])
        calls = set(fake.calls)
        await host.aclose()
        return calls

    host, fake = _host()
    fake.calls.clear()
    if member in {"CodexHostState.Ready.<init>", "CodexHostState.Ready.agent"}:
        ready = await _ready_state(host)
        subsequent = await _ready_state(host)
        unittest.TestCase().assertIs(ready.agent, subsequent.agent)
        unittest.TestCase().assertIs(ready.agent, ready.agent)
        projected = codex_agent.HostStateReady(ready.agent)
        unittest.TestCase().assertEqual(projected.kind, codex_agent.HostStateKind.READY)
        unittest.TestCase().assertIs(projected.agent, ready.agent)
        calls = set(fake.calls)
        await host.aclose()
        with unittest.TestCase().assertRaises(ClosedError):
            ready.agent._require()
        await ready.agent.aclose()
        return calls

    if member == "CodexHost.lifecycleState":
        current = host.state.current
        unittest.TestCase().assertEqual(current.kind, codex_agent.HostStateKind.NEW)
        subscription = host.state.subscribe()
        ready = await anext(subscription)
        closed = await anext(subscription)
        unittest.TestCase().assertIsInstance(ready, codex_agent.HostStateReady)
        unittest.TestCase().assertEqual(closed.kind, codex_agent.HostStateKind.CLOSED)
        unittest.TestCase().assertIs(ready.agent, ready.agent)
        with unittest.TestCase().assertRaises(StopAsyncIteration):
            await anext(subscription)

        fake.host_state_terminal = False
        cancelled = host.state.subscribe()
        subsequent = await anext(cancelled)
        unittest.TestCase().assertIsInstance(subsequent, codex_agent.HostStateReady)
        unittest.TestCase().assertIs(ready.agent, subsequent.agent)
        await cancelled.aclose()
        await cancelled.aclose()
        with unittest.TestCase().assertRaises(StopAsyncIteration):
            await anext(cancelled)
        fake.emit_after_cancel()
        await asyncio.sleep(0)
        unittest.TestCase().assertTrue(cancelled.queue.empty())
        calls = set(fake.calls)
        await host.aclose()
        with unittest.TestCase().assertRaises(ClosedError):
            ready.agent._require()
        await ready.agent.aclose()
        await subsequent.agent.aclose()
        return calls

    if member == "CodexHost.selectWorkspace":
        with unittest.TestCase().assertRaises(NativeStatusError):
            await host.select_workspace("/wrong")
        unittest.TestCase().assertEqual(fake.copied_selections, ["/wrong"])
        await _operation_semantics(
            host, fake, lambda: host.select_workspace(fake.expected_selection)
        )
        unittest.TestCase().assertEqual(
            fake.copied_selections[-3:], [fake.expected_selection] * 3
        )
    elif member == "CodexHost.start":
        await _operation_semantics(host, fake, host.start)
    elif member == "CodexHost.close":
        await _operation_semantics(host, fake, host.aclose)
        await host.aclose()
        await host.close()
        return set(fake.calls)
    else:
        raise AssertionError(member)
    calls = set(fake.calls)
    await host.aclose()
    return calls


def _compile_host_surface() -> None:
    source = """
#include "codex_agent.h"
_Static_assert(CODEX_AGENT_HOST_STATE_READY == 4, "ready state drifted");
static void python_host_surface(void) {
    codex_agent_host_options_t options = {0};
    (void)options;
}
int main(void) { python_host_surface(); return 0; }
"""
    include = ROOT.parents[1] / "native/c-api/include"
    compiler = shlex.split(os.environ.get("CC", "cl" if os.name == "nt" else "cc"))
    with tempfile.TemporaryDirectory() as directory:
        source_path = Path(directory) / "host_surface.c"
        object_path = Path(directory) / "host_surface.o"
        source_path.write_text(source, encoding="utf-8")
        if Path(compiler[0]).name.lower() in {"cl", "cl.exe"}:
            command = [
                *compiler,
                "/nologo",
                "/std:c11",
                "/W4",
                "/WX",
                f"/I{include}",
                "/c",
                str(source_path),
                f"/Fo{object_path}",
            ]
        else:
            command = [
                *compiler,
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-I",
                str(include),
                "-c",
                str(source_path),
                "-o",
                str(object_path),
            ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(f"Host C surface compilation failed:\n{result.stderr}")


def _exact_signature(symbol: str) -> tuple[object, ...]:
    if symbol == "codex_agent_host_create":
        return (Handle, ctypes.POINTER(HostOptionsStruct), HandlePointer)
    if symbol == "codex_agent_host_select_workspace":
        return (
            Handle,
            Handle,
            ctypes.POINTER(PathWorkspaceSelectionStruct),
            OperationCallback,
            ctypes.c_void_p,
            HandlePointer,
        )
    if symbol in {"codex_agent_host_state_kind", "codex_agent_operation_result"}:
        return (Handle, Handle, ctypes.POINTER(ctypes.c_int32))
    _, _, header = _bootstrap()
    return _expected_argtypes(header, symbol)


class HostReadyParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_consumer_lifecycle_example_runs_public_flow(self) -> None:
        host, fake = _host()
        example = runpy.run_path(str(ROOT / "consumer/lifecycle_example.py"))
        await example["run"](host)
        await host.aclose()
        self.assertTrue(
            {
                "codex_agent_host_start",
                "codex_agent_host_state_subscribe",
                "codex_agent_host_state_agent",
                "codex_agent_agent_conversations",
                "codex_agent_conversations_open",
                "codex_agent_conversation_send",
                "codex_agent_conversation_close",
                "codex_agent_host_close",
            }.issubset(fake.calls)
        )

    def test_exact_inventory_public_surface_and_reference_evidence(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        _compile_host_surface()
        self.assertTrue(issubclass(codex_agent.HostStateReady, codex_agent.HostState))
        self.assertEqual(
            inspect.signature(codex_agent.HostStateReady)
            .parameters["agent"]
            .annotation,
            "CodexAgent",
        )
        self.assertEqual(
            codex_agent.HostStateReady.__annotations__["agent"], "CodexAgent"
        )
        self.assertTrue(inspect.iscoroutinefunction(codex_agent.CodexHost.aclose))
        self.assertTrue(inspect.iscoroutinefunction(codex_agent.CodexHost.start))
        self.assertTrue(
            inspect.iscoroutinefunction(codex_agent.CodexHost.select_workspace)
        )
        state = inspect.getattr_static(codex_agent.CodexHost, "state")
        self.assertIsInstance(state, property)
        self.assertEqual(
            get_type_hints(state.fget)["return"],
            codex_agent.StateStream[codex_agent.HostState],
        )

    async def test_each_capability_executes_exact_production_ctypes_calls(self) -> None:
        bootstrap, _, header = _bootstrap()
        for row in _selected_rows(ordinary_parity._claims()):
            with self.subTest(capability=row[0]):
                calls = await _exercise(row[0])
                functions = _function_references(
                    header, bootstrap[row[0]]["headerReferences"]
                )
                self.assertTrue(functions.issubset(calls), functions - calls)

    def test_real_sdk_executes_every_exact_function_at_fail_closed_null_boundary(
        self,
    ) -> None:
        path = _real_library_path()
        self.assertTrue(path.is_file(), f"real release SDK is required: {path}")
        native = NativeLibrary(ctypes.CDLL(path))
        bootstrap, _, header = _bootstrap()
        executed: set[str] = set()
        for row in _selected_rows(ordinary_parity._claims()):
            for symbol in _function_references(
                header, bootstrap[row[0]]["headerReferences"]
            ):
                function = native.function(symbol)
                self.assertEqual(tuple(function.argtypes), _exact_signature(symbol))
                status = int(
                    function(
                        *(_null_argument(argument) for argument in function.argtypes)
                    )
                )
                self.assertNotEqual(status, int(Status.OK), symbol)
                executed.add(symbol)
        self.assertEqual(
            executed,
            {
                "codex_agent_host_close",
                "codex_agent_host_create",
                "codex_agent_host_select_workspace",
                "codex_agent_host_start",
                "codex_agent_host_state_agent",
                "codex_agent_host_state_get",
                "codex_agent_host_state_kind",
                "codex_agent_host_state_subscribe",
                "codex_agent_operation_result",
            },
        )

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
            (2, "python.host:999"),
            (3, "python-analyzer-host:999"),
            (4, "value-conversion"),
        ):
            candidate = [row[:] for row in rows]
            candidate[0][column] = stale
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)

        bootstrap, _, header = _bootstrap()
        for row in rows:
            calls = await _exercise(row[0])
            for symbol in _function_references(
                header, bootstrap[row[0]]["headerReferences"]
            ):
                disconnected = set(calls)
                disconnected.discard(symbol)
                self.assertFalse(
                    _function_references(
                        header, bootstrap[row[0]]["headerReferences"]
                    ).issubset(disconnected)
                )
                with self.assertRaises(AttributeError):
                    NativeLibrary(MissingSymbolLibrary(symbol))

    async def test_z_complete_556_row_evidence_is_exact(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        bootstrap, _, header = _bootstrap()
        compiler_additions: dict[str, set[str]] = {}
        executed_additions: set[str] = set()
        for row in rows:
            calls = await _exercise(row[0])
            self.assertTrue(
                _function_references(
                    header, bootstrap[row[0]]["headerReferences"]
                ).issubset(calls)
            )
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

        all_rows = ordinary_parity._claims()
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
        scenarios = {
            scenario
            for row in all_rows
            for scenario in enum_parity._exact_list(row[4], "sharedScenarios")
        }
        self.assertEqual((len(all_rows), len(claimed_tests)), (556, 556))
        self.assertEqual(len(scenarios), 14)
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
