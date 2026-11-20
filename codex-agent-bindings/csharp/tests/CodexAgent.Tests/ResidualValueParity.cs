using CodexAgent;
using System.Collections;
using System.Reflection;

internal static class ResidualValueParity
{
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/";
    private static readonly IReadOnlyDictionary<string, Type> OwnerTypes = new Dictionary<string, Type>(StringComparer.Ordinal)
    {
        ["AgentApprovalPreset"] = typeof(CodexApprovalPreset),
        ["AgentAuthenticationState"] = typeof(CodexAuthenticationState),
        ["AgentCapability"] = typeof(CodexCapability),
        ["AgentConversation"] = typeof(CodexConversationSnapshot),
        ["AgentConversationState"] = typeof(CodexConversationState),
        ["AgentElicitation"] = typeof(CodexElicitation),
        ["AgentElicitationResponse"] = typeof(CodexElicitationResponse),
        ["AgentFormField"] = typeof(CodexFormField),
        ["AgentFormValue.BooleanValue"] = typeof(CodexFormValue.BooleanValue),
        ["AgentFormValue.Number"] = typeof(CodexFormValue.Number),
        ["AgentFormValue.Text"] = typeof(CodexFormValue.Text),
        ["AgentFormValue.TextList"] = typeof(CodexFormValue.TextList),
        ["AgentHook"] = typeof(CodexHook),
        ["AgentHookCatalog"] = typeof(CodexHookCatalog),
        ["AgentHookHandler.Agent"] = typeof(CodexHookHandler.Agent),
        ["AgentHookHandler.Command"] = typeof(CodexHookHandler.Command),
        ["AgentHookHandler.McpTool"] = typeof(CodexHookHandler.McpTool),
        ["AgentHookHandler.Prompt"] = typeof(CodexHookHandler.Prompt),
        ["AgentIntegration"] = typeof(CodexIntegration),
        ["AgentIntegration.Connector"] = typeof(CodexIntegration.Connector),
        ["AgentIntegration.McpServer"] = typeof(CodexIntegration.McpServer),
        ["AgentIntegrationAuthorizationState"] = typeof(CodexIntegrationAuthorizationState),
        ["AgentInteractionState"] = typeof(CodexInteractionState),
        ["AgentInvocation"] = typeof(CodexInvocation),
        ["AgentInvocation.Plugin"] = typeof(CodexInvocation.Plugin),
        ["AgentInvocation.Skill"] = typeof(CodexInvocation.Skill),
        ["AgentMessage"] = typeof(CodexMessage),
        ["AgentPendingApproval"] = typeof(CodexPendingApproval),
        ["AgentPendingElicitation"] = typeof(CodexPendingElicitation),
        ["AgentPendingInteraction"] = typeof(CodexPendingInteraction),
        ["AgentSkillScope"] = typeof(CodexSkillScope),
        ["AgentTurnRequest"] = typeof(CodexTurnRequest),
        ["CodexAuthenticationMethod.ApiKey"] = typeof(CodexAuthenticationMethod.ApiKey),
        ["CodexAuthenticationMethod.ChatGptBrowser"] = typeof(CodexAuthenticationMethod.ChatGptBrowser),
        ["CodexAuthenticationMethod.ChatGptDeviceCode"] = typeof(CodexAuthenticationMethod.ChatGptDeviceCode),
        ["CodexAuthorizationUrl"] = typeof(CodexAuthorizationUrl),
        ["CodexHostState.Closed"] = typeof(CodexHostState.Closed),
        ["CodexHostState.Failed"] = typeof(CodexHostState.Failed),
        ["CodexHostState.New"] = typeof(CodexHostState.New),
        ["CodexHostState.Preparing"] = typeof(CodexHostState.Preparing),
        ["CodexHostState.Restoring"] = typeof(CodexHostState.Restoring),
        ["CodexHostState.WorkspaceRequired"] = typeof(CodexHostState.WorkspaceRequired),
        ["CodexPathWorkspaceSelection"] = typeof(CodexPathWorkspaceSelection),
        ["CodexWorkspaceResolution.Available"] = typeof(CodexWorkspaceResolution.Available),
        ["CodexWorkspaceResolution.SelectionRequired"] = typeof(CodexWorkspaceResolution.SelectionRequired),
    };
    private static readonly IReadOnlyDictionary<(string Owner, string Member), string> SpecialSymbols =
        new Dictionary<(string, string), string>
        {
            [("AgentApprovalPreset", "displayName")] = "CodexAgent.CodexEnumMetadata.ApprovalPresetDisplayName",
            [("AgentCapability", "id")] = "CodexAgent.CodexEnumMetadata.CapabilityId",
            [("AgentCapability", "displayLabel")] = "CodexAgent.CodexEnumMetadata.CapabilityDisplayLabel",
            [("AgentCapability", "icon")] = "CodexAgent.CodexEnumMetadata.CapabilityIcon",
            [("AgentCapability", "promptLabel")] = "CodexAgent.CodexEnumMetadata.CapabilityPromptLabel",
            [("AgentSkillScope", "displayName")] = "CodexAgent.CodexEnumMetadata.SkillScopeDisplayName",
        };
    private static readonly HashSet<string> ServiceOwners =
    [
        "CodexAgent",
        "CodexAuthentication",
        "CodexConnectors",
        "CodexConversation",
        "CodexConversations",
        "CodexHooks",
        "CodexHost",
        "CodexIntegrationAuthorization",
        "CodexInteractions",
        "CodexMcpServers",
        "CodexModels",
        "CodexPlugins",
        "CodexSkills",
    ];

    internal static void Verify(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities,
        ISet<string> executedTests)
    {
        var claims = allClaims.Where(row => row[2].StartsWith("csharp.residual.", StringComparison.Ordinal)).ToArray();
        Check(claims.Length == 175, "exact residual ordinary-value claim count");
        Check(OwnerTypes.Count == 45, "exact residual ordinary-value owner count");
        Check(claims.All(row => canonicalCapabilities.Contains(row[0])), "every residual claim is canonical");
        Check(claims.Select(row => row[0]).ToHashSet(StringComparer.Ordinal).Count == 175,
            "residual capability keys are unique");
        Check(claims.Select(row => row[2]).ToHashSet(StringComparer.Ordinal).Count == 175,
            "residual executed tests are distinct per capability");
        var claimedOwners = claims.Select(row => Owner(row[0])).ToHashSet(StringComparer.Ordinal);
        Check(claimedOwners.SetEquals(OwnerTypes.Keys), "residual claims use exactly the audited 45 owners");
        var prior = allClaims.Where(row => !row[2].StartsWith("csharp.residual.", StringComparison.Ordinal))
            .Select(row => row[0]).ToHashSet(StringComparer.Ordinal);
        var expectedResidual = canonicalCapabilities.Where(capability =>
        {
            var owner = CapabilityOwner(capability);
            var kind = Between(capability, "|kind=", "|");
            return !prior.Contains(capability) && kind is "constructor" or "property" or "object" &&
                !ServiceOwners.Contains(owner) && owner != "CodexHostState.Ready";
        }).ToHashSet(StringComparer.Ordinal);
        Check(expectedResidual.SetEquals(claims.Select(row => row[0])),
            "residual claims exactly match the audited constructor/property/object selection");

        McpValueParity.VerifyEvidenceReferences(claims);
        var staleHeader = claims[0].ToArray();
        staleHeader[3] = staleHeader[3].Replace(
            staleHeader[3].Split(',').First(value => value.StartsWith("c-header:", StringComparison.Ordinal)),
            "c-header:codex_agent_removed_residual_value",
            StringComparison.Ordinal);
        RequireThrows<InvalidOperationException>(() => McpValueParity.VerifyEvidenceReferences([staleHeader]));
        var staleFixture = claims[0].ToArray();
        staleFixture[3] = staleFixture[3].Replace(
            staleFixture[3].Split(',').First(value => value.StartsWith("cabi-fixture:", StringComparison.Ordinal)),
            "cabi-fixture:removed.native.test#stale[macosArm64]",
            StringComparison.Ordinal);
        RequireThrows<InvalidOperationException>(() => McpValueParity.VerifyEvidenceReferences([staleFixture]));

        var expected = ExpectedValues();
        foreach (var row in claims)
        {
            var capability = row[0];
            var owner = Owner(capability);
            var type = OwnerTypes[owner];
            var kind = Between(capability, "|kind=", "|");
            var abiMember = kind == "property" ? Between(capability, "|abi=", "|").Split('.').Last() : null;
            var member = kind switch
            {
                "constructor" => "#ctor",
                "object" => "Instance",
                _ => PublicMember(owner, abiMember!),
            };
            string? special = null;
            var expectedSymbol = abiMember is not null && SpecialSymbols.TryGetValue((owner, abiMember), out special)
                ? special
                : $"{PublicTypeName(type)}.{member}";
            Check(row[1] == expectedSymbol, $"{row[2]}: exact public symbol");
            Check(row[1].Split(',').Length == 1 && row[2].Split(',').Length == 1,
                $"{row[2]}: exactly one public symbol and executed test");
            Check(row[4] == ExpectedScenarios(capability), $"{row[2]}: exact shared scenarios");

            if (special is not null)
            {
                VerifyMetadata(owner, abiMember!, expected[owner], special);
            }
            else if (kind == "constructor")
            {
                Check(type.GetConstructors(BindingFlags.Public | BindingFlags.Instance).Length != 0,
                    $"{row[2]}: public constructor exists");
                Check(type.IsInstanceOfType(expected[owner]), $"{row[2]}: constructor creates the public value");
            }
            else if (kind == "object")
            {
                var instance = type.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static);
                Check(instance is { GetMethod.IsPublic: true } && ReferenceEquals(instance.GetValue(null), expected[owner]),
                    $"{row[2]}: exact public singleton exists");
            }
            else
            {
                var property = type.GetProperty(member, BindingFlags.Public | BindingFlags.Instance);
                Check(property is { GetMethod.IsPublic: true }, $"{row[2]}: exact public property exists");
                property!.GetValue(expected[owner]);
            }
            Check(executedTests.Add(row[2]), $"{row[2]}: executed exactly once");
        }

        VerifyValueSemantics();
        Console.WriteLine("CodexAgent C# residual ordinary-value capability tests passed: 175/175 across 45 owners.");
    }

    private static IReadOnlyDictionary<string, object> ExpectedValues()
    {
        var failure = new CodexFailure("failed", "Failure", true);
        var workspace = new CodexWorkspace("/workspace", "Workspace");
        var conversationId = new CodexConversationId("conversation-1");
        var summary = new CodexConversationSummary(conversationId, "Title", 42);
        var skillInvocation = new CodexInvocation.Skill("Skill", "skill.md");
        var pluginInvocation = new CodexInvocation.Plugin("Plugin", "plugin://plugin@market");
        var message = new CodexMessage(
            "message", "client-message", CodexMessageRole.Assistant, "Text", CodexCollaborationMode.Plan,
            "Reasoning", "Plan", "echo hi", 0, [CodexCapability.WebSearch], [skillInvocation, pluginInvocation]);
        var conversation = new CodexConversationSnapshot(summary, [message, message]);
        var turnProgress = new CodexTurnProgress(text: "progress");
        var state = new CodexConversationState(
            CodexConversationStatus.Failed, conversationId, conversation, turnProgress,
            "model", "high", "fast", failure);
        var textList = new CodexFormValue.TextList(["one", "one", "two"]);
        var formOption = new CodexFormOption("one", "One", "Description");
        var formField = new CodexFormField(
            "field", "Field", CodexFormFieldType.MultiSelect, "Description", true,
            [formOption, formOption], textList, 1, 10, CodexFormStringFormat.Uri,
            1, 20, 1, 3, true, true);
        var elicitation = new CodexElicitation(
            "request", "server", conversationId, "Complete the form", [formField, formField], "https://example.test/form");
        var response = new CodexElicitationResponse(
            CodexElicitationAction.Accept, new Dictionary<string, CodexFormValue> { ["field"] = textList });
        var commandHandler = new CodexHookHandler.Command("echo hi", true);
        var mcpHandler = new CodexHookHandler.McpTool("server", "tool");
        var hook = new CodexHook(
            "hook", "hash", true, "after-turn", commandHandler, false, "PLUGIN", "/hook", 30,
            CodexHookTrustStatus.Modified, "matcher", "plugin", "changed", canUninstall: true);
        var hookCatalog = new CodexHookCatalog([hook, hook], ["warning", "warning"], ["error", "error"]);
        var connector = new CodexConnector("connector", "Connector");
        var server = new CodexMcpServer(
            "server", "Server", CodexMcpAuthStatus.Unknown, null, CodexResourceOrigin.User);
        var connectorIntegration = new CodexIntegration.Connector(connector);
        var serverIntegration = new CodexIntegration.McpServer(server);
        var authorizationUrl = CodexAuthorizationUrl.FromNative(
            "https://auth.openai.com/authorize", CodexAuthorizationPurpose.ChatGpt);
        var authentication = new CodexAuthenticationState(
            CodexAuthenticationStatus.Authenticating, authorizationUrl,
            CodexAuthorizationUrl.FromNative(
                "http://127.0.0.1:8080/device", CodexAuthorizationPurpose.External), "CODE", failure);
        var approval = new CodexPendingApproval("approval", conversationId, "Approve", "Details");
        var pendingElicitation = new CodexPendingElicitation(elicitation);
        var interactionState = new CodexInteractionState([approval, pendingElicitation], ["approval"], failure);
        var selectionRequired = new CodexWorkspaceResolution.SelectionRequired(
            CodexWorkspaceSelectionReason.NotSelected, "Select a workspace");

        return new Dictionary<string, object>(StringComparer.Ordinal)
        {
            ["AgentApprovalPreset"] = CodexApprovalPreset.AutoReview,
            ["AgentAuthenticationState"] = authentication,
            ["AgentCapability"] = CodexCapability.WebSearch,
            ["AgentConversation"] = conversation,
            ["AgentConversationState"] = state,
            ["AgentElicitation"] = elicitation,
            ["AgentElicitationResponse"] = response,
            ["AgentFormField"] = formField,
            ["AgentFormValue.BooleanValue"] = new CodexFormValue.BooleanValue(true),
            ["AgentFormValue.Number"] = new CodexFormValue.Number(1.5),
            ["AgentFormValue.Text"] = new CodexFormValue.Text("text"),
            ["AgentFormValue.TextList"] = textList,
            ["AgentHook"] = hook,
            ["AgentHookCatalog"] = hookCatalog,
            ["AgentHookHandler.Agent"] = CodexHookHandler.Agent.Instance,
            ["AgentHookHandler.Command"] = commandHandler,
            ["AgentHookHandler.McpTool"] = mcpHandler,
            ["AgentHookHandler.Prompt"] = CodexHookHandler.Prompt.Instance,
            ["AgentIntegration"] = connectorIntegration,
            ["AgentIntegration.Connector"] = connectorIntegration,
            ["AgentIntegration.McpServer"] = serverIntegration,
            ["AgentIntegrationAuthorizationState"] = new CodexIntegrationAuthorizationState(
                CodexIntegrationAuthorizationStatus.Authorized, connectorIntegration, failure),
            ["AgentInteractionState"] = interactionState,
            ["AgentInvocation"] = skillInvocation,
            ["AgentInvocation.Plugin"] = pluginInvocation,
            ["AgentInvocation.Skill"] = skillInvocation,
            ["AgentMessage"] = message,
            ["AgentPendingApproval"] = approval,
            ["AgentPendingElicitation"] = pendingElicitation,
            ["AgentPendingInteraction"] = approval,
            ["AgentSkillScope"] = CodexSkillScope.Repo,
            ["AgentTurnRequest"] = new CodexTurnRequest(
                "Prompt", "client", "model", "high", "fast", CodexApprovalPreset.Strict,
                [CodexCapability.WebSearch], [skillInvocation, pluginInvocation], CodexCollaborationMode.Plan),
            ["CodexAuthenticationMethod.ApiKey"] = new CodexAuthenticationMethod.ApiKey("secret"),
            ["CodexAuthenticationMethod.ChatGptBrowser"] = CodexAuthenticationMethod.ChatGptBrowser.Instance,
            ["CodexAuthenticationMethod.ChatGptDeviceCode"] = CodexAuthenticationMethod.ChatGptDeviceCode.Instance,
            ["CodexAuthorizationUrl"] = authorizationUrl,
            ["CodexHostState.Closed"] = CodexHostState.Closed.Instance,
            ["CodexHostState.Failed"] = new CodexHostState.Failed(workspace, failure),
            ["CodexHostState.New"] = CodexHostState.New.Instance,
            ["CodexHostState.Preparing"] = new CodexHostState.Preparing(workspace),
            ["CodexHostState.Restoring"] = CodexHostState.Restoring.Instance,
            ["CodexHostState.WorkspaceRequired"] = new CodexHostState.WorkspaceRequired(selectionRequired),
            ["CodexPathWorkspaceSelection"] = new CodexPathWorkspaceSelection("/workspace"),
            ["CodexWorkspaceResolution.Available"] = new CodexWorkspaceResolution.Available(workspace),
            ["CodexWorkspaceResolution.SelectionRequired"] = selectionRequired,
        };
    }

    private static void VerifyMetadata(string owner, string member, object enumValue, string publicSymbol)
    {
        var methodName = publicSymbol.Split('.').Last();
        var method = typeof(CodexEnumMetadata).GetMethod(methodName, BindingFlags.Public | BindingFlags.Static);
        Check(method is not null, $"{publicSymbol}: compiler-visible metadata method");
        var actual = method!.Invoke(null, [enumValue]);
        var expected = (owner, member) switch
        {
            ("AgentApprovalPreset", "displayName") => "Auto review",
            ("AgentCapability", "id") => "web_search",
            ("AgentCapability", "displayLabel") => "Web search",
            ("AgentCapability", "icon") => "🌐",
            ("AgentCapability", "promptLabel") => "Use 🌐 Web search",
            ("AgentSkillScope", "displayName") => "Workspace",
            _ => throw new InvalidOperationException($"Unknown metadata capability: {owner}.{member}"),
        };
        Check(Equals(actual, expected), $"{publicSymbol}: exact metadata value");
    }

    private static void VerifyValueSemantics()
    {
        var messages = new List<CodexMessage>
        {
            new("one", null, CodexMessageRole.User, "one"),
            new("one", null, CodexMessageRole.User, "one"),
        };
        var snapshot = new CodexConversationSnapshot(
            new CodexConversationSummary(new CodexConversationId("conversation"), "Title", 1), messages);
        messages.Clear();
        Check(snapshot.Messages.Count == 2, "conversation snapshot defensively copies ordered duplicate messages");

        var invocation = new CodexInvocation.Skill("Skill", "skill.md");
        var invocations = new List<CodexInvocation> { invocation, invocation };
        var capabilities = new HashSet<CodexCapability> { CodexCapability.WebSearch };
        var message = new CodexMessage("id", null, CodexMessageRole.User, "text", capabilities: capabilities, invocations: invocations);
        var request = new CodexTurnRequest("prompt", capabilities: capabilities, invocations: invocations);
        invocations.Clear();
        capabilities.Clear();
        Check(message.Invocations.Count == 2 && request.Invocations.Count == 2,
            "message and turn request defensively copy ordered invocations");
        Check(message.Capabilities.SetEquals([CodexCapability.WebSearch]) && request.Capabilities.SetEquals([CodexCapability.WebSearch]),
            "message and turn request defensively copy capability sets");
        Check(invocation.Key == "skill:skill.md" && new CodexInvocation.Plugin("Plugin", "uri").Key == "plugin:uri",
            "invocation keys are derived exactly");

        var textValues = new List<string> { "one", "one" };
        var textList = new CodexFormValue.TextList(textValues);
        textValues.Clear();
        var options = new List<CodexFormOption> { new("one"), new("one") };
        var field = new CodexFormField("field", "Field", CodexFormFieldType.MultiSelect, options: options, defaultValue: textList);
        options.Clear();
        Check(textList.Value.SequenceEqual(["one", "one"]) && field.Options.Count == 2,
            "form values and fields defensively copy ordered duplicates");
        var form = new List<CodexFormField> { field, field };
        var elicitation = new CodexElicitation("request", "server", new CodexConversationId("conversation"), "Message", form);
        form.Clear();
        Check(elicitation.Form?.Count == 2 && new CodexElicitation("request", "server", elicitation.ConversationId, "Message").Form is null,
            "elicitation preserves null versus ordered form values");
        var content = new Dictionary<string, CodexFormValue> { ["field"] = textList };
        var response = new CodexElicitationResponse(CodexElicitationAction.Accept, content);
        content.Clear();
        Check(response.Content.Count == 1, "elicitation response defensively copies content");
        RequireThrows<NotSupportedException>(() => ((IDictionary)response.Content).Clear());

        var hook = new CodexHook(
            "hook", "hash", true, "event", CodexHookHandler.Prompt.Instance, false, "PLUGIN", "path", 1,
            CodexHookTrustStatus.Untrusted, pluginId: "plugin");
        var hooks = new List<CodexHook> { hook, hook };
        var warnings = new List<string> { "warning", "warning" };
        var catalog = new CodexHookCatalog(hooks, warnings, warnings);
        hooks.Clear();
        warnings.Clear();
        Check(catalog.Hooks.Count == 2 && catalog.Warnings.Count == 2 && catalog.Errors.Count == 2,
            "hook catalog defensively copies every ordered collection");
        Check(hook.Origin == CodexResourceOrigin.Plugin && hook.CanTrust,
            "hook origin and trust capability are derived exactly");

        var connector = new CodexConnector("id", "Connector");
        CodexIntegration integration = new CodexIntegration.Connector(connector);
        Check(integration.Id == "id" && integration.DisplayName == "Connector", "integration identity is derived exactly");
        var elicitationPending = new CodexPendingElicitation(elicitation);
        Check(elicitationPending.RequestId == elicitation.RequestId && elicitationPending.ConversationId == elicitation.ConversationId,
            "pending elicitation identity is derived exactly");

        var failed = new CodexConversationState(
            CodexConversationStatus.Failed, new CodexConversationId("id"), failure: new CodexFailure("failed", "Failure", true));
        Check(failed.CanStartTurn && failed.CanReload && !failed.CanCancelTurn,
            "conversation-state derived capabilities preserve failure semantics");
        Check(new CodexConversationState(CodexConversationStatus.RunningTurn).CanCancelTurn,
            "running conversation can cancel");
        Check(CodexHostState.New.Instance == CodexHostState.New.Instance &&
            CodexAuthenticationMethod.ChatGptBrowser.Instance == CodexAuthenticationMethod.ChatGptBrowser.Instance,
            "canonical object values are stable singletons");
        Check(new CodexAuthenticationMethod.ApiKey("secret").ToString() == "ApiKey(**redacted**)",
            "API keys are redacted");
        Check(CodexAuthorizationUrl.FromNative(
                "http://127.0.0.1:7777/auth", CodexAuthorizationPurpose.External).Purpose ==
            CodexAuthorizationPurpose.External, "authorization purpose is preserved");

        RequireThrows<ArgumentException>(() => new CodexAuthenticationMethod.ApiKey(" "));
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexFormField(
            "field", "Field", CodexFormFieldType.String, minimumLength: -1));
        RequireThrows<ArgumentException>(() => new CodexFormField(
            "field", "Field", CodexFormFieldType.String, minimumLength: 2, maximumLength: 1));
        RequireThrows<ArgumentException>(() => new CodexPathWorkspaceSelection("bad\0path"));
        RequireThrows<ArgumentOutOfRangeException>(() => CodexEnumMetadata.CapabilityId((CodexCapability)99));
    }

    private static string Owner(string capability) => OwnerTypes.Keys.Single(owner =>
        capability.StartsWith($"{OwnerPrefix}{owner}|", StringComparison.Ordinal));

    private static string CapabilityOwner(string capability) =>
        Between(capability, "|owner=", "|").Split('/').Last();

    private static string PublicMember(string owner, string abiMember) => (owner, abiMember) switch
    {
        ("AgentHookHandler.Command", "command") => "CommandText",
        ("AgentIntegration.Connector", "connector") => "ConnectorValue",
        _ => char.ToUpperInvariant(abiMember[0]) + abiMember[1..],
    };

    private static string PublicTypeName(Type type) => $"CodexAgent.{type.FullName!["CodexAgent.".Length..].Replace('+', '.')}";

    private static string ExpectedScenarios(string capability)
    {
        var scenarios = new List<string> { "value-conversion" };
        if (capability.Contains('?')) scenarios.Add("nullability");
        if (capability.Contains("kotlin.collections", StringComparison.Ordinal))
            scenarios.Add("collection-immutability-ordering");
        if (capability.Contains("CodexFailure", StringComparison.Ordinal)) scenarios.Add("structured-failure");
        scenarios.Sort(StringComparer.Ordinal);
        return string.Join(',', scenarios);
    }

    private static string Between(string value, string prefix, string suffix)
    {
        var start = value.IndexOf(prefix, StringComparison.Ordinal) + prefix.Length;
        var end = value.IndexOf(suffix, start, StringComparison.Ordinal);
        return value[start..end];
    }

    private static void RequireThrows<T>(Action action) where T : Exception
    {
        try { action(); }
        catch (T) { return; }
        throw new InvalidOperationException($"Expected {typeof(T).Name}.");
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
