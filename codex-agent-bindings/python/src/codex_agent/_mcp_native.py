from __future__ import annotations

import ctypes
from collections.abc import Mapping, Sequence

from ._enums import (
    McpAuthentication,
    McpAuthStatus,
    McpEnvironmentSource,
    McpToolApproval,
    McpToolExposureSurface,
    ResourceOrigin,
)
from ._ffi import Handle, NativeLibrary, StringView, null_view, utf8_view
from ._mcp_values import (
    McpEnvironmentVariable,
    McpHttpTransport,
    McpOauthConfiguration,
    McpServer,
    McpServerConfiguration,
    McpStdioTransport,
    McpToolConfiguration,
    McpTransport,
)


def _i32(native: NativeLibrary, name: str, *prefix: object) -> int:
    result = ctypes.c_int32()
    native.call(name, *prefix, ctypes.byref(result))
    return result.value


def _size(native: NativeLibrary, name: str, *prefix: object) -> int:
    result = ctypes.c_size_t()
    native.call(name, *prefix, ctypes.byref(result))
    return result.value


def _handle(native: NativeLibrary, name: str, *prefix: object) -> Handle:
    result = Handle()
    native.call(name, *prefix, ctypes.byref(result))
    if not result.value:
        raise RuntimeError(f"{name} returned an absent owned value")
    return result


def _view(value: str | None) -> tuple[StringView, object | None]:
    return (null_view(), None) if value is None else utf8_view(value)


def _views(values: Sequence[str]) -> tuple[object, tuple[object | None, ...]]:
    converted = tuple(utf8_view(value) for value in values)
    return (
        (StringView * len(converted))(*(view for view, _ in converted))
        if converted
        else None,
        tuple(backing for _, backing in converted),
    )


def _mapping_views(
    values: Mapping[str, str] | None,
) -> tuple[object, object, tuple[object | None, ...], tuple[object | None, ...]]:
    items = tuple((values or {}).items())
    keys, key_backings = _views(tuple(key for key, _ in items))
    mapped, value_backings = _views(tuple(value for _, value in items))
    return keys, mapped, key_backings, value_backings


def _handles(values: Sequence[Handle]) -> object:
    return (Handle * len(values))(*(value.value for value in values)) if values else None


def _destroy(native: NativeLibrary, context: Handle, name: str, value: Handle) -> None:
    if value.value:
        native.call(name, context, ctypes.byref(value))


def _create_environment_variable(
    native: NativeLibrary, context: Handle, value: McpEnvironmentVariable
) -> Handle:
    name, backing = utf8_view(value.name)
    return _handle(
        native,
        "codex_agent_mcp_environment_variable_create",
        context,
        ctypes.byref(name),
        int(value.source is not None),
        0 if value.source is None else int(value.source),
    )


def _create_oauth(
    native: NativeLibrary, context: Handle, value: McpOauthConfiguration
) -> Handle:
    client_id, backing = _view(value.client_id)
    return _handle(
        native,
        "codex_agent_mcp_oauth_configuration_create",
        context,
        int(value.client_id is not None),
        ctypes.byref(client_id),
        int(value.callback_port is not None),
        0 if value.callback_port is None else value.callback_port,
    )


def _create_tool(
    native: NativeLibrary, context: Handle, value: McpToolConfiguration
) -> Handle:
    return _handle(
        native,
        "codex_agent_mcp_tool_configuration_create",
        context,
        int(value.approval is not None),
        0 if value.approval is None else int(value.approval),
    )


def _create_transport(
    native: NativeLibrary, context: Handle, value: McpTransport
) -> Handle:
    if isinstance(value, McpHttpTransport):
        url, url_backing = utf8_view(value.url)
        bearer, bearer_backing = _view(value.bearer_token_environment_variable)
        header_keys, header_values, header_key_backings, header_value_backings = (
            _mapping_views(value.headers)
        )
        environment_keys, environment_values, environment_key_backings, environment_value_backings = (
            _mapping_views(value.environment_headers)
        )
        helper, helper_backing = _view(value.headers_helper)
        concrete = _handle(
            native,
            "codex_agent_mcp_transport_http_create",
            context,
            ctypes.byref(url),
            int(value.bearer_token_environment_variable is not None),
            ctypes.byref(bearer),
            int(value.headers is not None),
            header_keys,
            header_values,
            len(value.headers or ()),
            int(value.environment_headers is not None),
            environment_keys,
            environment_values,
            len(value.environment_headers or ()),
            int(value.headers_helper is not None),
            ctypes.byref(helper),
        )
        suffix = "http"
    elif isinstance(value, McpStdioTransport):
        command, command_backing = utf8_view(value.command)
        arguments, argument_backings = _views(value.arguments)
        working_directory, working_directory_backing = _view(value.working_directory)
        environment_keys, environment_values, environment_key_backings, environment_value_backings = (
            _mapping_views(value.environment)
        )
        forwarded = tuple(
            _create_environment_variable(native, context, variable)
            for variable in value.forwarded_environment
        )
        try:
            concrete = _handle(
                native,
                "codex_agent_mcp_transport_stdio_create",
                context,
                ctypes.byref(command),
                arguments,
                len(value.arguments),
                int(value.working_directory is not None),
                ctypes.byref(working_directory),
                int(value.environment is not None),
                environment_keys,
                environment_values,
                len(value.environment or ()),
                _handles(forwarded),
                len(forwarded),
            )
        finally:
            for variable in forwarded:
                _destroy(
                    native,
                    context,
                    "codex_agent_mcp_environment_variable_destroy",
                    variable,
                )
        suffix = "stdio"
    else:
        raise TypeError(f"unsupported MCP transport: {type(value).__name__}")
    try:
        return _handle(native, f"codex_agent_mcp_transport_from_{suffix}", context, concrete)
    finally:
        _destroy(native, context, f"codex_agent_mcp_transport_{suffix}_destroy", concrete)


def create_mcp_configuration(
    native: NativeLibrary, context: Handle, value: McpServerConfiguration
) -> Handle:
    """Creates one same-context input handle; the caller owns the result."""

    name, name_backing = utf8_view(value.name)
    environment_id, environment_backing = utf8_view(value.environment_id)
    omit_values = tuple(int(item) for item in value.omit_tools_from or ())
    omit = (
        (ctypes.c_int32 * len(omit_values))(*omit_values) if omit_values else None
    )
    enabled, enabled_backings = _views(value.enabled_tools or ())
    disabled, disabled_backings = _views(value.disabled_tools or ())
    scopes, scope_backings = _views(value.scopes or ())
    oauth_resource, oauth_resource_backing = _view(value.oauth_resource)
    tool_items = tuple(value.tools.items())
    tool_keys, tool_key_backings = _views(tuple(key for key, _ in tool_items))
    tools = tuple(_create_tool(native, context, tool) for _, tool in tool_items)
    oauth = _create_oauth(native, context, value.oauth) if value.oauth is not None else Handle()
    transport = _create_transport(native, context, value.transport)
    try:
        return _handle(
            native,
            "codex_agent_mcp_server_configuration_create",
            context,
            ctypes.byref(name),
            transport,
            int(value.authentication is not None),
            0 if value.authentication is None else int(value.authentication),
            ctypes.byref(environment_id),
            int(value.is_enabled),
            int(value.is_required),
            int(value.supports_parallel_tool_calls),
            int(value.omit_tools_from is not None),
            omit,
            len(omit_values),
            int(value.startup_timeout_seconds is not None),
            0.0 if value.startup_timeout_seconds is None else value.startup_timeout_seconds,
            int(value.tool_timeout_seconds is not None),
            0.0 if value.tool_timeout_seconds is None else value.tool_timeout_seconds,
            int(value.default_tool_approval is not None),
            0 if value.default_tool_approval is None else int(value.default_tool_approval),
            int(value.enabled_tools is not None),
            enabled,
            len(value.enabled_tools or ()),
            int(value.disabled_tools is not None),
            disabled,
            len(value.disabled_tools or ()),
            int(value.scopes is not None),
            scopes,
            len(value.scopes or ()),
            int(value.oauth is not None),
            oauth,
            int(value.oauth_resource is not None),
            ctypes.byref(oauth_resource),
            tool_keys,
            _handles(tools),
            len(tools),
        )
    finally:
        _destroy(native, context, "codex_agent_mcp_transport_destroy", transport)
        _destroy(native, context, "codex_agent_mcp_oauth_configuration_destroy", oauth)
        for tool in tools:
            _destroy(native, context, "codex_agent_mcp_tool_configuration_destroy", tool)


def create_mcp_server(native: NativeLibrary, context: Handle, value: McpServer) -> Handle:
    """Creates one same-context input handle; the caller owns the result."""

    name, name_backing = utf8_view(value.name)
    display_name, display_name_backing = utf8_view(value.display_name)
    configuration = (
        create_mcp_configuration(native, context, value.configuration)
        if value.configuration is not None
        else Handle()
    )
    try:
        return _handle(
            native,
            "codex_agent_mcp_server_create",
            context,
            ctypes.byref(name),
            ctypes.byref(display_name),
            int(value.auth_status),
            configuration,
            int(value.origin),
            int(value.can_remove),
        )
    finally:
        _destroy(
            native,
            context,
            "codex_agent_mcp_server_configuration_destroy",
            configuration,
        )


def _optional_scalar(
    native: NativeLibrary,
    name: str,
    c_type: type[ctypes.c_int32] | type[ctypes.c_double],
    context: Handle,
    value: Handle,
) -> int | float | None:
    present = ctypes.c_int32()
    result = c_type()
    native.call(name, context, value, ctypes.byref(present), ctypes.byref(result))
    return result.value if present.value else None


def _optional_string(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    presence_name: str,
    copy_name: str,
) -> str | None:
    return (
        native.copy_string(copy_name, context, value)
        if _i32(native, presence_name, context, value)
        else None
    )


def _string_list(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    count_name: str,
    copy_name: str,
) -> tuple[str, ...]:
    return tuple(
        native.copy_string(copy_name, context, value, index)
        for index in range(_size(native, count_name, context, value))
    )


def _optional_string_list(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    presence_name: str,
    count_name: str,
    copy_name: str,
) -> tuple[str, ...] | None:
    if not _i32(native, presence_name, context, value):
        return None
    return _string_list(native, context, value, count_name, copy_name)


def _optional_string_map(
    native: NativeLibrary,
    context: Handle,
    value: Handle,
    presence_name: str,
    count_name: str,
    key_name: str,
    value_name: str,
) -> dict[str, str] | None:
    if not _i32(native, presence_name, context, value):
        return None
    result: dict[str, str] = {}
    for index in range(_size(native, count_name, context, value)):
        key = native.copy_string(key_name, context, value, index)
        if key in result:
            raise RuntimeError(f"{count_name} returned duplicate key {key!r}")
        result[key] = native.copy_string(value_name, context, value, index)
    return result


def _read_environment_variable(
    native: NativeLibrary, context: Handle, variable: Handle
) -> McpEnvironmentVariable:
    try:
        source = _optional_scalar(
            native,
            "codex_agent_mcp_environment_variable_source",
            ctypes.c_int32,
            context,
            variable,
        )
        return McpEnvironmentVariable(
            native.copy_string(
                "codex_agent_mcp_environment_variable_name_copy", context, variable
            ),
            None if source is None else McpEnvironmentSource(source),
        )
    finally:
        _destroy(
            native,
            context,
            "codex_agent_mcp_environment_variable_destroy",
            variable,
        )


def _read_oauth(
    native: NativeLibrary, context: Handle, oauth: Handle
) -> McpOauthConfiguration:
    try:
        client_id = _optional_string(
            native,
            context,
            oauth,
            "codex_agent_mcp_oauth_configuration_has_client_id",
            "codex_agent_mcp_oauth_configuration_client_id_copy",
        )
        port = _optional_scalar(
            native,
            "codex_agent_mcp_oauth_configuration_callback_port",
            ctypes.c_int32,
            context,
            oauth,
        )
        return McpOauthConfiguration(client_id, None if port is None else int(port))
    finally:
        _destroy(
            native, context, "codex_agent_mcp_oauth_configuration_destroy", oauth
        )


def _read_tool(
    native: NativeLibrary, context: Handle, tool: Handle
) -> McpToolConfiguration:
    try:
        approval = _optional_scalar(
            native,
            "codex_agent_mcp_tool_configuration_approval",
            ctypes.c_int32,
            context,
            tool,
        )
        return McpToolConfiguration(
            None if approval is None else McpToolApproval(approval)
        )
    finally:
        _destroy(native, context, "codex_agent_mcp_tool_configuration_destroy", tool)


def _read_http(
    native: NativeLibrary, context: Handle, transport: Handle
) -> McpHttpTransport:
    http = _handle(native, "codex_agent_mcp_transport_http", context, transport)
    try:
        return McpHttpTransport(
            native.copy_string("codex_agent_mcp_transport_http_url_copy", context, http),
            _optional_string(
                native,
                context,
                http,
                "codex_agent_mcp_transport_http_has_bearer_token_environment_variable",
                "codex_agent_mcp_transport_http_bearer_token_environment_variable_copy",
            ),
            _optional_string_map(
                native,
                context,
                http,
                "codex_agent_mcp_transport_http_has_headers",
                "codex_agent_mcp_transport_http_headers_count",
                "codex_agent_mcp_transport_http_headers_key_copy_at",
                "codex_agent_mcp_transport_http_headers_value_copy_at",
            ),
            _optional_string_map(
                native,
                context,
                http,
                "codex_agent_mcp_transport_http_has_environment_headers",
                "codex_agent_mcp_transport_http_environment_headers_count",
                "codex_agent_mcp_transport_http_environment_headers_key_copy_at",
                "codex_agent_mcp_transport_http_environment_headers_value_copy_at",
            ),
            _optional_string(
                native,
                context,
                http,
                "codex_agent_mcp_transport_http_has_headers_helper",
                "codex_agent_mcp_transport_http_headers_helper_copy",
            ),
        )
    finally:
        _destroy(native, context, "codex_agent_mcp_transport_http_destroy", http)


def _read_stdio(
    native: NativeLibrary, context: Handle, transport: Handle
) -> McpStdioTransport:
    stdio = _handle(native, "codex_agent_mcp_transport_stdio", context, transport)
    try:
        forwarded = tuple(
            _read_environment_variable(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_mcp_transport_stdio_forwarded_environment_at",
                    context,
                    stdio,
                    index,
                ),
            )
            for index in range(
                _size(
                    native,
                    "codex_agent_mcp_transport_stdio_forwarded_environment_count",
                    context,
                    stdio,
                )
            )
        )
        return McpStdioTransport(
            native.copy_string(
                "codex_agent_mcp_transport_stdio_command_copy", context, stdio
            ),
            _string_list(
                native,
                context,
                stdio,
                "codex_agent_mcp_transport_stdio_arguments_count",
                "codex_agent_mcp_transport_stdio_argument_copy_at",
            ),
            _optional_string(
                native,
                context,
                stdio,
                "codex_agent_mcp_transport_stdio_has_working_directory",
                "codex_agent_mcp_transport_stdio_working_directory_copy",
            ),
            _optional_string_map(
                native,
                context,
                stdio,
                "codex_agent_mcp_transport_stdio_has_environment",
                "codex_agent_mcp_transport_stdio_environment_count",
                "codex_agent_mcp_transport_stdio_environment_key_copy_at",
                "codex_agent_mcp_transport_stdio_environment_value_copy_at",
            ),
            forwarded,
        )
    finally:
        _destroy(native, context, "codex_agent_mcp_transport_stdio_destroy", stdio)


def _read_transport(
    native: NativeLibrary, context: Handle, transport: Handle
) -> McpTransport:
    try:
        kind = _i32(native, "codex_agent_mcp_transport_kind", context, transport)
        if kind == 0:
            return _read_http(native, context, transport)
        if kind == 1:
            return _read_stdio(native, context, transport)
        raise RuntimeError(f"unknown MCP transport kind {kind}")
    finally:
        _destroy(native, context, "codex_agent_mcp_transport_destroy", transport)


def _read_configuration(
    native: NativeLibrary, context: Handle, configuration: Handle
) -> McpServerConfiguration:
    try:
        transport = _read_transport(
            native,
            context,
            _handle(
                native,
                "codex_agent_mcp_server_configuration_transport",
                context,
                configuration,
            ),
        )
        authentication = _optional_scalar(
            native,
            "codex_agent_mcp_server_configuration_authentication",
            ctypes.c_int32,
            context,
            configuration,
        )
        omit_tools_from: tuple[McpToolExposureSurface, ...] | None = None
        if _i32(
            native,
            "codex_agent_mcp_server_configuration_has_omit_tools_from",
            context,
            configuration,
        ):
            omit_tools_from = tuple(
                McpToolExposureSurface(
                    _read_indexed_i32(
                        native,
                        "codex_agent_mcp_server_configuration_omit_tools_from_at",
                        context,
                        configuration,
                        index,
                    )
                )
                for index in range(
                    _size(
                        native,
                        "codex_agent_mcp_server_configuration_omit_tools_from_count",
                        context,
                        configuration,
                    )
                )
            )
        default_approval = _optional_scalar(
            native,
            "codex_agent_mcp_server_configuration_default_tool_approval",
            ctypes.c_int32,
            context,
            configuration,
        )
        oauth = None
        if _i32(
            native,
            "codex_agent_mcp_server_configuration_has_oauth",
            context,
            configuration,
        ):
            oauth = _read_oauth(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_mcp_server_configuration_oauth",
                    context,
                    configuration,
                ),
            )
        tools: dict[str, McpToolConfiguration] = {}
        for index in range(
            _size(
                native,
                "codex_agent_mcp_server_configuration_tools_count",
                context,
                configuration,
            )
        ):
            key = native.copy_string(
                "codex_agent_mcp_server_configuration_tools_key_copy_at",
                context,
                configuration,
                index,
            )
            if key in tools:
                raise RuntimeError(f"native MCP tools contain duplicate key {key!r}")
            tools[key] = _read_tool(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_mcp_server_configuration_tools_value_at",
                    context,
                    configuration,
                    index,
                ),
            )
        return McpServerConfiguration(
            native.copy_string(
                "codex_agent_mcp_server_configuration_name_copy", context, configuration
            ),
            transport,
            None if authentication is None else McpAuthentication(authentication),
            native.copy_string(
                "codex_agent_mcp_server_configuration_environment_id_copy",
                context,
                configuration,
            ),
            bool(
                _i32(
                    native,
                    "codex_agent_mcp_server_configuration_is_enabled",
                    context,
                    configuration,
                )
            ),
            bool(
                _i32(
                    native,
                    "codex_agent_mcp_server_configuration_is_required",
                    context,
                    configuration,
                )
            ),
            bool(
                _i32(
                    native,
                    "codex_agent_mcp_server_configuration_supports_parallel_tool_calls",
                    context,
                    configuration,
                )
            ),
            omit_tools_from,
            _optional_scalar(
                native,
                "codex_agent_mcp_server_configuration_startup_timeout_seconds",
                ctypes.c_double,
                context,
                configuration,
            ),
            _optional_scalar(
                native,
                "codex_agent_mcp_server_configuration_tool_timeout_seconds",
                ctypes.c_double,
                context,
                configuration,
            ),
            None if default_approval is None else McpToolApproval(default_approval),
            _optional_string_list(
                native,
                context,
                configuration,
                "codex_agent_mcp_server_configuration_has_enabled_tools",
                "codex_agent_mcp_server_configuration_enabled_tools_count",
                "codex_agent_mcp_server_configuration_enabled_tool_copy_at",
            ),
            _optional_string_list(
                native,
                context,
                configuration,
                "codex_agent_mcp_server_configuration_has_disabled_tools",
                "codex_agent_mcp_server_configuration_disabled_tools_count",
                "codex_agent_mcp_server_configuration_disabled_tool_copy_at",
            ),
            _optional_string_list(
                native,
                context,
                configuration,
                "codex_agent_mcp_server_configuration_has_scopes",
                "codex_agent_mcp_server_configuration_scopes_count",
                "codex_agent_mcp_server_configuration_scope_copy_at",
            ),
            oauth,
            _optional_string(
                native,
                context,
                configuration,
                "codex_agent_mcp_server_configuration_has_oauth_resource",
                "codex_agent_mcp_server_configuration_oauth_resource_copy",
            ),
            tools,
        )
    finally:
        _destroy(
            native,
            context,
            "codex_agent_mcp_server_configuration_destroy",
            configuration,
        )


def _read_indexed_i32(
    native: NativeLibrary, name: str, *prefix: object
) -> int:
    result = ctypes.c_int32()
    native.call(name, *prefix, ctypes.byref(result))
    return result.value


def read_owned_mcp_server(
    native: NativeLibrary, context: Handle, server: Handle
) -> McpServer:
    """Projects and destroys one C-ABI-owned immutable MCP server graph."""

    try:
        configuration = None
        if _i32(
            native, "codex_agent_mcp_server_has_configuration", context, server
        ):
            configuration = _read_configuration(
                native,
                context,
                _handle(
                    native,
                    "codex_agent_mcp_server_configuration",
                    context,
                    server,
                ),
            )
        result = McpServer(
            native.copy_string("codex_agent_mcp_server_name_copy", context, server),
            native.copy_string(
                "codex_agent_mcp_server_display_name_copy", context, server
            ),
            McpAuthStatus(
                _i32(native, "codex_agent_mcp_server_auth_status", context, server)
            ),
            configuration,
            ResourceOrigin(
                _i32(native, "codex_agent_mcp_server_origin", context, server)
            ),
            bool(_i32(native, "codex_agent_mcp_server_can_remove", context, server)),
        )
        if result.is_authorized != bool(
            _i32(native, "codex_agent_mcp_server_is_authorized", context, server)
        ):
            raise RuntimeError("native MCP authorization projection is inconsistent")
        return result
    finally:
        _destroy(native, context, "codex_agent_mcp_server_destroy", server)
