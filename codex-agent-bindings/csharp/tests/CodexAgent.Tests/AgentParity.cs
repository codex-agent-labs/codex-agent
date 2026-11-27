using CodexAgent;
using CodexAgent.Interop;
using System.Reflection;
using System.Reflection.Emit;

internal static class AgentParity
{
    private const string Prefix = "csharp.agent:";
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexAgent|";

    internal static void VerifyContract(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        var claims = Claims(allClaims);
        var canonical = canonicalCapabilities.Where(capability =>
            capability.StartsWith(OwnerPrefix, StringComparison.Ordinal)).ToHashSet(StringComparer.Ordinal);
        Require(claims.Length == 11 && canonical.Count == 11 && canonical.SetEquals(claims.Select(row => row[0])),
            "agent claims exactly match the canonical 11-capability closure");
        Require(claims.Select(row => row[2]).SequenceEqual(Enumerable.Range(0, 11).Select(index => $"{Prefix}{index:000}")),
            "agent executed-test IDs are exact and stable");
        McpValueParity.VerifyEvidenceReferences(claims);
        foreach (var row in claims)
            SynchronousValueFunctionParity.ValidateLeafProductionConnection(
                [ResolveGetter(row)], HeaderEntryPoints(row), row[2]);
        VerifyNegativeEvidence(claims);
    }

    internal static Action VerifyManaged(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var authentication = Stable(() => agent.Authentication, 0, executed);
        var connectors = Stable(() => agent.Connectors, 1, executed);
        var conversations = Stable(() => agent.Conversations, 2, executed);
        var hooks = Stable(() => agent.Hooks, 3, executed);
        var integrationAuthorization = Stable(() => agent.IntegrationAuthorization, 4, executed);
        var interactions = Stable(() => agent.Interactions, 5, executed);
        var mcpServers = Stable(() => agent.McpServers, 6, executed);
        var models = Stable(() => agent.Models, 7, executed);
        var plugins = Stable(() => agent.Plugins, 8, executed);
        var skills = Stable(() => agent.Skills, 9, executed);
        var workspace = Stable(() => agent.Workspace, 10, executed);
        Require(workspace == new CodexWorkspace("/agent-workspace", "Agent Workspace"),
            "agent workspace is an exact immutable copied snapshot");
        Console.WriteLine("CodexAgent C# native-backed Agent property tests passed: 11/11.");

        return () =>
        {
            RequireDisposed(() => _ = authentication.State, "authentication");
            RequireDisposed(() => _ = connectors.IsAvailable, "connectors");
            RequireDisposed(() => _ = conversations.ActiveConversation, "conversations");
            RequireDisposed(() => _ = hooks.IsAvailable, "hooks");
            RequireDisposed(() => _ = integrationAuthorization.State, "integration authorization");
            RequireDisposed(() => _ = interactions.State, "interactions");
            RequireDisposed(() => _ = mcpServers.IsAvailable, "MCP servers");
            RequireDisposed(() => _ = models.ListAsync(), "models");
            RequireDisposed(() => _ = plugins.IsAvailable, "plugins");
            RequireDisposed(() => _ = skills.IsAvailable, "skills");
            Require(agent.Workspace == workspace, "workspace snapshot survives parent close");
        };
    }

    internal static void VerifyNative(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        VerifyContract(allClaims, canonicalCapabilities);
        var receipts = Claims(allClaims).Select(row =>
        {
            var entryPoint = HeaderEntryPoints(row).Single();
            Require(InvokeInvalidBoundary(entryPoint) != CodexStatus.Ok,
                $"{row[2]}: real SDK rejects null agent boundary for {entryPoint}");
            return $"{row[2]}\t{entryPoint}\tpassed";
        }).ToArray();
        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "agent-native-tests.tsv"),
            string.Join('\n', new[] { "executedTestId\tnativeSymbol\tstatus" }.Concat(receipts)) + "\n");
        Console.WriteLine("CodexAgent C# real C ABI Agent boundary tests passed: 11 capabilities, 11 symbols.");
    }

    internal static void ImportNativeEvidence(IReadOnlyList<string[]> allClaims)
    {
        var expected = Claims(allClaims).Select(row => (TestId: row[2], EntryPoint: HeaderEntryPoints(row).Single())).ToArray();
        var path = Path.Combine(AppContext.BaseDirectory, "artifacts", "agent-native-tests.tsv");
        Require(File.Exists(path), "real-SDK Agent evidence exists");
        var lines = File.ReadAllLines(path);
        Require(lines.Length == 12 && lines[0] == "executedTestId\tnativeSymbol\tstatus",
            "real-SDK Agent evidence has exact shape");
        var receipts = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
        Require(receipts.All(row => row.Length == 3 && row[2] == "passed"),
            "every real-SDK Agent receipt passed");
        Require(receipts.Select(row => (TestId: row[0], EntryPoint: row[1])).SequenceEqual(expected),
            "real-SDK Agent receipts exactly match every capability/header reference");
    }

    private static T Stable<T>(Func<T> read, int index, ISet<string> executed) where T : class
    {
        var first = read();
        Require(ReferenceEquals(first, read()), $"agent property {index:000} preserves identity");
        Require(executed.Add($"{Prefix}{index:000}"), $"duplicate Agent capability execution: {index:000}");
        return first;
    }

    private static string[][] Claims(IReadOnlyList<string[]> claims) => claims
        .Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();

    private static MethodInfo ResolveGetter(string[] row)
    {
        var symbol = row[1];
        var separator = symbol.LastIndexOf('.');
        var type = typeof(CodexAgent.CodexAgent).Assembly.GetType(symbol[..separator], throwOnError: false);
        var getter = type?.GetProperty(symbol[(separator + 1)..], BindingFlags.Public | BindingFlags.Instance)?.GetMethod;
        Require(type is { IsPublic: true } && getter is { IsPublic: true }, $"{row[2]}: exact public property exists");
        return getter!;
    }

    private static string[] HeaderEntryPoints(string[] row) => row[3].Split(',')
        .Where(value => value.StartsWith("c-header:codex_agent_", StringComparison.Ordinal))
        .Select(value => value["c-header:".Length..]).ToArray();

    private static void VerifyNegativeEvidence(IReadOnlyList<string[]> claims)
    {
        var firstGetter = ResolveGetter(claims[0]);
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            [typeof(AgentParity).GetMethod(nameof(LocalOnlyProbe), BindingFlags.NonPublic | BindingFlags.Static)!],
            HeaderEntryPoints(claims[0]), "local-only"));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            [firstGetter], ["codex_agent_removed_agent_symbol"], "stale-wrapper"));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            [firstGetter], HeaderEntryPoints(claims[1]), "wrong-production-edge"));
        var staleEvidence = claims[0].ToArray();
        staleEvidence[3] = staleEvidence[3].Replace("csharp-il-agent:000", "csharp-il-agent:999", StringComparison.Ordinal);
        RequireThrows(() => McpValueParity.VerifyEvidenceReferences([staleEvidence]));
    }

    private static CodexStatus InvokeInvalidBoundary(string entryPoint)
    {
        var wrapperName = string.Concat(entryPoint["codex_agent_".Length..]
            .Split('_', StringSplitOptions.RemoveEmptyEntries)
            .Select(value => char.ToUpperInvariant(value[0]) + value[1..]));
        var wrapper = typeof(NativeMethods).GetMethods(BindingFlags.NonPublic | BindingFlags.Static)
            .SingleOrDefault(method => method.Name == wrapperName && method.ReturnType == typeof(CodexStatus));
        Require(wrapper is not null, $"{entryPoint}: exact production wrapper exists");
        var probe = new DynamicMethod($"Probe{wrapper!.Name}", typeof(CodexStatus), Type.EmptyTypes,
            typeof(AgentParity).Module, skipVisibility: true);
        var il = probe.GetILGenerator();
        foreach (var parameter in wrapper.GetParameters()) EmitDefault(il, parameter.ParameterType);
        il.Emit(OpCodes.Call, wrapper);
        il.Emit(OpCodes.Ret);
        return ((Func<CodexStatus>)probe.CreateDelegate(typeof(Func<CodexStatus>)))();
    }

    private static void EmitDefault(ILGenerator il, Type type)
    {
        if (type.IsByRef) { var local = il.DeclareLocal(type.GetElementType()!); il.Emit(OpCodes.Ldloca, local); return; }
        if (type.IsPointer || type.IsFunctionPointer || type == typeof(nint) || type == typeof(nuint))
        { il.Emit(OpCodes.Ldc_I4_0); il.Emit(OpCodes.Conv_I); return; }
        if (!type.IsValueType) { il.Emit(OpCodes.Ldnull); return; }
        var value = il.DeclareLocal(type); il.Emit(OpCodes.Ldloc, value);
    }

    private static void RequireDisposed(Action action, string description)
    {
        try { action(); }
        catch (ObjectDisposedException) { return; }
        throw new InvalidOperationException($"parent close left {description} usable");
    }

    private static void LocalOnlyProbe() { }
    private static void RequireThrows(Action action)
    {
        try { action(); }
        catch (InvalidOperationException) { return; }
        throw new InvalidOperationException("fail-closed Agent evidence negative unexpectedly passed");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
