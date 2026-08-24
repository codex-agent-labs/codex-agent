# `@codex-agent-labs/codex-agent`

Node.js 24.18+ (<25) SDK for the local Desktop/Host Codex Agent runtime.

The package exposes the canonical `CodexHost` → `CodexAgent` → `CodexConversation` lifecycle through native promises, typed state subscriptions, structured errors, `AbortSignal`, and explicit disposal. It does not support browsers, browser Wasm, WASI, remote execution, or cloud execution.

`createCodexHost` accepts an authenticated Desktop classifier directory and a private data directory. The runtime validates classifier contents and its installed cache; callers must first verify the signed release artifact and keep the classifier directory non-attacker-writable.

The classifier directory must contain the archive for the current host and the
same SDK version:

```text
codex-agent-runtime-desktop-<version>-app-server-<host>-<architecture>.zip
```

Supported suffixes are `macos-arm64`, `macos-x64`, `linux-arm64`,
`linux-x64`, and `windows-x64`.

```js
import { createCodexHost } from "@codex-agent-labs/codex-agent";

await using host = createCodexHost(
  "/opt/my-app/codex-bundle",
  "/private/app-data/codex",
  "com.example.app",
  "Example App",
  "1.0.0",
);

const state = host.observeState((next) => console.log(next.status));
try {
  await host.start();
  if (host.state.status === "workspace_required") {
    await host.selectWorkspace("/absolute/workspace");
  }
  const agent = host.agent;
  if (!agent) throw new Error("Codex Host is not ready");
  const conversation = await agent.openConversation();
  await conversation.send("Explain this repository");
} finally {
  state.dispose();
}
```

Each subscription asynchronously receives the current snapshot and then the
newest observable snapshots. `close()`/`dispose()` is idempotent, prevents later
callbacks, and is automatic after a terminal `closed` snapshot. A callback
failure closes only that subscription and is reported through `console.error`.
