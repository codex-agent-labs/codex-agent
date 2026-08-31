from __future__ import annotations

import ctypes
import os
import platform
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable

from ._errors import Status, UnsupportedAbiError, check


ABI_VERSION = (1 << 24) | (12 << 16)
MINIMUM_ABI_VERSION = 1 << 24

Handle = ctypes.c_void_p
HandlePointer = ctypes.POINTER(Handle)


class StringView(ctypes.Structure):
    _fields_ = [("data", ctypes.POINTER(ctypes.c_uint8)), ("size", ctypes.c_size_t)]


class ClientInfoStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("name", StringView),
        ("title", StringView),
        ("version", StringView),
    ]


class HostOptionsStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("bundle_directory", StringView),
        ("data_directory", StringView),
        ("client_info", ClientInfoStruct),
    ]


class PathWorkspaceSelectionStruct(ctypes.Structure):
    _fields_ = [("struct_size", ctypes.c_uint32), ("path", StringView)]


class ConversationOpenOptionsStruct(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32),
        ("has_conversation_id", ctypes.c_int32),
        ("conversation_id", StringView),
        ("has_approval_preset", ctypes.c_int32),
        ("approval_preset", ctypes.c_int32),
        ("has_service_tier", ctypes.c_int32),
        ("service_tier", StringView),
    ]


OperationCallback = ctypes.CFUNCTYPE(None, Handle, Handle, ctypes.c_void_p)
StateCallback = ctypes.CFUNCTYPE(
    None,
    Handle,
    Handle,
    ctypes.c_int32,
    Handle,
    ctypes.c_int32,
    ctypes.c_void_p,
)


def utf8_view(value: str) -> tuple[StringView, Any]:
    encoded = value.encode("utf-8", errors="strict")
    if not encoded:
        return StringView(None, 0), None
    backing = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
    return StringView(backing, len(encoded)), backing


def null_view() -> StringView:
    return StringView(None, 0)


def current_classifier() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    architectures = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "x64",
        "amd64": "x64",
    }
    architecture = architectures.get(machine)
    if system == "darwin" and architecture is not None:
        return f"macos-{architecture}"
    if system == "linux" and architecture is not None:
        return f"linux-{architecture}"
    if system == "windows" and architecture == "x64":
        return "windows-x64"
    raise OSError(f"unsupported Codex Agent desktop host: {system}-{machine}")


def _library_name(classifier: str) -> str:
    if classifier.startswith("macos-"):
        return "libcodex_agent.dylib"
    if classifier.startswith("linux-"):
        return "libcodex_agent.so"
    return "codex_agent.dll"


def resolve_library_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    configured = explicit or os.environ.get("CODEX_AGENT_LIBRARY")
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        classifier = current_classifier()
        path = Path(
            str(
                files("codex_agent").joinpath(
                    "native", classifier, _library_name(classifier)
                )
            )
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"Codex Agent C SDK library not found at {path}; set CODEX_AGENT_LIBRARY or install the matching platform wheel"
        )
    return path


class NativeLibrary:
    """Strict ctypes declarations for the Python-owned portion of ABI 1.12."""

    def __init__(self, library: Any) -> None:
        self.library = library
        self._declare_all()
        actual = int(self.library.codex_agent_abi_version())
        compatible = int(self.library.codex_agent_abi_is_compatible(ABI_VERSION))
        if compatible != 1 or actual < MINIMUM_ABI_VERSION or actual >> 24 != 1:
            raise UnsupportedAbiError(
                f"Codex Agent ABI 1.12 is required; loaded 0x{actual:08x}"
            )

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> NativeLibrary:
        return cls(ctypes.CDLL(str(resolve_library_path(path))))

    def function(self, name: str) -> Any:
        return getattr(self.library, name)

    def call(self, name: str, *args: Any, allow: tuple[Status, ...] = ()) -> Status:
        return check(int(self.function(name)(*args)), name, allow=allow)

    def copy_string(
        self, name: str, *prefix: Any, nullable: bool = False
    ) -> str | None:
        function = self.function(name)
        required = ctypes.c_size_t()
        status = check(
            int(function(*prefix, None, 0, ctypes.byref(required))),
            name,
            allow=(
                (Status.BUFFER_TOO_SMALL, Status.NOT_READY)
                if nullable
                else (Status.BUFFER_TOO_SMALL,)
            ),
        )
        if status is Status.NOT_READY:
            return None
        if required.value == 0:
            return ""
        buffer = (ctypes.c_uint8 * required.value)()
        self.call(name, *prefix, buffer, required.value, ctypes.byref(required))
        return bytes(buffer[: required.value]).decode("utf-8", errors="strict")

    def _declare(
        self, name: str, arguments: list[Any], result: Any = ctypes.c_int32
    ) -> None:
        function = getattr(self.library, name)  # Missing required symbols fail closed.
        function.argtypes = arguments
        function.restype = result

    def _declare_all(self) -> None:
        h = Handle
        hp = HandlePointer
        p_i32 = ctypes.POINTER(ctypes.c_int32)
        p_i64 = ctypes.POINTER(ctypes.c_int64)
        p_size = ctypes.POINTER(ctypes.c_size_t)
        bytes_out = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, p_size]

        self._declare("codex_agent_abi_version", [], ctypes.c_uint32)
        self._declare(
            "codex_agent_abi_is_compatible", [ctypes.c_uint32], ctypes.c_int32
        )
        self._declare("codex_agent_context_create", [hp])
        self._declare("codex_agent_context_destroy", [hp])
        self._declare(
            "codex_agent_host_create", [h, ctypes.POINTER(HostOptionsStruct), hp]
        )
        self._declare("codex_agent_host_release", [h, hp])
        self._declare(
            "codex_agent_host_start", [h, h, OperationCallback, ctypes.c_void_p, hp]
        )
        self._declare(
            "codex_agent_host_select_workspace",
            [
                h,
                h,
                ctypes.POINTER(PathWorkspaceSelectionStruct),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )
        self._declare(
            "codex_agent_host_close", [h, h, OperationCallback, ctypes.c_void_p, hp]
        )
        self._declare("codex_agent_host_state_get", [h, h, hp])
        self._declare(
            "codex_agent_host_state_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_host_state_kind", [h, h, p_i32])
        self._declare("codex_agent_host_state_agent", [h, h, h, hp])
        self._declare("codex_agent_host_state_failure", [h, h, hp])
        self._declare("codex_agent_host_state_has_workspace", [h, h, p_i32])
        self._declare("codex_agent_host_state_workspace_path_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_host_state_workspace_display_name_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_host_state_requirement_reason", [h, h, p_i32])
        self._declare(
            "codex_agent_host_state_requirement_message_copy", [h, h, *bytes_out]
        )

        self._declare("codex_agent_agent_release", [h, hp])
        self._declare("codex_agent_agent_conversations", [h, h, hp])
        self._declare("codex_agent_agent_authentication", [h, h, hp])
        self._declare("codex_agent_agent_interactions", [h, h, hp])
        self._declare("codex_agent_agent_integration_authorization", [h, h, hp])
        self._declare("codex_agent_agent_models", [h, h, hp])
        self._declare("codex_agent_agent_skills", [h, h, hp])
        self._declare("codex_agent_agent_hooks", [h, h, hp])
        self._declare("codex_agent_agent_plugins", [h, h, hp])
        self._declare("codex_agent_agent_connectors", [h, h, hp])
        self._declare("codex_agent_agent_mcp_servers", [h, h, hp])
        self._declare("codex_agent_agent_workspace", [h, h, hp])
        self._declare("codex_agent_workspace_destroy", [h, hp])
        self._declare("codex_agent_workspace_path_copy", [h, h, *bytes_out])
        self._declare("codex_agent_workspace_display_name_copy", [h, h, *bytes_out])

        self._declare("codex_agent_conversations_release", [h, hp])
        self._declare("codex_agent_conversations_active_get", [h, h, hp])
        self._declare(
            "codex_agent_conversations_active_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_active_conversation", [h, h, h, hp])
        self._declare(
            "codex_agent_conversations_list",
            [h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_read",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_rename",
            [
                h,
                h,
                h,
                ctypes.POINTER(StringView),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )
        self._declare(
            "codex_agent_conversations_delete",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversations_open",
            [
                h,
                h,
                ctypes.POINTER(ConversationOpenOptionsStruct),
                OperationCallback,
                ctypes.c_void_p,
                hp,
            ],
        )

        self._declare("codex_agent_conversation_release", [h, hp])
        self._declare("codex_agent_conversation_is_same", [h, h, h, p_i32])
        self._declare(
            "codex_agent_conversation_send",
            [h, h, ctypes.POINTER(StringView), OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_send_request",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_run_shell_command",
            [h, h, ctypes.POINTER(StringView), OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("reload", "cancel_turn", "close"):
            self._declare(
                f"codex_agent_conversation_{name}",
                [h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        self._declare("codex_agent_conversation_state_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_state_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_conversation_state_status", [h, h, p_i32])
        self._declare("codex_agent_conversation_state_failure", [h, h, hp])
        self._declare("codex_agent_conversation_current_messages_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_current_messages_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare("codex_agent_conversation_current_messages_count", [h, h, p_size])
        self._declare(
            "codex_agent_conversation_current_messages_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_conversation_active_turn_progress_get", [h, h, hp])
        self._declare(
            "codex_agent_conversation_active_turn_progress_subscribe",
            [h, h, StateCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_conversation_active_turn_progress_has_value", [h, h, p_i32]
        )
        self._declare("codex_agent_conversation_active_turn_progress_value", [h, h, hp])
        for property_name in (
            "can_start_turn",
            "can_reload",
            "can_cancel_turn",
            "can_run_shell_command",
            "is_turn_active",
        ):
            self._declare(f"codex_agent_conversation_{property_name}_get", [h, h, hp])
            self._declare(
                f"codex_agent_conversation_{property_name}_subscribe",
                [h, h, StateCallback, ctypes.c_void_p, hp],
            )
        self._declare("codex_agent_state_boolean_value", [h, h, p_i32])

        self._declare("codex_agent_operation_cancel", [h, h])
        self._declare("codex_agent_operation_result", [h, h, p_i32])
        self._declare("codex_agent_operation_failure", [h, h, hp])
        self._declare("codex_agent_operation_destroy", [h, hp])
        self._declare("codex_agent_operation_conversation", [h, h, h, hp])
        self._declare("codex_agent_operation_conversation_value", [h, h, hp])
        self._declare(
            "codex_agent_operation_conversation_summaries_count", [h, h, p_size]
        )
        self._declare(
            "codex_agent_operation_conversation_summary_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_subscription_destroy", [h, hp])
        self._declare("codex_agent_snapshot_destroy", [h, hp])

        self._declare("codex_agent_failure_release", [h, hp])
        self._declare("codex_agent_failure_code_copy", [h, h, *bytes_out])
        self._declare("codex_agent_failure_message_copy", [h, h, *bytes_out])
        self._declare("codex_agent_failure_is_recoverable", [h, h, p_i32])
        self._declare(
            "codex_agent_conversation_id_create", [h, ctypes.POINTER(StringView), hp]
        )
        self._declare("codex_agent_conversation_id_destroy", [h, hp])
        self._declare("codex_agent_conversation_id_value_copy", [h, h, *bytes_out])
        self._declare("codex_agent_conversation_summary_destroy", [h, hp])
        self._declare("codex_agent_conversation_summary_conversation_id", [h, h, hp])
        self._declare("codex_agent_conversation_summary_title_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_conversation_summary_updated_at_epoch_seconds", [h, h, p_i64]
        )

        self._declare(
            "codex_agent_turn_request_create",
            [
                h,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                ctypes.POINTER(StringView),
                ctypes.c_int32,
                p_i32,
                ctypes.c_size_t,
                ctypes.POINTER(h),
                ctypes.c_size_t,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_turn_request_destroy", [h, hp])
        self._declare(
            "codex_agent_invocation_plugin_create",
            [h, ctypes.POINTER(StringView), ctypes.POINTER(StringView), hp],
        )
        self._declare("codex_agent_invocation_plugin_destroy", [h, hp])
        self._declare(
            "codex_agent_invocation_skill_create",
            [h, ctypes.POINTER(StringView), ctypes.POINTER(StringView), hp],
        )
        self._declare("codex_agent_invocation_skill_destroy", [h, hp])
        self._declare("codex_agent_invocation_from_plugin", [h, h, hp])
        self._declare("codex_agent_invocation_from_skill", [h, h, hp])
        self._declare("codex_agent_invocation_destroy", [h, hp])
        self._declare("codex_agent_invocation_kind", [h, h, p_i32])
        self._declare("codex_agent_invocation_plugin", [h, h, hp])
        self._declare("codex_agent_invocation_skill", [h, h, hp])
        for kind in ("plugin", "skill"):
            self._declare(
                f"codex_agent_invocation_{kind}_name_copy", [h, h, *bytes_out]
            )
        self._declare("codex_agent_invocation_plugin_uri_copy", [h, h, *bytes_out])
        self._declare("codex_agent_invocation_skill_path_copy", [h, h, *bytes_out])

        self._declare("codex_agent_message_destroy", [h, hp])
        for name in (
            "id",
            "client_message_id",
            "text",
            "reasoning",
            "plan",
            "shell_command",
        ):
            self._declare(f"codex_agent_message_{name}_copy", [h, h, *bytes_out])
        for name in (
            "has_client_message_id",
            "role",
            "collaboration_mode",
            "has_reasoning",
            "has_plan",
            "has_shell_command",
        ):
            self._declare(f"codex_agent_message_{name}", [h, h, p_i32])
        self._declare("codex_agent_message_exit_code", [h, h, p_i32, p_i32])
        self._declare("codex_agent_message_capabilities_count", [h, h, p_size])
        self._declare(
            "codex_agent_message_has_capability", [h, h, ctypes.c_int32, p_i32]
        )
        self._declare("codex_agent_message_invocations_count", [h, h, p_size])
        self._declare("codex_agent_message_invocation_at", [h, h, ctypes.c_size_t, hp])

        self._declare("codex_agent_conversation_value_destroy", [h, hp])
        self._declare("codex_agent_conversation_value_summary", [h, h, hp])
        self._declare("codex_agent_conversation_value_messages_count", [h, h, p_size])
        self._declare(
            "codex_agent_conversation_value_message_at", [h, h, ctypes.c_size_t, hp]
        )

        self._declare("codex_agent_turn_progress_destroy", [h, hp])
        for name in ("text", "commentary", "reasoning", "plan", "shell_output"):
            self._declare(f"codex_agent_turn_progress_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_turn_progress_has_plan_progress", [h, h, p_i32])
        self._declare("codex_agent_turn_progress_plan_progress", [h, h, hp])
        self._declare("codex_agent_turn_progress_shell_exit_code", [h, h, p_i32, p_i32])
        self._declare("codex_agent_turn_progress_work_activity", [h, h, p_i32, p_i32])
        self._declare("codex_agent_turn_progress_hook_activities_count", [h, h, p_size])
        self._declare(
            "codex_agent_turn_progress_hook_activity_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_turn_progress_is_truncated", [h, h, p_i32])

        self._declare("codex_agent_plan_progress_destroy", [h, hp])
        self._declare("codex_agent_plan_progress_has_explanation", [h, h, p_i32])
        self._declare("codex_agent_plan_progress_explanation_copy", [h, h, *bytes_out])
        self._declare("codex_agent_plan_progress_steps_count", [h, h, p_size])
        self._declare("codex_agent_plan_progress_step_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_plan_step_destroy", [h, hp])
        self._declare("codex_agent_plan_step_text_copy", [h, h, *bytes_out])
        self._declare("codex_agent_plan_step_status", [h, h, p_i32])

        self._declare("codex_agent_hook_activity_destroy", [h, hp])
        for name in ("id", "event_name", "handler_type", "status_message"):
            self._declare(f"codex_agent_hook_activity_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_hook_activity_status", [h, h, p_i32])
        self._declare("codex_agent_hook_activity_has_status_message", [h, h, p_i32])
        self._declare("codex_agent_hook_activity_details_count", [h, h, p_size])
        self._declare(
            "codex_agent_hook_activity_detail_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )

        for value in (
            "mcp_environment_variable",
            "mcp_oauth_configuration",
            "mcp_tool_configuration",
            "mcp_transport_http",
            "mcp_transport_stdio",
            "mcp_transport",
            "mcp_server_configuration",
            "mcp_server",
        ):
            self._declare(f"codex_agent_{value}_destroy", [h, hp])

        for name in (
            "mcp_environment_variable_name_copy",
            "mcp_oauth_configuration_client_id_copy",
            "mcp_transport_http_url_copy",
            "mcp_transport_http_bearer_token_environment_variable_copy",
            "mcp_transport_http_headers_helper_copy",
            "mcp_transport_stdio_command_copy",
            "mcp_transport_stdio_working_directory_copy",
            "mcp_server_configuration_name_copy",
            "mcp_server_configuration_environment_id_copy",
            "mcp_server_configuration_oauth_resource_copy",
            "mcp_server_name_copy",
            "mcp_server_display_name_copy",
        ):
            self._declare(f"codex_agent_{name}", [h, h, *bytes_out])
        for name in (
            "mcp_transport_http_headers_key_copy_at",
            "mcp_transport_http_headers_value_copy_at",
            "mcp_transport_http_environment_headers_key_copy_at",
            "mcp_transport_http_environment_headers_value_copy_at",
            "mcp_transport_stdio_argument_copy_at",
            "mcp_transport_stdio_environment_key_copy_at",
            "mcp_transport_stdio_environment_value_copy_at",
            "mcp_server_configuration_enabled_tool_copy_at",
            "mcp_server_configuration_disabled_tool_copy_at",
            "mcp_server_configuration_scope_copy_at",
            "mcp_server_configuration_tools_key_copy_at",
        ):
            self._declare(f"codex_agent_{name}", [h, h, ctypes.c_size_t, *bytes_out])

        for name in (
            "mcp_transport_http_has_bearer_token_environment_variable",
            "mcp_transport_http_has_headers",
            "mcp_transport_http_has_environment_headers",
            "mcp_transport_http_has_headers_helper",
            "mcp_transport_stdio_has_working_directory",
            "mcp_transport_stdio_has_environment",
            "mcp_server_configuration_is_enabled",
            "mcp_server_configuration_is_required",
            "mcp_server_configuration_supports_parallel_tool_calls",
            "mcp_server_configuration_has_omit_tools_from",
            "mcp_server_configuration_has_enabled_tools",
            "mcp_server_configuration_has_disabled_tools",
            "mcp_server_configuration_has_scopes",
            "mcp_server_configuration_has_oauth",
            "mcp_server_configuration_has_oauth_resource",
            "mcp_server_has_configuration",
            "mcp_server_can_remove",
            "mcp_server_is_authorized",
            "mcp_oauth_configuration_has_client_id",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32])
        for name in (
            "mcp_transport_http_headers_count",
            "mcp_transport_http_environment_headers_count",
            "mcp_transport_stdio_arguments_count",
            "mcp_transport_stdio_environment_count",
            "mcp_transport_stdio_forwarded_environment_count",
            "mcp_server_configuration_omit_tools_from_count",
            "mcp_server_configuration_enabled_tools_count",
            "mcp_server_configuration_disabled_tools_count",
            "mcp_server_configuration_scopes_count",
            "mcp_server_configuration_tools_count",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_size])

        for name in (
            "mcp_environment_variable_source",
            "mcp_oauth_configuration_callback_port",
            "mcp_tool_configuration_approval",
            "mcp_server_configuration_authentication",
            "mcp_server_configuration_default_tool_approval",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32, p_i32])
        for name in (
            "mcp_server_configuration_startup_timeout_seconds",
            "mcp_server_configuration_tool_timeout_seconds",
        ):
            self._declare(
                f"codex_agent_{name}",
                [h, h, p_i32, ctypes.POINTER(ctypes.c_double)],
            )
        for name in (
            "mcp_transport_kind",
            "mcp_server_auth_status",
            "mcp_server_origin",
        ):
            self._declare(f"codex_agent_{name}", [h, h, p_i32])
        for name in (
            "mcp_transport_http",
            "mcp_transport_stdio",
            "mcp_server_configuration_transport",
            "mcp_server_configuration_oauth",
            "mcp_server_configuration_tools_value_at",
            "mcp_server_configuration",
        ):
            arguments = [h, h]
            if name.endswith("_value_at"):
                arguments.append(ctypes.c_size_t)
            arguments.append(hp)
            self._declare(f"codex_agent_{name}", arguments)
        for name in ("mcp_transport_stdio_forwarded_environment_at",):
            self._declare(f"codex_agent_{name}", [h, h, ctypes.c_size_t, hp])
        self._declare(
            "codex_agent_mcp_server_configuration_omit_tools_from_at",
            [h, h, ctypes.c_size_t, p_i32],
        )

        p_view = ctypes.POINTER(StringView)
        p_double = ctypes.POINTER(ctypes.c_double)

        self._declare(
            "codex_agent_failure_create", [h, p_view, p_view, ctypes.c_int32, hp]
        )
        self._declare(
            "codex_agent_pending_approval_create", [h, p_view, h, p_view, p_view, hp]
        )
        self._declare("codex_agent_pending_approval_destroy", [h, hp])
        self._declare("codex_agent_pending_elicitation_create", [h, h, hp])
        self._declare("codex_agent_pending_elicitation_destroy", [h, hp])
        self._declare("codex_agent_pending_interaction_from_approval", [h, h, hp])
        self._declare("codex_agent_pending_interaction_from_elicitation", [h, h, hp])
        self._declare("codex_agent_pending_interaction_destroy", [h, hp])
        self._declare(
            "codex_agent_pending_interaction_request_id_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_pending_interaction_conversation_id", [h, h, hp])

        self._declare("codex_agent_form_boolean_value_create", [h, ctypes.c_int32, hp])
        self._declare("codex_agent_form_boolean_value_value", [h, h, p_i32])
        self._declare("codex_agent_form_number_value_create", [h, ctypes.c_double, hp])
        self._declare("codex_agent_form_number_value_value", [h, h, p_double])
        self._declare("codex_agent_form_text_value_create", [h, p_view, hp])
        self._declare("codex_agent_form_text_value_value_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_form_text_list_value_create", [h, p_view, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_form_text_list_value_count", [h, h, p_size])
        self._declare(
            "codex_agent_form_text_list_value_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        for kind in ("boolean", "number", "text", "text_list"):
            self._declare(f"codex_agent_form_value_from_{kind}", [h, h, hp])
            self._declare(f"codex_agent_form_value_{kind}", [h, h, hp])
        self._declare("codex_agent_form_value_destroy", [h, hp])
        self._declare("codex_agent_form_value_kind", [h, h, p_i32])

        self._declare(
            "codex_agent_form_option_create",
            [h, p_view, ctypes.c_int32, p_view, ctypes.c_int32, p_view, hp],
        )
        self._declare("codex_agent_form_option_destroy", [h, hp])
        self._declare(
            "codex_agent_form_field_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                h,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_form_field_destroy", [h, hp])
        self._declare("codex_agent_form_field_accepts", [h, h, h, p_i32])

        self._declare(
            "codex_agent_elicitation_create",
            [
                h,
                p_view,
                p_view,
                h,
                p_view,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_elicitation_destroy", [h, hp])
        self._declare(
            "codex_agent_elicitation_response_create",
            [h, ctypes.c_int32, p_view, hp, ctypes.c_size_t, hp],
        )
        self._declare("codex_agent_elicitation_response_destroy", [h, hp])
        self._declare("codex_agent_elicitation_response_action", [h, h, p_i32])
        self._declare("codex_agent_elicitation_response_content_count", [h, h, p_size])
        self._declare(
            "codex_agent_elicitation_response_content_value", [h, h, p_view, hp]
        )

        self._declare(
            "codex_agent_form_content_create", [h, p_view, hp, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_form_content_destroy", [h, hp])
        self._declare("codex_agent_form_content_count", [h, h, p_size])
        self._declare(
            "codex_agent_form_content_key_copy", [h, h, ctypes.c_size_t, *bytes_out]
        )
        self._declare("codex_agent_form_content_value_at", [h, h, p_view, hp])
        self._declare("codex_agent_elicitation_initial_values", [h, h, hp])
        self._declare("codex_agent_elicitation_validate", [h, h, h, hp])
        self._declare("codex_agent_elicitation_accept", [h, h, h, hp])
        self._declare("codex_agent_elicitation_accepts", [h, h, h, p_i32])
        self._declare("codex_agent_elicitation_response_decline", [h, hp])
        self._declare("codex_agent_elicitation_response_cancel", [h, hp])

        self._declare("codex_agent_elicitation_validation_destroy", [h, hp])
        self._declare("codex_agent_elicitation_validation_issue_count", [h, h, p_size])
        self._declare(
            "codex_agent_elicitation_validation_issue_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_elicitation_validation_issue_destroy", [h, hp])
        self._declare(
            "codex_agent_elicitation_validation_issue_field_name_copy",
            [h, h, *bytes_out],
        )
        self._declare("codex_agent_elicitation_validation_issue_reason", [h, h, p_i32])

        self._declare(
            "codex_agent_interaction_state_create",
            [h, hp, ctypes.c_size_t, p_view, ctypes.c_size_t, ctypes.c_int32, h, hp],
        )
        self._declare("codex_agent_interaction_state_destroy", [h, hp])
        self._declare(
            "codex_agent_interaction_state_resolving_request_ids_contains",
            [h, h, p_view, p_i32],
        )
        self._declare("codex_agent_interaction_state_is_resolving", [h, h, h, p_i32])
        self._declare("codex_agent_interaction_state_pending_for", [h, h, h, hp])
        self._declare("codex_agent_pending_interaction_list_destroy", [h, hp])
        self._declare("codex_agent_pending_interaction_list_count", [h, h, p_size])
        self._declare(
            "codex_agent_pending_interaction_list_at", [h, h, ctypes.c_size_t, hp]
        )

        self._declare("codex_agent_authorization_url_chat_gpt", [h, p_view, hp])
        self._declare("codex_agent_authorization_url_external", [h, p_view, hp])
        self._declare("codex_agent_authorization_url_destroy", [h, hp])
        self._declare("codex_agent_authorization_url_value_copy", [h, h, *bytes_out])
        self._declare("codex_agent_authorization_url_purpose", [h, h, p_i32])

        self._declare_service_api()

    def _declare_service_api(self) -> None:
        h = Handle
        hp = HandlePointer
        p_i32 = ctypes.POINTER(ctypes.c_int32)
        p_i64 = ctypes.POINTER(ctypes.c_int64)
        p_size = ctypes.POINTER(ctypes.c_size_t)
        p_double = ctypes.POINTER(ctypes.c_double)
        p_view = ctypes.POINTER(StringView)
        bytes_out = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, p_size]

        for owner in (
            "authentication",
            "interactions",
            "integration_authorization",
            "models",
            "skills",
            "hooks",
            "plugins",
            "connectors",
            "mcp_servers",
        ):
            self._declare(f"codex_agent_{owner}_release", [h, hp])
        for owner in ("skills", "hooks", "plugins", "connectors", "mcp_servers"):
            self._declare(f"codex_agent_{owner}_is_available", [h, h, p_i32])

        for suffix in ("api_key", "chat_gpt_browser", "chat_gpt_device_code"):
            arguments = [h]
            if suffix == "api_key":
                arguments.append(p_view)
            arguments.append(hp)
            self._declare(
                f"codex_agent_authentication_method_{suffix}_create", arguments
            )
            self._declare(
                f"codex_agent_authentication_method_{suffix}_destroy", [h, hp]
            )
            self._declare(
                f"codex_agent_authentication_authenticate_{suffix}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for suffix in ("cancel", "sign_out"):
            self._declare(
                f"codex_agent_authentication_{suffix}",
                [h, h, OperationCallback, ctypes.c_void_p, hp],
            )

        state_owners = {
            "authentication": ("state", "is_authenticated", "is_authenticating"),
            "integration_authorization": ("state", "active", "is_authorizing"),
            "interactions": ("state", "approvals", "elicitations"),
        }
        for owner, properties in state_owners.items():
            for property_name in properties:
                self._declare(f"codex_agent_{owner}_{property_name}_get", [h, h, hp])
                self._declare(
                    f"codex_agent_{owner}_{property_name}_subscribe",
                    [h, h, StateCallback, ctypes.c_void_p, hp],
                )
        for name in (
            "authentication_state_value",
            "integration_authorization_state_value",
            "integration_authorization_active_value",
            "interactions_state_value",
        ):
            self._declare(f"codex_agent_{name}", [h, h, hp])
        self._declare(
            "codex_agent_integration_authorization_active_has_value", [h, h, p_i32]
        )
        for name in ("interactions_approvals", "interactions_elicitations"):
            self._declare(f"codex_agent_{name}_count", [h, h, p_size])
            self._declare(f"codex_agent_{name}_at", [h, h, ctypes.c_size_t, hp])

        self._declare("codex_agent_authentication_state_destroy", [h, hp])
        self._declare("codex_agent_authentication_state_status", [h, h, p_i32])
        for name in (
            "pending_sign_in_url",
            "device_verification_url",
            "device_user_code",
            "failure",
        ):
            self._declare(f"codex_agent_authentication_state_has_{name}", [h, h, p_i32])
        for name in ("pending_sign_in_url", "device_verification_url", "failure"):
            self._declare(f"codex_agent_authentication_state_{name}", [h, h, hp])
        self._declare(
            "codex_agent_authentication_state_device_user_code_copy", [h, h, *bytes_out]
        )

        self._declare("codex_agent_integration_authorization_state_destroy", [h, hp])
        self._declare(
            "codex_agent_integration_authorization_state_status", [h, h, p_i32]
        )
        self._declare("codex_agent_integration_authorization_state_target", [h, h, hp])
        self._declare("codex_agent_integration_authorization_state_failure", [h, h, hp])
        self._declare(
            "codex_agent_integration_authorization_authorize",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_integration_authorization_cancel",
            [h, h, OperationCallback, ctypes.c_void_p, hp],
        )

        self._declare("codex_agent_interaction_state_pending_count", [h, h, p_size])
        self._declare(
            "codex_agent_interaction_state_pending_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare(
            "codex_agent_interaction_state_resolving_request_ids_count", [h, h, p_size]
        )
        self._declare("codex_agent_interaction_state_has_failure", [h, h, p_i32])
        self._declare("codex_agent_interaction_state_failure", [h, h, hp])
        self._declare("codex_agent_pending_interaction_kind", [h, h, p_i32])
        self._declare("codex_agent_pending_interaction_approval", [h, h, hp])
        self._declare("codex_agent_pending_interaction_elicitation", [h, h, hp])
        for name in ("request_id", "title", "details"):
            self._declare(
                f"codex_agent_pending_approval_{name}_copy", [h, h, *bytes_out]
            )
        self._declare("codex_agent_pending_approval_conversation_id", [h, h, hp])
        self._declare("codex_agent_pending_elicitation_elicitation", [h, h, hp])
        self._declare("codex_agent_elicitation_conversation_id", [h, h, hp])
        for name in ("request_id", "server_name", "message", "url"):
            self._declare(f"codex_agent_elicitation_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_elicitation_has_form", [h, h, p_i32])
        self._declare("codex_agent_elicitation_form_count", [h, h, p_size])
        self._declare("codex_agent_elicitation_form_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_elicitation_has_url", [h, h, p_i32])
        for name, arguments in (
            ("open_url", [h]),
            ("resolve_approval", [h, ctypes.c_int32]),
            ("resolve_elicitation", [h, h]),
        ):
            self._declare(
                f"codex_agent_interactions_{name}",
                [h, h, *arguments, OperationCallback, ctypes.c_void_p, hp],
            )

        for name in ("name", "title"):
            self._declare(f"codex_agent_form_field_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_form_field_has_description", [h, h, p_i32])
        self._declare("codex_agent_form_field_description_copy", [h, h, *bytes_out])
        for name in (
            "is_required",
            "type",
            "has_default_value",
            "allows_other",
            "is_secret",
        ):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32])
        self._declare("codex_agent_form_field_options_count", [h, h, p_size])
        self._declare("codex_agent_form_field_option_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_form_field_default_value", [h, h, hp])
        for name in ("minimum", "maximum"):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32, p_double])
        self._declare("codex_agent_form_field_format", [h, h, p_i32, p_i32])
        for name in (
            "minimum_length",
            "maximum_length",
            "minimum_selections",
            "maximum_selections",
        ):
            self._declare(f"codex_agent_form_field_{name}", [h, h, p_i32, p_i64])
        self._declare("codex_agent_form_option_destroy", [h, hp])
        for name in ("value", "title", "description"):
            self._declare(f"codex_agent_form_option_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_form_option_has_description", [h, h, p_i32])

        for name in (
            "models_list",
            "hooks_list",
            "mcp_servers_list",
        ):
            self._declare(
                f"codex_agent_{name}", [h, h, OperationCallback, ctypes.c_void_p, hp]
            )
        self._declare(
            "codex_agent_models_resolve",
            [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("resolve_effort", "resolve_service_tier"):
            self._declare(
                f"codex_agent_models_{name}",
                [h, h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
            )
        self._declare(
            "codex_agent_skills_list",
            [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_read",
            [h, h, p_view, ctypes.c_int64, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_install",
            [h, h, p_view, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_skills_uninstall",
            [h, h, h, OperationCallback, ctypes.c_void_p, hp],
        )
        self._declare(
            "codex_agent_hooks_install",
            [h, h, p_view, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
        )
        for name in ("uninstall", "trust"):
            self._declare(
                f"codex_agent_hooks_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for owner in ("plugins", "connectors"):
            self._declare(
                f"codex_agent_{owner}_list",
                [h, h, ctypes.c_int32, OperationCallback, ctypes.c_void_p, hp],
            )
        for name in ("read", "install", "uninstall"):
            self._declare(
                f"codex_agent_plugins_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )
        for name in ("add", "remove"):
            self._declare(
                f"codex_agent_mcp_servers_{name}",
                [h, h, h, OperationCallback, ctypes.c_void_p, hp],
            )

        for name in ("models", "connectors", "mcp_servers"):
            self._declare(f"codex_agent_operation_{name}_count", [h, h, p_size])
        for name in ("model", "connector", "mcp_server"):
            self._declare(
                f"codex_agent_operation_{name}_at", [h, h, ctypes.c_size_t, hp]
            )
        for name in (
            "model",
            "service_tier",
            "skill_catalog",
            "skill_chunk",
            "skill",
            "hook_catalog",
            "hook",
            "plugin_catalog",
            "plugin_detail",
            "plugin_install_result",
            "mcp_server",
        ):
            self._declare(f"codex_agent_operation_{name}", [h, h, hp])
        self._declare("codex_agent_operation_string_copy", [h, h, *bytes_out])
        self._declare("codex_agent_operation_has_service_tier", [h, h, p_i32])

        self._declare(
            "codex_agent_service_tier_create", [h, p_view, p_view, p_view, hp]
        )
        self._declare("codex_agent_service_tier_destroy", [h, hp])
        for name in ("id", "name", "description"):
            self._declare(f"codex_agent_service_tier_{name}_copy", [h, h, *bytes_out])
        self._declare(
            "codex_agent_model_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                p_view,
                ctypes.c_size_t,
                p_view,
                ctypes.c_int32,
                hp,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_model_destroy", [h, hp])
        for name in ("id", "display_name", "description", "default_effort"):
            self._declare(f"codex_agent_model_{name}_copy", [h, h, *bytes_out])
        self._declare("codex_agent_model_supported_efforts_count", [h, h, p_size])
        self._declare(
            "codex_agent_model_supported_effort_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_model_is_default", [h, h, p_i32])
        self._declare("codex_agent_model_service_tiers_count", [h, h, p_size])
        self._declare("codex_agent_model_service_tier_at", [h, h, ctypes.c_size_t, hp])
        self._declare("codex_agent_model_has_default_service_tier", [h, h, p_i32])
        self._declare("codex_agent_model_default_service_tier_copy", [h, h, *bytes_out])

        self._declare(
            "codex_agent_connector_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare("codex_agent_connector_destroy", [h, hp])
        for name in ("id", "name", "description", "install_url"):
            self._declare(f"codex_agent_connector_{name}_copy", [h, h, *bytes_out])
        for name in ("has_install_url", "is_accessible", "is_enabled"):
            self._declare(f"codex_agent_connector_{name}", [h, h, p_i32])
        self._declare("codex_agent_connector_plugin_names_count", [h, h, p_size])
        self._declare(
            "codex_agent_connector_plugin_names_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )

        self._declare(
            "codex_agent_plugin_reference_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare("codex_agent_plugin_reference_destroy", [h, hp])
        for name in (
            "id",
            "name",
            "marketplace_name",
            "marketplace_path",
            "remote_plugin_id",
            "uri",
        ):
            self._declare(
                f"codex_agent_plugin_reference_{name}_copy", [h, h, *bytes_out]
            )
        for name in ("has_marketplace_path", "has_remote_plugin_id"):
            self._declare(f"codex_agent_plugin_reference_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_skill_destroy", [h, hp])
        for name in ("name", "description", "path"):
            self._declare(f"codex_agent_plugin_skill_{name}_copy", [h, h, *bytes_out])
        for name in ("is_enabled", "has_path"):
            self._declare(f"codex_agent_plugin_skill_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_summary_destroy", [h, hp])
        self._declare("codex_agent_plugin_summary_reference", [h, h, hp])
        for name in (
            "display_name",
            "description",
            "brand_color",
            "privacy_policy_url",
            "terms_of_service_url",
            "website_url",
        ):
            self._declare(f"codex_agent_plugin_summary_{name}_copy", [h, h, *bytes_out])
        for name in (
            "is_installed",
            "is_enabled",
            "install_policy",
            "auth_policy",
            "is_available",
            "has_brand_color",
            "has_privacy_policy_url",
            "has_terms_of_service_url",
            "has_website_url",
        ):
            self._declare(f"codex_agent_plugin_summary_{name}", [h, h, p_i32])
        self._declare("codex_agent_plugin_summary_capabilities_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_summary_capabilities_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_catalog_destroy", [h, hp])
        self._declare("codex_agent_plugin_catalog_plugins_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_catalog_plugins_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_plugin_catalog_errors_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_catalog_errors_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_catalog_freshness", [h, h, p_i32])
        self._declare("codex_agent_plugin_detail_destroy", [h, hp])
        self._declare("codex_agent_plugin_detail_summary", [h, h, hp])
        self._declare("codex_agent_plugin_detail_description_copy", [h, h, *bytes_out])
        for name, child in (("skills", "skill"), ("connectors", "connector")):
            self._declare(f"codex_agent_plugin_detail_{name}_count", [h, h, p_size])
            self._declare(
                f"codex_agent_plugin_detail_{name}_at", [h, h, ctypes.c_size_t, hp]
            )
        self._declare("codex_agent_plugin_detail_mcp_servers_count", [h, h, p_size])
        self._declare(
            "codex_agent_plugin_detail_mcp_servers_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_plugin_detail_hook_count", [h, h, p_i32])
        self._declare("codex_agent_plugin_install_result_destroy", [h, hp])
        self._declare("codex_agent_plugin_install_result_auth_policy", [h, h, p_i32])
        self._declare(
            "codex_agent_plugin_install_result_connectors_count", [h, h, p_size]
        )
        self._declare(
            "codex_agent_plugin_install_result_connectors_at",
            [h, h, ctypes.c_size_t, hp],
        )
        self._declare("codex_agent_plugin_install_result_has_message", [h, h, p_i32])
        self._declare(
            "codex_agent_plugin_install_result_message_copy", [h, h, *bytes_out]
        )

        self._declare(
            "codex_agent_skill_create",
            [
                h,
                p_view,
                p_view,
                p_view,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_skill_destroy", [h, hp])
        for name in ("name", "display_name", "description", "path", "brand_color"):
            self._declare(f"codex_agent_skill_{name}_copy", [h, h, *bytes_out])
        for name in (
            "scope",
            "is_enabled",
            "has_brand_color",
            "can_uninstall",
            "origin",
        ):
            self._declare(f"codex_agent_skill_{name}", [h, h, p_i32])
        self._declare("codex_agent_skill_dependencies_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_dependencies_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_skill_catalog_destroy", [h, hp])
        self._declare("codex_agent_skill_catalog_skills_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_catalog_skills_at", [h, h, ctypes.c_size_t, hp]
        )
        self._declare("codex_agent_skill_catalog_errors_count", [h, h, p_size])
        self._declare(
            "codex_agent_skill_catalog_errors_copy_at",
            [h, h, ctypes.c_size_t, *bytes_out],
        )
        self._declare("codex_agent_skill_chunk_destroy", [h, hp])
        self._declare("codex_agent_skill_chunk_content_copy", [h, h, *bytes_out])
        self._declare("codex_agent_skill_chunk_next_offset", [h, h, p_i32, p_i64])
        self._declare("codex_agent_skill_chunk_total_bytes", [h, h, p_i64])

        for name in ("agent", "prompt"):
            self._declare(f"codex_agent_hook_handler_{name}_acquire", [h, hp])
            self._declare(f"codex_agent_hook_handler_{name}_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_command_create", [h, p_view, ctypes.c_int32, hp]
        )
        self._declare("codex_agent_hook_handler_command_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_command_command_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_hook_handler_command_is_async", [h, h, p_i32])
        self._declare(
            "codex_agent_hook_handler_mcp_tool_create", [h, p_view, p_view, hp]
        )
        self._declare("codex_agent_hook_handler_mcp_tool_destroy", [h, hp])
        self._declare(
            "codex_agent_hook_handler_mcp_tool_server_copy", [h, h, *bytes_out]
        )
        self._declare("codex_agent_hook_handler_mcp_tool_tool_copy", [h, h, *bytes_out])
        for name in ("agent", "command", "mcp_tool", "prompt"):
            self._declare(f"codex_agent_hook_handler_from_{name}", [h, h, hp])
            self._declare(f"codex_agent_hook_handler_{name}", [h, h, hp])
        self._declare("codex_agent_hook_handler_destroy", [h, hp])
        self._declare("codex_agent_hook_handler_kind", [h, h, p_i32])
        self._declare(
            "codex_agent_hook_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_int32,
                p_view,
                h,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_int64,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                hp,
            ],
        )
        self._declare("codex_agent_hook_destroy", [h, hp])
        for name in (
            "key",
            "current_hash",
            "event_name",
            "source",
            "source_path",
            "matcher",
            "plugin_id",
            "status_message",
        ):
            self._declare(f"codex_agent_hook_{name}_copy", [h, h, *bytes_out])
        for name in (
            "is_enabled",
            "is_managed",
            "trust_status",
            "has_matcher",
            "has_plugin_id",
            "has_status_message",
            "origin",
            "can_uninstall",
            "can_trust",
        ):
            self._declare(f"codex_agent_hook_{name}", [h, h, p_i32])
        self._declare("codex_agent_hook_handler", [h, h, hp])
        self._declare("codex_agent_hook_timeout_seconds", [h, h, p_i64])
        self._declare("codex_agent_hook_catalog_destroy", [h, hp])
        for name in ("hooks", "warnings", "errors"):
            self._declare(f"codex_agent_hook_catalog_{name}_count", [h, h, p_size])
        self._declare("codex_agent_hook_catalog_hooks_at", [h, h, ctypes.c_size_t, hp])
        for name in ("warnings", "errors"):
            self._declare(
                f"codex_agent_hook_catalog_{name}_copy_at",
                [h, h, ctypes.c_size_t, *bytes_out],
            )

        for name in ("connector", "mcp_server"):
            self._declare(f"codex_agent_integration_{name}_create", [h, h, hp])
            self._declare(f"codex_agent_integration_{name}_destroy", [h, hp])
            self._declare(f"codex_agent_integration_from_{name}", [h, h, hp])
            self._declare(f"codex_agent_integration_{name}", [h, h, hp])
        self._declare("codex_agent_integration_connector_connector", [h, h, hp])
        self._declare("codex_agent_integration_mcp_server_server", [h, h, hp])
        self._declare("codex_agent_integration_destroy", [h, hp])
        self._declare("codex_agent_integration_kind", [h, h, p_i32])

        self._declare(
            "codex_agent_mcp_environment_variable_create",
            [h, p_view, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_oauth_configuration_create",
            [h, ctypes.c_int32, p_view, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_tool_configuration_create",
            [h, ctypes.c_int32, ctypes.c_int32, hp],
        )
        self._declare(
            "codex_agent_mcp_transport_http_create",
            [
                h,
                p_view,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                hp,
            ],
        )
        self._declare(
            "codex_agent_mcp_transport_stdio_create",
            [
                h,
                p_view,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                p_view,
                p_view,
                ctypes.c_size_t,
                hp,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare("codex_agent_mcp_transport_from_http", [h, h, hp])
        self._declare("codex_agent_mcp_transport_from_stdio", [h, h, hp])
        self._declare(
            "codex_agent_mcp_server_configuration_create",
            [
                h,
                p_view,
                h,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_i32,
                ctypes.c_size_t,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_double,
                ctypes.c_int32,
                ctypes.c_int32,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                p_view,
                ctypes.c_size_t,
                ctypes.c_int32,
                h,
                ctypes.c_int32,
                p_view,
                p_view,
                hp,
                ctypes.c_size_t,
                hp,
            ],
        )
        self._declare(
            "codex_agent_mcp_server_create",
            [h, p_view, p_view, ctypes.c_int32, h, ctypes.c_int32, ctypes.c_int32, hp],
        )
        for name in ("boolean", "number", "text", "text_list"):
            self._declare(f"codex_agent_form_{name}_value_destroy", [h, hp])


def load_native(path: str | os.PathLike[str] | None = None) -> NativeLibrary:
    return NativeLibrary.load(path)
