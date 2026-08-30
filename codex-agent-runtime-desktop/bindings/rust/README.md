# Codex Agent for Rust

Rust 1.95+ bindings for the verified local Desktop/Host C SDK. The release
crate/import are `codex-agent`/`codex_agent`; before version `0.2.0` is
published, consume a locally built `codex-agent-0.2.0.crate`. The crate
is a thin projection: it loads `codex_agent_*` directly and does not implement
a runtime, protocol, daemon, or remote transport.

```rust,no_run
use codex_agent::{ClientInfo, CodexHost, HostOptions};

# async fn example() -> Result<(), codex_agent::CodexError> {
let host = CodexHost::create(HostOptions {
    bundle_directory: "./codex-runtime".into(),
    data_directory: "./codex-data".into(),
    client_info: ClientInfo {
        name: "example".into(),
        title: "Example".into(),
        version: "1.0".into(),
    },
})?;
host.start()?.await?;
let agent = host.agent()?;
let conversations = agent.conversations()?;
let conversation = conversations.open(Default::default())?.await?;
conversation.send("Explain this repository")?.await?;
conversation.close()?.await?;
drop(conversation);
host.close()?.await?;
drop(conversations);
drop(agent);
# Ok(())
# }
```

The equivalent installed-crate program is
[`consumer/src/bin/lifecycle_smoke.rs`](https://github.com/codex-agent-labs/codex-agent/blob/main/codex-agent-runtime-desktop/bindings/rust/consumer/src/bin/lifecycle_smoke.rs).

`CodexOperation<T>` implements `Future<Output = Result<T, CodexError>>`, supports
explicit cancellation, and requests cancellation when dropped unfinished.
`CodexStateStream<T>` implements `futures_core::Stream` and also provides
`next()` without an extension-trait dependency. Values retain parents until children are
released. Host and conversation shutdown is asynchronous: applications must await `close()`
before those values leave scope. Close the Host while final Agent/service/catalog projections are
still alive, then drop those child tokens; dropping a final current child while the Host is READY
can record `CleanupIssue(BUSY)`. Rust `Drop` never blocks to run semantic close, and an unclosed
Host or Conversation records a cleanup issue rather than pretending shutdown succeeded. Token
release is not semantic Host/Conversation close.

Resolution checks `CODEX_AGENT_LIBRARY`, an executable-adjacent native library,
then the executable's `runtimes/<target>/native/` directory. Copy the matching
verified crate asset to one of those deployment locations. Target IDs are `osx-arm64`, `osx-x64`,
`linux-arm64`, `linux-x64`, and `win-x64`. ABI `1.12.0` validation is
fail-closed at load time; no platform-loader search-path fallback is used.

The external consumer also has a release-only Host smoke mode. Release validation must copy
`consumer` outside the source tree, point its `codex-agent` dependency at a clean extraction of
the packaged `.crate`, and pass the exact matching-host C SDK library:

```sh
cargo run --manifest-path /path/to/external-consumer/Cargo.toml \
  --bin codex-agent-rust-host-smoke --release --locked --offline \
  -- /absolute/path/to/libcodex_agent.dylib
```

Use `libcodex_agent.so` on Linux or `codex_agent.dll` on Windows. This mode verifies the initial
Host state and repeated asynchronous close followed by Rust disposal without starting a runtime
bundle. Its dedicated entry point requires exactly one SDK path; zero or extra arguments fail.

The public handles and their futures/streams intentionally do not implement
`Send` or `Sync`: the C contract proves worker-thread callback safety but does
not grant arbitrary concurrent caller access to a handle. Callback storage is
thread-safe internally, catches Rust panics before they cross C, and is retained
until native destruction proves quiescence.

## Immutable values and MCP configuration

The crate projects the canonical immutable value graph as owned Rust values. Nested native
handles are decoded into `String`, `Option`, `Vec`, `BTreeMap`, and typed enums, then destroyed
immediately; callers never borrow memory from the C SDK. Lists preserve order and duplicates,
while optional lists and maps preserve absent versus present-empty state.
Derived value behavior—elicitation validation/factories, form acceptance, interaction filtering,
and authorization-URL factories—also calls the verified C SDK directly and returns
`Result<_, CodexError>` when native loading, marshalling, or validation fails.

```rust
use codex_agent::{
    McpAuthStatus, McpAuthentication, McpHttpTransport, McpServer, McpServerConfiguration,
    McpTransport, ResourceOrigin,
};
use std::collections::BTreeMap;

# fn example() -> Result<(), codex_agent::CodexError> {
let http = McpHttpTransport::new(
    "https://example.com/mcp",
    Some("TOKEN_ENV".into()),
    Some(BTreeMap::from([("X-Client".into(), "rust".into())])),
    None,
    None,
)?;
let configuration = McpServerConfiguration::new(
    "local_server",
    McpTransport::Http(http),
    Some(McpAuthentication::Oauth),
    "local",
    true,
    false,
    true,
    None,
    Some(5.0),
    Some(30.0),
    None,
    None,
    None,
    None,
    None,
    None,
    BTreeMap::new(),
)?;
let server = McpServer::new(
    "local_server",
    "Local server",
    McpAuthStatus::Oauth,
    Some(configuration),
    ResourceOrigin::User,
    true,
);
assert!(server.is_authorized());
# Ok(())
# }
```

Parity is fail-closed for 556 canonical capabilities: 110 enums, 355
constructors/properties/value operations across 77 dependency-closed value owners, all 11
synchronous value functions, 42 leaf-service capabilities, all 20 conversation capabilities, and
all 11 `CodexAgent` service/workspace properties, plus all 7 terminal Host/Ready capabilities.
Every claim names its exact compiled
Rust symbol, executed behavior test, reviewed `codex_agent.h` reference, and passed canonical C
fixture. Fixture tests exercise the complete owned graph and RAII behavior; matching-host real-SDK
evidence covers Host create/current/repeated close plus exact invalid/null-boundary probes, not a
READY Agent/Conversation success lifecycle.
