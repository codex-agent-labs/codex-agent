using CodexAgent;
using CodexAgent.Interop;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;

internal static class HostParity
{
    private const string Prefix = "csharp.host:";
    private const string HostOwner = "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHost|";
    private const string ReadyOwner = "common|owner=io.github.codex_agent_labs.codexagent.agent/CodexHostState.Ready|";

    private static readonly string[] Scenarios =
    [
        "identity,parent-child-ownership,value-conversion",
        "identity,parent-child-ownership,value-conversion",
        "parent-child-ownership,value-conversion",
        "async-failure,async-success,cancellation,parent-child-ownership,repeated-close-dispose,structured-failure,value-conversion",
        "async-failure,async-success,cancellation,parent-child-ownership,structured-failure,value-conversion",
        "async-failure,async-success,cancellation,parent-child-ownership,structured-failure,value-conversion",
        "identity,parent-child-ownership,state-current-value,state-subsequent-value,subscription-cancellation,terminal-delivery,value-conversion",
    ];

    internal static void VerifyContract(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        var claims = Claims(allClaims);
        VerifyClaimClosure(claims, canonicalCapabilities);
        McpValueParity.VerifyEvidenceReferences(claims);
        foreach (var row in claims)
            SynchronousValueFunctionParity.ValidateLeafProductionConnection(
                ProductionRoots(row[2]), HeaderEntryPoints(row), row[2]);
        VerifyNegativeEvidence(claims, canonicalCapabilities);
    }

    internal static async Task VerifyManaged(ISet<string> executed)
    {
        var options = new CodexHostOptions(
            "/host-parity-bundle",
            "/host-parity-data",
            new CodexClientInfo("host-parity", "Host parity", "1.0"));
        var host = CodexHost.Create(options);
        Require(NativeTestHostCopiedInputCount() == 5,
            "host constructor retains independent copies of all five input views beyond the call boundary");
        Require(host.State.Kind == CodexHostStateKind.New, "host constructor returns the new state");
        Mark(executed, 2);

        try
        {
            _ = CodexHost.Create(options with { ClientInfo = new CodexClientInfo("host-parity", "wrong", "1.0") });
            throw new InvalidOperationException("invalid native host factory input unexpectedly succeeded");
        }
        catch (CodexException error) when (error.Status == CodexStatus.InvalidArgument) { }

        var failedStart = host.StartAsync();
        Require(!failedStart.IsCompleted, "host start failure is genuinely asynchronous");
        CompleteHost(CodexStatus.OperationFailed, "host start failure");
        await ExpectFailure(failedStart, "host start");
        using (var cancellation = new CancellationTokenSource())
        {
            var cancelled = host.StartAsync(cancellation.Token);
            cancellation.Cancel();
            await ExpectCancelled(cancelled, "host start cancellation");
        }
        var started = host.StartAsync();
        Require(!started.IsCompleted, "host start success is genuinely asynchronous");
        CompleteHost(CodexStatus.Ok, "host start success");
        await started;
        Mark(executed, 5);

        var first = host.State;
        var second = host.State;
        Require(first is { Kind: CodexHostStateKind.Ready, Agent: not null } &&
            ReferenceEquals(first.Agent, second.Agent), "READY state preserves one stable Agent identity");
        Require(first.Workspace == new CodexWorkspace("/workspace"), "READY state copies its workspace value");
        var ready = new CodexHostState.Ready(first.Agent!);
        Require(ReferenceEquals(ready.Agent, first.Agent), "Ready constructor and Agent property preserve identity");
        Mark(executed, 0);
        Mark(executed, 1);

        using (var cancellation = new CancellationTokenSource())
        {
            await using var cancelledStates = host.ObserveStatesAsync(cancellation.Token).GetAsyncEnumerator();
            Require(await cancelledStates.MoveNextAsync() &&
                ReferenceEquals(cancelledStates.Current.Agent, first.Agent),
                "host state stream emits its current READY value first");
            cancellation.Cancel();
            await ExpectCancelled(cancelledStates.MoveNextAsync().AsTask(), "host state subscription cancellation");
        }

        var releasesBeforeStates = NativeTestAgentReleaseCalls();
        await using (var states = host.ObserveStatesAsync().GetAsyncEnumerator())
        {
            Require(await states.MoveNextAsync() && ReferenceEquals(states.Current.Agent, first.Agent),
                "host state stream current value preserves Agent identity");
            Require(NativeTestAdvanceHostSubscription(0) == CodexStatus.Ok,
                "host state stream advances through the native callback");
            Require(await states.MoveNextAsync() && ReferenceEquals(states.Current.Agent, first.Agent),
                "host state stream subsequent value preserves Agent identity");
            Require(!await states.MoveNextAsync(), "host state stream delivers its terminal event");
        }
        Require(NativeTestAgentReleaseCalls() == releasesBeforeStates + 4,
            "exactly two duplicate retained READY Agent aliases make exactly four release calls before their parent");
        Mark(executed, 6);

        await ExpectInputRejected(() => host.SelectWorkspaceAsync("/wrong"),
            "host workspace selection exact input");
        var selectionSource = "/selected-workspace".ToCharArray();
        var selected = host.SelectWorkspaceAsync(new string(selectionSource));
        selectionSource[1] = 'X';
        Require(!selected.IsCompleted, "host workspace selection success is genuinely asynchronous");
        CompleteHost(CodexStatus.Ok, "host workspace selection success");
        await selected;
        using (var cancellation = new CancellationTokenSource())
        {
            var cancelled = host.SelectWorkspaceAsync("/selected-workspace", cancellation.Token);
            cancellation.Cancel();
            await ExpectCancelled(cancelled, "host workspace selection cancellation");
        }
        var failedSelection = host.SelectWorkspaceAsync("/selected-workspace");
        Require(!failedSelection.IsCompleted, "host workspace selection failure is genuinely asynchronous");
        CompleteHost(CodexStatus.OperationFailed, "host workspace selection failure");
        await ExpectFailure(failedSelection, "host workspace selection");
        Mark(executed, 4);

        var authentication = first.Agent!.Authentication;
        var workspace = first.Agent.Workspace;
        var failedClose = host.CloseAsync();
        Require(!failedClose.IsCompleted, "host close failure is genuinely asynchronous");
        CompleteHost(CodexStatus.OperationFailed, "host close failure");
        await ExpectFailure(failedClose, "host close");
        using (var cancellation = new CancellationTokenSource())
        {
            var cancelled = host.CloseAsync(cancellation.Token);
            cancellation.Cancel();
            await ExpectCancelled(cancelled, "host close cancellation");
        }
        var closed = host.CloseAsync();
        Require(!closed.IsCompleted, "host close success is genuinely asynchronous");
        CompleteHost(CodexStatus.Ok, "host close success");
        await closed;
        var repeatedClose = host.CloseAsync();
        CompleteHost(CodexStatus.Ok, "repeated host close");
        await repeatedClose;
        Require(host.State.Kind == CodexHostStateKind.Closed, "host close projects the terminal closed state");
        host.Dispose();
        host.Dispose();
        RequireDisposed(() => _ = host.State, "disposed host");
        RequireDisposed(() => _ = authentication.State, "host-owned Agent child");
        Require(first.Agent.Workspace == workspace, "copied Agent workspace survives parent disposal");
        Mark(executed, 3);

        Console.WriteLine("CodexAgent C# native-backed Host/Ready tests passed: 7/7.");
    }

    internal static void VerifyNative(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        VerifyContract(allClaims, canonicalCapabilities);
        var receipts = Claims(allClaims).SelectMany(row => HeaderEntryPoints(row).Select(entryPoint =>
        {
            Require(InvokeInvalidBoundary(entryPoint) != CodexStatus.Ok,
                $"{row[2]}: real SDK rejects null Host boundary for {entryPoint}");
            return $"{row[2]}\t{entryPoint}\tpassed";
        })).ToArray();
        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "host-native-tests.tsv"),
            string.Join('\n', new[] { "executedTestId\tnativeSymbol\tstatus" }.Concat(receipts)) + "\n");
        Console.WriteLine($"CodexAgent C# real C ABI Host boundary tests passed: 7 capabilities, {receipts.Length} references to 9 symbols.");
    }

    internal static void ImportNativeEvidence(IReadOnlyList<string[]> allClaims)
    {
        var expected = Claims(allClaims).SelectMany(row => HeaderEntryPoints(row).Select(entryPoint =>
            (TestId: row[2], EntryPoint: entryPoint))).ToArray();
        var path = Path.Combine(AppContext.BaseDirectory, "artifacts", "host-native-tests.tsv");
        Require(File.Exists(path), "real-SDK Host evidence exists");
        var lines = File.ReadAllLines(path);
        Require(lines.Length == expected.Length + 1 && lines[0] == "executedTestId\tnativeSymbol\tstatus",
            "real-SDK Host evidence has exact shape");
        var receipts = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
        Require(receipts.All(row => row.Length == 3 && row[2] == "passed"),
            "every real-SDK Host receipt passed");
        Require(receipts.Select(row => (TestId: row[0], EntryPoint: row[1])).SequenceEqual(expected),
            "real-SDK Host receipts exactly match every capability/header reference");
    }

    private static void VerifyClaimClosure(IReadOnlyList<string[]> claims, ISet<string> canonicalCapabilities)
    {
        var canonical = canonicalCapabilities.Where(capability =>
            capability.StartsWith(HostOwner, StringComparison.Ordinal) ||
            capability.StartsWith(ReadyOwner, StringComparison.Ordinal)).ToHashSet(StringComparer.Ordinal);
        Require(claims.Count == 7 && canonical.Count == 7 && canonical.SetEquals(claims.Select(row => row[0])),
            "Host/Ready claims exactly match the canonical seven-capability closure");
        Require(claims.Select(row => row[2]).SequenceEqual(
            Enumerable.Range(0, 7).Select(index => $"{Prefix}{index:000}")),
            "Host/Ready executed-test IDs are exact and stable");
        Require(claims.Select(row => row[1]).Distinct(StringComparer.Ordinal).Count() == 7,
            "Host/Ready public symbols are distinct per capability");
        for (var index = 0; index < claims.Count; index++)
        {
            Require(claims[index][4] == Scenarios[index], $"{claims[index][2]}: exact shared scenarios");
            ResolvePublicSymbols(claims[index]);
        }
    }

    private static void ResolvePublicSymbols(string[] row)
    {
        foreach (var symbol in row[1].Split(','))
        {
            var ready = symbol.StartsWith("CodexAgent.CodexHostState.Ready.", StringComparison.Ordinal);
            var type = ready ? typeof(CodexHostState.Ready) : typeof(CodexHost);
            var member = symbol[(symbol.LastIndexOf('.') + 1)..];
            Require(type.IsPublic || type.IsNestedPublic, $"{row[2]}: exact public owner exists");
            if (member == "#ctor")
            {
                Require(type.GetConstructors(BindingFlags.Public | BindingFlags.Instance).Length == 1,
                    $"{row[2]}: exact public constructor exists");
            }
            else
            {
                var property = type.GetProperty(member, BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static);
                var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
                    .Where(method => method.Name == member).ToArray();
                Require(property?.GetMethod is { IsPublic: true } || methods.Length > 0,
                    $"{row[2]}: exact public member exists for {symbol}");
            }
        }
    }

    private static MethodInfo[] ProductionRoots(string testId) => testId switch
    {
        "csharp.host:000" or "csharp.host:001" => [StateGetter()],
        "csharp.host:002" => [Method(nameof(CodexHost.Create))],
        "csharp.host:003" => [Method(nameof(CodexHost.CloseAsync))],
        "csharp.host:004" => [Method(nameof(CodexHost.SelectWorkspaceAsync))],
        "csharp.host:005" => [Method(nameof(CodexHost.StartAsync))],
        "csharp.host:006" => [StateGetter(), Method(nameof(CodexHost.ObserveStatesAsync))],
        _ => throw new InvalidOperationException($"Unknown Host/Ready test ID: {testId}"),
    };

    private static MethodInfo StateGetter() => typeof(CodexHost).GetProperty(nameof(CodexHost.State))!.GetMethod!;
    private static MethodInfo Method(string name) => typeof(CodexHost).GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance)
        .Single(method => method.Name == name);

    private static string[][] Claims(IReadOnlyList<string[]> claims) => claims
        .Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();

    private static string[] HeaderEntryPoints(string[] row) => row[3].Split(',')
        .Where(value => value.StartsWith("c-header:codex_agent_", StringComparison.Ordinal) &&
            !value.EndsWith("_t", StringComparison.Ordinal))
        .Select(value => value["c-header:".Length..]).ToArray();

    private static void VerifyNegativeEvidence(IReadOnlyList<string[]> claims, ISet<string> canonicalCapabilities)
    {
        RequireThrows(() => VerifyClaimClosure(claims.Skip(1).ToArray(), canonicalCapabilities));
        var staleSymbol = claims.Select(row => row.ToArray()).ToArray();
        staleSymbol[0][1] = "CodexAgent.CodexHostState.Ready.Removed";
        RequireThrows(() => VerifyClaimClosure(staleSymbol, canonicalCapabilities));
        var staleHeader = claims[0].ToArray();
        staleHeader[3] = staleHeader[3].Replace("codex_agent_host_state_agent", "codex_agent_removed_host_symbol", StringComparison.Ordinal);
        RequireThrows(() => McpValueParity.VerifyEvidenceReferences([staleHeader]));
        var staleIl = claims[0].ToArray();
        staleIl[3] = staleIl[3].Replace("csharp-il-host:000", "csharp-il-host:999", StringComparison.Ordinal);
        RequireThrows(() => McpValueParity.VerifyEvidenceReferences([staleIl]));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            [typeof(HostParity).GetMethod(nameof(LocalOnlyProbe), BindingFlags.NonPublic | BindingFlags.Static)!],
            HeaderEntryPoints(claims[0]), "local-only"));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            ProductionRoots(claims[0][2]), HeaderEntryPoints(claims[2]), "wrong-production-edge"));
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
            typeof(HostParity).Module, skipVisibility: true);
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

    private static void CompleteHost(CodexStatus result, string description) =>
        Require(NativeTestCompleteHostOperation(result) == CodexStatus.Ok,
            $"{description} completes through the native callback");

    private static async Task ExpectFailure(Task task, string description)
    {
        try { await task; throw new InvalidOperationException($"{description} unexpectedly succeeded"); }
        catch (CodexOperationException error)
        {
            Require(error.Failure == new CodexFailure("test_failure", "expected failure", true),
                $"{description} projects its exact structured failure");
        }
    }

    private static async Task ExpectInputRejected(Func<Task> operation, string description)
    {
        try { await operation(); throw new InvalidOperationException($"{description} unexpectedly succeeded"); }
        catch (ArgumentException) { }
        catch (CodexException error) when (error.Status == CodexStatus.InvalidArgument) { }
    }

    private static async Task ExpectCancelled(Task task, string description)
    {
        try { await task; throw new InvalidOperationException($"{description} unexpectedly succeeded"); }
        catch (OperationCanceledException) { }
    }

    private static void RequireDisposed(Action action, string description)
    {
        try { action(); }
        catch (ObjectDisposedException) { return; }
        throw new InvalidOperationException($"{description} remained usable");
    }

    private static void Mark(ISet<string> executed, int index) =>
        Require(executed.Add($"{Prefix}{index:000}"), $"duplicate Host capability execution: {index:000}");

    [DllImport("codex_agent", EntryPoint = "codex_agent_test_complete_host_operation", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus NativeTestCompleteHostOperation(CodexStatus result);
    [DllImport("codex_agent", EntryPoint = "codex_agent_test_advance_host_subscription", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus NativeTestAdvanceHostSubscription(nint context);
    [DllImport("codex_agent", EntryPoint = "codex_agent_test_agent_release_calls", CallingConvention = CallingConvention.Cdecl)]
    private static extern int NativeTestAgentReleaseCalls();
    [DllImport("codex_agent", EntryPoint = "codex_agent_test_host_copied_input_count", CallingConvention = CallingConvention.Cdecl)]
    private static extern int NativeTestHostCopiedInputCount();

    private static void LocalOnlyProbe() { }
    private static void RequireThrows(Action action)
    {
        try { action(); }
        catch (InvalidOperationException) { return; }
        throw new InvalidOperationException("fail-closed Host/Ready evidence negative unexpectedly passed");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
