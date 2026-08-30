# Native asset staging

Release automation stages the verified C SDK libraries here before packing:

```text
osx-arm64/libcodex_agent.dylib
osx-x64/libcodex_agent.dylib
linux-arm64/libcodex_agent.so
linux-x64/libcodex_agent.so
win-x64/codex_agent.dll
```

Packing with `-p:CodexAgentRequireNativeAssets=true` fails closed if any target
is absent. This directory never contains a second runtime implementation.
