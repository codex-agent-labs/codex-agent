using CodexAgent.Interop;

namespace CodexAgent;

/// <summary>Canonical metadata for enum values whose Kotlin properties project as .NET methods.</summary>
public static class CodexEnumMetadata
{
    /// <summary>Returns the display name of an approval preset.</summary>
    public static string ApprovalPresetDisplayName(CodexApprovalPreset value) => value switch
    {
        CodexApprovalPreset.Never => "Never",
        CodexApprovalPreset.AutoReview => "Auto review",
        CodexApprovalPreset.AskMe => "Ask me",
        CodexApprovalPreset.Strict => "Strict",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    /// <summary>Returns the stable identifier of a capability.</summary>
    public static string CapabilityId(CodexCapability value) => value switch
    {
        CodexCapability.WebSearch => "web_search",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    /// <summary>Returns the display label of a capability.</summary>
    public static string CapabilityDisplayLabel(CodexCapability value) => value switch
    {
        CodexCapability.WebSearch => "Web search",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    /// <summary>Returns the optional icon of a capability.</summary>
    public static string? CapabilityIcon(CodexCapability value) => value switch
    {
        CodexCapability.WebSearch => "🌐",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    /// <summary>Returns the prompt label of a capability.</summary>
    public static string CapabilityPromptLabel(CodexCapability value) => value switch
    {
        CodexCapability.WebSearch => "Use 🌐 Web search",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };

    /// <summary>Returns the display name of a skill scope.</summary>
    public static string SkillScopeDisplayName(CodexSkillScope value) => value switch
    {
        CodexSkillScope.System => "Built in",
        CodexSkillScope.User => "User",
        CodexSkillScope.Repo => "Workspace",
        CodexSkillScope.Plugin => "Plugin",
        CodexSkillScope.Admin => "Managed",
        _ => throw new ArgumentOutOfRangeException(nameof(value)),
    };
}

/// <summary>A validated authorization URL.</summary>
public sealed record CodexAuthorizationUrl
{
    private CodexAuthorizationUrl(string value, CodexAuthorizationPurpose purpose)
    {
        Value = value;
        Purpose = purpose;
    }

    /// <summary>The validated URL string.</summary>
    public string Value { get; }
    /// <summary>The authorization purpose.</summary>
    public CodexAuthorizationPurpose Purpose { get; }

    /// <summary>Creates a trusted ChatGPT authorization URL.</summary>
    public static CodexAuthorizationUrl ChatGpt(string value) => NativeValueBridge.AuthorizationUrl(value, true);
    /// <summary>Creates a safe external-service authorization URL.</summary>
    public static CodexAuthorizationUrl External(string value) => NativeValueBridge.AuthorizationUrl(value, false);

    internal static CodexAuthorizationUrl FromNative(string value, CodexAuthorizationPurpose purpose) =>
        new(value, purpose);

    /// <inheritdoc />
    public override string ToString() => $"CodexAuthorizationUrl(Purpose={Purpose})";

}

/// <summary>An authentication method.</summary>
public abstract record CodexAuthenticationMethod
{
    private CodexAuthenticationMethod() { }

    /// <summary>Authentication through a browser.</summary>
    public sealed record ChatGptBrowser : CodexAuthenticationMethod
    {
        private ChatGptBrowser() { }
        /// <summary>The single browser-authentication value.</summary>
        public static ChatGptBrowser Instance { get; } = new();
    }

    /// <summary>Authentication through a device code.</summary>
    public sealed record ChatGptDeviceCode : CodexAuthenticationMethod
    {
        private ChatGptDeviceCode() { }
        /// <summary>The single device-code value.</summary>
        public static ChatGptDeviceCode Instance { get; } = new();
    }

    /// <summary>API-key authentication.</summary>
    public sealed record ApiKey : CodexAuthenticationMethod
    {
        /// <summary>Creates API-key authentication.</summary>
        public ApiKey(string value)
        {
            ArgumentException.ThrowIfNullOrWhiteSpace(value);
            Value = value;
        }

        /// <summary>The secret API-key value.</summary>
        public string Value { get; }
        /// <inheritdoc />
        public override string ToString() => "ApiKey(**redacted**)";
    }
}

/// <summary>Immutable authentication state.</summary>
public sealed record CodexAuthenticationState(
    CodexAuthenticationStatus Status = CodexAuthenticationStatus.SignedOut,
    CodexAuthorizationUrl? PendingSignInUrl = null,
    CodexAuthorizationUrl? DeviceVerificationUrl = null,
    string? DeviceUserCode = null,
    CodexFailure? Failure = null);

/// <summary>A complete conversation value.</summary>
public sealed record CodexConversationSnapshot
{
    /// <summary>Creates a conversation snapshot.</summary>
    public CodexConversationSnapshot(CodexConversationSummary summary, IReadOnlyList<CodexMessage> messages)
    {
        Summary = summary;
        Messages = CodexValueCopies.List(messages);
    }

    /// <summary>The summary.</summary>
    public CodexConversationSummary Summary { get; }
    /// <summary>The ordered messages.</summary>
    public IReadOnlyList<CodexMessage> Messages { get; }
}

/// <summary>An invocation attached to a message or turn.</summary>
public abstract record CodexInvocation
{
    private CodexInvocation() { }
    /// <summary>The display name.</summary>
    public abstract string Name { get; }
    /// <summary>The stable invocation key.</summary>
    public abstract string Key { get; }

    /// <summary>A skill invocation.</summary>
    public sealed record Skill : CodexInvocation
    {
        /// <summary>Creates a skill invocation.</summary>
        public Skill(string name, string path)
        {
            Name = name;
            Path = path;
        }
        /// <inheritdoc />
        public override string Name { get; }
        /// <summary>The skill path.</summary>
        public string Path { get; }
        /// <inheritdoc />
        public override string Key => $"skill:{Path}";
    }

    /// <summary>A plugin invocation.</summary>
    public sealed record Plugin : CodexInvocation
    {
        /// <summary>Creates a plugin invocation.</summary>
        public Plugin(string name, string uri)
        {
            Name = name;
            Uri = uri;
        }
        /// <inheritdoc />
        public override string Name { get; }
        /// <summary>The plugin URI.</summary>
        public string Uri { get; }
        /// <inheritdoc />
        public override string Key => $"plugin:{Uri}";
    }
}

/// <summary>An immutable conversation message.</summary>
public sealed record CodexMessage
{
    /// <summary>Creates a message.</summary>
    public CodexMessage(
        string id,
        string? clientMessageId,
        CodexMessageRole role,
        string text,
        CodexCollaborationMode collaborationMode = CodexCollaborationMode.Default,
        string? reasoning = null,
        string? plan = null,
        string? shellCommand = null,
        int? exitCode = null,
        IEnumerable<CodexCapability>? capabilities = null,
        IReadOnlyList<CodexInvocation>? invocations = null)
    {
        Id = id;
        ClientMessageId = clientMessageId;
        Role = role;
        Text = text;
        CollaborationMode = collaborationMode;
        Reasoning = reasoning;
        Plan = plan;
        ShellCommand = shellCommand;
        ExitCode = exitCode;
        Capabilities = CodexValueCopies.Set(capabilities);
        Invocations = CodexValueCopies.List(invocations);
    }

    /// <summary>The message identifier.</summary>
    public string Id { get; }
    /// <summary>The optional client message identifier.</summary>
    public string? ClientMessageId { get; }
    /// <summary>The author role.</summary>
    public CodexMessageRole Role { get; }
    /// <summary>The message text.</summary>
    public string Text { get; }
    /// <summary>The collaboration mode.</summary>
    public CodexCollaborationMode CollaborationMode { get; }
    /// <summary>The optional reasoning text.</summary>
    public string? Reasoning { get; }
    /// <summary>The optional plan text.</summary>
    public string? Plan { get; }
    /// <summary>The optional shell command.</summary>
    public string? ShellCommand { get; }
    /// <summary>The optional shell exit code.</summary>
    public int? ExitCode { get; }
    /// <summary>The enabled capabilities.</summary>
    public IReadOnlySet<CodexCapability> Capabilities { get; }
    /// <summary>The ordered invocations.</summary>
    public IReadOnlyList<CodexInvocation> Invocations { get; }
}

/// <summary>An immutable turn request.</summary>
public sealed record CodexTurnRequest
{
    /// <summary>Creates a turn request.</summary>
    public CodexTurnRequest(
        string prompt,
        string? clientMessageId = null,
        string? model = null,
        string? effort = null,
        string? serviceTier = null,
        CodexApprovalPreset approvalPreset = CodexApprovalPreset.AutoReview,
        IEnumerable<CodexCapability>? capabilities = null,
        IReadOnlyList<CodexInvocation>? invocations = null,
        CodexCollaborationMode collaborationMode = CodexCollaborationMode.Default)
    {
        Prompt = prompt;
        ClientMessageId = clientMessageId;
        Model = model;
        Effort = effort;
        ServiceTier = serviceTier;
        ApprovalPreset = approvalPreset;
        Capabilities = CodexValueCopies.Set(capabilities);
        Invocations = CodexValueCopies.List(invocations);
        CollaborationMode = collaborationMode;
    }

    /// <summary>The prompt.</summary>
    public string Prompt { get; }
    /// <summary>The optional client message identifier.</summary>
    public string? ClientMessageId { get; }
    /// <summary>The optional model.</summary>
    public string? Model { get; }
    /// <summary>The optional effort.</summary>
    public string? Effort { get; }
    /// <summary>The optional service tier.</summary>
    public string? ServiceTier { get; }
    /// <summary>The approval preset.</summary>
    public CodexApprovalPreset ApprovalPreset { get; }
    /// <summary>The enabled capabilities.</summary>
    public IReadOnlySet<CodexCapability> Capabilities { get; }
    /// <summary>The ordered invocations.</summary>
    public IReadOnlyList<CodexInvocation> Invocations { get; }
    /// <summary>The collaboration mode.</summary>
    public CodexCollaborationMode CollaborationMode { get; }
}

/// <summary>A form value.</summary>
public abstract record CodexFormValue
{
    private CodexFormValue() { }
    /// <summary>A text value.</summary>
    public sealed record Text(string Value) : CodexFormValue;
    /// <summary>A numeric value.</summary>
    public sealed record Number(double Value) : CodexFormValue;
    /// <summary>A Boolean value.</summary>
    public sealed record BooleanValue(bool Value) : CodexFormValue;
    /// <summary>An ordered text-list value.</summary>
    public sealed record TextList : CodexFormValue
    {
        /// <summary>Creates a text-list value.</summary>
        public TextList(IReadOnlyList<string> value) => Value = CodexValueCopies.List(value);
        /// <summary>The ordered strings.</summary>
        public IReadOnlyList<string> Value { get; }
    }
}

/// <summary>A field in an elicitation form.</summary>
public sealed record CodexFormField
{
    /// <summary>Creates a form field.</summary>
    public CodexFormField(
        string name,
        string title,
        CodexFormFieldType type,
        string? description = null,
        bool isRequired = false,
        IReadOnlyList<CodexFormOption>? options = null,
        CodexFormValue? defaultValue = null,
        double? minimum = null,
        double? maximum = null,
        CodexFormStringFormat? format = null,
        long? minimumLength = null,
        long? maximumLength = null,
        long? minimumSelections = null,
        long? maximumSelections = null,
        bool allowsOther = false,
        bool isSecret = false)
    {
        if (minimumLength is < 0 || maximumLength is < 0 || minimumSelections is < 0 || maximumSelections is < 0)
            throw new ArgumentOutOfRangeException(nameof(minimumLength), "Form bounds must not be negative.");
        if (minimumLength > maximumLength || minimumSelections > maximumSelections)
            throw new ArgumentException("Form minimum must not exceed maximum.");
        Name = name;
        Title = title;
        Type = type;
        Description = description;
        IsRequired = isRequired;
        Options = CodexValueCopies.List(options);
        DefaultValue = defaultValue;
        Minimum = minimum;
        Maximum = maximum;
        Format = format;
        MinimumLength = minimumLength;
        MaximumLength = maximumLength;
        MinimumSelections = minimumSelections;
        MaximumSelections = maximumSelections;
        AllowsOther = allowsOther;
        IsSecret = isSecret;
    }

    /// <summary>The field name.</summary>
    public string Name { get; }
    /// <summary>The field title.</summary>
    public string Title { get; }
    /// <summary>The optional description.</summary>
    public string? Description { get; }
    /// <summary>Whether the field is required.</summary>
    public bool IsRequired { get; }
    /// <summary>The field type.</summary>
    public CodexFormFieldType Type { get; }
    /// <summary>The ordered options.</summary>
    public IReadOnlyList<CodexFormOption> Options { get; }
    /// <summary>The optional default value.</summary>
    public CodexFormValue? DefaultValue { get; }
    /// <summary>The optional numeric minimum.</summary>
    public double? Minimum { get; }
    /// <summary>The optional numeric maximum.</summary>
    public double? Maximum { get; }
    /// <summary>The optional string format.</summary>
    public CodexFormStringFormat? Format { get; }
    /// <summary>The optional minimum string length.</summary>
    public long? MinimumLength { get; }
    /// <summary>The optional maximum string length.</summary>
    public long? MaximumLength { get; }
    /// <summary>The optional minimum selection count.</summary>
    public long? MinimumSelections { get; }
    /// <summary>The optional maximum selection count.</summary>
    public long? MaximumSelections { get; }
    /// <summary>Whether values outside the options are allowed.</summary>
    public bool AllowsOther { get; }
    /// <summary>Whether the value is secret.</summary>
    public bool IsSecret { get; }

    /// <summary>Whether a value satisfies this field's type and constraints.</summary>
    public bool Accepts(CodexFormValue? value) => NativeValueBridge.FormFieldAccepts(this, value);
}

/// <summary>An elicitation request.</summary>
public sealed record CodexElicitation
{
    /// <summary>Creates an elicitation.</summary>
    public CodexElicitation(
        string requestId,
        string serverName,
        CodexConversationId conversationId,
        string message,
        IReadOnlyList<CodexFormField>? form = null,
        string? url = null)
    {
        RequestId = requestId;
        ServerName = serverName;
        ConversationId = conversationId;
        Message = message;
        Form = CodexValueCopies.NullableList(form);
        Url = url;
    }

    /// <summary>The request identifier.</summary>
    public string RequestId { get; }
    /// <summary>The requesting server name.</summary>
    public string ServerName { get; }
    /// <summary>The conversation identifier.</summary>
    public CodexConversationId ConversationId { get; }
    /// <summary>The request message.</summary>
    public string Message { get; }
    /// <summary>The optional ordered form.</summary>
    public IReadOnlyList<CodexFormField>? Form { get; }
    /// <summary>The optional request URL.</summary>
    public string? Url { get; }

    /// <summary>Returns immutable snapshots of every form default.</summary>
    public IReadOnlyDictionary<string, CodexFormValue> InitialValues() =>
        NativeValueBridge.ElicitationInitialValues(this);

    /// <summary>Validates submitted content and preserves canonical issue order.</summary>
    public CodexElicitationValidation Validate(IReadOnlyDictionary<string, CodexFormValue> content) =>
        NativeValueBridge.ElicitationValidate(this, content);

    /// <summary>Creates an accepted response when submitted content is valid.</summary>
    public CodexElicitationResponse Accept(IReadOnlyDictionary<string, CodexFormValue> content) =>
        NativeValueBridge.ElicitationAccept(this, content);

    /// <summary>Whether a response is valid for this elicitation.</summary>
    public bool Accepts(CodexElicitationResponse response) =>
        NativeValueBridge.ElicitationAccepts(this, response);
}

/// <summary>An elicitation response.</summary>
public sealed record CodexElicitationResponse
{
    /// <summary>Creates an elicitation response.</summary>
    public CodexElicitationResponse(
        CodexElicitationAction action,
        IReadOnlyDictionary<string, CodexFormValue>? content = null)
    {
        Action = action;
        Content = CodexValueCopies.Map(content);
    }

    /// <summary>The response action.</summary>
    public CodexElicitationAction Action { get; }
    /// <summary>The immutable response content.</summary>
    public IReadOnlyDictionary<string, CodexFormValue> Content { get; }

    /// <summary>Creates a response that declines the request.</summary>
    public static CodexElicitationResponse Decline() => NativeValueBridge.ElicitationResponse(false);

    /// <summary>Creates a response that cancels the request.</summary>
    public static CodexElicitationResponse Cancel() => NativeValueBridge.ElicitationResponse(true);
}

/// <summary>A configured hook handler.</summary>
public abstract record CodexHookHandler
{
    private CodexHookHandler() { }
    /// <summary>A command handler.</summary>
    public sealed record Command(string CommandText, bool IsAsync) : CodexHookHandler;
    /// <summary>An MCP-tool handler.</summary>
    public sealed record McpTool(string Server, string Tool) : CodexHookHandler;
    /// <summary>A prompt handler.</summary>
    public sealed record Prompt : CodexHookHandler
    {
        private Prompt() { }
        /// <summary>The single prompt-handler value.</summary>
        public static Prompt Instance { get; } = new();
    }
    /// <summary>An agent handler.</summary>
    public sealed record Agent : CodexHookHandler
    {
        private Agent() { }
        /// <summary>The single agent-handler value.</summary>
        public static Agent Instance { get; } = new();
    }
}

/// <summary>An immutable hook definition.</summary>
public sealed record CodexHook
{
    /// <summary>Creates a hook snapshot.</summary>
    public CodexHook(
        string key,
        string currentHash,
        bool isEnabled,
        string eventName,
        CodexHookHandler handler,
        bool isManaged,
        string source,
        string sourcePath,
        long timeoutSeconds,
        CodexHookTrustStatus trustStatus,
        string? matcher = null,
        string? pluginId = null,
        string? statusMessage = null,
        CodexResourceOrigin? origin = null,
        bool canUninstall = false)
    {
        Key = key;
        CurrentHash = currentHash;
        IsEnabled = isEnabled;
        EventName = eventName;
        Handler = handler;
        IsManaged = isManaged;
        Source = source;
        SourcePath = sourcePath;
        TimeoutSeconds = timeoutSeconds;
        TrustStatus = trustStatus;
        Matcher = matcher;
        PluginId = pluginId;
        StatusMessage = statusMessage;
        Origin = origin ?? ResolveOrigin(source, isManaged, pluginId);
        CanUninstall = canUninstall;
    }

    /// <summary>The stable key.</summary>
    public string Key { get; }
    /// <summary>The current content hash.</summary>
    public string CurrentHash { get; }
    /// <summary>Whether the hook is enabled.</summary>
    public bool IsEnabled { get; }
    /// <summary>The event name.</summary>
    public string EventName { get; }
    /// <summary>The handler.</summary>
    public CodexHookHandler Handler { get; }
    /// <summary>Whether the hook is managed.</summary>
    public bool IsManaged { get; }
    /// <summary>The source identifier.</summary>
    public string Source { get; }
    /// <summary>The source path.</summary>
    public string SourcePath { get; }
    /// <summary>The timeout in seconds.</summary>
    public long TimeoutSeconds { get; }
    /// <summary>The trust status.</summary>
    public CodexHookTrustStatus TrustStatus { get; }
    /// <summary>The optional matcher.</summary>
    public string? Matcher { get; }
    /// <summary>The optional plugin identifier.</summary>
    public string? PluginId { get; }
    /// <summary>The optional status message.</summary>
    public string? StatusMessage { get; }
    /// <summary>The resolved origin.</summary>
    public CodexResourceOrigin Origin { get; }
    /// <summary>Whether the hook can be trusted.</summary>
    public bool CanTrust => TrustStatus is CodexHookTrustStatus.Untrusted or CodexHookTrustStatus.Modified;
    /// <summary>Whether the hook may be uninstalled.</summary>
    public bool CanUninstall { get; }

    private static CodexResourceOrigin ResolveOrigin(string source, bool isManaged, string? pluginId)
    {
        if (pluginId is not null || source == "PLUGIN") return CodexResourceOrigin.Plugin;
        if (isManaged || source is "SYSTEM" or "MDM" or "CLOUD_REQUIREMENTS" or "CLOUD_MANAGED_CONFIG" or
            "LEGACY_MANAGED_CONFIG_FILE" or "LEGACY_MANAGED_CONFIG_MDM") return CodexResourceOrigin.Managed;
        return source switch
        {
            "USER" => CodexResourceOrigin.User,
            "PROJECT" => CodexResourceOrigin.Workspace,
            _ => CodexResourceOrigin.Unknown,
        };
    }
}

/// <summary>An immutable hook catalog.</summary>
public sealed record CodexHookCatalog
{
    /// <summary>Creates a hook catalog.</summary>
    public CodexHookCatalog(
        IReadOnlyList<CodexHook> hooks,
        IReadOnlyList<string>? warnings = null,
        IReadOnlyList<string>? errors = null)
    {
        Hooks = CodexValueCopies.List(hooks);
        Warnings = CodexValueCopies.List(warnings);
        Errors = CodexValueCopies.List(errors);
    }

    /// <summary>The ordered hooks.</summary>
    public IReadOnlyList<CodexHook> Hooks { get; }
    /// <summary>The ordered warnings.</summary>
    public IReadOnlyList<string> Warnings { get; }
    /// <summary>The ordered errors.</summary>
    public IReadOnlyList<string> Errors { get; }
}

/// <summary>An integration that can be authorized.</summary>
public abstract record CodexIntegration
{
    private CodexIntegration() { }
    /// <summary>The stable identifier.</summary>
    public abstract string Id { get; }
    /// <summary>The display name.</summary>
    public abstract string DisplayName { get; }

    /// <summary>A connector integration.</summary>
    public sealed record Connector(CodexConnector ConnectorValue) : CodexIntegration
    {
        /// <inheritdoc />
        public override string Id => ConnectorValue.Id;
        /// <inheritdoc />
        public override string DisplayName => ConnectorValue.Name;
    }

    /// <summary>An MCP-server integration.</summary>
    public sealed record McpServer(CodexMcpServer Server) : CodexIntegration
    {
        /// <inheritdoc />
        public override string Id => Server.Name;
        /// <inheritdoc />
        public override string DisplayName => Server.DisplayName;
    }
}

/// <summary>Immutable integration-authorization state.</summary>
public sealed record CodexIntegrationAuthorizationState(
    CodexIntegrationAuthorizationStatus Status = CodexIntegrationAuthorizationStatus.Idle,
    CodexIntegration? Target = null,
    CodexFailure? Failure = null);

/// <summary>A pending user interaction.</summary>
public abstract record CodexPendingInteraction
{
    private protected CodexPendingInteraction() { }
    /// <summary>The request identifier.</summary>
    public abstract string RequestId { get; }
    /// <summary>The conversation identifier.</summary>
    public abstract CodexConversationId ConversationId { get; }
}

/// <summary>A pending approval.</summary>
public sealed record CodexPendingApproval : CodexPendingInteraction
{
    /// <summary>Creates a pending approval.</summary>
    public CodexPendingApproval(string requestId, CodexConversationId conversationId, string title, string details)
    {
        RequestId = requestId;
        ConversationId = conversationId;
        Title = title;
        Details = details;
    }

    /// <inheritdoc />
    public override string RequestId { get; }
    /// <inheritdoc />
    public override CodexConversationId ConversationId { get; }
    /// <summary>The approval title.</summary>
    public string Title { get; }
    /// <summary>The approval details.</summary>
    public string Details { get; }
}

/// <summary>A pending elicitation.</summary>
public sealed record CodexPendingElicitation(CodexElicitation Elicitation) : CodexPendingInteraction
{
    /// <inheritdoc />
    public override string RequestId => Elicitation.RequestId;
    /// <inheritdoc />
    public override CodexConversationId ConversationId => Elicitation.ConversationId;
}

/// <summary>Immutable interaction state.</summary>
public sealed record CodexInteractionState
{
    /// <summary>Creates interaction state.</summary>
    public CodexInteractionState(
        IReadOnlyList<CodexPendingInteraction>? pending = null,
        IEnumerable<string>? resolvingRequestIds = null,
        CodexFailure? failure = null)
    {
        Pending = CodexValueCopies.List(pending);
        ResolvingRequestIds = CodexValueCopies.Set(resolvingRequestIds);
        Failure = failure;
    }

    /// <summary>The ordered pending interactions.</summary>
    public IReadOnlyList<CodexPendingInteraction> Pending { get; }
    /// <summary>The request identifiers currently being resolved.</summary>
    public IReadOnlySet<string> ResolvingRequestIds { get; }
    /// <summary>The optional failure.</summary>
    public CodexFailure? Failure { get; }

    /// <summary>Returns pending interactions for one conversation in stable order.</summary>
    public IReadOnlyList<CodexPendingInteraction> PendingFor(CodexConversationId conversationId) =>
        NativeValueBridge.InteractionStatePendingFor(this, conversationId);

    /// <summary>Whether this exact live interaction object is being resolved.</summary>
    public bool IsResolving(CodexPendingInteraction interaction) =>
        NativeValueBridge.InteractionStateIsResolving(this, interaction);
}

/// <summary>A validated path workspace selection.</summary>
public sealed record CodexPathWorkspaceSelection
{
    /// <summary>Creates a path selection.</summary>
    public CodexPathWorkspaceSelection(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        if (path.Contains('\0')) throw new ArgumentException("Workspace path must not contain NUL.", nameof(path));
        Path = path;
    }

    /// <summary>The workspace path.</summary>
    public string Path { get; }
}

/// <summary>A workspace-resolution result.</summary>
public abstract record CodexWorkspaceResolution
{
    private CodexWorkspaceResolution() { }
    /// <summary>An available workspace.</summary>
    public sealed record Available(CodexWorkspace Workspace) : CodexWorkspaceResolution;
    /// <summary>A required workspace selection.</summary>
    public sealed record SelectionRequired(CodexWorkspaceSelectionReason Reason, string Message) : CodexWorkspaceResolution;
}
