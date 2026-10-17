@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthentication
import io.github.codex_agent_labs.codexagent.agent.AgentMcpOauthConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServerConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolApproval
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolExposureSurface
import io.github.codex_agent_labs.codexagent.agent.AgentMcpTransport
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.DoubleVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCMcpTransportSnapshot(
    val value: AgentMcpTransport,
) : CodexAgentCSnapshot

internal data class CodexAgentCMcpServerConfigurationSnapshot(
    val value: AgentMcpServerConfiguration,
) : CodexAgentCSnapshot

internal fun AgentMcpTransport.cAbiOwnedCopy(): AgentMcpTransport = when (this) {
    is AgentMcpTransport.Http -> copy(
        headers = headers?.entries?.associateTo(linkedMapOf()) { it.key to it.value },
        environmentHeaders = environmentHeaders?.entries?.associateTo(linkedMapOf()) { it.key to it.value },
    )
    is AgentMcpTransport.Stdio -> copy(
        arguments = arguments.toList(),
        environment = environment?.entries?.associateTo(linkedMapOf()) { it.key to it.value },
        forwardedEnvironment = forwardedEnvironment.map { it.copy() },
    )
}

internal fun AgentMcpServerConfiguration.cAbiOwnedCopy(): AgentMcpServerConfiguration = copy(
    transport = transport.cAbiOwnedCopy(),
    omitToolsFrom = omitToolsFrom?.toList(),
    enabledTools = enabledTools?.toList(),
    disabledTools = disabledTools?.toList(),
    scopes = scopes?.toList(),
    oauth = oauth?.copy(),
    tools = tools.entries.associateTo(linkedMapOf()) { it.key to it.value.copy() },
)

@CName("codex_agent_mcp_transport_from_http")
public fun codexAgentMcpTransportFromHttp(
    context: COpaquePointer?,
    http: COpaquePointer?,
    outTransport: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTransport)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpTransportHttpSnapshot>(contextPointer, http, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(outTransport, createSnapshot(contextPointer, CodexAgentCMcpTransportSnapshot(it.value.cAbiOwnedCopy())))
    }
}

@CName("codex_agent_mcp_transport_from_stdio")
public fun codexAgentMcpTransportFromStdio(
    context: COpaquePointer?,
    stdio: COpaquePointer?,
    outTransport: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTransport)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpTransportStdioSnapshot>(contextPointer, stdio, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(outTransport, createSnapshot(contextPointer, CodexAgentCMcpTransportSnapshot(it.value.cAbiOwnedCopy())))
    }
}

@CName("codex_agent_mcp_transport_destroy")
public fun codexAgentMcpTransportDestroy(
    context: COpaquePointer?,
    transport: CPointer<COpaquePointerVar>?,
): Int = destroyMcpServerConfigurationSnapshot<CodexAgentCMcpTransportSnapshot>(context, transport)

@CName("codex_agent_mcp_transport_kind")
public fun codexAgentMcpTransportKind(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpTransportSnapshot>(context, transport, outKind) {
    when (it.value) {
        is AgentMcpTransport.Http -> 0
        is AgentMcpTransport.Stdio -> 1
    }
}

@CName("codex_agent_mcp_transport_http")
public fun codexAgentMcpTransportHttp(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHttp: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHttp)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpTransportSnapshot>(contextPointer, transport, CodexAgentCHandleKind.SNAPSHOT) {
        val value = it.value as? AgentMcpTransport.Http
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(outHttp, createSnapshot(contextPointer, CodexAgentCMcpTransportHttpSnapshot(value.cAbiOwnedCopy() as AgentMcpTransport.Http)))
    }
}

@CName("codex_agent_mcp_transport_stdio")
public fun codexAgentMcpTransportStdio(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outStdio: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outStdio)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpTransportSnapshot>(contextPointer, transport, CodexAgentCHandleKind.SNAPSHOT) {
        val value = it.value as? AgentMcpTransport.Stdio
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(
            outStdio,
            createSnapshot(contextPointer, CodexAgentCMcpTransportStdioSnapshot(value.cAbiOwnedCopy() as AgentMcpTransport.Stdio)),
        )
    }
}

@CName("codex_agent_mcp_server_configuration_create")
public fun codexAgentMcpServerConfigurationCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    transport: COpaquePointer?,
    hasAuthentication: Int,
    authentication: Int,
    environmentId: CPointer<codex_agent_string_view>?,
    isEnabled: Int,
    isRequired: Int,
    supportsParallelToolCalls: Int,
    hasOmitToolsFrom: Int,
    omitToolsFrom: CPointer<IntVar>?,
    omitToolsFromCount: ULong,
    hasStartupTimeoutSeconds: Int,
    startupTimeoutSeconds: Double,
    hasToolTimeoutSeconds: Int,
    toolTimeoutSeconds: Double,
    hasDefaultToolApproval: Int,
    defaultToolApproval: Int,
    hasEnabledTools: Int,
    enabledTools: CPointer<codex_agent_string_view>?,
    enabledToolsCount: ULong,
    hasDisabledTools: Int,
    disabledTools: CPointer<codex_agent_string_view>?,
    disabledToolsCount: ULong,
    hasScopes: Int,
    scopes: CPointer<codex_agent_string_view>?,
    scopesCount: ULong,
    hasOauth: Int,
    oauth: COpaquePointer?,
    hasOauthResource: Int,
    oauthResource: CPointer<codex_agent_string_view>?,
    toolKeys: CPointer<codex_agent_string_view>?,
    toolConfigurations: CPointer<COpaquePointerVar>?,
    toolCount: ULong,
    outConfiguration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConfiguration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedTransport = arrayOfNulls<AgentMcpTransport>(1)
    val transportStatus = withPayload<CodexAgentCMcpTransportSnapshot>(
        contextPointer,
        transport,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copiedTransport[0] = it.value.cAbiOwnedCopy()
        CODEX_AGENT_STATUS_OK
    }
    if (transportStatus != CODEX_AGENT_STATUS_OK) return@abiStatus transportStatus

    val copiedOauth = arrayOfNulls<AgentMcpOauthConfiguration>(1)
    val oauthStatus = copyOptionalMcpServerConfigurationOauth(
        contextPointer,
        hasOauth,
        oauth,
        copiedOauth,
    )
    if (oauthStatus != CODEX_AGENT_STATUS_OK) return@abiStatus oauthStatus

    val copiedTools = linkedMapOf<String, AgentMcpToolConfiguration>()
    val toolsStatus = copyMcpServerConfigurationTools(
        contextPointer,
        toolKeys,
        toolConfigurations,
        toolCount,
        copiedTools,
    )
    if (toolsStatus != CODEX_AGENT_STATUS_OK) return@abiStatus toolsStatus

    val value = AgentMcpServerConfiguration(
        name = name.readMcpServerConfigurationRequiredUtf8(),
        transport = requireNotNull(copiedTransport[0]),
        authentication = optionalMcpAuthentication(hasAuthentication, authentication),
        environmentId = environmentId.readMcpServerConfigurationRequiredUtf8(),
        isEnabled = mcpServerConfigurationBoolean(isEnabled),
        isRequired = mcpServerConfigurationBoolean(isRequired),
        supportsParallelToolCalls = mcpServerConfigurationBoolean(supportsParallelToolCalls),
        omitToolsFrom = copyOptionalMcpToolExposureSurfaces(
            hasOmitToolsFrom,
            omitToolsFrom,
            omitToolsFromCount,
        ),
        startupTimeoutSeconds = optionalMcpServerConfigurationDouble(
            hasStartupTimeoutSeconds,
            startupTimeoutSeconds,
        ),
        toolTimeoutSeconds = optionalMcpServerConfigurationDouble(hasToolTimeoutSeconds, toolTimeoutSeconds),
        defaultToolApproval = optionalMcpToolApproval(hasDefaultToolApproval, defaultToolApproval),
        enabledTools = copyOptionalMcpServerConfigurationStrings(
            hasEnabledTools,
            enabledTools,
            enabledToolsCount,
        ),
        disabledTools = copyOptionalMcpServerConfigurationStrings(
            hasDisabledTools,
            disabledTools,
            disabledToolsCount,
        ),
        scopes = copyOptionalMcpServerConfigurationStrings(hasScopes, scopes, scopesCount),
        oauth = copiedOauth[0],
        oauthResource = oauthResource.readMcpServerConfigurationOptionalUtf8(hasOauthResource),
        tools = copiedTools,
    )
    installOutput(
        outConfiguration,
        createSnapshot(contextPointer, CodexAgentCMcpServerConfigurationSnapshot(value.cAbiOwnedCopy())),
    )
}

@CName("codex_agent_mcp_server_configuration_destroy")
public fun codexAgentMcpServerConfigurationDestroy(
    context: COpaquePointer?,
    configuration: CPointer<COpaquePointerVar>?,
): Int = destroyMcpServerConfigurationSnapshot<CodexAgentCMcpServerConfigurationSnapshot>(context, configuration)

@CName("codex_agent_mcp_server_configuration_name_copy")
public fun codexAgentMcpServerConfigurationNameCopy(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerConfigurationString(context, configuration, buffer, capacity, outRequired) { it.value.name }

@CName("codex_agent_mcp_server_configuration_transport")
public fun codexAgentMcpServerConfigurationTransport(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outTransport: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTransport)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        contextPointer,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outTransport,
            createSnapshot(contextPointer, CodexAgentCMcpTransportSnapshot(it.value.transport.cAbiOwnedCopy())),
        )
    }
}

@CName("codex_agent_mcp_server_configuration_authentication")
public fun codexAgentMcpServerConfigurationAuthentication(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasAuthentication: CPointer<IntVar>?,
    outAuthentication: CPointer<IntVar>?,
): Int = optionalMcpServerConfigurationInt(
    context,
    configuration,
    outHasAuthentication,
    outAuthentication,
) { it.value.authentication?.toMcpAuthenticationCValue() }

@CName("codex_agent_mcp_server_configuration_environment_id_copy")
public fun codexAgentMcpServerConfigurationEnvironmentIdCopy(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerConfigurationString(context, configuration, buffer, capacity, outRequired) {
    it.value.environmentId
}

@CName("codex_agent_mcp_server_configuration_is_enabled")
public fun codexAgentMcpServerConfigurationIsEnabled(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outIsEnabled: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outIsEnabled,
) { if (it.value.isEnabled) 1 else 0 }

@CName("codex_agent_mcp_server_configuration_is_required")
public fun codexAgentMcpServerConfigurationIsRequired(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outIsRequired: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outIsRequired,
) { if (it.value.isRequired) 1 else 0 }

@CName("codex_agent_mcp_server_configuration_supports_parallel_tool_calls")
public fun codexAgentMcpServerConfigurationSupportsParallelToolCalls(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outSupportsParallelToolCalls: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outSupportsParallelToolCalls,
) {
    if (it.value.supportsParallelToolCalls) 1 else 0
}

@CName("codex_agent_mcp_server_configuration_has_omit_tools_from")
public fun codexAgentMcpServerConfigurationHasOmitToolsFrom(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasOmitToolsFrom: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasOmitToolsFrom,
) {
    if (it.value.omitToolsFrom == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_omit_tools_from_count")
public fun codexAgentMcpServerConfigurationOmitToolsFromCount(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpServerConfigurationOptionalListCount(context, configuration, outCount) { it.value.omitToolsFrom }

@CName("codex_agent_mcp_server_configuration_omit_tools_from_at")
public fun codexAgentMcpServerConfigurationOmitToolsFromAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    outSurface: CPointer<IntVar>?,
): Int = abiStatus {
    if (outSurface == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val values = it.value.omitToolsFrom ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        val value = values.mcpServerConfigurationItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        outSurface.pointed.value = value.toMcpToolExposureSurfaceCValue()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_mcp_server_configuration_startup_timeout_seconds")
public fun codexAgentMcpServerConfigurationStartupTimeoutSeconds(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
    outValue: CPointer<DoubleVar>?,
): Int = optionalMcpServerConfigurationDouble(context, configuration, outHasValue, outValue) {
    it.value.startupTimeoutSeconds
}

@CName("codex_agent_mcp_server_configuration_tool_timeout_seconds")
public fun codexAgentMcpServerConfigurationToolTimeoutSeconds(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
    outValue: CPointer<DoubleVar>?,
): Int = optionalMcpServerConfigurationDouble(context, configuration, outHasValue, outValue) {
    it.value.toolTimeoutSeconds
}

@CName("codex_agent_mcp_server_configuration_default_tool_approval")
public fun codexAgentMcpServerConfigurationDefaultToolApproval(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
    outValue: CPointer<IntVar>?,
): Int = optionalMcpServerConfigurationInt(context, configuration, outHasValue, outValue) {
    it.value.defaultToolApproval?.toMcpToolApprovalCValue()
}

@CName("codex_agent_mcp_server_configuration_has_enabled_tools")
public fun codexAgentMcpServerConfigurationHasEnabledTools(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasEnabledTools: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasEnabledTools,
) {
    if (it.value.enabledTools == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_enabled_tools_count")
public fun codexAgentMcpServerConfigurationEnabledToolsCount(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpServerConfigurationOptionalListCount(context, configuration, outCount) { it.value.enabledTools }

@CName("codex_agent_mcp_server_configuration_enabled_tool_copy_at")
public fun codexAgentMcpServerConfigurationEnabledToolCopyAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerConfigurationOptionalStringListAt(
    context,
    configuration,
    index,
    buffer,
    capacity,
    outRequired,
) { it.value.enabledTools }

@CName("codex_agent_mcp_server_configuration_has_disabled_tools")
public fun codexAgentMcpServerConfigurationHasDisabledTools(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasDisabledTools: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasDisabledTools,
) {
    if (it.value.disabledTools == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_disabled_tools_count")
public fun codexAgentMcpServerConfigurationDisabledToolsCount(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpServerConfigurationOptionalListCount(context, configuration, outCount) { it.value.disabledTools }

@CName("codex_agent_mcp_server_configuration_disabled_tool_copy_at")
public fun codexAgentMcpServerConfigurationDisabledToolCopyAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerConfigurationOptionalStringListAt(
    context,
    configuration,
    index,
    buffer,
    capacity,
    outRequired,
) { it.value.disabledTools }

@CName("codex_agent_mcp_server_configuration_has_scopes")
public fun codexAgentMcpServerConfigurationHasScopes(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasScopes: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasScopes,
) {
    if (it.value.scopes == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_scopes_count")
public fun codexAgentMcpServerConfigurationScopesCount(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpServerConfigurationOptionalListCount(context, configuration, outCount) { it.value.scopes }

@CName("codex_agent_mcp_server_configuration_scope_copy_at")
public fun codexAgentMcpServerConfigurationScopeCopyAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerConfigurationOptionalStringListAt(
    context,
    configuration,
    index,
    buffer,
    capacity,
    outRequired,
) { it.value.scopes }

@CName("codex_agent_mcp_server_configuration_has_oauth")
public fun codexAgentMcpServerConfigurationHasOauth(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasOauth: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasOauth,
) {
    if (it.value.oauth == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_oauth")
public fun codexAgentMcpServerConfigurationOauth(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outOauth: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOauth)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        contextPointer,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val oauth = it.value.oauth ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outOauth,
            createSnapshot(contextPointer, CodexAgentCMcpOauthConfigurationSnapshot(oauth.copy())),
        )
    }
}

@CName("codex_agent_mcp_server_configuration_has_oauth_resource")
public fun codexAgentMcpServerConfigurationHasOauthResource(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasOauthResource: CPointer<IntVar>?,
): Int = mcpServerConfigurationInt<CodexAgentCMcpServerConfigurationSnapshot>(
    context,
    configuration,
    outHasOauthResource,
) {
    if (it.value.oauthResource == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration_oauth_resource_copy")
public fun codexAgentMcpServerConfigurationOauthResourceCopy(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalMcpServerConfigurationString(context, configuration, buffer, capacity, outRequired) {
    it.value.oauthResource
}

@CName("codex_agent_mcp_server_configuration_tools_count")
public fun codexAgentMcpServerConfigurationToolsCount(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outCount.pointed.value = it.value.tools.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_mcp_server_configuration_tools_key_copy_at")
public fun codexAgentMcpServerConfigurationToolsKeyCopyAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val entry = it.value.tools.entries.toList().mcpServerConfigurationItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(entry.key, buffer, capacity, outRequired)
    }
}

@CName("codex_agent_mcp_server_configuration_tools_value_at")
public fun codexAgentMcpServerConfigurationToolsValueAt(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    index: ULong,
    outToolConfiguration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outToolConfiguration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
        contextPointer,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val entry = it.value.tools.entries.toList().mcpServerConfigurationItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outToolConfiguration,
            createSnapshot(contextPointer, CodexAgentCMcpToolConfigurationSnapshot(entry.value.copy())),
        )
    }
}

private fun CPointer<codex_agent_string_view>?.readMcpServerConfigurationRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readMcpServerConfigurationOptionalUtf8(hasValue: Int): String? {
    requireMcpServerConfigurationFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0UL)
        return null
    }
    return view.readUtf8()
}

private fun requireMcpServerConfigurationFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun mcpServerConfigurationBoolean(value: Int): Boolean {
    requireMcpServerConfigurationFlag(value)
    return value == 1
}

private fun optionalMcpServerConfigurationInt(hasValue: Int, value: Int): Int? {
    requireMcpServerConfigurationFlag(hasValue)
    if (hasValue == 0) {
        require(value == 0)
        return null
    }
    return value
}

private fun optionalMcpServerConfigurationDouble(hasValue: Int, value: Double): Double? {
    requireMcpServerConfigurationFlag(hasValue)
    if (hasValue == 0) {
        require(value == 0.0)
        return null
    }
    return value
}

private fun optionalMcpAuthentication(hasValue: Int, value: Int): AgentMcpAuthentication? =
    optionalMcpServerConfigurationInt(hasValue, value)?.let(::mcpAuthenticationFromCValue)

private fun mcpAuthenticationFromCValue(value: Int): AgentMcpAuthentication = when (value) {
    0 -> AgentMcpAuthentication.OAUTH
    1 -> AgentMcpAuthentication.CHAT_GPT
    else -> throw IllegalArgumentException("Unknown MCP authentication")
}

private fun AgentMcpAuthentication.toMcpAuthenticationCValue(): Int = when (this) {
    AgentMcpAuthentication.OAUTH -> 0
    AgentMcpAuthentication.CHAT_GPT -> 1
}

private fun optionalMcpToolApproval(hasValue: Int, value: Int): AgentMcpToolApproval? =
    optionalMcpServerConfigurationInt(hasValue, value)?.let(::mcpToolApprovalFromCValue)

private fun mcpToolApprovalFromCValue(value: Int): AgentMcpToolApproval = when (value) {
    0 -> AgentMcpToolApproval.AUTO
    1 -> AgentMcpToolApproval.PROMPT
    2 -> AgentMcpToolApproval.WRITES
    3 -> AgentMcpToolApproval.APPROVE
    else -> throw IllegalArgumentException("Unknown MCP tool approval")
}

private fun AgentMcpToolApproval.toMcpToolApprovalCValue(): Int = when (this) {
    AgentMcpToolApproval.AUTO -> 0
    AgentMcpToolApproval.PROMPT -> 1
    AgentMcpToolApproval.WRITES -> 2
    AgentMcpToolApproval.APPROVE -> 3
}

private fun mcpToolExposureSurfaceFromCValue(value: Int): AgentMcpToolExposureSurface = when (value) {
    0 -> AgentMcpToolExposureSurface.CODE_MODE
    1 -> AgentMcpToolExposureSurface.DEFERRED
    2 -> AgentMcpToolExposureSurface.DIRECT
    else -> throw IllegalArgumentException("Unknown MCP tool exposure surface")
}

private fun AgentMcpToolExposureSurface.toMcpToolExposureSurfaceCValue(): Int = when (this) {
    AgentMcpToolExposureSurface.CODE_MODE -> 0
    AgentMcpToolExposureSurface.DEFERRED -> 1
    AgentMcpToolExposureSurface.DIRECT -> 2
}

private fun copyOptionalMcpToolExposureSurfaces(
    hasValues: Int,
    values: CPointer<IntVar>?,
    count: ULong,
): List<AgentMcpToolExposureSurface>? {
    requireMcpServerConfigurationFlag(hasValues)
    require(count <= Int.MAX_VALUE.toULong())
    if (hasValues == 0) {
        require(values == null && count == 0UL)
        return null
    }
    if (count == 0UL) {
        require(values == null)
        return emptyList()
    }
    val pointer = requireNotNull(values)
    return List(count.toInt()) { mcpToolExposureSurfaceFromCValue(pointer[it]) }
}

private fun copyOptionalMcpServerConfigurationStrings(
    hasValues: Int,
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): List<String>? {
    requireMcpServerConfigurationFlag(hasValues)
    require(count <= Int.MAX_VALUE.toULong())
    if (hasValues == 0) {
        require(values == null && count == 0UL)
        return null
    }
    if (count == 0UL) {
        require(values == null)
        return emptyList()
    }
    val pointer = requireNotNull(values)
    return List(count.toInt()) { pointer[it].readUtf8() }
}

private fun copyOptionalMcpServerConfigurationOauth(
    context: COpaquePointer,
    hasOauth: Int,
    oauth: COpaquePointer?,
    output: Array<AgentMcpOauthConfiguration?>,
): Int {
    requireMcpServerConfigurationFlag(hasOauth)
    if (hasOauth == 0) return if (oauth == null) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (oauth == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    return withPayload<CodexAgentCMcpOauthConfigurationSnapshot>(
        context,
        oauth,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        output[0] = it.value.copy()
        CODEX_AGENT_STATUS_OK
    }
}

private fun copyMcpServerConfigurationTools(
    context: COpaquePointer,
    keys: CPointer<codex_agent_string_view>?,
    configurations: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableMap<String, AgentMcpToolConfiguration>,
): Int {
    if (count > Int.MAX_VALUE.toULong()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (count == 0UL) {
        return if (keys == null && configurations == null) {
            CODEX_AGENT_STATUS_OK
        } else {
            CODEX_AGENT_STATUS_INVALID_ARGUMENT
        }
    }
    val keyPointer = keys ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val configurationPointer = configurations ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    repeat(count.toInt()) { index ->
        val key = keyPointer[index].readUtf8()
        if (output.containsKey(key)) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        val status = withPayload<CodexAgentCMcpToolConfigurationSnapshot>(
            context,
            configurationPointer[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output[key] = it.value.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private inline fun <reified T : CodexAgentCSnapshot> destroyMcpServerConfigurationSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT) else status
}

private inline fun <reified T : CodexAgentCSnapshot> mcpServerConfigurationInt(
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

private fun copyMcpServerConfigurationString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private fun copyOptionalMcpServerConfigurationString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> String?,
): Int = abiStatus {
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun optionalMcpServerConfigurationInt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
    outValue: CPointer<IntVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> Int?,
): Int = abiStatus {
    if (outHasValue == null || outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it)
        outHasValue.pointed.value = if (value == null) 0 else 1
        outValue.pointed.value = value ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

private fun optionalMcpServerConfigurationDouble(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
    outValue: CPointer<DoubleVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> Double?,
): Int = abiStatus {
    if (outHasValue == null || outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it)
        outHasValue.pointed.value = if (value == null) 0 else 1
        outValue.pointed.value = value ?: 0.0
        CODEX_AGENT_STATUS_OK
    }
}

private fun <T> mcpServerConfigurationOptionalListCount(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<ULongVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> List<T>?,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val values = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        output.pointed.value = values.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private fun copyMcpServerConfigurationOptionalStringListAt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCMcpServerConfigurationSnapshot) -> List<String>?,
): Int = abiStatus {
    withPayload<CodexAgentCMcpServerConfigurationSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val values = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        val value = values.mcpServerConfigurationItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun <T> List<T>.mcpServerConfigurationItemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())
