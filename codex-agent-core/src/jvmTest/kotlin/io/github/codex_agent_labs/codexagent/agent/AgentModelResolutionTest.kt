package io.github.codex_agent_labs.codexagent.agent

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
        "api-v1:AgentModel#constructor:<init>#sha256:e506e9d0b46391da6456fbd0cdb26c9db5c8b3a914061db6aaf190f2cf80eef2",
        "api-v1:AgentModel#property:id#sha256:a4d64b7f881fa25ab8c7928b1451959961b2880cc470768b3d3deaedb3468a64",
        "api-v1:AgentModel#property:isDefault#sha256:1431a6ae5b2e103f46a976677bc67435e12a2d54a714748b830c6f1428b76d80",
        "api-v1:AgentResolution#enum-entry:Default#sha256:a10429c86f93bea0e9bfc3c130e47732f94ab9d0467c5167d5936753d2f8e56a",
        "api-v1:AgentResolution#enum-entry:First#sha256:2715dda644d802aba12664228af38a103a28d423f0e81117d4b4208df2290934",
        "api-v1:AgentResolution#enum-entry:Preferred#sha256:88ac6d297955e7fddfc92554f34af826d5c5346026fb8c0a44c62acc20750367",
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
        "api-v1:AgentModel#property:defaultEffort#sha256:20bfd5e039cafdfb134a7fcceebde3e14344145b7cc044ce52c7d8f3042f03e2",
        "api-v1:AgentModel#property:supportedEfforts#sha256:09ac1e916175f180f5a16c53b732242089ddce67428858b80cd915e3702cf53e",
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
        "api-v1:AgentModel#property:defaultServiceTier#sha256:6850f987a939316e93b5887ebb441ffcea429330908d972f57dfa79433ad0771",
        "api-v1:AgentModel#property:serviceTiers#sha256:19898cc704ab84d628a543c69124378059a2526a574294fc62a1f6984c5e7308",
        "api-v1:AgentServiceTier#constructor:<init>#sha256:63885c453e3d30461a718b7eb28442aabb7f915edddcd93863bafd4d766fd397",
        "api-v1:AgentServiceTier#property:id#sha256:95861055366be74d42ab84db8c470a1b238d53a8fa8de7d2a356f1166c646763",
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
