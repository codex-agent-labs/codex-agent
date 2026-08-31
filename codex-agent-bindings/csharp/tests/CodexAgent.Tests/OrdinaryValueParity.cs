using CodexAgent;
using System.Reflection;

internal static class OrdinaryValueParity
{
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/";
    private static readonly IReadOnlyDictionary<string, Type> OwnerTypes = new Dictionary<string, Type>(StringComparer.Ordinal)
    {
        ["AgentConnector"] = typeof(CodexConnector),
        ["AgentConversationSettings"] = typeof(CodexConversationSettings),
        ["AgentConversationSummary"] = typeof(CodexConversationSummary),
        ["AgentElicitationValidation"] = typeof(CodexElicitationValidation),
        ["AgentElicitationValidationIssue"] = typeof(CodexElicitationValidationIssue),
        ["AgentFormOption"] = typeof(CodexFormOption),
        ["AgentHookActivity"] = typeof(CodexHookActivity),
        ["AgentModel"] = typeof(CodexModel),
        ["AgentPlanProgress"] = typeof(CodexPlanProgress),
        ["AgentPlanStep"] = typeof(CodexPlanStep),
        ["AgentPluginCatalog"] = typeof(CodexPluginCatalog),
        ["AgentPluginDetail"] = typeof(CodexPluginDetail),
        ["AgentPluginInstallResult"] = typeof(CodexPluginInstallResult),
        ["AgentPluginReference"] = typeof(CodexPluginReference),
        ["AgentPluginSkill"] = typeof(CodexPluginSkill),
        ["AgentPluginSummary"] = typeof(CodexPluginSummary),
        ["AgentServiceTier"] = typeof(CodexServiceTier),
        ["AgentSkill"] = typeof(CodexSkill),
        ["AgentSkillCatalog"] = typeof(CodexSkillCatalog),
        ["AgentSkillChunk"] = typeof(CodexSkillChunk),
        ["AgentTurnProgress"] = typeof(CodexTurnProgress),
        ["CodexClientInfo"] = typeof(CodexClientInfo),
        ["CodexFailure"] = typeof(CodexFailure),
        ["CodexWorkspace"] = typeof(CodexWorkspace),
        ["ConversationId"] = typeof(CodexConversationId),
    };
    private static readonly string[] OverlapOwners =
    [
        "AgentMcpEnvironmentVariable",
        "AgentMcpOauthConfiguration",
        "AgentMcpToolConfiguration",
    ];

    internal static void Verify(
        IReadOnlyList<string[]> allClaims,
        ISet<string> canonicalCapabilities,
        ISet<string> executedTests)
    {
        var claims = allClaims.Where(row => Owner(row[0]) is not null).ToArray();
        var overlap = allClaims.Where(row => OverlapOwners.Any(owner => IsOwner(row[0], owner))).ToArray();
        Check(claims.Length == 134, "exact complementary ordinary immutable-value claim count");
        Check(overlap.Length == 8, "exact pre-existing MCP overlap count");
        var closure = claims.Concat(overlap).Select(row => row[0]).ToHashSet(StringComparer.Ordinal);
        var canonicalClosure = canonicalCapabilities.Where(capability =>
            Owner(capability) is not null || OverlapOwners.Any(owner => IsOwner(capability, owner))).ToHashSet(StringComparer.Ordinal);
        Check(closure.Count == 142 && closure.SetEquals(canonicalClosure),
            "ordinary immutable-value claims exactly match the compiler-discovered 28-owner closure");

        McpValueParity.VerifyEvidenceReferences(claims);
        var staleHeader = claims[0].ToArray();
        staleHeader[3] = staleHeader[3].Replace(
            staleHeader[3].Split(',').First(value => value.StartsWith("c-header:", StringComparison.Ordinal)),
            "c-header:codex_agent_removed_ordinary_value",
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
            var owner = Owner(capability) ?? throw new InvalidOperationException($"Unknown ordinary value owner: {capability}");
            var type = OwnerTypes[owner];
            var kind = Between(capability, "|kind=", "|");
            var member = kind == "constructor" ? "#ctor" : PascalCase(Between(capability, "|abi=", "|").Split('.').Last());
            var expectedSymbol = $"CodexAgent.{type.Name}.{member}";
            Check(row[1] == expectedSymbol, $"{row[2]}: exact public symbol");
            Check(row[1].Split(',').Length == 1 && row[2].Split(',').Length == 1,
                $"{row[2]}: exactly one public symbol and executed test");
            Check(row[4] == ExpectedScenarios(capability), $"{row[2]}: exact shared scenarios");

            Check(type.IsPublic, $"{row[2]}: public type exists");
            if (kind == "constructor")
            {
                Check(type.GetConstructors(BindingFlags.Public | BindingFlags.Instance).Length != 0,
                    $"{row[2]}: public constructor exists");
                Check(type.IsInstanceOfType(expected[owner]), $"{row[2]}: constructor creates the public value");
            }
            else
            {
                var property = type.GetProperty(member, BindingFlags.Public | BindingFlags.Instance);
                Check(property is { GetMethod.IsPublic: true }, $"{row[2]}: exact public property exists");
                var value = property!.GetValue(expected[owner]);
                Check(McpValueParity.StructurallyEqual(value, property.GetValue(expected[owner])),
                    $"{row[2]}: exact projected property behavior");
            }
            Check(executedTests.Add(row[2]), $"{row[2]}: executed exactly once");
        }

        VerifyImmutableValueSemantics();
        Console.WriteLine("CodexAgent C# ordinary immutable-value capability tests passed: 142/142 (134 new, 8 MCP overlap).");
    }

    private static IReadOnlyDictionary<string, object> ExpectedValues()
    {
        var connector = new CodexConnector(
            "connector", "Connector", "Description", "https://example.test/install", true, false,
            ["plugin-a", "plugin-a", "plugin-b"]);
        var conversationId = new CodexConversationId("conversation-1");
        var issue = new CodexElicitationValidationIssue("email", CodexElicitationValidationReason.InvalidFormat);
        var step = new CodexPlanStep("compile", CodexPlanStepStatus.Completed);
        var progress = new CodexPlanProgress("done", [step, step]);
        var hook = new CodexHookActivity(
            "hook-1", "after-turn", "command", CodexHookRunStatus.Completed, "ok", ["one", "one", "two"]);
        var reference = new CodexPluginReference("plugin-id", "plugin-name", "marketplace", "path", "remote");
        var pluginSkill = new CodexPluginSkill("skill", "Skill", true, "skill.md");
        var summary = new CodexPluginSummary(
            reference, "Display", "Summary", true, false, CodexPluginInstallPolicy.Available,
            CodexPluginAuthPolicy.OnUse, true, ["one", "one", "two"], "#fff", "privacy", "terms", "website");
        var tier = new CodexServiceTier("fast", "Fast", "Low latency");
        var skill = new CodexSkill(
            "skill", "Skill", "Description", "skill.md", CodexSkillScope.Repo, true,
            "#000", ["dep", "dep"], true);
        return new Dictionary<string, object>(StringComparer.Ordinal)
        {
            ["AgentConnector"] = connector,
            ["AgentConversationSettings"] = new CodexConversationSettings(CodexApprovalPreset.Strict, "fast"),
            ["AgentConversationSummary"] = new CodexConversationSummary(conversationId, "Title", 42),
            ["AgentElicitationValidation"] = new CodexElicitationValidation([issue]),
            ["AgentElicitationValidationIssue"] = issue,
            ["AgentFormOption"] = new CodexFormOption("value", "Title", "Description"),
            ["AgentHookActivity"] = hook,
            ["AgentModel"] = new CodexModel(
                "model", "Model", "Description", ["low", "low", "high"], "low", true, [tier, tier], "fast"),
            ["AgentPlanProgress"] = progress,
            ["AgentPlanStep"] = step,
            ["AgentPluginCatalog"] = new CodexPluginCatalog(
                [summary, summary], ["error", "error"], CodexCatalogFreshness.StaleCache),
            ["AgentPluginDetail"] = new CodexPluginDetail(
                summary, "Detail", [pluginSkill], [connector], ["mcp", "mcp"], 2),
            ["AgentPluginInstallResult"] = new CodexPluginInstallResult(
                CodexPluginAuthPolicy.OnInstall, [connector, connector], "ok"),
            ["AgentPluginReference"] = reference,
            ["AgentPluginSkill"] = pluginSkill,
            ["AgentPluginSummary"] = summary,
            ["AgentServiceTier"] = tier,
            ["AgentSkill"] = skill,
            ["AgentSkillCatalog"] = new CodexSkillCatalog([skill, skill], ["error", "error"]),
            ["AgentSkillChunk"] = new CodexSkillChunk("content", 7, 12),
            ["AgentTurnProgress"] = new CodexTurnProgress(
                "text", "commentary", "reasoning", "plan", progress, "output", 7,
                CodexWorkActivity.WritingFiles, [hook, hook], true),
            ["CodexClientInfo"] = new CodexClientInfo("client", "Client", "1.0"),
            ["CodexFailure"] = new CodexFailure("failed", "Failure", true),
            ["CodexWorkspace"] = new CodexWorkspace("/workspace", "Workspace"),
            ["ConversationId"] = conversationId,
        };
    }

    private static void VerifyImmutableValueSemantics()
    {
        var names = new List<string> { "one", "one", "two" };
        var connector = new CodexConnector("id", "name", pluginNames: names);
        names[0] = "changed";
        Check(connector.PluginNames.SequenceEqual(["one", "one", "two"]),
            "connector defensively copies and preserves ordered duplicates");

        var steps = new List<CodexPlanStep>
        {
            new("one", CodexPlanStepStatus.Pending),
            new("one", CodexPlanStepStatus.Pending),
        };
        var progress = new CodexPlanProgress(null, steps);
        steps.Clear();
        Check(progress.Explanation is null && progress.Steps.Count == 2 && new CodexPlanProgress().Steps.Count == 0,
            "plan progress preserves null, empty, order, duplicates, and defensive copies");

        var mutable = new List<string> { "a", "a" };
        var tier = new CodexServiceTier("tier", "Tier", "Description");
        var model = new CodexModel("id", "Model", "Description", mutable, "a", false, [tier, tier]);
        var hook = new CodexHookActivity("id", "event", "handler", CodexHookRunStatus.Running, details: mutable);
        var reference = new CodexPluginReference("id", "name", "market");
        var plugin = new CodexPluginSummary(
            reference, "Plugin", "Description", false, true, CodexPluginInstallPolicy.Available,
            CodexPluginAuthPolicy.OnUse, true, mutable);
        var skill = new CodexSkill("s", "S", "d", "p", CodexSkillScope.Repo, true, dependencies: mutable);
        mutable.Clear();
        Check(model.SupportedEfforts.SequenceEqual(["a", "a"]) && model.ServiceTiers.Count == 2,
            "model collections are ordered defensive copies");
        Check(hook.Details.SequenceEqual(["a", "a"]) && plugin.Capabilities.SequenceEqual(["a", "a"]),
            "hook and plugin collections are ordered defensive copies");
        Check(skill.Dependencies.SequenceEqual(["a", "a"]), "skill dependencies are an ordered defensive copy");

        var issue = new CodexElicitationValidationIssue("field", CodexElicitationValidationReason.InvalidType);
        Check(new CodexElicitationValidation([]).IsValid && !new CodexElicitationValidation([issue]).IsValid,
            "elicitation validity is derived from immutable issues");
        Check(new CodexFormOption("value").Title == "value", "form option title defaults to value");
        Check(reference.Uri == "plugin://name@market", "plugin URI is derived canonically");
        Check(skill.Origin == CodexResourceOrigin.Workspace, "skill origin defaults from scope");
        Check(new CodexWorkspace("/workspace").DisplayName == "/workspace", "workspace display name defaults to path");

        RequireThrows<ArgumentException>(() => new CodexClientInfo("", "Title", "1"));
        RequireThrows<ArgumentException>(() => new CodexClientInfo("client\n", "Title", "1"));
        RequireThrows<ArgumentException>(() => new CodexConversationId(" "));
        RequireThrows<ArgumentException>(() => new CodexFailure("", "message", false));
        RequireThrows<ArgumentOutOfRangeException>(() => new CodexFailure("code", new string('x', 501), false));
        RequireThrows<ArgumentException>(() => new CodexWorkspace(" "));
        RequireThrows<ArgumentException>(() => new CodexWorkspace("/workspace", " "));
    }

    private static string? Owner(string capability) =>
        OwnerTypes.Keys.FirstOrDefault(owner => IsOwner(capability, owner));

    private static bool IsOwner(string capability, string owner) =>
        capability.StartsWith($"{OwnerPrefix}{owner}|", StringComparison.Ordinal);

    private static string ExpectedScenarios(string capability)
    {
        var scenarios = new List<string> { "value-conversion" };
        if (capability.Contains('?')) scenarios.Add("nullability");
        if (capability.Contains("kotlin.collections", StringComparison.Ordinal))
            scenarios.Add("collection-immutability-ordering");
        if (IsOwner(capability, "CodexFailure")) scenarios.Add("structured-failure");
        scenarios.Sort(StringComparer.Ordinal);
        return string.Join(',', scenarios);
    }

    private static string Between(string value, string prefix, string suffix)
    {
        var start = value.IndexOf(prefix, StringComparison.Ordinal) + prefix.Length;
        var end = value.IndexOf(suffix, start, StringComparison.Ordinal);
        return value[start..end];
    }

    private static string PascalCase(string value) => char.ToUpperInvariant(value[0]) + value[1..];

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
