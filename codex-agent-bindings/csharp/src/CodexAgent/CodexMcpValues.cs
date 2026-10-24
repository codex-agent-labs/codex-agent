using System.Collections.ObjectModel;

namespace CodexAgent;

/// <summary>An environment variable forwarded to an MCP server.</summary>
public sealed record CodexMcpEnvironmentVariable
{
    /// <summary>Creates an MCP environment-variable reference.</summary>
    public CodexMcpEnvironmentVariable(string name, CodexMcpEnvironmentSource? source = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (source is not null && !Enum.IsDefined(source.Value)) throw new ArgumentOutOfRangeException(nameof(source));
        Name = name;
        Source = source;
    }

    /// <summary>The variable name.</summary>
    public string Name { get; }

    /// <summary>The optional environment source.</summary>
    public CodexMcpEnvironmentSource? Source { get; }
}

/// <summary>Optional OAuth settings for an MCP server.</summary>
public sealed record CodexMcpOauthConfiguration
{
    /// <summary>Creates OAuth settings.</summary>
    public CodexMcpOauthConfiguration(string? clientId = null, int? callbackPort = null)
    {
        if (callbackPort is < 1 or > 65535) throw new ArgumentOutOfRangeException(nameof(callbackPort));
        ClientId = clientId;
        CallbackPort = callbackPort;
    }

    /// <summary>The optional OAuth client identifier.</summary>
    public string? ClientId { get; }

    /// <summary>The optional loopback callback port.</summary>
    public int? CallbackPort { get; }
}

/// <summary>Per-tool MCP approval settings.</summary>
public sealed record CodexMcpToolConfiguration
{
    /// <summary>Creates per-tool approval settings.</summary>
    public CodexMcpToolConfiguration(CodexMcpToolApproval? approval = null)
    {
        if (approval is not null && !Enum.IsDefined(approval.Value)) throw new ArgumentOutOfRangeException(nameof(approval));
        Approval = approval;
    }

    /// <summary>The optional approval policy.</summary>
    public CodexMcpToolApproval? Approval { get; }
}

/// <summary>The local transport used by an MCP server.</summary>
public abstract record CodexMcpTransport
{
    private CodexMcpTransport() { }

    /// <summary>An HTTP MCP transport.</summary>
    public sealed record Http : CodexMcpTransport
    {
        /// <summary>Creates an HTTP MCP transport.</summary>
        public Http(
            string url,
            string? bearerTokenEnvironmentVariable = null,
            IReadOnlyDictionary<string, string>? headers = null,
            IReadOnlyDictionary<string, string>? environmentHeaders = null,
            string? headersHelper = null)
        {
            if (!IsSafeHttpUrl(url)) throw new ArgumentException("MCP HTTP URL must use HTTPS or a loopback HTTP address.", nameof(url));
            if (bearerTokenEnvironmentVariable is not null && string.IsNullOrWhiteSpace(bearerTokenEnvironmentVariable))
                throw new ArgumentException("MCP bearer-token environment variable must not be blank.", nameof(bearerTokenEnvironmentVariable));
            if (headersHelper is not null && string.IsNullOrWhiteSpace(headersHelper))
                throw new ArgumentException("MCP headers helper must not be blank.", nameof(headersHelper));
            Url = url;
            BearerTokenEnvironmentVariable = bearerTokenEnvironmentVariable;
            Headers = CopyMap(headers);
            EnvironmentHeaders = CopyMap(environmentHeaders);
            HeadersHelper = headersHelper;
        }

        /// <summary>The HTTP endpoint.</summary>
        public string Url { get; }

        /// <summary>The optional bearer-token environment variable.</summary>
        public string? BearerTokenEnvironmentVariable { get; }

        /// <summary>Literal request headers, preserving null versus empty.</summary>
        public IReadOnlyDictionary<string, string>? Headers { get; }

        /// <summary>Environment-backed request headers, preserving null versus empty.</summary>
        public IReadOnlyDictionary<string, string>? EnvironmentHeaders { get; }

        /// <summary>The optional local headers helper.</summary>
        public string? HeadersHelper { get; }
    }

    /// <summary>A subprocess MCP transport.</summary>
    public sealed record Stdio : CodexMcpTransport
    {
        /// <summary>Creates a subprocess MCP transport.</summary>
        public Stdio(
            string command,
            IReadOnlyList<string>? arguments = null,
            string? workingDirectory = null,
            IReadOnlyDictionary<string, string>? environment = null,
            IReadOnlyList<CodexMcpEnvironmentVariable>? forwardedEnvironment = null)
        {
            ArgumentException.ThrowIfNullOrWhiteSpace(command);
            Command = command;
            Arguments = CopyList(arguments);
            WorkingDirectory = workingDirectory;
            Environment = CopyMap(environment);
            ForwardedEnvironment = CopyList(forwardedEnvironment);
        }

        /// <summary>The executable or command.</summary>
        public string Command { get; }

        /// <summary>Ordered command arguments.</summary>
        public IReadOnlyList<string> Arguments { get; }

        /// <summary>The optional working directory.</summary>
        public string? WorkingDirectory { get; }

        /// <summary>The optional explicit environment, preserving null versus empty.</summary>
        public IReadOnlyDictionary<string, string>? Environment { get; }

        /// <summary>Ordered environment variables forwarded from the host.</summary>
        public IReadOnlyList<CodexMcpEnvironmentVariable> ForwardedEnvironment { get; }
    }

    private static bool IsSafeHttpUrl(string value)
    {
        if (string.IsNullOrEmpty(value) || value.Any(static character => char.IsWhiteSpace(character) || char.IsControl(character))) return false;
        var scheme = value.StartsWith("https://", StringComparison.Ordinal) ? "https" :
            value.StartsWith("http://", StringComparison.Ordinal) ? "http" : null;
        if (scheme is null) return false;
        var authorityStart = scheme.Length + 3;
        var authorityEnd = value.IndexOfAny(['/', '?', '#'], authorityStart);
        if (authorityEnd < 0) authorityEnd = value.Length;
        var authority = value[authorityStart..authorityEnd];
        if (authority.Length == 0 || authority.Contains('@')) return false;

        string host;
        if (authority[0] == '[')
        {
            var closingBracket = authority.IndexOf(']');
            if (closingBracket <= 1 || !ValidPortAfter(authority, closingBracket + 1)) return false;
            host = authority[1..closingBracket];
            if (!host.Contains(':') || !host.Any(Uri.IsHexDigit) ||
                host.Any(character => !Uri.IsHexDigit(character) && character is not ':' and not '.')) return false;
        }
        else
        {
            if (authority.Count(character => character == ':') > 1) return false;
            var separator = authority.IndexOf(':');
            if (separator >= 0 && !ValidPortAfter(authority, separator)) return false;
            host = separator < 0 ? authority : authority[..separator];
            if (!ValidRegisteredHost(host)) return false;
        }
        return scheme == "https" || host.Equals("localhost", StringComparison.OrdinalIgnoreCase) || host == "127.0.0.1" || host == "::1";
    }

    private static bool ValidPortAfter(string authority, int separator)
    {
        if (separator == authority.Length) return true;
        if (authority[separator] != ':') return false;
        var port = authority[(separator + 1)..];
        return port.Length != 0 && port.All(char.IsAsciiDigit) && int.TryParse(port, out var value) && value is >= 1 and <= 65535;
    }

    private static bool ValidRegisteredHost(string host)
    {
        var hasName = false;
        for (var index = 0; index < host.Length; index += 1)
        {
            var character = host[index];
            if (char.IsAsciiLetterOrDigit(character))
            {
                hasName = true;
            }
            else if (character == '%')
            {
                if (index + 2 >= host.Length || !Uri.IsHexDigit(host[index + 1]) || !Uri.IsHexDigit(host[index + 2])) return false;
                hasName = true;
                index += 2;
            }
            else if (!"-._~!$&'()*+,;=".Contains(character))
            {
                return false;
            }
        }
        return hasName;
    }

    internal static IReadOnlyList<T> CopyList<T>(IReadOnlyList<T>? values) =>
        Array.AsReadOnly(values?.ToArray() ?? []);

    internal static IReadOnlyDictionary<string, T>? CopyMap<T>(IReadOnlyDictionary<string, T>? values) =>
        values is null ? null : new ReadOnlyDictionary<string, T>(new Dictionary<string, T>(values, StringComparer.Ordinal));
}

/// <summary>The full immutable configuration of an MCP server.</summary>
public sealed record CodexMcpServerConfiguration
{
    /// <summary>Creates MCP server configuration.</summary>
    public CodexMcpServerConfiguration(
        string name,
        CodexMcpTransport transport,
        CodexMcpAuthentication? authentication = null,
        string environmentId = "local",
        bool isEnabled = true,
        bool isRequired = false,
        bool supportsParallelToolCalls = false,
        IReadOnlyList<CodexMcpToolExposureSurface>? omitToolsFrom = null,
        double? startupTimeoutSeconds = null,
        double? toolTimeoutSeconds = null,
        CodexMcpToolApproval? defaultToolApproval = null,
        IReadOnlyList<string>? enabledTools = null,
        IReadOnlyList<string>? disabledTools = null,
        IReadOnlyList<string>? scopes = null,
        CodexMcpOauthConfiguration? oauth = null,
        string? oauthResource = null,
        IReadOnlyDictionary<string, CodexMcpToolConfiguration>? tools = null)
    {
        if (string.IsNullOrEmpty(name) || name.Any(static character => !char.IsAsciiLetterOrDigit(character) && character is not '-' and not '_'))
            throw new ArgumentException("MCP server name may contain only ASCII letters, numbers, '-', and '_'.", nameof(name));
        ArgumentNullException.ThrowIfNull(transport);
        if (authentication is not null && !Enum.IsDefined(authentication.Value)) throw new ArgumentOutOfRangeException(nameof(authentication));
        if (defaultToolApproval is not null && !Enum.IsDefined(defaultToolApproval.Value)) throw new ArgumentOutOfRangeException(nameof(defaultToolApproval));
        if (omitToolsFrom?.Any(static value => !Enum.IsDefined(value)) == true) throw new ArgumentOutOfRangeException(nameof(omitToolsFrom));
        ArgumentException.ThrowIfNullOrWhiteSpace(environmentId);
        ValidateTimeout(startupTimeoutSeconds, nameof(startupTimeoutSeconds));
        ValidateTimeout(toolTimeoutSeconds, nameof(toolTimeoutSeconds));
        if (transport is CodexMcpTransport.Stdio && (authentication is not null || oauth is not null || oauthResource is not null))
            throw new ArgumentException("MCP stdio servers do not support authentication or OAuth configuration.", nameof(transport));
        if (transport is CodexMcpTransport.Http { HeadersHelper: not null } && environmentId != "local")
            throw new ArgumentException("MCP HTTP headers helpers are only supported for local servers.", nameof(environmentId));

        Name = name;
        Transport = transport;
        Authentication = authentication;
        EnvironmentId = environmentId;
        IsEnabled = isEnabled;
        IsRequired = isRequired;
        SupportsParallelToolCalls = supportsParallelToolCalls;
        OmitToolsFrom = omitToolsFrom is null ? null : CodexMcpTransport.CopyList(omitToolsFrom);
        StartupTimeoutSeconds = startupTimeoutSeconds;
        ToolTimeoutSeconds = toolTimeoutSeconds;
        DefaultToolApproval = defaultToolApproval;
        EnabledTools = enabledTools is null ? null : CodexMcpTransport.CopyList(enabledTools);
        DisabledTools = disabledTools is null ? null : CodexMcpTransport.CopyList(disabledTools);
        Scopes = scopes is null ? null : CodexMcpTransport.CopyList(scopes);
        Oauth = oauth;
        OauthResource = oauthResource;
        Tools = CodexMcpTransport.CopyMap(tools) ?? new ReadOnlyDictionary<string, CodexMcpToolConfiguration>(new Dictionary<string, CodexMcpToolConfiguration>());
    }

    /// <summary>The stable server name.</summary>
    public string Name { get; }
    /// <summary>The transport configuration.</summary>
    public CodexMcpTransport Transport { get; }
    /// <summary>The optional authentication mechanism.</summary>
    public CodexMcpAuthentication? Authentication { get; }
    /// <summary>The execution environment identifier.</summary>
    public string EnvironmentId { get; }
    /// <summary>Whether this server is enabled.</summary>
    public bool IsEnabled { get; }
    /// <summary>Whether this server is required.</summary>
    public bool IsRequired { get; }
    /// <summary>Whether parallel tool calls are supported.</summary>
    public bool SupportsParallelToolCalls { get; }
    /// <summary>Optional surfaces from which tools are omitted.</summary>
    public IReadOnlyList<CodexMcpToolExposureSurface>? OmitToolsFrom { get; }
    /// <summary>The optional startup timeout in seconds.</summary>
    public double? StartupTimeoutSeconds { get; }
    /// <summary>The optional tool timeout in seconds.</summary>
    public double? ToolTimeoutSeconds { get; }
    /// <summary>The optional default approval policy.</summary>
    public CodexMcpToolApproval? DefaultToolApproval { get; }
    /// <summary>The optional allow-list of tools.</summary>
    public IReadOnlyList<string>? EnabledTools { get; }
    /// <summary>The optional deny-list of tools.</summary>
    public IReadOnlyList<string>? DisabledTools { get; }
    /// <summary>The optional OAuth scopes.</summary>
    public IReadOnlyList<string>? Scopes { get; }
    /// <summary>The optional OAuth client configuration.</summary>
    public CodexMcpOauthConfiguration? Oauth { get; }
    /// <summary>The optional OAuth resource.</summary>
    public string? OauthResource { get; }
    /// <summary>Per-tool configurations keyed by tool name.</summary>
    public IReadOnlyDictionary<string, CodexMcpToolConfiguration> Tools { get; }

    private static void ValidateTimeout(double? value, string parameterName)
    {
        if (value is not null && (!double.IsFinite(value.Value) || value <= 0.0 || value >= 1.8446744073709552E19))
            throw new ArgumentOutOfRangeException(parameterName);
    }
}

/// <summary>An installed or discoverable MCP server.</summary>
public sealed record CodexMcpServer
{
    /// <summary>Creates an MCP server value.</summary>
    public CodexMcpServer(
        string name,
        string displayName,
        CodexMcpAuthStatus authStatus,
        CodexMcpServerConfiguration? configuration = null,
        CodexResourceOrigin origin = CodexResourceOrigin.Unknown,
        bool canRemove = false)
    {
        ArgumentNullException.ThrowIfNull(name);
        ArgumentNullException.ThrowIfNull(displayName);
        if (!Enum.IsDefined(authStatus)) throw new ArgumentOutOfRangeException(nameof(authStatus));
        if (!Enum.IsDefined(origin)) throw new ArgumentOutOfRangeException(nameof(origin));
        Name = name;
        DisplayName = displayName;
        AuthStatus = authStatus;
        Configuration = configuration;
        Origin = origin;
        CanRemove = canRemove;
    }

    /// <summary>The stable server name.</summary>
    public string Name { get; }
    /// <summary>The display name.</summary>
    public string DisplayName { get; }
    /// <summary>The current authentication status.</summary>
    public CodexMcpAuthStatus AuthStatus { get; }
    /// <summary>The optional complete configuration.</summary>
    public CodexMcpServerConfiguration? Configuration { get; }
    /// <summary>The configuration origin.</summary>
    public CodexResourceOrigin Origin { get; }
    /// <summary>Whether the current user may remove the server.</summary>
    public bool CanRemove { get; }
    /// <summary>Whether the server has bearer-token or OAuth authorization.</summary>
    public bool IsAuthorized => AuthStatus is CodexMcpAuthStatus.BearerToken or CodexMcpAuthStatus.Oauth;
}
