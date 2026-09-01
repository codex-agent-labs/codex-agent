# Language and platform support

Version `0.2.0` is not tagged or published yet. The coordinates and asset names
below describe the release payload assembled by this repository; until that
release exists, consume locally built artifacts rather than a public registry.

All language surfaces project the same canonical user-facing
`CodexHost` → `CodexAgent` → `CodexConversation` contract. Platform/runtime SPI
is intentionally not part of every language SDK. The first and last columns of
this table are mechanically checked against the exact binding set used by the
M11 parity audit.

<!-- binding-support:start -->
| Contract ID | Language surface and distribution | Supported execution | Async, state, failure, and ownership projection | Required receipt |
| --- | --- | --- | --- | --- |
| `kotlin` | Maven `io.github.codex-agent-labs:codex-agent:0.2.0` plus one runtime adapter | Android 26+ Arm64; iOS 15+ Arm64 and Apple Silicon Simulator; JVM and Kotlin/Native on the five desktop hosts; Kotlin/JS and Kotlin/WasmJS on Node only | `suspend`, `StateFlow`, `CodexOperationException`/`CodexFailure`, explicit `close()` | `kotlin-parity.json` |
| `java` | The same core and Android/Desktop Maven artifacts; Java 17 | Android 26+ Arm64 and JVM Desktop/Host on macOS Arm64/x64, Linux Arm64/x64, and Windows x64 | `CompletableFuture`, current getters plus `CodexJavaObservation` callbacks, structured failures, `closeAsync()` and `AutoCloseable` observations | `java-parity.json` |
| `swift` | `CodexAgent-0.2.0.xcframework.zip`; Swift 5.9 package products `CodexAgent`, `CodexAgentAuthentication`, `CodexAgentObservation`, and `CodexAgentSwiftSupport` | iOS 15+ on iPhoneOS Arm64 and Apple Silicon Simulator Arm64 | native `async throws`, typed `AsyncStream`, `Error.codexFailure`, explicit asynchronous close | `swift-parity.json` |
| `objective-c` | The same `CodexAgent` XCFramework and Swift package binary target | iOS 15+ on iPhoneOS Arm64 and Apple Silicon Simulator Arm64 | completion blocks, current-value observation callbacks/tokens, `NSError` plus structured failure accessors, explicit close | `objective-c-parity.json` |
| `javascript-typescript` | npm `@codex-agent-labs/codex-agent@0.2.0`, with ESM, CommonJS, and reviewed declarations | Node.js `>=24.18.0 <25` on macOS Arm64/x64, Linux Arm64/x64, and Windows x64 | `Promise`, `AbortSignal`, synchronous current state plus callback observations, `CodexError`/`CodexFailure`, sync and async disposal | `javascript-typescript-parity.json` |
| `c-abi` | Maven `codex-agent-runtime-desktop:0.2.0` classifiers `c-abi-macos-arm64`, `c-abi-macos-x64`, `c-abi-linux-arm64`, `c-abi-linux-x64`, and `c-abi-windows-x64`; [contract](../codex-agent-runtime-desktop/native/c-api/README.md) | Native applications on the five desktop hosts | versioned `codex_agent_*` ABI, opaque handles, callbacks, cancellation, current state/subscriptions, status plus typed failure getters, explicit destroy/release | `c-abi-parity.json` |
| `python` | Planned GitHub release assets: five `codex-agent` wheels plus one sdist; import `codex_agent`; Python 3.11+ | CPython on macOS Arm64/x64, Linux Arm64/x64, and Windows x64 | `await`, cancellable operations, `StateStream.current` plus async iteration, typed exceptions/structured failures, semantic Host/Conversation async contexts followed by child-token release | `python-parity.json` |
| `csharp` | Planned GitHub release asset `CodexAgent.0.2.0.nupkg`; namespace/package `CodexAgent`; .NET 8+ | .NET on RIDs `osx-arm64`, `osx-x64`, `linux-arm64`, `linux-x64`, and `win-x64` | `Task`, `CancellationToken`, current properties plus `IAsyncEnumerable`, typed exceptions/structured failures, semantic Host/Conversation close followed by bounded `IDisposable`/`IAsyncDisposable` token cleanup | `csharp-parity.json` |
| `rust` | Planned GitHub release asset `codex-agent-0.2.0.crate`; crate/import `codex-agent`/`codex_agent`; Rust 1.95+ | Native Rust on `osx-arm64`, `osx-x64`, `linux-arm64`, `linux-x64`, and `win-x64` | `Future`, explicit cancellation, `CodexStateStream`, `CodexError`/`CodexFailure`, semantic Host/Conversation close before RAII child-token drop | `rust-parity.json` |
| `cpp` | Five planned target-specific GitHub release ZIPs `codex-agent-cpp-0.2.0-<classifier>.zip`; CMake 3.24+ target `CodexAgent::CodexAgent`; C++20 | Native C++ on `macos-arm64`, `macos-x64`, `linux-arm64`, `linux-x64`, and `windows-x64` | `AsyncOperation`, cancellation, typed current state/subscriptions, `OperationError`/structured failure, semantic Host/Conversation `close().get()` before move-only RAII child-token destruction | `cpp-parity.json` |
| `dart` | Planned GitHub release asset `codex-agent-dart-0.2.0.tar.gz`; package/import `codex_agent`/`package:codex_agent/codex_agent.dart`; Dart `>=3.6.0 <4.0.0` | Desktop Dart VM on macOS Arm64/x64, Linux Arm64/x64, and Windows x64 | `Future`, `CodexCancellation`, current-state `Future` plus broadcast streams, typed exceptions/structured failures, `Host.close()`/`closeConversation()` semantics followed by token `dispose()` | `dart-parity.json` |
<!-- binding-support:end -->

## Native wrapper installation and library resolution

The publication workflow will attach the Python, C#, Rust, C++, and Dart
packages as GitHub release assets. It will not upload them to PyPI, NuGet.org,
crates.io, a CMake registry, or pub.dev.

- Python: install the wheel matching the current host with
  `python -m pip install ./codex_agent-0.2.0-*.whl`. Resolution order is the
  `library_path` constructor argument, `CODEX_AGENT_LIBRARY`, then the wheel's
  `codex_agent/native/<classifier>/` directory.
- C#: add `CodexAgent.0.2.0.nupkg` as a local NuGet source. Call
  `CodexNativeLibrary.Configure(path)` before first use to override the packaged
  `runtimes/<rid>/native/` asset.
- Rust: extract `codex-agent-0.2.0.crate` or use it through a local package
  source. Resolution order is `CODEX_AGENT_LIBRARY`, an executable-adjacent
  library, then `runtimes/<target>/native/`; stage the matching verified crate
  asset into one of those deployment locations.
- C++: unpack the ZIP for the current classifier and add its prefix to
  `CMAKE_PREFIX_PATH`; then use `find_package(CodexAgent 0.2 REQUIRED)` and
  `CodexAgent::CodexAgent`.
- Dart: extract the release archive and use a local path dependency. Resolution
  order is `libraryPath`, `CODEX_AGENT_LIBRARY`, then
  `lib/src/native/<classifier>/`.

Every native wrapper rejects an unsupported host or incompatible ABI. Explicit
paths never fall back to an arbitrary system library. The release packages bind
the same verified C ABI `1.13.0` native bytes and their manifest/evidence files.

## Equivalent lifecycle examples

The executable consumer examples are the source of truth; package and CI tests
compile or analyze every file below so documentation cannot drift into
pseudocode:

- [Python](../codex-agent-bindings/python/consumer/lifecycle_example.py)
- [C#](../codex-agent-bindings/csharp/samples/CodexAgent.Consumer/Program.cs)
- [Rust](../codex-agent-bindings/rust/consumer/src/bin/lifecycle_smoke.rs)
- [C++](../codex-agent-bindings/cpp/consumer/lifecycle_example.cpp)
- [Dart](../codex-agent-bindings/dart/example/main.dart)

Examples need an authenticated matching-host runtime bundle to start the real
App Server. Deterministic CI compiles or analyzes every example and exercises
the equivalent lifecycle with binding test fixtures; Python, Rust on
macOS/Linux, and C++ execute the linked examples directly. Separate
installed-package Host smokes execute against the exact packaged C SDK; they
intentionally do not pretend an empty bundle can reach READY.

## Unsupported execution

Browser JavaScript, browser Wasm, WASI, remote execution, cloud execution, and
any caller-managed daemon, sidecar, gateway, HTTP server, or second JSON-RPC
service are not supported. Desktop/Host itself manages its verified App Server
child process. Node is an adapter under Desktop/Host, not a separate execution
model. Dart support is the desktop VM package only; Flutter and AOT packaging
remain unverified and unsupported. Intel iOS Simulator is unsupported.
