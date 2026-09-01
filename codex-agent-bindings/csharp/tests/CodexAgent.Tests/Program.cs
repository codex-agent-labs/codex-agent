using CodexAgent;
using CodexAgent.Interop;
using System.Runtime.InteropServices;
using System.Text.Json;

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static async Task RequireOpenDisposeRejected(Action dispose, string description)
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
    Require(rejected, $"synchronous disposal released an open {description}");
}

static async Task RequireNativeFailure(Task task, CodexStatus status, string description)
{
    try
    {
        await task;
        throw new InvalidOperationException($"{description} completed successfully");
    }
    catch (CodexException error)
    {
        Require(error.Status == status, $"{description} status");
    }
}

static string[][] ReadCapabilityClaims()
{
    var path = Path.Combine(AppContext.BaseDirectory, "parity", "capability-claims.tsv");
    var lines = File.ReadAllLines(path);
    Require(lines.Length > 1, "capability claims are not empty");
    Require(lines[0] == "capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios", "exact capability-claims header");
    var rows = lines.Skip(1).Select(line => line.Split('\t')).ToArray();
    Require(rows.All(columns => columns.Length == 5 && columns.All(column => column.Length != 0)),
        "each capability claim has exactly five nonempty columns");
    foreach (var cell in rows.SelectMany(row => row.Skip(1)))
    {
        var values = cell.Split(',');
        Require(values.SequenceEqual(values.Order(StringComparer.Ordinal)), $"claim evidence is sorted: {cell}");
        Require(values.Distinct(StringComparer.Ordinal).Count() == values.Length, $"claim evidence is unique: {cell}");
    }
    Require(rows.Select(columns => columns[0]).Distinct(StringComparer.Ordinal).Count() == rows.Length,
        "capability keys are unique");
    Require(rows.Select(columns => columns[0]).SequenceEqual(rows.Select(columns => columns[0]).Order(StringComparer.Ordinal)),
        "capability claims are deterministically sorted");
    return rows;
}

static HashSet<string> ReadCanonicalCapabilities()
{
    var parityDirectory = Path.Combine(AppContext.BaseDirectory, "parity");
    using var canonical = JsonDocument.Parse(File.ReadAllText(Path.Combine(parityDirectory, "canonical-api.json")));
    var capabilities = canonical.RootElement.GetProperty("owners")
        .EnumerateArray()
        .SelectMany(owner => owner.GetProperty("capabilities").EnumerateArray())
        .Select(capability => capability.GetString() ?? throw new InvalidDataException("null canonical capability"))
        .ToHashSet(StringComparer.Ordinal);
    Require(capabilities.Count == 556, "canonical API audit must contain exactly 556 members");
    return capabilities;
}

static void VerifyOrdinaryEnumCapabilities(
    IReadOnlyList<string[]> allClaimRows,
    ISet<string> canonicalCapabilities,
    ISet<string> executedTestIds)
{
    var canonicalEnumCapabilities = canonicalCapabilities
        .Where(capability => capability.Contains("|kind=enum-entry|", StringComparison.Ordinal))
        .ToHashSet(StringComparer.Ordinal);
    var claimRows = allClaimRows.Where(columns => canonicalEnumCapabilities.Contains(columns[0])).ToArray();
    Require(claimRows.Length == 110, "exact enum claim count");
    Require(claimRows.Select(columns => columns[1]).Distinct(StringComparer.Ordinal).Count() == claimRows.Length,
        "enum public symbols are unique");
    Require(claimRows.Select(columns => columns[2]).Distinct(StringComparer.Ordinal).Count() == claimRows.Length,
        "enum executed test IDs are unique");
    Require(canonicalEnumCapabilities.SetEquals(claimRows.Select(columns => columns[0])),
        "enum claims exactly match compiler-discovered canonical enum capabilities");
    Require(CodexTestNative.EnumCount() == (nuint)claimRows.Length,
        "C header compiler evidence count matches enum claims");

    for (var index = 0; index < claimRows.Length; index++)
    {
        var columns = claimRows[index];
        var capabilityKey = columns[0];
        var publicSymbol = columns[1];
        var testId = columns[2];
        Require(columns[1].Split(',').Length == 1 && columns[2].Split(',').Length == 1,
            $"{testId}: ordinary enum has exactly one symbol and test");
        Require(columns[3] == $"c-header-enum:{index}",
            $"{testId}: stable C ABI evidence index for {capabilityKey}");
        Require(columns[4] == "value-conversion", $"{testId}: exact shared scenario");
        var memberSeparator = publicSymbol.LastIndexOf('.');
        Require(memberSeparator > 0, $"{testId}: valid public symbol for {capabilityKey}");
        var typeName = publicSymbol[..memberSeparator];
        var memberName = publicSymbol[(memberSeparator + 1)..];
        var type = Type.GetType($"{typeName}, CodexAgent", throwOnError: false);
        Require(type is { IsPublic: true, IsEnum: true },
            $"{testId}: public enum type exists for {capabilityKey}");
        var member = type!.GetField(memberName, System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
        Require(member is not null && member.IsLiteral,
            $"{testId}: exact public enum member exists for {capabilityKey}");
        var status = CodexTestNative.EnumValue((nuint)index, out var cAbiValue);
        Require(status == CodexStatus.Ok,
            $"{testId}: C header compiler evidence is readable for {capabilityKey}");
        Require(Convert.ToInt32(member!.GetRawConstantValue()) == cAbiValue,
            $"{testId}: C# value equals exact C header value for {capabilityKey}");
        Require(executedTestIds.Add(testId), $"{testId}: executed once for {capabilityKey}");
    }
    Console.WriteLine("CodexAgent C# ordinary enum capability tests passed: 110/110.");
}

if (args is ["--runtime-loader-embedded-child", var library, var compatibility, var target, var snapshotRoot])
{
    NativeLibraryLoader.LoadEmbeddedForTests(
        library, File.ReadAllText(compatibility), target, snapshotRoot);
    Console.WriteLine("CodexAgent C# embedded Runtime child load passed.");
    return;
}

if (args is ["--runtime-loader-security"])
{
    RuntimeLoaderSecurity.Verify();
    var fileName = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
        ? "codex_agent.dll"
        : RuntimeInformation.IsOSPlatform(OSPlatform.OSX)
            ? "libcodex_agent.dylib"
            : "libcodex_agent.so";
    CodexNativeLibrary.Configure(Path.Combine(AppContext.BaseDirectory, fileName));
    RuntimeLoaderSecurity.VerifyNative();
    return;
}

var capabilityClaims = ReadCapabilityClaims();
var canonicalCapabilities = ReadCanonicalCapabilities();
if (args is ["--real-mcp-values", var realSdkPath])
{
    McpValueParity.VerifyNative(realSdkPath, capabilityClaims, canonicalCapabilities);
    var executed = new HashSet<string>(StringComparer.Ordinal);
    SynchronousValueFunctionParity.VerifyNative(capabilityClaims, canonicalCapabilities, executed);
    Require(executed.SetEquals(capabilityClaims
        .Where(row => row[2].StartsWith("csharp.function:", StringComparison.Ordinal))
        .Select(row => row[2])), "every synchronous value function ran against the real C SDK");
    SynchronousValueFunctionParity.WriteNativeEvidence(capabilityClaims, executed);
    LeafServiceParity.VerifyNative(capabilityClaims, canonicalCapabilities);
    ConversationParity.VerifyNative(capabilityClaims, canonicalCapabilities);
    AgentParity.VerifyNative(capabilityClaims, canonicalCapabilities);
    HostParity.VerifyNative(capabilityClaims, canonicalCapabilities);
    return;
}

Require(
    CodexNativeLibrary.RuntimeIdentifier is "osx-arm64" or "osx-x64" or "linux-arm64" or "linux-x64" or "win-x64",
    "supported RID");

var fakeLibraryName = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
    ? "codex_agent.dll"
    : RuntimeInformation.IsOSPlatform(OSPlatform.OSX)
        ? "libcodex_agent.dylib"
        : "libcodex_agent.so";
CodexNativeLibrary.Configure(Path.Combine(AppContext.BaseDirectory, fakeLibraryName));

var executedCapabilityTests = new HashSet<string>(StringComparer.Ordinal);
VerifyOrdinaryEnumCapabilities(capabilityClaims, canonicalCapabilities, executedCapabilityTests);
McpValueParity.VerifyManaged(capabilityClaims, canonicalCapabilities, executedCapabilityTests);
OrdinaryValueParity.Verify(capabilityClaims, canonicalCapabilities, executedCapabilityTests);
ResidualValueParity.Verify(capabilityClaims, canonicalCapabilities, executedCapabilityTests);
SynchronousValueFunctionParity.VerifyContract(capabilityClaims, canonicalCapabilities);
LeafServiceParity.VerifyContract(capabilityClaims, canonicalCapabilities);
ConversationParity.VerifyContract(capabilityClaims, canonicalCapabilities);
AgentParity.VerifyContract(capabilityClaims, canonicalCapabilities);
HostParity.VerifyContract(capabilityClaims, canonicalCapabilities);

await HostParity.VerifyManaged(executedCapabilityTests);

try
{
    _ = CodexHost.Create(new CodexHostOptions("", "data", new CodexClientInfo("test", "test", "1")));
    throw new InvalidOperationException("blank bundle directory accepted");
}
catch (ArgumentException)
{
    // Trust-boundary validation occurs before native calls.
}

var options = new CodexHostOptions(
    "/verified/bundle",
    "/tmp/codex-agent-dotnet-test",
    new CodexClientInfo("dotnet-test", ".NET lifecycle test", "1.0"));
await using var host = CodexHost.Create(options);

Require(host.State.Kind == CodexHostStateKind.New, "initial host state");
await host.StartAsync();
var ready = host.State;
Require(ready.Kind == CodexHostStateKind.Ready, "ready host state");
Require(ready.Workspace == new CodexWorkspace("/workspace", null), "nullable workspace display-name conversion");
Require(ready.Agent is not null, "ready agent");
Require(ReferenceEquals(ready.Agent, host.State.Agent), "stable agent identity");
await LeafServiceParity.VerifyManaged(ready.Agent!, executedCapabilityTests);
await ConversationParity.VerifyManaged(ready.Agent!, executedCapabilityTests);
var verifyAgentClosed = AgentParity.VerifyManaged(ready.Agent!, executedCapabilityTests);

using (var stateCancellation = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
{
    await using var states = host.ObserveStatesAsync(stateCancellation.Token).GetAsyncEnumerator();
    Require(await states.MoveNextAsync(), "host state subscription emits current value");
    Require(states.Current.Kind == CodexHostStateKind.Ready, "host state subscription projection");
}

var conversations = ready.Agent!.Conversations;
Require(conversations.ActiveConversation is null, "nullable active conversation");
var conversation = await conversations.OpenAsync(new CodexConversationOpenOptions(
    ApprovalPreset: CodexApprovalPreset.AskMe,
    ServiceTier: "fast"));
Require(conversation.State.Status == CodexConversationStatus.Ready, "conversation state projection");
Require(conversation.IsSame(conversation), "conversation identity");

await conversation.SendAsync("héllo");
await conversation.ReloadAsync();

try
{
    await conversation.SendAsync("fail");
    throw new InvalidOperationException("structured operation failure completed successfully");
}
catch (CodexOperationException error)
{
    Require(error.Failure == new CodexFailure("test_failure", "expected failure", true), "structured failure conversion");
}

using (var cancellation = new CancellationTokenSource())
{
    var command = conversation.RunShellCommandAsync("sleep", cancellation.Token);
    GC.Collect();
    GC.WaitForPendingFinalizers();
    cancellation.Cancel();
    try
    {
        await command;
        throw new InvalidOperationException("cancelled operation completed successfully");
    }
    catch (OperationCanceledException)
    {
        // The fake SDK completes cancellation inline before cancel returns.
    }
    await conversation.ReloadAsync();
}

using (var cancellation = new CancellationTokenSource())
{
    var command = conversation.RunShellCommandAsync("cancel-error", cancellation.Token);
    cancellation.Cancel();
    try
    {
        await command;
        throw new InvalidOperationException("native cancellation failure was ignored");
    }
    catch (CodexException error)
    {
        Require(error.Status == CodexStatus.InternalError, "native cancellation failure projection");
    }
    await conversation.ReloadAsync();
}

using (var stateCancellation = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
{
    await using var states = conversation.ObserveStatesAsync(stateCancellation.Token).GetAsyncEnumerator();
    Require(await states.MoveNextAsync(), "conversation state subscription emits current value");
    Require(states.Current.Status == CodexConversationStatus.Ready, "conversation subscription projection");
}

await conversation.CloseAsync();
await conversation.CloseAsync();
Require(conversation.State.Status == CodexConversationStatus.Closed, "closed conversation state");
conversation.Dispose();
conversation.Dispose();

var inFlightConversation = await conversations.OpenAsync();
using (var cancellation = new CancellationTokenSource())
{
    var command = inFlightConversation.RunShellCommandAsync("sleep", cancellation.Token);
    await RequireOpenDisposeRejected(inFlightConversation.Dispose, "conversation");
    cancellation.Cancel();
    try
    {
        await command;
        throw new InvalidOperationException("disposed-parent operation completed successfully");
    }
    catch (OperationCanceledException)
    {
        // Native operation destruction must finish before task completion is observable.
    }
    await inFlightConversation.ReloadAsync();
}

var replacementConversation = await conversations.OpenAsync();
try
{
    _ = inFlightConversation.State;
    throw new InvalidOperationException("replaced active conversation remained usable");
}
catch (ObjectDisposedException)
{
    // A→B disposes the old managed alias after canonical replacement closes it.
}
await replacementConversation.CloseAsync();
Require(conversations.ActiveConversation is null, "B→null clears the active wrapper");
try
{
    _ = replacementConversation.State;
    throw new InvalidOperationException("cleared active conversation remained usable");
}
catch (ObjectDisposedException)
{
    // Null projection releases the previous managed alias.
}

await RequireOpenDisposeRejected(host.Dispose, "host");

var firstHostDispose = host.DisposeAsync().AsTask();
var secondHostDispose = host.DisposeAsync().AsTask();
Require(ReferenceEquals(firstHostDispose, secondHostDispose), "host DisposeAsync coalesces");
await Task.WhenAll(firstHostDispose, secondHostDispose);
verifyAgentClosed();
try
{
    _ = host.State;
    throw new InvalidOperationException("disposed host remained usable");
}
catch (ObjectDisposedException)
{
    // Parent ownership closes the public tree.
}

var subscriptionHost = CodexHost.Create(options);
await subscriptionHost.StartAsync();
var subscriptionConversations = subscriptionHost.State.Agent!.Conversations;
var subscriptionConversation = await subscriptionConversations.OpenAsync();
var hostStates = subscriptionHost.ObserveStatesAsync().GetAsyncEnumerator();
var activeConversations = subscriptionConversations.ObserveActiveConversationAsync().GetAsyncEnumerator();
var conversationStates = subscriptionConversation.ObserveStatesAsync().GetAsyncEnumerator();
Require(await hostStates.MoveNextAsync(), "retained host subscription emits current value");
Require(await activeConversations.MoveNextAsync(), "retained conversations subscription emits current value");
Require(await conversationStates.MoveNextAsync(), "retained conversation subscription emits current value");
var firstConversationDispose = subscriptionConversation.DisposeAsync().AsTask();
var secondConversationDispose = subscriptionConversation.DisposeAsync().AsTask();
Require(ReferenceEquals(firstConversationDispose, secondConversationDispose), "conversation DisposeAsync coalesces");
await Task.WhenAll(firstConversationDispose, secondConversationDispose);
var firstSubscriptionHostDispose = subscriptionHost.DisposeAsync().AsTask();
var secondSubscriptionHostDispose = subscriptionHost.DisposeAsync().AsTask();
Require(ReferenceEquals(firstSubscriptionHostDispose, secondSubscriptionHostDispose), "subscribed host DisposeAsync coalesces");
await Task.WhenAll(firstSubscriptionHostDispose, secondSubscriptionHostDispose);
await conversationStates.DisposeAsync();
await activeConversations.DisposeAsync();
await hostStates.DisposeAsync();

var cleanupIssueStart = CodexNativeLibrary.CleanupIssues.Count;
var cleanupHost = CodexHost.Create(options);
await cleanupHost.StartAsync();
var cleanupConversations = cleanupHost.State.Agent!.Conversations;
var busyRelease = await cleanupConversations.OpenAsync(new CodexConversationOpenOptions("release-busy"));
var firstBusyDispose = busyRelease.DisposeAsync().AsTask();
var secondBusyDispose = busyRelease.DisposeAsync().AsTask();
Require(ReferenceEquals(firstBusyDispose, secondBusyDispose), "failed conversation DisposeAsync coalesces");
await RequireNativeFailure(firstBusyDispose, CodexStatus.Busy, "permanent BUSY release");
await RequireNativeFailure(secondBusyDispose, CodexStatus.Busy, "coalesced permanent BUSY release");
var unexpectedRelease = await cleanupConversations.OpenAsync(new CodexConversationOpenOptions("release-error"));
var unexpectedDispose = unexpectedRelease.DisposeAsync().AsTask();
await RequireNativeFailure(unexpectedDispose, CodexStatus.InternalError, "unexpected release failure");
var cleanupIssues = CodexNativeLibrary.CleanupIssues.Skip(cleanupIssueStart).ToArray();
Require(cleanupIssues.Length == 2, "both failed native releases are observable");
Require(cleanupIssues.Any(issue => issue is { Resource: "ConversationHandle", Status: CodexStatus.Busy }),
    "permanent BUSY release is quarantined");
Require(cleanupIssues.Any(issue => issue is { Resource: "ConversationHandle", Status: CodexStatus.InternalError }),
    "unexpected release status is quarantined");
await cleanupHost.DisposeAsync();

var contextIssueStart = CodexNativeLibrary.CleanupIssues.Count;
var busyContextHost = CodexHost.Create(options with
{
    ClientInfo = new CodexClientInfo("context-busy", ".NET context cleanup test", "1.0"),
});
var firstBusyContextDispose = busyContextHost.DisposeAsync().AsTask();
var secondBusyContextDispose = busyContextHost.DisposeAsync().AsTask();
Require(ReferenceEquals(firstBusyContextDispose, secondBusyContextDispose), "failed context DisposeAsync coalesces");
await RequireNativeFailure(firstBusyContextDispose, CodexStatus.Busy, "permanent BUSY context release");
await RequireNativeFailure(secondBusyContextDispose, CodexStatus.Busy, "coalesced permanent BUSY context release");
var unexpectedContextHost = CodexHost.Create(options with
{
    ClientInfo = new CodexClientInfo("context-error", ".NET context cleanup test", "1.0"),
});
await RequireNativeFailure(
    unexpectedContextHost.DisposeAsync().AsTask(),
    CodexStatus.InternalError,
    "unexpected context release failure");
var contextIssues = CodexNativeLibrary.CleanupIssues.Skip(contextIssueStart).ToArray();
Require(contextIssues.Length == 2, "both failed context releases are observable");
Require(contextIssues.Any(issue => issue is { Resource: "ContextHandle", Status: CodexStatus.Busy }),
    "permanent BUSY context release is quarantined");
Require(contextIssues.Any(issue => issue is { Resource: "ContextHandle", Status: CodexStatus.InternalError }),
    "unexpected context release status is quarantined");

SynchronousValueFunctionParity.ImportNativeEvidence(capabilityClaims, executedCapabilityTests);
LeafServiceParity.ImportNativeEvidence(capabilityClaims);
ConversationParity.ImportNativeEvidence(capabilityClaims);
AgentParity.ImportNativeEvidence(capabilityClaims);
HostParity.ImportNativeEvidence(capabilityClaims);
McpValueParity.EmitEvidence(capabilityClaims, executedCapabilityTests);
Console.WriteLine("CodexAgent .NET lifecycle and capability tests passed.");

internal static class CodexTestNative
{
    [DllImport("codex_agent", EntryPoint = "codex_agent_test_enum_count", CallingConvention = CallingConvention.Cdecl)]
    internal static extern nuint EnumCount();

    [DllImport("codex_agent", EntryPoint = "codex_agent_test_enum_value", CallingConvention = CallingConvention.Cdecl)]
    internal static extern CodexStatus EnumValue(nuint index, out int value);
}
