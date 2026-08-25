@file:OptIn(ExperimentalJsExport::class)

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationState as CoreAuthenticationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConnector as CoreConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSummary as CoreConversationSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSettings
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState as CoreConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidation as CoreElicitationValidation
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationIssue as CoreElicitationValidationIssue
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationReason as CoreElicitationValidationReason
import io.github.codex_agent_labs.codexmobile.agent.AgentFormOption as CoreFormOption
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue.BooleanValue as CoreFormBooleanValue
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue.Number as CoreFormNumberValue
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue.Text as CoreFormTextValue
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue.TextList as CoreFormTextListValue
import io.github.codex_agent_labs.codexmobile.agent.AgentHookActivity as CoreHookActivity
import io.github.codex_agent_labs.codexmobile.agent.AgentHookRunStatus as CoreHookRunStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentSource as CoreMcpEnvironmentSource
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentVariable as CoreMcpEnvironmentVariable
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpOauthConfiguration as CoreMcpOauthConfiguration
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolApproval as CoreMcpToolApproval
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolConfiguration as CoreMcpToolConfiguration
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage as CoreMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentModel as CoreModel
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanProgress as CorePlanProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStep as CorePlanStep
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStepStatus as CorePlanStepStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentResolution as CoreResolution
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier as CoreServiceTier
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress as CoreTurnProgress
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent as CoreAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthentication as CoreAuthentication
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod as CoreAuthenticationMethod
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexConnectors as CoreConnectors
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation as CoreConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure as CoreFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState as CoreHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexModels as CoreModels
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

/** Immutable text form value. */
@JsExport
public class AgentFormTextValue public constructor(value: String) {
    public val value: String

    init {
        val core = CoreFormTextValue(value.requireJavaScriptString("value"))
        this.value = core.value
        freezeSnapshot(this)
    }
}

/** Immutable number form value. */
@JsExport
public class AgentFormNumberValue public constructor(value: Double) {
    public val value: Double

    init {
        val core = CoreFormNumberValue(value.requireJavaScriptNumber("value"))
        this.value = core.value
        freezeSnapshot(this)
    }
}

/** Immutable boolean form value. */
@JsExport
public class AgentFormBooleanValue public constructor(value: Boolean) {
    public val value: Boolean

    init {
        val core = CoreFormBooleanValue(value.requireJavaScriptBoolean("value"))
        this.value = core.value
        freezeSnapshot(this)
    }
}

/** Immutable text-list form value. */
@JsExport
public class AgentFormTextListValue public constructor(value: Array<String>) {
    public val value: Array<String>

    init {
        requireJavaScriptArray(value, "value")
        val core = CoreFormTextListValue(
            List(value.size) { index ->
                requireOwnJavaScriptArrayIndex(value, index, "value")
                value[index].requireJavaScriptString("value[$index]")
            },
        )
        this.value = core.value.toTypedArray()
        freezeSnapshot(this.value)
        freezeSnapshot(this)
    }
}

/** Immutable MCP environment-variable reference. */
@JsExport
public class AgentMcpEnvironmentVariable public constructor(
    name: String,
    source: String? = null,
) {
    public val name: String
    public val source: String?

    init {
        val core = CoreMcpEnvironmentVariable(
            name.requireJavaScriptString("name"),
            source.requireJavaScriptNullableString("source")?.toCoreMcpEnvironmentSource(),
        )
        this.name = core.name
        this.source = core.source?.name?.lowercase()
        freezeSnapshot(this)
    }
}

/** Immutable MCP OAuth configuration. */
@JsExport
public class AgentMcpOauthConfiguration public constructor(
    clientId: String? = null,
    callbackPort: Int? = null,
) {
    public val clientId: String?
    public val callbackPort: Int?

    init {
        val core = CoreMcpOauthConfiguration(
            clientId.requireJavaScriptNullableString("clientId"),
            requireJavaScriptNullableInteger(callbackPort, "callbackPort"),
        )
        this.clientId = core.clientId
        this.callbackPort = core.callbackPort
        freezeSnapshot(this)
    }
}

/** Immutable MCP tool configuration. */
@JsExport
public class AgentMcpToolConfiguration public constructor(approval: String? = null) {
    public val approval: String?

    init {
        val core = CoreMcpToolConfiguration(
            approval.requireJavaScriptNullableString("approval")?.toCoreMcpToolApproval(),
        )
        this.approval = core.approval?.name?.lowercase()
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
        val stepSnapshots = List(steps.size) { index ->
            requireOwnJavaScriptArrayIndex(steps, index, "steps")
            val step = steps[index]
            AgentPlanStep(step.text, step.status)
        }.toTypedArray()
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

/** Immutable hook-run activity value. */
@JsExport
public class AgentHookActivity public constructor(
    id: String,
    eventName: String,
    handlerType: String,
    status: String,
    statusMessage: String? = null,
    details: Array<String> = emptyArray(),
) {
    public val id: String
    public val eventName: String
    public val handlerType: String
    public val status: String
    public val statusMessage: String?
    public val details: Array<String>

    init {
        requireJavaScriptArray(details, "details")
        val core = CoreHookActivity(
            id.requireJavaScriptString("id"),
            eventName.requireJavaScriptString("eventName"),
            handlerType.requireJavaScriptString("handlerType"),
            status.requireJavaScriptString("status").toCoreHookRunStatus(),
            statusMessage.requireJavaScriptNullableString("statusMessage"),
            List(details.size) { index ->
                requireOwnJavaScriptArrayIndex(details, index, "details")
                details[index].requireJavaScriptString("details[$index]")
            },
        )
        this.id = core.id
        this.eventName = core.eventName
        this.handlerType = core.handlerType
        this.status = core.status.name.lowercase()
        this.statusMessage = core.statusMessage
        this.details = core.details.toTypedArray()
        freezeSnapshot(this.details)
        freezeSnapshot(this)
    }
}

/** Immutable connector metadata value. */
@JsExport
public class AgentConnector public constructor(
    id: String,
    name: String,
    description: String = "",
    installUrl: String? = null,
    isAccessible: Boolean = false,
    isEnabled: Boolean = true,
    pluginNames: Array<String> = emptyArray(),
) {
    public val id: String
    public val name: String
    public val description: String
    public val installUrl: String?
    public val isAccessible: Boolean
    public val isEnabled: Boolean
    public val pluginNames: Array<String>

    init {
        requireJavaScriptArray(pluginNames, "pluginNames")
        val core = CoreConnector(
            id = id.requireJavaScriptString("id"),
            name = name.requireJavaScriptString("name"),
            description = description.requireJavaScriptString("description"),
            installUrl = installUrl.requireJavaScriptNullableString("installUrl"),
            isAccessible = isAccessible.requireJavaScriptBoolean("isAccessible"),
            isEnabled = isEnabled.requireJavaScriptBoolean("isEnabled"),
            pluginNames = List(pluginNames.size) { index ->
                requireOwnJavaScriptArrayIndex(pluginNames, index, "pluginNames")
                pluginNames[index].requireJavaScriptString("pluginNames[$index]")
            },
        )
        this.id = core.id
        this.name = core.name
        this.description = core.description
        this.installUrl = core.installUrl
        this.isAccessible = core.isAccessible
        this.isEnabled = core.isEnabled
        this.pluginNames = core.pluginNames.toTypedArray()
        freezeSnapshot(this.pluginNames)
        freezeSnapshot(this)
    }
}

/** Immutable model service-tier metadata. */
@JsExport
public class AgentServiceTier public constructor(
    id: String,
    name: String,
    description: String,
) {
    public val id: String
    public val name: String
    public val description: String

    init {
        val core = canonicalServiceTier(
            id = id,
            name = name,
            description = description,
        )
        this.id = core.id
        this.name = core.name
        this.description = core.description
        freezeSnapshot(this)
    }
}

/** Immutable model metadata. */
@JsExport
public class AgentModel public constructor(
    id: String,
    displayName: String,
    description: String,
    supportedEfforts: Array<String>,
    defaultEffort: String,
    isDefault: Boolean,
    serviceTiers: Array<AgentServiceTier> = emptyArray(),
    defaultServiceTier: String? = null,
) {
    public val id: String
    public val displayName: String
    public val description: String
    public val supportedEfforts: Array<String>
    public val defaultEffort: String
    public val isDefault: Boolean
    public val serviceTiers: Array<AgentServiceTier>
    public val defaultServiceTier: String?

    init {
        val core = canonicalModel(
            id = id,
            displayName = displayName,
            description = description,
            supportedEfforts = supportedEfforts,
            defaultEffort = defaultEffort,
            isDefault = isDefault,
            serviceTiers = serviceTiers,
            defaultServiceTier = defaultServiceTier,
        )
        this.id = core.id
        this.displayName = core.displayName
        this.description = core.description
        this.supportedEfforts = core.supportedEfforts.toTypedArray()
        this.defaultEffort = core.defaultEffort
        this.isDefault = core.isDefault
        this.serviceTiers = core.serviceTiers.map(CoreServiceTier::project).toTypedArray()
        this.defaultServiceTier = core.defaultServiceTier
        freezeSnapshot(this.supportedEfforts)
        freezeSnapshot(this.serviceTiers)
        freezeSnapshot(this)
    }
}

/** Immutable conversation-history summary. */
@JsExport
public class AgentConversationSummary public constructor(
    conversationId: String,
    title: String,
    updatedAtEpochSeconds: Long,
) {
    public val conversationId: String
    public val title: String
    public val updatedAtEpochSeconds: Long

    init {
        val core = CoreConversationSummary(
            conversationId = ConversationId(conversationId.requireJavaScriptString("conversationId")),
            title = title.requireJavaScriptString("title"),
            updatedAtEpochSeconds = updatedAtEpochSeconds
                .requireJavaScriptBigInt("updatedAtEpochSeconds")
                .toString()
                .toLong(),
        )
        this.conversationId = core.conversationId.value
        this.title = core.title
        this.updatedAtEpochSeconds = core.updatedAtEpochSeconds.toJavaScriptBigInt()
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
    text: String,
    commentary: String,
    reasoning: String,
    plan: String,
    planProgress: CorePlanProgress?,
    shellOutput: String,
    shellExitCode: Int?,
    workActivity: String?,
    hookActivities: List<CoreHookActivity>,
    truncated: Boolean,
) {
    public val text: String = text
    public val commentary: String = commentary
    public val reasoning: String = reasoning
    public val plan: String = plan
    public val planProgress: AgentPlanProgress? = planProgress?.project()
    public val shellOutput: String = shellOutput
    public val shellExitCode: Int? = shellExitCode
    public val workActivity: String? = workActivity
    public val hookActivities: Array<AgentHookActivity> =
        hookActivities.map { it.project() }.toTypedArray()
    public val truncated: Boolean = truncated

    init {
        freezeSnapshot(this.hookActivities)
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
): CodexHost {
    val name = clientName.requireJavaScriptString("clientName")
    val title = clientTitle.requireJavaScriptString("clientTitle")
    val version = clientVersion.requireJavaScriptString("clientVersion")
    return CodexHost(
        CoreHost(
            NodeCodexPlatform(bundleDirectory.toPath(), dataDirectory.toPath()),
            CodexClientInfo(name, title, version),
        ),
        jsApiToken,
    )
}

@JsExport
public fun codexApprovalPresetDisplayName(preset: String): String = preset.toApprovalPreset().displayName

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
    private val connectorsProjection: CodexConnectors =
        CodexConnectors(host, core.connectors, jsApiToken)
    private val modelsProjection: CodexModels =
        CodexModels(host, core.models, jsApiToken)
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

    public val connectors: CodexConnectors
        get() = connectorsProjection

    public val models: CodexModels
        get() = modelsProjection

    public val activeConversation: CodexConversation?
        get() = if (host.owns(core)) core.conversations.active.value?.let(::wrapConversation) else null

    public fun listConversations(
        signal: AbortSignal? = null,
    ): Promise<Array<AgentConversationSummary>> = host.operationScope().codexPromise(signal) {
        val conversations = core.conversations.list()
            .map(CoreConversationSummary::project)
            .toTypedArray()
        freezeSnapshot(conversations)
        conversations
    }

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

    public fun rename(
        conversationId: String,
        name: String,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        core.conversations.rename(ConversationId(conversationId), name)
    }

    public fun delete(
        conversationId: String,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        core.conversations.delete(ConversationId(conversationId))
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

/** Agent-owned connector catalog. */
@JsExport
public class CodexConnectors internal constructor(
    private val host: CodexHost,
    private val core: CoreConnectors,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex connector catalogs are created by an Agent" }
        hideBackingFields(this)
    }

    public val isAvailable: Boolean
        get() = core.isAvailable

    public fun list(
        forceReload: Boolean = false,
        signal: AbortSignal? = null,
    ): Promise<Array<AgentConnector>> = host.operationScope().codexPromise(signal) {
        val connectors = core.list(forceReload.requireJavaScriptBoolean("forceReload"))
            .map(CoreConnector::project)
            .toTypedArray()
        freezeSnapshot(connectors)
        connectors
    }
}

/** Agent-owned model catalog and preference resolver. */
@JsExport
public class CodexModels internal constructor(
    private val host: CodexHost,
    private val core: CoreModels,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex model catalogs are created by an Agent" }
        hideBackingFields(this)
    }

    public fun list(
        signal: AbortSignal? = null,
    ): Promise<Array<AgentModel>> = host.operationScope().codexPromise(signal) {
        val models = core.list().map(CoreModel::project).toTypedArray()
        freezeSnapshot(models)
        models
    }

    public fun resolve(
        resolution: String = "preferred",
        signal: AbortSignal? = null,
    ): Promise<AgentModel> = host.operationScope().codexPromise(signal) {
        core.resolve(resolution.toCoreResolution()).project()
    }

    public fun resolveEffort(
        model: AgentModel,
        resolution: String = "preferred",
        signal: AbortSignal? = null,
    ): Promise<String> = modelResolutionScope(host, resolution).codexPromise(signal) {
        core.resolveEffort(model.canonicalCopy(), resolution.toCoreResolution())
    }

    public fun resolveServiceTier(
        model: AgentModel,
        resolution: String = "preferred",
        signal: AbortSignal? = null,
    ): Promise<AgentServiceTier?> = modelResolutionScope(host, resolution).codexPromise(signal) {
        core.resolveServiceTier(model.canonicalCopy(), resolution.toCoreResolution())?.project()
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

private fun String?.toApprovalPreset(): AgentApprovalPreset {
    if (this == null) return AgentApprovalPreset.AUTO_REVIEW
    return AgentApprovalPreset.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown approval preset: $this")
}

private fun String.toCoreResolution(): CoreResolution {
    val value = requireJavaScriptString("resolution")
    return CoreResolution.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown agent resolution: $value")
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
    "api_key" -> CoreAuthenticationMethod.ApiKey(
        requireNotNull(apiKey) {
            "apiKey is required for api_key authentication"
        }.requireJavaScriptString("apiKey"),
    )
    else -> throw IllegalArgumentException("Unknown authentication method: $this")
}

private fun String.toCoreElicitationValidationReason(): CoreElicitationValidationReason =
    CoreElicitationValidationReason.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown elicitation validation reason: $this")

private fun String.toCorePlanStepStatus(): CorePlanStepStatus =
    CorePlanStepStatus.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown plan step status: $this")

private fun String.toCoreHookRunStatus(): CoreHookRunStatus =
    CoreHookRunStatus.entries.singleOrNull { it.name.lowercase() == this }
        ?: throw IllegalArgumentException("Unknown hook run status: $this")

private fun String.toCoreMcpEnvironmentSource(): CoreMcpEnvironmentSource = when (this) {
    "local" -> CoreMcpEnvironmentSource.LOCAL
    "remote" -> CoreMcpEnvironmentSource.REMOTE
    else -> throw IllegalArgumentException("Unknown MCP environment source: $this")
}

private fun String.toCoreMcpToolApproval(): CoreMcpToolApproval = when (this) {
    "approve" -> CoreMcpToolApproval.APPROVE
    "auto" -> CoreMcpToolApproval.AUTO
    "prompt" -> CoreMcpToolApproval.PROMPT
    "writes" -> CoreMcpToolApproval.WRITES
    else -> throw IllegalArgumentException("Unknown MCP tool approval: $this")
}

private fun String.requireJavaScriptString(name: String): String {
    require(jsTypeOf(this) == "string") { "$name must be a string" }
    return this
}

private fun String?.requireJavaScriptNullableString(name: String): String? {
    require(this == null || jsTypeOf(this) == "string") { "$name must be a string or null" }
    return this
}

private fun requireJavaScriptNullableInteger(value: Int?, name: String): Int? {
    require(value == null || js("Number.isInteger(value)") as Boolean) { "$name must be an integer or null" }
    return value
}

private fun Double.requireJavaScriptNumber(name: String): Double {
    require(jsTypeOf(this) == "number") { "$name must be a number" }
    return this
}

private fun Boolean.requireJavaScriptBoolean(name: String): Boolean {
    require(jsTypeOf(this) == "boolean") { "$name must be a boolean" }
    return this
}

private fun Long.requireJavaScriptBigInt(name: String): Long {
    val value: Any = this
    require(jsTypeOf(value) == "bigint") { "$name must be a bigint" }
    require(
        js("value >= BigInt('-9223372036854775808') && value <= BigInt('9223372036854775807')") as Boolean,
    ) { "$name must fit a signed 64-bit integer" }
    return this
}

private fun Long.toJavaScriptBigInt(): Long {
    val value = toString()
    return js("BigInt(value)").unsafeCast<Long>()
}

private fun requireJavaScriptArray(value: Any?, name: String): Unit {
    require(js("Array.isArray(value)") as Boolean) { "$name must be an array" }
}

private fun requireOwnJavaScriptArrayIndex(value: Any?, index: Int, name: String): Unit {
    require(js("Object.hasOwn(value, index)") as Boolean) { "$name must not contain sparse elements" }
}

private fun canonicalServiceTier(
    id: String,
    name: String,
    description: String,
): CoreServiceTier = CoreServiceTier(
    id = id.requireJavaScriptString("id"),
    name = name.requireJavaScriptString("name"),
    description = description.requireJavaScriptString("description"),
)

private fun canonicalModel(
    id: String,
    displayName: String,
    description: String,
    supportedEfforts: Array<String>,
    defaultEffort: String,
    isDefault: Boolean,
    serviceTiers: Array<AgentServiceTier>,
    defaultServiceTier: String?,
): CoreModel {
    requireJavaScriptArray(supportedEfforts, "supportedEfforts")
    requireJavaScriptArray(serviceTiers, "serviceTiers")
    return CoreModel(
        id = id.requireJavaScriptString("id"),
        displayName = displayName.requireJavaScriptString("displayName"),
        description = description.requireJavaScriptString("description"),
        supportedEfforts = List(supportedEfforts.size) { index ->
            requireOwnJavaScriptArrayIndex(supportedEfforts, index, "supportedEfforts")
            supportedEfforts[index].requireJavaScriptString("supportedEfforts[$index]")
        },
        defaultEffort = defaultEffort.requireJavaScriptString("defaultEffort"),
        isDefault = isDefault.requireJavaScriptBoolean("isDefault"),
        serviceTiers = List(serviceTiers.size) { index ->
            requireOwnJavaScriptArrayIndex(serviceTiers, index, "serviceTiers")
            val tier = serviceTiers[index]
            canonicalServiceTier(tier.id, tier.name, tier.description)
        },
        defaultServiceTier = defaultServiceTier.requireJavaScriptNullableString("defaultServiceTier"),
    )
}

private fun AgentModel.canonicalCopy(): CoreModel = canonicalModel(
    id = id,
    displayName = displayName,
    description = description,
    supportedEfforts = supportedEfforts,
    defaultEffort = defaultEffort,
    isDefault = isDefault,
    serviceTiers = serviceTiers,
    defaultServiceTier = defaultServiceTier,
)

private fun modelResolutionScope(host: CodexHost, resolution: String): CoroutineScope =
    if (jsTypeOf(resolution) == "string" && (resolution == "default" || resolution == "first")) {
        CoroutineScope(Dispatchers.Default)
    } else {
        host.operationScope()
    }

private fun CoreWorkspace.project(): CodexWorkspace = CodexWorkspace(path, displayName)

private fun CoreConnector.project(): AgentConnector = AgentConnector(
    id = id,
    name = name,
    description = description,
    installUrl = installUrl,
    isAccessible = isAccessible,
    isEnabled = isEnabled,
    pluginNames = pluginNames.toTypedArray(),
)

private fun CoreServiceTier.project(): AgentServiceTier = AgentServiceTier(id, name, description)

private fun CoreModel.project(): AgentModel = AgentModel(
    id = id,
    displayName = displayName,
    description = description,
    supportedEfforts = supportedEfforts.toTypedArray(),
    defaultEffort = defaultEffort,
    isDefault = isDefault,
    serviceTiers = serviceTiers.map(CoreServiceTier::project).toTypedArray(),
    defaultServiceTier = defaultServiceTier,
)

private fun CoreConversationSummary.project(): AgentConversationSummary = AgentConversationSummary(
    conversationId = conversationId.value,
    title = title,
    updatedAtEpochSeconds = updatedAtEpochSeconds.toJavaScriptBigInt(),
)

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

private fun CorePlanProgress.project(): AgentPlanProgress = AgentPlanProgress(
    explanation = explanation,
    steps = steps.map { AgentPlanStep(it.text, it.status.name.lowercase()) }.toTypedArray(),
)

private fun CoreHookActivity.project(): AgentHookActivity = AgentHookActivity(
    id = id,
    eventName = eventName,
    handlerType = handlerType,
    status = status.name.lowercase(),
    statusMessage = statusMessage,
    details = details.toTypedArray(),
)

private fun CoreTurnProgress.project(): CodexTurnProgress = CodexTurnProgress(
    text = text,
    commentary = commentary,
    reasoning = reasoning,
    plan = plan,
    planProgress = planProgress,
    shellOutput = shellOutput,
    shellExitCode = shellExitCode,
    workActivity = workActivity?.name?.lowercase(),
    hookActivities = hookActivities,
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
