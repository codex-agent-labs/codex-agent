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
bytes and original provenance. For example, a Windows-only `0.8.1` change may
reuse the four unchanged `0.8.0` native variants without relabeling their
original producers. The new aggregate identifies exactly five compatible
variants and its own Runtime release version; producer runs and source release
versions may differ, but Contract compatibility, ABI, target, toolchain, and
App Server policy must agree. SDK compatibility hashes deterministic Runtime
payloads, so a different CI run or signing key cannot silently change an
otherwise identical embedded default.

Verification flows forward across artifacts: `verifyContract` produces
Contract evidence, standalone `verifyRuntime` consumes the authenticated
Contract payload and detached attestation, and `verifySdk` consumes declared
Contract/Runtime artifacts.
`verifyRepository` reconciles their independently supplied evidence. A
wrapper-only change must not compile Runtime source; a no-change reusable
campaign must not start a product compiler. The protected final campaign and
publication gates remain mandatory; local helper tests are not substitutes
for five matching-host package/consumer receipts or the merge gate.

## Commands and release status

These verification entry points exist in the current builds:

```sh
./gradlew verifyContract
./gradlew verifySdk \
  -PcodexAgent.sdkBindingEvidenceDirectory="$M11_EVIDENCE_DIR" \
  -PcodexAgent.sdkCanonicalApiReport="$CONTRACT_API_REPORT" \
  -PcodexAgent.sdkCanonicalCoverageReceipt="$CONTRACT_COVERAGE_RECEIPT"
./gradlew verifyRepository \
  -PcodexAgent.repositoryContractEvidenceDirectory="$CONTRACT_EVIDENCE_DIR" \
  -PcodexAgent.repositoryRuntimeEvidenceDirectory="$RUNTIME_EVIDENCE_DIR" \
  -PcodexAgent.repositorySdkEvidenceDirectory="$SDK_EVIDENCE_DIR" \
  -PcodexAgent.repositoryTrustDomain="$PRODUCT_TRUST_DOMAIN"
```

The variables must name existing, independently verified evidence; these
commands do not create missing Contract, Runtime, SDK, or host receipts. The
standalone Runtime entry point is `./gradlew -p runtime verifyRuntime` with
explicit `-PcodexAgent.target`, Contract payload, metadata receipt, detached
attestation, attestation signature, public key, Contract version, and Runtime
version properties; `runtime/settings.gradle.kts` rejects missing inputs before
configuration. For a native target's binary phase, it also requires explicit
`-PcodexAgent.runtimeBinaryPlan`, `-PcodexAgent.runtimeBinaryFlagsDigest`, and
`-PcodexAgent.repositoryRevision`: the plan must be a verified, exact-source
input, not a placeholder or a value reconstructed from retained output. Other
selected phases require their own declared predecessor stages and evidence.
The full target-specific Runtime input contract is in
[`runtime/settings.gradle.kts`](../runtime/settings.gradle.kts); no generic
target-independent invocation supplies its required predecessor stages.
`ciProductPhase` selects an exact product, component, phase, and target; it is
not a whole-graph build command.

The existing combined candidate and publish workflows are a migration baseline,
not commands for a product-specific `0.8.0` release. None of the six separate
Contract, Runtime, or SDK candidate/publish workflows exists yet. They remain
subject to the local, protected, and five-host acceptance gates in
[releasing](RELEASING.md).
No candidate tag or publication is asserted here.

See [releasing](RELEASING.md) for the intended candidate/publication policy and
the [support matrix](SUPPORT_MATRIX.md) for language/host scope. Do not extract
repositories until a Runtime-only patch, an SDK-only release, and a
single-target Runtime release have each succeeded through these artifact
boundaries.
