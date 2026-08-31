# CodexAgent

The `CodexAgent` package and namespace are the .NET 8+ projection of the local
Codex Agent Desktop/Host C SDK. Before version `<sdkVersion>` is published, add
the release `CodexAgent.<sdkVersion>.nupkg` as a local NuGet source. The package uses
`Task`, `IAsyncEnumerable<T>`, cancellation tokens, and deterministic
`IDisposable`/`IAsyncDisposable` ownership.

Supported runtime identifiers are `osx-arm64`, `osx-x64`, `linux-arm64`,
`linux-x64`, and `win-x64`.
Call `CodexNativeLibrary.Configure(path)` once before first use to select an
explicit verified library. Otherwise resolution checks the application base
directory and then `runtimes/<rid>/native/`; there is no environment-variable
or system-loader fallback. The loader requires compatible C ABI `1.12.0`.

```csharp
await using var host = CodexHost.Create(new CodexHostOptions(
    bundleDirectory,
    dataDirectory,
    new CodexClientInfo("my-app", "My app", "1.0")));

await host.StartAsync(cancellationToken);
if (host.State.Agent is { } agent)
{
    await using var conversation = await agent.Conversations.OpenAsync(
        cancellationToken: cancellationToken);
    await conversation.SendAsync("Hello", cancellationToken);
}
```

Use `ObserveStatesAsync()` and `ObserveActiveConversationAsync()` for
current-value-first state streams. Native callbacks stay rooted until the C
SDK confirms operation or subscription quiescence.

Synchronous `Dispose()` releases an object that is already closed. Prefer
`await using` or `DisposeAsync()` for open hosts and conversations so the
canonical asynchronous close finishes before native ownership is released.
Concurrent `DisposeAsync()` calls share the same close-and-release completion.
Native release failures are quarantined and exposed through
`CodexNativeLibrary.CleanupIssues`.
Synchronous ABI calls raise `CodexException`, asynchronous structured failures
raise `CodexOperationException`, and ABI mismatch raises `CodexAbiException`.
Semantic close is distinct from releasing the owned ABI token.

MCP values are immutable managed projections of the same C ABI value handles:

```csharp
var transport = new CodexMcpTransport.Http(
    "https://example.com/mcp",
    bearerTokenEnvironmentVariable: "MCP_TOKEN");
var server = new CodexMcpServerConfiguration(
    "example",
    transport,
    authentication: CodexMcpAuthentication.Oauth,
    oauth: new CodexMcpOauthConfiguration(callbackPort: 8080));
```

Lists and maps are defensively copied, and nullable collections preserve the
difference between absent and present-empty native values.

Ordinary canonical values use the same immutable projection. For example:

```csharp
var steps = new[] { new CodexPlanStep("Compile", CodexPlanStepStatus.Completed) };
var progress = new CodexTurnProgress(
    planProgress: new CodexPlanProgress("Done", steps));
var plugin = new CodexPluginReference("id", "example", "marketplace");

Console.WriteLine(progress.PlanProgress?.Steps[0].Text);
Console.WriteLine(plugin.Uri); // plugin://example@marketplace
```

The package's exact 556-capability inventory covers all 110 canonical enum
entries, the 46-capability MCP graph, 134 complementary ordinary immutable
constructor/property capabilities, and a further 175 constructor/property/
object capabilities across 45 dependency-closed value owners. Eleven additional
synchronous value functions call their exact `codex_agent_*` C ABI entry points;
compiled call edges, import metadata, real-SDK execution, and per-capability
receipts are checked mechanically. Forty-two leaf-service capabilities add
native-backed async operations, current-value-first state streams, exact live
pending identity, structured failures, cancellation, and deterministic owned
service handles. Their compiled call graphs, 112 real-SDK invalid-boundary calls
covering all 83 unique exact C-header symbols, full managed behavior scenarios,
and canonical C ABI success-behavior rows are checked per capability. Twenty
conversation/catalog capabilities add list/read/rename/delete/open, live active
identity, conversation operations, and all derived current-value-first states.
Their exact compiled graphs cover 49 per-capability references to 39 C symbols;
fake and real-SDK receipts prove copied inputs, async/cancellation/failure,
identity, ordered immutable collections, nullable and state transitions,
ownership, and repeated disposal per capability. Eleven `CodexAgent` properties
add identity-stable service facades, conversations, and an immutable copied
workspace snapshot. Their exact compiled getter paths, real-SDK boundaries,
stable identity, and parent-close ownership are checked per capability. Seven
Host/READY capabilities add copied creation and workspace selection, async
start/selection/close outcomes, current/subsequent/terminal lifecycle state,
stable READY Agent identity, duplicate-alias release, and child-before-parent
disposal. Enum metadata is exposed through
`CodexEnumMetadata`; singleton sealed variants use an `Instance` property.
