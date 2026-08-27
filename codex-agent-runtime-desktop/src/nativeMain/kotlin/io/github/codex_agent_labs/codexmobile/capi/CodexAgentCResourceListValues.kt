@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentCatalogFreshness
import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginDetail
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallPolicy
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallResult
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin
import io.github.codex_agent_labs.codexmobile.agent.AgentSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillScope
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCConnectorSnapshot(
    val value: AgentConnector,
) : CodexAgentCSnapshot

internal data class CodexAgentCSkillSnapshot(
    val value: AgentSkill,
) : CodexAgentCSnapshot

internal data class CodexAgentCSkillCatalogSnapshot(
    val value: AgentSkillCatalog,
) : CodexAgentCSnapshot

internal data class CodexAgentCPluginSummarySnapshot(
    val value: AgentPluginSummary,
) : CodexAgentCSnapshot

internal data class CodexAgentCPluginCatalogSnapshot(
    val value: AgentPluginCatalog,
) : CodexAgentCSnapshot

internal data class CodexAgentCPluginDetailSnapshot(
    val value: AgentPluginDetail,
) : CodexAgentCSnapshot

internal data class CodexAgentCPluginInstallResultSnapshot(
    val value: AgentPluginInstallResult,
) : CodexAgentCSnapshot

@CName("codex_agent_connector_create")
public fun codexAgentConnectorCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    name: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    hasInstallUrl: Int,
    installUrl: CPointer<codex_agent_string_view>?,
    isAccessible: Int,
    isEnabled: Int,
    pluginNames: CPointer<codex_agent_string_view>?,
    pluginNameCount: ULong,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConnector)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(isAccessible)
    requireBoolean(isEnabled)
    val value = AgentConnector(
        id = id.readRequiredUtf8(),
        name = name.readRequiredUtf8(),
        description = description.readRequiredUtf8(),
        installUrl = installUrl.readOptionalUtf8(hasInstallUrl),
        isAccessible = isAccessible == 1,
        isEnabled = isEnabled == 1,
        pluginNames = readStringList(pluginNames, pluginNameCount),
    )
    installOutput(outConnector, createSnapshot(contextPointer, CodexAgentCConnectorSnapshot(value)))
}

@CName("codex_agent_connector_destroy")
public fun codexAgentConnectorDestroy(
    context: COpaquePointer?,
    connector: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCConnectorSnapshot>(context, connector)

@CName("codex_agent_connector_id_copy")
public fun codexAgentConnectorIdCopy(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCConnectorSnapshot>(
    context, connector, buffer, capacity, outRequired,
) { it.value.id }

@CName("codex_agent_connector_name_copy")
public fun codexAgentConnectorNameCopy(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCConnectorSnapshot>(
    context, connector, buffer, capacity, outRequired,
) { it.value.name }

@CName("codex_agent_connector_description_copy")
public fun codexAgentConnectorDescriptionCopy(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCConnectorSnapshot>(
    context, connector, buffer, capacity, outRequired,
) { it.value.description }

@CName("codex_agent_connector_has_install_url")
public fun codexAgentConnectorHasInstallUrl(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outHasInstallUrl: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCConnectorSnapshot>(context, connector, outHasInstallUrl) {
    it.value.installUrl != null
}

@CName("codex_agent_connector_install_url_copy")
public fun codexAgentConnectorInstallUrlCopy(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCConnectorSnapshot>(
    context, connector, buffer, capacity, outRequired,
) { it.value.installUrl }

@CName("codex_agent_connector_is_accessible")
public fun codexAgentConnectorIsAccessible(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outIsAccessible: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCConnectorSnapshot>(context, connector, outIsAccessible) {
    it.value.isAccessible
}

@CName("codex_agent_connector_is_enabled")
public fun codexAgentConnectorIsEnabled(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outIsEnabled: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCConnectorSnapshot>(context, connector, outIsEnabled) {
    it.value.isEnabled
}

@CName("codex_agent_connector_plugin_names_count")
public fun codexAgentConnectorPluginNamesCount(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCConnectorSnapshot>(context, connector, outCount) {
    it.value.pluginNames.size
}

@CName("codex_agent_connector_plugin_names_copy_at")
public fun codexAgentConnectorPluginNamesCopyAt(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCConnectorSnapshot>(
    context, connector, index, buffer, capacity, outRequired,
) { it.value.pluginNames }

@CName("codex_agent_skill_create")
public fun codexAgentSkillCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    displayName: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    path: CPointer<codex_agent_string_view>?,
    scope: Int,
    isEnabled: Int,
    hasBrandColor: Int,
    brandColor: CPointer<codex_agent_string_view>?,
    dependencies: CPointer<codex_agent_string_view>?,
    dependencyCount: ULong,
    canUninstall: Int,
    hasOrigin: Int,
    origin: Int,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSkill)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(isEnabled)
    requireBoolean(canUninstall)
    requireBoolean(hasOrigin)
    if (hasOrigin == 0) require(origin == 0)
    val parsedScope = skillScopeFromCValue(scope)
    val canonical = AgentSkill(
        name = name.readRequiredUtf8(),
        displayName = displayName.readRequiredUtf8(),
        description = description.readRequiredUtf8(),
        path = path.readRequiredUtf8(),
        scope = parsedScope,
        isEnabled = isEnabled == 1,
        brandColor = brandColor.readOptionalUtf8(hasBrandColor),
        dependencies = readStringList(dependencies, dependencyCount),
        canUninstall = canUninstall == 1,
    )
    val required = if (hasOrigin == 1) canonical.copy(origin = resourceOriginFromCValue(origin)) else canonical
    installOutput(outSkill, createSnapshot(contextPointer, CodexAgentCSkillSnapshot(required)))
}

@CName("codex_agent_skill_destroy")
public fun codexAgentSkillDestroy(
    context: COpaquePointer?,
    skill: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCSkillSnapshot>(context, skill)

@CName("codex_agent_skill_name_copy")
public fun codexAgentSkillNameCopy(
    context: COpaquePointer?, skill: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCSkillSnapshot>(
    context, skill, buffer, capacity, outRequired,
) { it.value.name }

@CName("codex_agent_skill_display_name_copy")
public fun codexAgentSkillDisplayNameCopy(
    context: COpaquePointer?, skill: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCSkillSnapshot>(
    context, skill, buffer, capacity, outRequired,
) { it.value.displayName }

@CName("codex_agent_skill_description_copy")
public fun codexAgentSkillDescriptionCopy(
    context: COpaquePointer?, skill: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCSkillSnapshot>(
    context, skill, buffer, capacity, outRequired,
) { it.value.description }

@CName("codex_agent_skill_path_copy")
public fun codexAgentSkillPathCopy(
    context: COpaquePointer?, skill: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCSkillSnapshot>(
    context, skill, buffer, capacity, outRequired,
) { it.value.path }

@CName("codex_agent_skill_scope")
public fun codexAgentSkillScope(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    outScope: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCSkillSnapshot>(context, skill, outScope) {
    skillScopeToCValue(it.value.scope)
}

@CName("codex_agent_skill_is_enabled")
public fun codexAgentSkillIsEnabled(
    context: COpaquePointer?, skill: COpaquePointer?, outIsEnabled: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCSkillSnapshot>(context, skill, outIsEnabled) {
    it.value.isEnabled
}

@CName("codex_agent_skill_has_brand_color")
public fun codexAgentSkillHasBrandColor(
    context: COpaquePointer?, skill: COpaquePointer?, outHasBrandColor: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCSkillSnapshot>(context, skill, outHasBrandColor) {
    it.value.brandColor != null
}

@CName("codex_agent_skill_brand_color_copy")
public fun codexAgentSkillBrandColorCopy(
    context: COpaquePointer?, skill: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCSkillSnapshot>(
    context, skill, buffer, capacity, outRequired,
) { it.value.brandColor }

@CName("codex_agent_skill_dependencies_count")
public fun codexAgentSkillDependenciesCount(
    context: COpaquePointer?, skill: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCSkillSnapshot>(context, skill, outCount) {
    it.value.dependencies.size
}

@CName("codex_agent_skill_dependencies_copy_at")
public fun codexAgentSkillDependenciesCopyAt(
    context: COpaquePointer?, skill: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCSkillSnapshot>(
    context, skill, index, buffer, capacity, outRequired,
) { it.value.dependencies }

@CName("codex_agent_skill_can_uninstall")
public fun codexAgentSkillCanUninstall(
    context: COpaquePointer?, skill: COpaquePointer?, outCanUninstall: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCSkillSnapshot>(context, skill, outCanUninstall) {
    it.value.canUninstall
}

@CName("codex_agent_skill_origin")
public fun codexAgentSkillOrigin(
    context: COpaquePointer?, skill: COpaquePointer?, outOrigin: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCSkillSnapshot>(context, skill, outOrigin) {
    resourceOriginToCValue(it.value.origin)
}

@CName("codex_agent_skill_catalog_create")
public fun codexAgentSkillCatalogCreate(
    context: COpaquePointer?,
    skills: CPointer<COpaquePointerVar>?,
    skillCount: ULong,
    errors: CPointer<codex_agent_string_view>?,
    errorCount: ULong,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outCatalog)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedSkills = readSnapshotList<CodexAgentCSkillSnapshot, AgentSkill>(
        contextPointer, skills, skillCount,
    ) { it.value.ownedCopy() }
    if (copiedSkills.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedSkills.status
    val value = AgentSkillCatalog(
        skills = checkNotNull(copiedSkills.value),
        errors = readStringList(errors, errorCount),
    )
    installOutput(outCatalog, createSnapshot(contextPointer, CodexAgentCSkillCatalogSnapshot(value)))
}

@CName("codex_agent_skill_catalog_destroy")
public fun codexAgentSkillCatalogDestroy(
    context: COpaquePointer?, catalog: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCSkillCatalogSnapshot>(context, catalog)

@CName("codex_agent_skill_catalog_skills_count")
public fun codexAgentSkillCatalogSkillsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCSkillCatalogSnapshot>(context, catalog, outCount) {
    it.value.skills.size
}

@CName("codex_agent_skill_catalog_skills_at")
public fun codexAgentSkillCatalogSkillsAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCSkillCatalogSnapshot, AgentSkill>(
    context, catalog, index, outSkill, { it.value.skills },
) { CodexAgentCSkillSnapshot(it.ownedCopy()) }

@CName("codex_agent_skill_catalog_errors_count")
public fun codexAgentSkillCatalogErrorsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCSkillCatalogSnapshot>(context, catalog, outCount) {
    it.value.errors.size
}

@CName("codex_agent_skill_catalog_errors_copy_at")
public fun codexAgentSkillCatalogErrorsCopyAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCSkillCatalogSnapshot>(
    context, catalog, index, buffer, capacity, outRequired,
) { it.value.errors }

@CName("codex_agent_plugin_summary_create")
public fun codexAgentPluginSummaryCreate(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    displayName: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    isInstalled: Int,
    isEnabled: Int,
    installPolicy: Int,
    authPolicy: Int,
    isAvailable: Int,
    capabilities: CPointer<codex_agent_string_view>?,
    capabilityCount: ULong,
    hasBrandColor: Int,
    brandColor: CPointer<codex_agent_string_view>?,
    hasPrivacyPolicyUrl: Int,
    privacyPolicyUrl: CPointer<codex_agent_string_view>?,
    hasTermsOfServiceUrl: Int,
    termsOfServiceUrl: CPointer<codex_agent_string_view>?,
    hasWebsiteUrl: Int,
    websiteUrl: CPointer<codex_agent_string_view>?,
    outSummary: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSummary)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(isInstalled)
    requireBoolean(isEnabled)
    requireBoolean(isAvailable)
    val copiedDisplayName = displayName.readRequiredUtf8()
    val copiedDescription = description.readRequiredUtf8()
    val copiedCapabilities = readStringList(capabilities, capabilityCount)
    val copiedBrandColor = brandColor.readOptionalUtf8(hasBrandColor)
    val copiedPrivacyPolicyUrl = privacyPolicyUrl.readOptionalUtf8(hasPrivacyPolicyUrl)
    val copiedTermsOfServiceUrl = termsOfServiceUrl.readOptionalUtf8(hasTermsOfServiceUrl)
    val copiedWebsiteUrl = websiteUrl.readOptionalUtf8(hasWebsiteUrl)
    withPayload<CodexAgentCPluginReferenceSnapshot>(
        contextPointer, reference, CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = AgentPluginSummary(
            reference = it.value.ownedCopy(),
            displayName = copiedDisplayName,
            description = copiedDescription,
            isInstalled = isInstalled == 1,
            isEnabled = isEnabled == 1,
            installPolicy = pluginInstallPolicyFromCValue(installPolicy),
            authPolicy = pluginAuthPolicyFromCValue(authPolicy),
            isAvailable = isAvailable == 1,
            capabilities = copiedCapabilities,
            brandColor = copiedBrandColor,
            privacyPolicyUrl = copiedPrivacyPolicyUrl,
            termsOfServiceUrl = copiedTermsOfServiceUrl,
            websiteUrl = copiedWebsiteUrl,
        )
        installOutput(outSummary, createSnapshot(contextPointer, CodexAgentCPluginSummarySnapshot(value)))
    }
}

@CName("codex_agent_plugin_summary_destroy")
public fun codexAgentPluginSummaryDestroy(
    context: COpaquePointer?, summary: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCPluginSummarySnapshot>(context, summary)

@CName("codex_agent_plugin_summary_reference")
public fun codexAgentPluginSummaryReference(
    context: COpaquePointer?, summary: COpaquePointer?, outReference: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginSummarySnapshot, AgentPluginReference>(
    context, summary, 0uL, outReference, { listOf(it.value.reference) },
) { CodexAgentCPluginReferenceSnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_summary_display_name_copy")
public fun codexAgentPluginSummaryDisplayNameCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.displayName }

@CName("codex_agent_plugin_summary_description_copy")
public fun codexAgentPluginSummaryDescriptionCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.description }

@CName("codex_agent_plugin_summary_is_installed")
public fun codexAgentPluginSummaryIsInstalled(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.isInstalled
}

@CName("codex_agent_plugin_summary_is_enabled")
public fun codexAgentPluginSummaryIsEnabled(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.isEnabled
}

@CName("codex_agent_plugin_summary_install_policy")
public fun codexAgentPluginSummaryInstallPolicy(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    pluginInstallPolicyToCValue(it.value.installPolicy)
}

@CName("codex_agent_plugin_summary_auth_policy")
public fun codexAgentPluginSummaryAuthPolicy(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    pluginAuthPolicyToCValue(it.value.authPolicy)
}

@CName("codex_agent_plugin_summary_is_available")
public fun codexAgentPluginSummaryIsAvailable(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.isAvailable
}

@CName("codex_agent_plugin_summary_capabilities_count")
public fun codexAgentPluginSummaryCapabilitiesCount(
    context: COpaquePointer?, summary: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginSummarySnapshot>(context, summary, outCount) {
    it.value.capabilities.size
}

@CName("codex_agent_plugin_summary_capabilities_copy_at")
public fun codexAgentPluginSummaryCapabilitiesCopyAt(
    context: COpaquePointer?, summary: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCPluginSummarySnapshot>(
    context, summary, index, buffer, capacity, outRequired,
) { it.value.capabilities }

@CName("codex_agent_plugin_summary_has_brand_color")
public fun codexAgentPluginSummaryHasBrandColor(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.brandColor != null
}

@CName("codex_agent_plugin_summary_brand_color_copy")
public fun codexAgentPluginSummaryBrandColorCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.brandColor }

@CName("codex_agent_plugin_summary_has_privacy_policy_url")
public fun codexAgentPluginSummaryHasPrivacyPolicyUrl(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.privacyPolicyUrl != null
}

@CName("codex_agent_plugin_summary_privacy_policy_url_copy")
public fun codexAgentPluginSummaryPrivacyPolicyUrlCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.privacyPolicyUrl }

@CName("codex_agent_plugin_summary_has_terms_of_service_url")
public fun codexAgentPluginSummaryHasTermsOfServiceUrl(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.termsOfServiceUrl != null
}

@CName("codex_agent_plugin_summary_terms_of_service_url_copy")
public fun codexAgentPluginSummaryTermsOfServiceUrlCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.termsOfServiceUrl }

@CName("codex_agent_plugin_summary_has_website_url")
public fun codexAgentPluginSummaryHasWebsiteUrl(
    context: COpaquePointer?, summary: COpaquePointer?, outValue: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginSummarySnapshot>(context, summary, outValue) {
    it.value.websiteUrl != null
}

@CName("codex_agent_plugin_summary_website_url_copy")
public fun codexAgentPluginSummaryWebsiteUrlCopy(
    context: COpaquePointer?, summary: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCPluginSummarySnapshot>(
    context, summary, buffer, capacity, outRequired,
) { it.value.websiteUrl }

@CName("codex_agent_plugin_catalog_create")
public fun codexAgentPluginCatalogCreate(
    context: COpaquePointer?,
    plugins: CPointer<COpaquePointerVar>?,
    pluginCount: ULong,
    errors: CPointer<codex_agent_string_view>?,
    errorCount: ULong,
    freshness: Int,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outCatalog)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedPlugins = readSnapshotList<CodexAgentCPluginSummarySnapshot, AgentPluginSummary>(
        contextPointer, plugins, pluginCount,
    ) { it.value.ownedCopy() }
    if (copiedPlugins.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedPlugins.status
    val value = AgentPluginCatalog(
        plugins = checkNotNull(copiedPlugins.value),
        errors = readStringList(errors, errorCount),
        freshness = catalogFreshnessFromCValue(freshness),
    )
    installOutput(outCatalog, createSnapshot(contextPointer, CodexAgentCPluginCatalogSnapshot(value)))
}

@CName("codex_agent_plugin_catalog_destroy")
public fun codexAgentPluginCatalogDestroy(
    context: COpaquePointer?, catalog: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCPluginCatalogSnapshot>(context, catalog)

@CName("codex_agent_plugin_catalog_plugins_count")
public fun codexAgentPluginCatalogPluginsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginCatalogSnapshot>(context, catalog, outCount) {
    it.value.plugins.size
}

@CName("codex_agent_plugin_catalog_plugins_at")
public fun codexAgentPluginCatalogPluginsAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    outSummary: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginCatalogSnapshot, AgentPluginSummary>(
    context, catalog, index, outSummary, { it.value.plugins },
) { CodexAgentCPluginSummarySnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_catalog_errors_count")
public fun codexAgentPluginCatalogErrorsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginCatalogSnapshot>(context, catalog, outCount) {
    it.value.errors.size
}

@CName("codex_agent_plugin_catalog_errors_copy_at")
public fun codexAgentPluginCatalogErrorsCopyAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCPluginCatalogSnapshot>(
    context, catalog, index, buffer, capacity, outRequired,
) { it.value.errors }

@CName("codex_agent_plugin_catalog_freshness")
public fun codexAgentPluginCatalogFreshness(
    context: COpaquePointer?, catalog: COpaquePointer?, outFreshness: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCPluginCatalogSnapshot>(context, catalog, outFreshness) {
    catalogFreshnessToCValue(it.value.freshness)
}

@CName("codex_agent_plugin_detail_create")
public fun codexAgentPluginDetailCreate(
    context: COpaquePointer?,
    summary: COpaquePointer?,
    description: CPointer<codex_agent_string_view>?,
    skills: CPointer<COpaquePointerVar>?,
    skillCount: ULong,
    connectors: CPointer<COpaquePointerVar>?,
    connectorCount: ULong,
    mcpServers: CPointer<codex_agent_string_view>?,
    mcpServerCount: ULong,
    hookCount: Int,
    outDetail: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outDetail)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedDescription = description.readRequiredUtf8()
    val copiedSkills = readSnapshotList<CodexAgentCPluginSkillSnapshot, AgentPluginSkill>(
        contextPointer, skills, skillCount,
    ) { it.value.ownedCopy() }
    if (copiedSkills.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedSkills.status
    val copiedConnectors = readSnapshotList<CodexAgentCConnectorSnapshot, AgentConnector>(
        contextPointer, connectors, connectorCount,
    ) { it.value.ownedCopy() }
    if (copiedConnectors.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedConnectors.status
    val copiedMcpServers = readStringList(mcpServers, mcpServerCount)
    withPayload<CodexAgentCPluginSummarySnapshot>(
        contextPointer, summary, CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = AgentPluginDetail(
            summary = it.value.ownedCopy(),
            description = copiedDescription,
            skills = checkNotNull(copiedSkills.value),
            connectors = checkNotNull(copiedConnectors.value),
            mcpServers = copiedMcpServers,
            hookCount = hookCount,
        )
        installOutput(outDetail, createSnapshot(contextPointer, CodexAgentCPluginDetailSnapshot(value)))
    }
}

@CName("codex_agent_plugin_detail_destroy")
public fun codexAgentPluginDetailDestroy(
    context: COpaquePointer?, detail: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCPluginDetailSnapshot>(context, detail)

@CName("codex_agent_plugin_detail_summary")
public fun codexAgentPluginDetailSummary(
    context: COpaquePointer?, detail: COpaquePointer?, outSummary: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginDetailSnapshot, AgentPluginSummary>(
    context, detail, 0uL, outSummary, { listOf(it.value.summary) },
) { CodexAgentCPluginSummarySnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_detail_description_copy")
public fun codexAgentPluginDetailDescriptionCopy(
    context: COpaquePointer?, detail: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListString<CodexAgentCPluginDetailSnapshot>(
    context, detail, buffer, capacity, outRequired,
) { it.value.description }

@CName("codex_agent_plugin_detail_skills_count")
public fun codexAgentPluginDetailSkillsCount(
    context: COpaquePointer?, detail: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginDetailSnapshot>(context, detail, outCount) {
    it.value.skills.size
}

@CName("codex_agent_plugin_detail_skills_at")
public fun codexAgentPluginDetailSkillsAt(
    context: COpaquePointer?, detail: COpaquePointer?, index: ULong,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginDetailSnapshot, AgentPluginSkill>(
    context, detail, index, outSkill, { it.value.skills },
) { CodexAgentCPluginSkillSnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_detail_connectors_count")
public fun codexAgentPluginDetailConnectorsCount(
    context: COpaquePointer?, detail: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginDetailSnapshot>(context, detail, outCount) {
    it.value.connectors.size
}

@CName("codex_agent_plugin_detail_connectors_at")
public fun codexAgentPluginDetailConnectorsAt(
    context: COpaquePointer?, detail: COpaquePointer?, index: ULong,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginDetailSnapshot, AgentConnector>(
    context, detail, index, outConnector, { it.value.connectors },
) { CodexAgentCConnectorSnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_detail_mcp_servers_count")
public fun codexAgentPluginDetailMcpServersCount(
    context: COpaquePointer?, detail: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginDetailSnapshot>(context, detail, outCount) {
    it.value.mcpServers.size
}

@CName("codex_agent_plugin_detail_mcp_servers_copy_at")
public fun codexAgentPluginDetailMcpServersCopyAt(
    context: COpaquePointer?, detail: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyResourceListStringAt<CodexAgentCPluginDetailSnapshot>(
    context, detail, index, buffer, capacity, outRequired,
) { it.value.mcpServers }

@CName("codex_agent_plugin_detail_hook_count")
public fun codexAgentPluginDetailHookCount(
    context: COpaquePointer?, detail: COpaquePointer?, outHookCount: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCPluginDetailSnapshot>(context, detail, outHookCount) {
    it.value.hookCount
}

@CName("codex_agent_plugin_install_result_create")
public fun codexAgentPluginInstallResultCreate(
    context: COpaquePointer?,
    authPolicy: Int,
    connectors: CPointer<COpaquePointerVar>?,
    connectorCount: ULong,
    hasMessage: Int,
    message: CPointer<codex_agent_string_view>?,
    outResult: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outResult)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedConnectors = readSnapshotList<CodexAgentCConnectorSnapshot, AgentConnector>(
        contextPointer, connectors, connectorCount,
    ) { it.value.ownedCopy() }
    if (copiedConnectors.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedConnectors.status
    val value = AgentPluginInstallResult(
        authPolicy = pluginAuthPolicyFromCValue(authPolicy),
        connectorsNeedingAuthentication = checkNotNull(copiedConnectors.value),
        message = message.readOptionalUtf8(hasMessage),
    )
    installOutput(outResult, createSnapshot(contextPointer, CodexAgentCPluginInstallResultSnapshot(value)))
}

@CName("codex_agent_plugin_install_result_destroy")
public fun codexAgentPluginInstallResultDestroy(
    context: COpaquePointer?, result: CPointer<COpaquePointerVar>?,
): Int = destroyResourceListValue<CodexAgentCPluginInstallResultSnapshot>(context, result)

@CName("codex_agent_plugin_install_result_auth_policy")
public fun codexAgentPluginInstallResultAuthPolicy(
    context: COpaquePointer?, result: COpaquePointer?, outPolicy: CPointer<IntVar>?,
): Int = resourceListInt<CodexAgentCPluginInstallResultSnapshot>(context, result, outPolicy) {
    pluginAuthPolicyToCValue(it.value.authPolicy)
}

@CName("codex_agent_plugin_install_result_connectors_count")
public fun codexAgentPluginInstallResultConnectorsCount(
    context: COpaquePointer?, result: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = resourceListCount<CodexAgentCPluginInstallResultSnapshot>(context, result, outCount) {
    it.value.connectorsNeedingAuthentication.size
}

@CName("codex_agent_plugin_install_result_connectors_at")
public fun codexAgentPluginInstallResultConnectorsAt(
    context: COpaquePointer?, result: COpaquePointer?, index: ULong,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = nestedResourceListValue<CodexAgentCPluginInstallResultSnapshot, AgentConnector>(
    context, result, index, outConnector, { it.value.connectorsNeedingAuthentication },
) { CodexAgentCConnectorSnapshot(it.ownedCopy()) }

@CName("codex_agent_plugin_install_result_has_message")
public fun codexAgentPluginInstallResultHasMessage(
    context: COpaquePointer?, result: COpaquePointer?, outHasMessage: CPointer<IntVar>?,
): Int = resourceListBoolean<CodexAgentCPluginInstallResultSnapshot>(context, result, outHasMessage) {
    it.value.message != null
}

@CName("codex_agent_plugin_install_result_message_copy")
public fun codexAgentPluginInstallResultMessageCopy(
    context: COpaquePointer?, result: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalResourceListString<CodexAgentCPluginInstallResultSnapshot>(
    context, result, buffer, capacity, outRequired,
) { it.value.message }

private data class SnapshotListResult<T : Any>(
    val status: Int,
    val value: List<T>? = null,
)

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readOptionalUtf8(hasValue: Int): String? {
    requireBoolean(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0uL)
        return null
    }
    return view.readUtf8()
}

private fun readStringList(
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): List<String> {
    requireValidList(count, values)
    if (count == 0uL) return emptyList()
    return List(count.toInt()) { index -> checkNotNull(values)[index].readUtf8() }
}

private inline fun <reified T : CodexAgentCSnapshot, R : Any> readSnapshotList(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    crossinline copy: (T) -> R,
): SnapshotListResult<R> {
    if (count > Int.MAX_VALUE.toULong() || count > 0uL && values == null) {
        return SnapshotListResult(CODEX_AGENT_STATUS_INVALID_ARGUMENT)
    }
    if (count == 0uL) return SnapshotListResult(CODEX_AGENT_STATUS_OK, emptyList())
    val result = ArrayList<R>(count.toInt())
    repeat(count.toInt()) { index ->
        var copied: R? = null
        val status = withPayload<T>(
            context,
            checkNotNull(values)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copied = copy(it)
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return SnapshotListResult(status)
        result += checkNotNull(copied)
    }
    return SnapshotListResult(CODEX_AGENT_STATUS_OK, result)
}

private fun requireValidList(count: ULong, values: Any?) {
    require(count <= Int.MAX_VALUE.toULong())
    require(count == 0uL || values != null)
}

private fun requireBoolean(value: Int) {
    require(value == 0 || value == 1)
}

private inline fun <reified T : CodexAgentCSnapshot> destroyResourceListValue(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyResourceListString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> String,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalResourceListString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> String?,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> resourceListBoolean(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<IntVar>?,
    crossinline select: (T) -> Boolean,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = if (select(it)) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> resourceListInt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<IntVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it)
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> resourceListCount(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<ULongVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it).toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyResourceListStringAt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> List<String>,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val values = select(it)
        if (index >= values.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(values[index.toInt()], buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot, E> nestedResourceListValue(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> List<E>,
    crossinline snapshot: (E) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val values = select(it)
        if (index >= values.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(output, createSnapshot(contextPointer, snapshot(values[index.toInt()])))
    }
}

private fun skillScopeFromCValue(value: Int): AgentSkillScope = when (value) {
    0 -> AgentSkillScope.SYSTEM
    1 -> AgentSkillScope.USER
    2 -> AgentSkillScope.REPO
    3 -> AgentSkillScope.PLUGIN
    4 -> AgentSkillScope.ADMIN
    else -> throw IllegalArgumentException("Unknown skill scope")
}

private fun skillScopeToCValue(value: AgentSkillScope): Int = when (value) {
    AgentSkillScope.SYSTEM -> 0
    AgentSkillScope.USER -> 1
    AgentSkillScope.REPO -> 2
    AgentSkillScope.PLUGIN -> 3
    AgentSkillScope.ADMIN -> 4
}

private fun resourceOriginFromCValue(value: Int): AgentResourceOrigin = when (value) {
    0 -> AgentResourceOrigin.USER
    1 -> AgentResourceOrigin.WORKSPACE
    2 -> AgentResourceOrigin.PLUGIN
    3 -> AgentResourceOrigin.MANAGED
    4 -> AgentResourceOrigin.UNKNOWN
    else -> throw IllegalArgumentException("Unknown resource origin")
}

private fun resourceOriginToCValue(value: AgentResourceOrigin): Int = when (value) {
    AgentResourceOrigin.USER -> 0
    AgentResourceOrigin.WORKSPACE -> 1
    AgentResourceOrigin.PLUGIN -> 2
    AgentResourceOrigin.MANAGED -> 3
    AgentResourceOrigin.UNKNOWN -> 4
}

private fun pluginInstallPolicyFromCValue(value: Int): AgentPluginInstallPolicy = when (value) {
    0 -> AgentPluginInstallPolicy.NOT_AVAILABLE
    1 -> AgentPluginInstallPolicy.AVAILABLE
    2 -> AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT
    else -> throw IllegalArgumentException("Unknown plugin install policy")
}

private fun pluginInstallPolicyToCValue(value: AgentPluginInstallPolicy): Int = when (value) {
    AgentPluginInstallPolicy.NOT_AVAILABLE -> 0
    AgentPluginInstallPolicy.AVAILABLE -> 1
    AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT -> 2
}

private fun pluginAuthPolicyFromCValue(value: Int): AgentPluginAuthPolicy = when (value) {
    0 -> AgentPluginAuthPolicy.ON_INSTALL
    1 -> AgentPluginAuthPolicy.ON_USE
    else -> throw IllegalArgumentException("Unknown plugin auth policy")
}

private fun pluginAuthPolicyToCValue(value: AgentPluginAuthPolicy): Int = when (value) {
    AgentPluginAuthPolicy.ON_INSTALL -> 0
    AgentPluginAuthPolicy.ON_USE -> 1
}

private fun catalogFreshnessFromCValue(value: Int): AgentCatalogFreshness = when (value) {
    0 -> AgentCatalogFreshness.LIVE
    1 -> AgentCatalogFreshness.FRESH_CACHE
    2 -> AgentCatalogFreshness.STALE_CACHE
    else -> throw IllegalArgumentException("Unknown catalog freshness")
}

private fun catalogFreshnessToCValue(value: AgentCatalogFreshness): Int = when (value) {
    AgentCatalogFreshness.LIVE -> 0
    AgentCatalogFreshness.FRESH_CACHE -> 1
    AgentCatalogFreshness.STALE_CACHE -> 2
}

private fun AgentPluginReference.ownedCopy(): AgentPluginReference = copy()

private fun AgentPluginSkill.ownedCopy(): AgentPluginSkill = copy()

private fun AgentConnector.ownedCopy(): AgentConnector = copy(pluginNames = pluginNames.toList())

private fun AgentSkill.ownedCopy(): AgentSkill = copy(dependencies = dependencies.toList())

private fun AgentPluginSummary.ownedCopy(): AgentPluginSummary = copy(
    reference = reference.ownedCopy(),
    capabilities = capabilities.toList(),
)
