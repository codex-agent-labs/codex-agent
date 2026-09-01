package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AgentPluginCatalogMergeTest {
    @CoversApi(
        "api-v1:AgentPluginAuthPolicy#enum-entry:ON_INSTALL#sha256:58e7dfe6dd80cd0f9974b6284abfd1359da4fdcf672b6c8a772da606fcb0d0c2",
        "api-v1:AgentPluginCatalog#constructor:<init>#sha256:c798b7613a535ca0eeb58a8f06f167e04c4f6f47e0b9a215f05cd06273592898",
        "api-v1:AgentPluginCatalog#property:errors#sha256:98c7f7522d44d471276e20b3806f33a9b84b83accf78e06dfc025efa9383f4ac",
        "api-v1:AgentPluginCatalog#property:freshness#sha256:7b343fca9a9459702f65a883955ce4215b9182c0f41c6295221f5f4d28e8a137",
        "api-v1:AgentPluginCatalog#property:plugins#sha256:65bfbf26a8d14c081f257a685870c9931dcb7eaaf4564f15a5180e535404145f",
        "api-v1:AgentPluginInstallPolicy#enum-entry:INSTALLED_BY_DEFAULT#sha256:591cf0ddce4b2f24d44fd87741834d6b221773c3572d42d0a19860eef036a4cc",
        "api-v1:AgentPluginReference#constructor:<init>#sha256:cb0126c582207affcc9ce0a454ec38a2e719c20647959a9f3418aaed695d6cb5",
        "api-v1:AgentPluginReference#property:id#sha256:1089179177ccb17a2f1a2efef1832b73bce13eef7b309d69ac9e89761918eb9f",
        "api-v1:AgentPluginSummary#constructor:<init>#sha256:5c1de8fa7dc3d136013a6e1b6c5185c68eae2484a455475ac2930e32db0443a9",
        "api-v1:AgentPluginSummary#property:authPolicy#sha256:fda2f70944e9038c7043cccdf80b0fc37086e2e494260dbb400b266140e15b1a",
        "api-v1:AgentPluginSummary#property:description#sha256:10edc9d1b6d2f58384146a785bceb0996d15d312b62b027d7f5740d3ad3f7dad",
        "api-v1:AgentPluginSummary#property:displayName#sha256:e41c4d3d8a0aeb4343697ec7fc93da5e8cbfd341a7fa9e81437d767204f44ec5",
        "api-v1:AgentPluginSummary#property:installPolicy#sha256:b038e3d2da33da112126e163313ac383d695ee867a2171a2c51c7504eb9b43f7",
        "api-v1:AgentPluginSummary#property:isEnabled#sha256:ed56b30b210cfa9a9bef5d9986caec53e0ea5dd4baa01c89052fb4faef156b5b",
    )
    @Test
    fun mergesInstalledStateWithoutReorderingAvailablePlugins() {
        val alpha = plugin("alpha", displayName = "Available Alpha")
        val availableBeta = plugin(
            "beta",
            displayName = "Available Beta",
            description = "Available description",
        )
        val installedBeta = plugin(
            "beta",
            displayName = "Installed Beta",
            description = "Installed description",
            isInstalled = true,
            isEnabled = true,
            installPolicy = AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT,
            authPolicy = AgentPluginAuthPolicy.ON_INSTALL,
        )
        val installedOnly = plugin("installed-only", isInstalled = true, isEnabled = true)

        val merged = mergePluginCatalogs(
            available = AgentPluginCatalog(
                plugins = listOf(alpha, availableBeta),
                errors = listOf("available error", "shared error"),
                freshness = AgentCatalogFreshness.LIVE,
            ),
            installed = AgentPluginCatalog(
                plugins = listOf(installedBeta, installedOnly),
                errors = listOf("shared error", "installed error"),
                freshness = AgentCatalogFreshness.FRESH_CACHE,
            ),
        )

        assertEquals(listOf("alpha", "beta", "installed-only"), merged.plugins.map { it.reference.id })
        assertEquals(alpha, merged.plugins[0])
        with(merged.plugins[1]) {
            assertEquals("Available Beta", displayName)
            assertEquals("Available description", description)
            assertTrue(isInstalled)
            assertTrue(isEnabled)
            assertEquals(AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT, installPolicy)
            assertEquals(AgentPluginAuthPolicy.ON_INSTALL, authPolicy)
        }
        assertEquals(installedOnly, merged.plugins[2])
        assertEquals(listOf("available error", "shared error", "installed error"), merged.errors)
        assertEquals(AgentCatalogFreshness.FRESH_CACHE, merged.freshness)
    }

    @CoversApi(
        "api-v1:AgentPluginAuthPolicy#enum-entry:ON_USE#sha256:fe3b7639ea1763b9c9923e3319613ce5757ae0d6526fde6e759dc08fba026adf",
        "api-v1:AgentPluginInstallPolicy#enum-entry:AVAILABLE#sha256:4eb0d3e8cd1af532c479cc9411188b4f9f4bbac516819508f2dd24b5ba0a6ca9",
    )
    @Test
    fun keepsAvailableStateWhenPluginIsNotInstalled() {
        val available = plugin("available", isEnabled = true)

        val merged = mergePluginCatalogs(
            available = AgentPluginCatalog(listOf(available)),
            installed = AgentPluginCatalog(emptyList()),
        )

        assertEquals(available, merged.plugins.single())
        assertFalse(merged.plugins.single().isInstalled)
    }

    @CoversApi(
        "api-v1:AgentCatalogFreshness#enum-entry:FRESH_CACHE#sha256:37b8d2c0fbe018b00ca384a4af3a69b98949093894116161fa9b8ee51484257c",
        "api-v1:AgentCatalogFreshness#enum-entry:LIVE#sha256:4a9457996072b00141ccd6280f3090ba5714c843bcc4489e893f2a0746df96ac",
        "api-v1:AgentCatalogFreshness#enum-entry:STALE_CACHE#sha256:221c7fe06b2931f41bc436197bfaca3a80aed2a6c30c40552ee9bfdd03000f16",
    )
    @Test
    fun reportsTheLeastFreshInputCatalog() {
        fun merge(first: AgentCatalogFreshness, second: AgentCatalogFreshness) = mergePluginCatalogs(
            available = AgentPluginCatalog(emptyList(), freshness = first),
            installed = AgentPluginCatalog(emptyList(), freshness = second),
        ).freshness

        assertEquals(AgentCatalogFreshness.LIVE, merge(AgentCatalogFreshness.LIVE, AgentCatalogFreshness.LIVE))
        assertEquals(
            AgentCatalogFreshness.FRESH_CACHE,
            merge(AgentCatalogFreshness.LIVE, AgentCatalogFreshness.FRESH_CACHE),
        )
        assertEquals(
            AgentCatalogFreshness.STALE_CACHE,
            merge(AgentCatalogFreshness.STALE_CACHE, AgentCatalogFreshness.LIVE),
        )
    }

    private fun plugin(
        id: String,
        displayName: String = id,
        description: String = "$id description",
        isInstalled: Boolean = false,
        isEnabled: Boolean = false,
        installPolicy: AgentPluginInstallPolicy = AgentPluginInstallPolicy.AVAILABLE,
        authPolicy: AgentPluginAuthPolicy = AgentPluginAuthPolicy.ON_USE,
    ) = AgentPluginSummary(
        reference = AgentPluginReference(
            id = id,
            name = id,
            marketplaceName = "test",
        ),
        displayName = displayName,
        description = description,
        isInstalled = isInstalled,
        isEnabled = isEnabled,
        installPolicy = installPolicy,
        authPolicy = authPolicy,
        isAvailable = true,
    )
}
