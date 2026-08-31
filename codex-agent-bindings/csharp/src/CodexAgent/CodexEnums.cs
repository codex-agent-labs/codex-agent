namespace CodexAgent;

/// <summary>A decision for an approval request.</summary>
public enum CodexApprovalDecision
{
    /// <summary>Accept the request.</summary>
    Accept = 0,
    /// <summary>Decline the request.</summary>
    Decline = 1,
}

/// <summary>The agent authentication state.</summary>
public enum CodexAuthenticationStatus
{
    /// <summary>The user is signed out.</summary>
    SignedOut = 0,
    /// <summary>Authentication is in progress.</summary>
    Authenticating = 1,
    /// <summary>The user is authenticated.</summary>
    Authenticated = 2,
}

/// <summary>A capability available to an agent.</summary>
public enum CodexCapability
{
    /// <summary>Search the web.</summary>
    WebSearch = 0,
}

/// <summary>The freshness of catalog data.</summary>
public enum CodexCatalogFreshness
{
    /// <summary>Data came from the live source.</summary>
    Live = 0,
    /// <summary>Data came from a fresh cache.</summary>
    FreshCache = 1,
    /// <summary>Data came from a stale cache.</summary>
    StaleCache = 2,
}

/// <summary>The collaboration mode for a conversation.</summary>
public enum CodexCollaborationMode
{
    /// <summary>Use the default collaboration mode.</summary>
    Default = 0,
    /// <summary>Use planning mode.</summary>
    Plan = 1,
}

/// <summary>The action taken for an elicitation request.</summary>
public enum CodexElicitationAction
{
    /// <summary>Accept the request.</summary>
    Accept = 0,
    /// <summary>Decline the request.</summary>
    Decline = 1,
    /// <summary>Cancel the request.</summary>
    Cancel = 2,
}

/// <summary>The reason elicitation input is invalid.</summary>
public enum CodexElicitationValidationReason
{
    /// <summary>A required value is missing.</summary>
    MissingRequired = 0,
    /// <summary>The field is unknown.</summary>
    UnknownField = 1,
    /// <summary>The value has an invalid type.</summary>
    InvalidType = 2,
    /// <summary>The number is not finite.</summary>
    NonFiniteNumber = 3,
    /// <summary>The number is below the minimum.</summary>
    BelowMinimum = 4,
    /// <summary>The number is above the maximum.</summary>
    AboveMaximum = 5,
    /// <summary>The number is not an integer.</summary>
    NonInteger = 6,
    /// <summary>The string has an invalid format.</summary>
    InvalidFormat = 7,
    /// <summary>The selection is invalid.</summary>
    InvalidSelection = 8,
    /// <summary>The selection contains duplicates.</summary>
    DuplicateSelection = 9,
}

/// <summary>The data type of a form field.</summary>
public enum CodexFormFieldType
{
    /// <summary>A string value.</summary>
    String = 0,
    /// <summary>A numeric value.</summary>
    Number = 1,
    /// <summary>An integer value.</summary>
    Integer = 2,
    /// <summary>A Boolean value.</summary>
    Boolean = 3,
    /// <summary>One selected option.</summary>
    SingleSelect = 4,
    /// <summary>Multiple selected options.</summary>
    MultiSelect = 5,
}

/// <summary>The expected format of a string form field.</summary>
public enum CodexFormStringFormat
{
    /// <summary>An email address.</summary>
    Email = 0,
    /// <summary>A URI.</summary>
    Uri = 1,
    /// <summary>A calendar date.</summary>
    Date = 2,
    /// <summary>A date and time.</summary>
    DateTime = 3,
}

/// <summary>The execution state of a hook run.</summary>
public enum CodexHookRunStatus
{
    /// <summary>The hook is running.</summary>
    Running = 0,
    /// <summary>The hook completed successfully.</summary>
    Completed = 1,
    /// <summary>The hook failed.</summary>
    Failed = 2,
    /// <summary>The hook was blocked.</summary>
    Blocked = 3,
    /// <summary>The hook was stopped.</summary>
    Stopped = 4,
}

/// <summary>The trust state of a hook.</summary>
public enum CodexHookTrustStatus
{
    /// <summary>The hook is centrally managed.</summary>
    Managed = 0,
    /// <summary>The hook is not trusted.</summary>
    Untrusted = 1,
    /// <summary>The hook is trusted.</summary>
    Trusted = 2,
    /// <summary>The trusted hook has been modified.</summary>
    Modified = 3,
}

/// <summary>The installation scope of a resource.</summary>
public enum CodexInstallationScope
{
    /// <summary>Install for the user.</summary>
    User = 0,
    /// <summary>Install for the workspace.</summary>
    Workspace = 1,
}

/// <summary>The state of integration authorization.</summary>
public enum CodexIntegrationAuthorizationStatus
{
    /// <summary>No authorization is active.</summary>
    Idle = 0,
    /// <summary>Authorization is starting.</summary>
    Starting = 1,
    /// <summary>Authorization is awaiting completion.</summary>
    AwaitingCompletion = 2,
    /// <summary>Authorization succeeded.</summary>
    Authorized = 3,
    /// <summary>Authorization failed.</summary>
    Failed = 4,
}

/// <summary>The authentication state of an MCP server.</summary>
public enum CodexMcpAuthStatus
{
    /// <summary>The authentication state is unknown.</summary>
    Unknown = 0,
    /// <summary>Authentication is unsupported.</summary>
    Unsupported = 1,
    /// <summary>The user is not logged in.</summary>
    NotLoggedIn = 2,
    /// <summary>A bearer token is configured.</summary>
    BearerToken = 3,
    /// <summary>OAuth is configured.</summary>
    Oauth = 4,
}

/// <summary>The authentication mechanism of an MCP server.</summary>
public enum CodexMcpAuthentication
{
    /// <summary>OAuth authentication.</summary>
    Oauth = 0,
    /// <summary>ChatGPT authentication.</summary>
    ChatGpt = 1,
}

/// <summary>The source of an MCP environment value.</summary>
public enum CodexMcpEnvironmentSource
{
    /// <summary>The local environment.</summary>
    Local = 0,
    /// <summary>The remote environment.</summary>
    Remote = 1,
}

/// <summary>The approval policy for an MCP tool.</summary>
public enum CodexMcpToolApproval
{
    /// <summary>Apply automatic approval policy.</summary>
    Auto = 0,
    /// <summary>Prompt before use.</summary>
    Prompt = 1,
    /// <summary>Prompt for writes.</summary>
    Writes = 2,
    /// <summary>Approve use.</summary>
    Approve = 3,
}

/// <summary>A surface on which an MCP tool is exposed.</summary>
public enum CodexMcpToolExposureSurface
{
    /// <summary>Expose the tool in code mode.</summary>
    CodeMode = 0,
    /// <summary>Expose the tool through deferred loading.</summary>
    Deferred = 1,
    /// <summary>Expose the tool directly.</summary>
    Direct = 2,
}

/// <summary>The author of a message.</summary>
public enum CodexMessageRole
{
    /// <summary>The user.</summary>
    User = 0,
    /// <summary>The assistant.</summary>
    Assistant = 1,
}

/// <summary>The state of a plan step.</summary>
public enum CodexPlanStepStatus
{
    /// <summary>The step is pending.</summary>
    Pending = 0,
    /// <summary>The step is in progress.</summary>
    InProgress = 1,
    /// <summary>The step is complete.</summary>
    Completed = 2,
}

/// <summary>When a plugin requests authentication.</summary>
public enum CodexPluginAuthPolicy
{
    /// <summary>Authenticate during installation.</summary>
    OnInstall = 0,
    /// <summary>Authenticate on first use.</summary>
    OnUse = 1,
}

/// <summary>The installation policy for a plugin.</summary>
public enum CodexPluginInstallPolicy
{
    /// <summary>The plugin is not available.</summary>
    NotAvailable = 0,
    /// <summary>The plugin is available to install.</summary>
    Available = 1,
    /// <summary>The plugin is installed by default.</summary>
    InstalledByDefault = 2,
}

/// <summary>How a value was resolved.</summary>
public enum CodexResolution
{
    /// <summary>The preferred value was selected.</summary>
    Preferred = 0,
    /// <summary>The default value was selected.</summary>
    Default = 1,
    /// <summary>The first available value was selected.</summary>
    First = 2,
}

/// <summary>The origin of a resource.</summary>
public enum CodexResourceOrigin
{
    /// <summary>The resource belongs to the user.</summary>
    User = 0,
    /// <summary>The resource belongs to the workspace.</summary>
    Workspace = 1,
    /// <summary>The resource came from a plugin.</summary>
    Plugin = 2,
    /// <summary>The resource is centrally managed.</summary>
    Managed = 3,
    /// <summary>The resource origin is unknown.</summary>
    Unknown = 4,
}

/// <summary>The scope of a skill.</summary>
public enum CodexSkillScope
{
    /// <summary>A system skill.</summary>
    System = 0,
    /// <summary>A user skill.</summary>
    User = 1,
    /// <summary>A repository skill.</summary>
    Repo = 2,
    /// <summary>A plugin skill.</summary>
    Plugin = 3,
    /// <summary>An administrator-provided skill.</summary>
    Admin = 4,
}

/// <summary>The agent's current work activity.</summary>
public enum CodexWorkActivity
{
    /// <summary>The agent is running a command.</summary>
    RunningCommand = 0,
    /// <summary>The agent is writing files.</summary>
    WritingFiles = 1,
}

/// <summary>The purpose of an authorization request.</summary>
public enum CodexAuthorizationPurpose
{
    /// <summary>Authorization for ChatGPT.</summary>
    ChatGpt = 0,
    /// <summary>Authorization for an external service.</summary>
    External = 1,
}
