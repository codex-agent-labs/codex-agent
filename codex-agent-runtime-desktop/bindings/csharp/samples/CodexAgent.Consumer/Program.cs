using CodexAgent;

static async Task RequireOpenDisposeRejected(Action dispose)
{
    var rejected = await Task.Run(() =>
    {
        try { dispose(); }
        catch (InvalidOperationException error) when (error.Message.Contains("DisposeAsync", StringComparison.Ordinal))
        {
            return true;
        }
        return false;
    }).WaitAsync(TimeSpan.FromSeconds(2));
    if (!rejected) throw new InvalidOperationException("Open host was synchronously released.");
}

static void VerifyMcpValues()
{
    var environmentVariable = new CodexMcpEnvironmentVariable("TOKEN", CodexMcpEnvironmentSource.Local);
    if (environmentVariable is not { Name: "TOKEN", Source: CodexMcpEnvironmentSource.Local })
        throw new InvalidOperationException("Packed MCP environment-variable projection is incompatible.");
    var oauth = new CodexMcpOauthConfiguration("client", 8080);
    if (oauth is not { ClientId: "client", CallbackPort: 8080 })
        throw new InvalidOperationException("Packed MCP OAuth projection is incompatible.");
    var tool = new CodexMcpToolConfiguration(CodexMcpToolApproval.Prompt);
    if (tool.Approval != CodexMcpToolApproval.Prompt)
        throw new InvalidOperationException("Packed MCP tool projection is incompatible.");

    var headers = new Dictionary<string, string> { ["X-Test"] = "value" };
    var environmentHeaders = new Dictionary<string, string> { ["Authorization"] = "AUTH" };
    var http = new CodexMcpTransport.Http("https://example.com/mcp", "TOKEN", headers, environmentHeaders, "helper");
    if (http.Url != "https://example.com/mcp" || http.BearerTokenEnvironmentVariable != "TOKEN" ||
        http.Headers!["X-Test"] != "value" || http.EnvironmentHeaders!["Authorization"] != "AUTH" || http.HeadersHelper != "helper")
        throw new InvalidOperationException("Packed HTTP MCP transport projection is incompatible.");

    var arguments = new List<string> { "server.js", "--stdio" };
    var stdioEnvironment = new Dictionary<string, string> { ["STATIC"] = "value" };
    var stdio = new CodexMcpTransport.Stdio("node", arguments, "/workspace", stdioEnvironment, [environmentVariable]);
    arguments[0] = "mutated";
    stdioEnvironment["STATIC"] = "mutated";
    if (stdio.Command != "node" || !stdio.Arguments.SequenceEqual(["server.js", "--stdio"]) ||
        stdio.WorkingDirectory != "/workspace" || stdio.Environment!["STATIC"] != "value" ||
        stdio.ForwardedEnvironment.Single() != environmentVariable)
        throw new InvalidOperationException("Packed stdio MCP transport projection is incompatible.");

    var configuration = new CodexMcpServerConfiguration(
        "consumer_server",
        http,
        CodexMcpAuthentication.Oauth,
        "local",
        false,
        true,
        true,
        [CodexMcpToolExposureSurface.CodeMode],
        1.5,
        2.5,
        CodexMcpToolApproval.Writes,
        ["search"],
        [],
        ["files.read"],
        oauth,
        "resource",
        new Dictionary<string, CodexMcpToolConfiguration> { ["search"] = tool });
    if (configuration.Name != "consumer_server" || configuration.Transport != http ||
        configuration.Authentication != CodexMcpAuthentication.Oauth || configuration.EnvironmentId != "local" ||
        configuration.IsEnabled || !configuration.IsRequired || !configuration.SupportsParallelToolCalls ||
        !configuration.OmitToolsFrom!.SequenceEqual([CodexMcpToolExposureSurface.CodeMode]) ||
        configuration.StartupTimeoutSeconds != 1.5 || configuration.ToolTimeoutSeconds != 2.5 ||
        configuration.DefaultToolApproval != CodexMcpToolApproval.Writes ||
        !configuration.EnabledTools!.SequenceEqual(["search"]) || configuration.DisabledTools!.Count != 0 ||
        !configuration.Scopes!.SequenceEqual(["files.read"]) || configuration.Oauth != oauth ||
        configuration.OauthResource != "resource" || configuration.Tools["search"] != tool)
        throw new InvalidOperationException("Packed MCP server-configuration projection is incompatible.");

    var server = new CodexMcpServer(
        "consumer_server", "Consumer Server", CodexMcpAuthStatus.Oauth, configuration, CodexResourceOrigin.User, true);
    if (server.Name != "consumer_server" || server.DisplayName != "Consumer Server" ||
        server.AuthStatus != CodexMcpAuthStatus.Oauth || server.Configuration != configuration ||
        server.Origin != CodexResourceOrigin.User || !server.CanRemove || !server.IsAuthorized)
        throw new InvalidOperationException("Packed MCP server projection is incompatible.");
}

static void VerifyOrdinaryValues()
{
    var pluginNames = new List<string> { "plugin", "plugin" };
    var connector = new CodexConnector("connector", "Connector", pluginNames: pluginNames);
    pluginNames.Clear();
    if (!connector.PluginNames.SequenceEqual(["plugin", "plugin"]))
        throw new InvalidOperationException("Packed connector projection is not an immutable ordered value.");

    var step = new CodexPlanStep("compile", CodexPlanStepStatus.Completed);
    var progress = new CodexPlanProgress("done", [step, step]);
    var hook = new CodexHookActivity("hook", "after-turn", "command", CodexHookRunStatus.Completed);
    var turn = new CodexTurnProgress(planProgress: progress, hookActivities: [hook, hook]);
    if (turn.PlanProgress?.Steps.Count != 2 || turn.HookActivities.Count != 2)
        throw new InvalidOperationException("Packed nested progress projection is incompatible.");

    var reference = new CodexPluginReference("id", "plugin", "marketplace");
    var skill = new CodexSkill("skill", "Skill", "Description", "skill.md", CodexSkillScope.Repo, true);
    if (reference.Uri != "plugin://plugin@marketplace" || skill.Origin != CodexResourceOrigin.Workspace)
        throw new InvalidOperationException("Packed derived immutable-value projection is incompatible.");

    if (!new CodexElicitationValidation([]).IsValid ||
        new CodexWorkspace("/workspace").DisplayName != "/workspace" ||
        new CodexFormOption("value").Title != "value")
        throw new InvalidOperationException("Packed canonical default-value projection is incompatible.");
}

static void VerifyResidualValues()
{
    var conversationId = new CodexConversationId("conversation");
    var invocation = new CodexInvocation.Skill("Skill", "skill.md");
    var message = new CodexMessage(
        "message", null, CodexMessageRole.User, "Hello",
        capabilities: [CodexCapability.WebSearch], invocations: [invocation]);
    var snapshot = new CodexConversationSnapshot(
        new CodexConversationSummary(conversationId, "Title", 1), [message]);
    var state = new CodexConversationState(
        CodexConversationStatus.Ready, conversationId, snapshot, new CodexTurnProgress());
    if (!state.CanStartTurn || state.CanCancelTurn || invocation.Key != "skill:skill.md")
        throw new InvalidOperationException("Packed conversation-value projection is incompatible.");

    var values = new CodexFormValue.TextList(["one", "one"]);
    var field = new CodexFormField(
        "field", "Field", CodexFormFieldType.MultiSelect,
        options: [new CodexFormOption("one")], defaultValue: values);
    var elicitation = new CodexElicitation("request", "server", conversationId, "Choose", [field]);
    var response = new CodexElicitationResponse(
        CodexElicitationAction.Accept,
        new Dictionary<string, CodexFormValue> { ["field"] = values });
    if (elicitation.Form?.Count != 1 || response.Content.Count != 1)
        throw new InvalidOperationException("Packed elicitation-value projection is incompatible.");

    var functionField = new CodexFormField(
        "name", "Name", CodexFormFieldType.String, isRequired: true,
        defaultValue: new CodexFormValue.Text("Codex"));
    var functionElicitation = new CodexElicitation(
        "function", "server", conversationId, "Complete", [functionField]);
    var validContent = new Dictionary<string, CodexFormValue>
    {
        ["name"] = new CodexFormValue.Text("Codex"),
    };
    var accepted = functionElicitation.Accept(validContent);
    if (!functionField.Accepts(validContent["name"]) ||
        functionElicitation.InitialValues().Count != 1 ||
        !functionElicitation.Validate(validContent).IsValid ||
        !functionElicitation.Accepts(accepted) ||
        CodexElicitationResponse.Cancel().Action != CodexElicitationAction.Cancel ||
        CodexElicitationResponse.Decline().Action != CodexElicitationAction.Decline)
        throw new InvalidOperationException("Packed elicitation-function projection is incompatible.");

    var pending = new CodexPendingApproval("pending", conversationId, "Approve", "Details");
    var interactions = new CodexInteractionState([pending], ["pending"]);
    if (!interactions.IsResolving(pending) || interactions.PendingFor(conversationId).Single() != pending)
        throw new InvalidOperationException("Packed interaction-function projection is incompatible.");

    var hook = new CodexHook(
        "hook", "hash", true, "event", CodexHookHandler.Prompt.Instance,
        false, "PLUGIN", "path", 1, CodexHookTrustStatus.Untrusted, pluginId: "plugin");
    if (!hook.CanTrust || hook.Origin != CodexResourceOrigin.Plugin)
        throw new InvalidOperationException("Packed hook-value projection is incompatible.");

    var connector = new CodexConnector("connector", "Connector");
    CodexIntegration integration = new CodexIntegration.Connector(connector);
    if (integration.Id != "connector" || integration.DisplayName != "Connector")
        throw new InvalidOperationException("Packed integration-value projection is incompatible.");

    var authorization = CodexAuthorizationUrl.ChatGpt("https://auth.openai.com/authorize");
    if (authorization.Purpose != CodexAuthorizationPurpose.ChatGpt ||
        CodexAuthorizationUrl.External("http://127.0.0.1/auth").Purpose != CodexAuthorizationPurpose.External ||
        new CodexAuthenticationMethod.ApiKey("secret").ToString() != "ApiKey(**redacted**)" ||
        CodexEnumMetadata.CapabilityId(CodexCapability.WebSearch) != "web_search" ||
        CodexHostState.New.Instance != CodexHostState.New.Instance)
        throw new InvalidOperationException("Packed metadata/object-value projection is incompatible.");
}

static void VerifyLeafServiceSurface()
{
    var capabilities = new (Type Type, string Member, Type? FirstParameter)[]
    {
        (typeof(CodexAuthentication), nameof(CodexAuthentication.AuthenticateAsync), null),
        (typeof(CodexAuthentication), nameof(CodexAuthentication.CancelAsync), null),
        (typeof(CodexAuthentication), nameof(CodexAuthentication.SignOutAsync), null),
        (typeof(CodexAuthentication), nameof(CodexAuthentication.IsAuthenticated), null),
        (typeof(CodexAuthentication), nameof(CodexAuthentication.IsAuthenticating), null),
        (typeof(CodexAuthentication), nameof(CodexAuthentication.State), null),
        (typeof(CodexConnectors), nameof(CodexConnectors.ListAsync), null),
        (typeof(CodexConnectors), nameof(CodexConnectors.IsAvailable), null),
        (typeof(CodexHooks), nameof(CodexHooks.InstallAsync), null),
        (typeof(CodexHooks), nameof(CodexHooks.ListAsync), null),
        (typeof(CodexHooks), nameof(CodexHooks.TrustAsync), null),
        (typeof(CodexHooks), nameof(CodexHooks.UninstallAsync), null),
        (typeof(CodexHooks), nameof(CodexHooks.IsAvailable), null),
        (typeof(CodexIntegrationAuthorization), nameof(CodexIntegrationAuthorization.AuthorizeAsync), null),
        (typeof(CodexIntegrationAuthorization), nameof(CodexIntegrationAuthorization.CancelAsync), null),
        (typeof(CodexIntegrationAuthorization), nameof(CodexIntegrationAuthorization.Active), null),
        (typeof(CodexIntegrationAuthorization), nameof(CodexIntegrationAuthorization.IsAuthorizing), null),
        (typeof(CodexIntegrationAuthorization), nameof(CodexIntegrationAuthorization.State), null),
        (typeof(CodexInteractions), nameof(CodexInteractions.OpenUrlAsync), null),
        (typeof(CodexInteractions), nameof(CodexInteractions.ResolveAsync), typeof(CodexPendingApproval)),
        (typeof(CodexInteractions), nameof(CodexInteractions.ResolveAsync), typeof(CodexPendingElicitation)),
        (typeof(CodexInteractions), nameof(CodexInteractions.Approvals), null),
        (typeof(CodexInteractions), nameof(CodexInteractions.Elicitations), null),
        (typeof(CodexInteractions), nameof(CodexInteractions.State), null),
        (typeof(CodexMcpServers), nameof(CodexMcpServers.AddAsync), null),
        (typeof(CodexMcpServers), nameof(CodexMcpServers.ListAsync), null),
        (typeof(CodexMcpServers), nameof(CodexMcpServers.RemoveAsync), null),
        (typeof(CodexMcpServers), nameof(CodexMcpServers.IsAvailable), null),
        (typeof(CodexModels), nameof(CodexModels.ListAsync), null),
        (typeof(CodexModels), nameof(CodexModels.ResolveEffortAsync), null),
        (typeof(CodexModels), nameof(CodexModels.ResolveServiceTierAsync), null),
        (typeof(CodexModels), nameof(CodexModels.ResolveAsync), null),
        (typeof(CodexPlugins), nameof(CodexPlugins.InstallAsync), null),
        (typeof(CodexPlugins), nameof(CodexPlugins.ListAsync), null),
        (typeof(CodexPlugins), nameof(CodexPlugins.ReadAsync), null),
        (typeof(CodexPlugins), nameof(CodexPlugins.UninstallAsync), null),
        (typeof(CodexPlugins), nameof(CodexPlugins.IsAvailable), null),
        (typeof(CodexSkills), nameof(CodexSkills.InstallAsync), null),
        (typeof(CodexSkills), nameof(CodexSkills.ListAsync), null),
        (typeof(CodexSkills), nameof(CodexSkills.ReadAsync), null),
        (typeof(CodexSkills), nameof(CodexSkills.UninstallAsync), null),
        (typeof(CodexSkills), nameof(CodexSkills.IsAvailable), null),
    };
    if (capabilities.Length != 42 || capabilities.Any(capability =>
        capability.Type.GetProperty(capability.Member) is null &&
        !capability.Type.GetMethods().Any(method => method.Name == capability.Member &&
            (capability.FirstParameter is null || method.GetParameters()[0].ParameterType == capability.FirstParameter))))
        throw new InvalidOperationException("Packed 42-capability leaf-service surface is incomplete.");
    if (capabilities.Select(capability => capability.Type).Distinct().Any(type =>
        !type.IsPublic || !type.IsSealed || !typeof(IDisposable).IsAssignableFrom(type) ||
        !typeof(IAsyncDisposable).IsAssignableFrom(type)))
        throw new InvalidOperationException("Packed leaf services do not expose deterministic ownership.");
}

static void VerifyConversationSurface()
{
    var capabilities = new (Type Type, string Member, Type? FirstParameter)[]
    {
        (typeof(CodexConversations), nameof(CodexConversations.DeleteAsync), null),
        (typeof(CodexConversations), nameof(CodexConversations.ListAsync), null),
        (typeof(CodexConversations), nameof(CodexConversations.OpenAsync), null),
        (typeof(CodexConversations), nameof(CodexConversations.ReadAsync), null),
        (typeof(CodexConversations), nameof(CodexConversations.RenameAsync), null),
        (typeof(CodexConversations), nameof(CodexConversations.ActiveConversation), null),
        (typeof(CodexConversations), nameof(CodexConversations.ObserveActiveConversationAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CancelTurnAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CloseAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.ReloadAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.RunShellCommandAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.SendAsync), typeof(CodexTurnRequest)),
        (typeof(CodexConversation), nameof(CodexConversation.SendAsync), typeof(string)),
        (typeof(CodexConversation), nameof(CodexConversation.ActiveTurnProgress), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveActiveTurnProgressAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CanCancelTurn), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveCanCancelTurnAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CanReload), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveCanReloadAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CanRunShellCommand), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveCanRunShellCommandAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CanStartTurn), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveCanStartTurnAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.CurrentMessages), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveCurrentMessagesAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.IsTurnActive), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveIsTurnActiveAsync), null),
        (typeof(CodexConversation), nameof(CodexConversation.State), null),
        (typeof(CodexConversation), nameof(CodexConversation.ObserveStatesAsync), null),
    };
    if (capabilities.Length != 29 || capabilities.Any(capability =>
        capability.Type.GetProperty(capability.Member) is null &&
        !capability.Type.GetMethods().Any(method => method.Name == capability.Member &&
            (capability.FirstParameter is null || method.GetParameters()[0].ParameterType == capability.FirstParameter))))
        throw new InvalidOperationException("Packed 20-capability conversation surface is incomplete.");

    var request = new CodexTurnRequest(
        "consumer", "client", "model", "high", "fast", CodexApprovalPreset.AskMe,
        [CodexCapability.WebSearch],
        [new CodexInvocation.Plugin("plugin", "plugin://plugin@market"), new CodexInvocation.Skill("skill", "skill.md")],
        CodexCollaborationMode.Plan);
    if (request.Invocations.Count != 2 || request.Capabilities.Count != 1)
        throw new InvalidOperationException("Packed structured conversation input is incompatible.");
}

static void VerifyAgentSurface()
{
    var properties = new[]
    {
        nameof(CodexAgent.CodexAgent.Authentication),
        nameof(CodexAgent.CodexAgent.Connectors),
        nameof(CodexAgent.CodexAgent.Conversations),
        nameof(CodexAgent.CodexAgent.Hooks),
        nameof(CodexAgent.CodexAgent.IntegrationAuthorization),
        nameof(CodexAgent.CodexAgent.Interactions),
        nameof(CodexAgent.CodexAgent.McpServers),
        nameof(CodexAgent.CodexAgent.Models),
        nameof(CodexAgent.CodexAgent.Plugins),
        nameof(CodexAgent.CodexAgent.Skills),
        nameof(CodexAgent.CodexAgent.Workspace),
    };
    if (properties.Length != 11 || properties.Any(name =>
        typeof(CodexAgent.CodexAgent).GetProperty(name)?.GetMethod is not { IsPublic: true }))
        throw new InvalidOperationException("Packed 11-capability Agent surface is incomplete.");
}

static void VerifyHostSurface()
{
    var readyType = typeof(CodexHostState.Ready);
    var capabilities = new Func<bool>[]
    {
        () => readyType.GetConstructors().SingleOrDefault()?.GetParameters() is [{ ParameterType: var type }] &&
            type == typeof(CodexAgent.CodexAgent),
        () => readyType.GetProperty(nameof(CodexHostState.Ready.Agent))?.GetMethod is { IsPublic: true },
        () => typeof(CodexHost).GetMethod(nameof(CodexHost.Create)) is { IsPublic: true, IsStatic: true },
        () => typeof(CodexHost).GetMethod(nameof(CodexHost.CloseAsync)) is { IsPublic: true },
        () => typeof(CodexHost).GetMethod(nameof(CodexHost.SelectWorkspaceAsync)) is { IsPublic: true },
        () => typeof(CodexHost).GetMethod(nameof(CodexHost.StartAsync)) is { IsPublic: true },
        () => typeof(CodexHost).GetProperty(nameof(CodexHost.State))?.GetMethod is { IsPublic: true } &&
            typeof(CodexHost).GetMethod(nameof(CodexHost.ObserveStatesAsync)) is { IsPublic: true },
    };
    if (capabilities.Length != 7 || capabilities.Any(capability => !capability()) ||
        !typeof(IDisposable).IsAssignableFrom(typeof(CodexHost)) ||
        !typeof(IAsyncDisposable).IsAssignableFrom(typeof(CodexHost)))
        throw new InvalidOperationException("Packed seven-capability Host/Ready surface is incomplete.");
}

if (args.Length is < 1 or > 2) throw new ArgumentException("Usage: <native-library> [lifecycle|release-only]");
CodexNativeLibrary.Configure(args[0]);
if (CodexResolution.Preferred != 0 || CodexFormFieldType.MultiSelect != (CodexFormFieldType)5)
    throw new InvalidOperationException("Packed ordinary enum projection is incompatible with the C SDK.");
VerifyMcpValues();
VerifyOrdinaryValues();
VerifyResidualValues();
VerifyLeafServiceSurface();
VerifyConversationSurface();
VerifyAgentSurface();
VerifyHostSurface();
var mode = args.ElementAtOrDefault(1) ?? "lifecycle";
var options = new CodexHostOptions(
    "/verified/bundle",
    "/tmp/codex-agent-dotnet-consumer",
    new CodexClientInfo("consumer", ".NET consumer", "1.0"));
var host = CodexHost.Create(options);

await RequireOpenDisposeRejected(host.Dispose);

if (mode == "lifecycle")
{
    await host.StartAsync();
    var agent = host.State.Agent ?? throw new InvalidOperationException("Host did not become ready.");
    var ready = new CodexHostState.Ready(agent);
    if (!ReferenceEquals(ready.Agent, agent) || !ReferenceEquals(host.State.Agent, agent))
        throw new InvalidOperationException("Packed READY Agent identity is incompatible.");
    await using (var states = host.ObserveStatesAsync().GetAsyncEnumerator())
    {
        if (!await states.MoveNextAsync() || !ReferenceEquals(states.Current.Agent, agent))
            throw new InvalidOperationException("Packed Host state stream is incompatible.");
    }
    await host.SelectWorkspaceAsync("/consumer-workspace");
    var conversation = await agent.Conversations.OpenAsync();
    await conversation.SendAsync("Hello from the packed package");
    var firstConversationDispose = conversation.DisposeAsync().AsTask();
    var secondConversationDispose = conversation.DisposeAsync().AsTask();
    if (!ReferenceEquals(firstConversationDispose, secondConversationDispose))
        throw new InvalidOperationException("Conversation disposal did not coalesce.");
    await Task.WhenAll(firstConversationDispose, secondConversationDispose);
    await host.CloseAsync();
}
else if (mode != "release-only")
{
    throw new ArgumentException($"Unknown consumer mode: {mode}");
}

var firstHostDispose = host.DisposeAsync().AsTask();
var secondHostDispose = host.DisposeAsync().AsTask();
if (!ReferenceEquals(firstHostDispose, secondHostDispose))
    throw new InvalidOperationException("Host disposal did not coalesce.");
await Task.WhenAll(firstHostDispose, secondHostDispose);
Console.WriteLine($"CodexAgent packed consumer passed on {CodexNativeLibrary.RuntimeIdentifier} ({mode}).");
