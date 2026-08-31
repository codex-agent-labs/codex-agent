# `codex-agent` for Python

Python 3.11+ bindings for the verified local Desktop/Host C SDK. The release
distribution is `codex-agent` and the import is `codex_agent`; before version
`<sdkVersion>` is published, install a locally built matching wheel. The package
does not start a bridge or implement another runtime; every operation calls the
same `codex_agent_*` ABI used by the other native desktop bindings.

```python
import asyncio
from codex_agent import ClientInfo, CodexHost

async def main() -> None:
    async with CodexHost(
        bundle_directory="./runtime",
        data_directory="./data",
        client_info=ClientInfo("sample", "Sample", "1.0"),
    ) as host:
        await host.start()
        async with host.state.subscribe() as states:
            async for state in states:
                if state.agent is not None:
                    conversation = await state.agent.conversations.open()
                    async with conversation:
                        await conversation.send("Hello")
                    break

asyncio.run(main())
```

The same code is compiled and executed as the
[lifecycle consumer example](https://github.com/codex-agent-labs/codex-agent/blob/main/codex-agent-bindings/python/consumer/lifecycle_example.py).

Set `CODEX_AGENT_LIBRARY` to the exact verified C SDK library, pass
`library_path=` to `CodexHost`, or install a platform wheel containing the
library under `codex_agent/native/<classifier>/`. Supported classifiers are
`macos-arm64`, `macos-x64`, `linux-arm64`, `linux-x64`, and `windows-x64`.
That is the complete resolution order; there is no executable-adjacent or
system-loader fallback. The loader requires compatible C ABI `1.12.0` before
it creates a context.

Canonical closed value sets are exported as typed `IntEnum` classes from
`codex_agent`; their integer values match the public C SDK constants exactly.

MCP configuration values are frozen Python objects. Ordered lists are copied
to tuples and maps are copied to read-only mappings, while `None` remains
distinct from an explicitly empty collection:

```python
from codex_agent import McpHttpTransport, McpServerConfiguration

headers = {"X-Client": "sample"}
transport = McpHttpTransport("https://example.com/mcp", headers=headers)
configuration = McpServerConfiguration("sample", transport, enabled_tools=[])
headers["X-Client"] = "changed"

assert transport.headers["X-Client"] == "sample"
assert configuration.enabled_tools == ()
assert configuration.disabled_tools is None
```

Synchronous value behavior also goes through the verified C SDK; Python does
not maintain a second URL, form-validation, elicitation, or interaction-state
implementation:

```python
from codex_agent import (
    AuthorizationUrl, ConversationId, Elicitation, FormField,
    FormFieldType, FormTextValue,
)

field = FormField("name", "Name", FormFieldType.STRING, is_required=True)
elicitation = Elicitation(
    "request", ConversationId("conversation"), "server", "Choose", form=(field,)
)
content = {"name": FormTextValue("Codex")}

assert field.accepts(content["name"])
assert elicitation.validate(content).is_valid
assert elicitation.accepts(elicitation.accept(content))
assert "openai.com" not in repr(
    AuthorizationUrl.chat_gpt("https://auth.openai.com/authorize")
)
```

The package also exports the thin leaf-service projections
`CodexAuthentication`, `CodexConnectors`, `CodexHooks`,
`CodexIntegrationAuthorization`, `CodexInteractions`, `CodexMcpServers`,
`CodexModels`, `CodexPlugins`, and `CodexSkills`. Their operations use `await`,
state uses `StateStream`, and every service has explicit asynchronous token
release. A final current service token can remain `BUSY` while its Host is
READY, so Host semantic close precedes child-token release. Pending interaction
values retain native identity; only the exact live value emitted by the same
service may be resolved.

`CodexAgent` exposes those nine services plus `conversations` as stable typed
properties: repeated access returns the same Python projection until its Agent
is closed. Its `workspace` property copies the independently owned C snapshot
into an immutable `Workspace`. Every property is connected to its exact
`codex_agent_agent_*` getter and retains the Agent-to-child ownership boundary.

`CodexHost` is the asynchronous root owner: `start()`, `select_workspace()`,
and `aclose()` are cancellable native operations with structured failures.
`state.current` is synchronous; subscriptions deliver the current value and
later values asynchronously. A ready event is a `HostStateReady` whose non-null
`agent` remains owned by that Host. Host close performs canonical graph
shutdown and then releases its cached Agent/service tokens. Conversation
semantic close and subscription close happen before Host close; standalone
Agent/service `aclose()` only releases a token and belongs after ancestor
invalidation. Garbage collection is not a deterministic cleanup strategy.

Synchronous ABI failures raise `NativeStatusError`; asynchronous completion
failures raise `OperationError` and retain the optional structured `Failure`.
Cancelling the Python task requests native cancellation. Semantic Host or
Conversation close is separate from releasing an owned ABI token.

To smoke-test a built wheel against the exact real C SDK for the current host,
install the wheel into a clean environment and run the external consumer (it
uses empty temporary bundle and data directories and does not start a runtime):

```sh
python -m pip install dist/codex_agent-*.whl
python consumer/host_smoke.py /absolute/path/to/libcodex_agent.dylib
```

Use `libcodex_agent.so` on Linux or `codex_agent.dll` on Windows.

The parity harness accepts only declared artifacts. Set
`CODEX_AGENT_CANONICAL_API_REPORT` to `canonical-api.json`,
`CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE` to `bootstrap-evidence.json`,
`CODEX_AGENT_C_SDK_ROOT` to the C SDK directory containing
`include/codex_agent.h`, and `CODEX_AGENT_LIBRARY` to the exact real C SDK
library before running `python -m unittest discover -s tests -v`.
