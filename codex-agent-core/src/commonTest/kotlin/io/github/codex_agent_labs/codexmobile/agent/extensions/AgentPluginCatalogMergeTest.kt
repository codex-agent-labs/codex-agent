package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class AgentPluginCatalogMergeTest {
    @CoversApi(
        "api-v1:AgentPluginAuthPolicy#enum-entry:ON_INSTALL#sha256:933c1e362dd399c48f6dd19ca04eb67e9d9a0603ae98f2121a50b5f19973f328",
        "api-v1:AgentPluginCatalog#constructor:<init>#sha256:3c8826b82175075a9c7909e41dbe8a0bed94587d1b7c4cd6b1658a953f1e4733",
        "api-v1:AgentPluginCatalog#property:errors#sha256:c8a929fa8db18f67c72cc198fa92a70490eceda7d5312bcf2e1fa8a9616f4135",
        "api-v1:AgentPluginCatalog#property:freshness#sha256:f4b20da0109c932e5c31af23ce9a43f51f982f0b488fd85bb5c797385af75b25",
        "api-v1:AgentPluginCatalog#property:plugins#sha256:40f4a8735fd0b4332d97b116050b0c5b481c1933599a3e2abc34022e09c8a527",
        "api-v1:AgentPluginInstallPolicy#enum-entry:INSTALLED_BY_DEFAULT#sha256:b5a649f8712e948803bb086a1c6055bd5cebc121e52dd3767bc606b1ff31eb05",
        "api-v1:AgentPluginReference#constructor:<init>#sha256:b49847b8d01f9f4df2851c056dd42e1d112172f39aee5a20fee082d05f0db2b9",
        "api-v1:AgentPluginReference#property:id#sha256:d134fe8ce11dcb0e53ae4da4e0bfaa2e8750322385b4254ca635ee03c20e703a",
        "api-v1:AgentPluginSummary#constructor:<init>#sha256:1f5637b4c6721c77ea2375bc94fb6c12702722e064e4e86526f9d9467ccf60ed",
        "api-v1:AgentPluginSummary#property:authPolicy#sha256:de59ab5227e606be37679e7b14fe83e30dad4b87b9603c86db15738cb349262f",
        "api-v1:AgentPluginSummary#property:description#sha256:bd9d7c589360643a26ebf4fd62cb7f17480b53bdea656a3d3367753801d5a144",
        "api-v1:AgentPluginSummary#property:displayName#sha256:361acebaf353dde1a9959821339e71e3ac0f644eb17eaa5c1ea3f1c2a371d3bd",
        "api-v1:AgentPluginSummary#property:installPolicy#sha256:80cc62623558ed7764adb23b860c9755543bacca1abd6e426d3da6b975497e10",
        "api-v1:AgentPluginSummary#property:isEnabled#sha256:98cb38a2e22338b89ccaaf507b8de0ae60b320c6419f80a8eec61f974e4360e6",
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
        "api-v1:AgentPluginAuthPolicy#enum-entry:ON_USE#sha256:b709607fd00cd4282bb34977eb150e04b4d64736383f0ee00c7e22737e457620",
        "api-v1:AgentPluginInstallPolicy#enum-entry:AVAILABLE#sha256:da8460e57104a8b453fef2d4ce15f2744618af8bb73a112350ae74c7c0329a92",
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
        "api-v1:AgentCatalogFreshness#enum-entry:FRESH_CACHE#sha256:dca4b0790f2fb20458b58b09870cbb2927bdb384a805ae56237c5bc33b69bdc7",
        "api-v1:AgentCatalogFreshness#enum-entry:LIVE#sha256:7037b2eac51fb95582a1b442a38459c66fbc12c1c9f0c0bdd76c6f3cc4096f7c",
        "api-v1:AgentCatalogFreshness#enum-entry:STALE_CACHE#sha256:c6e31c879adddb10b9c91be6d442b433683ebff729c474809ad920d2b9eecc93",
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
