namespace CodexAgent.Interop;

internal static unsafe class NativeMcpValues
{
    internal static CodexMcpServer ReadOwnedServer(NativeContext context, ref nint server)
    {
        try
        {
            return ReadServer(context, server);
        }
        finally
        {
            if (server != 0) NativeApi.ThrowIfFailed(NativeMethods.McpServerDestroy(context.Pointer, ref server), "destroy MCP server value");
        }
    }

    private static CodexMcpServer ReadServer(NativeContext context, nint server)
    {
        var name = CopyString(context, server, NativeMethods.McpServerNameCopy);
        var displayName = CopyString(context, server, NativeMethods.McpServerDisplayNameCopy);
        NativeApi.ThrowIfFailed(NativeMethods.McpServerAuthStatus(context.Pointer, server, out var authStatus), "read MCP server auth status");
        NativeApi.ThrowIfFailed(NativeMethods.McpServerHasConfiguration(context.Pointer, server, out var hasConfiguration), "read MCP server configuration presence");
        CodexMcpServerConfiguration? configuration = null;
        if (hasConfiguration != 0)
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfiguration(context.Pointer, server, out var owned), "read MCP server configuration");
            configuration = ReadOwnedConfiguration(context, ref owned);
        }
        NativeApi.ThrowIfFailed(NativeMethods.McpServerOrigin(context.Pointer, server, out var origin), "read MCP server origin");
        NativeApi.ThrowIfFailed(NativeMethods.McpServerCanRemove(context.Pointer, server, out var canRemove), "read MCP server removal capability");
        NativeApi.ThrowIfFailed(NativeMethods.McpServerIsAuthorized(context.Pointer, server, out var isAuthorized), "read MCP server authorization");
        var result = new CodexMcpServer(name, displayName, authStatus, configuration, origin, canRemove != 0);
        if (result.IsAuthorized != (isAuthorized != 0))
            throw new CodexException(CodexStatus.InternalError, "Native MCP server authorization projection is inconsistent.");
        return result;
    }

    private static CodexMcpServerConfiguration ReadOwnedConfiguration(NativeContext context, ref nint configuration)
    {
        try
        {
            var name = CopyString(context, configuration, NativeMethods.McpServerConfigurationNameCopy);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationTransport(context.Pointer, configuration, out var transportHandle), "read MCP transport");
            var transport = ReadOwnedTransport(context, ref transportHandle);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationAuthentication(context.Pointer, configuration, out var hasAuthentication, out var authenticationValue), "read MCP authentication");
            var environmentId = CopyString(context, configuration, NativeMethods.McpServerConfigurationEnvironmentIdCopy);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationIsEnabled(context.Pointer, configuration, out var isEnabled), "read MCP enabled state");
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationIsRequired(context.Pointer, configuration, out var isRequired), "read MCP required state");
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationSupportsParallelToolCalls(context.Pointer, configuration, out var supportsParallel), "read MCP parallel-call support");
            var omitToolsFrom = ReadOptionalList(
                context, configuration,
                NativeMethods.McpServerConfigurationHasOmitToolsFrom,
                NativeMethods.McpServerConfigurationOmitToolsFromCount,
                (nint c, nint value, nuint index, out CodexMcpToolExposureSurface item) => NativeMethods.McpServerConfigurationOmitToolsFromAt(c, value, index, out item));
            var startupTimeout = ReadOptionalDouble(context, configuration, NativeMethods.McpServerConfigurationStartupTimeoutSeconds);
            var toolTimeout = ReadOptionalDouble(context, configuration, NativeMethods.McpServerConfigurationToolTimeoutSeconds);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationDefaultToolApproval(context.Pointer, configuration, out var hasDefaultApproval, out var defaultApprovalValue), "read MCP default tool approval");
            var enabledTools = ReadOptionalStringList(context, configuration, NativeMethods.McpServerConfigurationHasEnabledTools, NativeMethods.McpServerConfigurationEnabledToolsCount, NativeMethods.McpServerConfigurationEnabledToolCopyAt);
            var disabledTools = ReadOptionalStringList(context, configuration, NativeMethods.McpServerConfigurationHasDisabledTools, NativeMethods.McpServerConfigurationDisabledToolsCount, NativeMethods.McpServerConfigurationDisabledToolCopyAt);
            var scopes = ReadOptionalStringList(context, configuration, NativeMethods.McpServerConfigurationHasScopes, NativeMethods.McpServerConfigurationScopesCount, NativeMethods.McpServerConfigurationScopeCopyAt);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationHasOauth(context.Pointer, configuration, out var hasOauth), "read MCP OAuth presence");
            CodexMcpOauthConfiguration? oauth = null;
            if (hasOauth != 0)
            {
                NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationOauth(context.Pointer, configuration, out var ownedOauth), "read MCP OAuth configuration");
                oauth = ReadOwnedOauth(context, ref ownedOauth);
            }
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationHasOauthResource(context.Pointer, configuration, out var hasOauthResource), "read MCP OAuth resource presence");
            var oauthResource = hasOauthResource == 0 ? null : CopyString(context, configuration, NativeMethods.McpServerConfigurationOauthResourceCopy);
            var tools = ReadTools(context, configuration);
            return new CodexMcpServerConfiguration(
                name,
                transport,
                hasAuthentication == 0 ? null : authenticationValue,
                environmentId,
                isEnabled != 0,
                isRequired != 0,
                supportsParallel != 0,
                omitToolsFrom,
                startupTimeout,
                toolTimeout,
                hasDefaultApproval == 0 ? null : defaultApprovalValue,
                enabledTools,
                disabledTools,
                scopes,
                oauth,
                oauthResource,
                tools);
        }
        finally
        {
            if (configuration != 0) NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationDestroy(context.Pointer, ref configuration), "destroy MCP server configuration value");
        }
    }

    private static CodexMcpTransport ReadOwnedTransport(NativeContext context, ref nint transport)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpTransportKind(context.Pointer, transport, out var kind), "read MCP transport kind");
            return kind switch
            {
                NativeMcpTransportKind.Http => ReadHttp(context, transport),
                NativeMcpTransportKind.Stdio => ReadStdio(context, transport),
                _ => throw new CodexException(CodexStatus.InternalError, $"Unknown MCP transport kind {(int)kind}."),
            };
        }
        finally
        {
            if (transport != 0) NativeApi.ThrowIfFailed(NativeMethods.McpTransportDestroy(context.Pointer, ref transport), "destroy MCP transport value");
        }
    }

    private static CodexMcpTransport.Http ReadHttp(NativeContext context, nint transport)
    {
        NativeApi.ThrowIfFailed(NativeMethods.McpTransportHttp(context.Pointer, transport, out var http), "read HTTP MCP transport");
        try
        {
            var url = CopyString(context, http, NativeMethods.McpTransportHttpUrlCopy);
            var bearer = ReadOptionalString(context, http, NativeMethods.McpTransportHttpHasBearerTokenEnvironmentVariable, NativeMethods.McpTransportHttpBearerTokenEnvironmentVariableCopy);
            var headers = ReadOptionalStringMap(context, http, NativeMethods.McpTransportHttpHasHeaders, NativeMethods.McpTransportHttpHeadersCount, NativeMethods.McpTransportHttpHeadersKeyCopyAt, NativeMethods.McpTransportHttpHeadersValueCopyAt);
            var environmentHeaders = ReadOptionalStringMap(context, http, NativeMethods.McpTransportHttpHasEnvironmentHeaders, NativeMethods.McpTransportHttpEnvironmentHeadersCount, NativeMethods.McpTransportHttpEnvironmentHeadersKeyCopyAt, NativeMethods.McpTransportHttpEnvironmentHeadersValueCopyAt);
            var helper = ReadOptionalString(context, http, NativeMethods.McpTransportHttpHasHeadersHelper, NativeMethods.McpTransportHttpHeadersHelperCopy);
            return new CodexMcpTransport.Http(url, bearer, headers, environmentHeaders, helper);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpTransportHttpDestroy(context.Pointer, ref http), "destroy HTTP MCP transport value");
        }
    }

    private static CodexMcpTransport.Stdio ReadStdio(NativeContext context, nint transport)
    {
        NativeApi.ThrowIfFailed(NativeMethods.McpTransportStdio(context.Pointer, transport, out var stdio), "read stdio MCP transport");
        try
        {
            var command = CopyString(context, stdio, NativeMethods.McpTransportStdioCommandCopy);
            var arguments = ReadStringList(context, stdio, NativeMethods.McpTransportStdioArgumentsCount, NativeMethods.McpTransportStdioArgumentCopyAt);
            var workingDirectory = ReadOptionalString(context, stdio, NativeMethods.McpTransportStdioHasWorkingDirectory, NativeMethods.McpTransportStdioWorkingDirectoryCopy);
            var environment = ReadOptionalStringMap(context, stdio, NativeMethods.McpTransportStdioHasEnvironment, NativeMethods.McpTransportStdioEnvironmentCount, NativeMethods.McpTransportStdioEnvironmentKeyCopyAt, NativeMethods.McpTransportStdioEnvironmentValueCopyAt);
            NativeApi.ThrowIfFailed(NativeMethods.McpTransportStdioForwardedEnvironmentCount(context.Pointer, stdio, out var count), "read forwarded MCP environment count");
            var forwarded = new CodexMcpEnvironmentVariable[CheckedCount(count)];
            for (var index = 0; index < forwarded.Length; index += 1)
            {
                NativeApi.ThrowIfFailed(NativeMethods.McpTransportStdioForwardedEnvironmentAt(context.Pointer, stdio, (nuint)index, out var variable), "read forwarded MCP environment variable");
                forwarded[index] = ReadOwnedEnvironmentVariable(context, ref variable);
            }
            return new CodexMcpTransport.Stdio(command, arguments, workingDirectory, environment, forwarded);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpTransportStdioDestroy(context.Pointer, ref stdio), "destroy stdio MCP transport value");
        }
    }

    private static CodexMcpEnvironmentVariable ReadOwnedEnvironmentVariable(NativeContext context, ref nint variable)
    {
        try
        {
            var name = CopyString(context, variable, NativeMethods.McpEnvironmentVariableNameCopy);
            NativeApi.ThrowIfFailed(NativeMethods.McpEnvironmentVariableSource(context.Pointer, variable, out var hasSource, out var source), "read MCP environment source");
            return new CodexMcpEnvironmentVariable(name, hasSource == 0 ? null : source);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpEnvironmentVariableDestroy(context.Pointer, ref variable), "destroy MCP environment-variable value");
        }
    }

    private static CodexMcpOauthConfiguration ReadOwnedOauth(NativeContext context, ref nint oauth)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpOauthConfigurationHasClientId(context.Pointer, oauth, out var hasClientId), "read MCP OAuth client presence");
            var clientId = hasClientId == 0 ? null : CopyString(context, oauth, NativeMethods.McpOauthConfigurationClientIdCopy);
            NativeApi.ThrowIfFailed(NativeMethods.McpOauthConfigurationCallbackPort(context.Pointer, oauth, out var hasPort, out var port), "read MCP OAuth callback port");
            return new CodexMcpOauthConfiguration(clientId, hasPort == 0 ? null : port);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpOauthConfigurationDestroy(context.Pointer, ref oauth), "destroy MCP OAuth value");
        }
    }

    private static CodexMcpToolConfiguration ReadOwnedToolConfiguration(NativeContext context, ref nint configuration)
    {
        try
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpToolConfigurationApproval(context.Pointer, configuration, out var hasApproval, out var approval), "read MCP tool approval");
            return new CodexMcpToolConfiguration(hasApproval == 0 ? null : approval);
        }
        finally
        {
            NativeApi.ThrowIfFailed(NativeMethods.McpToolConfigurationDestroy(context.Pointer, ref configuration), "destroy MCP tool configuration value");
        }
    }

    private static IReadOnlyDictionary<string, CodexMcpToolConfiguration> ReadTools(NativeContext context, nint configuration)
    {
        NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationToolsCount(context.Pointer, configuration, out var count), "read MCP tools count");
        var result = new Dictionary<string, CodexMcpToolConfiguration>(CheckedCount(count), StringComparer.Ordinal);
        for (var index = 0; index < (int)count; index += 1)
        {
            var key = CopyStringAt(context, configuration, (nuint)index, NativeMethods.McpServerConfigurationToolsKeyCopyAt);
            NativeApi.ThrowIfFailed(NativeMethods.McpServerConfigurationToolsValueAt(context.Pointer, configuration, (nuint)index, out var tool), "read MCP tool configuration");
            if (!result.TryAdd(key, ReadOwnedToolConfiguration(context, ref tool)))
                throw new CodexException(CodexStatus.InternalError, $"Native MCP tools contain duplicate key '{key}'.");
        }
        return result;
    }

    private delegate CodexStatus Presence(nint context, nint value, out int hasValue);
    private delegate CodexStatus Count(nint context, nint value, out nuint count);
    private delegate CodexStatus Copy(nint context, nint value, byte* buffer, nuint capacity, out nuint required);
    private delegate CodexStatus CopyAt(nint context, nint value, nuint index, byte* buffer, nuint capacity, out nuint required);
    private delegate CodexStatus ReadAt<T>(nint context, nint value, nuint index, out T item);
    private delegate CodexStatus OptionalDouble(nint context, nint value, out int hasValue, out double item);

    private static string CopyString(NativeContext context, nint value, Copy copy) =>
        NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) => copy(context.Pointer, value, buffer, capacity, out required));

    private static string CopyStringAt(NativeContext context, nint value, nuint index, CopyAt copy) =>
        NativeApi.CopyString((byte* buffer, nuint capacity, out nuint required) => copy(context.Pointer, value, index, buffer, capacity, out required));

    private static string? ReadOptionalString(NativeContext context, nint value, Presence presence, Copy copy)
    {
        NativeApi.ThrowIfFailed(presence(context.Pointer, value, out var hasValue), "read optional string presence");
        return hasValue == 0 ? null : CopyString(context, value, copy);
    }

    private static double? ReadOptionalDouble(NativeContext context, nint value, OptionalDouble read)
    {
        NativeApi.ThrowIfFailed(read(context.Pointer, value, out var hasValue, out var result), "read optional number");
        return hasValue == 0 ? null : result;
    }

    private static IReadOnlyList<string> ReadStringList(NativeContext context, nint value, Count count, CopyAt copy)
    {
        NativeApi.ThrowIfFailed(count(context.Pointer, value, out var nativeCount), "read string-list count");
        var result = new string[CheckedCount(nativeCount)];
        for (var index = 0; index < result.Length; index += 1) result[index] = CopyStringAt(context, value, (nuint)index, copy);
        return result;
    }

    private static IReadOnlyList<string>? ReadOptionalStringList(NativeContext context, nint value, Presence presence, Count count, CopyAt copy)
    {
        NativeApi.ThrowIfFailed(presence(context.Pointer, value, out var hasValue), "read optional string-list presence");
        return hasValue == 0 ? null : ReadStringList(context, value, count, copy);
    }

    private static IReadOnlyDictionary<string, string>? ReadOptionalStringMap(NativeContext context, nint value, Presence presence, Count count, CopyAt keyCopy, CopyAt valueCopy)
    {
        NativeApi.ThrowIfFailed(presence(context.Pointer, value, out var hasValue), "read optional string-map presence");
        if (hasValue == 0) return null;
        NativeApi.ThrowIfFailed(count(context.Pointer, value, out var nativeCount), "read string-map count");
        var result = new Dictionary<string, string>(CheckedCount(nativeCount), StringComparer.Ordinal);
        for (var index = 0; index < (int)nativeCount; index += 1)
        {
            var key = CopyStringAt(context, value, (nuint)index, keyCopy);
            if (!result.TryAdd(key, CopyStringAt(context, value, (nuint)index, valueCopy)))
                throw new CodexException(CodexStatus.InternalError, $"Native string map contains duplicate key '{key}'.");
        }
        return result;
    }

    private static IReadOnlyList<T>? ReadOptionalList<T>(NativeContext context, nint value, Presence presence, Count count, ReadAt<T> read)
    {
        NativeApi.ThrowIfFailed(presence(context.Pointer, value, out var hasValue), "read optional list presence");
        if (hasValue == 0) return null;
        NativeApi.ThrowIfFailed(count(context.Pointer, value, out var nativeCount), "read list count");
        var result = new T[CheckedCount(nativeCount)];
        for (var index = 0; index < result.Length; index += 1)
            NativeApi.ThrowIfFailed(read(context.Pointer, value, (nuint)index, out result[index]), "read list item");
        return result;
    }

    private static int CheckedCount(nuint count)
    {
        if (count > int.MaxValue) throw new CodexException(CodexStatus.OutOfMemory, "Native collection is too large.");
        return (int)count;
    }
}
