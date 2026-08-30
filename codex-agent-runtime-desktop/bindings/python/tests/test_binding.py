from __future__ import annotations

import asyncio
import ctypes
import os
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from codex_agent import (  # noqa: E402
    ClientInfo,
    CodexHost,
    ConversationStatus,
    HostStateKind,
    OperationError,
    Status,
    UnsupportedAbiError,
)
from codex_agent._ffi import (
    ABI_VERSION,
    Handle,
    NativeLibrary,
    current_classifier,
    resolve_library_path,
)  # noqa: E402


def _set_handle(pointer: object, value: int | None) -> None:
    ctypes.cast(pointer, ctypes.POINTER(Handle))[0] = Handle(value)


def _set_i32(pointer: object, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int32))[0] = value


def _set_i64(pointer: object, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int64))[0] = value


def _set_size(pointer: object, value: int) -> None:
    ctypes.cast(pointer, ctypes.POINTER(ctypes.c_size_t))[0] = value


class FakeFunction:
    def __init__(self, owner: FakeLibrary, name: str) -> None:
        self.owner = owner
        self.name = name
        self.argtypes: list[object] = []
        self.restype: object = ctypes.c_int32

    def __call__(self, *args: object) -> int:
        return self.owner.invoke(self.name, *args)


class FakeLibrary:
    def __init__(self) -> None:
        self.functions: dict[str, FakeFunction] = {}
        self.calls: list[str] = []
        self.next_operation_result = Status.OK
        self.busy_destroy_once = False
        self.destroy_was_busy = False
        self.delay_operation = False
        self.delayed_callback: tuple[object, object] | None = None
        self.operation_cancelled = False

    def __getattr__(self, name: str) -> FakeFunction:
        return self.functions.setdefault(name, FakeFunction(self, name))

    def invoke(self, name: str, *args: object) -> int:
        self.calls.append(name)
        if name == "codex_agent_abi_version":
            return ABI_VERSION
        if name == "codex_agent_abi_is_compatible":
            return 1
        if name == "codex_agent_context_create":
            _set_handle(args[0], 1)
        elif name == "codex_agent_context_destroy":
            _set_handle(args[0], None)
        elif name == "codex_agent_host_create":
            options = ctypes.cast(
                args[1], ctypes.POINTER(type_for_host_options())
            ).contents
            assert options.struct_size == ctypes.sizeof(type(options))
            _set_handle(args[2], 2)
        elif name == "codex_agent_host_state_get":
            _set_handle(args[2], 201)
        elif name == "codex_agent_host_state_kind":
            _set_i32(args[2], HostStateKind.READY)
        elif name == "codex_agent_host_state_has_workspace":
            _set_i32(args[2], 0)
        elif name == "codex_agent_host_state_agent":
            _set_handle(args[3], 3)
        elif name == "codex_agent_agent_conversations":
            _set_handle(args[2], 4)
        elif name == "codex_agent_active_conversation":
            return Status.NOT_READY
        elif name == "codex_agent_operation_conversation":
            _set_handle(args[3], 5)
        elif name == "codex_agent_operation_conversation_summaries_count":
            _set_size(args[2], 1)
        elif name == "codex_agent_operation_conversation_summary_at":
            _set_handle(args[3], 500)
        elif name == "codex_agent_conversation_summary_conversation_id":
            _set_handle(args[2], 501)
        elif name == "codex_agent_conversation_summary_updated_at_epoch_seconds":
            _set_i64(args[2], 1234)
        elif name == "codex_agent_conversation_state_get":
            _set_handle(args[2], 202)
        elif name == "codex_agent_conversation_state_status":
            _set_i32(args[2], ConversationStatus.READY)
        elif name.endswith("_get") and name.startswith("codex_agent_conversation_can_"):
            _set_handle(args[2], 203)
        elif name == "codex_agent_conversation_is_turn_active_get":
            _set_handle(args[2], 203)
        elif name == "codex_agent_state_boolean_value":
            _set_i32(args[2], 1)
        elif name == "codex_agent_conversation_is_same":
            _set_i32(args[3], int(args[1].value == args[2].value))
        elif name == "codex_agent_operation_result":
            _set_i32(args[2], self.next_operation_result)
        elif name == "codex_agent_operation_failure":
            if self.next_operation_result is Status.OPERATION_FAILED:
                _set_handle(args[2], 400)
            else:
                return Status.NOT_READY
        elif name == "codex_agent_failure_is_recoverable":
            _set_i32(args[2], 1)
        elif name.endswith("_copy"):
            return self._copy(name, *args)
        elif name == "codex_agent_operation_destroy":
            if self.busy_destroy_once and not self.destroy_was_busy:
                self.destroy_was_busy = True
                return Status.BUSY
            _set_handle(args[1], None)
        elif name == "codex_agent_subscription_destroy":
            _set_handle(args[1], None)
        elif name == "codex_agent_snapshot_destroy":
            _set_handle(args[1], None)
        elif name.endswith("_release") or name.endswith("_destroy"):
            _set_handle(args[-1], None)
        elif name == "codex_agent_operation_cancel":
            self.operation_cancelled = True
        elif self._is_operation_start(name):
            callback, user_data, out = args[-3:]
            _set_handle(out, 100)
            if self.delay_operation:
                self.delayed_callback = (callback, user_data)
            else:
                callback(Handle(1), Handle(100), user_data)
        elif name == "codex_agent_host_state_subscribe":
            callback, user_data, out = args[-3:]
            _set_handle(out, 300)
            callback(Handle(1), Handle(300), Status.OK, Handle(201), 1, user_data)
        return Status.OK

    def _is_operation_start(self, name: str) -> bool:
        return name in {
            "codex_agent_host_start",
            "codex_agent_host_select_workspace",
            "codex_agent_host_close",
            "codex_agent_conversations_list",
            "codex_agent_conversations_open",
            "codex_agent_conversations_rename",
            "codex_agent_conversations_delete",
            "codex_agent_conversation_send",
            "codex_agent_conversation_run_shell_command",
            "codex_agent_conversation_reload",
            "codex_agent_conversation_cancel_turn",
            "codex_agent_conversation_close",
        }

    def _copy(self, name: str, *args: object) -> int:
        values = {
            "codex_agent_failure_code_copy": b"fixture.failure",
            "codex_agent_failure_message_copy": b"fixture failed",
            "codex_agent_conversation_id_value_copy": b"conversation-1",
            "codex_agent_conversation_summary_title_copy": b"Fixture",
        }
        value = values.get(name, b"")
        buffer, capacity, required = args[-3:]
        _set_size(required, len(value))
        if len(value) > int(capacity):
            return Status.BUFFER_TOO_SMALL
        if value:
            ctypes.memmove(buffer, value, len(value))
        return Status.OK

    def complete_delayed(self) -> None:
        assert self.delayed_callback is not None
        callback, user_data = self.delayed_callback
        self.delayed_callback = None
        callback(Handle(1), Handle(100), user_data)


def type_for_host_options() -> type[ctypes.Structure]:
    from codex_agent._ffi import HostOptionsStruct

    return HostOptionsStruct


class BindingTests(unittest.IsolatedAsyncioTestCase):
    def make_host(
        self, fake: FakeLibrary | None = None
    ) -> tuple[CodexHost, FakeLibrary]:
        library = fake or FakeLibrary()
        native = NativeLibrary(library)
        host = CodexHost(
            "bundle", "data", ClientInfo("test", "Test", "1"), _native=native
        )
        return host, library

    async def test_host_agent_conversation_lifecycle_and_state(self) -> None:
        host, fake = self.make_host()
        await host.start()
        state = host.state.current
        self.assertEqual(state.kind, HostStateKind.READY)
        self.assertIsNotNone(state.agent)
        agent = state.agent
        conversations = agent.conversations
        self.assertIsNone(conversations.active.current)
        summaries = await conversations.list()
        self.assertEqual(summaries[0].conversation_id.value, "conversation-1")
        self.assertEqual(summaries[0].title, "Fixture")
        self.assertEqual(summaries[0].updated_at_epoch_seconds, 1234)
        conversation = await conversations.open()
        self.assertEqual(conversation.state.current.status, ConversationStatus.READY)
        self.assertTrue(conversation.can_start_turn.current)
        self.assertTrue(conversation.is_same(conversation))
        await conversation.send("hello")
        await conversation.aclose()
        await conversation.aclose()
        await conversations.aclose()
        await conversations.aclose()
        await agent.aclose()
        await agent.aclose()
        await host.aclose()
        await host.aclose()
        self.assertFalse(host._context.open)
        self.assertIn("codex_agent_conversation_close", fake.calls)
        self.assertIn("codex_agent_conversation_id_destroy", fake.calls)
        self.assertIn("codex_agent_conversation_summary_destroy", fake.calls)
        self.assertIn("codex_agent_context_destroy", fake.calls)

    async def test_state_subscription_is_async_iterable_and_terminal(self) -> None:
        host, _ = self.make_host()
        subscription = host.state.subscribe()
        state = await anext(subscription)
        self.assertEqual(state.kind, HostStateKind.READY)
        with self.assertRaises(StopAsyncIteration):
            await anext(subscription)
        await host.aclose()

    async def test_structured_operation_failure_and_busy_quiescence(self) -> None:
        fake = FakeLibrary()
        fake.next_operation_result = Status.OPERATION_FAILED
        fake.busy_destroy_once = True
        host, _ = self.make_host(fake)
        with self.assertRaises(OperationError) as raised:
            await host.start()
        self.assertEqual(raised.exception.status, Status.OPERATION_FAILED)
        self.assertEqual(raised.exception.failure.code, "fixture.failure")
        self.assertTrue(raised.exception.failure.is_recoverable)
        self.assertTrue(fake.destroy_was_busy)
        fake.next_operation_result = Status.OK
        await host.aclose()

    async def test_task_cancellation_requests_native_cancellation(self) -> None:
        fake = FakeLibrary()
        fake.delay_operation = True
        host, _ = self.make_host(fake)
        task = asyncio.create_task(host.start())
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(fake.operation_cancelled)
        fake.complete_delayed()
        await asyncio.sleep(0.01)
        fake.delay_operation = False
        await host.aclose()


class LoaderAndPackageTests(unittest.TestCase):
    def test_metadata_has_canonical_identity_and_floor(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(metadata["project"]["name"], "codex-agent")
        self.assertEqual(metadata["project"]["version"], "0.2.0")
        self.assertEqual(metadata["project"]["requires-python"], ">=3.11")
        self.assertEqual(metadata["project"]["license"], "GPL-3.0-or-later")

    def test_current_machine_is_one_of_the_five_supported_classifiers(self) -> None:
        self.assertIn(
            current_classifier(),
            {"macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64"},
        )

    def test_explicit_library_path_is_exact_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "libcodex_agent.so"
            library.touch()
            self.assertEqual(resolve_library_path(library), library.resolve())
            with self.assertRaises(FileNotFoundError):
                resolve_library_path(Path(directory) / "missing.so")

    def test_incompatible_abi_is_rejected(self) -> None:
        fake = FakeLibrary()
        fake.functions["codex_agent_abi_is_compatible"] = FakeFunction(
            fake, "incompatible"
        )
        original = fake.invoke

        def invoke(name: str, *args: object) -> int:
            if name == "incompatible":
                return 0
            return original(name, *args)

        fake.invoke = invoke  # type: ignore[method-assign]
        with self.assertRaises(UnsupportedAbiError):
            NativeLibrary(fake)

    def test_every_declared_ctypes_symbol_exists_in_the_canonical_header(self) -> None:
        fake = FakeLibrary()
        NativeLibrary(fake)
        header = (
            ROOT.parents[1] / "native" / "c-api" / "include" / "codex_agent.h"
        ).read_text()
        header_symbols = set(re.findall(r"\b(codex_agent_[a-z0-9_]+)\s*\(", header))
        required = {name for name in fake.functions if name.startswith("codex_agent_")}
        self.assertGreater(len(required), 60)
        self.assertEqual(required - header_symbols, set())


if __name__ == "__main__":
    unittest.main()
