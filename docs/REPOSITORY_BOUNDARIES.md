# Product and repository boundaries

This is the target architecture for the planned initial `0.8.0` release. It
does not assert that a product has been published or that the remaining CI and
release gates have passed. The sources remain in one repository for this work.

```text
Contract K ───────────► Desktop Runtime R
    │                         │
    └────────────► SDK S ◄────┘
```

The SDK facade and Android/iOS adapters consume Contract K directly. Desktop
language packages also consume Runtime R. This graph is not a single chain.

| Product owner | Version authority | Main artifacts |
| --- | --- | --- |
| Contract K | `gradle/release/versions/contract.txt` | `codex-agent-core` Maven KMP variants and deterministic Contract ZIP |
| Desktop Runtime R | `gradle/release/versions/runtime.txt` | `codex-agent-runtime-desktop`, five native variants, JVM/Node adapters, aggregate |
| SDK S | `gradle/release/versions/sdk.txt` | `codex-agent` facade, BOM, Android/iOS adapters, Swift package, JavaScript and native-language packages |

The planned Maven coordinates are
`io.github.codex-agent-labs:codex-agent-core:<contractVersion>`,
`io.github.codex-agent-labs:codex-agent-runtime-desktop:<runtimeVersion>`, and
`io.github.codex-agent-labs:codex-agent:<sdkVersion>`. The SDK-owned
`io.github.codex-agent-labs:codex-agent-bom:<sdkVersion>` constrains the facade
and Android/iOS adapters to `sdkVersion`, Contract to `contractVersion`, and
Desktop Runtime to the SDK's selected embedded default `runtimeVersion`. It
does not make the three version authorities one version.

“Runtime product” means the independently versioned Desktop/Host external-
process runtime. Android and iOS have different execution models and remain
SDK-versioned platform adapters even though their module names contain
`runtime`. No browser JS/Wasm, WASI, remote/cloud execution, extra daemon,
sidecar, bridge, or protocol is included.

## Version and package policy

The initial Contract, Runtime, and SDK versions are each `0.8.0`. The SDK
embeds verified Runtime `0.8.0` by default and declares both Runtime release
and Runtime compatibility ranges as `>=0.8.0 <0.9.0`. A user can select an
explicit compatible external `0.8.x` Runtime; each native loader must prove
its target, Contract digest, ABI, identity schema, and compatibility version
before use. No loader silently falls back to an arbitrary system library.

A Runtime-only compatible patch does not force an SDK release. Changing the
SDK's embedded default or shipped package bytes does. Android and iOS do not
select Desktop Runtime R. Stable coordinates and assets are immutable:
publishing different bytes under an existing identity is rejected.

## Artifact handoffs and reuse

Contract payloads, reusable Runtime variants, and SDK package payloads contain
deterministic product/content identity. Original commit, tree, run, producer,
retrieval, and reuse history remains in immutable external receipts and
transport evidence, not rewritten into reusable payloads. Release trust signs
or attests exact pre-existing payload bytes without rebuilding them.

A target-specific Runtime release reuses an unchanged native variant's exact
bytes and original provenance. Its new aggregate identifies the selected five
variants and its own Runtime release version. SDK compatibility hashes those
deterministic Runtime payloads, so a different CI run or signing key cannot
silently change an otherwise identical embedded default.

Verification flows forward across artifacts: `verifyContract` produces
Contract evidence, standalone `verifyRuntime` consumes the authenticated
Contract Bundle, and `verifySdk` consumes declared Contract/Runtime artifacts.
`verifyRepository` reconciles their independently supplied evidence. A
wrapper-only change must not compile Runtime source; a no-change reusable
campaign must not start a product compiler. The protected final campaign and
publication gates remain mandatory; local helper tests are not substitutes
for five matching-host package/consumer receipts or the merge gate.

See [releasing](RELEASING.md) for the intended candidate/publication policy and
the [support matrix](SUPPORT_MATRIX.md) for language/host scope. Do not extract
repositories until a Runtime-only patch, an SDK-only release, and a
single-target Runtime release have each succeeded through these artifact
boundaries.
