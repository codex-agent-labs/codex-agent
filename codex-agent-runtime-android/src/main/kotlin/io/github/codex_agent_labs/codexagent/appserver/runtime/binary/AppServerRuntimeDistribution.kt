package io.github.codex_agent_labs.codexagent.appserver.runtime

internal enum class RuntimeKernel { LINUX }

internal enum class RuntimeArchitecture { AARCH64 }

internal data class RuntimeEnvironment(
    val kernel: RuntimeKernel,
    val architecture: RuntimeArchitecture,
    val supportsStaticElf: Boolean,
)

internal data class AppServerRuntimeDistribution(
    val appServerVersion: String,
    val upstreamRevision: String,
    val schemaSha256: String,
    val targetTriple: String,
    val architecture: RuntimeArchitecture,
    val archiveSha256: String,
    val binarySha256: String,
) {
    init {
        require(appServerVersion.isNotBlank())
        require(upstreamRevision.matches(SHA256_OR_GIT_REVISION))
        require(schemaSha256.matches(SHA256))
        require(targetTriple.isNotBlank())
        require(archiveSha256.matches(SHA256))
        require(binarySha256.matches(SHA256))
    }

    fun requireCompatible(
        protocolVersion: String,
        protocolRevision: String,
        protocolSchemaSha256: String,
        environment: RuntimeEnvironment,
    ) {
        require(protocolVersion == appServerVersion) { "App Server client/runtime version mismatch" }
        require(protocolRevision == upstreamRevision) { "App Server client/runtime revision mismatch" }
        require(protocolSchemaSha256 == schemaSha256) { "App Server client/runtime schema mismatch" }
        require(environment.kernel == RuntimeKernel.LINUX) { "App Server runtime requires Linux" }
        require(environment.architecture == architecture) { "App Server runtime architecture mismatch" }
        require(environment.supportsStaticElf) { "App Server runtime requires static ELF execution" }
    }

    private companion object {
        val SHA256 = Regex("[a-f0-9]{64}")
        val SHA256_OR_GIT_REVISION = Regex("[a-f0-9]{40}|[a-f0-9]{64}")
    }
}

internal object CodexAgentAppServerRuntime {
    val DISTRIBUTION = AppServerRuntimeDistribution(
        appServerVersion = "0.149.0",
        upstreamRevision = "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0",
        schemaSha256 = "9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9",
        targetTriple = "aarch64-unknown-linux-musl",
        architecture = RuntimeArchitecture.AARCH64,
        archiveSha256 = "ab91c737ff50e5e1187582ffa316ba8b5341c250657c5c5d678a88b6dc7f4f71",
        binarySha256 = "96ac7e010cc38b90e66fc0dc67f5baa343b61f5471c6625bb2694d7991e2bbe0",
    )

}
