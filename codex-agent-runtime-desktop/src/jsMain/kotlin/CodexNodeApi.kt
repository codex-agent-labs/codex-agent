@file:OptIn(ExperimentalJsExport::class)

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationState as CoreAuthenticationState
import io.github.codex_agent_labs.codexmobile.agent.AgentCapability as CoreCapability
import io.github.codex_agent_labs.codexmobile.agent.AgentCollaborationMode as CoreCollaborationMode
import io.github.codex_agent_labs.codexmobile.agent.AgentConnector as CoreConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentConversation as CoreAgentConversation
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
import io.github.codex_agent_labs.codexmobile.agent.AgentHook as CoreHook
import io.github.codex_agent_labs.codexmobile.agent.AgentHookCatalog as CoreHookCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler as CoreHookHandler
import io.github.codex_agent_labs.codexmobile.agent.AgentHookRunStatus as CoreHookRunStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentHookTrustStatus as CoreHookTrustStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope as CoreInstallationScope
import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation as CoreInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentSource as CoreMcpEnvironmentSource
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentVariable as CoreMcpEnvironmentVariable
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpOauthConfiguration as CoreMcpOauthConfiguration
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolApproval as CoreMcpToolApproval
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolConfiguration as CoreMcpToolConfiguration
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage as CoreMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentMessageRole as CoreMessageRole
import io.github.codex_agent_labs.codexmobile.agent.AgentModel as CoreModel
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanProgress as CorePlanProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStep as CorePlanStep
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStepStatus as CorePlanStepStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentResolution as CoreResolution
import io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin as CoreResourceOrigin
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier as CoreServiceTier
import io.github.codex_agent_labs.codexmobile.agent.AgentSkill as CoreSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillCatalog as CoreSkillCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillChunk as CoreSkillChunk
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillScope as CoreAgentSkillScope
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress as CoreTurnProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest as CoreTurnRequest
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent as CoreAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthentication as CoreAuthentication
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod as CoreAuthenticationMethod
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexConnectors as CoreConnectors
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation as CoreConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure as CoreFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState as CoreHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexHooks as CoreHooks
import io.github.codex_agent_labs.codexmobile.agent.CodexModels as CoreModels
import io.github.codex_agent_labs.codexmobile.agent.CodexOperationException
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexSkills as CoreSkills
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

/** Structural turn request accepted by [CodexConversation.sendRequest]. */
@JsExport
public external interface AgentTurnRequest {
    public val prompt: String
    public val clientMessageId: String?
    public val model: String?
    public val effort: String?
    public val serviceTier: String?
    public val approvalPreset: String?
    public val capabilities: Array<String>?
    public val invocations: Array<AgentInvocation>?
    public val collaborationMode: String?
}

/** Structural hook handler projected as a reviewed discriminated union. */
@JsExport
public external interface AgentHookHandler

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

/** Immutable hook metadata. Handler values use the reviewed AgentHookHandler structural union. */
@JsExport
public class AgentHook public constructor(
    key: String,
    currentHash: String,
    isEnabled: Boolean,
    eventName: String,
    handler: AgentHookHandler,
    isManaged: Boolean,
    source: String,
    sourcePath: String,
    timeoutSeconds: Long,
    trustStatus: String,
    matcher: String? = null,
    pluginId: String? = null,
    statusMessage: String? = null,
    origin: String = canonicalDefaultAgentHookOrigin(source, isManaged, pluginId),
    canUninstall: Boolean = false,
) {
    public val key: String
    public val currentHash: String
    public val isEnabled: Boolean
    public val eventName: String
    public val handler: AgentHookHandler
    public val isManaged: Boolean
    public val source: String
    public val sourcePath: String
    public val timeoutSeconds: Long
    public val trustStatus: String
    public val matcher: String?
    public val pluginId: String?
    public val statusMessage: String?
    public val origin: String
    public val canUninstall: Boolean
    public val canTrust: Boolean

    init {
        val core = canonicalHook(
            key = key,
            currentHash = currentHash,
            isEnabled = isEnabled,
            eventName = eventName,
            handler = handler,
            isManaged = isManaged,
            source = source,
            sourcePath = sourcePath,
            timeoutSeconds = timeoutSeconds,
            trustStatus = trustStatus,
            matcher = matcher,
            pluginId = pluginId,
            statusMessage = statusMessage,
            origin = origin,
            canUninstall = canUninstall,
        )
        this.key = core.key
        this.currentHash = core.currentHash
        this.isEnabled = core.isEnabled
        this.eventName = core.eventName
        this.handler = core.handler.project()
        this.isManaged = core.isManaged
        this.source = core.source
        this.sourcePath = core.sourcePath
        this.timeoutSeconds = core.timeoutSeconds.toJavaScriptBigInt()
        this.trustStatus = core.trustStatus.name.lowercase()
        this.matcher = core.matcher
        this.pluginId = core.pluginId
        this.statusMessage = core.statusMessage
        this.origin = core.origin.name.lowercase()
        this.canUninstall = core.canUninstall
        this.canTrust = core.canTrust
        freezeSnapshot(this)
    }
}

/** Immutable hook catalog. */
@JsExport
public class AgentHookCatalog public constructor(
    hooks: Array<AgentHook>,
    warnings: Array<String> = emptyArray(),
    errors: Array<String> = emptyArray(),
) {
    public val hooks: Array<AgentHook>
    public val warnings: Array<String>
    public val errors: Array<String>

    init {
        requireJavaScriptArray(hooks, "hooks")
        requireJavaScriptArray(warnings, "warnings")
        requireJavaScriptArray(errors, "errors")
        val core = CoreHookCatalog(
            hooks = List(hooks.size) { index ->
                requireOwnJavaScriptArrayIndex(hooks, index, "hooks")
                val hook: Any? = hooks[index]
                require(hook is AgentHook) { "hooks[$index] must be an AgentHook" }
                hook.canonicalCopy()
            },
            warnings = List(warnings.size) { index ->
                requireOwnJavaScriptArrayIndex(warnings, index, "warnings")
                warnings[index].requireJavaScriptString("warnings[$index]")
            },
            errors = List(errors.size) { index ->
                requireOwnJavaScriptArrayIndex(errors, index, "errors")
                errors[index].requireJavaScriptString("errors[$index]")
            },
        )
        this.hooks = core.hooks.map(CoreHook::project).toTypedArray()
        this.warnings = core.warnings.toTypedArray()
        this.errors = core.errors.toTypedArray()
        freezeSnapshot(this.hooks)
        freezeSnapshot(this.warnings)
        freezeSnapshot(this.errors)
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

/** Common immutable skill/plugin invocation projection. */
@JsExport
public interface AgentInvocation {
    public val name: String
    public val key: String
}

/** Immutable skill invocation value. */
@JsExport
public class AgentSkillInvocation public constructor(
    name: String,
    path: String,
) : AgentInvocation {
    public override val name: String
    public val path: String
    public override val key: String

    init {
        val core = CoreInvocation.Skill(
            name.requireJavaScriptString("name"),
            path.requireJavaScriptString("path"),
        )
        this.name = core.name
        this.path = core.path
        this.key = core.key
        freezeSnapshot(this)
    }
}

/** Immutable plugin invocation value. */
@JsExport
public class AgentPluginInvocation public constructor(
    name: String,
    uri: String,
) : AgentInvocation {
    public override val name: String
    public val uri: String
    public override val key: String

    init {
        val core = CoreInvocation.Plugin(
            name.requireJavaScriptString("name"),
            uri.requireJavaScriptString("uri"),
        )
        this.name = core.name
        this.uri = core.uri
        this.key = core.key
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

/** Immutable skill metadata. */
@JsExport
public class AgentSkill public constructor(
    name: String,
    displayName: String,
    description: String,
    path: String,
    scope: String,
    isEnabled: Boolean,
    brandColor: String? = null,
    dependencies: Array<String> = emptyArray(),
    canUninstall: Boolean = false,
    origin: String = canonicalDefaultAgentSkillOrigin(scope),
) {
    public val name: String
    public val displayName: String
    public val description: String
    public val path: String
    public val scope: String
    public val isEnabled: Boolean
    public val brandColor: String?
    public val dependencies: Array<String>
    public val canUninstall: Boolean
    public val origin: String

    init {
        val core = canonicalSkill(
            name = name,
            displayName = displayName,
            description = description,
            path = path,
            scope = scope,
            isEnabled = isEnabled,
            brandColor = brandColor,
            dependencies = dependencies,
            canUninstall = canUninstall,
            origin = origin,
        )
        this.name = core.name
        this.displayName = core.displayName
        this.description = core.description
        this.path = core.path
        this.scope = core.scope.name.lowercase()
        this.isEnabled = core.isEnabled
        this.brandColor = core.brandColor
        this.dependencies = core.dependencies.toTypedArray()
        this.canUninstall = core.canUninstall
        this.origin = core.origin.name.lowercase()
        freezeSnapshot(this.dependencies)
        freezeSnapshot(this)
    }
}

/** Immutable skill catalog. */
@JsExport
public class AgentSkillCatalog public constructor(
    skills: Array<AgentSkill>,
    errors: Array<String> = emptyArray(),
) {
    public val skills: Array<AgentSkill>
    public val errors: Array<String>

    init {
        requireJavaScriptArray(skills, "skills")
        requireJavaScriptArray(errors, "errors")
        val core = CoreSkillCatalog(
            skills = List(skills.size) { index ->
                requireOwnJavaScriptArrayIndex(skills, index, "skills")
                skills[index].canonicalCopy()
            },
            errors = List(errors.size) { index ->
                requireOwnJavaScriptArrayIndex(errors, index, "errors")
                errors[index].requireJavaScriptString("errors[$index]")
            },
        )
        this.skills = core.skills.map(CoreSkill::project).toTypedArray()
        this.errors = core.errors.toTypedArray()
        freezeSnapshot(this.skills)
        freezeSnapshot(this.errors)
        freezeSnapshot(this)
    }
}

/** Immutable bounded skill-source chunk. */
@JsExport
public class AgentSkillChunk public constructor(
    content: String,
    nextOffset: Long?,
    totalBytes: Long,
) {
    public val content: String
    public val nextOffset: Long?
    public val totalBytes: Long

    init {
        val core = CoreSkillChunk(
            content = content.requireJavaScriptString("content"),
            nextOffset = nextOffset.requireJavaScriptNullableBigInt("nextOffset")?.toString()?.toLong(),
            totalBytes = totalBytes.requireJavaScriptBigInt("totalBytes").toString().toLong(),
        )
        this.content = core.content
        this.nextOffset = core.nextOffset?.toJavaScriptBigInt()
        this.totalBytes = core.totalBytes.toJavaScriptBigInt()
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

/** Immutable conversation-history snapshot. */
@JsExport
public class AgentConversation public constructor(
    summary: AgentConversationSummary,
    messages: Array<CodexMessage>,
) {
    public val summary: AgentConversationSummary
    public val messages: Array<CodexMessage>

    init {
        val summaryValue: Any? = summary
        require(summaryValue is AgentConversationSummary) {
            "summary must be an AgentConversationSummary"
        }
        requireJavaScriptArray(messages, "messages")
        this.summary = summaryValue.detachedCopy()
        this.messages = Array(messages.size) { index ->
            requireOwnJavaScriptArrayIndex(messages, index, "messages")
            val message: Any? = messages[index]
            require(message is CodexMessage) { "messages[$index] must be a CodexMessage" }
            message.detachedCopy()
        }
        freezeSnapshot(this.messages)
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
    public val collaborationMode: String,
    public val reasoning: String?,
    public val plan: String?,
    public val shellCommand: String?,
    public val exitCode: Int?,
    public val capabilities: Array<String>,
    public val invocations: Array<AgentInvocation>,
) {
    init {
        freezeSnapshot(capabilities)
        freezeSnapshot(invocations)
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
    public val conversation: AgentConversation?,
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

@JsExport
public fun agentSkillScopeDisplayName(scope: String): String = scope.toAgentSkillScope().displayName

@JsExport
public fun agentCapabilityId(capability: String): String = capability.toAgentCapability().id

@JsExport
public fun agentCapabilityDisplayLabel(capability: String): String = capability.toAgentCapability().displayLabel

@JsExport
public fun agentCapabilityIcon(capability: String): String? = capability.toAgentCapability().icon

@JsExport
public fun agentCapabilityPromptLabel(capability: String): String = capability.toAgentCapability().promptLabel

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
    private val skillsProjection: CodexSkills =
        CodexSkills(host, core.skills, jsApiToken)
    private val hooksProjection: CodexHooks =
        CodexHooks(host, core.hooks, jsApiToken)
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

    public val skills: CodexSkills
        get() = skillsProjection

    public val hooks: CodexHooks
        get() = hooksProjection

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

    public fun readConversation(
        conversationId: String,
        signal: AbortSignal? = null,
    ): Promise<AgentConversation> = host.operationScope().codexPromise(signal) {
        core.conversations.read(
            ConversationId(conversationId.requireJavaScriptString("conversationId")),
        ).project()
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

/** Agent-owned skill catalog, source reader, and installation lifecycle. */
@JsExport
public class CodexSkills internal constructor(
    private val host: CodexHost,
    private val core: CoreSkills,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex skill catalogs are created by an Agent" }
        hideBackingFields(this)
    }

    public val isAvailable: Boolean
        get() = core.isAvailable

    public fun list(
        forceReload: Boolean = false,
        signal: AbortSignal? = null,
    ): Promise<AgentSkillCatalog> = host.operationScope().codexPromise(signal) {
        core.list(forceReload.requireJavaScriptBoolean("forceReload")).project()
    }

    public fun read(
        path: String,
        offset: Long = 0L,
        signal: AbortSignal? = null,
    ): Promise<AgentSkillChunk> = host.operationScope().codexPromise(signal) {
        core.read(
            path.requireJavaScriptString("path"),
            offset.requireJavaScriptBigInt("offset").toString().toLong(),
        ).project()
    }

    public fun install(
        directory: String,
        scope: String,
        signal: AbortSignal? = null,
    ): Promise<AgentSkill> = host.operationScope().codexPromise(signal) {
        core.install(
            directory.requireJavaScriptString("directory"),
            scope.toCoreInstallationScope(),
        ).project()
    }

    public fun uninstall(
        skill: AgentSkill,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        core.uninstall(skill.canonicalCopy())
    }
}

/** Agent-owned hook discovery, installation, and trust lifecycle. */
@JsExport
public class CodexHooks internal constructor(
    private val host: CodexHost,
    private val core: CoreHooks,
    token: Any,
) {
    init {
        require(token === jsApiToken) { "Codex hook catalogs are created by an Agent" }
        hideBackingFields(this)
    }

    public val isAvailable: Boolean
        get() = core.isAvailable

    public fun list(
        signal: AbortSignal? = null,
    ): Promise<AgentHookCatalog> = host.operationScope().codexPromise(signal) {
        core.list().project()
    }

    public fun install(
        directory: String,
        scope: String,
        signal: AbortSignal? = null,
    ): Promise<AgentHook> = host.operationScope().codexPromise(signal) {
        core.install(
            directory.requireJavaScriptString("directory"),
            scope.toCoreInstallationScope(),
        ).project()
    }

    public fun uninstall(
        hook: AgentHook,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        val value: Any? = hook
        require(value is AgentHook) { "hook must be an AgentHook" }
        core.uninstall(value.canonicalCopy())
    }

    public fun trust(
        hook: AgentHook,
        signal: AbortSignal? = null,
    ): Promise<Unit> = host.operationScope().codexUnitPromise(signal) {
        val value: Any? = hook
        require(value is AgentHook) { "hook must be an AgentHook" }
        core.trust(value.canonicalCopy())
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

    public fun sendRequest(request: AgentTurnRequest, signal: AbortSignal? = null): Promise<Unit> =
        host.operationScope().codexUnitPromise(signal) { core.send(request.toCoreTurnRequest()) }

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

private fun String.toAgentSkillScope(): CoreAgentSkillScope {
    val value = requireJavaScriptString("scope")
    return CoreAgentSkillScope.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown skill scope: $value")
}

private fun String.toAgentCapability(name: String = "capability"): CoreCapability {
    val value = requireJavaScriptString(name)
    return CoreCapability.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown agent capability: $value")
}

private fun String.toCoreMessageRole(): CoreMessageRole {
    val value = requireJavaScriptString("role")
    return CoreMessageRole.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown message role: $value")
}

private fun String.toCoreCollaborationMode(): CoreCollaborationMode {
    val value = requireJavaScriptString("collaborationMode")
    return CoreCollaborationMode.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown collaboration mode: $value")
}

private fun String.toCoreInstallationScope(): CoreInstallationScope {
    val value = requireJavaScriptString("scope")
    return CoreInstallationScope.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown installation scope: $value")
}

private fun String.toCoreResourceOrigin(): CoreResourceOrigin {
    val value = requireJavaScriptString("origin")
    return CoreResourceOrigin.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown resource origin: $value")
}

private fun canonicalDefaultAgentSkillOrigin(scope: String): String = CoreSkill(
    name = "",
    displayName = "",
    description = "",
    path = "",
    scope = scope.toAgentSkillScope(),
    isEnabled = false,
).origin.name.lowercase()

private fun canonicalDefaultAgentHookOrigin(
    source: String,
    isManaged: Boolean,
    pluginId: String?,
): String = CoreHook(
    key = "",
    currentHash = "",
    isEnabled = false,
    eventName = "",
    handler = CoreHookHandler.Prompt,
    isManaged = isManaged.requireJavaScriptBoolean("isManaged"),
    source = source.requireJavaScriptString("source"),
    sourcePath = "",
    timeoutSeconds = 0,
    trustStatus = CoreHookTrustStatus.TRUSTED,
    pluginId = pluginId.requireJavaScriptNullableString("pluginId"),
).origin.name.lowercase()

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

private fun String.toCoreHookTrustStatus(): CoreHookTrustStatus {
    val value = requireJavaScriptString("trustStatus")
    return CoreHookTrustStatus.entries.singleOrNull { it.name.lowercase() == value }
        ?: throw IllegalArgumentException("Unknown hook trust status: $value")
}

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
    require(
        value == null ||
            js("Number.isInteger(value) && value >= -2147483648 && value <= 2147483647") as Boolean,
    ) { "$name must be an integer or null" }
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

private fun Long?.requireJavaScriptNullableBigInt(name: String): Long? {
    if (this == null) return null
    return requireJavaScriptBigInt(name)
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

private fun canonicalSkill(
    name: String,
    displayName: String,
    description: String,
    path: String,
    scope: String,
    isEnabled: Boolean,
    brandColor: String?,
    dependencies: Array<String>,
    canUninstall: Boolean,
    origin: String,
): CoreSkill {
    requireJavaScriptArray(dependencies, "dependencies")
    return CoreSkill(
        name = name.requireJavaScriptString("name"),
        displayName = displayName.requireJavaScriptString("displayName"),
        description = description.requireJavaScriptString("description"),
        path = path.requireJavaScriptString("path"),
        scope = scope.toAgentSkillScope(),
        isEnabled = isEnabled.requireJavaScriptBoolean("isEnabled"),
        brandColor = brandColor.requireJavaScriptNullableString("brandColor"),
        dependencies = List(dependencies.size) { index ->
            requireOwnJavaScriptArrayIndex(dependencies, index, "dependencies")
            dependencies[index].requireJavaScriptString("dependencies[$index]")
        },
        canUninstall = canUninstall.requireJavaScriptBoolean("canUninstall"),
        origin = origin.toCoreResourceOrigin(),
    )
}

private fun AgentSkill.canonicalCopy(): CoreSkill = canonicalSkill(
    name = name,
    displayName = displayName,
    description = description,
    path = path,
    scope = scope,
    isEnabled = isEnabled,
    brandColor = brandColor,
    dependencies = dependencies,
    canUninstall = canUninstall,
    origin = origin,
)

private fun AgentHookHandler.toCoreHookHandler(): CoreHookHandler {
    val value: Any? = this
    require(value != null && jsTypeOf(value) == "object") { "handler must be an object" }
    val objectValue = value.asDynamic()
    val type = objectValue.type.unsafeCast<String>().requireJavaScriptString("handler.type")
    return when (type) {
        "agent" -> CoreHookHandler.Agent
        "command" -> CoreHookHandler.Command(
            objectValue.command.unsafeCast<String>().requireJavaScriptString("handler.command"),
            objectValue.isAsync.unsafeCast<Boolean>().requireJavaScriptBoolean("handler.isAsync"),
        )
        "mcp_tool" -> CoreHookHandler.McpTool(
            objectValue.server.unsafeCast<String>().requireJavaScriptString("handler.server"),
            objectValue.tool.unsafeCast<String>().requireJavaScriptString("handler.tool"),
        )
        "prompt" -> CoreHookHandler.Prompt
        else -> throw IllegalArgumentException("Unknown hook handler type: $type")
    }
}

private fun canonicalHook(
    key: String,
    currentHash: String,
    isEnabled: Boolean,
    eventName: String,
    handler: AgentHookHandler,
    isManaged: Boolean,
    source: String,
    sourcePath: String,
    timeoutSeconds: Long,
    trustStatus: String,
    matcher: String?,
    pluginId: String?,
    statusMessage: String?,
    origin: String,
    canUninstall: Boolean,
): CoreHook = CoreHook(
    key = key.requireJavaScriptString("key"),
    currentHash = currentHash.requireJavaScriptString("currentHash"),
    isEnabled = isEnabled.requireJavaScriptBoolean("isEnabled"),
    eventName = eventName.requireJavaScriptString("eventName"),
    handler = handler.toCoreHookHandler(),
    isManaged = isManaged.requireJavaScriptBoolean("isManaged"),
    source = source.requireJavaScriptString("source"),
    sourcePath = sourcePath.requireJavaScriptString("sourcePath"),
    timeoutSeconds = timeoutSeconds.requireJavaScriptBigInt("timeoutSeconds").toString().toLong(),
    trustStatus = trustStatus.toCoreHookTrustStatus(),
    matcher = matcher.requireJavaScriptNullableString("matcher"),
    pluginId = pluginId.requireJavaScriptNullableString("pluginId"),
    statusMessage = statusMessage.requireJavaScriptNullableString("statusMessage"),
    origin = origin.toCoreResourceOrigin(),
    canUninstall = canUninstall.requireJavaScriptBoolean("canUninstall"),
)

private fun AgentHook.canonicalCopy(): CoreHook = canonicalHook(
    key = key,
    currentHash = currentHash,
    isEnabled = isEnabled,
    eventName = eventName,
    handler = handler,
    isManaged = isManaged,
    source = source,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSeconds,
    trustStatus = trustStatus,
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
    origin = origin,
    canUninstall = canUninstall,
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

private fun CoreSkill.project(): AgentSkill = AgentSkill(
    name = name,
    displayName = displayName,
    description = description,
    path = path,
    scope = scope.name.lowercase(),
    isEnabled = isEnabled,
    brandColor = brandColor,
    dependencies = dependencies.toTypedArray(),
    canUninstall = canUninstall,
    origin = origin.name.lowercase(),
)

private fun CoreSkillCatalog.project(): AgentSkillCatalog = AgentSkillCatalog(
    skills = skills.map(CoreSkill::project).toTypedArray(),
    errors = errors.toTypedArray(),
)

private fun CoreSkillChunk.project(): AgentSkillChunk = AgentSkillChunk(
    content = content,
    nextOffset = nextOffset?.toJavaScriptBigInt(),
    totalBytes = totalBytes.toJavaScriptBigInt(),
)

private fun CoreHookHandler.project(): AgentHookHandler {
    val snapshot: dynamic = js("({})")
    when (this) {
        CoreHookHandler.Agent -> snapshot.type = "agent"
        is CoreHookHandler.Command -> {
            snapshot.type = "command"
            snapshot.command = command
            snapshot.isAsync = isAsync
        }
        is CoreHookHandler.McpTool -> {
            snapshot.type = "mcp_tool"
            snapshot.server = server
            snapshot.tool = tool
        }
        CoreHookHandler.Prompt -> snapshot.type = "prompt"
    }
    val value = snapshot.unsafeCast<AgentHookHandler>()
    js("Object.freeze(value)")
    return value
}

private fun CoreHook.project(): AgentHook = AgentHook(
    key = key,
    currentHash = currentHash,
    isEnabled = isEnabled,
    eventName = eventName,
    handler = handler.project(),
    isManaged = isManaged,
    source = source,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSeconds.toJavaScriptBigInt(),
    trustStatus = trustStatus.name.lowercase(),
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
    origin = origin.name.lowercase(),
    canUninstall = canUninstall,
)

private fun CoreHookCatalog.project(): AgentHookCatalog = AgentHookCatalog(
    hooks = hooks.map(CoreHook::project).toTypedArray(),
    warnings = warnings.toTypedArray(),
    errors = errors.toTypedArray(),
)

private fun CoreConversationSummary.project(): AgentConversationSummary = AgentConversationSummary(
    conversationId = conversationId.value,
    title = title,
    updatedAtEpochSeconds = updatedAtEpochSeconds.toJavaScriptBigInt(),
)

private fun CoreAgentConversation.project(): AgentConversation = AgentConversation(
    summary = summary.project(),
    messages = messages.map(CoreMessage::project).toTypedArray(),
)

private fun AgentConversationSummary.detachedCopy(): AgentConversationSummary = AgentConversationSummary(
    conversationId = conversationId,
    title = title,
    updatedAtEpochSeconds = updatedAtEpochSeconds,
)

private fun AgentTurnRequest.toCoreTurnRequest(): CoreTurnRequest {
    val request: Any? = this
    require(request != null && jsTypeOf(request) == "object") { "request must be an object" }

    val promptValue = prompt
    val clientMessageIdValue = clientMessageId
    val modelValue = model
    val effortValue = effort
    val serviceTierValue = serviceTier
    val approvalPresetValue = approvalPreset
    val capabilitiesValue = capabilities
    val invocationsValue = invocations
    val collaborationModeValue = collaborationMode

    val coreCapabilities = if (capabilitiesValue == null) {
        emptySet()
    } else {
        requireJavaScriptArray(capabilitiesValue, "capabilities")
        List(capabilitiesValue.size) { index ->
            requireOwnJavaScriptArrayIndex(capabilitiesValue, index, "capabilities")
            capabilitiesValue[index].toAgentCapability("capabilities[$index]")
        }.toSet()
    }
    val coreInvocations = if (invocationsValue == null) {
        emptyList()
    } else {
        requireJavaScriptArray(invocationsValue, "invocations")
        List(invocationsValue.size) { index ->
            requireOwnJavaScriptArrayIndex(invocationsValue, index, "invocations")
            invocationsValue[index].toCoreInvocation(index)
        }
    }

    return CoreTurnRequest(
        prompt = promptValue.requireJavaScriptString("prompt"),
        clientMessageId = clientMessageIdValue.requireJavaScriptNullableString("clientMessageId"),
        model = modelValue.requireJavaScriptNullableString("model"),
        effort = effortValue.requireJavaScriptNullableString("effort"),
        serviceTier = serviceTierValue.requireJavaScriptNullableString("serviceTier"),
        approvalPreset = approvalPresetValue.requireJavaScriptNullableString("approvalPreset").toApprovalPreset(),
        capabilities = coreCapabilities,
        invocations = coreInvocations,
        collaborationMode = collaborationModeValue.requireJavaScriptNullableString("collaborationMode")
            ?.toCoreCollaborationMode() ?: CoreCollaborationMode.DEFAULT,
    )
}

private fun CodexMessage.detachedCopy(): CodexMessage {
    return CoreMessage(
        id = id.requireJavaScriptString("id"),
        clientMessageId = clientMessageId.requireJavaScriptNullableString("clientMessageId"),
        role = role.toCoreMessageRole(),
        text = text.requireJavaScriptString("text"),
        collaborationMode = collaborationMode.toCoreCollaborationMode(),
        reasoning = reasoning.requireJavaScriptNullableString("reasoning"),
        plan = plan.requireJavaScriptNullableString("plan"),
        shellCommand = shellCommand.requireJavaScriptNullableString("shellCommand"),
        exitCode = requireJavaScriptNullableInteger(exitCode, "exitCode"),
        capabilities = run {
            requireJavaScriptArray(capabilities, "capabilities")
            List(capabilities.size) { index ->
                requireOwnJavaScriptArrayIndex(capabilities, index, "capabilities")
                capabilities[index].toAgentCapability("capabilities[$index]")
            }.toSet()
        },
        invocations = run {
            requireJavaScriptArray(invocations, "invocations")
            List(invocations.size) { index ->
                requireOwnJavaScriptArrayIndex(invocations, index, "invocations")
                invocations[index].toCoreInvocation(index)
            }
        },
    ).project()
}

private fun AgentInvocation.toCoreInvocation(index: Int): CoreInvocation {
    val invocation: Any? = this
    return when (invocation) {
        is AgentSkillInvocation -> CoreInvocation.Skill(
            name = invocation.name.requireJavaScriptString("invocations[$index].name"),
            path = invocation.path.requireJavaScriptString("invocations[$index].path"),
        )
        is AgentPluginInvocation -> CoreInvocation.Plugin(
            name = invocation.name.requireJavaScriptString("invocations[$index].name"),
            uri = invocation.uri.requireJavaScriptString("invocations[$index].uri"),
        )
        else -> throw IllegalArgumentException(
            "invocations[$index] must be an AgentSkillInvocation or AgentPluginInvocation",
        )
    }
}

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
    collaborationMode = collaborationMode.name.lowercase(),
    reasoning = reasoning,
    plan = plan,
    shellCommand = shellCommand,
    exitCode = exitCode,
    capabilities = capabilities.map(CoreCapability::id).toTypedArray(),
    invocations = invocations.map(CoreInvocation::project).toTypedArray(),
)

private fun CoreInvocation.project(): AgentInvocation = when (this) {
    is CoreInvocation.Skill -> AgentSkillInvocation(name, path)
    is CoreInvocation.Plugin -> AgentPluginInvocation(name, uri)
}

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
        conversation = state.conversation?.project(),
        title = state.conversation?.summary?.title,
        messages = currentMessages.value.map(CoreMessage::project).toTypedArray(),
        turnProgress = state.turnProgress.takeUnless { it == CoreTurnProgress() }?.project(),
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
