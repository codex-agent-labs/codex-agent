from __future__ import annotations

import csv
import ctypes
import inspect
import re
import unittest
from pathlib import Path
from typing import get_type_hints

import codex_agent
from codex_agent._client import _Context
from codex_agent._ffi import (
    ConversationOpenOptionsStruct,
    Handle,
    NativeLibrary,
    StringView,
)
from codex_agent._errors import Status
import test_enum_parity as enum_parity
import test_ordinary_value_parity as ordinary_parity
from test_binding import _set_handle, _set_i32, _set_size
from test_z_leaf_service_parity import (
    LeafFakeLibrary,
    MissingSymbolLibrary,
    _bootstrap,
    _expected_argtypes,
    _null_argument,
    _real_library_path,
)


OWNER_PREFIX = "common|owner=io.github.codex_agent_labs.codexagent.agent/"
OWNERS = {"CodexConversations", "CodexConversation"}
SNAKE = {
    "activeTurnProgress": "active_turn_progress",
    "canCancelTurn": "can_cancel_turn",
    "canReload": "can_reload",
    "canRunShellCommand": "can_run_shell_command",
    "canStartTurn": "can_start_turn",
    "cancelTurn": "cancel_turn",
    "currentMessages": "current_messages",
    "isTurnActive": "is_turn_active",
    "runShellCommand": "run_shell_command",
}


def _owner(capability: str) -> str | None:
    return next(
        (owner for owner in OWNERS if capability.startswith(f"{OWNER_PREFIX}{owner}|")),
        None,
    )


def _member(capability: str) -> str:
    owner = _owner(capability)
    if owner is None:
        raise AssertionError(f"not a conversation capability: {capability}")
    marker = f"|abi=io.github.codex_agent_labs.codexagent.agent/{owner}."
    return capability.split(marker, 1)[1].split("|", 1)[0]


def _public_symbol(capability: str) -> str:
    owner = _owner(capability)
    assert owner is not None
    member = SNAKE.get(_member(capability), _member(capability))
    projected_owner = "Conversations" if owner == "CodexConversations" else owner
    return f"codex_agent.{projected_owner}.{member}"


def _expected_scenarios(capability: str) -> tuple[str, ...]:
    member = _member(capability)
    scenarios = {"parent-child-ownership", "value-conversion"}
    if "|kind=function|" in capability:
        scenarios.add("async-success")
    if "StateFlow" in capability:
        scenarios.update(
            {
                "state-current-value",
                "state-subsequent-value",
                "subscription-cancellation",
                "terminal-delivery",
            }
        )
    if "kotlin.collections" in capability:
        scenarios.add("collection-immutability-ordering")
    if "?" in capability:
        scenarios.add("nullability")
    if member == "close":
        scenarios.add("repeated-close-dispose")
    if member in {"active", "open"}:
        scenarios.add("identity")
    return tuple(sorted(scenarios))


def _selected_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if _owner(row[0]) is not None]


def _validate_rows(rows: list[list[str]]) -> None:
    bootstrap, passed, header = _bootstrap()
    canonical = {key for key in bootstrap if _owner(key) is not None}
    if len(rows) != 20 or not all(len(row) == 5 and all(row) for row in rows):
        raise AssertionError("exactly 20 complete conversation claims are required")
    keys = [row[0] for row in rows]
    if keys != sorted(set(keys)) or set(keys) != canonical:
        raise AssertionError(
            "conversation claims contain a stale, missing, or duplicate key"
        )
    for index, row in enumerate(rows):
        capability, symbols, tests, evidence, scenarios = row
        claim = bootstrap[capability]
        if enum_parity._exact_list(symbols, "publicSymbols") != (
            _public_symbol(capability),
        ):
            raise AssertionError(f"stale Python projection: {capability}")
        if enum_parity._exact_list(tests, "executedTests") != (
            f"python.conversation:{index:03d}",
        ):
            raise AssertionError(f"stale executed-test ID: {capability}")
        expected_evidence = tuple(
            sorted(
                [f"c-header:{name}" for name in claim["headerReferences"]]
                + [f"cabi-fixture:{test}" for test in claim["nativeTestIds"]]
                + [f"python-analyzer-conversation:{index:03d}"]
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


def _string(pointer: object) -> str:
    view = ctypes.cast(pointer, ctypes.POINTER(StringView)).contents
    if not view.data or not view.size:
        return ""
    return ctypes.string_at(view.data, view.size).decode("utf-8")


class ConversationFakeLibrary(LeafFakeLibrary):
    def __init__(self) -> None:
        super().__init__()
        self.active_present = True
        self.progress_present = True
        self.structured_request_seen = False
        self.input_values: list[str] = []

    def _is_operation_start(self, name: str) -> bool:
        return name in {
            "codex_agent_conversations_read",
            "codex_agent_conversation_send_request",
        } or super()._is_operation_start(name)

    def invoke(self, name: str, *args: object) -> int:
        if name == "codex_agent_host_state_kind":
            self.calls.append(name)
            _set_i32(args[-1], int(codex_agent.HostStateKind.READY))
            return Status.OK
        if name == "codex_agent_host_state_has_workspace":
            self.calls.append(name)
            _set_i32(args[-1], 0)
            return Status.OK
        if name == "codex_agent_host_state_agent":
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if self._is_operation_start(name):
            self.calls.append(name)
            if name in {
                "codex_agent_conversation_send",
                "codex_agent_conversation_run_shell_command",
            }:
                self.input_values.append(_string(args[2]))
            elif name == "codex_agent_conversations_rename":
                self.input_values.append(_string(args[3]))
            elif name == "codex_agent_conversations_open":
                options = ctypes.cast(
                    args[2], ctypes.POINTER(ConversationOpenOptionsStruct)
                ).contents
                if options.has_conversation_id:
                    self.input_values.append(
                        ctypes.string_at(
                            options.conversation_id.data,
                            options.conversation_id.size,
                        ).decode("utf-8")
                    )
            callback, user_data, out = args[-3:]
            self._fresh(out)
            callback(Handle(1), Handle(self.handle_seed), user_data)
            return Status.OK
        state = re.fullmatch(
            r"codex_agent_(conversations_active|conversation_(state|current_messages|"
            r"active_turn_progress|can_cancel_turn|can_reload|can_run_shell_command|"
            r"can_start_turn|is_turn_active))_(get|subscribe)",
            name,
        )
        if state:
            self.calls.append(name)
            if state.group(3) == "get":
                self._fresh(args[-1])
            else:
                callback, user_data, out = args[-3:]
                self._fresh(out)
                callback(
                    Handle(1),
                    Handle(self.handle_seed),
                    Status.OK,
                    Handle(self.handle_seed + 100),
                    int(self.state_terminal),
                    user_data,
                )
            return Status.OK
        if name == "codex_agent_active_conversation":
            self.calls.append(name)
            if not self.active_present:
                return Status.NOT_READY
            _set_handle(args[-1], 5)
            return Status.OK
        if name == "codex_agent_conversation_is_same":
            self.calls.append(name)
            _set_i32(args[-1], int(args[1].value == args[2].value))
            return Status.OK
        if name == "codex_agent_conversation_state_status":
            self.calls.append(name)
            _set_i32(args[-1], int(codex_agent.ConversationStatus.READY))
            return Status.OK
        if name == "codex_agent_operation_conversation_value":
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if name in {
            "codex_agent_conversation_value_summary",
            "codex_agent_conversation_value_message_at",
            "codex_agent_conversation_current_messages_at",
            "codex_agent_message_invocation_at",
            "codex_agent_invocation_plugin",
            "codex_agent_conversation_active_turn_progress_value",
            "codex_agent_turn_progress_plan_progress",
            "codex_agent_plan_progress_step_at",
            "codex_agent_turn_progress_hook_activity_at",
        }:
            self.calls.append(name)
            self._fresh(args[-1])
            return Status.OK
        if name in {
            "codex_agent_conversation_value_messages_count",
            "codex_agent_conversation_current_messages_count",
            "codex_agent_message_invocations_count",
            "codex_agent_message_capabilities_count",
            "codex_agent_plan_progress_steps_count",
            "codex_agent_turn_progress_hook_activities_count",
            "codex_agent_hook_activity_details_count",
        }:
            self.calls.append(name)
            _set_size(args[-1], 1)
            return Status.OK
        if name == "codex_agent_operation_conversation_summaries_count":
            self.calls.append(name)
            _set_size(args[-1], 2)
            return Status.OK
        if name == "codex_agent_message_has_capability":
            self.calls.append(name)
            _set_i32(
                args[-1], int(int(args[-2]) == int(codex_agent.Capability.WEB_SEARCH))
            )
            return Status.OK
        if name in {
            "codex_agent_message_has_client_message_id",
            "codex_agent_message_has_reasoning",
            "codex_agent_message_has_plan",
            "codex_agent_message_has_shell_command",
            "codex_agent_turn_progress_has_plan_progress",
            "codex_agent_plan_progress_has_explanation",
            "codex_agent_hook_activity_has_status_message",
        }:
            self.calls.append(name)
            _set_i32(args[-1], 1)
            return Status.OK
        if name == "codex_agent_conversation_active_turn_progress_has_value":
            self.calls.append(name)
            _set_i32(args[-1], int(self.progress_present))
            return Status.OK
        if name == "codex_agent_message_exit_code":
            self.calls.append(name)
            _set_i32(args[-2], 1)
            _set_i32(args[-1], 7)
            return Status.OK
        if name == "codex_agent_turn_progress_shell_exit_code":
            self.calls.append(name)
            _set_i32(args[-2], 1)
            _set_i32(args[-1], 0)
            return Status.OK
        if name == "codex_agent_turn_progress_work_activity":
            self.calls.append(name)
            _set_i32(args[-2], 1)
            _set_i32(args[-1], int(codex_agent.WorkActivity.RUNNING_COMMAND))
            return Status.OK
        integer_values = {
            "codex_agent_message_role": codex_agent.MessageRole.ASSISTANT,
            "codex_agent_message_collaboration_mode": codex_agent.CollaborationMode.PLAN,
            "codex_agent_invocation_kind": 0,
            "codex_agent_plan_step_status": codex_agent.PlanStepStatus.COMPLETED,
            "codex_agent_hook_activity_status": codex_agent.HookRunStatus.COMPLETED,
            "codex_agent_turn_progress_is_truncated": 1,
        }
        if name in integer_values:
            self.calls.append(name)
            _set_i32(args[-1], int(integer_values[name]))
            return Status.OK
        if name == "codex_agent_turn_request_create":
            self.calls.append(name)
            assert _string(args[1]) == "structured"
            assert tuple(int(args[index]) for index in (2, 4, 6, 8)) == (1, 1, 1, 1)
            assert tuple(_string(args[index]) for index in (3, 5, 7, 9)) == (
                "client-1",
                "model",
                "high",
                "fast",
            )
            assert int(args[10]) == int(codex_agent.ApprovalPreset.ASK_ME)
            assert int(args[12]) == 1
            assert int(args[14]) == 2
            assert int(args[15]) == int(codex_agent.CollaborationMode.PLAN)
            self.structured_request_seen = True
            self._fresh(args[-1])
            return Status.OK
        if name == "codex_agent_hook_activity_detail_copy_at":
            self.calls.append(name)
            return self._copy(name, *args)
        if name in {
            "codex_agent_invocation_plugin_create",
            "codex_agent_invocation_skill_create",
        }:
            self.calls.append(name)
            self.input_values.extend((_string(args[1]), _string(args[2])))
            self._fresh(args[-1])
            return Status.OK
        if name == "codex_agent_conversation_id_create":
            self.calls.append(name)
            self.input_values.append(_string(args[1]))
            self._fresh(args[-1])
            return Status.OK
        return super().invoke(name, *args)

    def _copy(self, name: str, *args: object) -> int:
        values = {
            "codex_agent_message_id_copy": b"message-1",
            "codex_agent_message_client_message_id_copy": b"client-1",
            "codex_agent_message_text_copy": b"hello",
            "codex_agent_message_reasoning_copy": b"because",
            "codex_agent_message_plan_copy": b"plan",
            "codex_agent_message_shell_command_copy": b"pwd",
            "codex_agent_invocation_plugin_name_copy": b"plugin",
            "codex_agent_invocation_plugin_uri_copy": b"plugin://plugin@market",
            "codex_agent_turn_progress_text_copy": b"working",
            "codex_agent_turn_progress_commentary_copy": b"commentary",
            "codex_agent_turn_progress_reasoning_copy": b"reasoning",
            "codex_agent_turn_progress_plan_copy": b"plan",
            "codex_agent_turn_progress_shell_output_copy": b"output",
            "codex_agent_plan_progress_explanation_copy": b"explanation",
            "codex_agent_plan_step_text_copy": b"step",
            "codex_agent_hook_activity_id_copy": b"hook-1",
            "codex_agent_hook_activity_event_name_copy": b"after-turn",
            "codex_agent_hook_activity_handler_type_copy": b"command",
            "codex_agent_hook_activity_status_message_copy": b"done",
            "codex_agent_hook_activity_detail_copy_at": b"detail",
            "codex_agent_conversation_id_value_copy": b"conversation-1",
            "codex_agent_conversation_summary_title_copy": b"Fixture",
        }
        if name not in values:
            return super()._copy(name, *args)
        value = values[name]
        buffer, capacity, required = args[-3:]
        _set_size(required, len(value))
        if len(value) > int(capacity):
            return Status.BUFFER_TOO_SMALL
        if value:
            ctypes.memmove(buffer, value, len(value))
        return Status.OK


async def _exercise_state(
    stream: object, fake: ConversationFakeLibrary
) -> tuple[object, object]:
    current = stream.current
    subscription = stream.subscribe()
    subsequent = await anext(subscription)
    with unittest.TestCase().assertRaises(StopAsyncIteration):
        await anext(subscription)
    fake.state_terminal = False
    cancellable = stream.subscribe()
    await anext(cancellable)
    await cancellable.aclose()
    await cancellable.aclose()
    return current, subsequent


async def _exercise(capability: str) -> set[str]:
    fake = ConversationFakeLibrary()
    host = codex_agent.CodexHost(
        "bundle",
        "data",
        codex_agent.ClientInfo("test", "Test", "1"),
        _native=NativeLibrary(fake),
    )
    await host.start()
    agent = host.state.current.agent
    assert agent is not None
    conversations = agent.conversations
    conversation = await conversations.open()
    fake.calls.clear()
    fake.input_values.clear()
    owner = _owner(capability)
    member = _member(capability)
    try:
        if owner == "CodexConversations":
            if member == "delete":
                await conversations.delete("conversation-1")
                unittest.TestCase().assertIn("conversation-1", fake.input_values)
            elif member == "list":
                summaries = await conversations.list()
                unittest.TestCase().assertEqual(
                    tuple(summary.title for summary in summaries),
                    ("Fixture", "Fixture"),
                )
            elif member == "open":
                opened = await conversations.open(
                    "conversation-2",
                    approval_preset=codex_agent.ApprovalPreset.ASK_ME,
                    service_tier="fast",
                )
                unittest.TestCase().assertIn("conversation-2", fake.input_values)
                unittest.TestCase().assertTrue(opened.is_same(opened))
            elif member == "read":
                value = await conversations.read("conversation-1")
                unittest.TestCase().assertEqual(value.summary.title, "Fixture")
                unittest.TestCase().assertEqual(value.messages[0].text, "hello")
                unittest.TestCase().assertEqual(
                    value.messages[0].invocations[0].name, "plugin"
                )
            elif member == "rename":
                await conversations.rename("conversation-1", "Renamed")
                unittest.TestCase().assertEqual(
                    fake.input_values, ["conversation-1", "Renamed"]
                )
            else:
                current, subsequent = await _exercise_state(conversations.active, fake)
                unittest.TestCase().assertIsNotNone(current)
                unittest.TestCase().assertIsNotNone(subsequent)
                unittest.TestCase().assertTrue(current.is_same(subsequent))
                fake.active_present = False
                unittest.TestCase().assertIsNone(conversations.active.current)
        elif "|kind=function|" in capability:
            if member == "cancelTurn":
                await conversation.cancel_turn()
            elif member == "close":
                await conversation.close()
                await conversation.close()
            elif member == "reload":
                await conversation.reload()
            elif member == "runShellCommand":
                await conversation.run_shell_command("pwd")
                unittest.TestCase().assertIn("pwd", fake.input_values)
            elif "AgentTurnRequest" in capability:
                await conversation.send(
                    codex_agent.TurnRequest(
                        "structured",
                        model="model",
                        effort="high",
                        approval_preset=codex_agent.ApprovalPreset.ASK_ME,
                        service_tier="fast",
                        capabilities={codex_agent.Capability.WEB_SEARCH},
                        collaboration_mode=codex_agent.CollaborationMode.PLAN,
                        invocations=(
                            codex_agent.PluginInvocation(
                                "plugin", "plugin://plugin@market"
                            ),
                            codex_agent.SkillInvocation("skill", "skill.md"),
                        ),
                        client_message_id="client-1",
                    )
                )
                unittest.TestCase().assertTrue(fake.structured_request_seen)
                unittest.TestCase().assertEqual(
                    fake.input_values,
                    ["plugin", "plugin://plugin@market", "skill", "skill.md"],
                )
            else:
                await conversation.send("hello")
                unittest.TestCase().assertIn("hello", fake.input_values)
        else:
            stream = getattr(conversation, SNAKE.get(member, member))
            current, subsequent = await _exercise_state(stream, fake)
            if member == "currentMessages":
                unittest.TestCase().assertEqual(current[0].text, "hello")
                unittest.TestCase().assertEqual(subsequent[0].text, "hello")
            elif member == "activeTurnProgress":
                unittest.TestCase().assertEqual(
                    current.plan_progress.steps[0].text, "step"
                )
                unittest.TestCase().assertEqual(
                    current.hook_activities[0].details, ("detail",)
                )
                unittest.TestCase().assertEqual(
                    subsequent.plan_progress.steps[0].text, "step"
                )
                fake.progress_present = False
                unittest.TestCase().assertIsNone(stream.current)
            elif member == "state":
                unittest.TestCase().assertEqual(
                    current.status, codex_agent.ConversationStatus.READY
                )
                unittest.TestCase().assertEqual(
                    subsequent.status, codex_agent.ConversationStatus.READY
                )
            else:
                unittest.TestCase().assertTrue(current)
                unittest.TestCase().assertTrue(subsequent)
        return set(fake.calls)
    finally:
        await conversation.aclose()
        await conversations.aclose()
        await agent.aclose()
        await host.aclose()


class ConversationParityTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_inventory_public_surface_and_reference_evidence(self) -> None:
        rows = _selected_rows(ordinary_parity._claims())
        _validate_rows(rows)
        for capability, symbols, *_ in rows:
            owner = _owner(capability)
            assert owner is not None
            projected = enum_parity._exact_list(symbols, "publicSymbols")[0].rsplit(
                ".", 1
            )[1]
            projected_owner = (
                "Conversations" if owner == "CodexConversations" else owner
            )
            public = inspect.getattr_static(
                getattr(codex_agent, projected_owner), projected
            )
            target = public.fget if isinstance(public, property) else public
            self.assertIsNotNone(target)
            self.assertIn("return", get_type_hints(target))

    async def test_each_capability_executes_exact_production_ctypes_calls(self) -> None:
        bootstrap, _, _ = _bootstrap()
        for row in _selected_rows(ordinary_parity._claims()):
            with self.subTest(capability=row[0]):
                calls = await _exercise(row[0])
                self.assertTrue(
                    set(bootstrap[row[0]]["headerReferences"]).issubset(calls),
                    set(bootstrap[row[0]]["headerReferences"]) - calls,
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
        self.assertEqual(
            executed,
            {
                symbol
                for row in _selected_rows(ordinary_parity._claims())
                for symbol in bootstrap[row[0]]["headerReferences"]
            },
        )

    def test_stale_missing_fallback_and_claimed_call_evidence_fail_closed(self) -> None:
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
            (2, "python.conversation:999"),
            (3, "python-analyzer-conversation:999"),
            (4, "value-conversion"),
        ):
            candidate = [row[:] for row in rows]
            candidate[0][column] = stale
            with self.assertRaises(AssertionError):
                _validate_rows(candidate)
        bootstrap, _, _ = _bootstrap()
        calls = awaitable_result(_exercise(rows[0][0]))
        calls.remove(bootstrap[rows[0][0]]["headerReferences"][0])
        self.assertFalse(set(bootstrap[rows[0][0]]["headerReferences"]).issubset(calls))
        with self.assertRaises(AttributeError):
            NativeLibrary(
                MissingSymbolLibrary(bootstrap[rows[0][0]]["headerReferences"][0])
            )

    async def test_z_complete_538_row_evidence_is_exact(self) -> None:
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
                row[0].startswith(f"{OWNER_PREFIX}{owner}|")
                for owner in {"CodexAgent", "CodexHost", "CodexHostState.Ready"}
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
        self.assertEqual((len(all_rows), len(claimed_tests)), (538, 538))
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


def awaitable_result(awaitable: object) -> set[str]:
    import asyncio

    return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
