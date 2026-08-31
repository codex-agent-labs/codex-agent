namespace CodexAgent;

/// <summary>Status values returned by the stable Codex Agent C ABI.</summary>
public enum CodexStatus
{
    /// <summary>The call succeeded.</summary>
    Ok = 0,
    /// <summary>An argument violates the ABI contract.</summary>
    InvalidArgument = 1,
    /// <summary>Native allocation failed.</summary>
    OutOfMemory = 2,
    /// <summary>The handle is no longer valid.</summary>
    StaleHandle = 3,
    /// <summary>The handle has the wrong native type.</summary>
    WrongHandleType = 4,
    /// <summary>The handle belongs to another context.</summary>
    WrongContext = 5,
    /// <summary>The resource is still in use.</summary>
    Busy = 6,
    /// <summary>The operation was cancelled.</summary>
    Cancelled = 7,
    /// <summary>An internal native failure occurred.</summary>
    InternalError = 8,
    /// <summary>The destination buffer is too small.</summary>
    BufferTooSmall = 9,
    /// <summary>The loaded ABI is incompatible.</summary>
    UnsupportedAbi = 10,
    /// <summary>The resource is closed.</summary>
    Closed = 11,
    /// <summary>The call would deadlock on the current callback thread.</summary>
    WouldDeadlock = 12,
    /// <summary>The requested value is not available.</summary>
    NotReady = 13,
    /// <summary>The operation completed with a structured failure.</summary>
    OperationFailed = 14,
}

/// <summary>Host lifecycle states.</summary>
public enum CodexHostStateKind
{
    /// <summary>The host has not started.</summary>
    New = 0,
    /// <summary>The host is restoring prior state.</summary>
    Restoring = 1,
    /// <summary>The user must select a workspace.</summary>
    WorkspaceRequired = 2,
    /// <summary>The runtime is being prepared.</summary>
    Preparing = 3,
    /// <summary>The agent is ready.</summary>
    Ready = 4,
    /// <summary>Startup failed.</summary>
    Failed = 5,
    /// <summary>The host is closed.</summary>
    Closed = 6,
}

/// <summary>Reasons that explicit workspace selection is required.</summary>
public enum CodexWorkspaceSelectionReason
{
    /// <summary>No workspace has been selected.</summary>
    NotSelected = 0,
    /// <summary>The selected workspace cannot be found.</summary>
    NotFound = 1,
    /// <summary>Access to the selected workspace was revoked.</summary>
    AccessRevoked = 2,
    /// <summary>The selection is invalid.</summary>
    InvalidSelection = 3,
}

/// <summary>Conversation lifecycle states.</summary>
public enum CodexConversationStatus
{
    /// <summary>The conversation is new.</summary>
    New = 0,
    /// <summary>The conversation is opening.</summary>
    Opening = 1,
    /// <summary>The conversation accepts work.</summary>
    Ready = 2,
    /// <summary>A turn is starting.</summary>
    StartingTurn = 3,
    /// <summary>A turn is running.</summary>
    RunningTurn = 4,
    /// <summary>The active turn is being cancelled.</summary>
    CancellingTurn = 5,
    /// <summary>The conversation is reloading.</summary>
    Reloading = 6,
    /// <summary>The conversation failed.</summary>
    Failed = 7,
    /// <summary>The conversation is closed.</summary>
    Closed = 8,
}

/// <summary>Approval behavior for a conversation.</summary>
public enum CodexApprovalPreset
{
    /// <summary>Never request approval.</summary>
    Never = 0,
    /// <summary>Use automatic review.</summary>
    AutoReview = 1,
    /// <summary>Ask the user when approval is needed.</summary>
    AskMe = 2,
    /// <summary>Use strict approval.</summary>
    Strict = 3,
}

/// <summary>Identifies the embedding .NET client.</summary>
public sealed record CodexClientInfo
{
    /// <summary>Creates a validated client identity.</summary>
    public CodexClientInfo(string name, string title, string version)
    {
        ValidateValue(name, nameof(name));
        ValidateValue(title, nameof(title));
        ValidateValue(version, nameof(version));
        Name = name;
        Title = title;
        Version = version;
    }

    /// <summary>The stable machine-readable client name.</summary>
    public string Name { get; }

    /// <summary>The human-readable client title.</summary>
    public string Title { get; }

    /// <summary>The client version.</summary>
    public string Version { get; }

    internal void Validate()
    {
        ValidateValue(Name, nameof(Name));
        ValidateValue(Title, nameof(Title));
        ValidateValue(Version, nameof(Version));
    }

    private static void ValidateValue(string value, string parameterName)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value, parameterName);
        if (value.Any(char.IsControl))
            throw new ArgumentException("Client information must not contain control characters.", parameterName);
    }
}

/// <summary>Inputs used to create a local desktop host.</summary>
/// <param name="BundleDirectory">Verified runtime bundle directory.</param>
/// <param name="DataDirectory">Persistent host data directory.</param>
/// <param name="ClientInfo">Embedding client identity.</param>
public sealed record CodexHostOptions(
    string BundleDirectory,
    string DataDirectory,
    CodexClientInfo ClientInfo)
{
    internal void Validate()
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(BundleDirectory);
        ArgumentException.ThrowIfNullOrWhiteSpace(DataDirectory);
        ArgumentNullException.ThrowIfNull(ClientInfo);
        ClientInfo.Validate();
    }
}

/// <summary>Optional inputs used to open or resume a conversation.</summary>
/// <param name="ConversationId">Existing conversation identifier, or null for a new conversation.</param>
/// <param name="ApprovalPreset">Optional approval behavior.</param>
/// <param name="ServiceTier">Optional service tier.</param>
public sealed record CodexConversationOpenOptions(
    string? ConversationId = null,
    CodexApprovalPreset? ApprovalPreset = null,
    string? ServiceTier = null);

/// <summary>A resolved workspace.</summary>
public sealed record CodexWorkspace
{
    /// <summary>Creates a validated workspace.</summary>
    public CodexWorkspace(string path, string? displayName = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        if (path.Contains('\0')) throw new ArgumentException("Workspace path must not contain NUL.", nameof(path));
        displayName ??= path;
        ArgumentException.ThrowIfNullOrWhiteSpace(displayName);
        Path = path;
        DisplayName = displayName;
    }

    /// <summary>The workspace path.</summary>
    public string Path { get; }

    /// <summary>The human-readable workspace name.</summary>
    public string DisplayName { get; }
}

/// <summary>A structured canonical failure.</summary>
public sealed record CodexFailure
{
    /// <summary>Creates a validated structured failure.</summary>
    public CodexFailure(string code, string message, bool isRecoverable)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(code);
        ArgumentException.ThrowIfNullOrWhiteSpace(message);
        if (message.Length > 500) throw new ArgumentOutOfRangeException(nameof(message), "Failure message must not exceed 500 characters.");
        Code = code;
        Message = message;
        IsRecoverable = isRecoverable;
    }

    /// <summary>The stable failure code.</summary>
    public string Code { get; }

    /// <summary>The human-readable failure message.</summary>
    public string Message { get; }

    /// <summary>Whether retry or user action may recover.</summary>
    public bool IsRecoverable { get; }
}

/// <summary>An immutable host state snapshot.</summary>
/// <param name="Kind">Lifecycle state.</param>
/// <param name="Workspace">Resolved workspace when available.</param>
/// <param name="Agent">Stable agent when ready.</param>
/// <param name="SelectionReason">Workspace selection reason when required.</param>
/// <param name="RequirementMessage">Workspace selection guidance.</param>
/// <param name="Failure">Structured failure when failed.</param>
public sealed record CodexHostState(
    CodexHostStateKind Kind,
    CodexWorkspace? Workspace = null,
    CodexAgent? Agent = null,
    CodexWorkspaceSelectionReason? SelectionReason = null,
    string? RequirementMessage = null,
    CodexFailure? Failure = null)
{
    /// <summary>The canonical new-state value.</summary>
    public sealed record New
    {
        private New() { }
        /// <summary>The single new-state instance.</summary>
        public static New Instance { get; } = new();
    }

    /// <summary>The canonical restoring-state value.</summary>
    public sealed record Restoring
    {
        private Restoring() { }
        /// <summary>The single restoring-state instance.</summary>
        public static Restoring Instance { get; } = new();
    }

    /// <summary>A workspace-required state.</summary>
    public sealed record WorkspaceRequired(CodexWorkspaceResolution.SelectionRequired Requirement);

    /// <summary>A runtime-preparation state.</summary>
    public sealed record Preparing(CodexWorkspace Workspace);

    /// <summary>A failed host state.</summary>
    public sealed record Failed(CodexWorkspace? Workspace, CodexFailure Failure);

    /// <summary>A ready host with its stable agent.</summary>
    public sealed record Ready(CodexAgent Agent);

    /// <summary>The canonical closed-state value.</summary>
    public sealed record Closed
    {
        private Closed() { }
        /// <summary>The single closed-state instance.</summary>
        public static Closed Instance { get; } = new();
    }
}

/// <summary>An immutable conversation state snapshot.</summary>
public sealed record CodexConversationState
{
    /// <summary>Creates a lifecycle-compatible conversation state.</summary>
    public CodexConversationState(CodexConversationStatus status, CodexFailure? failure) :
        this(status, null, null, null, null, null, null, failure) { }

    /// <summary>Creates a complete canonical conversation state.</summary>
    public CodexConversationState(
        CodexConversationStatus status = CodexConversationStatus.New,
        CodexConversationId? conversationId = null,
        CodexConversationSnapshot? conversation = null,
        CodexTurnProgress? turnProgress = null,
        string? model = null,
        string? effort = null,
        string? serviceTier = null,
        CodexFailure? failure = null)
    {
        Status = status;
        ConversationId = conversationId;
        Conversation = conversation;
        TurnProgress = turnProgress ?? new CodexTurnProgress();
        Model = model;
        Effort = effort;
        ServiceTier = serviceTier;
        Failure = failure;
    }

    /// <summary>The lifecycle status.</summary>
    public CodexConversationStatus Status { get; }
    /// <summary>The optional conversation identifier.</summary>
    public CodexConversationId? ConversationId { get; }
    /// <summary>The optional conversation snapshot.</summary>
    public CodexConversationSnapshot? Conversation { get; }
    /// <summary>The current turn progress.</summary>
    public CodexTurnProgress TurnProgress { get; }
    /// <summary>The optional model identifier.</summary>
    public string? Model { get; }
    /// <summary>The optional reasoning effort.</summary>
    public string? Effort { get; }
    /// <summary>The optional service tier.</summary>
    public string? ServiceTier { get; }
    /// <summary>The optional structured failure.</summary>
    public CodexFailure? Failure { get; }
    /// <summary>Whether a turn may start.</summary>
    public bool CanStartTurn => ConversationId is not null &&
        (Status == CodexConversationStatus.Ready || Status == CodexConversationStatus.Failed && Failure?.IsRecoverable == true);
    /// <summary>Whether the conversation may reload.</summary>
    public bool CanReload => ConversationId is not null && Status is CodexConversationStatus.Ready or CodexConversationStatus.Failed;
    /// <summary>Whether the current turn may be cancelled.</summary>
    public bool CanCancelTurn => Status is CodexConversationStatus.StartingTurn or CodexConversationStatus.RunningTurn;
}
