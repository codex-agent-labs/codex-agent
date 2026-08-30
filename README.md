# Codex Agent

Codex Agent is a reusable Kotlin Multiplatform host for the Codex App Server.
Applications construct one `CodexHost` with an official platform adapter. A
ready host supplies a `CodexAgent`, and the agent opens one active
`CodexConversation`. These three objects expose their own immutable observable
state and follow the runtime, agent, and conversation lifetimes respectively.

## Execution models and supported hosts

| Execution model | Runtime placement | Adapters and supported hosts |
| --- | --- | --- |
| Android | Packaged local process | Android |
| iOS | Embedded in-process | iOS Arm64 and Apple Silicon Simulator |
| Desktop/Host | Verified external process | JVM, Kotlin/Native, and Node adapters on macOS Arm64/x64, Linux Arm64/x64, and Windows x64 |

Kotlin/JS and Kotlin/WasmJS use the Node adapter within Desktop/Host; Node is
not a fourth execution model.

Browser JavaScript, browser Wasm, and WASI are not supported execution targets.
The runtime API does not provide remote or cloud execution, a gateway, or a
general-purpose shell.

## Modules

- `codex-agent-core` contains `CodexHost`, `CodexAgent`,
  `CodexConversation`, their public domain model, and the narrow runtime and
  extension contracts used by platform adapters.
- `codex-agent-runtime-android` verifies and launches the packaged Android App
  Server with its loopback proxy, certificate preparation, and SQLite privacy
  guard.
- `codex-agent-runtime-ios` embeds the pinned Rust App Server and confines its
  workspace tools to the selected sandbox or security-scoped folder.
- `codex-agent-runtime-desktop` supplies native and JVM adapters for the five
  supported desktop hosts plus the same local lifecycle to Kotlin/JS and
  Kotlin/WasmJS applications running on Node.js.

## Coordinates

```kotlin
implementation("io.github.codex-agent-labs:codex-agent:0.2.0")
implementation("io.github.codex-agent-labs:codex-agent-runtime-android:0.2.0")
implementation("io.github.codex-agent-labs:codex-agent-runtime-ios:0.2.0")
implementation("io.github.codex-agent-labs:codex-agent-runtime-desktop:0.2.0")
```

Version `0.2.0` has not yet been tagged or published.

The other implemented package surfaces are:

- Node-only npm package `@codex-agent-labs/codex-agent`;
- `CodexAgent-<version>.xcframework.zip` through SwiftPM products
  `CodexAgent`, `CodexAgentAuthentication`, `CodexAgentObservation`, and
  `CodexAgentSwiftSupport`;
- the stable C ABI and the Python, C#, Rust, C++, and Dart Desktop/Host
  projections packaged for the five native hosts;
- the five Desktop/Host App Server classifiers listed below.

See the mechanically checked [language and platform support](docs/SUPPORT_MATRIX.md)
for exact coordinates, compatibility floors, host classifiers, package asset
names, idiomatic async/state/failure/ownership mappings, and unsupported modes.
The publication workflow will attach the native wrapper packages as GitHub
release assets and will not upload them to language registries. No release
claim is final until strict five-host M11 evidence passes for the exact commit
and tree.

## Pre-release module migration

This is a clean migration with no forwarding modules or compatibility
artifacts.

- The Gradle project `:codex-agent-client` became `:codex-agent-core`. Its
  Maven root publication is
  `io.github.codex-agent-labs:codex-agent:<version>`, not
  `codex-agent-core`; no compatibility publication exists.
- The Gradle project `:codex-agent-runtime-node` was merged into
  `:codex-agent-runtime-desktop`. JVM, Kotlin/Native, Kotlin/JS-on-Node, and
  Kotlin/WasmJS-on-Node use that one Desktop/Host runtime and its five App
  Server classifiers; no `codex-agent-runtime-node` publication exists.

## Storage

Every official platform adapter accepts `storageRoots: CodexStorageRoots? =
null`. `null` uses the platform defaults below; an explicit value overrides
them, and `CodexStorageRoots()` disables library persistence.

| Platform | Cache root | State root |
| --- | --- | --- |
| Android | `cacheDir/codex-agent` | `noBackupFilesDir/codex-agent` |
| iOS | `Library/Caches/CodexAgent` | configured Application Support `codexHomePath` |
| Desktop | `dataDirectory/cache` | `dataDirectory/state` |
| Node | `dataDirectory/cache` | `dataDirectory/state` |

`CodexStorageArea` documents the stable subdirectories for plugin cache, shell
transcripts, and turn-input metadata. Platform-derived absolute paths remain
runtime configuration rather than enum constants.

## Packaged desktop runtimes

Desktop and Node applications ship exactly one matching classifier per host:

- `app-server-macos-arm64`
- `app-server-macos-x64`
- `app-server-linux-arm64`
- `app-server-linux-x64`
- `app-server-windows-x64`

Each classifier ZIP contains the pinned App Server, its matching process
supervisor, licenses, and a strict internal runtime manifest. Point the platform
adapter at the directory containing the ZIP; it selects the current target,
verifies every member, installs it atomically into the versioned data cache, and
repairs a corrupt cache before starting the host.

The caller establishes the bundle directory as an authenticated-delivery
boundary: verify the signed Maven classifier artifact (or independently
authenticate those exact bytes) before copying it, and keep the directory
non-attacker-writable. The runtime does not verify the artifact signature. The
compiled library pins the App Server hash; authenticated classifier delivery
authenticates the supervisor and legal files, while the internal manifest binds
and re-verifies every installed member. A self-consistent manifest is not a
substitute for artifact authentication.

```kotlin
val platform = DesktopCodexPlatform(
    bundleDirectory = bundledClassifiers.toPath(),
    dataDirectory = appData.toPath(),
)
val clientInfo = CodexClientInfo(
    name = "com.example.app",
    title = "Example App",
    version = appVersion,
)
val codex = CodexHost(platform, clientInfo)
codex.start()
```

Kotlin/JS and Kotlin/WasmJS applications on Node use the equivalent Node
support:

```kotlin
val platform = NodeCodexPlatform(bundledClassifiers.toPath(), appData.toPath())
```

The libraries do not use an update feed or network downloader. An application
updates the runtime by shipping the classifier for a newer library version; the
installer keeps versioned caches side by side. Process launch, verification,
and installation plumbing remains internal. Neither adapter accepts arbitrary
arguments, commands, shells, or remote transports.

Android hosts keep the bundled executable extractable so it can be verified and
launched by path:

```kotlin
android { packaging { jniLibs.useLegacyPackaging = true } }
```

Android hosts provide `AndroidCodexPlatform(context)`. The application owns the
folder picker and permission presentation; the platform adapter persists and
revalidates selected canonical paths, rejects `Android/data` and `Android/obb`,
and does not request all-files access.

An iOS host may select either an application-container folder or a folder URL
returned by its document picker. `IosCodexPlatform` persists a
security-scoped bookmark, restores and leases it for the runtime, coordinates
file access, and requests reselection when the bookmark is stale or revoked.
Codex home and credentials always stay inside the application sandbox:

```kotlin
val platform = IosCodexPlatform(
    sandboxRootPath = sandbox,
    credentialProtection = IosCodexCredentialProtection.WHEN_UNLOCKED,
)
val codex = CodexHost(
    platform,
    CodexClientInfo("com.example.app", "Example App", appVersion),
)
```

The Apple distribution also contains a static `CodexAgent.xcframework` and a
Swift Package. Its optional authentication product exposes only
`CodexWebAuthenticationBrowser`, an `ASWebAuthenticationSession` presenter for
validated `CodexAuthorizationUrl` values. The App Server owns PKCE, callback
handling, tokens, refresh, and completion events; the adapter does not receive
or store OAuth tokens.

Every runtime platform exposes a native browser through `CodexPlatform`:
Android Custom Tabs, Apple `ASWebAuthenticationSession` (when injected from the
Swift helper), JVM `Desktop.browse`, macOS `NSWorkspace`, Linux `xdg-open`,
Windows `ShellExecuteW`, and Node's direct `open`/`xdg-open`/`explorer.exe`
spawn. Use `CodexAuthorizationUrl.chatGpt` for the strict OpenAI/ChatGPT HTTPS
policy and `CodexAuthorizationUrl.external` for connector, MCP OAuth, and
elicitation URLs (HTTPS or loopback HTTP only). The ready `CodexAgent`
coordinates browser presentation and authorization state on every Kotlin
target.

Custom targets implement `CodexPlatform` and return a `PreparedCodexRuntime`.
`CodexRuntime`, `CodexRuntimeFactory`, and the bounded `JsonLineFramer` exist
only to construct that adapter; `AppServerProtocolIdentity` supplies the three
values needed to reject an incompatible runtime. None of these support types
exposes App Server operations independently of `CodexAgent`.
Every prepared runtime must also declare its exact `CodexRuntimeFeature` set;
there is no permissive default that could advertise an operation the runtime
cannot actually perform.

Applications that do not need to assemble those pieces manually can use the
shared lifecycle layer on every Kotlin target:

```kotlin
val clientInfo = CodexClientInfo("com.example.app", "Example App", appVersion)
val host = CodexHost(platform, clientInfo)
applicationScope.launch { host.lifecycleState.collect(::render) }
host.start()

when (val state = host.lifecycleState.value) {
    is CodexHostState.Ready -> {
        val agent = state.agent
        val conversation = agent.conversations.open()
        conversation.send("Hello")
    }
    is CodexHostState.WorkspaceRequired -> {
        host.selectWorkspace(selectionFromThePlatformPicker)
    }
    is CodexHostState.Failed -> showStartupError(state.failure)
    else -> showStartupProgress()
}
```

The two-argument Host constructor owns a supervised default coroutine scope and
cancels it on `close()`. Applications that need their own parent job may use
`CodexHost(platform, applicationScope, clientInfo)` instead. `CodexClientInfo`
identifies the embedding application in the App Server initialize request; it
is deliberately not the Codex Agent library version.

`CodexHost` owns workspace/runtime startup and shutdown. A ready `CodexAgent`
groups backend capabilities into focused resources: `authentication`,
`interactions`, `integrationAuthorization`, `conversations`, `models`,
`skills`, `hooks`, `plugins`, `connectors`, and `mcpServers`.
`CodexConversation` owns live text, reasoning, plan, shell, work, and hook
updates, then reconciles with canonical history after completion. The raw
client, connection, generated protocol, and workflow controllers remain
internal.

Swift applications receive the same host, ready agent, conversation handles,
and immutable state through the `CodexAgent` framework. The
`CodexAgentObservation` SwiftPM product adds cancellation-safe typed
`AsyncStream` properties such as `host.lifecycleStates`,
`agent.authentication.states`, `agent.conversations.activeConversations`, and
`conversation.states`.
`CodexAgentSwiftSupport` adds only the natural default calls
`agent.authentication.authenticate()`, `agent.conversations.open()`, and
`conversation.send(_:)`, plus `Error.codexFailure` for stable code, message,
and recoverability. Advanced Kotlin overloads remain available as native Swift
`async throws` operations.
`CodexAgentAuthentication` contributes only the native browser adapter; it does
not introduce a second host, client, event broadcaster, authentication session,
or reducer.

## Runtime features and failures

Each optional resource exposes `isAvailable`; adopters do not need to interpret
a shared feature enum. Android, Desktop, and Node make skills, hooks, plugins,
connectors, and MCP servers available. On embedded iOS only
`agent.skills.isAvailable` is true; its sandboxed built-in file tools are
runtime implementation details. Calling an unavailable capability fails before
an RPC with
`CodexOperationException` and a non-recoverable `CodexFailure` whose code is
`unsupported_feature`.

Host, authentication, interaction, integration-authorization, and conversation
state expose `CodexFailure` instead of unrelated error strings. Conversation
state also supplies `canStartTurn`, `canReload`, and `canCancelTurn`, and reaches
the terminal `CLOSED` status when its owner replaces or closes the handle.

## Capability boundary

The process runtimes launch only the verified App Server from their exact local
classifier. They expose no arbitrary process configuration or remote runtime.

The iOS runtime additionally limits built-in tools to sandboxed file reads,
directory listing, text search, atomic writes, and workspace-confined patches.
Model API network access remains available through the App Server.

### Cross-language contribution flow

`@CodexBindingApi` marks canonical owner types. Adding a normal public
constructor, property, function, or object to a marked owner automatically adds
it to the compiler-derived API; mark a new user-facing owner once rather than
listing its members. Do not edit generated reports or create a manual
capability manifest.

After adding the member, run:

```shell
./gradlew :codex-agent-core:verifyCrossLanguageApiCoverage
```

For a new member, the expected initial failure prints a pair shaped like
`api-v1:<owner>#<kind>:<member>#sha256:<digest> -> <full compiler key>`.
Copy the exact `api-v1` token into `@CoversApi` on a meaningful executed
canonical test, then rerun the task. Do not calculate or shorten the token. The
full key binds source set, owner, member kind, ABI signature, types,
nullability, suspend status, parameters, defaults, and varargs, so signature
drift makes old coverage stale. `@CodexBindingApiKotlinOnly` is reserved for
the narrow Kotlin coroutine-scope ownership boundary; it is not a general
binding exclusion.

The core tasks write content-hash-bound evidence under
`codex-agent-core/build/reports/cross-language-api/`:

- `canonical-api.json` is the compiler-derived owner and member inventory.
- `canonical-coverage.json` binds every member to successful canonical tests.
- `bindings/kotlin-parity.json` and `bindings/java-parity.json` are verified
  core language receipts.
- `codex-agent-runtime-desktop/build/reports/cross-language-api/bindings/javascript-typescript-parity.json`
  is the verified JavaScript/TypeScript receipt.
- `codex-agent-runtime-ios/build/reports/cross-language-api/bindings/swift-parity.json`
  and `codex-agent-runtime-ios/build/reports/cross-language-api/bindings/objective-c-parity.json`
  are the verified Apple receipts.
- `codex-agent-runtime-desktop/build/reports/cross-language-api/c-abi/` contains
  the canonical bootstrap, exact shared-scenario proof, and matching-host SDK
  package proofs.
- The same binding report directory contains `python-parity.json`,
  `csharp-parity.json`, `rust-parity.json`, `cpp-parity.json`, and
  `dart-parity.json`; every strict merge-gate-derived native receipt also binds
  exact installed-package consumer proof from all five hosts.

Only a successful exact five-host merge-gate run may derive the strict C and
native-wrapper receipts from those exact artifacts. M11 then produces
`binding-obligations-m11.json` over all eleven languages; local producer output
cannot substitute for that final-head distributed receipt.

For a binding, add the smallest idiomatic public artifact projection and a real
consumer test. Extend that language's evidence derivation so each exact
canonical key resolves to real public symbol(s), passed test ID(s), and the
applicable shared scenario(s); never hand-write claims into the aggregate
report. The current focused gates are:

```shell
./gradlew :codex-agent-core:verifyKotlinBindingParity \
  :codex-agent-core:verifyJavaBindingParity \
  :codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity \
  :codex-agent-runtime-desktop:verifyPythonBindingParity \
  :codex-agent-runtime-desktop:verifyCSharpBindingParity \
  :codex-agent-runtime-desktop:verifyRustBindingParity \
  :codex-agent-runtime-desktop:verifyCppBindingParity \
  :codex-agent-runtime-desktop:verifyDartBindingParity
./gradlew verifyRepository
# macOS only
./gradlew verifyIosRuntime
./gradlew :codex-agent-runtime-desktop:generateCodexAgentCAbiScenarioProof
```

The portable root `verifyRepository` task produces the Kotlin, Java, and
JavaScript/TypeScript receipts without running Xcode. It also runs native-wrapper
parity when all authoritative five-host release/consumer inputs are supplied
together; a local invocation without them makes no native-wrapper or distributed
aggregate claim. On macOS, root `verifyIosRuntime` verifies the iOS runtime and
Apple receipts. Only a successful merge-gate run can collect all five
matching-host C SDK and installed-package proofs, derive the C/native receipts,
run the exact eleven-receipt M11 audit, and preserve the canonical API, coverage,
packages, receipts, and audit through promotion and release-candidate
verification.
An active pair without verified projection evidence is `missing`. A future
phase pair remains applicable but `pending`: M7.5 historically activated
Kotlin, Java, Swift, Objective-C, and JavaScript/TypeScript; M8 also activates
the C ABI. The
`M9_PYTHON`, `M9_CSHARP`, `M9_RUST`, `M9_CPP`, and `M9_DART` phases activate
their wrappers independently; M11 requires the all-eleven set to be satisfied.
A C receipt cannot satisfy a wrapper.

An applicability exclusion belongs in the language's evidence derivation and
must name one exact canonical key, one exact language, and a fixed narrow
architectural reason. Its matcher and tests must reject owner, kind, ABI,
signature, stale-key, wildcard, broad-reason, duplicate, and projection-conflict
drift. An unfinished binding or future-phase obligation is never an exclusion.

Native wrapper gates reuse `CrossLanguageBindingReceipt`,
`CrossLanguageBindingPhase`, and `writeCompleteCrossLanguageBindingAudit`,
which derive active languages and required receipt names. A new capability must
pass canonical coverage, exact per-language compiler/reference/executed
behavior matching, installed-package consumption, and M11 fan-in; do not add a
manual capability manifest or a second language-activation mechanism.

## Release evidence

An unlabeled pull request runs lightweight workflow and impact planning; its
required merge gate remains failed until readiness is declared. On a non-draft
pull request, adding `merge-ready` validates the prospective merge tree and
runs its affected product, platform, and consumer lanes. Adding `ci:full`
forces every lane. Successful lanes from an earlier run of the same pull
request may be reused; full mode never suppresses required work. A merge group
reuses the pull-request result when its Git tree is identical, otherwise it
reevaluates the changed base and runs the newly affected lanes.

A push to `main` only promotes equal-tree validation receipts, their exact
GitHub-hosted artifacts, and selected cache seeds; it never compiles or tests.
A protected `candidate/v<version>-rc.N` tag consumes those promoted bytes and
performs verification, signing, sidecar generation, and release assembly only.
Publication consumes the exact candidate bytes. Protected environments hold
the Android evidence, signing, and publication authority.

Git commit, tree, and blob identities determine whether inputs changed.
Checksums remain only where a format or integrity boundary requires them; they
never decide whether source changed, whether a lane must run, or whether two
independent builds are equivalent.

See [protocol provenance](docs/PROTOCOL.md), the
[iOS runtime design](docs/RUNTIME_IOS.md), the
[Desktop/Host Node-adapter design](docs/RUNTIME_NODE.md), and the
[release procedure](docs/RELEASING.md).

## License

Codex Agent is licensed under GPL-3.0-or-later. The bundled Codex App Server is
licensed separately under Apache-2.0; see
[third-party notices](THIRD_PARTY_NOTICES.md). Distribution of the static Apple
framework and native runtime classifiers remains subject to the repository's
hash-bound GPL approvals.
