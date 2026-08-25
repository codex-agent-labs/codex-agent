package io.github.codex_agent_labs.codexagent.agent.runtime

import io.github.codex_agent_labs.codexagent.agent.CodexRuntimeFeature
import kotlin.test.Test
import kotlin.test.assertEquals

class IosCodexPlatformTest {
    @Test
    fun supportsOnlyFilesystemSkills() {
        assertEquals(setOf(CodexRuntimeFeature.SKILLS), iosCodexRuntimeFeatures)
    }
}
