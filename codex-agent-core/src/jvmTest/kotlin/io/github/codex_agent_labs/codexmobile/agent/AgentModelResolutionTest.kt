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
    @CoversApi(
        "api-v1:AgentModel#constructor:<init>#sha256:209f61477ddab41963560f842b81b43c626abf86383dcaf25cf00e20cb0d82eb",
        "api-v1:AgentModel#property:id#sha256:6798322fa669b7cf41b34920973e5f09fc3a99003f62fb6405cf8d0f16164d59",
        "api-v1:AgentModel#property:isDefault#sha256:5dd2b108633242b4c2fda9858dfe8c2286940fcdaae7daffa0aea134a9429803",
        "api-v1:AgentResolution#enum-entry:Default#sha256:56b8800a9b71d7cbb0d918a16b8cb6ec7a7a492fb8b0e307e4ebec8de85b32d8",
        "api-v1:AgentResolution#enum-entry:First#sha256:c614cbe1a93e86c5012ba4e8f6eed819ddf198d94b93d90e8ae9c4fad73b0480",
        "api-v1:AgentResolution#enum-entry:Preferred#sha256:65e61b703c6aacd555d2f796f5ebb3aaedee75a91c0f15ed4de740b85c5675cd",
    )
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
    @CoversApi(
        "api-v1:AgentModel#property:defaultEffort#sha256:e6436e97e04aa9ece0ced090409f475fb5bc9a8682628f368dda95c83646aab5",
        "api-v1:AgentModel#property:supportedEfforts#sha256:8dd5276bcaa5eb6b8ccfcade2f96ace4819a6bb8ff9470629ead22690dac0ea3",
    )
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
    @CoversApi(
        "api-v1:AgentModel#property:defaultServiceTier#sha256:50c3df84c4f8a09bc9df99f34ae7fee98d97a05cc2951ff7e4b31a2ee284f870",
        "api-v1:AgentModel#property:serviceTiers#sha256:aa44134bff6beba8b3c25446a4692224f202e14d30d8f3b1c84add1c7f7e953b",
        "api-v1:AgentServiceTier#constructor:<init>#sha256:212458ededbe17026b6ba1b8b97f167bb1fd89a2efe0bb75ce4a1e4d95dda099",
        "api-v1:AgentServiceTier#property:id#sha256:25b620e9cdda81b1a4ac17ac155e97cfdfadeb41929b15307b5257cdcde9fcf8",
    )
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
