from __future__ import annotations

import asyncio
import ctypes
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from ._async import StateStream, StateSubscription, run_operation
from ._conversation_native import (
    create_turn_request,
    read_conversation_summary,
    read_conversation_value,
    read_message,
    read_turn_progress,
)
from ._errors import ClosedError, Failure, Status
from ._ffi import (
    ClientInfoStruct,
    ConversationOpenOptionsStruct,
    Handle,
    HostOptionsStruct,
    NativeLibrary,
    PathWorkspaceSelectionStruct,
    null_view,
    load_native,
    utf8_view,
)
from ._models import (
    ApprovalPreset,
    ClientInfo,
    ConversationId,
    ConversationState,
    ConversationStatus,
    ConversationSummary,
    HostState,
    HostStateKind,
    Workspace,
    WorkspaceRequirement,
    WorkspaceSelectionReason,
)
from ._residual_values import ConversationValue, Message, TurnRequest
from ._values import TurnProgress


T = TypeVar("T")


class _Context:
    def __init__(self, native: NativeLibrary) -> None:
        self.native = native
        self.handle = Handle()
        native.call("codex_agent_context_create", ctypes.byref(self.handle))
        self.open = True

    def require(self) -> Handle:
        if not self.open or not self.handle.value:
            raise ClosedError("the owning CodexHost is closed")
        return self.handle

    async def destroy(self) -> None:
        if not self.open:
            return
        await _retry_slot(
            self.native, "codex_agent_context_destroy", ctypes.byref(self.handle)
        )
        self.open = False


async def _retry_slot(native: NativeLibrary, name: str, *arguments: Any) -> None:
    while True:
        status = native.call(name, *arguments, allow=(Status.BUSY,))
        if status is not Status.BUSY:
            return
        await asyncio.sleep(0)


def _failure(context: _Context, handle: Handle) -> Failure:
    native = context.native
    context_handle = context.require()
    try:
        code = native.copy_string(
            "codex_agent_failure_code_copy", context_handle, handle
        )
        message = native.copy_string(
            "codex_agent_failure_message_copy", context_handle, handle
        )
        recoverable = ctypes.c_int32()
        native.call(
            "codex_agent_failure_is_recoverable",
            context_handle,
            handle,
            ctypes.byref(recoverable),
        )
        return Failure(code or "", message or "", bool(recoverable.value))
    finally:
        native.call("codex_agent_failure_release", context_handle, ctypes.byref(handle))


def _optional_failure(context: _Context, name: str, *arguments: Any) -> Failure | None:
    handle = Handle()
    status = context.native.call(
        name, *arguments, ctypes.byref(handle), allow=(Status.NOT_READY,)
    )
    return _failure(context, handle) if status is Status.OK else None


def _snapshot(
    context: _Context,
    getter_name: str,
    target: Handle,
    decoder: Callable[[Handle], T],
) -> T:
    context_handle = context.require()
    snapshot = Handle()
    context.native.call(getter_name, context_handle, target, ctypes.byref(snapshot))
    try:
        return decoder(snapshot)
    finally:
        context.native.call(
            "codex_agent_snapshot_destroy", context_handle, ctypes.byref(snapshot)
        )


def _stream(
    context: _Context,
    getter_name: str,
    subscribe_name: str,
    target: Handle,
    decoder: Callable[[Handle], T],
) -> StateStream[T]:
    def current() -> T:
        return _snapshot(context, getter_name, target, decoder)

    def subscribe() -> StateSubscription[T]:
        context_handle = context.require()
        return StateSubscription(
            context.native,
            context_handle,
            lambda callback, user_data, out: context.native.function(subscribe_name)(
                context_handle, target, callback, user_data, out
            ),
            decoder,
        )

    return StateStream(current, subscribe)


class _OwnedHandle:
    _release_name: str

    def __init__(self, context: _Context, handle: Handle) -> None:
        self._context = context
        self._handle = handle

    def _require(self) -> tuple[Handle, Handle]:
        context = self._context.require()
        if not self._handle.value:
            raise ClosedError(f"{type(self).__name__} is closed")
        return context, self._handle

    async def aclose(self) -> None:
        if not self._handle.value or not self._context.open:
            self._handle = Handle()
            return
        await _retry_slot(
            self._context.native,
            self._release_name,
            self._context.require(),
            ctypes.byref(self._handle),
        )

    async def __aenter__(self) -> _OwnedHandle:
        self._require()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


class CodexHost:
    """Owner of one local Desktop/Host runtime and its complete object graph."""

    def __init__(
        self,
        bundle_directory: str | os.PathLike[str],
        data_directory: str | os.PathLike[str],
        client_info: ClientInfo,
        *,
        library_path: str | os.PathLike[str] | None = None,
        _native: NativeLibrary | None = None,
    ) -> None:
        self._native = _native or load_native(library_path)
        self._context = _Context(self._native)
        self._handle = Handle()
        self._agent: CodexAgent | None = None

        bundle, bundle_backing = utf8_view(os.fspath(bundle_directory))
        data, data_backing = utf8_view(os.fspath(data_directory))
        name, name_backing = utf8_view(client_info.name)
        title, title_backing = utf8_view(client_info.title)
        version, version_backing = utf8_view(client_info.version)
        # Keep all backing buffers alive through the native call; the ABI copies them.
        _backings = (
            bundle_backing,
            data_backing,
            name_backing,
            title_backing,
            version_backing,
        )
        native_client = ClientInfoStruct(
            ctypes.sizeof(ClientInfoStruct), name, title, version
        )
        options = HostOptionsStruct(
            ctypes.sizeof(HostOptionsStruct),
            bundle,
            data,
            native_client,
        )
        try:
            self._native.call(
                "codex_agent_host_create",
                self._context.require(),
                ctypes.byref(options),
                ctypes.byref(self._handle),
            )
        except BaseException:
            # Constructor cleanup cannot await. No callbacks exist yet, so BUSY is impossible.
            self._native.call(
                "codex_agent_context_destroy", ctypes.byref(self._context.handle)
            )
            self._context.open = False
            raise
        del _backings

    def _require(self) -> tuple[Handle, Handle]:
        context = self._context.require()
        if not self._handle.value:
            raise ClosedError("CodexHost is closed")
        return context, self._handle

    def _decode_state(self, snapshot: Handle) -> HostState:
        context, host = self._require()
        kind_value = ctypes.c_int32()
        self._native.call(
            "codex_agent_host_state_kind", context, snapshot, ctypes.byref(kind_value)
        )
        kind = HostStateKind(kind_value.value)

        workspace: Workspace | None = None
        has_workspace = ctypes.c_int32()
        self._native.call(
            "codex_agent_host_state_has_workspace",
            context,
            snapshot,
            ctypes.byref(has_workspace),
        )
        if has_workspace.value:
            path = self._native.copy_string(
                "codex_agent_host_state_workspace_path_copy", context, snapshot
            )
            display = self._native.copy_string(
                "codex_agent_host_state_workspace_display_name_copy",
                context,
                snapshot,
                nullable=True,
            )
            workspace = Workspace(path or "", display)

        requirement: WorkspaceRequirement | None = None
        if kind is HostStateKind.WORKSPACE_REQUIRED:
            reason = ctypes.c_int32()
            self._native.call(
                "codex_agent_host_state_requirement_reason",
                context,
                snapshot,
                ctypes.byref(reason),
            )
            message = self._native.copy_string(
                "codex_agent_host_state_requirement_message_copy", context, snapshot
            )
            requirement = WorkspaceRequirement(
                WorkspaceSelectionReason(reason.value), message or ""
            )

        failure = None
        if kind is HostStateKind.FAILED:
            failure = _optional_failure(
                self._context, "codex_agent_host_state_failure", context, snapshot
            )

        agent = None
        if kind is HostStateKind.READY:
            agent_handle = Handle()
            self._native.call(
                "codex_agent_host_state_agent",
                context,
                host,
                snapshot,
                ctypes.byref(agent_handle),
            )
            if self._agent is None or not self._agent._handle.value:
                self._agent = CodexAgent(self._context, agent_handle)
            else:
                self._native.call(
                    "codex_agent_agent_release",
                    context,
                    ctypes.byref(agent_handle),
                )
            agent = self._agent
        if agent is not None:
            return HostStateReady(agent)
        return HostState(kind, None, workspace, requirement, failure)

    @property
    def state(self) -> StateStream[HostState]:
        _, host = self._require()
        return _stream(
            self._context,
            "codex_agent_host_state_get",
            "codex_agent_host_state_subscribe",
            host,
            self._decode_state,
        )

    def states(self) -> StateStream[HostState]:
        return self.state

    async def _void_operation(self, name: str, *arguments: Any) -> None:
        context, host = self._require()
        await run_operation(
            self._native,
            context,
            lambda callback, user_data, out: self._native.function(name)(
                context, host, *arguments, callback, user_data, out
            ),
            lambda _operation: None,
            lambda failure: _failure(self._context, failure),
        )

    async def start(self) -> None:
        await self._void_operation("codex_agent_host_start")

    async def select_workspace(self, path: str | os.PathLike[str]) -> None:
        view, backing = utf8_view(os.fspath(path))
        selection = PathWorkspaceSelectionStruct(
            ctypes.sizeof(PathWorkspaceSelectionStruct), view
        )
        await self._void_operation(
            "codex_agent_host_select_workspace", ctypes.byref(selection)
        )
        del backing

    async def aclose(self) -> None:
        if not self._handle.value:
            return
        await self._void_operation("codex_agent_host_close")
        if self._agent is not None:
            await self._agent.aclose()
        await _retry_slot(
            self._native,
            "codex_agent_host_release",
            self._context.require(),
            ctypes.byref(self._handle),
        )
        await self._context.destroy()

    close = aclose

    async def __aenter__(self) -> CodexHost:
        self._require()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


class CodexAgent(_OwnedHandle):
    _release_name = "codex_agent_agent_release"

    def __init__(self, context: _Context, handle: Handle) -> None:
        super().__init__(context, handle)
        self._projections: dict[str, _OwnedHandle] = {}

    def _projection(self, name: str, wrapper: Callable[[_Context, Handle], T]) -> T:
        projection = self._projections.get(name)
        if projection is None:
            context, agent = self._require()
            handle = Handle()
            self._context.native.call(name, context, agent, ctypes.byref(handle))
            projection = wrapper(self._context, handle)
            self._projections[name] = projection
        return projection  # type: ignore[return-value]

    @property
    def conversations(self) -> Conversations:
        return self._projection("codex_agent_agent_conversations", Conversations)

    @property
    def authentication(self) -> CodexAuthentication:
        return self._projection("codex_agent_agent_authentication", CodexAuthentication)

    @property
    def connectors(self) -> CodexConnectors:
        return self._projection("codex_agent_agent_connectors", CodexConnectors)

    @property
    def hooks(self) -> CodexHooks:
        return self._projection("codex_agent_agent_hooks", CodexHooks)

    @property
    def integration_authorization(self) -> CodexIntegrationAuthorization:
        return self._projection(
            "codex_agent_agent_integration_authorization",
            CodexIntegrationAuthorization,
        )

    @property
    def interactions(self) -> CodexInteractions:
        return self._projection("codex_agent_agent_interactions", CodexInteractions)

    @property
    def mcp_servers(self) -> CodexMcpServers:
        return self._projection("codex_agent_agent_mcp_servers", CodexMcpServers)

    @property
    def models(self) -> CodexModels:
        return self._projection("codex_agent_agent_models", CodexModels)

    @property
    def plugins(self) -> CodexPlugins:
        return self._projection("codex_agent_agent_plugins", CodexPlugins)

    @property
    def skills(self) -> CodexSkills:
        return self._projection("codex_agent_agent_skills", CodexSkills)

    @property
    def workspace(self) -> Workspace:
        context, agent = self._require()
        handle = Handle()
        self._context.native.call(
            "codex_agent_agent_workspace", context, agent, ctypes.byref(handle)
        )
        try:
            path = self._context.native.copy_string(
                "codex_agent_workspace_path_copy", context, handle
            )
            display_name = self._context.native.copy_string(
                "codex_agent_workspace_display_name_copy", context, handle
            )
            return Workspace(path or "", display_name)
        finally:
            self._context.native.call(
                "codex_agent_workspace_destroy", context, ctypes.byref(handle)
            )

    async def aclose(self) -> None:
        await super().aclose()
        for projection in self._projections.values():
            await projection.aclose()
        self._projections.clear()


@dataclass(frozen=True, slots=True, init=False)
class HostStateReady(HostState):
    """Ready host state with its non-null, host-owned agent."""

    agent: CodexAgent

    def __init__(self, agent: CodexAgent) -> None:
        super().__init__(HostStateKind.READY, agent)


class Conversations(_OwnedHandle):
    _release_name = "codex_agent_conversations_release"

    def _decode_active(self, snapshot: Handle) -> CodexConversation | None:
        context, conversations = self._require()
        handle = Handle()
        status = self._context.native.call(
            "codex_agent_active_conversation",
            context,
            conversations,
            snapshot,
            ctypes.byref(handle),
            allow=(Status.NOT_READY,),
        )
        return CodexConversation(self._context, handle) if status is Status.OK else None

    @property
    def active(self) -> StateStream[CodexConversation | None]:
        _, conversations = self._require()
        return _stream(
            self._context,
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            conversations,
            self._decode_active,
        )

    async def list(self) -> tuple[ConversationSummary, ...]:
        context, conversations = self._require()

        def decode(operation: Handle) -> tuple[ConversationSummary, ...]:
            count = ctypes.c_size_t()
            self._context.native.call(
                "codex_agent_operation_conversation_summaries_count",
                context,
                operation,
                ctypes.byref(count),
            )
            values: list[ConversationSummary] = []
            for index in range(count.value):
                summary = Handle()
                self._context.native.call(
                    "codex_agent_operation_conversation_summary_at",
                    context,
                    operation,
                    index,
                    ctypes.byref(summary),
                )
                values.append(
                    read_conversation_summary(self._context.native, context, summary)
                )
            return tuple(values)

        return await run_operation(
            self._context.native,
            context,
            lambda callback, user_data, out: self._context.native.function(
                "codex_agent_conversations_list"
            )(context, conversations, callback, user_data, out),
            decode,
            lambda failure: _failure(self._context, failure),
        )

    async def open(
        self,
        conversation_id: ConversationId | str | None = None,
        *,
        approval_preset: ApprovalPreset | None = None,
        service_tier: str | None = None,
    ) -> CodexConversation:
        context, conversations = self._require()
        id_text = (
            conversation_id.value
            if isinstance(conversation_id, ConversationId)
            else conversation_id
        )
        id_view, id_backing = (
            utf8_view(id_text) if id_text is not None else (null_view(), None)
        )
        tier_view, tier_backing = (
            utf8_view(service_tier) if service_tier is not None else (null_view(), None)
        )
        options = ConversationOpenOptionsStruct(
            ctypes.sizeof(ConversationOpenOptionsStruct),
            int(id_text is not None),
            id_view,
            int(approval_preset is not None),
            int(approval_preset or 0),
            int(service_tier is not None),
            tier_view,
        )

        def decode(operation: Handle) -> CodexConversation:
            handle = Handle()
            self._context.native.call(
                "codex_agent_operation_conversation",
                context,
                conversations,
                operation,
                ctypes.byref(handle),
            )
            return CodexConversation(self._context, handle)

        result = await run_operation(
            self._context.native,
            context,
            lambda callback, user_data, out: self._context.native.function(
                "codex_agent_conversations_open"
            )(context, conversations, ctypes.byref(options), callback, user_data, out),
            decode,
            lambda failure: _failure(self._context, failure),
        )
        del id_backing, tier_backing
        return result

    async def read(self, conversation_id: ConversationId | str) -> ConversationValue:
        context, conversations = self._require()
        id_handle = _create_conversation_id(self._context, conversation_id)
        try:

            def decode(operation: Handle) -> ConversationValue:
                value = Handle()
                self._context.native.call(
                    "codex_agent_operation_conversation_value",
                    context,
                    operation,
                    ctypes.byref(value),
                )
                return read_conversation_value(self._context.native, context, value)

            return await run_operation(
                self._context.native,
                context,
                lambda callback, user_data, out: self._context.native.function(
                    "codex_agent_conversations_read"
                )(
                    context,
                    conversations,
                    id_handle,
                    callback,
                    user_data,
                    out,
                ),
                decode,
                lambda failure: _failure(self._context, failure),
            )
        finally:
            self._context.native.call(
                "codex_agent_conversation_id_destroy",
                context,
                ctypes.byref(id_handle),
            )

    async def rename(self, conversation_id: ConversationId | str, name: str) -> None:
        await self._with_id_and_optional_name(
            "codex_agent_conversations_rename", conversation_id, name
        )

    async def delete(self, conversation_id: ConversationId | str) -> None:
        await self._with_id_and_optional_name(
            "codex_agent_conversations_delete", conversation_id, None
        )

    async def _with_id_and_optional_name(
        self, name: str, conversation_id: ConversationId | str, value: str | None
    ) -> None:
        context, conversations = self._require()
        id_handle = _create_conversation_id(self._context, conversation_id)
        view, backing = utf8_view(value) if value is not None else (null_view(), None)
        try:
            await run_operation(
                self._context.native,
                context,
                lambda callback, user_data, out: self._context.native.function(name)(
                    context,
                    conversations,
                    id_handle,
                    *([ctypes.byref(view)] if value is not None else []),
                    callback,
                    user_data,
                    out,
                ),
                lambda _operation: None,
                lambda failure: _failure(self._context, failure),
            )
        finally:
            self._context.native.call(
                "codex_agent_conversation_id_destroy", context, ctypes.byref(id_handle)
            )
            del backing


class CodexConversation(_OwnedHandle):
    _release_name = "codex_agent_conversation_release"

    def _decode_state(self, snapshot: Handle) -> ConversationState:
        context, _ = self._require()
        value = ctypes.c_int32()
        self._context.native.call(
            "codex_agent_conversation_state_status",
            context,
            snapshot,
            ctypes.byref(value),
        )
        status = ConversationStatus(value.value)
        failure = None
        if status is ConversationStatus.FAILED:
            failure = _optional_failure(
                self._context,
                "codex_agent_conversation_state_failure",
                context,
                snapshot,
            )
        return ConversationState(status, failure)

    @property
    def state(self) -> StateStream[ConversationState]:
        _, conversation = self._require()
        return _stream(
            self._context,
            "codex_agent_conversation_state_get",
            "codex_agent_conversation_state_subscribe",
            conversation,
            self._decode_state,
        )

    def _boolean_stream(self, property_name: str) -> StateStream[bool]:
        _, conversation = self._require()

        def decode(snapshot: Handle) -> bool:
            value = ctypes.c_int32()
            self._context.native.call(
                "codex_agent_state_boolean_value",
                self._context.require(),
                snapshot,
                ctypes.byref(value),
            )
            return bool(value.value)

        return _stream(
            self._context,
            f"codex_agent_conversation_{property_name}_get",
            f"codex_agent_conversation_{property_name}_subscribe",
            conversation,
            decode,
        )

    @property
    def can_start_turn(self) -> StateStream[bool]:
        return self._boolean_stream("can_start_turn")

    @property
    def can_reload(self) -> StateStream[bool]:
        return self._boolean_stream("can_reload")

    @property
    def can_cancel_turn(self) -> StateStream[bool]:
        return self._boolean_stream("can_cancel_turn")

    @property
    def can_run_shell_command(self) -> StateStream[bool]:
        return self._boolean_stream("can_run_shell_command")

    @property
    def is_turn_active(self) -> StateStream[bool]:
        return self._boolean_stream("is_turn_active")

    def is_same(self, other: CodexConversation) -> bool:
        context, conversation = self._require()
        other_context, other_handle = other._require()
        if context.value != other_context.value:
            return False
        value = ctypes.c_int32()
        self._context.native.call(
            "codex_agent_conversation_is_same",
            context,
            conversation,
            other_handle,
            ctypes.byref(value),
        )
        return bool(value.value)

    @property
    def current_messages(self) -> StateStream[tuple[Message, ...]]:
        context, conversation = self._require()

        def decode(snapshot: Handle) -> tuple[Message, ...]:
            count = ctypes.c_size_t()
            self._context.native.call(
                "codex_agent_conversation_current_messages_count",
                context,
                snapshot,
                ctypes.byref(count),
            )
            messages = []
            for index in range(count.value):
                message = Handle()
                self._context.native.call(
                    "codex_agent_conversation_current_messages_at",
                    context,
                    snapshot,
                    index,
                    ctypes.byref(message),
                )
                messages.append(read_message(self._context.native, context, message))
            return tuple(messages)

        return _stream(
            self._context,
            "codex_agent_conversation_current_messages_get",
            "codex_agent_conversation_current_messages_subscribe",
            conversation,
            decode,
        )

    @property
    def active_turn_progress(self) -> StateStream[TurnProgress | None]:
        context, conversation = self._require()

        def decode(snapshot: Handle) -> TurnProgress | None:
            present = ctypes.c_int32()
            self._context.native.call(
                "codex_agent_conversation_active_turn_progress_has_value",
                context,
                snapshot,
                ctypes.byref(present),
            )
            if not present.value:
                return None
            progress = Handle()
            self._context.native.call(
                "codex_agent_conversation_active_turn_progress_value",
                context,
                snapshot,
                ctypes.byref(progress),
            )
            return read_turn_progress(self._context.native, context, progress)

        return _stream(
            self._context,
            "codex_agent_conversation_active_turn_progress_get",
            "codex_agent_conversation_active_turn_progress_subscribe",
            conversation,
            decode,
        )

    async def _void_operation(self, name: str, argument: str | None = None) -> None:
        context, conversation = self._require()
        arguments: list[Any] = []
        backing = None
        if argument is not None:
            view, backing = utf8_view(argument)
            arguments.append(ctypes.byref(view))
        await run_operation(
            self._context.native,
            context,
            lambda callback, user_data, out: self._context.native.function(name)(
                context, conversation, *arguments, callback, user_data, out
            ),
            lambda _operation: None,
            lambda failure: _failure(self._context, failure),
        )
        del backing

    async def send(self, prompt: str | TurnRequest) -> None:
        if isinstance(prompt, str):
            await self._void_operation("codex_agent_conversation_send", prompt)
            return
        context, conversation = self._require()
        request = create_turn_request(self._context.native, context, prompt)
        try:
            await run_operation(
                self._context.native,
                context,
                lambda callback, user_data, out: self._context.native.function(
                    "codex_agent_conversation_send_request"
                )(
                    context,
                    conversation,
                    request,
                    callback,
                    user_data,
                    out,
                ),
                lambda _operation: None,
                lambda failure: _failure(self._context, failure),
            )
        finally:
            self._context.native.call(
                "codex_agent_turn_request_destroy", context, ctypes.byref(request)
            )

    async def run_shell_command(self, command: str) -> None:
        await self._void_operation(
            "codex_agent_conversation_run_shell_command", command
        )

    async def reload(self) -> None:
        await self._void_operation("codex_agent_conversation_reload")

    async def cancel_turn(self) -> None:
        await self._void_operation("codex_agent_conversation_cancel_turn")

    async def aclose(self) -> None:
        if not self._handle.value or not self._context.open:
            self._handle = Handle()
            return
        await self._void_operation("codex_agent_conversation_close")
        await super().aclose()

    close = aclose


def _create_conversation_id(
    context: _Context, conversation_id: ConversationId | str
) -> Handle:
    value = (
        conversation_id.value
        if isinstance(conversation_id, ConversationId)
        else conversation_id
    )
    view, backing = utf8_view(value)
    handle = Handle()
    context.native.call(
        "codex_agent_conversation_id_create",
        context.require(),
        ctypes.byref(view),
        ctypes.byref(handle),
    )
    del backing
    return handle


# Imported after the owner classes so `_services` can reuse their private FFI seams.
from ._services import (  # noqa: E402
    CodexAuthentication,
    CodexConnectors,
    CodexHooks,
    CodexIntegrationAuthorization,
    CodexInteractions,
    CodexMcpServers,
    CodexModels,
    CodexPlugins,
    CodexSkills,
)
