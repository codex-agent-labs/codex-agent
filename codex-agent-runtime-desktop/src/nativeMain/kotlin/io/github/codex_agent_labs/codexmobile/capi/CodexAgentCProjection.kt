@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSettings
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexConversations
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.agent.runtime.DesktopCodexPlatform
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_conversation_open_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_host_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.concurrent.atomics.AtomicInt
import kotlin.concurrent.atomics.AtomicReference
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.readBytes
import kotlinx.cinterop.set
import kotlinx.cinterop.sizeOf
import kotlinx.cinterop.value
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import okio.Path.Companion.toPath

internal data class CodexAgentCHostOptions(
    val bundleDirectory: String,
    val dataDirectory: String,
    val clientInfo: CodexClientInfo,
)

internal data class CodexAgentCOpenOptions(
    val conversationId: ConversationId?,
    val settings: AgentConversationSettings,
)

internal class CodexAgentCHost(
    val core: CodexHost,
    val runtime: CodexAgentCContextRuntime,
) {
    private val cacheLock = AtomicInt(0)
    private var cachedCoreAgent: CodexAgent? = null
    private var cachedAgentHandle: COpaquePointer? = null
    val closeFailure = AtomicReference<CodexFailure?>(null)

    fun projectAgent(
        context: COpaquePointer,
        host: COpaquePointer,
        agent: CodexAgent,
    ): CodexAgentCRegistryResult<COpaquePointer> = cacheLock.withSpinLock {
        val existing = cachedAgentHandle
        if (cachedCoreAgent === agent && existing != null) {
            return@withSpinLock handleRegistry.retain(context, existing, CodexAgentCHandleKind.AGENT)
        }
        val wrapper = CodexAgentCAgent(agent, this)
        val created = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            wrapper,
            host,
            CodexAgentCHandleKind.HOST,
        )
        val token = created.value ?: return@withSpinLock created
        cachedCoreAgent = agent
        cachedAgentHandle = token
        handleRegistry.retain(context, token, CodexAgentCHandleKind.AGENT)
    }

    fun invalidateChildren(context: COpaquePointer, host: COpaquePointer): Int =
        cacheLock.withSpinLock {
            val status = handleRegistry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST)
            if (status == CODEX_AGENT_STATUS_OK) {
                cachedAgentHandle?.let {
                    handleRegistry.release(context, it, CodexAgentCHandleKind.AGENT)
                }
                cachedCoreAgent = null
                cachedAgentHandle = null
            }
            status
        }

    fun clearInvalidatedChildren(context: COpaquePointer) {
        cacheLock.withSpinLock {
            cachedAgentHandle?.let {
                handleRegistry.release(context, it, CodexAgentCHandleKind.AGENT)
            }
            cachedCoreAgent = null
            cachedAgentHandle = null
        }
    }
}

internal class CodexAgentCAgent(
    val core: CodexAgent,
    private val host: CodexAgentCHost,
) {
    private val cacheLock = AtomicInt(0)
    private var cachedConversationsHandle: COpaquePointer? = null

    fun projectConversations(
        context: COpaquePointer,
        agent: COpaquePointer,
    ): CodexAgentCRegistryResult<COpaquePointer> = cacheLock.withSpinLock {
        val existing = cachedConversationsHandle
        if (existing != null) {
            return@withSpinLock handleRegistry.retain(
                context,
                existing,
                CodexAgentCHandleKind.CONVERSATIONS,
            )
        }
        val created = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATIONS,
            CodexAgentCConversations(core.conversations, host, core),
            agent,
            CodexAgentCHandleKind.AGENT,
        )
        val token = created.value ?: return@withSpinLock created
        cachedConversationsHandle = token
        handleRegistry.retain(context, token, CodexAgentCHandleKind.CONVERSATIONS)
    }
}

internal class CodexAgentCConversations(
    val core: CodexConversations,
    val host: CodexAgentCHost,
    val agent: CodexAgent,
) {
    private val cacheLock = AtomicInt(0)
    private var cachedCoreConversation: CodexConversation? = null
    private var cachedConversationHandle: COpaquePointer? = null
    private var cachedActiveState: StateFlow<CodexAgentCActiveState>? = null

    fun activeState(): StateFlow<CodexAgentCActiveState> = cacheLock.withSpinLock {
        cachedActiveState ?: combine(host.core.lifecycleState, core.active) { state, conversation ->
            CodexAgentCActiveState(
                conversation = conversation,
                terminal = (state as? CodexHostState.Ready)?.agent !== agent,
            )
        }.stateIn(
            host.runtime.scope,
            SharingStarted.Eagerly,
            CodexAgentCActiveState(
                conversation = core.active.value,
                terminal = (host.core.lifecycleState.value as? CodexHostState.Ready)?.agent !== agent,
            ),
        ).also { cachedActiveState = it }
    }

    fun projectConversation(
        context: COpaquePointer,
        conversations: COpaquePointer,
        conversation: CodexConversation,
        allowLeasedTransitionParent: Boolean = false,
    ): CodexAgentCRegistryResult<COpaquePointer> = cacheLock.withSpinLock {
        val existing = cachedConversationHandle
        if (cachedCoreConversation === conversation && existing != null) {
            return@withSpinLock handleRegistry.retain(
                context,
                existing,
                CodexAgentCHandleKind.CONVERSATION,
            )
        }
        val created = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATION,
            CodexAgentCConversation(conversation, host.runtime),
            conversations,
            CodexAgentCHandleKind.CONVERSATIONS,
            allowLeasedTransitionParent,
        )
        val token = created.value ?: return@withSpinLock created
        cachedCoreConversation = conversation
        cachedConversationHandle = token
        handleRegistry.retain(context, token, CodexAgentCHandleKind.CONVERSATION)
    }

    fun clearInvalidatedChildren(context: COpaquePointer) {
        cacheLock.withSpinLock {
            cachedConversationHandle?.let {
                handleRegistry.release(context, it, CodexAgentCHandleKind.CONVERSATION)
            }
            cachedCoreConversation = null
            cachedConversationHandle = null
        }
    }
}

internal class CodexAgentCConversation(
    val core: CodexConversation,
    val runtime: CodexAgentCContextRuntime,
) {
    val closeFailure = AtomicReference<CodexFailure?>(null)
}

internal data class CodexAgentCActiveState(
    val conversation: CodexConversation?,
    val terminal: Boolean,
)

internal sealed interface CodexAgentCSnapshot

internal data class CodexAgentCHostStateSnapshot(
    val owner: CodexHost,
    val state: CodexHostState,
) : CodexAgentCSnapshot

internal data class CodexAgentCActiveConversationSnapshot(
    val owner: CodexConversations,
    val conversation: CodexConversation?,
) : CodexAgentCSnapshot

internal data class CodexAgentCConversationStateSnapshot(
    val state: AgentConversationState,
) : CodexAgentCSnapshot

internal fun parseHostOptions(
    pointer: CPointer<codex_agent_host_options>?,
): CodexAgentCHostOptions {
    val options = requireNotNull(pointer).pointed
    require(options.struct_size.toULong() >= sizeOf<codex_agent_host_options>().toULong())
    val clientInfo = options.client_info
    require(clientInfo.struct_size.toULong() >=
        sizeOf<io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_client_info>().toULong())
    return CodexAgentCHostOptions(
        bundleDirectory = options.bundle_directory.readUtf8(),
        dataDirectory = options.data_directory.readUtf8(),
        clientInfo = CodexClientInfo(
            clientInfo.name.readUtf8(),
            clientInfo.title.readUtf8(),
            clientInfo.version.readUtf8(),
        ),
    )
}

internal fun CodexAgentCHostOptions.createHost(runtime: CodexAgentCContextRuntime): CodexAgentCHost =
    CodexAgentCHost(
        CodexHost(
            DesktopCodexPlatform(
                bundleDirectory.toPath(normalize = true),
                dataDirectory.toPath(normalize = true),
            ),
            clientInfo,
        ),
        runtime,
    )

internal fun parseWorkspaceSelection(
    pointer: CPointer<codex_agent_path_workspace_selection>?,
): CodexPathWorkspaceSelection {
    val selection = requireNotNull(pointer).pointed
    require(selection.struct_size.toULong() >=
        sizeOf<codex_agent_path_workspace_selection>().toULong())
    return CodexPathWorkspaceSelection(selection.path.readUtf8())
}

internal fun parseOpenOptions(
    pointer: CPointer<codex_agent_conversation_open_options>?,
): CodexAgentCOpenOptions {
    if (pointer == null) return CodexAgentCOpenOptions(null, AgentConversationSettings())
    val options = pointer.pointed
    require(options.struct_size.toULong() >=
        sizeOf<codex_agent_conversation_open_options>().toULong())
    require(options.has_conversation_id == 0 || options.has_conversation_id == 1)
    require(options.has_approval_preset == 0 || options.has_approval_preset == 1)
    require(options.has_service_tier == 0 || options.has_service_tier == 1)
    val preset = if (options.has_approval_preset == 0) {
        require(options.approval_preset == 0)
        AgentConversationSettings().approvalPreset
    } else {
        AgentApprovalPreset.entries.getOrNull(options.approval_preset)
            ?: throw IllegalArgumentException("Unknown approval preset")
    }
    return CodexAgentCOpenOptions(
        conversationId = if (options.has_conversation_id == 0) {
            require(options.conversation_id.data == null && options.conversation_id.size == 0uL)
            null
        } else {
            ConversationId(options.conversation_id.readUtf8())
        },
        settings = AgentConversationSettings(
            approvalPreset = preset,
            serviceTier = if (options.has_service_tier == 0) {
                require(options.service_tier.data == null && options.service_tier.size == 0uL)
                null
            } else {
                options.service_tier.readUtf8()
            },
        ),
    )
}

internal fun codex_agent_string_view.readUtf8(): String {
    require(size <= Int.MAX_VALUE.toULong())
    if (size == 0uL) return ""
    val source = requireNotNull(data)
    return try {
        source.readBytes(size.toInt()).decodeToString(throwOnInvalidSequence = true)
    } catch (error: OutOfMemoryError) {
        throw error
    } catch (error: Throwable) {
        throw IllegalArgumentException("Invalid UTF-8", error)
    }
}

internal fun copyUtf8(
    value: String,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int {
    if (outRequired == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val bytes = value.encodeToByteArray()
    outRequired.pointed.value = bytes.size.toULong()
    if (capacity < bytes.size.toULong()) return CODEX_AGENT_STATUS_BUFFER_TOO_SMALL
    if (bytes.isNotEmpty() && buffer == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    bytes.forEachIndexed { index, byte -> checkNotNull(buffer)[index] = byte.toUByte() }
    return CODEX_AGENT_STATUS_OK
}

internal fun createSnapshot(
    context: COpaquePointer,
    snapshot: CodexAgentCSnapshot,
): CodexAgentCRegistryResult<COpaquePointer> =
    handleRegistry.createEntry(context, CodexAgentCHandleKind.SNAPSHOT, snapshot)

internal fun createFailure(
    context: COpaquePointer,
    failure: CodexFailure,
): CodexAgentCRegistryResult<COpaquePointer> =
    handleRegistry.createEntry(context, CodexAgentCHandleKind.FAILURE, failure)

internal fun CodexHostState.kind(): Int = when (this) {
    CodexHostState.New -> 0
    CodexHostState.Restoring -> 1
    is CodexHostState.WorkspaceRequired -> 2
    is CodexHostState.Preparing -> 3
    is CodexHostState.Ready -> 4
    is CodexHostState.Failed -> 5
    CodexHostState.Closed -> 6
}

internal fun CodexHostState.workspaceOrNull(): CodexWorkspace? = when (this) {
    is CodexHostState.Preparing -> workspace
    is CodexHostState.Failed -> workspace
    else -> null
}

internal inline fun <T> AtomicInt.withSpinLock(block: () -> T): T {
    // ponytail: tiny per-owner cache lock; replace only if profiling shows contention.
    while (!compareAndSet(0, 1)) Unit
    return try {
        block()
    } finally {
        store(0)
    }
}
