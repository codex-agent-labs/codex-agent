package io.github.codex_agent_labs.codexmobile.agent

import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntime
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexHostTest {
    @Test
    fun staleCloseDoesNotDetachANewerHandleForTheSameConversationId(): Unit = runBlocking {
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start", "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-shared") }
                })
                "thread/read" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-shared") }
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            val first = agent.openConversation()
            val id = checkNotNull(first.state.value.conversationId)
            val replacement = agent.openConversation(id)
            assertSame(replacement, agent.activeConversation.value)
            first.close()

            runtime.request(990, "item/commandExecution/requestApproval", hostApprovalRequest(id.value, "turn-shared"))
            val pending = withTimeout(1_000) { agent.interactionState.first { it.pending.isNotEmpty() } }
            assertEquals(id, pending.pending.single().conversationId)
        } finally {
            host.close()
        }
    }

    @Test
    fun newerWorkspaceSelectionIsTheLastPersistedSelection(): Unit = runBlocking {
        val firstStarted = CompletableDeferred<Unit>()
        val releaseFirst = CompletableDeferred<Unit>()
        val persisted = mutableListOf<String>()
        val store = object : CodexWorkspaceStore {
            override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution {
                val path = (selection as CodexPathWorkspaceSelection).path
                if (path == "/workspace/a") {
                    firstStarted.complete(Unit)
                    releaseFirst.await()
                }
                persisted += path
                return CodexWorkspaceResolution.Available(CodexWorkspace(path))
            }

            override suspend fun restore() = CodexWorkspaceResolution.SelectionRequired(
                CodexWorkspaceSelectionReason.NOT_SELECTED,
                "Select",
            )

            override suspend fun clear() = Unit
        }
        val runtime = FakeCodexRuntime { message, server ->
            if (message.method == "initialize") server.respond(message.id, buildJsonObject {})
        }
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = store

            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            val first = async(start = CoroutineStart.UNDISPATCHED) {
                host.selectWorkspace(CodexPathWorkspaceSelection("/workspace/a"))
            }
            firstStarted.await()
            val second = async(start = CoroutineStart.UNDISPATCHED) {
                host.selectWorkspace(CodexPathWorkspaceSelection("/workspace/b"))
            }
            releaseFirst.complete(Unit)
            assertFailsWith<CancellationException> { first.await() }
            second.await()

            assertEquals(listOf("/workspace/a", "/workspace/b"), persisted)
            assertEquals("/workspace/b", readyAgent(host).workspace.path)
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentTurnRequest#property:invocations#sha256:ebbd7dc36627bc359e26a3a52750314c2689462c9f5ba8fa614c556639281e11",
        "api-v1:CodexAgent#property:connectors#sha256:f604c83b32c1208445efc88b2dbba7b5fe66fc77a44f0fe77c00b680f8049365",
        "api-v1:CodexAgent#property:mcpServers#sha256:9e78cffd1c9fd6f5313f9fa335079bc08ca872550683d7403ddb4f39bca6edc9",
    )
    fun unavailablePreparedFeaturesFailBeforeTheirRpc(): Unit = runBlocking {
        val requestedMethods = mutableListOf<String>()
        var unsupportedStartupFlags: List<Boolean>? = null
        var startupInstructions = ""
        var hasShellPolicy = true
        val runtime = FakeCodexRuntime { message, server ->
            message.method?.let(requestedMethods::add)
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    val config = message.params.requiredObject("config")
                    val flags = config.requiredObject("features")
                    unsupportedStartupFlags = listOf(
                        "shell_tool",
                        "apps",
                        "enable_mcp_apps",
                        "plugins",
                        "hooks",
                    ).map { flags.getValue(it).jsonPrimitive.content.toBoolean() }
                    startupInstructions = message.params.requiredString("developerInstructions")
                    hasShellPolicy = "shell_environment_policy" in config
                    putJsonObject("thread") { put("id", "thread-limited") }
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))

            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = emptySet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            host.start()
            val agent = readyAgent(host)
            val conversation = agent.conversations.open()
            assertFalse(agent.skills.isAvailable)
            assertFalse(agent.hooks.isAvailable)
            assertFalse(agent.plugins.isAvailable)
            assertFalse(agent.connectors.isAvailable)
            assertFalse(agent.mcpServers.isAvailable)
            val failures = listOf(
                assertFailsWith<CodexOperationException> { agent.skills.list() },
                assertFailsWith<CodexOperationException> { agent.hooks.list() },
                assertFailsWith<CodexOperationException> { agent.plugins.list() },
                assertFailsWith<CodexOperationException> { agent.connectors.list() },
                assertFailsWith<CodexOperationException> { agent.mcpServers.list() },
                assertFailsWith<CodexOperationException> { conversation.runShellCommand("pwd") },
                assertFailsWith<CodexOperationException> {
                    conversation.send(
                        AgentTurnRequest(
                            "review",
                            invocations = listOf(AgentInvocation.Skill("Review", "/skills/review/SKILL.md")),
                        ),
                    )
                },
                assertFailsWith<CodexOperationException> {
                    conversation.send(
                        AgentTurnRequest(
                            "use plugin",
                            invocations = listOf(AgentInvocation.Plugin("Drive", "plugin://drive@catalog")),
                        ),
                    )
                },
            )
            assertTrue(failures.all { it.failure.code == "unsupported_feature" && !it.failure.isRecoverable })
            assertEquals(AgentConversationStatus.READY, conversation.state.value.status)
            assertEquals(listOf("initialize", "initialized", "thread/start"), requestedMethods)
            assertEquals(List(5) { false }, unsupportedStartupFlags)
            assertFalse(hasShellPolicy)
            assertFalse("shell" in startupInstructions.lowercase())
            assertFalse("plugin" in startupInstructions.lowercase())
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:CodexAgent#property:authentication#sha256:799f1d0c28410f5135ab32eeadb8745704d68b8ddfe0386674504830fba0a65b",
        "api-v1:CodexAgent#property:conversations#sha256:fb027560a8d85208765127f17015db1015b54558cb14ca48179bccaab08bfe5b",
        "api-v1:CodexAgent#property:hooks#sha256:3dab7847134f334ba448d4df322e1a3e117b4f1324116b13ecd566aafa35e231",
        "api-v1:CodexAgent#property:integrationAuthorization#sha256:bb33f3477fe2cf3da8355a92192589371817eb559fd0b2aa3e87a74f0774bd1b",
        "api-v1:CodexAgent#property:interactions#sha256:35498a67da381809079d86c3900dcbe1a29302faaad872dbb6443182b4b5d4e9",
        "api-v1:CodexAgent#property:plugins#sha256:ea7e5e98395c441f63b5ae64765d552d6260a088a41970affbcb29d5dadde4a6",
        "api-v1:CodexAgent#property:skills#sha256:4abb6e1fa9604e1a25aa3416e31307f83060134691c21482c54f23412e500ae7",
        "api-v1:CodexAgent#property:workspace#sha256:8a553889c30587123344fe910c359dfd72238ed1c54d575a525028318a20b973",
        "api-v1:CodexClientInfo#property:name#sha256:c1477a2ead2d738a7b4ea37727ca22e3e0f6aac210f7f56a8dae8dcac2ab5ea1",
        "api-v1:CodexClientInfo#property:title#sha256:c3c69a080afc3ec74ba91578a3554adc47174606af9d5f331190751e5a2ce478",
        "api-v1:CodexClientInfo#property:version#sha256:71f05fe551852d8dc5b47bb80386574b7c54ff4317d397d32b13dff26511c7db",
        "api-v1:CodexWorkspace#constructor:<init>#sha256:6052e1fb89e9482f7f58fd8df9279eb8095e8c730634e6c15841a147032182d3",
        "api-v1:CodexWorkspace#property:displayName#sha256:d6e22600a7aff3e203772f9343fb21208309923ad2e4cbdb923b4925a3b05307",
        "api-v1:CodexWorkspace#property:path#sha256:d0cc25e91bc838c45c466c3b3bca8eef9046212a1c9e09b59f31474869cae4e5",
    )
    fun ownedHostUsesClientIdentityPreparedPathAndDeclaredFeatures(): Unit = runBlocking {
        val paths = mutableListOf<String>()
        var initializedClient: Triple<String, String, String>? = null
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> {
                    val info = message.params.requiredObject("clientInfo")
                    initializedClient = Triple(
                        info.requiredString("name"),
                        info.requiredString("title"),
                        info.requiredString("version"),
                    )
                    server.respond(message.id, buildJsonObject {})
                }
                "thread/start" -> {
                    paths += message.params.requiredString("cwd")
                    server.respond(message.id, buildJsonObject {
                        putJsonObject("thread") { put("id", "thread-prepared") }
                    })
                }
                "skills/list" -> {
                    paths += message.params.requiredArray("cwds").single().jsonPrimitive.content
                    server.respond(message.id, buildJsonObject { putJsonArray("data") {} })
                }
                "hooks/list" -> {
                    paths += message.params.requiredArray("cwds").single().jsonPrimitive.content
                    server.respond(message.id, buildJsonObject { putJsonArray("data") {} })
                }
                "plugin/list", "plugin/installed" -> {
                    paths += message.params.requiredArray("cwds").single().jsonPrimitive.content
                    server.respond(message.id, buildJsonObject {
                        putJsonArray("marketplaces") {}
                        putJsonArray("marketplaceLoadErrors") {}
                    })
                }
            }
        }
        val logicalWorkspace = CodexWorkspace("/selected", "Selected")
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(logicalWorkspace))

            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = "/prepared",
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            host.start()
            val agent = readyAgent(host)
            assertEquals(logicalWorkspace, agent.workspace)
            assertTrue(agent.skills.isAvailable)
            assertTrue(agent.hooks.isAvailable)
            assertTrue(agent.plugins.isAvailable)
            assertSame(agent.authentication, agent.authentication)
            assertSame(agent.conversations, agent.conversations)
            val conversation = agent.conversations.open()
            assertFalse(host.lifecycleState is MutableStateFlow<*>)
            assertFalse(agent.authentication.state is MutableStateFlow<*>)
            assertFalse(agent.interactions.state is MutableStateFlow<*>)
            assertFalse(agent.integrationAuthorization.state is MutableStateFlow<*>)
            assertFalse(agent.conversations.active is MutableStateFlow<*>)
            assertFalse(conversation.state is MutableStateFlow<*>)
            agent.skills.list()
            agent.hooks.list()
            agent.plugins.list()
            assertTrue(paths.size >= 5)
            assertTrue(paths.all { it == "/prepared" })
            assertEquals(
                Triple(TEST_CLIENT_INFO.name, TEST_CLIENT_INFO.title, TEST_CLIENT_INFO.version),
                initializedClient,
            )
        } finally {
            host.close()
        }
        assertTrue(runtime.allClientStreamsClosed())
    }

    @Test
    fun typedExtensionMutationsUseOnlyTheirSnapshotIdentity(): Unit = runBlocking {
        val mutations = mutableListOf<String>()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "skills/config/write" -> {
                    mutations += "skill:${message.params.requiredString("path")}:${message.params.requiredBoolean("enabled")}"
                    server.respond(message.id, buildJsonObject { put("effectiveEnabled", true) })
                }
                "config/batchWrite" -> {
                    val value = message.params.requiredArray("edits").single().jsonObject.requiredObject("value")
                    val (key, state) = value.entries.single()
                    val snapshot = state.jsonObject
                    mutations += if ("trusted_hash" in snapshot) {
                        "trust:$key:${snapshot.requiredString("trusted_hash")}"
                    } else {
                        "hook:$key:${snapshot.requiredBoolean("enabled")}"
                    }
                    server.respond(message.id, buildJsonObject {
                        put("filePath", "/tmp/config.toml")
                        put("status", "ok")
                        put("version", "1")
                    })
                }
                "config/value/write" -> {
                    mutations += "plugin:${message.params.requiredString("keyPath")}:${message.params.getValue("value").jsonPrimitive.content}"
                    server.respond(message.id, buildJsonObject {})
                }
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            agent.setSkillEnabled(
                AgentSkill("review", "Review", "Review", "/skills/typed/SKILL.md", AgentSkillScope.USER, false),
                true,
            )
            val hook = AgentHook(
                key = "typed-hook",
                currentHash = "hash-from-snapshot",
                isEnabled = false,
                eventName = "afterTurn",
                handler = AgentHookHandler.Command("./typed-hook", isAsync = false),
                isManaged = false,
                source = "user",
                sourcePath = "/hooks/typed.json",
                timeoutSeconds = 10,
                trustStatus = AgentHookTrustStatus.UNTRUSTED,
            )
            agent.setHookEnabled(hook, true)
            agent.hooks.trust(hook)
            agent.setPluginEnabled(
                AgentPluginSummary(
                    reference = AgentPluginReference("typed-plugin", "typed", "catalog", remotePluginId = "remote"),
                    displayName = "Typed",
                    description = "Typed",
                    isInstalled = true,
                    isEnabled = false,
                    installPolicy = AgentPluginInstallPolicy.AVAILABLE,
                    authPolicy = AgentPluginAuthPolicy.ON_USE,
                    isAvailable = true,
                ),
                true,
            )
            assertEquals(
                listOf(
                    "skill:/skills/typed/SKILL.md:true",
                    "hook:typed-hook:true",
                    "trust:typed-hook:hash-from-snapshot",
                    "plugin:plugins.typed-plugin.enabled:true",
                ),
                mutations,
            )
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:CodexAgent#property:models#sha256:1b22b0700597a95300774809e34f0443a191ea0e5e114363dc6025e7b95867cd",
        "api-v1:CodexModels#function:resolveEffort#sha256:bb74f468a50633a029ae8354f0e2924e7bbe2ee6bd8dc11732fb41eeccbfd665",
        "api-v1:CodexModels#function:resolveServiceTier#sha256:57af6d303b0d802917d7c4873a4490ec5a7a69a96751a87b81a551bae96c7970",
        "api-v1:CodexModels#function:resolve#sha256:2ab51e1910fa8238efc503a1a6f197441bbc807ae33b9d2f588e0ab62be0666e",
    )
    fun modelFacadeResolvesConfiguredModelEffortAndTierWithoutCallerPreferences(): Unit = runBlocking {
        var configReads = 0
        val preferred = buildJsonObject {
            model("preferred-catalog", "preferred", "Preferred", "medium", false)
                .forEach { (name, value) -> put(name, value) }
            put("defaultServiceTier", "free")
            putJsonArray("serviceTiers") {
                add(buildJsonObject {
                    put("id", "free")
                    put("name", "Free")
                    put("description", "Default")
                })
                add(buildJsonObject {
                    put("id", "fast")
                    put("name", "Fast")
                    put("description", "Faster")
                })
            }
        }
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "model/list" -> server.respond(message.id, page(
                    listOf(
                        model("default-catalog", "default", "Default", "medium", true),
                        preferred,
                    ),
                    nextCursor = null,
                ))
                "config/read" -> server.respond(message.id, buildJsonObject {
                    configReads += 1
                    putJsonObject("config") {
                        put("model", "preferred")
                        put("model_reasoning_effort", "low")
                        put("service_tier", "fast")
                    }
                    putJsonObject("origins") {}
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val models = readyAgent(host).models
            val selected = models.resolve()
            assertEquals("preferred", selected.id)
            assertEquals("low", models.resolveEffort(selected))
            assertEquals("fast", models.resolveServiceTier(selected)?.id)
            assertEquals("default", models.resolve(AgentResolution.Default).id)
            assertEquals("medium", models.resolveEffort(selected, AgentResolution.Default))
            assertEquals("free", models.resolveServiceTier(selected, AgentResolution.First)?.id)
            assertEquals(3, configReads)
        } finally {
            host.close()
        }
    }

    @Test
    fun modelFacadeReportsAnEmptyCatalogBeforeReadingPreferences(): Unit = runBlocking {
        var configReads = 0
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "model/list" -> server.respond(message.id, buildJsonObject { putJsonArray("data") {} })
                "config/read" -> {
                    configReads += 1
                    server.respond(message.id, buildJsonObject {
                        putJsonObject("config") {}
                        putJsonObject("origins") {}
                    })
                }
            }
        }
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(CodexWorkspace("/workspace"))),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            assertFailsWith<AgentModelUnavailableException> { readyAgent(host).models.resolve() }
            assertEquals(0, configReads)
        } finally {
            host.close()
        }
    }

    @Test
    fun limitedRuntimeKeepsLocalToolsAndOmitsPluginDependentTools(): Unit = runBlocking {
        var dynamicTools = emptyList<String>()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> {
                    dynamicTools = message.params.requiredArray("dynamicTools")
                        .map { it.jsonObject.requiredString("name") }
                    server.respond(message.id, buildJsonObject {
                        putJsonObject("thread") { put("id", "thread-local-tools") }
                    })
                }
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val provider = object : CodexToolProvider {
            override fun definitions() = listOf(
                BuiltInToolDefinition("local", "local_read", "Read", buildJsonObject {}, requiresEnabledPlugin = false),
                BuiltInToolDefinition("plugin", "plugin_read", "Read", buildJsonObject {}),
            )

            override suspend fun execute(
                call: BuiltInToolCall,
                context: CodexToolExecutionContext,
            ) = BuiltInToolResult.text("ok")
        }
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = setOf(CodexRuntimeFeature.SKILLS),
                toolProvider = provider,
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            host.start()
            readyAgent(host).openConversation()
            assertEquals(listOf("local_read"), dynamicTools)
        } finally {
            host.close()
        }
    }

    @Test
    fun hostClosePreservesPresentationFailureAfterClosingTheRuntime(): Unit = runBlocking {
        val presentationCloseStarted = CountDownLatch(1)
        val releasePresentationClose = CountDownLatch(1)
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/read" -> server.respond(message.id, buildJsonObject {
                    put("account", kotlinx.serialization.json.JsonNull)
                    put("requiresOpenaiAuth", true)
                })
                "account/login/start" -> server.respond(message.id, buildJsonObject {
                    put("type", "chatgpt")
                    put("loginId", "login-close")
                    put("authUrl", "https://auth.openai.com/oauth?state=login-close")
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser = CodexAuthorizationBrowser {
                CodexAuthorizationPresentation {
                    presentationCloseStarted.countDown()
                    check(releasePresentationClose.await(5, TimeUnit.SECONDS))
                    error("presentation close failed")
                }
            }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        host.start()
        val agent = readyAgent(host)
        agent.authenticate()
        withTimeout(1_000) { agent.authenticationState.first { it.pendingSignInUrl != null } }

        val firstClose = async(Dispatchers.Default) { runCatching { host.close() } }
        assertTrue(presentationCloseStarted.await(1, TimeUnit.SECONDS))
        val secondClose = async(Dispatchers.Default) { runCatching { host.close() } }
        yield()
        assertFalse(secondClose.isCompleted)
        releasePresentationClose.countDown()
        val firstFailure = assertIs<CodexOperationException>(firstClose.await().exceptionOrNull())
        val secondFailure = assertIs<CodexOperationException>(secondClose.await().exceptionOrNull())
        assertEquals("host_close_failed", firstFailure.failure.code)
        assertEquals(firstFailure.failure, secondFailure.failure)
        assertEquals("presentation close failed", firstFailure.cause?.message)
        assertEquals("presentation close failed", secondFailure.cause?.message)
        assertIs<CodexHostState.Closed>(host.state.value)
        assertTrue(runtime.allClientStreamsClosed())
    }

    @Test
    fun hostCloseWaitsForAnInFlightBrowserPresentationAndClosesIt(): Unit = runBlocking {
        val browserOpenStarted = CountDownLatch(1)
        val releaseBrowserOpen = CountDownLatch(1)
        val presentationCloseCount = AtomicInteger()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/read" -> server.respond(message.id, buildJsonObject {
                    put("account", kotlinx.serialization.json.JsonNull)
                    put("requiresOpenaiAuth", true)
                })
                "account/login/start" -> server.respond(message.id, buildJsonObject {
                    put("type", "chatgpt")
                    put("loginId", "login-blocked-browser")
                    put("authUrl", "https://auth.openai.com/oauth?state=login-blocked-browser")
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser = CodexAuthorizationBrowser {
                browserOpenStarted.countDown()
                check(releaseBrowserOpen.await(5, TimeUnit.SECONDS))
                CodexAuthorizationPresentation { presentationCloseCount.incrementAndGet() }
            }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        host.start()
        readyAgent(host).authenticate()
        assertTrue(browserOpenStarted.await(1, TimeUnit.SECONDS))

        val closing = async(Dispatchers.Default) { host.close() }
        yield()
        assertFalse(closing.isCompleted)
        releaseBrowserOpen.countDown()
        closing.await()

        assertEquals(1, presentationCloseCount.get())
        assertTrue(runtime.allClientStreamsClosed())
    }

    @Test
    fun duplicateConversationCloseReportsTheSameDetachFailure(): Unit = runBlocking {
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-close-failure") }
                })
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser = CodexAuthorizationBrowser {
                CodexAuthorizationPresentation { error("elicitation presentation close failed") }
            }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace) = PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            host.start()
            val agent = readyAgent(host)
            val conversation = agent.openConversation()
            runtime.request(905, "mcpServer/elicitation/request", buildJsonObject {
                put("serverName", "example")
                put("threadId", "thread-close-failure")
                put("elicitationId", "elicitation-close")
                put("message", "Authorize")
                put("url", "https://accounts.example.com/authorize")
                put("turnId", "turn-close")
                put("mode", "url")
            })
            val pending = withTimeout(1_000) {
                agent.interactionState.first { it.pending.isNotEmpty() }.pending.single()
            }
            agent.interactions.openUrl(assertIs<AgentPendingElicitation>(pending))

            val first = assertFailsWith<CodexOperationException> { conversation.close() }
            val second = assertFailsWith<CodexOperationException> { conversation.close() }
            assertEquals("close_failed", first.failure.code)
            assertEquals(first.failure, second.failure)
            assertEquals("elicitation presentation close failed", first.cause?.message)
            assertEquals("elicitation presentation close failed", second.cause?.message)
            assertEquals(AgentConversationStatus.CLOSED, conversation.state.value.status)
            assertNull(agent.activeConversation.value)
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentApprovalDecision#enum-entry:ACCEPT#sha256:c6613f75901ffd0146f3c8f945f73fabdc67efb237d52809c8a1e062835dc868",
    )
    fun readyAgentPublishesReturnedConversationAndResolvesTypedApproval(): Unit = runBlocking {
        val approvalResponse = CompletableDeferred<String>()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-typed") }
                })
                null -> if (message.id == 903L) {
                    approvalResponse.complete(
                        message.objectValue.getValue("result").jsonObject
                            .getValue("decision").jsonPrimitive.content,
                    )
                }
            }
        }
        val workspace = CodexWorkspace("/workspace", "Workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            this,
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            assertEquals(workspace, agent.workspace)
            assertEquals(AgentAuthenticationStatus.SIGNED_OUT, agent.authenticationState.value.status)
            val conversation = agent.openConversation()
            assertSame(conversation, agent.activeConversation.value)

            runtime.request(
                903,
                "item/commandExecution/requestApproval",
                hostApprovalRequest("thread-typed", "turn-typed"),
            )
            val approval = withTimeout(1_000) {
                agent.interactionState.first { it.pending.isNotEmpty() }.pending.single()
            }
            agent.resolveApproval(assertIs<AgentPendingApproval>(approval), AgentApprovalDecision.ACCEPT)
            assertEquals("accept", withTimeout(1_000) { approvalResponse.await() })
            conversation.close()
            conversation.close()
            assertNull(agent.activeConversation.value)
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:CodexHostState.Preparing#constructor:<init>#sha256:f5ed8a44dbb2cec0c0b3e0344b28df1a2f8a3432198ebd7e165a734ff511b52e",
        "api-v1:CodexHostState.Preparing#property:workspace#sha256:4c777093c8a55e6abceb156e95a45d69027ecd55f5055befb96e75da786bf2fc",
    )
    fun cancellationDoesNotLeaveHostInARestoreOrPrepareTransition(): Unit = runBlocking {
        val restoringHost = CodexHost(
            object : CodexPlatform {
                override val authorizationBrowser =
                    CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
                override val workspaceStore = object : CodexWorkspaceStore {
                    override suspend fun select(selection: CodexWorkspaceSelection) = awaitCancellation()
                    override suspend fun restore(): CodexWorkspaceResolution = awaitCancellation()
                    override suspend fun clear() = Unit
                }

                override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime =
                    error("prepare must not be reached")
            },
            this,
            TEST_CLIENT_INFO,
        )
        val restoring = async(start = CoroutineStart.UNDISPATCHED) { restoringHost.start() }
        assertIs<CodexHostState.Restoring>(restoringHost.lifecycleState.value)
        restoring.cancelAndJoin()
        assertIs<CodexHostState.Failed>(restoringHost.lifecycleState.value)
        restoringHost.close()

        val workspace = CodexWorkspace("/workspace", "Workspace")
        val preparingHost = CodexHost(
            object : CodexPlatform {
                override val authorizationBrowser =
                    CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
                override val workspaceStore = object : CodexWorkspaceStore {
                    override suspend fun select(selection: CodexWorkspaceSelection) =
                        CodexWorkspaceResolution.Available(workspace)
                    override suspend fun restore() = CodexWorkspaceResolution.Available(workspace)
                    override suspend fun clear() = Unit
                }

                override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime =
                    awaitCancellation()
            },
            this,
            TEST_CLIENT_INFO,
        )
        val preparing = async(start = CoroutineStart.UNDISPATCHED) { preparingHost.start() }
        assertEquals(
            workspace,
            assertIs<CodexHostState.Preparing>(preparingHost.lifecycleState.value).workspace,
        )
        preparing.cancelAndJoin()
        assertEquals(
            workspace,
            assertIs<CodexHostState.Failed>(preparingHost.lifecycleState.value).workspace,
        )
        preparingHost.close()
    }

    @Test
    fun closeWaitsForAnInFlightPrepareAndTheStartIsSuperseded(): Unit = runBlocking {
        val prepareStarted = CompletableDeferred<Unit>()
        val releasePrepare = CompletableDeferred<Unit>()
        val runtime = FakeCodexRuntime { message, server ->
            if (message.method == "initialize") server.respond(message.id, buildJsonObject {})
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
                prepareStarted.complete(Unit)
                releasePrepare.await()
                return PreparedCodexRuntime(
                    runtimeFactory = { runtime },
                    workspacePath = workspace.path,
                    features = CodexRuntimeFeature.entries.toSet(),
                )
            }
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            val starting = async(start = CoroutineStart.UNDISPATCHED) { host.start() }
            prepareStarted.await()
            val closing = async(start = CoroutineStart.UNDISPATCHED) { host.close() }
            yield()
            assertFalse(closing.isCompleted)

            releasePrepare.complete(Unit)
            assertFailsWith<CancellationException> { starting.await() }
            closing.await()
            assertIs<CodexHostState.Closed>(host.state.value)
            assertTrue(runtime.allClientStreamsClosed())
        } finally {
            releasePrepare.complete(Unit)
            host.close()
        }
    }

    @Test
    fun closeReportsCleanupFailureFromAnInFlightPrepare(): Unit = runBlocking {
        val prepareStarted = CompletableDeferred<Unit>()
        val releasePrepare = CompletableDeferred<Unit>()
        val delegate = FakeCodexRuntime { message, server ->
            if (message.method == "initialize") server.respond(message.id, buildJsonObject {})
        }
        val runtime = object : CodexRuntime by delegate {
            override fun close() {
                delegate.close()
                error("late runtime close failed")
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val platform = object : CodexPlatform {
            override val authorizationBrowser =
                CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
            override val workspaceStore = FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace))
            override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
                prepareStarted.complete(Unit)
                releasePrepare.await()
                return PreparedCodexRuntime(
                    runtimeFactory = { runtime },
                    workspacePath = workspace.path,
                    features = CodexRuntimeFeature.entries.toSet(),
                )
            }
        }
        val host = CodexHost(platform, TEST_CLIENT_INFO)
        try {
            val starting = async(start = CoroutineStart.UNDISPATCHED) { runCatching { host.start() } }
            prepareStarted.await()
            val closing = async(start = CoroutineStart.UNDISPATCHED) { runCatching { host.close() } }
            yield()
            assertFalse(closing.isCompleted)

            releasePrepare.complete(Unit)
            val startFailure = assertIs<CodexOperationException>(starting.await().exceptionOrNull())
            val closeFailure = assertIs<CodexOperationException>(closing.await().exceptionOrNull())
            assertEquals("host_close_failed", startFailure.failure.code)
            assertEquals("host_close_failed", closeFailure.failure.code)
            assertEquals("late runtime close failed", closeFailure.cause?.message)
            assertTrue(delegate.allClientStreamsClosed())
        } finally {
            releasePrepare.complete(Unit)
            runCatching { host.close() }
        }
    }

    @Test
    fun closeConversationDoesNotWaitForAnOverlappingOpenRequest(): Unit = runBlocking {
        val startRequested = CountDownLatch(1)
        val releaseStart = CountDownLatch(1)
        val staleApprovalRejected = CountDownLatch(1)
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> {
                    startRequested.countDown()
                    check(releaseStart.await(5, TimeUnit.SECONDS))
                    server.respond(message.id, buildJsonObject {
                        putJsonObject("thread") { put("id", "thread-overlap") }
                    })
                }
                null -> if (message.id == 904L) staleApprovalRejected.countDown()
            }
        }
        val workspace = CodexWorkspace("/workspace", "Workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            this,
            clientInfo = TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            val opening = async(start = CoroutineStart.UNDISPATCHED) { agent.openConversation() }
            withTimeout(1_000) {
                while (startRequested.count != 0L) yield()
            }

            val retained = assertNotNull(agent.activeConversation.value)
            withTimeout(1_000) { retained.close() }
            assertNull(agent.activeConversation.value)
            assertEquals(AgentConversationStatus.CLOSED, retained.state.value.status)

            releaseStart.countDown()
            assertFailsWith<CancellationException> { opening.await() }
            assertNull(agent.activeConversation.value)
            runtime.request(
                904,
                "item/commandExecution/requestApproval",
                hostApprovalRequest("thread-overlap", "turn-overlap"),
            )
            assertTrue(staleApprovalRejected.await(1, TimeUnit.SECONDS))
        } finally {
            releaseStart.countDown()
            host.close()
        }
    }

    @Test
    fun rejectedConversationOpenDoesNotStartAnEventObserver(): Unit = runBlocking {
        val logoutRequest = CompletableDeferred<Pair<Long, FakeCodexRuntime>>()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/logout" -> logoutRequest.complete(checkNotNull(message.id) to server)
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            this,
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            val signingOut = async(start = CoroutineStart.UNDISPATCHED) {
                agent.authentication.signOut()
            }
            val (requestId, server) = withTimeout(1_000) { logoutRequest.await() }
            try {
                val activeJobsBefore = checkNotNull(coroutineContext[Job]).activeDescendantCount()
                assertFailsWith<IllegalStateException> { agent.conversations.open() }

                assertEquals(activeJobsBefore, checkNotNull(coroutineContext[Job]).activeDescendantCount())
                assertNull(agent.conversations.active.value)
            } finally {
                server.respond(requestId, buildJsonObject {})
                signingOut.await()
            }
        } finally {
            host.close()
        }
    }

    @Test
    fun closedConversationsAreNotRetainedInAnAgentCollection(): Unit = runBlocking {
        val threadIds = AtomicInteger()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-${threadIds.incrementAndGet()}") }
                })
            }
        }
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(CodexWorkspace("/workspace"))),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            repeat(32) { agent.conversations.open().close() }

            assertEquals(0, agent.directlyRetainedClosedConversationCount())
        } finally {
            host.close()
        }
    }

    @Test
    fun cancellingCloseConversationStillClosesAndDetachesTheConversation(): Unit = runBlocking {
        val interruptRequest = CompletableDeferred<Long>()
        val staleApprovalRejected = CountDownLatch(1)
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-cancel-close") }
                })
                "turn/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-cancel-close") }
                })
                "turn/interrupt" -> interruptRequest.complete(checkNotNull(message.id))
                null -> if (message.id == 901L) staleApprovalRejected.countDown()
            }
        }
        val workspace = CodexWorkspace("/workspace", "Workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            this,
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            val conversation = agent.openConversation()
            conversation.send(AgentTurnRequest("hello"))

            val closing = async(start = CoroutineStart.UNDISPATCHED) { conversation.close() }
            val interruptId = withTimeout(1_000) { interruptRequest.await() }
            closing.cancel()
            runtime.respond(interruptId, buildJsonObject {})

            assertFailsWith<CancellationException> { closing.await() }
            assertNull(agent.activeConversation.value)
            assertEquals(AgentConversationStatus.CLOSED, conversation.state.value.status)
            runtime.request(
                901,
                "item/commandExecution/requestApproval",
                hostApprovalRequest("thread-cancel-close", "turn-cancel-close"),
            )
            assertTrue(staleApprovalRejected.await(1, TimeUnit.SECONDS))
            assertTrue(agent.interactionState.value.pending.isEmpty())
        } finally {
            host.close()
        }
    }

    @Test
    fun cancellingABlockedTurnStartDoesNotDelayConversationClose(): Unit = runBlocking {
        val turnStartRequested = CountDownLatch(1)
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-cancel-send") }
                })
                "turn/start" -> turnStartRequested.countDown()
            }
        }
        val workspace = CodexWorkspace("/workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            TEST_CLIENT_INFO,
        )
        try {
            host.start()
            val conversation = readyAgent(host).openConversation()
            val sending = async(start = CoroutineStart.UNDISPATCHED) { conversation.send("hello") }
            withTimeout(5_000) {
                while (turnStartRequested.count != 0L) yield()
            }
            sending.cancel()
            assertFailsWith<CancellationException> { sending.await() }
            assertEquals(AgentConversationStatus.FAILED, conversation.state.value.status)

            withTimeout(1_000) { conversation.close() }
            assertEquals(AgentConversationStatus.CLOSED, conversation.state.value.status)
        } finally {
            host.close()
        }
    }

    @Test
    fun gracefulCloseTimeoutStillClosesAndDetachesTheConversation(): Unit = runBlocking {
        val staleApprovalRejected = CountDownLatch(1)
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-close-timeout") }
                })
                "turn/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-close-timeout") }
                })
                "turn/interrupt" -> Unit
                null -> if (message.id == 902L) staleApprovalRejected.countDown()
            }
        }
        val workspace = CodexWorkspace("/workspace", "Workspace")
        val host = CodexHost(
            FakePlatformSupport(
                FakeWorkspaceStore(CodexWorkspaceResolution.Available(workspace)),
                ArrayDeque<FakeCodexRuntime>().apply { add(runtime) },
            ),
            this,
            TEST_CLIENT_INFO,
            requestTimeoutMillis = 50,
        )
        try {
            host.start()
            val agent = readyAgent(host)
            val conversation = agent.openConversation()
            conversation.send(AgentTurnRequest("hello"))

            withTimeout(1_000) { conversation.close() }
            assertNull(agent.activeConversation.value)
            assertEquals(AgentConversationStatus.CLOSED, conversation.state.value.status)
            runtime.request(
                902,
                "item/commandExecution/requestApproval",
                hostApprovalRequest("thread-close-timeout", "turn-close-timeout"),
            )
            assertTrue(staleApprovalRejected.await(1, TimeUnit.SECONDS))
            assertTrue(agent.interactionState.value.pending.isEmpty())
        } finally {
            host.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentConversationState#property:conversationId#sha256:f6d329a5729a719f0b8095c25f1d2728397f486cc580634699ded378058e2ea4",
        "api-v1:CodexConversations#property:active#sha256:51f563ccfb23b3619f03442768195a4a46a9a0ad7cc4684c4a4b918b3cdd910a",
        "api-v1:CodexHost#constructor:<init>#sha256:e01e9e81541906e439d36a508a657a208b2de603e5c12a69841df6d33a0c9b0d",
        "api-v1:CodexHost#function:close#sha256:7162d5c35564c04a1748f00e59c1a4f4e29ab328c33013d84ce80899144b317d",
        "api-v1:CodexHost#function:selectWorkspace#sha256:95f020ad538882bdb4937c43fa6100064993e7e73f90858607b430566f6b759e",
        "api-v1:CodexHost#function:start#sha256:7885840abf9ffae9c432a01d1b625ba9da051574290b1eb24944b9d2bcfc66a8",
        "api-v1:CodexHost#property:lifecycleState#sha256:530c20068ea1f147d4e2cd87e3d4a7d116205064825b2c5e2dd7788deebbb164",
        "api-v1:CodexHostState.Failed#constructor:<init>#sha256:6b173df69eda3640954bcf72e592f58acfef5923b702473a580ef73432d93b60",
        "api-v1:CodexHostState.Failed#property:failure#sha256:4c857a428aab1bc9e6dc2752f8f02597cee73deef5f73a6840499fc4846206a4",
        "api-v1:CodexHostState.Failed#property:workspace#sha256:29f650191156a988a7bc3f28775875d026f26fa2ea9897c5ee695ec520c90778",
        "api-v1:CodexHostState.Ready#constructor:<init>#sha256:bbab17fde3424d747ab4d8e791198a63738ed40aec4633c06e65c5081436e835",
        "api-v1:CodexHostState.Ready#property:agent#sha256:9d964c550c89f365ba10fa5135f0093371eb9252d9adc0072a2463bf5b49ec4a",
        "api-v1:CodexHostState.WorkspaceRequired#constructor:<init>#sha256:b2bd8add02cbfa2c44bc8feb0d057cb810714e3cc1cedff07f147a37ee32c332",
        "api-v1:CodexHostState.WorkspaceRequired#property:requirement#sha256:db2d8accfa2ebd83f04cc6c1e66cd028b49cfb1ebe76a0d340cfa6e02f8d75b7",
        "api-v1:CodexPathWorkspaceSelection#constructor:<init>#sha256:f267155b28d3890ac579ce9d7d3726772dd71a576814dcc8058a4ced24df33e3",
        "api-v1:CodexPathWorkspaceSelection#property:path#sha256:d4f0303b78fe110d49d695f6a30cb0f96977c284ccb7b3bc9d75d7c27abf1b91",
        "api-v1:CodexWorkspaceResolution.Available#constructor:<init>#sha256:080ecff0867650b076c57a1513364c1f3838e3560de5ff674a80361e4f0c249e",
        "api-v1:CodexWorkspaceResolution.Available#property:workspace#sha256:b91e8c45f3f4c667a0192ae3385bad0c7b3fc9cbe710c0d04310fa7b30509231",
        "api-v1:CodexWorkspaceResolution.SelectionRequired#constructor:<init>#sha256:e3997a8a3d4c7239045142ca1f6ea3b0c2139cd15a6d606801f3177dc0405685",
        "api-v1:CodexWorkspaceResolution.SelectionRequired#property:reason#sha256:3e34abc2a345a5dfa0d3bb41c62ab9ae7152bbe313ab4efdf769517f88f02ec0",
        "api-v1:CodexWorkspaceSelectionReason#enum-entry:NOT_FOUND#sha256:b761c39041169dfec8948b0926594a98e6b7393062e78e7a9afca0e63f403c3f",
    )
    fun restoresSelectsReplacesRetriesAndClosesOneOwnedGraph(): Unit = runBlocking {
        val runtimes = ArrayDeque<FakeCodexRuntime>()
        val threadIds = AtomicInteger()
        val conversationWorkspaces = mutableListOf<String?>()
        repeat(3) { runtimes += hostRuntime(threadIds, conversationWorkspaces) }
        val workspaceOne = CodexWorkspace("/workspace/one", "One")
        val workspaceTwo = CodexWorkspace("/workspace/two", "Two")
        val store = FakeWorkspaceStore(
            restoreResult = CodexWorkspaceResolution.SelectionRequired(
                CodexWorkspaceSelectionReason.NOT_FOUND,
                "Choose a workspace",
            ),
        )
        val support = FakePlatformSupport(store, runtimes)
        val host = CodexHost(support, this, clientInfo = TEST_CLIENT_INFO)

        assertIs<CodexHostState.New>(host.lifecycleState.value)
        host.start()
        val required = assertIs<CodexHostState.WorkspaceRequired>(host.lifecycleState.value)
        assertEquals(CodexWorkspaceSelectionReason.NOT_FOUND, required.requirement.reason)
        assertFailsWith<IllegalStateException> { host.start() }

        store.selectResult = CodexWorkspaceResolution.Available(workspaceOne)
        host.selectWorkspace(CodexPathWorkspaceSelection(workspaceOne.path))
        val firstAgent = readyAgent(host)
        assertEquals(AgentIntegrationAuthorizationStatus.IDLE, firstAgent.integrationAuthorization.state.value.status)
        firstAgent.models.list()
        val firstRuntime = support.preparedRuntimes[0]

        val firstConversation = firstAgent.conversations.open()
        assertSame(firstConversation, firstAgent.conversations.active.value)
        val firstConversationId = firstConversation.state.value.conversationId
        assertEquals("/workspace/one", conversationWorkspaces.last())
        val secondConversation = firstAgent.conversations.open()
        val secondConversationId = secondConversation.state.value.conversationId
        assertTrue(firstConversationId != secondConversationId)
        assertEquals(AgentConversationStatus.CLOSED, firstConversation.state.value.status)
        assertFailsWith<IllegalStateException> { firstConversation.reload() }

        store.selectResult = CodexWorkspaceResolution.Available(workspaceTwo)
        host.selectWorkspace(CodexPathWorkspaceSelection(workspaceTwo.path))
        val secondAgent = readyAgent(host)
        assertNull(secondAgent.conversations.active.value)
        assertFailsWith<IllegalStateException> { firstAgent.models.list() }
        assertTrue(firstRuntime.allClientStreamsClosed())

        support.failNextPrepare = true
        store.selectResult = CodexWorkspaceResolution.Available(CodexWorkspace("/workspace/three", "Three"))
        assertFailsWith<CodexOperationException> {
            host.selectWorkspace(CodexPathWorkspaceSelection("/workspace/three"))
        }
        val failed = assertIs<CodexHostState.Failed>(host.lifecycleState.value)
        assertEquals("/workspace/three", failed.workspace?.path)
        assertEquals("Could not prepare Codex", failed.failure.message)
        host.start()
        val thirdAgent = readyAgent(host)
        thirdAgent.models.list()

        val signedOutConversation = thirdAgent.conversations.open()
        thirdAgent.authentication.signOut()
        assertNull(thirdAgent.conversations.active.value)
        assertEquals(AgentConversationStatus.CLOSED, signedOutConversation.state.value.status)
        assertFailsWith<IllegalStateException> {
            signedOutConversation.send(AgentTurnRequest("after sign-out"))
        }

        host.close()
        host.close()
        assertIs<CodexHostState.Closed>(host.lifecycleState.value)
        assertFailsWith<IllegalStateException> { thirdAgent.models.list() }
        signedOutConversation.close()
        assertTrue(support.preparedRuntimes.last().allClientStreamsClosed())
    }
}

private fun readyAgent(host: CodexHost): CodexAgent =
    assertIs<CodexHostState.Ready>(host.lifecycleState.value).agent

private class FakeWorkspaceStore(
    var restoreResult: CodexWorkspaceResolution,
) : CodexWorkspaceStore {
    lateinit var selectResult: CodexWorkspaceResolution

    override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution = selectResult

    override suspend fun restore(): CodexWorkspaceResolution = restoreResult

    override suspend fun clear() = Unit
}

private class FakePlatformSupport(
    override val workspaceStore: CodexWorkspaceStore,
    private val runtimes: ArrayDeque<FakeCodexRuntime>,
) : CodexPlatform {
    val preparedRuntimes = mutableListOf<FakeCodexRuntime>()
    var failNextPrepare = false

    override val authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }

    override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
        if (failNextPrepare) {
            failNextPrepare = false
            error("prepare failed")
        }
        val runtime = runtimes.removeFirst()
        preparedRuntimes += runtime
        return PreparedCodexRuntime(
            runtimeFactory = { runtime },
            workspacePath = workspace.path,
            features = CodexRuntimeFeature.entries.toSet(),
        )
    }
}

private val TEST_CLIENT_INFO = CodexClientInfo("codex_agent_tests", "Codex Agent Tests", "test")

private fun Job.activeDescendantCount(): Int = children.sumOf { child ->
    (if (child.isActive) 1 else 0) + child.activeDescendantCount()
}

private fun CodexAgent.directlyRetainedClosedConversationCount(): Int =
    javaClass.declaredFields.sumOf { field ->
        field.isAccessible = true
        when (val value = field.get(this)) {
            is Map<*, *> -> (value.keys + value.values).count { it is CodexConversation }
            is Iterable<*> -> value.count { it is CodexConversation }
            else -> 0
        }
    }

private fun hostRuntime(
    threadIds: AtomicInteger,
    conversationWorkspaces: MutableList<String?>,
): FakeCodexRuntime = FakeCodexRuntime { message, server ->
    when (message.method) {
        "initialize" -> server.respond(message.id, buildJsonObject {})
        "model/list" -> server.respond(message.id, buildJsonObject { putJsonArray("data") {} })
        "account/logout" -> server.respond(message.id, buildJsonObject {})
        "thread/start" -> {
            conversationWorkspaces += message.params.optionalString("cwd")
            val id = "thread-${threadIds.incrementAndGet()}"
            server.respond(message.id, buildJsonObject { putJsonObject("thread") { put("id", id) } })
        }
    }
}

private fun hostApprovalRequest(conversationId: String, turnId: String) = buildJsonObject {
    put("itemId", "item-1")
    put("startedAtMs", 1)
    put("threadId", conversationId)
    put("turnId", turnId)
    put("command", "git status")
}
