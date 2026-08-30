# Codex Agent desktop C ABI

This directory owns the single public native interop contract used by the
Python, C#, Rust, C++, and Dart Desktop/Host bindings. It is a local projection
of the canonical API, not a daemon, transport, or second runtime.

The public header is [`include/codex_agent.h`](include/codex_agent.h). ABI
`1.12.0` accepts compatible `1.x` requests from `1.0.0` through the current
version. Release SDK classifier ZIPs are carried by
`io.github.codex-agent-labs:codex-agent-runtime-desktop:0.2.0` for
`macos-arm64`, `macos-x64`, `linux-arm64`, `linux-x64`, and `windows-x64`.

## Ownership and callbacks

- Every non-null returned handle is a distinct, context-scoped owned token.
  Copying the pointer does not retain it; use an explicit retain operation when
  one exists.
- Create operations copy their input. Returned snapshots and immutable values
  stay owned until their matching destroy succeeds or their context is
  successfully destroyed.
- Release/destroy accepts a null slot idempotently and writes null only on
  `CODEX_AGENT_STATUS_OK`. `BUSY` and every other failure preserve the exact
  slot, so retry with the original mutable slot.
- Host/Conversation semantic close is separate from releasing its ABI token.
  Semantically close a Conversation before its Host. Keep final
  Agent/service/catalog tokens reachable until Host close invalidates the graph,
  then release child tokens before the Host token; early release can return
  `BUSY`.
- Callbacks may begin before the initiating function returns, run on library
  worker threads, and serialize per context. Operation and subscription
  callback storage remains live until terminal callback return or successful
  destroy. `BUSY` does not prove quiescence.
- A state callback owns each non-null snapshot it receives and must destroy it
  exactly once unless successful context destruction reclaims it first.

The header comments are normative. The five matching-host SDK proofs, raw C
consumer tests, symbol/export policies, wrapper receipts, and M11 audit fail
closed on ABI, hash, ownership, callback, or package drift.
