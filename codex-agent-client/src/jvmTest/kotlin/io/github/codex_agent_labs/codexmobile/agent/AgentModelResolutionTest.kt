package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull

class AgentModelResolutionTest {
    private val first = model("first")
    private val default = model("default", isDefault = true)
    private val preferred = model("preferred")
    private val models = listOf(first, default, preferred)

    @Test
    fun modelResolutionUsesPreferredDefaultFirstFallbackOrder() {
        assertEquals(preferred, models.resolveModel(AgentResolution.Preferred, preferred.id))
        assertEquals(default, models.resolveModel(AgentResolution.Preferred, "missing"))
        assertEquals(default, models.resolveModel(AgentResolution.Default, preferred.id))
        assertEquals(first, models.resolveModel(AgentResolution.First, preferred.id))
        assertFailsWith<AgentModelUnavailableException> {
            emptyList<AgentModel>().resolveModel(AgentResolution.Preferred, preferred.id)
        }
    }

    @Test
    fun effortResolutionUsesModelMetadataAndConfiguredPreference() {
        val model = model("model")
        assertEquals("high", model.resolveEffort(AgentResolution.Preferred, "high"))
        assertEquals("medium", model.resolveEffort(AgentResolution.Preferred, "missing"))
        assertEquals("medium", model.resolveEffort(AgentResolution.Default, "high"))
        assertEquals("low", model.resolveEffort(AgentResolution.First, "high"))
        assertEquals(
            "medium",
            model.copy(supportedEfforts = emptyList()).resolveEffort(AgentResolution.First, null),
        )
    }

    @Test
    fun serviceTierResolutionIsNullableOnlyWhenTheModelHasNoTiers() {
        val free = AgentServiceTier("free", "Free", "")
        val fast = AgentServiceTier("fast", "Fast", "")
        val model = model("model").copy(
            serviceTiers = listOf(fast, free),
            defaultServiceTier = free.id,
        )

        assertEquals(fast, model.resolveServiceTier(AgentResolution.Preferred, fast.id))
        assertEquals(free, model.resolveServiceTier(AgentResolution.Preferred, "missing"))
        assertEquals(free, model.resolveServiceTier(AgentResolution.Default, fast.id))
        assertEquals(fast, model.resolveServiceTier(AgentResolution.First, fast.id))
        assertNull(model.copy(serviceTiers = emptyList()).resolveServiceTier(AgentResolution.Preferred, fast.id))
    }
}

private fun model(id: String, isDefault: Boolean = false) = AgentModel(
    id = id,
    displayName = id,
    description = "",
    supportedEfforts = listOf("low", "medium", "high"),
    defaultEffort = "medium",
    isDefault = isDefault,
)
