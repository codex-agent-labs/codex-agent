# Codex Agent for Dart

This `codex_agent` package requires Dart `>=3.6.0 <4.0.0`; import it as
`package:codex_agent/codex_agent.dart`. Before the selected SDK version is
published, consume a locally built `codex-agent-dart-<sdkVersion>.tar.gz`. It
is the desktop Dart VM projection of the canonical
`CodexHost -> CodexAgent -> CodexConversation` API. It loads the release-supplied
Codex Agent C SDK locally and does not run a daemon or introduce another
protocol.

```dart
final host = await CodexHost.create(
  bundleDirectory: '/path/to/codex-bundle',
  dataDirectory: '/path/to/app-data',
  clientInfo: CodexClientInfo(
    name: 'example',
    title: 'Dart example',
    version: '1.0.0',
  ),
);
try {
  await host.start();
  final ready = await host.states.firstWhere(
    (state) => state.kind == CodexHostStateKind.ready,
  );
  final agent = ready.agent!;
  final conversation = await agent.conversations.open();
  try {
    await conversation.send('Hello');
  } finally {
    try {
      await conversation.closeConversation();
    } finally {
      await conversation.dispose();
    }
  }
} finally {
  await host.close();
}
```

This compact example assumes the data directory restores a selected workspace.
If the Host reports `workspaceRequired`, call `selectWorkspace` before waiting
for `ready`.

`CodexAgent` exposes identity-stable `authentication`, `interactions`,
`integrationAuthorization`, `models`, `skills`, `hooks`, `plugins`,
`connectors`, `mcpServers`, and `conversations` projections. Its `workspace`
is an immutable copied snapshot. READY host snapshots are
`CodexReadyHostState` values and reuse one stable `CodexAgent` identity while
releasing duplicate retained aliases. The Host owns canonical Agent graph
shutdown. `CodexConversation.closeConversation()` is semantic close and
`dispose()` releases that token. `CodexAgent.close()`, service `close()`, and
`CodexConversations.close()` only release tokens and can remain `BUSY` while the
Host is READY; use `CodexHost.close()` for semantic graph shutdown before final
child-token release. Finalizers are fallback only.

Canonical immutable values are projected as ordinary Dart classes, sealed
families, enums, immutable `List`/`Set`/`Map` collections, and nullable Dart
types. For example, `CodexTurnRequest`, `CodexMessage`, `CodexElicitation`,
`CodexHook`, and the MCP transport/configuration graph preserve the canonical
ordering, nullability, derived identity, and validation semantics. API keys are
redacted by `toString`, authorization URLs fail closed, and singleton canonical
objects expose stable `instance` values.

Synchronous elicitation, form-validation, interaction-query, and authorization
URL operations use the same verified C SDK as `CodexHost`. They can be called
before a host is created. The loader accepts an exact `libraryPath` or
`CODEX_AGENT_LIBRARY` override, otherwise it selects the packaged classifier
library. It never falls back to a process or bare system-library name.

The release package must place the native library under
`lib/src/native/<classifier>/` for `macos-arm64`, `macos-x64`,
`linux-arm64`, `linux-x64`, and `windows-x64`. For local development,
pass `libraryPath` to `CodexHost.create` or set `CODEX_AGENT_LIBRARY`. The Dart
loader uses exactly that precedence followed by the packaged directory. It
requires ABI `1.13+` and Runtime identity schema 1. Before an embedded library
is loaded, its SHA-256, target, and component identity must match the packaged
`sdk-compatibility.json`. An explicit override may have different bytes and a
different component ID, but must prove the declared Contract, target, ABI, and
Runtime compatibility range through `codex_agent_runtime_identity`.

Operations return `Future` and accept explicit `CodexCancellation`. State has a
separate current-value `Future` plus current-value-first broadcast changes.
Synchronous ABI failures raise `CodexNativeException`; asynchronous failures
raise `CodexOperationException` with an optional structured failure. Close a
Conversation with `closeConversation()` before `dispose()`; close the Host with
`CodexHost.close()` before releasing final Agent/service/catalog tokens.

The external consumer can smoke-test an explicitly supplied matching-host C
SDK without a prepared runtime bundle:

```sh
cd consumer
dart pub get --enforce-lockfile
dart run bin/host_smoke.dart /absolute/path/to/libcodex_agent.dylib
```

The command verifies Host creation, the current initial state, asynchronous
repeated close, and disposed-handle behavior through the package's public API.

Parity verification consumes staged evidence rather than repository build
directories. Set `CODEX_AGENT_CANONICAL_API_REPORT`,
`CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE`, and `CODEX_AGENT_C_SDK_ROOT` (whose
`include/codex_agent.h` must exist). On macOS Arm64, the real-boundary receipt
also requires `CODEX_AGENT_REAL_LIBRARY`.

Only desktop Dart VM execution is supported. Browser JavaScript, browser
Wasm, WASI, remote execution, cloud execution, and unverified Flutter/AOT
packaging are not supported.

The Dart binding is licensed under GPL-3.0-or-later. The separately bundled
Codex App Server retains its own Apache-2.0 license.
