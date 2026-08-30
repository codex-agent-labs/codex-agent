# CodexAgent for .NET

This directory contains the .NET 8 projection of the stable
`codex_agent_*` desktop C ABI. The locally built release artifact is
`CodexAgent.0.2.0.nupkg`; it is not claimed as published to NuGet.org. It does
not implement a runtime or protocol.

The managed package is `CodexAgent` and uses the `CodexAgent` namespace. Native
release packaging stages the verified C SDK under `native/<rid>/` for these
runtime identifiers:

- `osx-arm64`
- `osx-x64`
- `linux-arm64`
- `linux-x64`
- `win-x64`

Inside the NuGet package those files are under `runtimes/<rid>/native/`.
`CodexNativeLibrary.Configure(path)` overrides application-base and packaged
RID resolution before first use; there is no environment or system fallback.
The loader requires compatible C ABI `1.12.0`.

The current mechanically checked surface contains 556 exact capabilities: 110
ordinary enum entries, 46 MCP immutable-value capabilities, a complementary
134-capability immutable-value slice, the audited 175-capability residual
constructor/property/object slice across 45 owners, and 11 synchronous value
functions, 42 authentication, interaction, integration-authorization,
model, skill, hook, plugin, connector, and MCP-server leaf-service capabilities,
plus 20 conversation/catalog capabilities, all 11 `CodexAgent` properties, and
the seven canonical `CodexHost`/READY capabilities.
It covers conversation and
interaction state, messages, turns, forms and elicitations, authentication,
integrations, hooks, models, plans, plugins, skills, connectors, workspace
resolution, and structured failures. Every capability has its own public
symbol, executed test ID, exact reviewed C header references, and passed
canonical C ABI fixture references.

The 11 synchronous functions are thin native projections. The harness inspects
the compiled public-to-bridge-to-wrapper call edge and each wrapper's exact
`LibraryImport` entry point, then records the wrapper actually executed against
the real C SDK. A managed trace or local-only implementation cannot produce the
receipt.

The 42 leaf-service capabilities are also thin projections. Each capability
has an exact compiled public-member-to-production-wrapper-to-`LibraryImport`
graph, real-SDK invalid-boundary receipts for every one of its exact C-header
references (112 per-capability references to 83 unique symbols), and a passed
canonical C ABI success-behavior row. The local fake exercises every claimed
managed scenario: typed async results, cancellation, structured failure,
current/subsequent/terminal state, subscription cancellation, immutable ordered
duplicates, nullability, live pending identity, parent-child retention, and
repeated disposal.

The 11-property `CodexAgent` slice exposes identity-stable authentication,
connector, conversation, hook, integration-authorization, interaction, MCP,
model, plugin, and skill facades plus an immutable copied workspace snapshot.
Compiled getter paths reach the exact 11 C entry points; managed tests prove
stable identity and parent-close invalidation, and the real-SDK receipt executes
every null boundary.

The seven-capability Host/READY slice covers creation, async start, workspace
selection and close, current-value-first lifecycle state, and the READY value's
stable Agent. Its compiled graphs cover 10 per-capability references to nine C
symbols. Managed tests exercise copied inputs, success, cancellation, structured
failure, current/subsequent/terminal delivery, duplicate retained-alias release,
parent retention and parent-close invalidation before final child-token release,
and repeated close/dispose; real-SDK receipts execute every referenced null
boundary.

The 20-capability conversation slice projects catalog list/read/rename/delete/
open operations, live active-conversation identity, conversation operations,
and every current-value-first derived state. Its method-scoped compiled call
graphs cover all 49 per-capability references to 39 exact C symbols. The fake
executes copied-input rejection, typed async results, cancellation, structured
failure, identity, immutable ordered duplicates, nullable transitions,
current/subsequent/terminal delivery, subscription cancellation, ownership,
and repeated close/dispose. A separate real-SDK receipt executes the null
boundary for every exact header reference.

All projected collections are defensively copied while preserving order and
duplicates. Nullable values, empty collections, derived values such as plugin
URIs and validation state, and canonical defaults remain explicit.

Local verification uses small C ABI fixtures that deliberately exercise
callback-before-return, cancellation, current-value state subscriptions,
structured failures, identity, nullability, bounded disposal, and cleanup-failure
quarantine through `CodexNativeLibrary.CleanupIssues`:

```sh
dotnet build tests/CodexAgent.Tests/CodexAgent.Tests.csproj --configuration Release
dotnet run --project tests/CodexAgent.Tests/CodexAgent.Tests.csproj --configuration Release --no-build
dotnet run --project tests/CodexAgent.Tests/CodexAgent.Tests.csproj \
  --configuration Release \
  -p:CodexAgentRealSdkPath=/path/to/libcodex_agent \
  -- --real-mcp-values /path/to/libcodex_agent
dotnet pack src/CodexAgent/CodexAgent.csproj --configuration Release --output artifacts
dotnet restore samples/CodexAgent.Consumer/CodexAgent.Consumer.csproj --force
dotnet build samples/CodexAgent.Consumer/CodexAgent.Consumer.csproj --configuration Release --no-restore
dotnet run --project samples/CodexAgent.Consumer/CodexAgent.Consumer.csproj \
  --configuration Release --no-build -- /path/to/libcodex_agent release-only
```

The harness emits deterministic `compiler-evidence.tsv` and
`executed-tests.tsv` files below its ignored Release output, plus exact
`synchronous-native-tests.tsv`, `leaf-native-tests.tsv`,
`conversation-native-tests.tsv`, `agent-native-tests.tsv`, and
`host-native-tests.tsv` real-SDK receipts.
Every MCP, leaf-service, conversation, Agent, and Host/READY claim
resolves its `c-header:` symbol against the compiled public header and its
`cabi-fixture:` test against a passed native test in the canonical bootstrap
evidence.

Use `release-only` with a real C SDK library to verify bounded synchronous
rejection followed by asynchronous close and release without requiring a
prepared runtime bundle. The sample's `lifecycle` mode uses the repository test
fixture and fixed fixture paths; a real lifecycle invocation needs a prepared
bundle, data directory, and selectable workspace.

Release packing is fail-closed when any verified native asset is absent:

```sh
dotnet pack src/CodexAgent/CodexAgent.csproj \
  --configuration Release \
  -p:CodexAgentRequireNativeAssets=true
```
