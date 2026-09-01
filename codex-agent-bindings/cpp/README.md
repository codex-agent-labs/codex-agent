# CodexAgent C++

This directory contains the C++20 projection of the verified desktop C SDK and
requires CMake 3.24+. It does not implement a runtime or protocol.
`CodexAgent::CodexAgent` loads the packaged platform C SDK by its exact absolute
path after validating its package hash and runtime identity, and adds move-only RAII
handles, typed failures, cancellable future-like operations, and typed state
subscriptions.

Before `<sdkVersion>` is published, unpack the matching locally built archive
`codex-agent-cpp-<sdkVersion>-<classifier>.zip`, add its prefix to
`CMAKE_PREFIX_PATH`, and consume the installed package:

```cmake
find_package(CodexAgent CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE CodexAgent::CodexAgent)
```

The verified embedded Runtime is the default. To select a compatible external
Runtime explicitly, call `codex_agent::CodexNativeLibrary::configure(absolutePath)`
before the first CodexAgent API call. The wrapper never searches `PATH`, the
current directory, or a bare system-library name. `CodexAgent::C` remains
available only for applications that intentionally want the raw C ABI target.

When consuming from source, set `CodexAgent_C_SDK_ROOT` and
`CodexAgent_NATIVE_CLASSIFIER` to the verified classifier directory and its
exact ID. Classifier IDs are
`macos-arm64`, `macos-x64`, `linux-arm64`, `linux-x64`, and `windows-x64`.
Parity-test configuration additionally requires the compiler-derived Contract
report as `CodexAgent_CANONICAL_API_REPORT` and passed C ABI fixture evidence
as `CodexAgent_C_ABI_BOOTSTRAP_EVIDENCE`. No source-tree or build-directory
fallback is used for any of these inputs.

Host and conversation `close()` calls are explicit asynchronous lifecycle
operations and must complete with `.get()` before destruction. Destructors are
`noexcept` and may block while retrying a `BUSY` token release; token release is
not semantic close. Semantically close Conversation first and Host while final
Agent/service wrappers remain alive, then destroy child wrappers before Host;
destroying a final current child token while Host is READY can remain `BUSY`.
Destroying an unfinished `AsyncOperation` requests
cancellation and waits for completion. Subscription close may wait for callback
quiescence, while callback-thread disposal delegates that cleanup safely.

The executable [lifecycle example](https://github.com/codex-agent-labs/codex-agent/blob/main/codex-agent-bindings/cpp/consumer/lifecycle_example.cpp)
is built against the extracted installed CMake package and run with the
repository C ABI fixture. A separate Host smoke executes the packaged native
library.

The typed surface in this package currently covers:

- `Host` → move-only `HostStateReady` → `Agent` → `Conversations` →
  `Conversation` ownership;
- host construction with copied paths/client information, start, copied
  workspace selection, current and observed state, Ready Agent projection, and
  repeated close;
- conversation open/list/read/rename/delete, active-conversation observation,
  prompt and structured-request send, shell commands, reload, turn
  cancellation, full and derived state observation, identity, and close;
- immutable workspace and conversation-summary values;
- all 110 canonical enum entries across 30 typed `enum class` projections;
- canonical form, elicitation, interaction-state, and authorization-URL
  synchronous behavior delegated to the exact C ABI operations;
- all 42 currently frozen leaf-service capabilities across authentication,
  models, skills, hooks, plugins, connectors, MCP servers, integration
  authorization, and interactions, including typed async cancellation, current
  and observed state, strict pending-interaction ownership, and nullable value
  projection;
- structured failures, cancellation, future-like completion, and callback-safe
  subscription disposal.

The package currently carries exactly 556 mechanically checked C++ capability
claims. Its bundled and installed typed consumers execute the 7 Host/Ready,
11 Agent, 42 leaf-service, and 20 conversation rows through the production
wrapper API with repository fixtures. Separate real-SDK gates execute Host
create/current/repeated close and connect typed members to the packaged native
library through invalid-boundary probes over all 12 Host/Ready, 11 Agent, 112
leaf-service, and 49 conversation C references; they do not claim a real READY
Agent/Conversation success lifecycle.
Tests cover async success/failure and structured cancellation,
current/subsequent/terminal state delivery and post-close quiescence, identity,
parent-child ownership, repeated close, nullability, ordered collections, and
value conversion. Future canonical API additions still fail parity until their
own C++ projection and evidence are added; raw C-header access is never counted
as idiomatic C++.
