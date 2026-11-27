using CodexAgent;
using CodexAgent.Interop;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;

internal static class LeafServiceParity
{
    private const string Prefix = "csharp.leaf:";
    private static readonly IReadOnlyDictionary<string, string> CapabilityIds = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["CodexAuthentication.authenticate"]="000", ["CodexAuthentication.cancel"]="001", ["CodexAuthentication.signOut"]="002",
        ["CodexAuthentication.isAuthenticated"]="003", ["CodexAuthentication.isAuthenticating"]="004", ["CodexAuthentication.state"]="005",
        ["CodexConnectors.list"]="006", ["CodexConnectors.isAvailable"]="007",
        ["CodexHooks.install"]="008", ["CodexHooks.list"]="009", ["CodexHooks.trust"]="010", ["CodexHooks.uninstall"]="011", ["CodexHooks.isAvailable"]="012",
        ["CodexIntegrationAuthorization.authorize"]="013", ["CodexIntegrationAuthorization.cancel"]="014", ["CodexIntegrationAuthorization.active"]="015",
        ["CodexIntegrationAuthorization.isAuthorizing"]="016", ["CodexIntegrationAuthorization.state"]="017",
        ["CodexInteractions.openUrl"]="018", ["CodexInteractions.resolveApproval"]="019", ["CodexInteractions.resolveElicitation"]="020",
        ["CodexInteractions.approvals"]="021", ["CodexInteractions.elicitations"]="022", ["CodexInteractions.state"]="023",
        ["CodexMcpServers.add"]="024", ["CodexMcpServers.list"]="025", ["CodexMcpServers.remove"]="026", ["CodexMcpServers.isAvailable"]="027",
        ["CodexModels.list"]="028", ["CodexModels.resolveEffort"]="029", ["CodexModels.resolveServiceTier"]="030", ["CodexModels.resolve"]="031",
        ["CodexPlugins.install"]="032", ["CodexPlugins.list"]="033", ["CodexPlugins.read"]="034", ["CodexPlugins.uninstall"]="035", ["CodexPlugins.isAvailable"]="036",
        ["CodexSkills.install"]="037", ["CodexSkills.list"]="038", ["CodexSkills.read"]="039", ["CodexSkills.uninstall"]="040", ["CodexSkills.isAvailable"]="041",
    };
    private static readonly string[] Owners =
    [
        "CodexAuthentication", "CodexConnectors", "CodexHooks", "CodexIntegrationAuthorization",
        "CodexInteractions", "CodexMcpServers", "CodexModels", "CodexPlugins", "CodexSkills",
    ];

    internal static void VerifyContract(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        var claims = allClaims.Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();
        var canonical = canonicalCapabilities.Where(capability => Owners.Any(owner =>
            capability.StartsWith($"common|owner=io.github.codex_agent_labs.codexagent.agent/{owner}|", StringComparison.Ordinal))).ToHashSet(StringComparer.Ordinal);
        Require(claims.Length == 42 && canonical.Count == 42 && canonical.SetEquals(claims.Select(row => row[0])),
            "leaf claims exactly match the canonical 42-capability closure");
        Require(claims.Select(row => row[2]).SequenceEqual(Enumerable.Range(0, 42).Select(index => $"{Prefix}{index:000}")),
            "leaf executed-test IDs are exact and stable");
        McpValueParity.VerifyEvidenceReferences(claims);
        foreach (var row in claims)
        {
            var publicMethods = ResolvePublicMethods(row);
            var entryPoints = row[3].Split(',').Where(value => value.StartsWith("c-header:codex_agent_", StringComparison.Ordinal))
                .Select(value => value["c-header:".Length..]).ToArray();
            SynchronousValueFunctionParity.ValidateLeafProductionConnection(publicMethods, entryPoints, row[2]);
        }
        VerifyNegativeEvidence(claims);
    }

    internal static async Task VerifyManaged(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyAuthentication(agent, executed);
        await VerifyConnectors(agent, executed);
        await VerifyHooks(agent, executed);
        await VerifyIntegrationAuthorization(agent, executed);
        await VerifyInteractions(agent, executed);
        await VerifyMcpServers(agent, executed);
        await VerifyModels(agent, executed);
        await VerifyPlugins(agent, executed);
        await VerifySkills(agent, executed);
        Console.WriteLine("CodexAgent C# native-backed leaf service tests passed: 42/42.");
    }

    internal static void VerifyNative(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        VerifyContract(allClaims, canonicalCapabilities);
        var claims = allClaims.Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();
        var receipts = new List<string>();
        foreach (var row in claims)
        {
            foreach (var entryPoint in HeaderEntryPoints(row))
            {
                Require(InvokeInvalidBoundary(entryPoint) != CodexStatus.Ok,
                    $"{row[2]}: real SDK rejects null leaf boundary for {entryPoint}");
                receipts.Add($"{row[2]}\t{entryPoint}\tpassed");
            }
        }
        Require(receipts.Count == 112, "real SDK executes all 112 per-capability C-header references");
        Require(receipts.Select(line => line.Split('\t')[1]).Distinct(StringComparer.Ordinal).Count() == 83,
            "real SDK executes all 83 unique C-header symbols");
        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "leaf-native-tests.tsv"),
            string.Join('\n', new[] { "executedTestId\tnativeSymbol\tstatus" }.Concat(receipts)) + "\n");
        Console.WriteLine("CodexAgent C# real C ABI leaf-service boundary tests passed: 42 capabilities, 83 symbols, 112 references.");
    }

    internal static void ImportNativeEvidence(IReadOnlyList<string[]> allClaims)
    {
        var claims = allClaims.Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();
        var path = Path.Combine(AppContext.BaseDirectory, "artifacts", "leaf-native-tests.tsv");
        Require(File.Exists(path), "real-SDK leaf-service evidence exists");
        var lines = File.ReadAllLines(path);
        Require(lines.Length == 113 && lines[0] == "executedTestId\tnativeSymbol\tstatus",
            "real-SDK leaf-service evidence has exact shape");
        var receipts = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
        Require(receipts.All(row => row.Length == 3 && row[2] == "passed"), "every real-SDK leaf-service receipt passed");
        var expected = claims.SelectMany(row => HeaderEntryPoints(row).Select(entryPoint => (TestId: row[2], EntryPoint: entryPoint))).ToArray();
        Require(expected.Length == 112 && expected.Select(item => item.EntryPoint).Distinct(StringComparer.Ordinal).Count() == 83,
            "claims contain exact 112 references to 83 unique C-header symbols");
        Require(receipts.Select(row => (TestId: row[0], EntryPoint: row[1])).SequenceEqual(expected),
            "real-SDK leaf-service receipts exactly match every capability/header reference");
    }

    private static async Task VerifyAuthentication(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyState(() => agent.OpenAuthentication(), service => service.State, service => service.ObserveStateAsync(),
            value => value.Status == CodexAuthenticationStatus.SignedOut,
            value => value.Status == CodexAuthenticationStatus.Authenticated, "authentication state");
        Mark(executed, "CodexAuthentication.state");
        await VerifyState(() => agent.OpenAuthentication(), service => service.IsAuthenticated, service => service.ObserveIsAuthenticatedAsync(),
            value => value, value => !value, "authenticated Boolean");
        Mark(executed, "CodexAuthentication.isAuthenticated");
        await VerifyState(() => agent.OpenAuthentication(), service => service.IsAuthenticating, service => service.ObserveIsAuthenticatingAsync(),
            value => !value, value => value, "authenticating Boolean");
        Mark(executed, "CodexAuthentication.isAuthenticating");
        await CompleteOwned(agent.OpenAuthentication(), service => service.AuthenticateAsync(new CodexAuthenticationMethod.ApiKey("secret")), "API-key authentication");
        await CompleteOwned(agent.OpenAuthentication(), service => service.AuthenticateAsync(CodexAuthenticationMethod.ChatGptBrowser.Instance), "browser authentication");
        await CompleteOwned(agent.OpenAuthentication(), service => service.AuthenticateAsync(CodexAuthenticationMethod.ChatGptDeviceCode.Instance), "device authentication");
        await ExpectInputRejected(agent.OpenAuthentication(),
            service => service.AuthenticateAsync(new CodexAuthenticationMethod.ApiKey("wrong")), "authentication copied API key");
        Mark(executed, "CodexAuthentication.authenticate");
        await CompleteOwned(agent.OpenAuthentication(), service => service.CancelAsync(), "authentication cancellation");
        Mark(executed, "CodexAuthentication.cancel");
        await CompleteOwned(agent.OpenAuthentication(), service => service.SignOutAsync(), "authentication sign out");
        Mark(executed, "CodexAuthentication.signOut");
    }

    private static async Task VerifyConnectors(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyAvailable(agent.OpenConnectors(), service => service.IsAvailable, "connector availability");
        Mark(executed, "CodexConnectors.isAvailable");
        var connectors = await CompleteOwned(agent.OpenConnectors(), service => service.ListAsync(forceReload: true), "connector list");
        RequireOrderedImmutable(connectors, value => value.Id, "connector-alpha", "connector-beta", "connector list");
        await ExpectInputRejected(agent.OpenConnectors(), service => service.ListAsync(forceReload: false), "connector list force-reload flag");
        Mark(executed, "CodexConnectors.list");
    }

    private static async Task VerifyHooks(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var hook = InputHook();
        await VerifyAvailable(agent.OpenHooks(), service => service.IsAvailable, "hook availability");
        Mark(executed, "CodexHooks.isAvailable");
        var catalog = await CompleteOwned(agent.OpenHooks(), service => service.ListAsync(), "hook list");
        Require(catalog.Hooks.Count == 0 && catalog.Warnings is ["native hook warning"] && catalog.Errors is ["native hook error"],
            "hook catalog projects typed native values");
        Mark(executed, "CodexHooks.list");
        var installed = await CompleteOwned(agent.OpenHooks(), service => service.InstallAsync("/hook", CodexInstallationScope.User), "hook install");
        Require(installed.Key == "native-hook" && installed.Handler is CodexHookHandler.Agent, "hook install projects typed native value");
        await ExpectInputRejected(agent.OpenHooks(), service => service.InstallAsync("/wrong", CodexInstallationScope.Workspace),
            "hook install copied directory and scope");
        Mark(executed, "CodexHooks.install");
        await CompleteOwned(agent.OpenHooks(), service => service.TrustAsync(hook), "hook trust");
        await ExpectInputRejected(agent.OpenHooks(), service => service.TrustAsync(InputHook(sourcePath: "/wrong")),
            "hook trust copied exact hook");
        Mark(executed, "CodexHooks.trust");
        await CompleteOwned(agent.OpenHooks(), service => service.UninstallAsync(hook), "hook uninstall");
        await ExpectInputRejected(agent.OpenHooks(), service => service.UninstallAsync(InputHook(timeoutSeconds: 10)),
            "hook uninstall copied exact hook");
        Mark(executed, "CodexHooks.uninstall");
    }

    private static async Task VerifyIntegrationAuthorization(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyState(() => agent.OpenIntegrationAuthorization(), service => service.State, service => service.ObserveStateAsync(),
            value => value.Status == CodexIntegrationAuthorizationStatus.Idle,
            value => value.Status == CodexIntegrationAuthorizationStatus.Authorized, "integration state");
        Mark(executed, "CodexIntegrationAuthorization.state");
        await VerifyState(() => agent.OpenIntegrationAuthorization(), service => service.Active, service => service.ObserveActiveAsync(),
            value => value is null,
            value => value is CodexIntegration.Connector { ConnectorValue.Id: "connector-alpha" }, "active integration nullability");
        Mark(executed, "CodexIntegrationAuthorization.active");
        await VerifyState(() => agent.OpenIntegrationAuthorization(), service => service.IsAuthorizing, service => service.ObserveIsAuthorizingAsync(),
            value => !value, value => value, "integration authorizing Boolean");
        Mark(executed, "CodexIntegrationAuthorization.isAuthorizing");
        var target = new CodexIntegration.Connector(InputConnector());
        await CompleteOwned(agent.OpenIntegrationAuthorization(), service => service.AuthorizeAsync(target), "integration authorize");
        await ExpectInputRejected(agent.OpenIntegrationAuthorization(),
            service => service.AuthorizeAsync(new CodexIntegration.Connector(InputConnector(id: "wrong"))),
            "integration authorize copied nested connector");
        Mark(executed, "CodexIntegrationAuthorization.authorize");
        await CompleteOwned(agent.OpenIntegrationAuthorization(), service => service.CancelAsync(), "integration cancel");
        Mark(executed, "CodexIntegrationAuthorization.cancel");
    }

    private static async Task VerifyInteractions(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyState(() => agent.OpenInteractions(), service => service.State, service => service.ObserveStateAsync(),
            value => value.Pending is [{ RequestId: "approval-first" }],
            value => value.Pending is [{ RequestId: "approval-first" }, { RequestId: "elicitation-second" }],
            "interaction state");
        var stateIdentityService = agent.OpenInteractions();
        var stateApproval = stateIdentityService.State.Pending.Single() as CodexPendingApproval ??
            throw new InvalidOperationException("interaction state did not project pending approval identity");
        var copiedStateApproval = new CodexPendingApproval(
            stateApproval.RequestId, stateApproval.ConversationId, stateApproval.Title, stateApproval.Details);
        await ExpectUnowned(() => stateIdentityService.ResolveAsync(copiedStateApproval, CodexApprovalDecision.Accept),
            "interaction-state pending identity");
        await CompleteOwned(stateIdentityService,
            service => service.ResolveAsync(stateApproval, CodexApprovalDecision.Accept),
            "interaction-state pending native identity");
        Mark(executed, "CodexInteractions.state");
        await VerifyState(() => agent.OpenInteractions(), service => service.Approvals, service => service.ObserveApprovalsAsync(),
            value => IsOrderedImmutable(value, item => item.RequestId, "approval-first", "approval-second"),
            value => value is [{ RequestId: "approval-first" }, { RequestId: "approval-second" }],
            "approval collection");
        Mark(executed, "CodexInteractions.approvals");
        await VerifyState(() => agent.OpenInteractions(), service => service.Elicitations, service => service.ObserveElicitationsAsync(),
            value => IsOrderedImmutable(value, item => item.RequestId, "elicitation-first", "elicitation-second"),
            value => value is [{ RequestId: "elicitation-first" }, { RequestId: "elicitation-second" }],
            "elicitation collection");
        Mark(executed, "CodexInteractions.elicitations");

        var approvalService = agent.OpenInteractions();
        var approval = approvalService.Approvals[0];
        var unownedApproval = new CodexPendingApproval(approval.RequestId, approval.ConversationId, approval.Title, approval.Details);
        await ExpectUnowned(() => approvalService.ResolveAsync(unownedApproval, CodexApprovalDecision.Accept), "approval identity");
        await CompleteOwned(approvalService, service => service.ResolveAsync(approval, CodexApprovalDecision.Accept), "approval resolution");
        var wrongDecisionService = agent.OpenInteractions();
        var wrongDecisionApproval = wrongDecisionService.Approvals[0];
        await ExpectInputRejected(wrongDecisionService,
            service => service.ResolveAsync(wrongDecisionApproval, CodexApprovalDecision.Decline),
            "approval copied decision");
        var cancelApprovalService = agent.OpenInteractions();
        var cancelApproval = cancelApprovalService.Approvals[1];
        await CancelOwned(cancelApprovalService,
            (service, cancellation) => service.ResolveAsync(cancelApproval, CodexApprovalDecision.Accept, cancellation), "approval cancellation");
        Mark(executed, "CodexInteractions.resolveApproval");

        var elicitationService = agent.OpenInteractions();
        var elicitation = elicitationService.Elicitations[0];
        var equalElicitation = new CodexPendingElicitation(elicitation.Elicitation);
        var response = InputElicitationResponse();
        await ExpectUnowned(() => elicitationService.ResolveAsync(equalElicitation, response), "elicitation identity");
        await CompleteOwned(elicitationService, service => service.ResolveAsync(elicitation, response), "elicitation resolution");
        var wrongResponseService = agent.OpenInteractions();
        var wrongResponseElicitation = wrongResponseService.Elicitations[0];
        await ExpectInputRejected(wrongResponseService,
            service => service.ResolveAsync(wrongResponseElicitation, new CodexElicitationResponse(CodexElicitationAction.Decline)),
            "elicitation copied action and content");
        var cancelElicitationService = agent.OpenInteractions();
        var cancelElicitation = cancelElicitationService.Elicitations[1];
        await CancelOwned(cancelElicitationService,
            (service, cancellation) => service.ResolveAsync(cancelElicitation, response, cancellation), "elicitation cancellation");
        Mark(executed, "CodexInteractions.resolveElicitation");

        var urlService = agent.OpenInteractions();
        var urlElicitations = urlService.Elicitations;
        var unownedUrl = new CodexPendingElicitation(urlElicitations[0].Elicitation);
        await ExpectUnowned(() => urlService.OpenUrlAsync(unownedUrl), "URL identity");
        await CompleteOwned(urlService, service => service.OpenUrlAsync(urlElicitations[0]), "interaction URL success");
        var cancelUrlService = agent.OpenInteractions();
        var cancelUrl = cancelUrlService.Elicitations[1];
        await CancelOwned(cancelUrlService, (service, cancellation) => service.OpenUrlAsync(cancelUrl, cancellation), "URL cancellation");
        await using var failureUrlService = agent.OpenInteractions();
        await ExpectOperationFailure(failureUrlService.OpenUrlAsync(failureUrlService.Elicitations[2]), "interaction URL structured failure");
        Mark(executed, "CodexInteractions.openUrl");
    }

    private static async Task VerifyMcpServers(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        await VerifyAvailable(agent.OpenMcpServers(), service => service.IsAvailable, "MCP availability");
        Mark(executed, "CodexMcpServers.isAvailable");
        var servers = await CompleteOwned(agent.OpenMcpServers(), service => service.ListAsync(), "MCP list");
        RequireOrderedImmutable(servers, value => value.Name, "server-alpha", "server-beta", "MCP list");
        Mark(executed, "CodexMcpServers.list");
        var configuration = InputMcpConfiguration();
        var added = await CompleteOwned(agent.OpenMcpServers(), service => service.AddAsync(configuration), "MCP add");
        Require(added.Name == "server-alpha" && added.Configuration is null && !added.IsAuthorized, "MCP add projects typed nullable server");
        await ExpectInputRejected(agent.OpenMcpServers(),
            service => service.AddAsync(InputMcpConfiguration(name: "wrong")),
            "MCP add copied exact nested configuration");
        Mark(executed, "CodexMcpServers.add");
        var server = InputMcpServer();
        await CompleteOwned(agent.OpenMcpServers(), service => service.RemoveAsync(server), "MCP remove");
        await ExpectInputRejected(agent.OpenMcpServers(),
            service => service.RemoveAsync(InputMcpServer(canRemove: false)), "MCP remove copied exact server");
        Mark(executed, "CodexMcpServers.remove");
    }

    private static async Task VerifyModels(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var model = InputModel();
        var models = await CompleteOwned(agent.OpenModels(), service => service.ListAsync(), "model list");
        RequireOrderedImmutable(models, value => value.Id, "model-alpha", "model-beta", "model list");
        Require(models[0].SupportedEfforts is ["low", "medium"], "model list decodes nested efforts");
        Mark(executed, "CodexModels.list");
        var resolved = await CompleteOwned(agent.OpenModels(), service => service.ResolveAsync(CodexResolution.Preferred), "model resolve");
        Require(resolved.Id == "model-alpha" && resolved.IsDefault, "model resolve projects typed native model");
        await ExpectInputRejected(agent.OpenModels(), service => service.ResolveAsync(CodexResolution.Default),
            "model resolve copied resolution enum");
        Mark(executed, "CodexModels.resolve");
        var effort = await CompleteOwned(agent.OpenModels(), service => service.ResolveEffortAsync(model), "effort resolve");
        Require(effort == "medium", "effort resolve projects native string");
        await ExpectInputRejected(agent.OpenModels(), service => service.ResolveEffortAsync(InputModel(id: "wrong")),
            "effort resolve copied model collection and fields");
        Mark(executed, "CodexModels.resolveEffort");
        var tier = await CompleteOwned(agent.OpenModels(), service => service.ResolveServiceTierAsync(model), "service-tier resolve present");
        Require(tier is { Id: "fast", Name: "Fast" }, "service-tier resolve projects present value");
        var absent = await CompleteOwned(agent.OpenModels(), service => service.ResolveServiceTierAsync(model, CodexResolution.First), "service-tier resolve absent");
        Require(absent is null, "service-tier resolve projects null value");
        await ExpectInputRejected(agent.OpenModels(),
            service => service.ResolveServiceTierAsync(model, CodexResolution.Default),
            "service-tier resolve copied resolution enum");
        Mark(executed, "CodexModels.resolveServiceTier");
    }

    private static async Task VerifyPlugins(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var plugin = InputPluginReference();
        await VerifyAvailable(agent.OpenPlugins(), service => service.IsAvailable, "plugin availability");
        Mark(executed, "CodexPlugins.isAvailable");
        var catalog = await CompleteOwned(agent.OpenPlugins(), service => service.ListAsync(forceReload: true), "plugin list");
        Require(catalog.Plugins is [{ DisplayName: "Native Plugin" }] && catalog.Errors is ["native plugin warning"],
            "plugin list projects typed catalog");
        await ExpectInputRejected(agent.OpenPlugins(), service => service.ListAsync(forceReload: false),
            "plugin list copied force-reload flag");
        Mark(executed, "CodexPlugins.list");
        var detail = await CompleteOwned(agent.OpenPlugins(), service => service.ReadAsync(plugin), "plugin read");
        Require(detail.Summary.DisplayName == "Native Plugin" && detail.Description == "native plugin detail", "plugin read projects typed detail");
        await ExpectInputRejected(agent.OpenPlugins(), service => service.ReadAsync(InputPluginReference(id: "wrong")),
            "plugin read copied exact reference");
        Mark(executed, "CodexPlugins.read");
        var install = await CompleteOwned(agent.OpenPlugins(), service => service.InstallAsync(plugin), "plugin install");
        Require(install.ConnectorsNeedingAuthentication is [{ Id: "connector-alpha" }] && install.Message == "installed", "plugin install projects typed result");
        await ExpectInputRejected(agent.OpenPlugins(), service => service.InstallAsync(InputPluginReference(remotePluginId: "wrong")),
            "plugin install copied exact reference");
        Mark(executed, "CodexPlugins.install");
        await CompleteOwned(agent.OpenPlugins(), service => service.UninstallAsync(plugin), "plugin uninstall");
        await ExpectInputRejected(agent.OpenPlugins(), service => service.UninstallAsync(InputPluginReference(marketplacePath: "/wrong")),
            "plugin uninstall copied exact reference");
        Mark(executed, "CodexPlugins.uninstall");
    }

    private static async Task VerifySkills(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var skill = InputSkill();
        await VerifyAvailable(agent.OpenSkills(), service => service.IsAvailable, "skill availability");
        Mark(executed, "CodexSkills.isAvailable");
        var catalog = await CompleteOwned(agent.OpenSkills(), service => service.ListAsync(forceReload: true), "skill list");
        Require(catalog.Skills is [{ Name: "skill" }] && catalog.Errors is ["native skill warning"], "skill list projects typed catalog");
        await ExpectInputRejected(agent.OpenSkills(), service => service.ListAsync(forceReload: false),
            "skill list copied force-reload flag");
        Mark(executed, "CodexSkills.list");
        var chunk = await CompleteOwned(agent.OpenSkills(), service => service.ReadAsync("/skill", 7), "skill read");
        Require(chunk.Content == "native skill content" && chunk.NextOffset == 27 && chunk.TotalBytes == 42, "skill read projects typed chunk");
        await ExpectInputRejected(agent.OpenSkills(), service => service.ReadAsync("/wrong", 8),
            "skill read copied path and offset");
        Mark(executed, "CodexSkills.read");
        var installed = await CompleteOwned(agent.OpenSkills(), service => service.InstallAsync("/skill", CodexInstallationScope.User), "skill install");
        Require(installed.Name == "skill" && installed.Dependencies is ["dep-one", "dep-two"], "skill install projects typed value");
        await ExpectInputRejected(agent.OpenSkills(), service => service.InstallAsync("/wrong", CodexInstallationScope.Workspace),
            "skill install copied directory and scope");
        Mark(executed, "CodexSkills.install");
        await CompleteOwned(agent.OpenSkills(), service => service.UninstallAsync(skill), "skill uninstall");
        await ExpectInputRejected(agent.OpenSkills(), service => service.UninstallAsync(InputSkill(name: "wrong")),
            "skill uninstall copied exact skill");
        Mark(executed, "CodexSkills.uninstall");
    }

    private static CodexModel InputModel(string id = "input-model") => new(
        id, "Input Model", "input description", ["low", "medium", "low"], "medium", true);

    private static CodexSkill InputSkill(string name = "input-skill") => new(
        name, "Input Skill", "input skill description", "/input/skill", CodexSkillScope.User, true,
        "#123456", ["dep-one", "dep-two", "dep-one"], true, CodexResourceOrigin.User);

    private static CodexPluginReference InputPluginReference(
        string id = "input-plugin",
        string marketplacePath = "/input/marketplace",
        string remotePluginId = "input-remote") =>
        new(id, "input-name", "input-marketplace", marketplacePath, remotePluginId);

    private static CodexConnector InputConnector(string id = "input-connector") => new(
        id, "Input Connector", "input connector description", "https://example.invalid/install",
        isAccessible: true, isEnabled: false, ["plugin-one", "plugin-two", "plugin-one"]);

    private static CodexHook InputHook(string sourcePath = "/input/hook", long timeoutSeconds = 9) => new(
        "input-hook", "input-hash", true, "input-event", CodexHookHandler.Agent.Instance, false,
        "USER", sourcePath, timeoutSeconds, CodexHookTrustStatus.Untrusted, "*.kt", "plugin-id", "status",
        CodexResourceOrigin.User, true);

    private static CodexElicitationResponse InputElicitationResponse() => new(
        CodexElicitationAction.Accept,
        new Dictionary<string, CodexFormValue>(StringComparer.Ordinal)
        {
            ["answer"] = new CodexFormValue.Text("accepted"),
        });

    private static CodexMcpServerConfiguration InputMcpConfiguration(string name = "input-server") => new(
        name,
        new CodexMcpTransport.Http(
            "https://example.invalid/mcp",
            "TOKEN",
            new Dictionary<string, string>(StringComparer.Ordinal) { ["X-One"] = "one", ["X-Two"] = "two" },
            new Dictionary<string, string>(StringComparer.Ordinal) { ["Authorization"] = "AUTH" },
            "helper"),
        CodexMcpAuthentication.Oauth,
        "local",
        isEnabled: false,
        isRequired: true,
        supportsParallelToolCalls: true,
        [CodexMcpToolExposureSurface.CodeMode, CodexMcpToolExposureSurface.Deferred, CodexMcpToolExposureSurface.CodeMode],
        startupTimeoutSeconds: 1.5,
        toolTimeoutSeconds: 2.5,
        CodexMcpToolApproval.Writes,
        ["search", "fetch", "search"],
        ["delete"],
        ["files.read", "files.write", "files.read"],
        oauthResource: "resource");

    private static CodexMcpServer InputMcpServer(bool canRemove = true) => new(
        "remove-server", "Remove Server", CodexMcpAuthStatus.Oauth, origin: CodexResourceOrigin.User,
        canRemove: canRemove);

    private static async Task VerifyState<TService, T>(
        Func<TService> create,
        Func<TService, T> current,
        Func<TService, IAsyncEnumerable<T>> observe,
        Func<T, bool> currentPredicate,
        Func<T, bool> subsequentPredicate,
        string description)
        where TService : IDisposable, IAsyncDisposable
    {
        var service = create();
        Require(currentPredicate(current(service)), $"{description} current value");
        await using (var enumerator = observe(service).GetAsyncEnumerator())
        {
            Require(await enumerator.MoveNextAsync() && currentPredicate(enumerator.Current), $"{description} subscription current value");
            service.Dispose();
            service.Dispose();
            Require(await enumerator.MoveNextAsync() && subsequentPredicate(enumerator.Current), $"{description} subsequent value");
            Require(!await enumerator.MoveNextAsync(), $"{description} terminal delivery");
        }
        await service.DisposeAsync();

        var cancelledService = create();
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await using var cancelled = observe(cancelledService).GetAsyncEnumerator(cancellation.Token);
        try
        {
            await cancelled.MoveNextAsync();
            throw new InvalidOperationException($"{description} ignored subscription cancellation");
        }
        catch (OperationCanceledException) { }
        cancelledService.Dispose();
        cancelledService.Dispose();
        await cancelledService.DisposeAsync();
    }

    private static async Task VerifyAvailable<TService>(TService service, Func<TService, bool> read, string description)
        where TService : IDisposable, IAsyncDisposable
    {
        Require(read(service), description);
        service.Dispose();
        service.Dispose();
        await service.DisposeAsync();
    }

    private static async Task CompleteOwned<TService>(TService service, Func<TService, Task> start, string description)
        where TService : IDisposable, IAsyncDisposable
    {
        var operation = start(service);
        service.Dispose();
        service.Dispose();
        Require(NativeTestCompleteLeafOperation(0) == CodexStatus.Ok, $"{description} completes through fake native callback");
        await operation;
        await service.DisposeAsync();
    }

    private static async Task<T> CompleteOwned<TService, T>(TService service, Func<TService, Task<T>> start, string description)
        where TService : IDisposable, IAsyncDisposable
    {
        var operation = start(service);
        service.Dispose();
        service.Dispose();
        Require(NativeTestCompleteLeafOperation(0) == CodexStatus.Ok, $"{description} completes through fake native callback");
        var value = await operation;
        await service.DisposeAsync();
        return value;
    }

    private static async Task CancelOwned<TService>(
        TService service,
        Func<TService, CancellationToken, Task> start,
        string description)
        where TService : IDisposable, IAsyncDisposable
    {
        using var cancellation = new CancellationTokenSource();
        var operation = start(service, cancellation.Token);
        service.Dispose();
        service.Dispose();
        cancellation.Cancel();
        try { await operation; throw new InvalidOperationException($"{description} unexpectedly succeeded"); }
        catch (OperationCanceledException) { }
        await service.DisposeAsync();
    }

    private static void RequireOrderedImmutable<T>(IReadOnlyList<T> values, Func<T, string> key, string first, string second, string description) =>
        Require(IsOrderedImmutable(values, key, first, second), $"{description} preserves immutable ordered duplicate collection");

    private static bool IsOrderedImmutable<T>(IReadOnlyList<T> values, Func<T, string> key, string first, string second)
    {
        if (values.Count != 3 || key(values[0]) != first || key(values[1]) != second || key(values[2]) != first) return false;
        if (values is not IList<T> list) return true;
        try { list[0] = values[0]; return false; }
        catch (NotSupportedException) { return true; }
    }

    [DllImport("codex_agent", EntryPoint = "codex_agent_test_complete_leaf_operation", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus NativeTestCompleteLeafOperation(nint context);

    private static async Task ExpectOperationFailure(Task task, string description)
    {
        try { await task; throw new InvalidOperationException($"{description} unexpectedly succeeded"); }
        catch (CodexOperationException error) { Require(error.Failure.Code == "test_failure", $"{description} structured failure"); }
    }

    private static async Task ExpectUnowned(Func<Task> operation, string description)
    {
        try { await operation(); throw new InvalidOperationException($"{description} accepted an unowned pending value"); }
        catch (ArgumentException error) { Require(error.ParamName == "value", $"{description} rejects by exact identity"); }
    }

    private static async Task ExpectInputRejected<TService>(
        TService service,
        Func<TService, Task> start,
        string description)
        where TService : IDisposable, IAsyncDisposable
    {
        try
        {
            await start(service);
            throw new InvalidOperationException($"{description} unexpectedly succeeded");
        }
        catch (ArgumentException) { }
        catch (CodexException error) when (error.Status == CodexStatus.InvalidArgument) { }
        finally
        {
            service.Dispose();
            service.Dispose();
            await service.DisposeAsync();
        }
    }

    private static void Mark(ISet<string> executed, string name) =>
        Require(executed.Add(Prefix + CapabilityIds[name]), $"duplicate leaf capability execution: {name}");

    private static MethodInfo[] ResolvePublicMethods(string[] row)
    {
        var methods = new List<MethodInfo>();
        foreach (var symbol in row[1].Split(','))
        {
            var memberSeparator = symbol.LastIndexOf('.');
            Require(memberSeparator > "CodexAgent.".Length, $"{row[2]}: valid public symbol");
            var type = typeof(CodexAuthentication).Assembly.GetType(symbol[..memberSeparator], throwOnError: false);
            Require(type is { IsPublic: true }, $"{row[2]}: public owner type exists");
            var member = symbol[(memberSeparator + 1)..];
            var property = type!.GetProperty(member, BindingFlags.Public | BindingFlags.Instance);
            if (property?.GetMethod is { } getter) { methods.Add(getter); continue; }
            var candidates = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(method => method.Name == member).ToArray();
            if (type == typeof(CodexInteractions) && member == nameof(CodexInteractions.ResolveAsync))
            {
                var parameterType = row[0].Contains("AgentPendingApproval", StringComparison.Ordinal)
                    ? typeof(CodexPendingApproval) : typeof(CodexPendingElicitation);
                candidates = candidates.Where(method => method.GetParameters()[0].ParameterType == parameterType).ToArray();
            }
            Require(candidates.Length == 1, $"{row[2]}: exact public method overload exists");
            methods.Add(candidates[0]);
        }
        return methods.Distinct().ToArray();
    }

    private static void VerifyNegativeEvidence(IReadOnlyList<string[]> claims)
    {
        var first = claims[0];
        var firstMethods = ResolvePublicMethods(first);
        var firstEntryPoints = HeaderEntryPoints(first);
        NativeMethods.SetExactCallObserver(_ => { });
        try
        {
            RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
                [typeof(LeafServiceParity).GetMethod(nameof(LocalOnlyProbe), BindingFlags.NonPublic | BindingFlags.Static)!],
                [firstEntryPoints[0]], "stale-trace"));
        }
        finally { NativeMethods.SetExactCallObserver(null); }

        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            firstMethods, ["codex_agent_removed_leaf_symbol"], "stale-wrapper"));
        var second = claims[1];
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            firstMethods, [HeaderEntryPoints(second)[0]], "missing-production-edge"));

        var staleIl = first.ToArray();
        staleIl[3] = staleIl[3].Replace("csharp-il-leaf:000", "csharp-il-leaf:999", StringComparison.Ordinal);
        RequireThrows(() => McpValueParity.VerifyEvidenceReferences([staleIl]));
    }

    private static string[] HeaderEntryPoints(string[] row) => row[3].Split(',')
        .Where(value => value.StartsWith("c-header:codex_agent_", StringComparison.Ordinal))
        .Select(value => value["c-header:".Length..]).ToArray();

    private static string WrapperName(string entryPoint) => string.Concat(entryPoint["codex_agent_".Length..]
        .Split('_', StringSplitOptions.RemoveEmptyEntries)
        .Select(value => char.ToUpperInvariant(value[0]) + value[1..]));

    private static CodexStatus InvokeInvalidBoundary(string entryPoint)
    {
        var wrapperName = WrapperName(entryPoint);
        var wrapper = typeof(NativeMethods).GetMethods(BindingFlags.NonPublic | BindingFlags.Static)
            .SingleOrDefault(method => method.Name == wrapperName && method.ReturnType == typeof(CodexStatus));
        Require(wrapper is not null, $"{entryPoint}: exact production wrapper exists");

        var probe = new DynamicMethod($"Probe{wrapperName}", typeof(CodexStatus), Type.EmptyTypes,
            typeof(LeafServiceParity).Module, skipVisibility: true);
        var il = probe.GetILGenerator();
        foreach (var parameter in wrapper!.GetParameters()) EmitDefault(il, parameter.ParameterType);
        il.Emit(OpCodes.Call, wrapper);
        il.Emit(OpCodes.Ret);
        return ((Func<CodexStatus>)probe.CreateDelegate(typeof(Func<CodexStatus>)))();
    }

    private static void EmitDefault(ILGenerator il, Type type)
    {
        if (type.IsByRef)
        {
            var local = il.DeclareLocal(type.GetElementType()!);
            il.Emit(OpCodes.Ldloca, local);
            return;
        }
        if (type.IsPointer || type.IsFunctionPointer || type == typeof(nint) || type == typeof(nuint))
        {
            il.Emit(OpCodes.Ldc_I4_0);
            il.Emit(OpCodes.Conv_I);
            return;
        }
        if (!type.IsValueType)
        {
            il.Emit(OpCodes.Ldnull);
            return;
        }
        var value = il.DeclareLocal(type);
        il.Emit(OpCodes.Ldloc, value);
    }

    private static void LocalOnlyProbe() { }

    private static void RequireThrows(Action action)
    {
        try { action(); }
        catch (InvalidOperationException) { return; }
        throw new InvalidOperationException("fail-closed leaf evidence negative unexpectedly passed");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
