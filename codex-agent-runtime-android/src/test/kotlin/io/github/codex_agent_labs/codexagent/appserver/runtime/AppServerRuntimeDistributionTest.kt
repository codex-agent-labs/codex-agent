package io.github.codex_agent_labs.codexagent.appserver.runtime

import kotlin.test.Test
import kotlin.test.assertFailsWith

class AppServerRuntimeDistributionTest {
    private val distribution = CodexAgentAppServerRuntime.DISTRIBUTION
    private val environment = RuntimeEnvironment(RuntimeKernel.LINUX, RuntimeArchitecture.AARCH64, true)

    @Test
    fun acceptsOnlyTheExactProtocolIdentityAndExecutableEnvironment() {
        distribution.requireCompatible(
            distribution.appServerVersion,
            distribution.upstreamRevision,
            distribution.schemaSha256,
            environment,
        )
        assertFailsWith<IllegalArgumentException> {
            distribution.requireCompatible("0.144.7", distribution.upstreamRevision, distribution.schemaSha256, environment)
        }
        assertFailsWith<IllegalArgumentException> {
            distribution.requireCompatible(
                distribution.appServerVersion,
                "0".repeat(40),
                distribution.schemaSha256,
                environment,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            distribution.requireCompatible(
                distribution.appServerVersion,
                distribution.upstreamRevision,
                "0".repeat(64),
                environment,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            distribution.requireCompatible(
                distribution.appServerVersion,
                distribution.upstreamRevision,
                distribution.schemaSha256,
                environment.copy(supportsStaticElf = false),
            )
        }
    }
}
