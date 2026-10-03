using System.Collections.Frozen;
using System.Collections.ObjectModel;

namespace CodexAgent;

/// <summary>A stable conversation identifier.</summary>
public sealed record CodexConversationId
{
    /// <summary>Creates a validated conversation identifier.</summary>
    public CodexConversationId(string value)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(value);
        Value = value;
    }

    /// <summary>The identifier value.</summary>
    public string Value { get; }
}

/// <summary>Immutable conversation settings.</summary>
public sealed record CodexConversationSettings(
    CodexApprovalPreset ApprovalPreset = CodexApprovalPreset.AutoReview,
    string? ServiceTier = null);

/// <summary>An immutable conversation summary.</summary>
public sealed record CodexConversationSummary(
    CodexConversationId ConversationId,
    string Title,
    long UpdatedAtEpochSeconds);

/// <summary>An available connector.</summary>
public sealed record CodexConnector
{
    /// <summary>Creates a connector snapshot.</summary>
    public CodexConnector(
        string id,
        string name,
        string description = "",
        string? installUrl = null,
        bool isAccessible = false,
        bool isEnabled = true,
        IReadOnlyList<string>? pluginNames = null)
    {
        Id = id;
        Name = name;
        Description = description;
        InstallUrl = installUrl;
        IsAccessible = isAccessible;
        IsEnabled = isEnabled;
        PluginNames = CodexValueCopies.List(pluginNames);
    }

    /// <summary>The connector identifier.</summary>
    public string Id { get; }
    /// <summary>The connector name.</summary>
    public string Name { get; }
    /// <summary>The connector description.</summary>
    public string Description { get; }
    /// <summary>The optional installation URL.</summary>
    public string? InstallUrl { get; }
    /// <summary>Whether the connector is accessible.</summary>
    public bool IsAccessible { get; }
    /// <summary>Whether the connector is enabled.</summary>
    public bool IsEnabled { get; }
    /// <summary>Ordered plugin names associated with the connector.</summary>
    public IReadOnlyList<string> PluginNames { get; }
}

/// <summary>A validation issue for one elicitation field.</summary>
public sealed record CodexElicitationValidationIssue(
    string FieldName,
    CodexElicitationValidationReason Reason);

/// <summary>An immutable elicitation validation result.</summary>
public sealed record CodexElicitationValidation
{
    /// <summary>Creates a validation result.</summary>
    public CodexElicitationValidation(IReadOnlyList<CodexElicitationValidationIssue> issues) =>
        Issues = CodexValueCopies.List(issues);

    /// <summary>The ordered validation issues.</summary>
    public IReadOnlyList<CodexElicitationValidationIssue> Issues { get; }

    /// <summary>Whether no validation issue exists.</summary>
    public bool IsValid => Issues.Count == 0;
}

/// <summary>An option in an elicitation form.</summary>
public sealed record CodexFormOption
{
    /// <summary>Creates a form option.</summary>
    public CodexFormOption(string value, string? title = null, string? description = null)
    {
        Value = value;
        Title = title ?? value;
        Description = description;
    }

    /// <summary>The submitted value.</summary>
    public string Value { get; }
    /// <summary>The display title.</summary>
    public string Title { get; }
    /// <summary>The optional description.</summary>
    public string? Description { get; }
}

/// <summary>One step in a plan.</summary>
public sealed record CodexPlanStep(string Text, CodexPlanStepStatus Status);

/// <summary>Immutable plan progress.</summary>
public sealed record CodexPlanProgress
{
    /// <summary>Creates plan progress.</summary>
    public CodexPlanProgress(string? explanation = null, IReadOnlyList<CodexPlanStep>? steps = null)
    {
        Explanation = explanation;
        Steps = CodexValueCopies.List(steps);
    }

    /// <summary>The optional plan explanation.</summary>
    public string? Explanation { get; }
    /// <summary>The ordered plan steps.</summary>
    public IReadOnlyList<CodexPlanStep> Steps { get; }
}

/// <summary>A service tier supported by a model.</summary>
public sealed record CodexServiceTier(string Id, string Name, string Description);

/// <summary>An available model.</summary>
public sealed record CodexModel
{
    /// <summary>Creates a model snapshot.</summary>
    public CodexModel(
        string id,
        string displayName,
        string description,
        IReadOnlyList<string> supportedEfforts,
        string defaultEffort,
        bool isDefault,
        IReadOnlyList<CodexServiceTier>? serviceTiers = null,
        string? defaultServiceTier = null)
    {
        Id = id;
        DisplayName = displayName;
        Description = description;
        SupportedEfforts = CodexValueCopies.List(supportedEfforts);
        DefaultEffort = defaultEffort;
        IsDefault = isDefault;
        ServiceTiers = CodexValueCopies.List(serviceTiers);
        DefaultServiceTier = defaultServiceTier;
    }

    /// <summary>The model identifier.</summary>
    public string Id { get; }
    /// <summary>The display name.</summary>
    public string DisplayName { get; }
    /// <summary>The model description.</summary>
    public string Description { get; }
    /// <summary>The ordered supported reasoning efforts.</summary>
    public IReadOnlyList<string> SupportedEfforts { get; }
    /// <summary>The default reasoning effort.</summary>
    public string DefaultEffort { get; }
    /// <summary>Whether this is the default model.</summary>
    public bool IsDefault { get; }
    /// <summary>The ordered supported service tiers.</summary>
    public IReadOnlyList<CodexServiceTier> ServiceTiers { get; }
    /// <summary>The optional default service tier.</summary>
    public string? DefaultServiceTier { get; }
}

/// <summary>A stable plugin reference.</summary>
public sealed record CodexPluginReference(
    string Id,
    string Name,
    string MarketplaceName,
    string? MarketplacePath = null,
    string? RemotePluginId = null)
{
    /// <summary>The canonical plugin URI.</summary>
    public string Uri => $"plugin://{Name}@{MarketplaceName}";
}

/// <summary>A skill contributed by a plugin.</summary>
public sealed record CodexPluginSkill(
    string Name,
    string Description,
    bool IsEnabled,
    string? Path = null);

/// <summary>An immutable plugin summary.</summary>
public sealed record CodexPluginSummary
{
    /// <summary>Creates a plugin summary.</summary>
    public CodexPluginSummary(
        CodexPluginReference reference,
        string displayName,
        string description,
        bool isInstalled,
        bool isEnabled,
        CodexPluginInstallPolicy installPolicy,
        CodexPluginAuthPolicy authPolicy,
        bool isAvailable,
        IReadOnlyList<string>? capabilities = null,
        string? brandColor = null,
        string? privacyPolicyUrl = null,
        string? termsOfServiceUrl = null,
        string? websiteUrl = null)
    {
        Reference = reference;
        DisplayName = displayName;
        Description = description;
        IsInstalled = isInstalled;
        IsEnabled = isEnabled;
        InstallPolicy = installPolicy;
        AuthPolicy = authPolicy;
        IsAvailable = isAvailable;
        Capabilities = CodexValueCopies.List(capabilities);
        BrandColor = brandColor;
        PrivacyPolicyUrl = privacyPolicyUrl;
        TermsOfServiceUrl = termsOfServiceUrl;
        WebsiteUrl = websiteUrl;
    }

    /// <summary>The stable reference.</summary>
    public CodexPluginReference Reference { get; }
    /// <summary>The plugin display name.</summary>
    public string DisplayName { get; }
    /// <summary>The plugin description.</summary>
    public string Description { get; }
    /// <summary>Whether the plugin is installed.</summary>
    public bool IsInstalled { get; }
    /// <summary>Whether the plugin is enabled.</summary>
    public bool IsEnabled { get; }
    /// <summary>The installation policy.</summary>
    public CodexPluginInstallPolicy InstallPolicy { get; }
    /// <summary>The authentication policy.</summary>
    public CodexPluginAuthPolicy AuthPolicy { get; }
    /// <summary>Whether the plugin is available.</summary>
    public bool IsAvailable { get; }
    /// <summary>The ordered capability names.</summary>
    public IReadOnlyList<string> Capabilities { get; }
    /// <summary>The optional brand color.</summary>
    public string? BrandColor { get; }
    /// <summary>The optional privacy-policy URL.</summary>
    public string? PrivacyPolicyUrl { get; }
    /// <summary>The optional terms-of-service URL.</summary>
    public string? TermsOfServiceUrl { get; }
    /// <summary>The optional website URL.</summary>
    public string? WebsiteUrl { get; }
}

/// <summary>An immutable plugin catalog.</summary>
public sealed record CodexPluginCatalog
{
    /// <summary>Creates a plugin catalog.</summary>
    public CodexPluginCatalog(
        IReadOnlyList<CodexPluginSummary> plugins,
        IReadOnlyList<string>? errors = null,
        CodexCatalogFreshness freshness = CodexCatalogFreshness.Live)
    {
        Plugins = CodexValueCopies.List(plugins);
        Errors = CodexValueCopies.List(errors);
        Freshness = freshness;
    }

    /// <summary>The ordered plugins.</summary>
    public IReadOnlyList<CodexPluginSummary> Plugins { get; }
    /// <summary>The ordered catalog errors.</summary>
    public IReadOnlyList<string> Errors { get; }
    /// <summary>The catalog freshness.</summary>
    public CodexCatalogFreshness Freshness { get; }
}

/// <summary>Complete plugin details.</summary>
public sealed record CodexPluginDetail
{
    /// <summary>Creates plugin details.</summary>
    public CodexPluginDetail(
        CodexPluginSummary summary,
        string description,
        IReadOnlyList<CodexPluginSkill> skills,
        IReadOnlyList<CodexConnector> connectors,
        IReadOnlyList<string> mcpServers,
        int hookCount)
    {
        Summary = summary;
        Description = description;
        Skills = CodexValueCopies.List(skills);
        Connectors = CodexValueCopies.List(connectors);
        McpServers = CodexValueCopies.List(mcpServers);
        HookCount = hookCount;
    }

    /// <summary>The plugin summary.</summary>
    public CodexPluginSummary Summary { get; }
    /// <summary>The detailed description.</summary>
    public string Description { get; }
    /// <summary>The ordered plugin skills.</summary>
    public IReadOnlyList<CodexPluginSkill> Skills { get; }
    /// <summary>The ordered connectors.</summary>
    public IReadOnlyList<CodexConnector> Connectors { get; }
    /// <summary>The ordered MCP server names.</summary>
    public IReadOnlyList<string> McpServers { get; }
    /// <summary>The number of hooks.</summary>
    public int HookCount { get; }
}

/// <summary>The result of installing a plugin.</summary>
public sealed record CodexPluginInstallResult
{
    /// <summary>Creates an installation result.</summary>
    public CodexPluginInstallResult(
        CodexPluginAuthPolicy authPolicy,
        IReadOnlyList<CodexConnector> connectorsNeedingAuthentication,
        string? message = null)
    {
        AuthPolicy = authPolicy;
        ConnectorsNeedingAuthentication = CodexValueCopies.List(connectorsNeedingAuthentication);
        Message = message;
    }

    /// <summary>The authentication policy.</summary>
    public CodexPluginAuthPolicy AuthPolicy { get; }
    /// <summary>The connectors that still require authentication.</summary>
    public IReadOnlyList<CodexConnector> ConnectorsNeedingAuthentication { get; }
    /// <summary>The optional result message.</summary>
    public string? Message { get; }
}

/// <summary>An installed skill.</summary>
public sealed record CodexSkill
{
    /// <summary>Creates a skill snapshot.</summary>
    public CodexSkill(
        string name,
        string displayName,
        string description,
        string path,
        CodexSkillScope scope,
        bool isEnabled,
        string? brandColor = null,
        IReadOnlyList<string>? dependencies = null,
        bool canUninstall = false,
        CodexResourceOrigin? origin = null)
    {
        Name = name;
        DisplayName = displayName;
        Description = description;
        Path = path;
        Scope = scope;
        IsEnabled = isEnabled;
        BrandColor = brandColor;
        Dependencies = CodexValueCopies.List(dependencies);
        CanUninstall = canUninstall;
        Origin = origin ?? scope switch
        {
            CodexSkillScope.User => CodexResourceOrigin.User,
            CodexSkillScope.Repo => CodexResourceOrigin.Workspace,
            CodexSkillScope.Plugin => CodexResourceOrigin.Plugin,
            CodexSkillScope.System or CodexSkillScope.Admin => CodexResourceOrigin.Managed,
            _ => CodexResourceOrigin.Unknown,
        };
    }

    /// <summary>The skill name.</summary>
    public string Name { get; }
    /// <summary>The display name.</summary>
    public string DisplayName { get; }
    /// <summary>The skill description.</summary>
    public string Description { get; }
    /// <summary>The skill path.</summary>
    public string Path { get; }
    /// <summary>The installation scope.</summary>
    public CodexSkillScope Scope { get; }
    /// <summary>Whether the skill is enabled.</summary>
    public bool IsEnabled { get; }
    /// <summary>The optional brand color.</summary>
    public string? BrandColor { get; }
    /// <summary>The ordered dependencies.</summary>
    public IReadOnlyList<string> Dependencies { get; }
    /// <summary>Whether the skill may be uninstalled.</summary>
    public bool CanUninstall { get; }
    /// <summary>The resolved skill origin.</summary>
    public CodexResourceOrigin Origin { get; }
}

/// <summary>An immutable skill catalog.</summary>
public sealed record CodexSkillCatalog
{
    /// <summary>Creates a skill catalog.</summary>
    public CodexSkillCatalog(IReadOnlyList<CodexSkill> skills, IReadOnlyList<string>? errors = null)
    {
        Skills = CodexValueCopies.List(skills);
        Errors = CodexValueCopies.List(errors);
    }

    /// <summary>The ordered skills.</summary>
    public IReadOnlyList<CodexSkill> Skills { get; }
    /// <summary>The ordered errors.</summary>
    public IReadOnlyList<string> Errors { get; }
}

/// <summary>A chunk of skill content.</summary>
public sealed record CodexSkillChunk(string Content, long? NextOffset, long TotalBytes);

/// <summary>A hook activity snapshot.</summary>
public sealed record CodexHookActivity
{
    /// <summary>Creates a hook activity.</summary>
    public CodexHookActivity(
        string id,
        string eventName,
        string handlerType,
        CodexHookRunStatus status,
        string? statusMessage = null,
        IReadOnlyList<string>? details = null)
    {
        Id = id;
        EventName = eventName;
        HandlerType = handlerType;
        Status = status;
        StatusMessage = statusMessage;
        Details = CodexValueCopies.List(details);
    }

    /// <summary>The activity identifier.</summary>
    public string Id { get; }
    /// <summary>The hook event name.</summary>
    public string EventName { get; }
    /// <summary>The handler type.</summary>
    public string HandlerType { get; }
    /// <summary>The run status.</summary>
    public CodexHookRunStatus Status { get; }
    /// <summary>The optional status message.</summary>
    public string? StatusMessage { get; }
    /// <summary>The ordered detail lines.</summary>
    public IReadOnlyList<string> Details { get; }
}

/// <summary>Immutable progress for the current turn.</summary>
public sealed record CodexTurnProgress
{
    /// <summary>Creates a turn-progress snapshot.</summary>
    public CodexTurnProgress(
        string text = "",
        string commentary = "",
        string reasoning = "",
        string plan = "",
        CodexPlanProgress? planProgress = null,
        string shellOutput = "",
        int? shellExitCode = null,
        CodexWorkActivity? workActivity = null,
        IReadOnlyList<CodexHookActivity>? hookActivities = null,
        bool isTruncated = false)
    {
        Text = text;
        Commentary = commentary;
        Reasoning = reasoning;
        Plan = plan;
        PlanProgress = planProgress;
        ShellOutput = shellOutput;
        ShellExitCode = shellExitCode;
        WorkActivity = workActivity;
        HookActivities = CodexValueCopies.List(hookActivities);
        IsTruncated = isTruncated;
    }

    /// <summary>The assistant text.</summary>
    public string Text { get; }
    /// <summary>The assistant commentary.</summary>
    public string Commentary { get; }
    /// <summary>The assistant reasoning.</summary>
    public string Reasoning { get; }
    /// <summary>The plan text.</summary>
    public string Plan { get; }
    /// <summary>The optional structured plan progress.</summary>
    public CodexPlanProgress? PlanProgress { get; }
    /// <summary>The accumulated shell output.</summary>
    public string ShellOutput { get; }
    /// <summary>The optional shell exit code.</summary>
    public int? ShellExitCode { get; }
    /// <summary>The optional work activity.</summary>
    public CodexWorkActivity? WorkActivity { get; }
    /// <summary>The ordered hook activities.</summary>
    public IReadOnlyList<CodexHookActivity> HookActivities { get; }
    /// <summary>Whether retained progress was truncated.</summary>
    public bool IsTruncated { get; }
}

internal static class CodexValueCopies
{
    internal static IReadOnlyList<T> List<T>(IReadOnlyList<T>? values) =>
        Array.AsReadOnly(values?.ToArray() ?? []);

    internal static IReadOnlyList<T>? NullableList<T>(IReadOnlyList<T>? values) =>
        values is null ? null : List(values);

    internal static IReadOnlySet<T> Set<T>(IEnumerable<T>? values) =>
        (values ?? []).ToFrozenSet();

    internal static IReadOnlyDictionary<TKey, TValue> Map<TKey, TValue>(IReadOnlyDictionary<TKey, TValue>? values)
        where TKey : notnull =>
        new ReadOnlyDictionary<TKey, TValue>(new Dictionary<TKey, TValue>(values ?? new Dictionary<TKey, TValue>()));
}
