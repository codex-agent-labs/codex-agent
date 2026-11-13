using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace CodexAgent.Interop;

internal enum NativeMcpTransportKind
{
    Http = 0,
    Stdio = 1,
}

internal static unsafe partial class NativeMethods
{
    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_environment_variable_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpEnvironmentVariableDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_environment_variable_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpEnvironmentVariableNameCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_environment_variable_source")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpEnvironmentVariableSource(nint context, nint value, out int hasValue, out CodexMcpEnvironmentSource source);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_oauth_configuration_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpOauthConfigurationDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_oauth_configuration_has_client_id")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpOauthConfigurationHasClientId(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_oauth_configuration_client_id_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpOauthConfigurationClientIdCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_oauth_configuration_callback_port")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpOauthConfigurationCallbackPort(nint context, nint value, out int hasValue, out int port);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_tool_configuration_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpToolConfigurationDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_tool_configuration_approval")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpToolConfigurationApproval(nint context, nint value, out int hasValue, out CodexMcpToolApproval approval);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_kind")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportKind(nint context, nint value, out NativeMcpTransportKind kind);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttp(nint context, nint value, out nint http);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdio(nint context, nint value, out nint stdio);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_url_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpUrlCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_has_bearer_token_environment_variable")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHasBearerTokenEnvironmentVariable(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_bearer_token_environment_variable_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpBearerTokenEnvironmentVariableCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_has_headers")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHasHeaders(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_headers_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHeadersCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_headers_key_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHeadersKeyCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_headers_value_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHeadersValueCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_has_environment_headers")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHasEnvironmentHeaders(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_environment_headers_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpEnvironmentHeadersCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_environment_headers_key_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpEnvironmentHeadersKeyCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_environment_headers_value_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpEnvironmentHeadersValueCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_has_headers_helper")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHasHeadersHelper(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_http_headers_helper_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportHttpHeadersHelperCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_command_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioCommandCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_arguments_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioArgumentsCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_argument_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioArgumentCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_has_working_directory")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioHasWorkingDirectory(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_working_directory_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioWorkingDirectoryCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_has_environment")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioHasEnvironment(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_environment_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioEnvironmentCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_environment_key_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioEnvironmentKeyCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_environment_value_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioEnvironmentValueCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_forwarded_environment_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioForwardedEnvironmentCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_transport_stdio_forwarded_environment_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpTransportStdioForwardedEnvironmentAt(nint context, nint value, nuint index, out nint variable);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationNameCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_transport")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationTransport(nint context, nint value, out nint transport);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_authentication")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationAuthentication(nint context, nint value, out int hasValue, out CodexMcpAuthentication authentication);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_environment_id_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationEnvironmentIdCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_is_enabled")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationIsEnabled(nint context, nint value, out int result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_is_required")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationIsRequired(nint context, nint value, out int result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_supports_parallel_tool_calls")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationSupportsParallelToolCalls(nint context, nint value, out int result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_omit_tools_from")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasOmitToolsFrom(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_omit_tools_from_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationOmitToolsFromCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_omit_tools_from_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationOmitToolsFromAt(nint context, nint value, nuint index, out CodexMcpToolExposureSurface surface);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_startup_timeout_seconds")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationStartupTimeoutSeconds(nint context, nint value, out int hasValue, out double result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_tool_timeout_seconds")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationToolTimeoutSeconds(nint context, nint value, out int hasValue, out double result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_default_tool_approval")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationDefaultToolApproval(nint context, nint value, out int hasValue, out CodexMcpToolApproval result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_enabled_tools")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasEnabledTools(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_enabled_tools_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationEnabledToolsCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_enabled_tool_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationEnabledToolCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_disabled_tools")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasDisabledTools(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_disabled_tools_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationDisabledToolsCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_disabled_tool_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationDisabledToolCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_scopes")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasScopes(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_scopes_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationScopesCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_scope_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationScopeCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_oauth")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasOauth(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_oauth")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationOauth(nint context, nint value, out nint oauth);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_has_oauth_resource")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationHasOauthResource(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_oauth_resource_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationOauthResourceCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_tools_count")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationToolsCount(nint context, nint value, out nuint count);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_tools_key_copy_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationToolsKeyCopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration_tools_value_at")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfigurationToolsValueAt(nint context, nint value, nuint index, out nint configuration);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_destroy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerDestroy(nint context, ref nint value);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerNameCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_display_name_copy")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerDisplayNameCopy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_auth_status")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerAuthStatus(nint context, nint value, out CodexMcpAuthStatus status);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_has_configuration")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerHasConfiguration(nint context, nint value, out int hasValue);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_configuration")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerConfiguration(nint context, nint value, out nint configuration);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_origin")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerOrigin(nint context, nint value, out CodexResourceOrigin origin);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_can_remove")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerCanRemove(nint context, nint value, out int result);

    [LibraryImport(LibraryName, EntryPoint = "codex_agent_mcp_server_is_authorized")]
    [UnmanagedCallConv(CallConvs = [typeof(CallConvCdecl)])]
    internal static partial CodexStatus McpServerIsAuthorized(nint context, nint value, out int result);
}
