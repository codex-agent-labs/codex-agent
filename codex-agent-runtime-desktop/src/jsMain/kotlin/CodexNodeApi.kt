@file:OptIn(ExperimentalJsExport::class)

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationState as CoreAuthenticationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSettings
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState as CoreConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidation as CoreElicitationValidation
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationIssue as CoreElicitationValidationIssue
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationReason as CoreElicitationValidationReason
import io.github.codex_agent_labs.codexmobile.agent.AgentFormOption as CoreFormOption
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage as CoreMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanProgress as CorePlanProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStep as CorePlanStep
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStepStatus as CorePlanStepStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress as CoreTurnProgress
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent as CoreAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthentication as CoreAuthentication
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod as CoreAuthenticationMethod
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation as CoreConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure as CoreFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState as CoreHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexOperationException
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace as CoreWorkspace
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.agent.runtime.NodeCodexPlatform
import kotlin.js.ExperimentalJsExport
import kotlin.js.JsExport
import kotlin.js.Promise
import kotlin.js.jsTypeOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import kotlinx.coroutines.promise
import okio.Path.Companion.toPath

/** The native Node `AbortSignal` accepted by cancellable SDK operations. */
public external interface AbortSignal {
    public val aborted: Boolean
    public fun addEventListener(type: String, listener: () -> Unit)
    public fun removeEventListener(type: String, listener: () -> Unit)
}

/** Immutable form option value. */
@JsExport
public class AgentFormOption public constructor(
    value: String,
    title: String = value,
    description: String? = null,
) {
    public val value: String
    public val title: String
    public val description: String?

    init {
        val core = CoreFormOption(
            value.requireJavaScriptString("value"),
            title.requireJavaScriptString("title"),
            description.requireJavaScriptNullableString("description"),
        )
        this.value = core.value
        this.title = core.title
        this.description = core.description
        freezeSnapshot(this)
    }
}

/** Immutable elicitation validation issue. */
@JsExport
public class AgentElicitationValidationIssue public constructor(
    fieldName: String,
    reason: String,
) {
    public val fieldName: String
    public val reason: String

    init {
        val core = CoreElicitationValidationIssue(
            fieldName.requireJavaScriptString("fieldName"),
            reason.requireJavaScriptString("reason").toCoreElicitationValidationReason(),
        )
        this.fieldName = core.fieldName
        this.reason = core.reason.name.lowercase()
        freezeSnapshot(this)
    }
}

/** Immutable elicitation validation result. */
@JsExport
public class AgentElicitationValidation public constructor(
    issues: Array<AgentElicitationValidationIssue>,
) {
    public val issues: Array<AgentElicitationValidationIssue>
    public val isValid: Boolean

    init {
        requireJavaScriptArray(issues, "issues")
        this.issues = issues.map {
            AgentElicitationValidationIssue(it.fieldName, it.reason)
        }.toTypedArray()
        this.isValid = CoreElicitationValidation(
            this.issues.map {
                CoreElicitationValidationIssue(it.fieldName, it.reason.toCoreElicitationValidationReason())
            },
        ).isValid
        freezeSnapshot(this.issues)
        freezeSnapshot(this)
    }
}

/** Immutable plan step value. */
@JsExport
public class AgentPlanStep public constructor(
    text: String,
    status: String,
) {
    public val text: String
    public val status: String

    init {
        val core = CorePlanStep(
            text.requireJavaScriptString("text"),
            status.requireJavaScriptString("status").toCorePlanStepStatus(),
        )
        this.text = core.text
        this.status = core.status.name.lowercase()
        freezeSnapshot(this)
    }
}

/** Immutable plan progress value. */
@JsExport
public class AgentPlanProgress public constructor(
    explanation: String? = null,
    steps: Array<AgentPlanStep> = emptyArray(),
) {
    public val explanation: String?
    public val steps: Array<AgentPlanStep>

    init {
        requireJavaScriptArray(steps, "steps")
        val stepSnapshots = steps.map { AgentPlanStep(it.text, it.status) }.toTypedArray()
        val core = CorePlanProgress(
            explanation.requireJavaScriptNullableString("explanation"),
            stepSnapshots.map { CorePlanStep(it.text, it.status.toCorePlanStepStatus()) },
        )
        this.explanation = core.explanation
        this.steps = stepSnapshots
        freezeSnapshot(this.steps)
        freezeSnapshot(this)
    }
}

/** Structured failure data exposed by observable state snapshots. */
@JsExport
public class CodexFailure internal constructor(
    public val code: String,
    public val message: String,
    public val recoverable: Boolean,
) {
    init {
        freezeSnapshot(this)
    }
}

/** Immutable authentication lifecycle snapshot. */
@JsExport
public class CodexAuthenticationState internal constructor(
    public val status: String,
    public val pendingSignInUrl: String?,
    public val deviceVerificationUrl: String?,
    public val deviceUserCode: String?,
    public val failure: CodexFailure?,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex authentication states are created by the SDK" }
        freezeSnapshot(this)
    }
}

/** Rejection type for canonical Codex operation failures. */
@JsExport
public class CodexError internal constructor(
    message: String,
    public val code: String,
    public val recoverable: Boolean,
    cause: Throwable?,
) : Exception(message, cause) {
    init {
        asDynamic().name = "CodexError"
        if (cause != null) asDynamic().cause = cause
    }
}

/** Immutable workspace snapshot. */
@JsExport
public class CodexWorkspace internal constructor(
    public val path: String,
    public val displayName: String,
) {
    init {
        freezeSnapshot(this)
    }
}

/** Immutable Host lifecycle snapshot. */
@JsExport
public class CodexHostState internal constructor(
    public val status: String,
    public val workspace: CodexWorkspace?,
    public val agent: CodexAgent?,
    public val selectionReason: String?,
    public val selectionMessage: String?,
    public val failure: CodexFailure?,
) {
    init {
        freezeSnapshot(this)
    }
}

/** Immutable conversation message snapshot. */
@JsExport
public class CodexMessage internal constructor(
    public val id: String,
    public val clientMessageId: String?,
    public val role: String,
    public val text: String,
    public val reasoning: String?,
    public val plan: String?,
    public val shellCommand: String?,
    public val exitCode: Int?,
) {
    init {
        freezeSnapshot(this)
    }
}

/** Immutable live turn-progress snapshot. */
@JsExport
public class CodexTurnProgress internal constructor(
    public val text: String,
    public val commentary: String,
    public val reasoning: String,
    public val plan: String,
    public val shellOutput: String,
    public val shellExitCode: Int?,
    public val workActivity: String?,
    public val truncated: Boolean,
) {
    init {
        freezeSnapshot(this)
    }
}

/** Immutable Conversation lifecycle and output snapshot. */
@JsExport
public class CodexConversationState internal constructor(
    public val status: String,
    public val conversationId: String?,
    public val title: String?,
    public val messages: Array<CodexMessage>,
    public val turnProgress: CodexTurnProgress?,
    public val model: String?,
    public val effort: String?,
    public val serviceTier: String?,
    public val failure: CodexFailure?,
    public val isTurnActive: Boolean,
    public val canStartTurn: Boolean,
    public val canReload: Boolean,
    public val canCancelTurn: Boolean,
    public val canRunShellCommand: Boolean,
) {
    init {
        freezeSnapshot(messages)
        freezeSnapshot(this)
    }
}

/** Idempotent handle for one typed state subscription. */
@JsExport
public class CodexObservation internal constructor(
    private val job: Job,
    token: Any,
) {
    private var active: Boolean = true

    init {
        require(token === jsApiToken) { "Codex observations are created by the SDK" }
        hideBackingFields(this)
    }

    public val isClosed: Boolean
        get() = !active

    public fun close(): Unit {
        if (active) {
            active = false
            job.cancel()
        }
    }

    public fun dispose(): Unit {
        close()
    }

    internal fun deliver(callback: () -> Unit): Boolean {
        if (!active) return false
        try {
            callback()
        } catch (error: Throwable) {
            close()
            reportUnhandledCallbackError(error)
            return false
        }
        return active
    }
}

/** Node-only projection of the canonical Host -> Agent -> Conversation API. */
@JsExport
public class CodexHost internal constructor(
    private val core: CoreHost,
    token: Any,
) {
    private val ownerJob: Job = SupervisorJob()
    private val scope: CoroutineScope = CoroutineScope(ownerJob + Dispatchers.Default)
    private var cachedCoreAgent: CoreAgent? = null
    private var cachedAgent: CodexAgent? = null

    init {
        require(token === jsApiToken) { "Use createCodexHost()" }
        hideBackingFields(this)
    }

    public val state: CodexHostState
        get() = projectHostState(core.lifecycleState.value)

    public val agent: CodexAgent?
        get() = (core.lifecycleState.value as? CoreHostState.Ready)?.agent?.let(::wrapAgent)

    public fun start(signal: AbortSignal? = null): Promise<Unit> =
        scope.codexUnitPromise(signal) { core.start() }

    public fun selectWorkspace(path: String, signal: AbortSignal? = null): Promise<Unit> =
        scope.codexUnitPromise(signal) { core.selectWorkspace(CodexPathWorkspaceSelection(path)) }

    public fun observeState(listener: (CodexHostState) -> Unit): CodexObservation = observeStateFlow(
        scope = scope,
        state = core.lifecycleState,
        project = ::projectHostState,
        listener = listener,
        isTerminal = { it is CoreHostState.Closed },
    )

    public fun close(): Promise<Unit> = cleanupPromise { core.close() }

    public fun dispose(): Promise<Unit> = close()

    internal fun operationScope(): CoroutineScope = scope

    internal fun lifecycleState(): StateFlow<CoreHostState> = core.lifecycleState

    internal fun owns(agent: CoreAgent): Boolean =
        (core.lifecycleState.value as? CoreHostState.Ready)?.agent === agent

    internal fun wrapAgent(agent: CoreAgent): CodexAgent {
        if (cachedCoreAgent !== agent) {
            cachedCoreAgent = agent
            cachedAgent = CodexAgent(this, agent, jsApiToken)
        }
        return checkNotNull(cachedAgent)
    }

    private fun projectHostState(state: CoreHostState): CodexHostState = when (state) {
        CoreHostState.New -> CodexHostState("new", null, null, null, null, null)
        CoreHostState.Restoring -> CodexHostState("restoring", null, null, null, null, null)
        is CoreHostState.WorkspaceRequired -> CodexHostState(
            status = "workspace_required",
            workspace = null,
            agent = null,
            selectionReason = state.requirement.reason.name.lowercase(),
            selectionMessage = state.requirement.message,
            failure = null,
        )
        is CoreHostState.Preparing -> CodexHostState(
            "preparing",
            state.workspace.project(),
            null,
            null,
            null,
            null,
        )
        is CoreHostState.Ready -> CodexHostState(
            "ready",
            state.agent.workspace.project(),
            wrapAgent(state.agent),
            null,
            null,
            null,
        )
        is CoreHostState.Failed -> CodexHostState(
            "failed",
            state.workspace?.project(),
            null,
            null,
            null,
            state.failure.project(),
        )
        CoreHostState.Closed -> CodexHostState("closed", null, null, null, null, null)
    }
}

/** Creates a Node Host backed by the verified Desktop classifier lifecycle. */
@JsExport
public fun createCodexHost(
    bundleDirectory: String,
    dataDirectory: String,
    clientName: String,
    clientTitle: String,
    clientVersion: String,
): CodexHost = CodexHost(
    CoreHost(
        NodeCodexPlatform(bundleDirectory.toPath(), dataDirectory.toPath()),
        CodexClientInfo(clientName, clientTitle, clientVersion),
    ),
    jsApiToken,
)

internal fun wrapCodexHost(core: CoreHost): CodexHost = CodexHost(core, jsApiToken)

/** Host-owned Agent projection. */
@JsExport
public class CodexAgent internal constructor(
    private val host: CodexHost,
    private val core: CoreAgent,
    token: Any,
) {
    private val authenticationProjection: CodexAuthentication =
        CodexAuthentication(host, core, core.authentication, jsApiToken)
    private var cachedCoreConversation: CoreConversation? = null
    private var cachedConversation: CodexConversation? = null

    init {
        require(token === jsApiToken) { "Codex agents are created by a Host" }
        hideBackingFields(this)
    }

    public val workspace: CodexWorkspace
        get() = core.workspace.project()

    public val authentication: CodexAuthentication
        get() = authenticationProjection

    public val activeConversation: CodexConversation?
        get() = if (host.owns(core)) core.conversations.active.value?.let(::wrapConversation) else null

    public fun openConversation(
        conversationId: String? = null,
        approvalPreset: String? = null,
        serviceTier: String? = null,
        signal: AbortSignal? = null,
    ): Promise<CodexConversation> = host.operationScope().codexPromise(signal) {
        core.conversations.open(
            conversationId = conversationId?.let(::ConversationId),
            settings = AgentConversationSettings(
                approvalPreset = approvalPreset.toApprovalPreset(),
                serviceTier = serviceTier,
            ),
        ).let(::wrapConversation)
    }

    public fun observeActiveConversation(listener: (CodexConversation?) -> Unit): CodexObservation {
        val state = combine(host.lifecycleState(), core.conversations.active) { hostState, active ->
            val ownsAgent = (hostState as? CoreHostState.Ready)?.agent === core
            ActiveConversationState(
                conversation = if (ownsAgent) active?.let(::wrapConversation) else null,
                terminal = !ownsAgent,
            )
        }
        return observeFlow(
            scope = host.operationScope(),
            state = state,
            project = { it.conversation },
            listener = listener,
            isTerminal = { it.terminal },
        )
    }

    internal fun wrapConversation(conversation: CoreConversation): CodexConversation {
        if (cachedCoreConversation !== conversation) {
            cachedCoreConversation = conversation
            cachedConversation = CodexConversation(host, conversation, jsApiToken)
        }
        return checkNotNull(cachedConversation)
    }
}

/** Agent-owned authentication projection. */
@JsExport
public class CodexAuthentication internal constructor(
    private val host: CodexHost,
    private val agent: CoreAgent,
    private val core: CoreAuthentication,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex authentication is created by an Agent" }
        hideBackingFields(this)
    }

    public val state: CodexAuthenticationState
        get() = core.state.value.project()

    public val isAuthenticated: Boolean
        get() = core.isAuthenticated.value

    public val isAuthenticating: Boolean
        get() = core.isAuthenticating.value

    public fun authenticate(
        method: String? = null,
        apiKey: String? = null,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        core.authenticate(method.toAuthenticationMethod(apiKey))
    }

    public fun cancel(signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.cancel() }

    public fun signOut(signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.signOut() }

    public fun observeState(listener: (CodexAuthenticationState) -> Unit): CodexObservation =
        observeOwnedState(core.state, CoreAuthenticationState::project, listener)

    public fun observeAuthenticated(listener: (Boolean) -> Unit): CodexObservation =
        observeOwnedState(core.isAuthenticated, { it }, listener)

    public fun observeAuthenticating(listener: (Boolean) -> Unit): CodexObservation =
        observeOwnedState(core.isAuthenticating, { it }, listener)

    private fun <T, R> observeOwnedState(
        state: StateFlow<T>,
        project: (T) -> R,
        listener: (R) -> Unit,
    ): CodexObservation {
        val owned = combine(host.lifecycleState(), state) { hostState, value ->
            OwnedValue(value, (hostState as? CoreHostState.Ready)?.agent !== agent)
        }
        return observeFlow(
            scope = host.operationScope(),
            state = owned,
            project = { project(it.value) },
            listener = listener,
            isTerminal = { it.terminal },
        )
    }
}

/** Explicitly closeable canonical Conversation projection. */
@JsExport
public class CodexConversation internal constructor(
    private val host: CodexHost,
    private val core: CoreConversation,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex conversations are created by an Agent" }
        hideBackingFields(this)
    }

    public val state: CodexConversationState
        get() = core.project()

    public fun send(prompt: String, signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.send(prompt) }

    public fun runShellCommand(command: String, signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.runShellCommand(command) }

    public fun cancelTurn(): Promise<Unit> =
        host.operationScope().codexUnitPromise(null) { core.cancelTurn() }

    public fun reload(signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.reload() }

    public fun observeState(listener: (CodexConversationState) -> Unit): CodexObservation = observeStateFlow(
        scope = host.operationScope(),
        state = core.state,
        project = { core.project(it) },
        listener = listener,
        isTerminal = { it.status == AgentConversationStatus.CLOSED },
    )

    public fun close(): Promise<Unit> = cleanupPromise { core.close() }

    public fun dispose(): Promise<Unit> = close()
}

private data class ActiveConversationState(
    val conversation: CodexConversation?,
    val terminal: Boolean,
)

private data class OwnedValue<T>(
    val value: T,
    val terminal: Boolean,
)

private class CodexAbortError(message: String) : CancellationException(message) {
    init {
        asDynamic().name = "AbortError"
    }
}

private fun String?.toApprovalPreset(): AgentApprovalPreset = when (this) {
    null, "auto_review" -> AgentApprovalPreset.AUTO_REVIEW
    "never" -> AgentApprovalPreset.NEVER
    "ask_me" -> AgentApprovalPreset.ASK_ME
    "strict" -> AgentApprovalPreset.STRICT
    else -> throw IllegalArgumentException("Unknown approval preset: $this")
}

private fun String?.toAuthenticationMethod(apiKey: String?): CoreAuthenticationMethod = when (this) {
    null, "chatgpt_browser" -> {
        require(apiKey == null) { "apiKey is only valid for api_key authentication" }
        CoreAuthenticationMethod.ChatGptBrowser
    }
    "chatgpt_device_code" -> {
        require(apiKey == null) { "apiKey is only valid for api_key authentication" }
        CoreAuthenticationMethod.ChatGptDeviceCode
    }
    "api_key" -> CoreAuthenticationMethod.ApiKey(requireNotNull(apiKey) {
        "apiKey is required for api_key authentication"
    })
    else -> throw IllegalArgumentException("Unknown authentication method: $this")
}

private fun String.toCoreElicitationValidationReason(): CoreElicitationValidationReason =
    CoreElicitationValidationReason.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown elicitation validation reason: $this")

private fun String.toCorePlanStepStatus(): CorePlanStepStatus =
    CorePlanStepStatus.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown plan step status: $this")

private fun String.requireJavaScriptString(name: String): String {
    require(jsTypeOf(this) == "string") { "$name must be a string" }
    return this
}

private fun String?.requireJavaScriptNullableString(name: String): String? {
    require(this == null || jsTypeOf(this) == "string") { "$name must be a string or null" }
    return this
}

private fun requireJavaScriptArray(value: Any?, name: String): Unit {
    require(js("Array.isArray(value)") as Boolean) { "$name must be an array" }
}

private fun CoreWorkspace.project(): CodexWorkspace = CodexWorkspace(path, displayName)

private fun CoreFailure.project(): CodexFailure = CodexFailure(code, message, isRecoverable)

private fun CoreAuthenticationState.project(): CodexAuthenticationState = CodexAuthenticationState(
    status = status.name.lowercase(),
    pendingSignInUrl = pendingSignInUrl?.value,
    deviceVerificationUrl = deviceVerificationUrl?.value,
    deviceUserCode = deviceUserCode,
    failure = failure?.project(),
    token = jsApiToken,
)

private fun CoreMessage.project(): CodexMessage = CodexMessage(
    id = id,
    clientMessageId = clientMessageId,
    role = role.name.lowercase(),
    text = text,
    reasoning = reasoning,
    plan = plan,
    shellCommand = shellCommand,
    exitCode = exitCode,
)

private fun CoreTurnProgress.project(): CodexTurnProgress = CodexTurnProgress(
    text = text,
    commentary = commentary,
    reasoning = reasoning,
    plan = plan,
    shellOutput = shellOutput,
    shellExitCode = shellExitCode,
    workActivity = workActivity?.name?.lowercase(),
    truncated = isTruncated,
)

private fun CoreConversation.project(state: CoreConversationState = this.state.value): CodexConversationState =
    CodexConversationState(
        status = state.status.name.lowercase(),
        conversationId = state.conversationId?.value,
        title = state.conversation?.summary?.title,
        messages = currentMessages.value.map(CoreMessage::project).toTypedArray(),
        turnProgress = activeTurnProgress.value?.project(),
        model = state.model,
        effort = state.effort,
        serviceTier = state.serviceTier,
        failure = state.failure?.project(),
        isTurnActive = isTurnActive.value,
        canStartTurn = state.canStartTurn,
        canReload = state.canReload,
        canCancelTurn = state.canCancelTurn,
        canRunShellCommand = canRunShellCommand.value,
    )

private fun <T> CoroutineScope.codexPromise(
    signal: AbortSignal?,
    operation: suspend () -> T,
): Promise<T> = promise {
    val job = checkNotNull(currentCoroutineContext()[Job])
    var abortError: CodexAbortError? = null
    val abort = {
        if (abortError == null) {
            abortError = CodexAbortError("The operation was aborted")
            job.cancel(abortError)
        }
    }
    if (signal != null) {
        signal.addEventListener("abort", abort)
        if (signal.aborted) abort()
    }
    try {
        currentCoroutineContext().ensureActive()
        operation()
    } catch (error: Throwable) {
        throw abortError ?: error.toJavaScriptError()
    } finally {
        signal?.removeEventListener("abort", abort)
    }
}

private fun CoroutineScope.codexUnitPromise(
    signal: AbortSignal?,
    operation: suspend () -> Unit,
): Promise<Unit> = discardPromiseResult(codexPromise(signal, operation))

private fun cleanupPromise(operation: suspend () -> Unit): Promise<Unit> =
    discardPromiseResult(CoroutineScope(Dispatchers.Default).promise {
        try {
            operation()
        } catch (error: Throwable) {
            throw error.toJavaScriptError()
        }
    })

private fun discardPromiseResult(promise: Promise<Unit>): Promise<Unit> =
    js("promise.then(function () {})")

private fun Throwable.toJavaScriptError(): Throwable = when (this) {
    is CodexOperationException -> CodexError(
        message = failure.message,
        code = failure.code,
        recoverable = failure.isRecoverable,
        cause = cause,
    )
    is CancellationException -> CodexAbortError(message ?: "The operation was cancelled")
    else -> this
}

private fun <T, R> observeStateFlow(
    scope: CoroutineScope,
    state: StateFlow<T>,
    project: (T) -> R,
    listener: (R) -> Unit,
    isTerminal: (T) -> Boolean,
): CodexObservation = observeFlow(scope, state, project, listener, isTerminal)

private fun <T, R> observeFlow(
    scope: CoroutineScope,
    state: Flow<T>,
    project: (T) -> R,
    listener: (R) -> Unit,
    isTerminal: (T) -> Boolean,
): CodexObservation {
    val job = Job(scope.coroutineContext[Job])
    val observation = CodexObservation(job, jsApiToken)
    CoroutineScope(scope.coroutineContext + job).launch {
        try {
            state.collect { value ->
                if (!observation.deliver { listener(project(value)) }) return@collect
                if (isTerminal(value)) observation.close()
            }
        } finally {
            observation.close()
        }
    }
    return observation
}

private val jsApiToken: Any = Any()

private fun hideBackingFields(value: Any): Unit {
    js("Object.keys(value).forEach(function (key) { Object.defineProperty(value, key, { enumerable: false }); })")
}

private fun freezeSnapshot(value: Any): Unit {
    hideBackingFields(value)
    js("Object.freeze(value)")
}

private fun reportUnhandledCallbackError(error: Throwable): Unit {
    js("console.error(error)")
}
