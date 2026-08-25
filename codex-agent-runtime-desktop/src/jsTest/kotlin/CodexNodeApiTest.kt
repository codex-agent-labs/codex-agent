import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceStore
import io.github.codex_agent_labs.codexmobile.agent.PreparedCodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexJsonLine
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntimeEvent
import kotlin.js.jsTypeOf
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.yield
import kotlinx.coroutines.await
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexNodeApiTest {
    @Test
    fun projectsCanonicalLifecycleIdentityFailureAndOwnership() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val hostStates = mutableListOf<String>()
        val hostObservation = host.observeState { hostStates += it.status }

        AgentApprovalPreset.entries.forEach { preset ->
            assertEquals(preset.displayName, codexApprovalPresetDisplayName(preset.name.lowercase()))
        }
        val invalidPreset = runCatching { codexApprovalPresetDisplayName("sometimes") }.exceptionOrNull()
        assertEquals("Unknown approval preset: sometimes", invalidPreset?.message)

        val sourcePluginNames = arrayOf("Plugin one", "Plugin two")
        val localConnector = AgentConnector(
            id = "connector-local",
            name = "Local connector",
            pluginNames = sourcePluginNames,
        )
        sourcePluginNames[0] = "Changed"
        assertEquals("", localConnector.description)
        assertNull(localConnector.installUrl)
        assertFalse(localConnector.isAccessible)
        assertTrue(localConnector.isEnabled)
        assertEquals(listOf("Plugin one", "Plugin two"), localConnector.pluginNames.toList())
        assertTrue(isFrozen(localConnector))
        assertTrue(isFrozen(localConnector.pluginNames))
        assertEquals(0, enumerablePropertyCount(localConnector))
        val invalidConnector = runCatching {
            AgentConnector(js("({})").unsafeCast<String>(), "Invalid")
        }.exceptionOrNull()
        assertEquals("id must be a string", invalidConnector?.message)

        val sourceEfforts = arrayOf("low", "medium")
        val sourceTiers = arrayOf(AgentServiceTier("fast", "Fast", "Faster responses"))
        val localModel = AgentModel(
            id = "model-local",
            displayName = "Local model",
            description = "Local description",
            supportedEfforts = sourceEfforts,
            defaultEffort = "medium",
            isDefault = true,
            serviceTiers = sourceTiers,
            defaultServiceTier = "fast",
        )
        sourceEfforts[0] = "changed"
        sourceTiers[0] = AgentServiceTier("changed", "Changed", "Changed")
        assertEquals("model-local", localModel.id)
        assertEquals("Local model", localModel.displayName)
        assertEquals("Local description", localModel.description)
        assertEquals(listOf("low", "medium"), localModel.supportedEfforts.toList())
        assertEquals("medium", localModel.defaultEffort)
        assertTrue(localModel.isDefault)
        assertEquals(listOf("fast"), localModel.serviceTiers.map(AgentServiceTier::id))
        assertEquals("Fast", localModel.serviceTiers.single().name)
        assertEquals("Faster responses", localModel.serviceTiers.single().description)
        assertEquals("fast", localModel.defaultServiceTier)
        assertTrue(isFrozen(localModel))
        assertTrue(isFrozen(localModel.supportedEfforts))
        assertTrue(isFrozen(localModel.serviceTiers))
        assertTrue(isFrozen(localModel.serviceTiers.single()))
        assertEquals(0, enumerablePropertyCount(localModel))
        assertEquals(0, enumerablePropertyCount(localModel.serviceTiers.single()))

        val sourceDependencies = arrayOf("git", "rg")
        val localSkill = AgentSkill(
            name = "review-skill",
            displayName = "Review skill",
            description = "Reviews a change",
            path = "/skills/review-skill/SKILL.md",
            scope = "repo",
            isEnabled = true,
            brandColor = "#123456",
            dependencies = sourceDependencies,
            canUninstall = true,
        )
        sourceDependencies[0] = "changed"
        assertEquals("review-skill", localSkill.name)
        assertEquals("Review skill", localSkill.displayName)
        assertEquals("Reviews a change", localSkill.description)
        assertEquals("/skills/review-skill/SKILL.md", localSkill.path)
        assertEquals("repo", localSkill.scope)
        assertTrue(localSkill.isEnabled)
        assertEquals("#123456", localSkill.brandColor)
        assertEquals(listOf("git", "rg"), localSkill.dependencies.toList())
        assertTrue(localSkill.canUninstall)
        assertEquals("workspace", localSkill.origin)
        assertTrue(isFrozen(localSkill))
        assertTrue(isFrozen(localSkill.dependencies))
        assertEquals(0, enumerablePropertyCount(localSkill))

        val sourceSkills = arrayOf(localSkill)
        val sourceErrors = arrayOf("warning")
        val localCatalog = AgentSkillCatalog(sourceSkills, sourceErrors)
        sourceSkills[0] = AgentSkill("changed", "Changed", "Changed", "/changed", "user", false)
        sourceErrors[0] = "changed"
        assertEquals(listOf("review-skill"), localCatalog.skills.map(AgentSkill::name))
        assertEquals(listOf("warning"), localCatalog.errors.toList())
        assertTrue(isFrozen(localCatalog))
        assertTrue(isFrozen(localCatalog.skills))
        assertTrue(isFrozen(localCatalog.errors))
        assertTrue(isFrozen(localCatalog.skills.single()))
        val localChunk = AgentSkillChunk(
            "content",
            javaScriptBigInt("7"),
            javaScriptBigInt("20"),
        )
        assertEquals("content", localChunk.content)
        assertEquals("7", localChunk.nextOffset?.toString())
        assertEquals("20", localChunk.totalBytes.toString())
        assertEquals("bigint", jsTypeOf(localChunk.totalBytes))
        assertTrue(isFrozen(localChunk))
        assertEquals(0, enumerablePropertyCount(localChunk))

        val invalidSkillScope = runCatching {
            AgentSkill("invalid", "Invalid", "Invalid", "/invalid", "temporary", true)
        }.exceptionOrNull()
        assertEquals("Unknown skill scope: temporary", invalidSkillScope?.message)
        val invalidSkillDependencies = runCatching {
            AgentSkill(
                "invalid",
                "Invalid",
                "Invalid",
                "/invalid",
                "user",
                true,
                dependencies = js("({ length: 0 })").unsafeCast<Array<String>>(),
            )
        }.exceptionOrNull()
        assertEquals("dependencies must be an array", invalidSkillDependencies?.message)

        val defaultModel = AgentModel("model-defaults", "Defaults", "", emptyArray(), "medium", false)
        assertTrue(defaultModel.serviceTiers.isEmpty())
        assertNull(defaultModel.defaultServiceTier)
        val invalidTier = runCatching {
            AgentServiceTier(js("({})").unsafeCast<String>(), "Invalid", "Invalid")
        }.exceptionOrNull()
        assertEquals("id must be a string", invalidTier?.message)
        val nonArrayEfforts = runCatching {
            AgentModel(
                "invalid",
                "Invalid",
                "Invalid",
                js("({})").unsafeCast<Array<String>>(),
                "medium",
                false,
            )
        }.exceptionOrNull()
        assertEquals("supportedEfforts must be an array", nonArrayEfforts?.message)
        val sparseEfforts = runCatching {
            AgentModel(
                "invalid",
                "Invalid",
                "Invalid",
                js("new Array(1)").unsafeCast<Array<String>>(),
                "medium",
                false,
            )
        }.exceptionOrNull()
        assertEquals("supportedEfforts must not contain sparse elements", sparseEfforts?.message)
        val hostileEffort = runCatching {
            AgentModel(
                "invalid",
                "Invalid",
                "Invalid",
                arrayOf(js("({})").unsafeCast<String>()),
                "medium",
                false,
            )
        }.exceptionOrNull()
        assertEquals("supportedEfforts[0] must be a string", hostileEffort?.message)
        val sparseTiers = runCatching {
            AgentModel(
                "invalid",
                "Invalid",
                "Invalid",
                emptyArray(),
                "medium",
                false,
                js("new Array(1)").unsafeCast<Array<AgentServiceTier>>(),
            )
        }.exceptionOrNull()
        assertEquals("serviceTiers must not contain sparse elements", sparseTiers?.message)

        val localSummary = AgentConversationSummary(
            conversationId = "thread-local",
            title = "Local title",
            updatedAtEpochSeconds = javaScriptBigInt("9007199254740993"),
        )
        assertEquals("thread-local", localSummary.conversationId)
        assertEquals("Local title", localSummary.title)
        assertEquals("9007199254740993", localSummary.updatedAtEpochSeconds.toString())
        assertEquals("bigint", jsTypeOf(localSummary.updatedAtEpochSeconds))
        assertTrue(isFrozen(localSummary))
        assertEquals(0, enumerablePropertyCount(localSummary))
        val blankSummaryId = runCatching {
            AgentConversationSummary("  ", "Invalid", javaScriptBigInt("1"))
        }.exceptionOrNull()
        assertEquals("Conversation ID must not be blank", blankSummaryId?.message)
        val invalidSummaryId = runCatching {
            AgentConversationSummary(
                js("({})").unsafeCast<String>(),
                "Invalid",
                javaScriptBigInt("1"),
            )
        }.exceptionOrNull()
        assertEquals("conversationId must be a string", invalidSummaryId?.message)
        val invalidSummaryTitle = runCatching {
            AgentConversationSummary(
                "thread-invalid",
                js("BigInt(1)").unsafeCast<String>(),
                javaScriptBigInt("1"),
            )
        }.exceptionOrNull()
        assertEquals("title must be a string", invalidSummaryTitle?.message)
        val numericSummaryTimestamp = runCatching {
            AgentConversationSummary("thread-invalid", "Invalid", js("1").unsafeCast<Long>())
        }.exceptionOrNull()
        assertEquals("updatedAtEpochSeconds must be a bigint", numericSummaryTimestamp?.message)
        val stringSummaryTimestamp = runCatching {
            AgentConversationSummary("thread-invalid", "Invalid", js("'1'").unsafeCast<Long>())
        }.exceptionOrNull()
        assertEquals("updatedAtEpochSeconds must be a bigint", stringSummaryTimestamp?.message)

        yield()
        assertEquals(listOf("new"), hostStates)
        assertTrue(isFrozen(host.state))
        assertEquals(0, enumerablePropertyCount(host))
        host.start().await()
        yield()
        assertEquals("ready", host.state.status)
        assertEquals("ready", hostStates.last())

        val agent = assertIs<CodexAgent>(host.agent)
        assertSame(agent, host.state.agent)
        val unavailableConnectors = agent.connectors
        assertSame(unavailableConnectors, agent.connectors)
        assertFalse(unavailableConnectors.isAvailable)
        assertEquals(0, enumerablePropertyCount(unavailableConnectors))
        val unsupportedConnectors = runCatching { unavailableConnectors.list().await() }.exceptionOrNull()
        val unsupportedConnectorsError = assertIs<CodexError>(unsupportedConnectors)
        assertEquals("unsupported_feature", unsupportedConnectorsError.code)
        assertFalse(unsupportedConnectorsError.recoverable)
        assertTrue(runtime.appListRequests.isEmpty())
        val active = mutableListOf<CodexConversation?>()
        val activeObservation = agent.observeActiveConversation { active += it }
        awaitCondition { active.isNotEmpty() }
        assertNull(active.single())

        val conversation = agent.openConversation().await()
        awaitCondition { active.lastOrNull() != null }
        val defaultOpen = checkNotNull(runtime.threadStartParams)
        assertEquals("on-request", defaultOpen["approvalPolicy"]?.jsonPrimitive?.content)
        assertEquals("auto_review", defaultOpen["approvalsReviewer"]?.jsonPrimitive?.content)
        assertEquals("/workspace", defaultOpen["cwd"]?.jsonPrimitive?.content)
        assertNull(defaultOpen["serviceTier"])
        assertSame(conversation, agent.activeConversation)
        assertSame(conversation, active.last())
        assertEquals("ready", conversation.state.status)
        assertEquals("thread-js", conversation.state.conversationId)
        assertTrue(conversation.state.messages.isEmpty())
        assertNull(conversation.state.turnProgress)
        assertTrue(conversation.state.canStartTurn)
        assertTrue(conversation.state.canReload)
        assertFalse(conversation.state.canCancelTurn)
        assertFalse(conversation.state.canRunShellCommand)
        assertFalse(conversation.state.isTurnActive)
        assertTrue(isFrozen(conversation.state))
        assertTrue(isFrozen(conversation.state.messages))
        assertEquals(0, enumerablePropertyCount(conversation))

        val conversationStates = mutableListOf<CodexConversationState>()
        val conversationObservation = conversation.observeState { conversationStates += it }
        awaitCondition { conversationStates.isNotEmpty() }
        assertEquals(listOf("ready"), conversationStates.map(CodexConversationState::status))

        conversation.send("hello").await()
        awaitCondition { conversation.state.status == "running_turn" }
        val activeState = conversation.state
        assertEquals(listOf("hello"), activeState.messages.map(CodexMessage::text))
        assertNull(activeState.turnProgress)
        assertFalse(activeState.canStartTurn)
        assertFalse(activeState.canReload)
        assertTrue(activeState.canCancelTurn)
        assertFalse(activeState.canRunShellCommand)
        assertTrue(activeState.isTurnActive)

        runtime.emitAgentMessageDelta("working")
        awaitCondition {
            conversation.state.turnProgress?.text == "working" &&
                conversationStates.any { it.turnProgress?.text == "working" }
        }
        val progressState = conversation.state
        assertEquals("working", progressState.turnProgress?.text)
        val textProgress = checkNotNull(progressState.turnProgress)
        assertNull(textProgress.planProgress)
        assertTrue(textProgress.hookActivities.isEmpty())
        assertTrue(isFrozen(textProgress))
        assertTrue(isFrozen(textProgress.hookActivities))

        runtime.emitPlanUpdated()
        awaitCondition {
            conversation.state.turnProgress?.planProgress?.steps?.singleOrNull()?.status == "in_progress"
        }
        val planProgress = checkNotNull(checkNotNull(conversation.state.turnProgress).planProgress)
        assertEquals("Executing the plan", planProgress.explanation)
        assertEquals(listOf("Inspect runtime"), planProgress.steps.map(AgentPlanStep::text))
        assertEquals(listOf("in_progress"), planProgress.steps.map(AgentPlanStep::status))
        assertTrue(isFrozen(planProgress))
        assertTrue(isFrozen(planProgress.steps))
        planProgress.steps.forEach { assertTrue(isFrozen(it)) }

        runtime.emitHookStarted()
        awaitCondition {
            conversation.state.turnProgress?.hookActivities?.singleOrNull()?.status == "running"
        }
        val runningHook = checkNotNull(conversation.state.turnProgress).hookActivities.single()
        assertEquals("hook-js", runningHook.id)
        assertEquals("STOP", runningHook.eventName)
        assertEquals("COMMAND", runningHook.handlerType)
        assertEquals("Running hook", runningHook.statusMessage)
        assertEquals(listOf("started"), runningHook.details.toList())
        assertTrue(isFrozen(runningHook))
        assertTrue(isFrozen(runningHook.details))

        runtime.emitHookCompleted()
        awaitCondition {
            conversation.state.turnProgress?.hookActivities?.singleOrNull()?.status == "completed"
        }
        val completedHook = checkNotNull(conversation.state.turnProgress).hookActivities.single()
        assertEquals("Complete", completedHook.statusMessage)
        assertEquals(listOf("finished", "detached"), completedHook.details.toList())
        assertEquals("running", runningHook.status)
        assertEquals(listOf("started"), runningHook.details.toList())
        assertTrue(isFrozen(completedHook))
        assertTrue(isFrozen(completedHook.details))

        runtime.completeTurn()
        awaitCondition { conversation.state.status == "ready" && conversation.state.messages.size == 2 }
        awaitCondition { conversationStates.any { it.messages.size == 2 && !it.isTurnActive } }
        val messageState = conversation.state
        val messages = messageState.messages
        assertEquals(listOf("user-1", "assistant-1"), messages.map(CodexMessage::id))
        assertEquals(listOf("hello", "world"), messages.map(CodexMessage::text))
        assertEquals(listOf("user", "assistant"), messages.map(CodexMessage::role))
        assertNull(messageState.turnProgress)
        assertTrue(messageState.canStartTurn)
        assertTrue(messageState.canReload)
        assertFalse(messageState.canCancelTurn)
        assertFalse(messageState.canRunShellCommand)
        assertFalse(messageState.isTurnActive)
        assertTrue(isFrozen(messageState))
        assertTrue(isFrozen(messages))
        messages.forEach { assertTrue(isFrozen(it)) }
        assertTrue(conversationStates.any { it.isTurnActive && it.canCancelTurn })
        assertTrue(conversationStates.any { it.turnProgress?.text == "working" })
        assertTrue(conversationStates.any { it.messages.size == 2 && !it.isTurnActive })
        conversationStates.forEach {
            assertTrue(isFrozen(it))
            assertTrue(isFrozen(it.messages))
            it.turnProgress?.let { progress ->
                assertTrue(isFrozen(progress))
                assertTrue(isFrozen(progress.hookActivities))
                progress.hookActivities.forEach { activity ->
                    assertTrue(isFrozen(activity))
                    assertTrue(isFrozen(activity.details))
                }
                progress.planProgress?.let { plan ->
                    assertTrue(isFrozen(plan))
                    assertTrue(isFrozen(plan.steps))
                    plan.steps.forEach { step -> assertTrue(isFrozen(step)) }
                }
            }
        }

        val failure = runCatching { conversation.runShellCommand("pwd").await() }.exceptionOrNull()
        val codexError = assertIs<CodexError>(failure)
        assertEquals("CodexError", codexError.asDynamic().name as String)
        assertEquals("unsupported_feature", codexError.code)
        assertFalse(codexError.recoverable)

        val blankName = runCatching { agent.rename("thread-history", "  ").await() }.exceptionOrNull()
        assertEquals("Conversation name must not be blank", blankName?.message)
        val blankId = runCatching { agent.delete("  ").await() }.exceptionOrNull()
        assertEquals("Conversation ID must not be blank", blankId?.message)
        assertNull(runtime.renamedConversationId)
        assertNull(runtime.deletedConversationId)

        agent.rename("thread-history", "  Useful name  ").await()
        assertEquals("thread-history", runtime.renamedConversationId)
        assertEquals("Useful name", runtime.renamedConversationName)

        runtime.failNextRename = true
        val renameFailure = runCatching { agent.rename("thread-history", "Rejected").await() }.exceptionOrNull()
        val renameError = assertIs<CodexError>(renameFailure)
        assertEquals("conversation_rename_failed", renameError.code)
        assertEquals("rename denied", renameError.message)
        assertTrue(renameError.recoverable)

        val deleteEntered = CompletableDeferred<Unit>()
        val deleteRelease = CompletableDeferred<Unit>()
        runtime.deleteEntered = deleteEntered
        runtime.deleteRelease = deleteRelease
        val deletion = agent.delete("thread-js")
        try {
            deleteEntered.await()
            assertEquals("closed", conversation.state.status)
            assertNull(agent.activeConversation)
            assertEquals("thread-js", runtime.deletedConversationId)
        } finally {
            deleteRelease.complete(Unit)
        }
        deletion.await()
        conversation.dispose().await()
        awaitCondition { conversationObservation.isClosed }
        assertEquals("closed", conversationStates.last().status)
        assertTrue(conversationObservation.isClosed)
        assertNull(agent.activeConversation)

        host.close().await()
        host.close().await()
        awaitCondition { hostObservation.isClosed && activeObservation.isClosed }
        assertEquals("closed", hostStates.last())
        assertTrue(hostObservation.isClosed)
        assertTrue(activeObservation.isClosed)
        assertTrue(runtime.closed)

        val skillFixture = createSkillTestFixture()
        val shellRuntime = ApiTestRuntime().apply {
            skillWorkspacePath = skillFixture.workspacePath
            skillManifestPath = skillFixture.sourceManifestPath
        }
        val shellHost = wrapCodexHost(CoreHost(
            ApiTestPlatform(shellRuntime, features = setOf(
                CodexRuntimeFeature.SHELL_COMMANDS,
                CodexRuntimeFeature.CONNECTORS,
                CodexRuntimeFeature.SKILLS,
            ), workspacePath = skillFixture.workspacePath),
            CodexClientInfo("node_test", "Node Test", "test"),
        ))
        try {
            shellHost.start().await()
            val shellAgent = assertIs<CodexAgent>(shellHost.agent)
            val connectors = shellAgent.connectors
            assertSame(connectors, shellAgent.connectors)
            assertTrue(connectors.isAvailable)
            assertEquals(0, enumerablePropertyCount(connectors))
            val models = shellAgent.models
            assertSame(models, shellAgent.models)
            assertEquals(0, enumerablePropertyCount(models))
            val skills = shellAgent.skills
            assertSame(skills, shellAgent.skills)
            assertTrue(skills.isAvailable)
            assertEquals(0, enumerablePropertyCount(skills))

            val controller = js("new AbortController()")
            controller.abort()
            val abortedList = runCatching {
                connectors.list(signal = controller.signal.unsafeCast<AbortSignal>()).await()
            }.exceptionOrNull()
            assertEquals("AbortError", abortedList?.asDynamic()?.name as String)
            assertTrue(shellRuntime.appListRequests.isEmpty())

            val abortedConversationList = runCatching {
                shellAgent.listConversations(controller.signal.unsafeCast<AbortSignal>()).await()
            }.exceptionOrNull()
            assertEquals("AbortError", abortedConversationList?.asDynamic()?.name as String)
            assertTrue(shellRuntime.threadListRequests.isEmpty())

            listOf(
                runCatching {
                    skills.list(signal = controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    skills.read(
                        skillFixture.sourceManifestPath,
                        signal = controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
                runCatching {
                    skills.install(
                        skillFixture.sourceDirectory,
                        "workspace",
                        controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
                runCatching {
                    skills.uninstall(localSkill, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
            ).forEach { aborted ->
                assertEquals("AbortError", aborted?.asDynamic()?.name as String)
            }
            assertTrue(shellRuntime.skillListRequests.isEmpty())

            listOf(
                runCatching {
                    models.list(controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    models.resolve(signal = controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    models.resolveEffort(
                        localModel,
                        signal = controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
                runCatching {
                    models.resolveServiceTier(
                        localModel,
                        signal = controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
            ).forEach { aborted ->
                assertEquals("AbortError", aborted?.asDynamic()?.name as String)
            }
            assertTrue(shellRuntime.modelListRequests.isEmpty())
            assertTrue(shellRuntime.configReadRequests.isEmpty())

            val skillCatalog = skills.list(forceReload = true).await()
            assertEquals(listOf("fixture-skill"), skillCatalog.skills.map(AgentSkill::name))
            assertEquals(
                listOf("${skillFixture.sourceManifestPath}.warning: ignored entry"),
                skillCatalog.errors.toList(),
            )
            val listedSkill = skillCatalog.skills.single()
            assertEquals("Fixture skill", listedSkill.displayName)
            assertEquals("Projected description", listedSkill.description)
            assertEquals(skillFixture.sourceManifestPath, listedSkill.path)
            assertEquals("repo", listedSkill.scope)
            assertTrue(listedSkill.isEnabled)
            assertEquals("#abcdef", listedSkill.brandColor)
            assertEquals(listOf("git", "rg"), listedSkill.dependencies.toList())
            assertFalse(listedSkill.canUninstall)
            assertEquals("workspace", listedSkill.origin)
            assertTrue(isFrozen(skillCatalog))
            assertTrue(isFrozen(skillCatalog.skills))
            assertTrue(isFrozen(skillCatalog.errors))
            assertTrue(isFrozen(listedSkill))
            assertTrue(isFrozen(listedSkill.dependencies))
            assertEquals(1, shellRuntime.skillListRequests.size)
            val firstSkillList = shellRuntime.skillListRequests.single()
            assertEquals(
                listOf(skillFixture.workspacePath),
                firstSkillList["cwds"]?.jsonArray?.map { it.jsonPrimitive.content },
            )
            assertEquals("true", firstSkillList["forceReload"]?.jsonPrimitive?.content)

            val skillChunk = skills.read(skillFixture.sourceManifestPath).await()
            assertEquals(SKILL_FIXTURE_CONTENT, skillChunk.content)
            assertNull(skillChunk.nextOffset)
            assertEquals(SKILL_FIXTURE_CONTENT.encodeToByteArray().size.toString(), skillChunk.totalBytes.toString())
            assertEquals("bigint", jsTypeOf(skillChunk.totalBytes))
            assertTrue(isFrozen(skillChunk))

            val requestsBeforeInvalidSkillInputs = shellRuntime.requestMethods.size
            val invalidSkillPath = runCatching { skills.read("relative/SKILL.md").await() }.exceptionOrNull()
            assertEquals("Skill path must be absolute", invalidSkillPath?.message)
            val invalidSkillOffset = runCatching {
                skills.read(skillFixture.sourceManifestPath, javaScriptBigInt("-1")).await()
            }.exceptionOrNull()
            assertEquals("Offset must not be negative", invalidSkillOffset?.message)
            val invalidInstallationScope = runCatching {
                skills.install(skillFixture.sourceDirectory, "temporary").await()
            }.exceptionOrNull()
            assertEquals("Unknown installation scope: temporary", invalidInstallationScope?.message)
            assertEquals(requestsBeforeInvalidSkillInputs, shellRuntime.requestMethods.size)

            val unownedFailure = assertIs<CodexError>(
                runCatching { skills.uninstall(listedSkill).await() }.exceptionOrNull(),
            )
            assertEquals("skill_uninstall_failed", unownedFailure.code)
            assertEquals("Could not uninstall skill", unownedFailure.message)
            assertTrue(unownedFailure.recoverable)
            assertEquals(requestsBeforeInvalidSkillInputs, shellRuntime.requestMethods.size)

            shellRuntime.skillManifestPath = skillFixture.installedManifestPath
            val installedSkill = skills.install(skillFixture.sourceDirectory, "workspace").await()
            assertEquals(skillFixture.installedManifestPath, installedSkill.path)
            assertTrue(installedSkill.canUninstall)
            assertEquals("workspace", installedSkill.origin)
            assertTrue(isFrozen(installedSkill))
            assertTrue(nodeFileExists(skillFixture.installedManifestPath))
            assertEquals(2, shellRuntime.skillListRequests.size)

            shellRuntime.skillManifestPath = null
            skills.uninstall(installedSkill).await()
            assertFalse(nodeFileExists(skillFixture.installedManifestPath))
            assertEquals(3, shellRuntime.skillListRequests.size)

            shellRuntime.failNextSkillList = true
            val skillListFailure = assertIs<CodexError>(
                runCatching { skills.list().await() }.exceptionOrNull(),
            )
            assertEquals("skill_list_failed", skillListFailure.code)
            assertEquals("skill list denied", skillListFailure.message)
            assertTrue(skillListFailure.recoverable)
            assertEquals(4, shellRuntime.skillListRequests.size)

            val listedModels = models.list().await()
            assertEquals(
                listOf("model-first", "model-default", "model-preferred"),
                listedModels.map(AgentModel::id),
            )
            assertEquals(2, shellRuntime.modelListRequests.size)
            assertNull(shellRuntime.modelListRequests[0]["cursor"])
            assertNull(shellRuntime.modelListRequests[0]["includeHidden"])
            assertNull(shellRuntime.modelListRequests[0]["limit"])
            assertEquals(
                "models-page-2",
                shellRuntime.modelListRequests[1]["cursor"]?.jsonPrimitive?.content,
            )
            val preferredModel = listedModels.last()
            assertEquals("Preferred model", preferredModel.displayName)
            assertEquals("Preferred model description", preferredModel.description)
            assertEquals(listOf("low", "medium"), preferredModel.supportedEfforts.toList())
            assertEquals("medium", preferredModel.defaultEffort)
            assertFalse(preferredModel.isDefault)
            assertEquals(listOf("fast", "free"), preferredModel.serviceTiers.map(AgentServiceTier::id))
            assertEquals("Fast", preferredModel.serviceTiers[0].name)
            assertEquals("Faster responses", preferredModel.serviceTiers[0].description)
            assertEquals("free", preferredModel.defaultServiceTier)
            assertTrue(isFrozen(listedModels))
            listedModels.forEach { model ->
                assertTrue(isFrozen(model))
                assertTrue(isFrozen(model.supportedEfforts))
                assertTrue(isFrozen(model.serviceTiers))
                model.serviceTiers.forEach { assertTrue(isFrozen(it)) }
            }

            assertEquals("model-preferred", models.resolve().await().id)
            assertEquals("model-default", models.resolve("default").await().id)
            assertEquals("model-first", models.resolve("first").await().id)
            assertEquals("low", models.resolveEffort(preferredModel).await())
            assertEquals("medium", models.resolveEffort(preferredModel, "default").await())
            assertEquals("low", models.resolveEffort(preferredModel, "first").await())
            assertEquals("fast", models.resolveServiceTier(preferredModel).await()?.id)
            assertEquals("free", models.resolveServiceTier(preferredModel, "default").await()?.id)
            assertEquals("fast", models.resolveServiceTier(preferredModel, "first").await()?.id)
            assertNull(models.resolveServiceTier(listedModels.first(), "first").await())
            assertEquals(3, shellRuntime.configReadRequests.size)
            assertTrue(shellRuntime.configReadRequests.all { request ->
                request["cwd"]?.jsonPrimitive?.content == skillFixture.workspacePath &&
                    request["includeLayers"] == null
            })

            shellRuntime.modelPreference = "missing"
            shellRuntime.effortPreference = "missing"
            shellRuntime.serviceTierPreference = "missing"
            assertEquals("model-default", models.resolve().await().id)
            assertEquals("medium", models.resolveEffort(preferredModel).await())
            assertEquals("free", models.resolveServiceTier(preferredModel).await()?.id)
            assertEquals(6, shellRuntime.configReadRequests.size)
            shellRuntime.modelPreference = "model-preferred"
            shellRuntime.effortPreference = "low"
            shellRuntime.serviceTierPreference = "fast"

            val requestsBeforeInvalidResolution = shellRuntime.requestMethods.size
            val invalidResolution = runCatching { models.resolve("sometimes").await() }.exceptionOrNull()
            assertEquals("Unknown agent resolution: sometimes", invalidResolution?.message)
            val hostileResolution = runCatching {
                models.resolve(js("({})").unsafeCast<String>()).await()
            }.exceptionOrNull()
            assertEquals("resolution must be a string", hostileResolution?.message)
            assertEquals(requestsBeforeInvalidResolution, shellRuntime.requestMethods.size)

            shellRuntime.failNextModelList = true
            val modelListFailure = runCatching { models.list().await() }.exceptionOrNull()
            val modelListError = assertIs<CodexError>(modelListFailure)
            assertEquals("model_list_failed", modelListError.code)
            assertEquals("model list denied", modelListError.message)
            assertTrue(modelListError.recoverable)

            shellRuntime.failNextConfigRead = true
            val preferenceFailure = runCatching { models.resolveEffort(preferredModel).await() }.exceptionOrNull()
            val preferenceError = assertIs<CodexError>(preferenceFailure)
            assertEquals("model_preferences_failed", preferenceError.code)
            assertEquals("model preferences denied", preferenceError.message)
            assertTrue(preferenceError.recoverable)
            assertEquals(7, shellRuntime.configReadRequests.size)

            val configReadsBeforeEmptyCatalog = shellRuntime.configReadRequests.size
            shellRuntime.emptyNextModelList = true
            val emptyCatalog = runCatching { models.resolve().await() }.exceptionOrNull()
            assertEquals("No Codex models are available", emptyCatalog?.message)
            assertEquals(configReadsBeforeEmptyCatalog, shellRuntime.configReadRequests.size)

            val conversationSummaries = shellAgent.listConversations().await()
            assertEquals(
                listOf("thread-recent", "thread-older"),
                conversationSummaries.map(AgentConversationSummary::conversationId),
            )
            assertEquals(
                listOf("Recent title", "Older preview"),
                conversationSummaries.map(AgentConversationSummary::title),
            )
            assertEquals(
                listOf("9007199254740993", "7"),
                conversationSummaries.map { it.updatedAtEpochSeconds.toString() },
            )
            assertEquals("bigint", jsTypeOf(conversationSummaries[0].updatedAtEpochSeconds))
            assertEquals(2, shellRuntime.threadListRequests.size)
            val firstConversationListRequest = shellRuntime.threadListRequests[0]
            val secondConversationListRequest = shellRuntime.threadListRequests[1]
            assertNull(firstConversationListRequest["cursor"])
            assertEquals("updated_at", firstConversationListRequest["sortKey"]?.jsonPrimitive?.content)
            assertEquals("desc", firstConversationListRequest["sortDirection"]?.jsonPrimitive?.content)
            assertEquals(
                "history-page-2",
                secondConversationListRequest["cursor"]?.jsonPrimitive?.content,
            )
            assertEquals("updated_at", secondConversationListRequest["sortKey"]?.jsonPrimitive?.content)
            assertEquals("desc", secondConversationListRequest["sortDirection"]?.jsonPrimitive?.content)
            assertTrue(isFrozen(conversationSummaries))
            conversationSummaries.forEach {
                assertTrue(isFrozen(it))
                assertEquals(0, enumerablePropertyCount(it))
            }

            shellRuntime.failNextThreadList = true
            val conversationListFailure = runCatching {
                shellAgent.listConversations().await()
            }.exceptionOrNull()
            val conversationListError = assertIs<CodexError>(conversationListFailure)
            assertEquals("conversation_list_failed", conversationListError.code)
            assertEquals("conversation list denied", conversationListError.message)
            assertTrue(conversationListError.recoverable)
            assertEquals(3, shellRuntime.threadListRequests.size)

            val shellConversation = shellAgent.openConversation().await()
            val listedConnectors = connectors.list(forceReload = true).await()
            assertEquals(listOf("connector-custom", "connector-default"), listedConnectors.map(AgentConnector::id))
            assertEquals(2, shellRuntime.appListRequests.size)
            val firstListRequest = shellRuntime.appListRequests[0]
            val secondListRequest = shellRuntime.appListRequests[1]
            assertNull(firstListRequest["cursor"])
            assertEquals("true", firstListRequest["forceRefetch"]?.jsonPrimitive?.content)
            assertEquals("thread-js", firstListRequest["threadId"]?.jsonPrimitive?.content)
            assertEquals("page-2", secondListRequest["cursor"]?.jsonPrimitive?.content)
            assertEquals("true", secondListRequest["forceRefetch"]?.jsonPrimitive?.content)
            assertEquals("thread-js", secondListRequest["threadId"]?.jsonPrimitive?.content)
            val customConnector = listedConnectors[0]
            assertEquals("Custom connector", customConnector.name)
            assertEquals("Custom description", customConnector.description)
            assertEquals("https://example.com/install", customConnector.installUrl)
            assertTrue(customConnector.isAccessible)
            assertFalse(customConnector.isEnabled)
            assertEquals(listOf("Plugin one", "Plugin two"), customConnector.pluginNames.toList())
            val defaultConnector = listedConnectors[1]
            assertEquals("Default connector", defaultConnector.name)
            assertEquals("", defaultConnector.description)
            assertNull(defaultConnector.installUrl)
            assertFalse(defaultConnector.isAccessible)
            assertTrue(defaultConnector.isEnabled)
            assertTrue(defaultConnector.pluginNames.isEmpty())
            assertTrue(isFrozen(listedConnectors))
            listedConnectors.forEach { connector ->
                assertTrue(isFrozen(connector))
                assertTrue(isFrozen(connector.pluginNames))
            }

            shellRuntime.failNextAppList = true
            val listFailure = runCatching { connectors.list().await() }.exceptionOrNull()
            val listError = assertIs<CodexError>(listFailure)
            assertEquals("connector_list_failed", listError.code)
            assertEquals("connector list denied", listError.message)
            assertTrue(listError.recoverable)
            assertEquals(3, shellRuntime.appListRequests.size)

            val shellAvailability = mutableListOf<Boolean>()
            shellConversation.observeState { shellAvailability += it.canRunShellCommand }
            awaitCondition { shellAvailability.lastOrNull() == true }
            assertTrue(shellConversation.state.canRunShellCommand)

            shellConversation.send("hello").await()
            awaitCondition {
                !shellConversation.state.canRunShellCommand && shellAvailability.lastOrNull() == false
            }
            shellRuntime.completeTurn()
            awaitCondition {
                shellConversation.state.status == "ready" && shellConversation.state.canRunShellCommand &&
                    shellAvailability.lastOrNull() == true
            }
            assertTrue(shellAvailability.first())
            assertTrue(false in shellAvailability)
            assertTrue(shellAvailability.last())

            val blankId = runCatching { shellAgent.openConversation("  ").await() }.exceptionOrNull()
            assertEquals("Conversation ID must not be blank", blankId?.message)
            assertNull(shellRuntime.threadResumeParams)

            val resumed = shellAgent.openConversation(
                conversationId = "thread-resumed",
                approvalPreset = "strict",
                serviceTier = "fast",
            ).await()
            val resumedOpen = checkNotNull(shellRuntime.threadResumeParams)
            assertEquals("thread-resumed", resumedOpen["threadId"]?.jsonPrimitive?.content)
            assertEquals("untrusted", resumedOpen["approvalPolicy"]?.jsonPrimitive?.content)
            assertEquals("user", resumedOpen["approvalsReviewer"]?.jsonPrimitive?.content)
            assertEquals("fast", resumedOpen["serviceTier"]?.jsonPrimitive?.content)
            assertEquals(skillFixture.workspacePath, resumedOpen["cwd"]?.jsonPrimitive?.content)
            assertEquals("thread-resumed", resumed.state.conversationId)
            assertEquals("fast", resumed.state.serviceTier)
            assertEquals("closed", shellConversation.state.status)
            shellHost.close().await()
            assertSame(connectors, shellAgent.connectors)
            assertSame(models, shellAgent.models)
            assertSame(skills, shellAgent.skills)
            val requestsBeforeClosedList = shellRuntime.appListRequests.size
            val conversationRequestsBeforeClosedList = shellRuntime.threadListRequests.size
            val modelRequestsBeforeClosedList = shellRuntime.modelListRequests.size
            val skillRequestsBeforeClosedList = shellRuntime.skillListRequests.size
            val closedList = runCatching { connectors.list().await() }.exceptionOrNull()
            assertEquals("IllegalStateException", closedList?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedList.message)
            assertEquals(requestsBeforeClosedList, shellRuntime.appListRequests.size)
            val closedConversationList = runCatching { shellAgent.listConversations().await() }.exceptionOrNull()
            assertEquals("IllegalStateException", closedConversationList?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedConversationList.message)
            assertEquals(conversationRequestsBeforeClosedList, shellRuntime.threadListRequests.size)
            val closedModelList = runCatching { models.list().await() }.exceptionOrNull()
            assertEquals("IllegalStateException", closedModelList?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedModelList.message)
            assertEquals(modelRequestsBeforeClosedList, shellRuntime.modelListRequests.size)
            listOf(
                runCatching { skills.list().await() }.exceptionOrNull(),
                runCatching { skills.read(skillFixture.sourceManifestPath).await() }.exceptionOrNull(),
                runCatching { skills.install(skillFixture.sourceDirectory, "workspace").await() }.exceptionOrNull(),
                runCatching { skills.uninstall(listedSkill).await() }.exceptionOrNull(),
            ).forEach { closedSkillOperation ->
                assertEquals("IllegalStateException", closedSkillOperation?.asDynamic()?.name as String)
                assertEquals("Codex agent is closed", closedSkillOperation.message)
            }
            assertEquals(skillRequestsBeforeClosedList, shellRuntime.skillListRequests.size)
            val requestsBeforePureResolution = shellRuntime.requestMethods.size
            assertEquals("medium", models.resolveEffort(preferredModel, "default").await())
            assertEquals("low", models.resolveEffort(preferredModel, "first").await())
            assertEquals("free", models.resolveServiceTier(preferredModel, "default").await()?.id)
            assertEquals("fast", models.resolveServiceTier(preferredModel, "first").await()?.id)
            assertEquals(requestsBeforePureResolution, shellRuntime.requestMethods.size)
        } finally {
            shellHost.close().await()
            deleteSkillTestFixture(skillFixture.root)
        }
    }

    @Test
    fun abortsBeforeStartingAndStopsDisposedObservation() = runTest {
        val runtime = ApiTestRuntime()
        val platform = ApiTestPlatform(runtime)
        val core = CoreHost(platform, CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val values = mutableListOf<String>()
        val observation = host.observeState { values += it.status }
        yield()
        observation.dispose()
        observation.dispose()

        val controller = js("new AbortController()")
        controller.abort()
        val error = runCatching {
            host.start(controller.signal.unsafeCast<AbortSignal>()).await()
        }.exceptionOrNull()
        assertEquals("AbortError", error?.asDynamic()?.name as String)
        assertEquals("new", host.state.status)
        assertEquals(listOf("new"), values)
        assertTrue(observation.isClosed)
        assertFalse(runtime.started)

        val blankPath = runCatching { host.selectWorkspace("  ").await() }.exceptionOrNull()
        assertEquals("Workspace path must not be blank", blankPath?.message)
        assertNull(platform.selectedWorkspacePath)
        host.selectWorkspace("/selected workspace").await()
        assertEquals("/selected workspace", platform.selectedWorkspacePath)
        assertEquals("/selected workspace", host.state.workspace?.path)
        assertEquals("ready", host.state.status)
        host.close().await()
        yield()
        assertEquals(listOf("new"), values)
    }

    @Test
    fun mapsCanonicalCancellationAndRemovesAbortListener() = runTest {
        val restoreEntered = CompletableDeferred<Unit>()
        val restoreRelease = CompletableDeferred<Unit>()
        val runtime = ApiTestRuntime()
        val core = CoreHost(
            ApiTestPlatform(runtime, restoreEntered, restoreRelease),
            CodexClientInfo("node_test", "Node Test", "test"),
        )
        val host = wrapCodexHost(core)
        val signal = CountingAbortSignal()

        val start = host.start(signal)
        restoreEntered.await()
        val close = host.close()
        restoreRelease.complete(Unit)

        val error = runCatching { start.await() }.exceptionOrNull()
        assertEquals("AbortError", error?.asDynamic()?.name as String)
        close.await()
        assertEquals("closed", host.state.status)
        assertEquals(1, signal.additions)
        assertEquals(1, signal.removals)
        assertFalse(runtime.started)
    }

    @Test
    fun isolatesListenerFailureWhileOtherObserversAndCleanupContinue() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val console = js("globalThis.console")
        val originalConsoleError = console.error
        val reported = mutableListOf<Throwable>()
        console.error = { error: Throwable -> reported += error }
        try {
            val failedObservation = host.observeState { error("listener failed") }
            val states = mutableListOf<String>()
            val healthyObservation = host.observeState { states += it.status }
            awaitCondition { failedObservation.isClosed && reported.size == 1 && states.isNotEmpty() }

            host.start().await()
            awaitCondition { states.lastOrNull() == "ready" }
            host.close().await()
            awaitCondition { healthyObservation.isClosed }

            assertEquals("new", states.first())
            assertTrue("ready" in states)
            assertEquals("closed", states.last())
            assertEquals("listener failed", reported.single().message)
            assertTrue(runtime.closed)
        } finally {
            console.error = originalConsoleError
            host.close().await()
        }
    }

    @Test
    fun projectsAuthenticationStateMethodsIdentityAndDisposal() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        host.start().await()
        val agent = assertIs<CodexAgent>(host.agent)
        val authentication = agent.authentication

        assertSame(authentication, agent.authentication)
        assertEquals(0, enumerablePropertyCount(authentication))
        assertEquals("signed_out", authentication.state.status)
        assertFalse(authentication.isAuthenticated)
        assertFalse(authentication.isAuthenticating)
        assertTrue(isFrozen(authentication.state))

        val states = mutableListOf<CodexAuthenticationState>()
        val authenticated = mutableListOf<Boolean>()
        val authenticating = mutableListOf<Boolean>()
        val stateObservation = authentication.observeState(states::add)
        val authenticatedObservation = authentication.observeAuthenticated(authenticated::add)
        val authenticatingObservation = authentication.observeAuthenticating(authenticating::add)
        val disposedStates = mutableListOf<String>()
        val disposedObservation = authentication.observeState { disposedStates += it.status }
        awaitCondition {
            states.isNotEmpty() && authenticated.isNotEmpty() &&
                authenticating.isNotEmpty() && disposedStates.isNotEmpty()
        }
        disposedObservation.dispose()

        authentication.authenticate("chatgpt_browser").await()
        awaitCondition {
            states.lastOrNull()?.pendingSignInUrl == "https://auth.openai.com/oauth?state=login-1" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        assertEquals("https://auth.openai.com/oauth?state=login-1", authentication.state.pendingSignInUrl)
        assertEquals("authenticating", states.last().status)
        assertTrue(authentication.isAuthenticating)

        authentication.cancel().await()
        awaitCondition {
            states.lastOrNull()?.failure?.code == "authentication_failed" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }
        assertEquals("signed_out", authentication.state.status)
        assertEquals("authentication_failed", authentication.state.failure?.code)
        assertEquals("signed_out", states.last().status)
        assertTrue(isFrozen(checkNotNull(authentication.state.failure)))
        assertEquals(1, runtime.cancelRequests)

        authentication.authenticate("chatgpt_device_code").await()
        awaitCondition {
            states.lastOrNull()?.deviceUserCode == "ABCD-EFGH" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        assertEquals("https://auth.openai.com/device", authentication.state.deviceVerificationUrl)
        assertEquals("ABCD-EFGH", authentication.state.deviceUserCode)
        assertEquals("https://auth.openai.com/device", states.last().deviceVerificationUrl)
        authentication.cancel().await()
        awaitCondition {
            states.lastOrNull()?.status == "signed_out" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }

        val requestsBeforeRejectedApiKeys = runtime.requestMethods.size
        listOf("", " \t").forEach { rejectedKey ->
            val rejected = runCatching {
                authentication.authenticate("api_key", rejectedKey).await()
            }.exceptionOrNull()
            assertEquals("API key must not be blank", rejected?.message)
        }
        val hostileKey = runCatching {
            authentication.authenticate(
                "api_key",
                js("({})").unsafeCast<String>(),
            ).await()
        }.exceptionOrNull()
        assertEquals("apiKey must be a string", hostileKey?.message)
        assertEquals(requestsBeforeRejectedApiKeys, runtime.requestMethods.size)

        val controller = js("new AbortController()")
        controller.abort()
        val preAborted = runCatching {
            authentication.authenticate(
                "api_key",
                "sk-pre-aborted",
                controller.signal.unsafeCast<AbortSignal>(),
            ).await()
        }.exceptionOrNull()
        assertEquals("AbortError", preAborted?.asDynamic()?.name as String)
        assertEquals(requestsBeforeRejectedApiKeys, runtime.requestMethods.size)

        val requestsBeforeApiKey = runtime.requestMethods.size
        authentication.authenticate("api_key", "sk-js-test").await()
        awaitCondition {
            states.lastOrNull()?.status == "authenticated" &&
                authenticated.lastOrNull() == true && authenticating.lastOrNull() == false
        }
        assertEquals("authenticated", authentication.state.status)
        assertEquals("sk-js-test", runtime.apiKey)
        assertEquals(
            listOf("account/read", "account/login/start"),
            runtime.requestMethods.drop(requestsBeforeApiKey),
        )

        authentication.signOut().await()
        awaitCondition {
            states.lastOrNull()?.let { it.status == "signed_out" && it.failure == null } == true &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }
        assertEquals(1, runtime.logoutRequests)
        assertEquals(listOf("signed_out"), disposedStates)

        host.close().await()
        awaitCondition {
            stateObservation.isClosed && authenticatedObservation.isClosed && authenticatingObservation.isClosed
        }
    }

    @Test
    fun mapsAuthenticationFailureAndAbortSignalCancellation() = runTest {
        val failedRuntime = ApiTestRuntime().apply { failNextAccountRead = true }
        val failedHost = wrapCodexHost(
            CoreHost(ApiTestPlatform(failedRuntime), CodexClientInfo("node_test", "Node Test", "test")),
        )
        failedHost.start().await()
        val failedAuthentication = assertIs<CodexAgent>(failedHost.agent).authentication
        val failure = runCatching { failedAuthentication.authenticate().await() }.exceptionOrNull()
        val codexError = assertIs<CodexError>(failure)
        assertEquals("authentication_failed", codexError.code)
        assertTrue(codexError.recoverable)
        assertEquals("authentication denied", codexError.message)
        assertEquals("authentication_failed", failedAuthentication.state.failure?.code)
        assertTrue(isFrozen(failedAuthentication.state))
        failedHost.close().await()

        val readEntered = CompletableDeferred<Unit>()
        val readRelease = CompletableDeferred<Unit>()
        val cancelledRuntime = ApiTestRuntime().apply {
            accountReadEntered = readEntered
            accountReadRelease = readRelease
        }
        val cancelledHost = wrapCodexHost(
            CoreHost(ApiTestPlatform(cancelledRuntime), CodexClientInfo("node_test", "Node Test", "test")),
        )
        cancelledHost.start().await()
        val cancelledAuthentication = assertIs<CodexAgent>(cancelledHost.agent).authentication
        val controller = js("new AbortController()")
        val operation = cancelledAuthentication.authenticate(
            signal = controller.signal.unsafeCast<AbortSignal>(),
        )
        readEntered.await()
        controller.abort()
        readRelease.complete(Unit)

        val abort = runCatching { operation.await() }.exceptionOrNull()
        assertEquals("AbortError", abort?.asDynamic()?.name as String)
        awaitCondition { cancelledAuthentication.state.status == "signed_out" }
        assertFalse(cancelledAuthentication.isAuthenticating)
        cancelledHost.close().await()
    }
}

private suspend fun awaitCondition(condition: () -> Boolean) {
    repeat(100) {
        if (condition()) return
        yield()
    }
    assertTrue(condition(), "Condition did not become true")
}

private class ApiTestPlatform(
    private val runtime: ApiTestRuntime,
    private val restoreEntered: CompletableDeferred<Unit>? = null,
    private val restoreRelease: CompletableDeferred<Unit>? = null,
    private val features: Set<CodexRuntimeFeature> = emptySet(),
    private val workspacePath: String = "/workspace",
) : CodexPlatform {
    var selectedWorkspacePath: String? = null

    override val authorizationBrowser: CodexAuthorizationBrowser =
        CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
    override val workspaceStore: CodexWorkspaceStore = object : CodexWorkspaceStore {
        override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution {
            val path = (selection as CodexPathWorkspaceSelection).path
            selectedWorkspacePath = path
            return CodexWorkspaceResolution.Available(CodexWorkspace(path))
        }

        override suspend fun restore(): CodexWorkspaceResolution {
            restoreEntered?.complete(Unit)
            restoreRelease?.await()
            return CodexWorkspaceResolution.Available(CodexWorkspace(workspacePath))
        }

        override suspend fun clear(): Unit = Unit
    }

    override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime = PreparedCodexRuntime(
        runtimeFactory = { runtime },
        workspacePath = workspace.path,
        features = features,
    )
}

private class CountingAbortSignal : AbortSignal {
    override val aborted: Boolean = false
    var additions: Int = 0
    var removals: Int = 0
    private var listener: (() -> Unit)? = null

    override fun addEventListener(type: String, listener: () -> Unit): Unit {
        assertEquals("abort", type)
        additions += 1
        this.listener = listener
    }

    override fun removeEventListener(type: String, listener: () -> Unit): Unit {
        assertEquals("abort", type)
        assertSame(this.listener, listener)
        removals += 1
        this.listener = null
    }
}

private fun isFrozen(value: Any): Boolean = js("Object.isFrozen(value)")

private fun enumerablePropertyCount(value: Any): Int = js("Object.keys(value).length")

private fun javaScriptBigInt(value: String): Long = js("BigInt(value)").unsafeCast<Long>()

private const val SKILL_FIXTURE_CONTENT =
    "---\nname: fixture-skill\ndescription: Fixture skill\n---\nBinding projection body.\n"

private data class SkillTestFixture(
    val root: String,
    val workspacePath: String,
    val sourceDirectory: String,
    val sourceManifestPath: String,
    val installedManifestPath: String,
)

private fun createSkillTestFixture(): SkillTestFixture {
    val fs: dynamic = js("require('node:fs')")
    val os: dynamic = js("require('node:os')")
    val path: dynamic = js("require('node:path')")
    val root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "codex-js-skills-"))) as String
    val workspacePath = path.join(root, "workspace") as String
    val sourceDirectory = path.join(root, "fixture-skill") as String
    val sourceManifestPath = path.join(sourceDirectory, "SKILL.md") as String
    fs.mkdirSync(workspacePath, js("({ recursive: true })"))
    fs.mkdirSync(sourceDirectory, js("({ recursive: true })"))
    fs.writeFileSync(sourceManifestPath, SKILL_FIXTURE_CONTENT, "utf8")
    return SkillTestFixture(
        root = root,
        workspacePath = workspacePath,
        sourceDirectory = sourceDirectory,
        sourceManifestPath = sourceManifestPath,
        installedManifestPath = path.join(
            workspacePath,
            ".agents",
            "skills",
            "fixture-skill",
            "SKILL.md",
        ) as String,
    )
}

private fun nodeFileExists(path: String): Boolean {
    val fs: dynamic = js("require('node:fs')")
    return fs.existsSync(path) as Boolean
}

private fun deleteSkillTestFixture(path: String) {
    val fs: dynamic = js("require('node:fs')")
    fs.rmSync(path, js("({ recursive: true, force: true })"))
}

private class ApiTestRuntime : CodexRuntime {
    private val eventChannel = Channel<CodexRuntimeEvent>(Channel.UNLIMITED)
    override val events: Flow<CodexRuntimeEvent> = eventChannel.receiveAsFlow()
    var started: Boolean = false
    var closed: Boolean = false
    var failNextAccountRead: Boolean = false
    var accountReadEntered: CompletableDeferred<Unit>? = null
    var accountReadRelease: CompletableDeferred<Unit>? = null
    val requestMethods: MutableList<String> = mutableListOf()
    var apiKey: String? = null
    var cancelRequests: Int = 0
    var logoutRequests: Int = 0
    var renamedConversationId: String? = null
    var renamedConversationName: String? = null
    var deletedConversationId: String? = null
    var failNextRename: Boolean = false
    var deleteEntered: CompletableDeferred<Unit>? = null
    var deleteRelease: CompletableDeferred<Unit>? = null
    var threadStartParams: JsonObject? = null
    var threadResumeParams: JsonObject? = null
    val threadListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextThreadList: Boolean = false
    val appListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextAppList: Boolean = false
    val modelListRequests: MutableList<JsonObject> = mutableListOf()
    val configReadRequests: MutableList<JsonObject> = mutableListOf()
    var failNextModelList: Boolean = false
    var failNextConfigRead: Boolean = false
    var emptyNextModelList: Boolean = false
    val skillListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextSkillList: Boolean = false
    var skillWorkspacePath: String = "/workspace"
    var skillManifestPath: String? = null
    var modelPreference: String = "model-preferred"
    var effortPreference: String = "low"
    var serviceTierPreference: String = "fast"
    private var loginAttempts: Int = 0

    suspend fun completeTurn(): Unit = notify("turn/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turn", completedTurn())
    })

    suspend fun emitAgentMessageDelta(text: String): Unit = notify("item/agentMessage/delta", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("itemId", "assistant-live")
        put("delta", text)
    })

    suspend fun emitPlanUpdated(): Unit = notify("turn/plan/updated", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("explanation", "Executing the plan")
        putJsonArray("plan") {
            add(buildJsonObject {
                put("step", "Inspect runtime")
                put("status", "inProgress")
            })
        }
    })

    suspend fun emitHookStarted(): Unit = notify("hook/started", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("run", hookRun("running", "Running hook", listOf("started")))
    })

    suspend fun emitHookCompleted(): Unit = notify("hook/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("run", hookRun("completed", "Complete", listOf("finished", "detached")))
    })

    override suspend fun start(): Unit {
        started = true
    }

    override suspend fun send(line: CodexJsonLine): Unit {
        val request = Json.parseToJsonElement(line.value).jsonObject
        val id = request["id"]?.jsonPrimitive?.long ?: return
        val method = request["method"]?.jsonPrimitive?.content ?: return
        requestMethods += method
        when (method) {
            "initialize" -> respond(id, initializeResult())
            "thread/start" -> {
                threadStartParams = checkNotNull(request["params"]).jsonObject
                respond(id, threadStartResult())
            }
            "thread/resume" -> {
                val params = checkNotNull(request["params"]).jsonObject
                threadResumeParams = params
                respond(id, threadResumeResult(checkNotNull(params["threadId"]).jsonPrimitive.content))
            }
            "thread/read" -> {
                val params = checkNotNull(request["params"]).jsonObject
                respond(id, threadReadResult(checkNotNull(params["threadId"]).jsonPrimitive.content))
            }
            "thread/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                threadListRequests += params
                if (failNextThreadList) {
                    failNextThreadList = false
                    respondError(id, "conversation list denied")
                } else {
                    val cursor = params["cursor"]?.let {
                        if (it == JsonNull) null else it.jsonPrimitive.content
                    }
                    respond(id, threadListResult(cursor))
                }
            }
            "app/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                appListRequests += params
                if (failNextAppList) {
                    failNextAppList = false
                    respondError(id, "connector list denied")
                } else {
                    val cursor = params["cursor"]?.let {
                        if (it == JsonNull) null else it.jsonPrimitive.content
                    }
                    respond(id, appListResult(cursor))
                }
            }
            "model/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                modelListRequests += params
                when {
                    failNextModelList -> {
                        failNextModelList = false
                        respondError(id, "model list denied")
                    }
                    emptyNextModelList -> {
                        emptyNextModelList = false
                        respond(id, buildJsonObject { putJsonArray("data") {} })
                    }
                    else -> {
                        val cursor = params["cursor"]?.let {
                            if (it == JsonNull) null else it.jsonPrimitive.content
                        }
                        respond(id, modelListResult(cursor))
                    }
                }
            }
            "skills/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                skillListRequests += params
                if (failNextSkillList) {
                    failNextSkillList = false
                    respondError(id, "skill list denied")
                } else {
                    respond(id, skillListResult(skillWorkspacePath, skillManifestPath))
                }
            }
            "config/read" -> {
                val params = checkNotNull(request["params"]).jsonObject
                configReadRequests += params
                if (failNextConfigRead) {
                    failNextConfigRead = false
                    respondError(id, "model preferences denied")
                } else {
                    respond(id, buildJsonObject {
                        putJsonObject("config") {
                            put("model", modelPreference)
                            put("model_reasoning_effort", effortPreference)
                            put("service_tier", serviceTierPreference)
                        }
                        putJsonObject("origins") {}
                    })
                }
            }
            "thread/name/set" -> {
                val params = checkNotNull(request["params"]).jsonObject
                renamedConversationId = params["threadId"]?.jsonPrimitive?.content
                renamedConversationName = params["name"]?.jsonPrimitive?.content
                if (failNextRename) {
                    failNextRename = false
                    respondError(id, "rename denied")
                } else {
                    respond(id, buildJsonObject {})
                }
            }
            "thread/delete" -> {
                deletedConversationId = checkNotNull(request["params"])
                    .jsonObject["threadId"]?.jsonPrimitive?.content
                deleteEntered?.complete(Unit)
                deleteRelease?.await()
                respond(id, buildJsonObject {})
            }
            "turn/start" -> respond(id, turnStartResult())
            "account/read" -> {
                accountReadEntered?.complete(Unit)
                accountReadRelease?.await()
                if (failNextAccountRead) {
                    failNextAccountRead = false
                    respondError(id, "authentication denied")
                } else {
                    respond(id, buildJsonObject {
                        put("account", JsonNull)
                        put("requiresOpenaiAuth", true)
                    })
                }
            }
            "account/login/start" -> {
                val params = checkNotNull(request["params"]).jsonObject
                when (params["type"]?.jsonPrimitive?.content) {
                    "chatgpt" -> respond(id, buildJsonObject {
                        put("type", "chatgpt")
                        put("loginId", "login-${++loginAttempts}")
                        put("authUrl", "https://auth.openai.com/oauth?state=login-$loginAttempts")
                    })
                    "chatgptDeviceCode" -> respond(id, buildJsonObject {
                        put("type", "chatgptDeviceCode")
                        put("loginId", "login-${++loginAttempts}")
                        put("userCode", "ABCD-EFGH")
                        put("verificationUrl", "https://auth.openai.com/device")
                    })
                    "apiKey" -> {
                        apiKey = params["apiKey"]?.jsonPrimitive?.content
                        respond(id, buildJsonObject { put("type", "apiKey") })
                    }
                    else -> error("Unexpected authentication method")
                }
            }
            "account/login/cancel" -> {
                cancelRequests += 1
                val loginId = checkNotNull(request["params"]).jsonObject["loginId"]!!.jsonPrimitive.content
                notify("account/login/completed", buildJsonObject {
                    put("loginId", loginId)
                    put("success", false)
                    put("error", "cancelled")
                })
                respond(id, buildJsonObject { put("status", "canceled") })
            }
            "account/logout" -> {
                logoutRequests += 1
                respond(id, buildJsonObject {})
            }
            else -> respond(id, buildJsonObject {})
        }
    }

    private suspend fun respond(id: Long, result: JsonObject): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("id", id)
                put("result", result)
            }.toString(),
        )))
    }

    private suspend fun respondError(id: Long, message: String): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("id", id)
                putJsonObject("error") {
                    put("code", -32000)
                    put("message", message)
                }
            }.toString(),
        )))
    }

    private suspend fun notify(method: String, params: JsonObject): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("method", method)
                put("params", params)
            }.toString(),
        )))
    }

    override fun close(): Unit {
        closed = true
        eventChannel.close()
    }
}

private fun hookRun(status: String, statusMessage: String, details: List<String>): JsonObject = buildJsonObject {
    put("displayOrder", 0)
    putJsonArray("entries") {
        details.forEach { detail ->
            add(buildJsonObject {
                put("kind", "context")
                put("text", detail)
            })
        }
    }
    put("eventName", "stop")
    put("executionMode", "sync")
    put("handlerType", "command")
    put("id", "hook-js")
    put("scope", "turn")
    put("sourcePath", "/workspace/.codex/hooks.json")
    put("startedAt", 0)
    put("status", status)
    put("statusMessage", statusMessage)
}

private fun initializeResult(): JsonObject = buildJsonObject {
    put("codexHome", "/tmp/codex")
    put("platformFamily", "unix")
    put("platformOs", "node")
    put("userAgent", "test")
}

private fun skillListResult(workspacePath: String, manifestPath: String?): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("cwd", workspacePath)
            putJsonArray("errors") {
                add(buildJsonObject {
                    put("path", "${manifestPath ?: workspacePath}.warning")
                    put("message", "ignored entry")
                })
            }
            putJsonArray("skills") {
                if (manifestPath != null) {
                    add(skillMetadata(manifestPath))
                    add(skillMetadata(manifestPath))
                }
            }
        })
    }
}

private fun skillMetadata(manifestPath: String): JsonObject = buildJsonObject {
    put("name", "fixture-skill")
    put("description", "Protocol description")
    put("enabled", true)
    put("path", manifestPath)
    put("scope", "repo")
    putJsonObject("dependencies") {
        putJsonArray("tools") {
            listOf("git", "rg").forEach { tool ->
                add(buildJsonObject {
                    put("type", "command")
                    put("value", tool)
                })
            }
        }
    }
    putJsonObject("interface") {
        put("displayName", "Fixture skill")
        put("shortDescription", "Projected description")
        put("brandColor", "#abcdef")
    }
}

private fun threadStartResult(): JsonObject = buildJsonObject {
    put("thread", threadResult())
    put("approvalPolicy", "on-request")
    put("approvalsReviewer", "user")
    put("cwd", "/workspace")
    put("model", "test")
    put("modelProvider", "openai")
    putJsonObject("sandbox") { put("type", "dangerFullAccess") }
}

private fun threadResumeResult(threadId: String): JsonObject = buildJsonObject {
    put("thread", threadResult(threadId = threadId))
    put("approvalPolicy", "untrusted")
    put("approvalsReviewer", "user")
    put("cwd", "/workspace")
    put("model", "test")
    put("modelProvider", "openai")
    put("serviceTier", "fast")
    putJsonObject("sandbox") { put("type", "dangerFullAccess") }
}

private fun threadReadResult(threadId: String): JsonObject = buildJsonObject {
    put("thread", threadResult(buildJsonArray { add(completedTurn()) }, threadId))
}

private fun appListResult(cursor: String?): JsonObject = buildJsonObject {
    putJsonArray("data") {
        when (cursor) {
            null -> add(buildJsonObject {
                put("id", "connector-custom")
                put("name", "Custom connector")
                put("description", "Custom description")
                put("installUrl", "https://example.com/install")
                put("isAccessible", true)
                put("isEnabled", false)
                putJsonArray("pluginDisplayNames") {
                    add(JsonPrimitive("Plugin one"))
                    add(JsonPrimitive("Plugin two"))
                }
            })
            "page-2" -> add(buildJsonObject {
                put("id", "connector-default")
                put("name", "Default connector")
            })
            else -> error("Unexpected app/list cursor: $cursor")
        }
    }
    if (cursor == null) put("nextCursor", "page-2")
}

private fun modelListResult(cursor: String?): JsonObject = buildJsonObject {
    putJsonArray("data") {
        when (cursor) {
            null -> add(modelResult(
                catalogId = "catalog-first",
                runtimeId = "model-first",
                displayName = "First model",
                supportedEfforts = listOf("low", "medium"),
                defaultEffort = "medium",
                isDefault = false,
            ))
            "models-page-2" -> {
                add(modelResult(
                    catalogId = "catalog-default",
                    runtimeId = "model-default",
                    displayName = "Default model",
                    supportedEfforts = listOf("medium", "high"),
                    defaultEffort = "medium",
                    isDefault = true,
                ))
                add(modelResult(
                    catalogId = "catalog-preferred",
                    runtimeId = "model-preferred",
                    displayName = "Preferred model",
                    supportedEfforts = listOf("low", "medium"),
                    defaultEffort = "medium",
                    isDefault = false,
                    serviceTiers = listOf(
                        Triple("fast", "Fast", "Faster responses"),
                        Triple("free", "Free", "Default responses"),
                        Triple("fast", "Ignored duplicate", "Ignored duplicate"),
                    ),
                    defaultServiceTier = "free",
                ))
            }
            else -> error("Unexpected model/list cursor: $cursor")
        }
    }
    if (cursor == null) put("nextCursor", "models-page-2")
}

private fun modelResult(
    catalogId: String,
    runtimeId: String,
    displayName: String,
    supportedEfforts: List<String>,
    defaultEffort: String,
    isDefault: Boolean,
    serviceTiers: List<Triple<String, String, String>> = emptyList(),
    defaultServiceTier: String? = null,
): JsonObject = buildJsonObject {
    put("id", catalogId)
    put("model", runtimeId)
    put("displayName", displayName)
    put("description", "$displayName description")
    put("hidden", false)
    put("isDefault", isDefault)
    put("defaultReasoningEffort", defaultEffort)
    putJsonArray("supportedReasoningEfforts") {
        supportedEfforts.forEach { effort ->
            add(buildJsonObject {
                put("reasoningEffort", effort)
                put("description", "$effort reasoning")
            })
        }
    }
    if (serviceTiers.isNotEmpty()) {
        putJsonArray("serviceTiers") {
            serviceTiers.forEach { (id, name, description) ->
                add(buildJsonObject {
                    put("id", id)
                    put("name", name)
                    put("description", description)
                })
            }
        }
    }
    if (defaultServiceTier != null) put("defaultServiceTier", defaultServiceTier)
}

private fun threadListResult(cursor: String?): JsonObject = buildJsonObject {
    putJsonArray("data") {
        when (cursor) {
            null -> add(threadResult(
                threadId = "thread-recent",
                name = "Recent title",
                preview = "Ignored preview",
                updatedAt = 9_007_199_254_740_993L,
            ))
            "history-page-2" -> add(threadResult(
                threadId = "thread-older",
                preview = "  Older preview\nIgnored suffix",
                updatedAt = 7L,
            ))
            else -> error("Unexpected thread/list cursor: $cursor")
        }
    }
    if (cursor == null) put("nextCursor", "history-page-2")
}

private fun threadResult(
    turns: JsonArray = buildJsonArray {},
    threadId: String = "thread-js",
    name: String? = null,
    preview: String = "",
    updatedAt: Long = 0,
): JsonObject = buildJsonObject {
    put("id", threadId)
    put("cliVersion", "0.149.0")
    put("createdAt", 0)
    put("cwd", "/workspace")
    put("ephemeral", false)
    put("modelProvider", "openai")
    if (name != null) put("name", name)
    put("preview", preview)
    put("conversationId", threadId)
    put("sessionId", threadId)
    put("source", "cli")
    putJsonObject("status") { put("type", "idle") }
    put("turns", turns)
    put("updatedAt", updatedAt)
}

private fun turnStartResult(): JsonObject = buildJsonObject {
    putJsonObject("turn") {
        put("id", "turn-js")
        putJsonArray("items") {}
        put("status", "inProgress")
    }
}

private fun completedTurn(): JsonObject = buildJsonObject {
    put("id", "turn-js")
    putJsonArray("items") {
        add(buildJsonObject {
            put("id", "user-1")
            put("type", "userMessage")
            putJsonArray("content") {
                add(buildJsonObject {
                    put("type", "text")
                    put("text", "hello")
                })
            }
        })
        add(buildJsonObject {
            put("id", "assistant-1")
            put("type", "agentMessage")
            put("text", "world")
        })
    }
    put("status", "completed")
}
