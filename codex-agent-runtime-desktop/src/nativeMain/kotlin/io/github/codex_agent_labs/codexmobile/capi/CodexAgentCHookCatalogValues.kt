@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentHook
import io.github.codex_agent_labs.codexmobile.agent.AgentHookCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler
import io.github.codex_agent_labs.codexmobile.agent.AgentHookTrustStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCHookHandlerSnapshot(
    val value: AgentHookHandler,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookSnapshot(
    val value: AgentHook,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookCatalogSnapshot(
    val value: AgentHookCatalog,
) : CodexAgentCSnapshot

@CName("codex_agent_hook_handler_from_agent")
public fun codexAgentHookHandlerFromAgent(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = createHookHandlerCarrier<CodexAgentCHookHandlerAgentSnapshot>(context, agent, outHandler) {
    AgentHookHandler.Agent
}

@CName("codex_agent_hook_handler_from_command")
public fun codexAgentHookHandlerFromCommand(
    context: COpaquePointer?,
    command: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = createHookHandlerCarrier<CodexAgentCHookHandlerCommandSnapshot>(context, command, outHandler) {
    it.value.copy()
}

@CName("codex_agent_hook_handler_from_mcp_tool")
public fun codexAgentHookHandlerFromMcpTool(
    context: COpaquePointer?,
    mcpTool: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = createHookHandlerCarrier<CodexAgentCHookHandlerMcpToolSnapshot>(context, mcpTool, outHandler) {
    it.value.copy()
}

@CName("codex_agent_hook_handler_from_prompt")
public fun codexAgentHookHandlerFromPrompt(
    context: COpaquePointer?,
    prompt: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = createHookHandlerCarrier<CodexAgentCHookHandlerPromptSnapshot>(context, prompt, outHandler) {
    AgentHookHandler.Prompt
}

@CName("codex_agent_hook_handler_destroy")
public fun codexAgentHookHandlerDestroy(
    context: COpaquePointer?,
    handler: CPointer<COpaquePointerVar>?,
): Int = destroyHookCatalogValue<CodexAgentCHookHandlerSnapshot>(context, handler)

@CName("codex_agent_hook_handler_kind")
public fun codexAgentHookHandlerKind(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = hookCatalogInt<CodexAgentCHookHandlerSnapshot>(context, handler, outKind) {
    when (it.value) {
        AgentHookHandler.Agent -> 0
        is AgentHookHandler.Command -> 1
        is AgentHookHandler.McpTool -> 2
        AgentHookHandler.Prompt -> 3
    }
}

@CName("codex_agent_hook_handler_agent")
public fun codexAgentHookHandlerAgent(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outAgent: CPointer<COpaquePointerVar>?,
): Int = projectHookHandler<AgentHookHandler.Agent>(context, handler, outAgent) {
    CodexAgentCHookHandlerAgentSnapshot(AgentHookHandler.Agent)
}

@CName("codex_agent_hook_handler_command")
public fun codexAgentHookHandlerCommand(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outCommand: CPointer<COpaquePointerVar>?,
): Int = projectHookHandler<AgentHookHandler.Command>(context, handler, outCommand) {
    CodexAgentCHookHandlerCommandSnapshot(it.copy())
}

@CName("codex_agent_hook_handler_mcp_tool")
public fun codexAgentHookHandlerMcpTool(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outMcpTool: CPointer<COpaquePointerVar>?,
): Int = projectHookHandler<AgentHookHandler.McpTool>(context, handler, outMcpTool) {
    CodexAgentCHookHandlerMcpToolSnapshot(it.copy())
}

@CName("codex_agent_hook_handler_prompt")
public fun codexAgentHookHandlerPrompt(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outPrompt: CPointer<COpaquePointerVar>?,
): Int = projectHookHandler<AgentHookHandler.Prompt>(context, handler, outPrompt) {
    CodexAgentCHookHandlerPromptSnapshot(AgentHookHandler.Prompt)
}

@CName("codex_agent_hook_create")
public fun codexAgentHookCreate(
    context: COpaquePointer?,
    key: CPointer<codex_agent_string_view>?,
    currentHash: CPointer<codex_agent_string_view>?,
    isEnabled: Int,
    eventName: CPointer<codex_agent_string_view>?,
    handler: COpaquePointer?,
    isManaged: Int,
    source: CPointer<codex_agent_string_view>?,
    sourcePath: CPointer<codex_agent_string_view>?,
    timeoutSeconds: Long,
    trustStatus: Int,
    hasMatcher: Int,
    matcher: CPointer<codex_agent_string_view>?,
    hasPluginId: Int,
    pluginId: CPointer<codex_agent_string_view>?,
    hasStatusMessage: Int,
    statusMessage: CPointer<codex_agent_string_view>?,
    hasOrigin: Int,
    origin: Int,
    canUninstall: Int,
    outHook: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHook)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireHookFlag(isEnabled)
    requireHookFlag(isManaged)
    requireHookFlag(canUninstall)
    requireHookFlag(hasOrigin)
    if (hasOrigin == 0) require(origin == 0)
    val copiedKey = key.readHookRequiredUtf8()
    val copiedCurrentHash = currentHash.readHookRequiredUtf8()
    val copiedEventName = eventName.readHookRequiredUtf8()
    val copiedSource = source.readHookRequiredUtf8()
    val copiedSourcePath = sourcePath.readHookRequiredUtf8()
    val copiedMatcher = matcher.readHookOptionalUtf8(hasMatcher)
    val copiedPluginId = pluginId.readHookOptionalUtf8(hasPluginId)
    val copiedStatusMessage = statusMessage.readHookOptionalUtf8(hasStatusMessage)
    val copiedTrustStatus = hookTrustStatusFromCValue(trustStatus)
    withPayload<CodexAgentCHookHandlerSnapshot>(
        contextPointer,
        handler,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { handlerSnapshot ->
        val canonical = AgentHook(
            key = copiedKey,
            currentHash = copiedCurrentHash,
            isEnabled = isEnabled == 1,
            eventName = copiedEventName,
            handler = handlerSnapshot.value.hookOwnedCopy(),
            isManaged = isManaged == 1,
            source = copiedSource,
            sourcePath = copiedSourcePath,
            timeoutSeconds = timeoutSeconds,
            trustStatus = copiedTrustStatus,
            matcher = copiedMatcher,
            pluginId = copiedPluginId,
            statusMessage = copiedStatusMessage,
            canUninstall = canUninstall == 1,
        )
        val value = if (hasOrigin == 1) {
            canonical.copy(origin = hookOriginFromCValue(origin))
        } else {
            canonical
        }
        installOutput(outHook, createSnapshot(contextPointer, CodexAgentCHookSnapshot(value)))
    }
}

@CName("codex_agent_hook_destroy")
public fun codexAgentHookDestroy(
    context: COpaquePointer?,
    hook: CPointer<COpaquePointerVar>?,
): Int = destroyHookCatalogValue<CodexAgentCHookSnapshot>(context, hook)

@CName("codex_agent_hook_key_copy")
public fun codexAgentHookKeyCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.key
}

@CName("codex_agent_hook_current_hash_copy")
public fun codexAgentHookCurrentHashCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.currentHash
}

@CName("codex_agent_hook_is_enabled")
public fun codexAgentHookIsEnabled(
    context: COpaquePointer?, hook: COpaquePointer?, outIsEnabled: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outIsEnabled) { it.value.isEnabled }

@CName("codex_agent_hook_event_name_copy")
public fun codexAgentHookEventNameCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.eventName
}

@CName("codex_agent_hook_handler")
public fun codexAgentHookHandler(
    context: COpaquePointer?,
    hook: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = nestedHookCatalogValue<CodexAgentCHookSnapshot>(context, hook, outHandler) {
    CodexAgentCHookHandlerSnapshot(it.value.handler.hookOwnedCopy())
}

@CName("codex_agent_hook_is_managed")
public fun codexAgentHookIsManaged(
    context: COpaquePointer?, hook: COpaquePointer?, outIsManaged: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outIsManaged) { it.value.isManaged }

@CName("codex_agent_hook_source_copy")
public fun codexAgentHookSourceCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.source
}

@CName("codex_agent_hook_source_path_copy")
public fun codexAgentHookSourcePathCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.sourcePath
}

@CName("codex_agent_hook_timeout_seconds")
public fun codexAgentHookTimeoutSeconds(
    context: COpaquePointer?, hook: COpaquePointer?, outTimeoutSeconds: CPointer<LongVar>?,
): Int = abiStatus {
    if (outTimeoutSeconds == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHookSnapshot>(context, hook, CodexAgentCHandleKind.SNAPSHOT) {
        outTimeoutSeconds.pointed.value = it.value.timeoutSeconds
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_hook_trust_status")
public fun codexAgentHookTrustStatus(
    context: COpaquePointer?, hook: COpaquePointer?, outTrustStatus: CPointer<IntVar>?,
): Int = hookCatalogInt<CodexAgentCHookSnapshot>(context, hook, outTrustStatus) {
    hookTrustStatusToCValue(it.value.trustStatus)
}

@CName("codex_agent_hook_has_matcher")
public fun codexAgentHookHasMatcher(
    context: COpaquePointer?, hook: COpaquePointer?, outHasMatcher: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outHasMatcher) { it.value.matcher != null }

@CName("codex_agent_hook_matcher_copy")
public fun codexAgentHookMatcherCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.matcher
}

@CName("codex_agent_hook_has_plugin_id")
public fun codexAgentHookHasPluginId(
    context: COpaquePointer?, hook: COpaquePointer?, outHasPluginId: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outHasPluginId) { it.value.pluginId != null }

@CName("codex_agent_hook_plugin_id_copy")
public fun codexAgentHookPluginIdCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.pluginId
}

@CName("codex_agent_hook_has_status_message")
public fun codexAgentHookHasStatusMessage(
    context: COpaquePointer?, hook: COpaquePointer?, outHasStatusMessage: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outHasStatusMessage) {
    it.value.statusMessage != null
}

@CName("codex_agent_hook_status_message_copy")
public fun codexAgentHookStatusMessageCopy(
    context: COpaquePointer?, hook: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyOptionalHookCatalogString<CodexAgentCHookSnapshot>(context, hook, buffer, capacity, outRequired) {
    it.value.statusMessage
}

@CName("codex_agent_hook_origin")
public fun codexAgentHookOrigin(
    context: COpaquePointer?, hook: COpaquePointer?, outOrigin: CPointer<IntVar>?,
): Int = hookCatalogInt<CodexAgentCHookSnapshot>(context, hook, outOrigin) {
    hookOriginToCValue(it.value.origin)
}

@CName("codex_agent_hook_can_uninstall")
public fun codexAgentHookCanUninstall(
    context: COpaquePointer?, hook: COpaquePointer?, outCanUninstall: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outCanUninstall) {
    it.value.canUninstall
}

@CName("codex_agent_hook_can_trust")
public fun codexAgentHookCanTrust(
    context: COpaquePointer?, hook: COpaquePointer?, outCanTrust: CPointer<IntVar>?,
): Int = hookCatalogBoolean<CodexAgentCHookSnapshot>(context, hook, outCanTrust) { it.value.canTrust }

@CName("codex_agent_hook_catalog_create")
public fun codexAgentHookCatalogCreate(
    context: COpaquePointer?,
    hooks: CPointer<COpaquePointerVar>?,
    hookCount: ULong,
    warnings: CPointer<codex_agent_string_view>?,
    warningCount: ULong,
    errors: CPointer<codex_agent_string_view>?,
    errorCount: ULong,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outCatalog)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedHooks = readHookList(contextPointer, hooks, hookCount)
    if (copiedHooks.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedHooks.status
    val value = AgentHookCatalog(
        hooks = checkNotNull(copiedHooks.value),
        warnings = readHookStrings(warnings, warningCount),
        errors = readHookStrings(errors, errorCount),
    )
    installOutput(outCatalog, createSnapshot(contextPointer, CodexAgentCHookCatalogSnapshot(value)))
}

@CName("codex_agent_hook_catalog_destroy")
public fun codexAgentHookCatalogDestroy(
    context: COpaquePointer?,
    catalog: CPointer<COpaquePointerVar>?,
): Int = destroyHookCatalogValue<CodexAgentCHookCatalogSnapshot>(context, catalog)

@CName("codex_agent_hook_catalog_hooks_count")
public fun codexAgentHookCatalogHooksCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = hookCatalogCount<CodexAgentCHookCatalogSnapshot>(context, catalog, outCount) { it.value.hooks.size }

@CName("codex_agent_hook_catalog_hooks_at")
public fun codexAgentHookCatalogHooksAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    outHook: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHook)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHookCatalogSnapshot>(contextPointer, catalog, CodexAgentCHandleKind.SNAPSHOT) {
        if (index >= it.value.hooks.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outHook,
            createSnapshot(contextPointer, CodexAgentCHookSnapshot(it.value.hooks[index.toInt()].hookOwnedCopy())),
        )
    }
}

@CName("codex_agent_hook_catalog_warnings_count")
public fun codexAgentHookCatalogWarningsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = hookCatalogCount<CodexAgentCHookCatalogSnapshot>(context, catalog, outCount) {
    it.value.warnings.size
}

@CName("codex_agent_hook_catalog_warnings_copy_at")
public fun codexAgentHookCatalogWarningsCopyAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogStringAt(context, catalog, index, buffer, capacity, outRequired) {
    it.value.warnings
}

@CName("codex_agent_hook_catalog_errors_count")
public fun codexAgentHookCatalogErrorsCount(
    context: COpaquePointer?, catalog: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = hookCatalogCount<CodexAgentCHookCatalogSnapshot>(context, catalog, outCount) { it.value.errors.size }

@CName("codex_agent_hook_catalog_errors_copy_at")
public fun codexAgentHookCatalogErrorsCopyAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyHookCatalogStringAt(context, catalog, index, buffer, capacity, outRequired) { it.value.errors }

private data class HookListResult(
    val status: Int,
    val value: List<AgentHook>? = null,
)

private inline fun <reified T : CodexAgentCSnapshot> createHookHandlerCarrier(
    context: COpaquePointer?,
    source: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    crossinline copy: (T) -> AgentHookHandler,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, source, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(output, createSnapshot(contextPointer, CodexAgentCHookHandlerSnapshot(copy(it))))
    }
}

private inline fun <reified T : AgentHookHandler> projectHookHandler(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    crossinline snapshot: (T) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHookHandlerSnapshot>(
        contextPointer,
        handler,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = it.value as? T ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(output, createSnapshot(contextPointer, snapshot(value)))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> destroyHookCatalogValue(
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

private inline fun <reified T : CodexAgentCSnapshot> copyHookCatalogString(
    context: COpaquePointer?, handle: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?, crossinline select: (T) -> String,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalHookCatalogString(
    context: COpaquePointer?, handle: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?, crossinline select: (T) -> String?,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> hookCatalogBoolean(
    context: COpaquePointer?, handle: COpaquePointer?, output: CPointer<IntVar>?,
    crossinline select: (T) -> Boolean,
): Int = hookCatalogInt<T>(context, handle, output) { if (select(it)) 1 else 0 }

private inline fun <reified T : CodexAgentCSnapshot> hookCatalogInt(
    context: COpaquePointer?, handle: COpaquePointer?, output: CPointer<IntVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it)
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> hookCatalogCount(
    context: COpaquePointer?, handle: COpaquePointer?, output: CPointer<ULongVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it).toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> nestedHookCatalogValue(
    context: COpaquePointer?, handle: COpaquePointer?, output: CPointer<COpaquePointerVar>?,
    crossinline snapshot: (T) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, handle, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(output, createSnapshot(contextPointer, snapshot(it)))
    }
}

private fun copyHookCatalogStringAt(
    context: COpaquePointer?, catalog: COpaquePointer?, index: ULong,
    buffer: CPointer<UByteVar>?, capacity: ULong, outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCHookCatalogSnapshot) -> List<String>,
): Int = abiStatus {
    withPayload<CodexAgentCHookCatalogSnapshot>(context, catalog, CodexAgentCHandleKind.SNAPSHOT) {
        val values = select(it)
        if (index >= values.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(values[index.toInt()], buffer, capacity, outRequired)
    }
}

private fun readHookList(
    context: COpaquePointer,
    hooks: CPointer<COpaquePointerVar>?,
    count: ULong,
): HookListResult {
    if (count > Int.MAX_VALUE.toULong() || count > 0uL && hooks == null) {
        return HookListResult(CODEX_AGENT_STATUS_INVALID_ARGUMENT)
    }
    val output = ArrayList<AgentHook>(count.toInt())
    repeat(count.toInt()) { index ->
        val status = withPayload<CodexAgentCHookSnapshot>(
            context,
            checkNotNull(hooks)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.hookOwnedCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return HookListResult(status)
    }
    return HookListResult(CODEX_AGENT_STATUS_OK, output)
}

private fun readHookStrings(
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): List<String> {
    require(count <= Int.MAX_VALUE.toULong())
    require(count == 0uL || values != null)
    return List(count.toInt()) { index -> checkNotNull(values)[index].readUtf8() }
}

private fun CPointer<codex_agent_string_view>?.readHookRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readHookOptionalUtf8(hasValue: Int): String? {
    requireHookFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0uL)
        return null
    }
    return view.readUtf8()
}

private fun requireHookFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun hookTrustStatusFromCValue(value: Int): AgentHookTrustStatus = when (value) {
    0 -> AgentHookTrustStatus.MANAGED
    1 -> AgentHookTrustStatus.UNTRUSTED
    2 -> AgentHookTrustStatus.TRUSTED
    3 -> AgentHookTrustStatus.MODIFIED
    else -> throw IllegalArgumentException("Unknown hook trust status")
}

private fun hookTrustStatusToCValue(value: AgentHookTrustStatus): Int = when (value) {
    AgentHookTrustStatus.MANAGED -> 0
    AgentHookTrustStatus.UNTRUSTED -> 1
    AgentHookTrustStatus.TRUSTED -> 2
    AgentHookTrustStatus.MODIFIED -> 3
}

private fun hookOriginFromCValue(value: Int): AgentResourceOrigin = when (value) {
    0 -> AgentResourceOrigin.USER
    1 -> AgentResourceOrigin.WORKSPACE
    2 -> AgentResourceOrigin.PLUGIN
    3 -> AgentResourceOrigin.MANAGED
    4 -> AgentResourceOrigin.UNKNOWN
    else -> throw IllegalArgumentException("Unknown resource origin")
}

private fun hookOriginToCValue(value: AgentResourceOrigin): Int = when (value) {
    AgentResourceOrigin.USER -> 0
    AgentResourceOrigin.WORKSPACE -> 1
    AgentResourceOrigin.PLUGIN -> 2
    AgentResourceOrigin.MANAGED -> 3
    AgentResourceOrigin.UNKNOWN -> 4
}

private fun AgentHookHandler.hookOwnedCopy(): AgentHookHandler = when (this) {
    AgentHookHandler.Agent -> AgentHookHandler.Agent
    is AgentHookHandler.Command -> copy()
    is AgentHookHandler.McpTool -> copy()
    AgentHookHandler.Prompt -> AgentHookHandler.Prompt
}

private fun AgentHook.hookOwnedCopy(): AgentHook = copy(handler = handler.hookOwnedCopy())
