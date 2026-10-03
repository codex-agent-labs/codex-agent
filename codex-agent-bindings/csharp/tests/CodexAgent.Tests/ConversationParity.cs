using CodexAgent;
using CodexAgent.Interop;
using System.Collections;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.InteropServices;

internal static class ConversationParity
{
    private const string Prefix = "csharp.conversation:";
    private const string OwnerPrefix = "common|owner=io.github.codex_agent_labs.codexagent.agent/";

    internal static void VerifyContract(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        var claims = Claims(allClaims);
        var canonical = canonicalCapabilities.Where(capability =>
            capability.StartsWith($"{OwnerPrefix}CodexConversations|", StringComparison.Ordinal) ||
            capability.StartsWith($"{OwnerPrefix}CodexConversation|", StringComparison.Ordinal)).ToHashSet(StringComparer.Ordinal);
        Require(claims.Length == 20 && canonical.Count == 20 && canonical.SetEquals(claims.Select(row => row[0])),
            "conversation claims exactly match the canonical 20-capability closure");
        Require(claims.Select(row => row[2]).SequenceEqual(Enumerable.Range(0, 20).Select(index => $"{Prefix}{index:000}")),
            "conversation executed-test IDs are exact and stable");
        McpValueParity.VerifyEvidenceReferences(claims);
        foreach (var row in claims)
            SynchronousValueFunctionParity.ValidateLeafProductionConnection(
                ResolvePublicMethods(row), HeaderEntryPoints(row), row[2]);
        VerifyNegativeEvidence(claims);
    }

    internal static async Task VerifyManaged(CodexAgent.CodexAgent agent, ISet<string> executed)
    {
        var conversations = agent.Conversations;
        Require(conversations.ActiveConversation is null, "active conversation starts absent");

        var listTask = conversations.ListAsync();
        Require(!listTask.IsCompleted, "conversation list is genuinely asynchronous");
        CompletePending("conversation list");
        var summaries = await listTask;
        RequireOrderedImmutable(summaries, value => value.ConversationId.Value,
            "conversation-alpha", "conversation-beta", "conversation-alpha", "conversation list");
        Require(summaries[0] is { Title: "Alpha", UpdatedAtEpochSeconds: 11 } &&
            summaries[1] is { Title: "Beta", UpdatedAtEpochSeconds: 22 } &&
            summaries[2] is { Title: "Alpha", UpdatedAtEpochSeconds: 11 }, "conversation summaries project exact values");
        Mark(executed, 1);

        var readTask = conversations.ReadAsync(new CodexConversationId("read-input"));
        Require(!readTask.IsCompleted, "conversation read is genuinely asynchronous");
        CompletePending("conversation read");
        var snapshot = await readTask;
        Require(snapshot.Summary is { ConversationId.Value: "conversation-alpha", Title: "Alpha", UpdatedAtEpochSeconds: 11 },
            "conversation read projects exact summary");
        RequireExactMessages(snapshot.Messages, "message-alpha", "message-beta", "message-alpha", "conversation read");
        await ExpectInputRejected(() => conversations.ReadAsync(new CodexConversationId("wrong")), "conversation read copied ID");
        Mark(executed, 3);

        var renameTask = conversations.RenameAsync(new CodexConversationId("rename-input"), "Renamed");
        CompletePending("conversation rename");
        await renameTask;
        await ExpectInputRejected(() => conversations.RenameAsync(new CodexConversationId("rename-input"), "Wrong"),
            "conversation rename copied name");
        await ExpectInputRejected(() => conversations.RenameAsync(new CodexConversationId("wrong"), "Renamed"),
            "conversation rename copied ID");
        Mark(executed, 4);

        var deleteTask = conversations.DeleteAsync(new CodexConversationId("delete-input"));
        CompletePending("conversation delete");
        await deleteTask;
        await ExpectInputRejected(() => conversations.DeleteAsync(new CodexConversationId("wrong")), "conversation delete copied ID");
        Mark(executed, 0);

        await ExpectInputRejected(() => conversations.OpenAsync(new CodexConversationOpenOptions("wrong-open")),
            "conversation open copied ID");
        await ExpectInputRejected(() => conversations.OpenAsync(new CodexConversationOpenOptions(
            "conversation-open", CodexApprovalPreset.Never, "fast")), "conversation open copied approval preset");
        var conversation = await conversations.OpenAsync(new CodexConversationOpenOptions(
            "conversation-open", CodexApprovalPreset.AskMe, "fast"));
        Require(ReferenceEquals(conversation, conversations.ActiveConversation) && conversation.IsSame(conversation),
            "conversation open preserves live identity");
        Mark(executed, 2);

        await VerifyConversationOperations(conversation, executed);
        await VerifyConversationStates(conversation, executed);

        await conversation.CloseAsync();
        await conversation.CloseAsync();
        conversation.Dispose();
        conversation.Dispose();
        await conversation.DisposeAsync();
        Mark(executed, 7);

        var active = await conversations.OpenAsync(new CodexConversationOpenOptions(
            "conversation-open", CodexApprovalPreset.AskMe, "fast"));
        await VerifyActiveState(conversations, active);
        Mark(executed, 5);
        Console.WriteLine("CodexAgent C# native-backed conversation tests passed: 20/20.");
    }

    private static async Task VerifyConversationOperations(CodexConversation conversation, ISet<string> executed)
    {
        await conversation.CancelTurnAsync();
        Mark(executed, 6);

        await conversation.ReloadAsync();
        Mark(executed, 8);

        var shell = conversation.RunShellCommandAsync("pwd");
        Require(!shell.IsCompleted, "shell operation is genuinely asynchronous");
        CompletePending("shell command");
        await shell;
        await ExpectInputRejected(() => conversation.RunShellCommandAsync("wrong-shell"), "shell command copied input");
        using (var cancellation = new CancellationTokenSource())
        {
            var cancelled = conversation.RunShellCommandAsync("sleep", cancellation.Token);
            cancellation.Cancel();
            await ExpectCancelled(cancelled, "shell command cancellation");
        }
        await conversation.ReloadAsync();
        Mark(executed, 9);

        var request = new CodexTurnRequest(
            "structured", "client-1", "model", "high", "fast", CodexApprovalPreset.AskMe,
            [CodexCapability.WebSearch],
            [new CodexInvocation.Plugin("plugin", "plugin://plugin@market"), new CodexInvocation.Skill("skill", "skill.md")],
            CodexCollaborationMode.Plan);
        var structured = conversation.SendAsync(request);
        Require(!structured.IsCompleted, "structured send is genuinely asynchronous");
        CompletePending("structured send");
        await structured;
        await ExpectInputRejected(() => conversation.SendAsync(new CodexTurnRequest(
            "structured", "client-1", "model", "wrong", "fast", CodexApprovalPreset.AskMe,
            [CodexCapability.WebSearch],
            [new CodexInvocation.Plugin("plugin", "plugin://plugin@market"), new CodexInvocation.Skill("skill", "skill.md")],
            CodexCollaborationMode.Plan)),
            "structured send copied every request field");
        Mark(executed, 10);

        await conversation.SendAsync("héllo");
        await ExpectInputRejected(() => conversation.SendAsync("wrong-input"), "string send copied prompt");
        try
        {
            await conversation.SendAsync("fail");
            throw new InvalidOperationException("structured send failure unexpectedly succeeded");
        }
        catch (CodexOperationException error)
        {
            Require(error.Failure == new CodexFailure("test_failure", "expected failure", true),
                "string send projects structured failure");
        }
        Mark(executed, 11);
    }

    private static async Task VerifyConversationStates(CodexConversation conversation, ISet<string> executed)
    {
        await VerifyState(
            () => conversation.ActiveTurnProgress,
            token => conversation.ObserveActiveTurnProgressAsync(token),
            value => value is { Text: "working", Commentary: "commentary", Reasoning: "reasoning", Plan: "plan",
                PlanProgress: null, ShellOutput: "output", ShellExitCode: 0,
                WorkActivity: CodexWorkActivity.RunningCommand, HookActivities.Count: 0, IsTruncated: true },
            value => value is null, "active turn progress");
        Mark(executed, 12);

        await VerifyState(() => conversation.CanCancelTurn, token => conversation.ObserveCanCancelTurnAsync(token),
            value => value, value => !value, "can cancel turn");
        Mark(executed, 13);
        await VerifyState(() => conversation.CanReload, token => conversation.ObserveCanReloadAsync(token),
            value => value, value => !value, "can reload");
        Mark(executed, 14);
        await VerifyState(() => conversation.CanRunShellCommand, token => conversation.ObserveCanRunShellCommandAsync(token),
            value => value, value => !value, "can run shell command");
        Mark(executed, 15);
        await VerifyState(() => conversation.CanStartTurn, token => conversation.ObserveCanStartTurnAsync(token),
            value => value, value => !value, "can start turn");
        Mark(executed, 16);

        await VerifyState(
            () => conversation.CurrentMessages,
            token => conversation.ObserveCurrentMessagesAsync(token),
            value => ExactMessages(value, "message-alpha", "message-beta", "message-alpha", "current messages"),
            value => ExactMessages(value, "message-gamma", "message-delta", "message-gamma", "subsequent messages"),
            "current messages");
        Mark(executed, 17);

        await VerifyState(() => conversation.IsTurnActive, token => conversation.ObserveIsTurnActiveAsync(token),
            value => value, value => !value, "turn active");
        Mark(executed, 18);

        await VerifyState(() => conversation.State, token => conversation.ObserveStatesAsync(token),
            value => value.Status == CodexConversationStatus.Ready,
            value => value.Status == CodexConversationStatus.CancellingTurn,
            "conversation state");
        Mark(executed, 19);
    }

    private static async Task VerifyActiveState(CodexConversations conversations, CodexConversation active)
    {
        Require(ReferenceEquals(active, conversations.ActiveConversation), "active getter preserves exact conversation identity");
        await using (var enumerator = conversations.ObserveActiveConversationAsync().GetAsyncEnumerator())
        {
            Require(await enumerator.MoveNextAsync() && ReferenceEquals(active, enumerator.Current),
                "active subscription emits exact current identity");
            Require(NativeTestAdvanceActiveSubscription(0) == CodexStatus.Ok,
                "fake advances active subscription through native callback");
            Require(await enumerator.MoveNextAsync() && enumerator.Current is null,
                "active subscription emits distinct nullable subsequent value");
            Require(!await enumerator.MoveNextAsync(), "active subscription delivers terminal event");
        }
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await using var cancelled = conversations.ObserveActiveConversationAsync(cancellation.Token).GetAsyncEnumerator();
        await ExpectCancelled(cancelled.MoveNextAsync().AsTask(), "active subscription cancellation");
    }

    private static async Task VerifyState<T>(
        Func<T> current,
        Func<CancellationToken, IAsyncEnumerable<T>> observe,
        Func<T, bool> currentPredicate,
        Func<T, bool> subsequentPredicate,
        string description)
    {
        Require(currentPredicate(current()), $"{description} exact current value");
        await using (var enumerator = observe(default).GetAsyncEnumerator())
        {
            Require(await enumerator.MoveNextAsync() && currentPredicate(enumerator.Current),
                $"{description} subscription current value");
            Require(await enumerator.MoveNextAsync() && subsequentPredicate(enumerator.Current),
                $"{description} distinct subsequent value");
            Require(!await enumerator.MoveNextAsync(), $"{description} terminal delivery");
        }
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await using var cancelled = observe(cancellation.Token).GetAsyncEnumerator();
        await ExpectCancelled(cancelled.MoveNextAsync().AsTask(), $"{description} subscription cancellation");
    }

    internal static void VerifyNative(IReadOnlyList<string[]> allClaims, ISet<string> canonicalCapabilities)
    {
        VerifyContract(allClaims, canonicalCapabilities);
        var receipts = Claims(allClaims).SelectMany(row => HeaderEntryPoints(row)
            .Select(entryPoint => (row[2], EntryPoint: entryPoint, Status: InvokeInvalidBoundary(entryPoint)))).ToArray();
        Require(receipts.Length == 49 && receipts.Select(value => value.EntryPoint).Distinct(StringComparer.Ordinal).Count() == 39,
            "real SDK executes all 49 per-capability references to 39 unique conversation symbols");
        Require(receipts.All(value => value.Status != CodexStatus.Ok), "real SDK rejects every null conversation boundary");
        var directory = Path.Combine(AppContext.BaseDirectory, "artifacts");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, "conversation-native-tests.tsv"),
            string.Join('\n', new[] { "executedTestId\tnativeSymbol\tstatus" }.Concat(
                receipts.Select(value => $"{value.Item1}\t{value.EntryPoint}\tpassed"))) + "\n");
        Console.WriteLine("CodexAgent C# real C ABI conversation boundary tests passed: 20 capabilities, 39 symbols, 49 references.");
    }

    internal static void ImportNativeEvidence(IReadOnlyList<string[]> allClaims)
    {
        var expected = Claims(allClaims).SelectMany(row => HeaderEntryPoints(row)
            .Select(entryPoint => (TestId: row[2], EntryPoint: entryPoint))).ToArray();
        var path = Path.Combine(AppContext.BaseDirectory, "artifacts", "conversation-native-tests.tsv");
        Require(File.Exists(path), "real-SDK conversation evidence exists");
        var lines = File.ReadAllLines(path);
        Require(lines.Length == 50 && lines[0] == "executedTestId\tnativeSymbol\tstatus",
            "real-SDK conversation evidence has exact shape");
        var receipts = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
        Require(receipts.All(row => row.Length == 3 && row[2] == "passed"), "every real-SDK conversation receipt passed");
        Require(receipts.Select(row => (TestId: row[0], EntryPoint: row[1])).SequenceEqual(expected),
            "real-SDK conversation receipts exactly match every capability/header reference");
    }

    private static string[][] Claims(IReadOnlyList<string[]> claims) => claims
        .Where(row => row[2].StartsWith(Prefix, StringComparison.Ordinal)).ToArray();

    private static MethodInfo[] ResolvePublicMethods(string[] row)
    {
        var methods = new List<MethodInfo>();
        foreach (var symbol in row[1].Split(','))
        {
            var separator = symbol.LastIndexOf('.');
            var type = typeof(CodexConversation).Assembly.GetType(symbol[..separator], throwOnError: false);
            Require(type is { IsPublic: true }, $"{row[2]}: public owner type exists");
            var name = symbol[(separator + 1)..];
            if (type!.GetProperty(name, BindingFlags.Public | BindingFlags.Instance)?.GetMethod is { } getter)
            {
                methods.Add(getter);
                continue;
            }
            var candidates = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(method => method.Name == name).ToArray();
            if (type == typeof(CodexConversation) && name == nameof(CodexConversation.SendAsync))
            {
                var parameterType = row[0].Contains("AgentTurnRequest", StringComparison.Ordinal)
                    ? typeof(CodexTurnRequest) : typeof(string);
                candidates = candidates.Where(method => method.GetParameters()[0].ParameterType == parameterType).ToArray();
            }
            Require(candidates.Length == 1, $"{row[2]}: exact public method overload exists");
            methods.Add(candidates[0]);
        }
        return methods.Distinct().ToArray();
    }

    private static void VerifyNegativeEvidence(IReadOnlyList<string[]> claims)
    {
        var firstMethods = ResolvePublicMethods(claims[0]);
        var firstEntry = HeaderEntryPoints(claims[0])[0];
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            [typeof(ConversationParity).GetMethod(nameof(LocalOnlyProbe), BindingFlags.NonPublic | BindingFlags.Static)!],
            [firstEntry], "local-only"));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            firstMethods, ["codex_agent_removed_conversation_symbol"], "stale-wrapper"));
        RequireThrows(() => SynchronousValueFunctionParity.ValidateLeafProductionConnection(
            firstMethods, [HeaderEntryPoints(claims[1])[0]], "wrong-production-edge"));
        var staleEvidence = claims[0].ToArray();
        staleEvidence[3] = staleEvidence[3].Replace("csharp-il-conversation:000", "csharp-il-conversation:999", StringComparison.Ordinal);
        RequireThrows(() => McpValueParity.VerifyEvidenceReferences([staleEvidence]));
    }

    private static string[] HeaderEntryPoints(string[] row) => row[3].Split(',')
        .Where(value => value.StartsWith("c-header:codex_agent_", StringComparison.Ordinal))
        .Select(value => value["c-header:".Length..]).ToArray();

    private static string WrapperName(string entryPoint) => string.Concat(entryPoint["codex_agent_".Length..]
        .Split('_', StringSplitOptions.RemoveEmptyEntries)
        .Select(value => char.ToUpperInvariant(value[0]) + value[1..]));

    private static CodexStatus InvokeInvalidBoundary(string entryPoint)
    {
        var wrapper = typeof(NativeMethods).GetMethods(BindingFlags.NonPublic | BindingFlags.Static)
            .SingleOrDefault(method => method.Name == WrapperName(entryPoint) && method.ReturnType == typeof(CodexStatus));
        Require(wrapper is not null, $"{entryPoint}: exact production wrapper exists");
        var probe = new DynamicMethod($"Probe{wrapper!.Name}", typeof(CodexStatus), Type.EmptyTypes,
            typeof(ConversationParity).Module, skipVisibility: true);
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

    private static void CompletePending(string description) =>
        Require(NativeTestCompleteLeafOperation(0) == CodexStatus.Ok, $"{description} completes through native callback");

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

    private static void RequireExactMessages(IReadOnlyList<CodexMessage> values, string first, string second, string third, string description) =>
        Require(ExactMessages(values, first, second, third, description), $"{description} projects exact immutable values");

    private static bool ExactMessages(IReadOnlyList<CodexMessage> values, string first, string second, string third, string description)
    {
        if (values.Count != 3 || values[0].Id != first || values[1].Id != second || values[2].Id != third) return false;
        var expected = new[] { first, second, third };
        for (var index = 0; index < values.Count; index++)
        {
            var value = values[index];
            var id = expected[index];
            if (value.ClientMessageId != id.Replace("message-", "client-", StringComparison.Ordinal) ||
                value.Text != id.Replace("message-", "hello-", StringComparison.Ordinal) ||
                value.Role != CodexMessageRole.Assistant || value.CollaborationMode != CodexCollaborationMode.Plan ||
                value.Reasoning != id.Replace("message-", "reason-", StringComparison.Ordinal) ||
                value.Plan != id.Replace("message-", "plan-", StringComparison.Ordinal) ||
                value.ShellCommand != id.Replace("message-", "pwd-", StringComparison.Ordinal) ||
                value.ExitCode != (id == "message-beta" ? 8 : 7) ||
                !value.Capabilities.SetEquals([CodexCapability.WebSearch]) ||
                value.Invocations is not [CodexInvocation.Plugin { Name: "plugin", Uri: "plugin://plugin@market" },
                    CodexInvocation.Skill { Name: "skill", Path: "skill.md" }]) return false;
        }
        if (values is IList<CodexMessage> list)
        {
            try { list[0] = values[0]; return false; }
            catch (NotSupportedException) { }
        }
        _ = description;
        return true;
    }

    private static void RequireOrderedImmutable<T>(IReadOnlyList<T> values, Func<T, string> key,
        string first, string second, string third, string description)
    {
        Require(values.Count == 3 && key(values[0]) == first && key(values[1]) == second && key(values[2]) == third,
            $"{description} preserves exact order and duplicate");
        if (values is IList<T> list)
        {
            try { list[0] = values[0]; throw new InvalidOperationException($"{description} is mutable"); }
            catch (NotSupportedException) { }
        }
    }

    private static void Mark(ISet<string> executed, int index) =>
        Require(executed.Add($"{Prefix}{index:000}"), $"duplicate conversation capability execution: {index:000}");

    [DllImport("codex_agent", EntryPoint = "codex_agent_test_complete_leaf_operation", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus NativeTestCompleteLeafOperation(nint context);
    [DllImport("codex_agent", EntryPoint = "codex_agent_test_advance_active_subscription", CallingConvention = CallingConvention.Cdecl)]
    private static extern CodexStatus NativeTestAdvanceActiveSubscription(nint context);

    private static void LocalOnlyProbe() { }
    private static void RequireThrows(Action action)
    {
        try { action(); }
        catch (InvalidOperationException) { return; }
        throw new InvalidOperationException("fail-closed conversation evidence negative unexpectedly passed");
    }
    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
