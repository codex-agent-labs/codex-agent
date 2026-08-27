@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCResourceListValuesTest {
    @Test
    fun connectorCopiesOrderedDuplicateNamesAndProjectsEveryProperty(): Unit = memScoped {
        val contextSlot = resourceListContext()
        val context = assertNotNull(contextSlot.value)
        val mutableId = mutableResourceListView("connector-id")
        val pluginNames = resourceListViews("plugin-a", "plugin-a", "plugin-b")
        val connectorSlot = emptyResourceListHandle()
        val emptySlot = emptyResourceListHandle()
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorCreate(
                    context,
                    mutableId.view,
                    resourceListView("Connector"),
                    resourceListView("Description"),
                    1,
                    resourceListView("https://example.invalid/install"),
                    1,
                    0,
                    pluginNames.views,
                    3uL,
                    connectorSlot.ptr,
                ),
            )
            val connector = assertNotNull(connectorSlot.value)
            mutableId.bytes[0] = 'X'.code.toUByte()
            assertNotNull(pluginNames.buffers[0])[0] = 'X'.code.toUByte()
            assertResourceListString(context, connector, "connector-id", ::codexAgentConnectorIdCopy)
            assertResourceListString(context, connector, "Connector", ::codexAgentConnectorNameCopy)
            assertResourceListString(context, connector, "Description", ::codexAgentConnectorDescriptionCopy)
            assertResourceListFlag(context, connector, 1, ::codexAgentConnectorHasInstallUrl)
            assertResourceListString(
                context,
                connector,
                "https://example.invalid/install",
                ::codexAgentConnectorInstallUrlCopy,
            )
            assertResourceListFlag(context, connector, 1, ::codexAgentConnectorIsAccessible)
            assertResourceListFlag(context, connector, 0, ::codexAgentConnectorIsEnabled)
            assertResourceListCount(context, connector, 3uL, ::codexAgentConnectorPluginNamesCount)
            assertResourceListStringAt(
                context, connector, 0uL, "plugin-a", ::codexAgentConnectorPluginNamesCopyAt,
            )
            assertResourceListStringAt(
                context, connector, 1uL, "plugin-a", ::codexAgentConnectorPluginNamesCopyAt,
            )
            assertResourceListStringAt(
                context, connector, 2uL, "plugin-b", ::codexAgentConnectorPluginNamesCopyAt,
            )

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("empty"),
                    resourceListView("Empty"),
                    resourceListView(""),
                    0,
                    emptyResourceListView(),
                    0,
                    1,
                    null,
                    0uL,
                    emptySlot.ptr,
                ),
            )
            val empty = assertNotNull(emptySlot.value)
            assertResourceListFlag(context, empty, 0, ::codexAgentConnectorHasInstallUrl)
            assertAbsentResourceListString(context, empty, ::codexAgentConnectorInstallUrlCopy)
            assertResourceListCount(context, empty, 0uL, ::codexAgentConnectorPluginNamesCount)
            val required = alloc<ULongVar>().also { it.value = 91uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorPluginNamesCopyAt(context, empty, 0uL, null, 0uL, required.ptr),
            )
            assertEquals(91uL, required.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, emptySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            assertNull(connectorSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun skillAndCatalogPreserveDefaultsListsAndIndependentChildren(): Unit = memScoped {
        val contextSlot = resourceListContext()
        val context = assertNotNull(contextSlot.value)
        val dependencies = resourceListViews("git", "git", "docker")
        val firstSkillSlot = emptyResourceListHandle()
        val secondSkillSlot = emptyResourceListHandle()
        val catalogSlot = emptyResourceListHandle()
        val emptyCatalogSlot = emptyResourceListHandle()
        val nestedOneSlot = emptyResourceListHandle()
        val nestedTwoSlot = emptyResourceListHandle()
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCreate(
                    context,
                    resourceListView("review"),
                    resourceListView("Review"),
                    resourceListView("Review changes"),
                    resourceListView("/skills/review.md"),
                    1,
                    1,
                    1,
                    resourceListView("#123456"),
                    dependencies.views,
                    3uL,
                    1,
                    0,
                    0,
                    firstSkillSlot.ptr,
                ),
            )
            val firstSkill = assertNotNull(firstSkillSlot.value)
            assertNotNull(dependencies.buffers[0])[0] = 'X'.code.toUByte()
            assertResourceListString(context, firstSkill, "review", ::codexAgentSkillNameCopy)
            assertResourceListString(context, firstSkill, "Review", ::codexAgentSkillDisplayNameCopy)
            assertResourceListString(context, firstSkill, "Review changes", ::codexAgentSkillDescriptionCopy)
            assertResourceListString(context, firstSkill, "/skills/review.md", ::codexAgentSkillPathCopy)
            assertResourceListInt(context, firstSkill, 1, ::codexAgentSkillScope)
            assertResourceListFlag(context, firstSkill, 1, ::codexAgentSkillIsEnabled)
            assertResourceListFlag(context, firstSkill, 1, ::codexAgentSkillHasBrandColor)
            assertResourceListString(context, firstSkill, "#123456", ::codexAgentSkillBrandColorCopy)
            assertResourceListCount(context, firstSkill, 3uL, ::codexAgentSkillDependenciesCount)
            assertResourceListStringAt(context, firstSkill, 0uL, "git", ::codexAgentSkillDependenciesCopyAt)
            assertResourceListStringAt(context, firstSkill, 1uL, "git", ::codexAgentSkillDependenciesCopyAt)
            assertResourceListStringAt(context, firstSkill, 2uL, "docker", ::codexAgentSkillDependenciesCopyAt)
            assertResourceListFlag(context, firstSkill, 1, ::codexAgentSkillCanUninstall)
            assertResourceListInt(context, firstSkill, 0, ::codexAgentSkillOrigin)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCreate(
                    context,
                    resourceListView("managed"),
                    resourceListView("Managed"),
                    resourceListView("Managed skill"),
                    resourceListView("/skills/managed.md"),
                    0,
                    0,
                    0,
                    emptyResourceListView(),
                    null,
                    0uL,
                    0,
                    1,
                    4,
                    secondSkillSlot.ptr,
                ),
            )
            val secondSkill = assertNotNull(secondSkillSlot.value)
            assertResourceListFlag(context, secondSkill, 0, ::codexAgentSkillHasBrandColor)
            assertAbsentResourceListString(context, secondSkill, ::codexAgentSkillBrandColorCopy)
            assertResourceListInt(context, secondSkill, 4, ::codexAgentSkillOrigin)

            val skillHandles = resourceListHandles(firstSkill, firstSkill, secondSkill)
            val errors = resourceListViews("warning", "warning")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCatalogCreate(
                    context,
                    skillHandles,
                    3uL,
                    errors.views,
                    2uL,
                    catalogSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, firstSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, secondSkillSlot.ptr))
            val catalog = assertNotNull(catalogSlot.value)
            assertResourceListCount(context, catalog, 3uL, ::codexAgentSkillCatalogSkillsCount)
            assertResourceListCount(context, catalog, 2uL, ::codexAgentSkillCatalogErrorsCount)
            assertResourceListStringAt(
                context, catalog, 0uL, "warning", ::codexAgentSkillCatalogErrorsCopyAt,
            )
            assertResourceListStringAt(
                context, catalog, 1uL, "warning", ::codexAgentSkillCatalogErrorsCopyAt,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCatalogSkillsAt(context, catalog, 0uL, nestedOneSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCatalogSkillsAt(context, catalog, 0uL, nestedTwoSlot.ptr),
            )
            val nestedOne = assertNotNull(nestedOneSlot.value)
            val nestedTwo = assertNotNull(nestedTwoSlot.value)
            assertNotEquals(nestedOne, nestedTwo)
            assertResourceListString(context, nestedOne, "review", ::codexAgentSkillNameCopy)
            assertResourceListString(context, nestedTwo, "review", ::codexAgentSkillNameCopy)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCatalogCreate(
                    context, null, 0uL, null, 0uL, emptyCatalogSlot.ptr,
                ),
            )
            val emptyCatalog = assertNotNull(emptyCatalogSlot.value)
            assertResourceListCount(context, emptyCatalog, 0uL, ::codexAgentSkillCatalogSkillsCount)
            assertResourceListCount(context, emptyCatalog, 0uL, ::codexAgentSkillCatalogErrorsCount)
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillCatalogDestroy(context, emptyCatalogSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, nestedTwoSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, nestedOneSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillCatalogDestroy(context, catalogSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, secondSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillDestroy(context, firstSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun pluginSummaryAndCatalogOwnNestedValuesAndProjectEveryField(): Unit = memScoped {
        val contextSlot = resourceListContext()
        val context = assertNotNull(contextSlot.value)
        val referenceSlot = createResourceListReference(context, "plugin-id", "tools")
        val summarySlot = emptyResourceListHandle()
        val absentSummarySlot = emptyResourceListHandle()
        val nestedReferenceOneSlot = emptyResourceListHandle()
        val nestedReferenceTwoSlot = emptyResourceListHandle()
        val catalogSlot = emptyResourceListHandle()
        val emptyCatalogSlot = emptyResourceListHandle()
        val nestedSummarySlot = emptyResourceListHandle()
        val capabilities = resourceListViews("hooks", "hooks", "skills")
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSummaryCreate(
                    context,
                    assertNotNull(referenceSlot.value),
                    resourceListView("Tools"),
                    resourceListView("Tooling plugin"),
                    1,
                    0,
                    2,
                    1,
                    1,
                    capabilities.views,
                    3uL,
                    1,
                    resourceListView("#abcdef"),
                    1,
                    resourceListView("https://example.invalid/privacy"),
                    1,
                    resourceListView("https://example.invalid/terms"),
                    1,
                    resourceListView("https://example.invalid"),
                    summarySlot.ptr,
                ),
            )
            assertNotNull(capabilities.buffers[0])[0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            val summary = assertNotNull(summarySlot.value)
            assertResourceListString(context, summary, "Tools", ::codexAgentPluginSummaryDisplayNameCopy)
            assertResourceListString(
                context, summary, "Tooling plugin", ::codexAgentPluginSummaryDescriptionCopy,
            )
            assertResourceListFlag(context, summary, 1, ::codexAgentPluginSummaryIsInstalled)
            assertResourceListFlag(context, summary, 0, ::codexAgentPluginSummaryIsEnabled)
            assertResourceListInt(context, summary, 2, ::codexAgentPluginSummaryInstallPolicy)
            assertResourceListInt(context, summary, 1, ::codexAgentPluginSummaryAuthPolicy)
            assertResourceListFlag(context, summary, 1, ::codexAgentPluginSummaryIsAvailable)
            assertResourceListCount(context, summary, 3uL, ::codexAgentPluginSummaryCapabilitiesCount)
            assertResourceListStringAt(
                context, summary, 0uL, "hooks", ::codexAgentPluginSummaryCapabilitiesCopyAt,
            )
            assertResourceListStringAt(
                context, summary, 1uL, "hooks", ::codexAgentPluginSummaryCapabilitiesCopyAt,
            )
            assertResourceListStringAt(
                context, summary, 2uL, "skills", ::codexAgentPluginSummaryCapabilitiesCopyAt,
            )
            assertOptionalSummaryString(
                context,
                summary,
                1,
                "#abcdef",
                ::codexAgentPluginSummaryHasBrandColor,
                ::codexAgentPluginSummaryBrandColorCopy,
            )
            assertOptionalSummaryString(
                context,
                summary,
                1,
                "https://example.invalid/privacy",
                ::codexAgentPluginSummaryHasPrivacyPolicyUrl,
                ::codexAgentPluginSummaryPrivacyPolicyUrlCopy,
            )
            assertOptionalSummaryString(
                context,
                summary,
                1,
                "https://example.invalid/terms",
                ::codexAgentPluginSummaryHasTermsOfServiceUrl,
                ::codexAgentPluginSummaryTermsOfServiceUrlCopy,
            )
            assertOptionalSummaryString(
                context,
                summary,
                1,
                "https://example.invalid",
                ::codexAgentPluginSummaryHasWebsiteUrl,
                ::codexAgentPluginSummaryWebsiteUrlCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSummaryReference(context, summary, nestedReferenceOneSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSummaryReference(context, summary, nestedReferenceTwoSlot.ptr),
            )
            assertNotEquals(nestedReferenceOneSlot.value, nestedReferenceTwoSlot.value)
            assertResourceListString(
                context,
                assertNotNull(nestedReferenceOneSlot.value),
                "plugin-id",
                ::codexAgentPluginReferenceIdCopy,
            )

            val absentReference = createResourceListReference(context, "absent-id", "absent")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSummaryCreate(
                    context,
                    assertNotNull(absentReference.value),
                    resourceListView("Absent"),
                    resourceListView("No optional values"),
                    0,
                    1,
                    0,
                    0,
                    0,
                    null,
                    0uL,
                    0,
                    emptyResourceListView(),
                    0,
                    emptyResourceListView(),
                    0,
                    emptyResourceListView(),
                    0,
                    emptyResourceListView(),
                    absentSummarySlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, absentReference.ptr))
            val absentSummary = assertNotNull(absentSummarySlot.value)
            assertOptionalSummaryString(
                context,
                absentSummary,
                0,
                null,
                ::codexAgentPluginSummaryHasBrandColor,
                ::codexAgentPluginSummaryBrandColorCopy,
            )
            assertOptionalSummaryString(
                context,
                absentSummary,
                0,
                null,
                ::codexAgentPluginSummaryHasPrivacyPolicyUrl,
                ::codexAgentPluginSummaryPrivacyPolicyUrlCopy,
            )
            assertOptionalSummaryString(
                context,
                absentSummary,
                0,
                null,
                ::codexAgentPluginSummaryHasTermsOfServiceUrl,
                ::codexAgentPluginSummaryTermsOfServiceUrlCopy,
            )
            assertOptionalSummaryString(
                context,
                absentSummary,
                0,
                null,
                ::codexAgentPluginSummaryHasWebsiteUrl,
                ::codexAgentPluginSummaryWebsiteUrlCopy,
            )

            val summaryHandles = resourceListHandles(summary, summary, absentSummary)
            val errors = resourceListViews("catalog-error", "catalog-error")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginCatalogCreate(
                    context, summaryHandles, 3uL, errors.views, 2uL, 2, catalogSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, summarySlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSummaryDestroy(context, absentSummarySlot.ptr),
            )
            val catalog = assertNotNull(catalogSlot.value)
            assertResourceListCount(context, catalog, 3uL, ::codexAgentPluginCatalogPluginsCount)
            assertResourceListCount(context, catalog, 2uL, ::codexAgentPluginCatalogErrorsCount)
            assertResourceListStringAt(
                context, catalog, 1uL, "catalog-error", ::codexAgentPluginCatalogErrorsCopyAt,
            )
            assertResourceListInt(context, catalog, 2, ::codexAgentPluginCatalogFreshness)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginCatalogPluginsAt(context, catalog, 0uL, nestedSummarySlot.ptr),
            )
            assertResourceListString(
                context,
                assertNotNull(nestedSummarySlot.value),
                "Tools",
                ::codexAgentPluginSummaryDisplayNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginCatalogCreate(
                    context, null, 0uL, null, 0uL, 0, emptyCatalogSlot.ptr,
                ),
            )
            val emptyCatalog = assertNotNull(emptyCatalogSlot.value)
            assertResourceListCount(context, emptyCatalog, 0uL, ::codexAgentPluginCatalogPluginsCount)
            assertResourceListCount(context, emptyCatalog, 0uL, ::codexAgentPluginCatalogErrorsCount)
            assertResourceListInt(context, emptyCatalog, 0, ::codexAgentPluginCatalogFreshness)
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginCatalogDestroy(context, emptyCatalogSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, nestedSummarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginCatalogDestroy(context, catalogSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceDestroy(context, nestedReferenceTwoSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceDestroy(context, nestedReferenceOneSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, absentSummarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, summarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun pluginDetailAndInstallResultOwnOrderedNestedValues(): Unit = memScoped {
        val contextSlot = resourceListContext()
        val context = assertNotNull(contextSlot.value)
        val connectorSlot = createResourceListConnector(context, "connector")
        val pluginSkillSlot = createResourceListPluginSkill(context, "review")
        val referenceSlot = createResourceListReference(context, "detail-id", "detail")
        val summarySlot = createResourceListSummary(context, assertNotNull(referenceSlot.value), "Detail")
        val detailSlot = emptyResourceListHandle()
        val emptyDetailSlot = emptyResourceListHandle()
        val installSlot = emptyResourceListHandle()
        val absentInstallSlot = emptyResourceListHandle()
        val nestedSummarySlot = emptyResourceListHandle()
        val nestedSkillSlot = emptyResourceListHandle()
        val nestedConnectorOneSlot = emptyResourceListHandle()
        val nestedConnectorTwoSlot = emptyResourceListHandle()
        val installConnectorSlot = emptyResourceListHandle()
        try {
            val skillHandles = resourceListHandles(
                assertNotNull(pluginSkillSlot.value),
                assertNotNull(pluginSkillSlot.value),
            )
            val connectorHandles = resourceListHandles(
                assertNotNull(connectorSlot.value),
                assertNotNull(connectorSlot.value),
            )
            val servers = resourceListViews("server-a", "server-a", "server-b")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailCreate(
                    context,
                    assertNotNull(summarySlot.value),
                    resourceListView("Detailed description"),
                    skillHandles,
                    2uL,
                    connectorHandles,
                    2uL,
                    servers.views,
                    3uL,
                    17,
                    detailSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginInstallResultCreate(
                    context,
                    1,
                    connectorHandles,
                    2uL,
                    1,
                    resourceListView("Authentication required"),
                    installSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailCreate(
                    context,
                    assertNotNull(summarySlot.value),
                    resourceListView("Empty detail"),
                    null,
                    0uL,
                    null,
                    0uL,
                    null,
                    0uL,
                    0,
                    emptyDetailSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginInstallResultCreate(
                    context,
                    0,
                    null,
                    0uL,
                    0,
                    emptyResourceListView(),
                    absentInstallSlot.ptr,
                ),
            )
            assertNotNull(servers.buffers[0])[0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, summarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, pluginSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))

            val detail = assertNotNull(detailSlot.value)
            assertResourceListString(
                context, detail, "Detailed description", ::codexAgentPluginDetailDescriptionCopy,
            )
            assertResourceListCount(context, detail, 2uL, ::codexAgentPluginDetailSkillsCount)
            assertResourceListCount(context, detail, 2uL, ::codexAgentPluginDetailConnectorsCount)
            assertResourceListCount(context, detail, 3uL, ::codexAgentPluginDetailMcpServersCount)
            assertResourceListStringAt(
                context, detail, 0uL, "server-a", ::codexAgentPluginDetailMcpServersCopyAt,
            )
            assertResourceListStringAt(
                context, detail, 1uL, "server-a", ::codexAgentPluginDetailMcpServersCopyAt,
            )
            assertResourceListStringAt(
                context, detail, 2uL, "server-b", ::codexAgentPluginDetailMcpServersCopyAt,
            )
            assertResourceListInt(context, detail, 17, ::codexAgentPluginDetailHookCount)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailSummary(context, detail, nestedSummarySlot.ptr),
            )
            assertResourceListString(
                context,
                assertNotNull(nestedSummarySlot.value),
                "Detail",
                ::codexAgentPluginSummaryDisplayNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailSkillsAt(context, detail, 1uL, nestedSkillSlot.ptr),
            )
            assertResourceListString(
                context,
                assertNotNull(nestedSkillSlot.value),
                "review",
                ::codexAgentPluginSkillNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailConnectorsAt(context, detail, 0uL, nestedConnectorOneSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginDetailConnectorsAt(context, detail, 0uL, nestedConnectorTwoSlot.ptr),
            )
            assertNotEquals(nestedConnectorOneSlot.value, nestedConnectorTwoSlot.value)

            val install = assertNotNull(installSlot.value)
            assertResourceListInt(context, install, 1, ::codexAgentPluginInstallResultAuthPolicy)
            assertResourceListCount(
                context, install, 2uL, ::codexAgentPluginInstallResultConnectorsCount,
            )
            assertResourceListFlag(context, install, 1, ::codexAgentPluginInstallResultHasMessage)
            assertResourceListString(
                context,
                install,
                "Authentication required",
                ::codexAgentPluginInstallResultMessageCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginInstallResultConnectorsAt(
                    context, install, 1uL, installConnectorSlot.ptr,
                ),
            )
            assertResourceListString(
                context,
                assertNotNull(installConnectorSlot.value),
                "connector",
                ::codexAgentConnectorIdCopy,
            )

            val emptyDetail = assertNotNull(emptyDetailSlot.value)
            assertResourceListCount(context, emptyDetail, 0uL, ::codexAgentPluginDetailSkillsCount)
            assertResourceListCount(
                context, emptyDetail, 0uL, ::codexAgentPluginDetailConnectorsCount,
            )
            assertResourceListCount(
                context, emptyDetail, 0uL, ::codexAgentPluginDetailMcpServersCount,
            )
            val absentInstall = assertNotNull(absentInstallSlot.value)
            assertResourceListCount(
                context, absentInstall, 0uL, ::codexAgentPluginInstallResultConnectorsCount,
            )
            assertResourceListFlag(
                context, absentInstall, 0, ::codexAgentPluginInstallResultHasMessage,
            )
            assertAbsentResourceListString(
                context, absentInstall, ::codexAgentPluginInstallResultMessageCopy,
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, installConnectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, nestedConnectorTwoSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, nestedConnectorOneSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, nestedSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, nestedSummarySlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginInstallResultDestroy(context, absentInstallSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginInstallResultDestroy(context, installSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginDetailDestroy(context, emptyDetailSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginDetailDestroy(context, detailSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSummaryDestroy(context, summarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, pluginSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun rejectsInvalidListsFlagsEnumsUtf8ContextsTypesAndOutputs(): Unit = memScoped {
        val contextSlot = resourceListContext()
        val otherContextSlot = resourceListContext()
        val context = assertNotNull(contextSlot.value)
        val otherContext = assertNotNull(otherContextSlot.value)
        val connectorSlot = createResourceListConnector(context, "valid")
        val connector = assertNotNull(connectorSlot.value)
        val output = emptyResourceListHandle()
        val occupied = alloc<COpaquePointerVar>().also { it.value = connector }
        val empty = emptyResourceListView()
        try {
            listOf(-1, 2).forEach { invalidFlag ->
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConnectorCreate(
                        context,
                        resourceListView("id"),
                        resourceListView("name"),
                        resourceListView("description"),
                        invalidFlag,
                        empty,
                        0,
                        1,
                        null,
                        0uL,
                        output.ptr,
                    ),
                )
                assertNull(output.value)
            }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("id"),
                    invalidResourceListUtf8View(),
                    resourceListView("description"),
                    0,
                    empty,
                    0,
                    1,
                    null,
                    0uL,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("id"),
                    resourceListView("name"),
                    resourceListView("description"),
                    0,
                    empty,
                    0,
                    1,
                    invalidResourceListUtf8View(),
                    1uL,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("id"),
                    resourceListView("name"),
                    resourceListView("description"),
                    0,
                    empty,
                    0,
                    1,
                    null,
                    1uL,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("id"),
                    resourceListView("name"),
                    resourceListView("description"),
                    0,
                    empty,
                    0,
                    1,
                    null,
                    ULong.MAX_VALUE,
                    output.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorCreate(
                    context,
                    resourceListView("id"),
                    resourceListView("name"),
                    resourceListView("description"),
                    0,
                    empty,
                    0,
                    1,
                    null,
                    0uL,
                    occupied.ptr,
                ),
            )
            assertEquals(connector, occupied.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillCreate(
                    context,
                    resourceListView("skill"),
                    resourceListView("Skill"),
                    resourceListView("Description"),
                    resourceListView("/skill"),
                    99,
                    1,
                    0,
                    empty,
                    null,
                    0uL,
                    0,
                    0,
                    0,
                    output.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillCreate(
                    context,
                    resourceListView("skill"),
                    resourceListView("Skill"),
                    resourceListView("Description"),
                    resourceListView("/skill"),
                    1,
                    1,
                    0,
                    empty,
                    null,
                    0uL,
                    0,
                    0,
                    1,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val wrongHandles = resourceListHandles(connector)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentSkillCatalogCreate(
                    context, wrongHandles, 1uL, null, 0uL, output.ptr,
                ),
            )
            assertNull(output.value)
            val foreignHandles = resourceListHandles(connector)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentPluginInstallResultCreate(
                    otherContext, 0, foreignHandles, 1uL, 0, empty, output.ptr,
                ),
            )
            assertNull(output.value)

            val untouchedCount = alloc<ULongVar>().also { it.value = 81uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentSkillCatalogSkillsCount(context, connector, untouchedCount.ptr),
            )
            assertEquals(81uL, untouchedCount.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConnectorPluginNamesCount(context, connector, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillCatalogSkillsAt(context, connector, 0uL, null),
            )

            val staleSlot = createResourceListConnector(otherContext, "stale")
            val stale = assertNotNull(staleSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentConnectorIdCopy(otherContext, stale, null, 0uL, untouchedCount.ptr),
            )
            assertEquals(81uL, untouchedCount.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }
}

private fun MemScope.resourceListContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyResourceListHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.resourceListView(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = value.encodeToByteArray()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
        view.size = bytes.size.toULong()
    }.ptr

private fun MemScope.emptyResourceListView(): CPointer<codex_agent_string_view> =
    resourceListView("")

private fun MemScope.mutableResourceListView(value: String): ResourceListMutableView {
    val bytes = value.encodeToByteArray()
    require(bytes.isNotEmpty())
    val buffer = allocArray<UByteVar>(bytes.size)
    bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    return ResourceListMutableView(
        view = alloc<codex_agent_string_view>().also {
            it.data = buffer
            it.size = bytes.size.toULong()
        }.ptr,
        bytes = buffer,
    )
}

private fun MemScope.invalidResourceListUtf8View(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also {
        val bytes = allocArray<UByteVar>(2)
        bytes[0] = 0xc3u
        bytes[1] = 0x28u
        it.data = bytes
        it.size = 2uL
    }.ptr

private fun MemScope.resourceListViews(vararg values: String): ResourceListViews {
    val views = allocArray<codex_agent_string_view>(values.size)
    val buffers = values.mapIndexed { index, value ->
        val bytes = value.encodeToByteArray()
        val buffer = if (bytes.isEmpty()) null else allocArray<UByteVar>(bytes.size)
        bytes.forEachIndexed { byteIndex, byte -> checkNotNull(buffer)[byteIndex] = byte.toUByte() }
        views[index].data = buffer
        views[index].size = bytes.size.toULong()
        buffer
    }
    return ResourceListViews(views, buffers)
}

private fun MemScope.resourceListHandles(vararg handles: COpaquePointer): CPointer<COpaquePointerVar> =
    allocArray<COpaquePointerVar>(handles.size).also { values ->
        handles.forEachIndexed { index, handle -> values[index] = handle }
    }

private fun MemScope.createResourceListConnector(
    context: COpaquePointer,
    id: String,
): COpaquePointerVar = emptyResourceListHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConnectorCreate(
            context,
            resourceListView(id),
            resourceListView("Connector $id"),
            resourceListView("Description"),
            0,
            emptyResourceListView(),
            1,
            1,
            null,
            0uL,
            slot.ptr,
        ),
    )
}

private fun MemScope.createResourceListReference(
    context: COpaquePointer,
    id: String,
    name: String,
): COpaquePointerVar = emptyResourceListHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPluginReferenceCreate(
            context,
            resourceListView(id),
            resourceListView(name),
            resourceListView("marketplace"),
            0,
            emptyResourceListView(),
            0,
            emptyResourceListView(),
            slot.ptr,
        ),
    )
}

private fun MemScope.createResourceListPluginSkill(
    context: COpaquePointer,
    name: String,
): COpaquePointerVar = emptyResourceListHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPluginSkillCreate(
            context,
            resourceListView(name),
            resourceListView("Plugin skill"),
            1,
            0,
            emptyResourceListView(),
            slot.ptr,
        ),
    )
}

private fun MemScope.createResourceListSummary(
    context: COpaquePointer,
    reference: COpaquePointer,
    displayName: String,
): COpaquePointerVar = emptyResourceListHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPluginSummaryCreate(
            context,
            reference,
            resourceListView(displayName),
            resourceListView("Summary"),
            1,
            1,
            1,
            0,
            1,
            null,
            0uL,
            0,
            emptyResourceListView(),
            0,
            emptyResourceListView(),
            0,
            emptyResourceListView(),
            0,
            emptyResourceListView(),
            slot.ptr,
        ),
    )
}

private fun MemScope.assertResourceListString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: ResourceListStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertAbsentResourceListString(
    context: COpaquePointer,
    handle: COpaquePointer,
    copy: ResourceListStringCopy,
) {
    val required = alloc<ULongVar>().also { it.value = 77uL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, copy(context, handle, null, 0uL, required.ptr))
    assertEquals(77uL, required.value)
}

private fun MemScope.assertResourceListStringAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    copy: ResourceListStringCopyAt,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, index, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, index, buffer, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertResourceListFlag(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: ResourceListIntGetter,
) = assertResourceListInt(context, handle, expected, getter)

private fun MemScope.assertResourceListInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: ResourceListIntGetter,
) {
    val output = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertResourceListCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    getter: ResourceListCountGetter,
) {
    val output = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertOptionalSummaryString(
    context: COpaquePointer,
    summary: COpaquePointer,
    expectedPresent: Int,
    expected: String?,
    has: ResourceListIntGetter,
    copy: ResourceListStringCopy,
) {
    assertResourceListFlag(context, summary, expectedPresent, has)
    if (expected == null) {
        assertAbsentResourceListString(context, summary, copy)
    } else {
        assertResourceListString(context, summary, expected, copy)
    }
}

private data class ResourceListMutableView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>,
)

private data class ResourceListViews(
    val views: CPointer<codex_agent_string_view>,
    val buffers: List<CPointer<UByteVar>?>,
)

private typealias ResourceListStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias ResourceListStringCopyAt = (
    COpaquePointer?, COpaquePointer?, ULong, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias ResourceListIntGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?,
) -> Int

private typealias ResourceListCountGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?,
) -> Int
