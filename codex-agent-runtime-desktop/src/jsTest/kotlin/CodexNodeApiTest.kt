import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentCapability as CoreCapability
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
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
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
        val prepareEntered = CompletableDeferred<Unit>()
        val prepareRelease = CompletableDeferred<Unit>()
        val platform = ApiTestPlatform(
            runtime = runtime,
            restoreResolution = CodexWorkspaceResolution.SelectionRequired(
                CodexWorkspaceSelectionReason.NOT_FOUND,
                "Choose a workspace",
            ),
            prepareEntered = prepareEntered,
            prepareRelease = prepareRelease,
        )
        val core = CoreHost(platform, CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val hostStates = mutableListOf<CodexHostState>()
        val hostObservation = host.observeState { hostStates += it }

        AgentApprovalPreset.entries.forEach { preset ->
            assertEquals(preset.displayName, codexApprovalPresetDisplayName(preset.name.lowercase()))
        }
        val invalidPreset = runCatching { codexApprovalPresetDisplayName("sometimes") }.exceptionOrNull()
        assertEquals("Unknown approval preset: sometimes", invalidPreset?.message)

        val webSearch = CoreCapability.WEB_SEARCH
        assertEquals(webSearch.id, agentCapabilityId("web_search"))
        assertEquals(webSearch.displayLabel, agentCapabilityDisplayLabel("web_search"))
        assertEquals(webSearch.icon, agentCapabilityIcon("web_search"))
        assertEquals(webSearch.promptLabel, agentCapabilityPromptLabel("web_search"))
        val invalidCapability = runCatching { agentCapabilityId("filesystem") }.exceptionOrNull()
        assertEquals("Unknown agent capability: filesystem", invalidCapability?.message)
        listOf(
            runCatching {
                agentCapabilityId(js("({})").unsafeCast<String>())
            }.exceptionOrNull(),
            runCatching {
                agentCapabilityDisplayLabel(js("1").unsafeCast<String>())
            }.exceptionOrNull(),
            runCatching {
                agentCapabilityIcon(js("true").unsafeCast<String>())
            }.exceptionOrNull(),
            runCatching {
                agentCapabilityPromptLabel(js("BigInt(1)").unsafeCast<String>())
            }.exceptionOrNull(),
        ).forEach { error -> assertEquals("capability must be a string", error?.message) }

        val skillInvocation = AgentSkillInvocation("review", "/skills/review/SKILL.md")
        val pluginInvocation = AgentPluginInvocation("drive", "plugin://drive@catalog")
        val localInvocations: Array<AgentInvocation> = arrayOf(skillInvocation, pluginInvocation)
        assertEquals(listOf("review", "drive"), localInvocations.map(AgentInvocation::name))
        assertEquals(
            listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
            localInvocations.map(AgentInvocation::key),
        )
        assertEquals("/skills/review/SKILL.md", skillInvocation.path)
        assertEquals("plugin://drive@catalog", pluginInvocation.uri)
        localInvocations.forEach {
            assertTrue(isFrozen(it))
            assertEquals(0, enumerablePropertyCount(it))
        }
        listOf(
            runCatching {
                AgentSkillInvocation(js("({})").unsafeCast<String>(), "/skill")
            }.exceptionOrNull() to "name must be a string",
            runCatching {
                AgentSkillInvocation("skill", js("({})").unsafeCast<String>())
            }.exceptionOrNull() to "path must be a string",
            runCatching {
                AgentPluginInvocation(js("({})").unsafeCast<String>(), "plugin://drive@catalog")
            }.exceptionOrNull() to "name must be a string",
            runCatching {
                AgentPluginInvocation("drive", js("({})").unsafeCast<String>())
            }.exceptionOrNull() to "uri must be a string",
        ).forEach { (error, message) -> assertEquals(message, error?.message) }

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

        val localConnectorIntegration = AgentConnectorIntegration(localConnector)
        assertEquals("connector-local", localConnectorIntegration.id)
        assertEquals("Local connector", localConnectorIntegration.displayName)
        assertEquals("connector-local", localConnectorIntegration.connector.id)
        assertTrue(isFrozen(localConnectorIntegration))
        assertTrue(isFrozen(localConnectorIntegration.connector))
        assertEquals(
            "connector must be an AgentConnector",
            runCatching {
                AgentConnectorIntegration(js("({})").unsafeCast<AgentConnector>())
            }.exceptionOrNull()?.message,
        )
        val invalidConnector = runCatching {
            AgentConnector(js("({})").unsafeCast<String>(), "Invalid")
        }.exceptionOrNull()
        assertEquals("id must be a string", invalidConnector?.message)

        val localPluginReference = AgentPluginReference(
            "drive@openai-curated",
            "drive",
            "openai-curated",
            remotePluginId = REMOTE_PLUGIN_ID,
        )
        assertEquals("plugin://drive@openai-curated", localPluginReference.uri)
        assertNull(localPluginReference.marketplacePath)
        assertEquals(REMOTE_PLUGIN_ID, localPluginReference.remotePluginId)
        assertTrue(isFrozen(localPluginReference))
        val sourcePluginCapabilities = arrayOf("Search files", "Share files")
        val localPluginSummary = AgentPluginSummary(
            localPluginReference,
            "Drive",
            "Files in Drive",
            true,
            true,
            "available",
            "on_install",
            true,
            sourcePluginCapabilities,
            "#4285f4",
            "https://example.com/privacy",
            "https://example.com/terms",
            "https://example.com",
        )
        sourcePluginCapabilities[0] = "changed"
        assertEquals(listOf("Search files", "Share files"), localPluginSummary.capabilities.toList())
        assertEquals("available", localPluginSummary.installPolicy)
        assertEquals("on_install", localPluginSummary.authPolicy)
        assertEquals("#4285f4", localPluginSummary.brandColor)
        assertTrue(isFrozen(localPluginSummary))
        assertTrue(isFrozen(localPluginSummary.reference))
        assertTrue(isFrozen(localPluginSummary.capabilities))
        val sourcePluginSummaries = arrayOf(localPluginSummary)
        val sourcePluginErrors = arrayOf("catalog warning")
        val localPluginCatalog = AgentPluginCatalog(sourcePluginSummaries, sourcePluginErrors, "stale_cache")
        sourcePluginSummaries[0] = AgentPluginSummary(
            localPluginReference,
            "Changed",
            "Changed",
            false,
            false,
            "not_available",
            "on_use",
            false,
        )
        sourcePluginErrors[0] = "changed"
        assertEquals(listOf("Drive"), localPluginCatalog.plugins.map(AgentPluginSummary::displayName))
        assertEquals(listOf("catalog warning"), localPluginCatalog.errors.toList())
        assertEquals("stale_cache", localPluginCatalog.freshness)
        assertTrue(isFrozen(localPluginCatalog))
        assertTrue(isFrozen(localPluginCatalog.plugins))
        assertTrue(isFrozen(localPluginCatalog.errors))
        assertTrue(isFrozen(localPluginCatalog.plugins.single()))
        val localPluginSkill = AgentPluginSkill("search-drive", "Search Drive", true, "/plugin/SKILL.md")
        val localPluginDetail = AgentPluginDetail(
            localPluginSummary,
            "Complete Drive plugin",
            arrayOf(localPluginSkill),
            arrayOf(localConnector),
            arrayOf("drive-mcp"),
            1,
        )
        assertEquals("search-drive", localPluginDetail.skills.single().name)
        assertEquals("connector-local", localPluginDetail.connectors.single().id)
        assertEquals(listOf("drive-mcp"), localPluginDetail.mcpServers.toList())
        assertEquals(1, localPluginDetail.hookCount)
        assertTrue(isFrozen(localPluginDetail))
        assertTrue(isFrozen(localPluginDetail.summary))
        assertTrue(isFrozen(localPluginDetail.skills))
        assertTrue(isFrozen(localPluginDetail.connectors))
        assertTrue(isFrozen(localPluginDetail.mcpServers))
        val localPluginInstallResult = AgentPluginInstallResult(
            "on_install",
            arrayOf(localConnector),
            "Authorize Drive",
        )
        assertEquals("on_install", localPluginInstallResult.authPolicy)
        assertEquals("connector-local", localPluginInstallResult.connectorsNeedingAuthentication.single().id)
        assertEquals("Authorize Drive", localPluginInstallResult.message)
        assertTrue(isFrozen(localPluginInstallResult))
        assertTrue(isFrozen(localPluginInstallResult.connectorsNeedingAuthentication))
        listOf(
            runCatching {
                AgentPluginReference(js("({})").unsafeCast<String>(), "drive", "catalog")
            }.exceptionOrNull() to "id must be a string",
            runCatching {
                AgentPluginSummary(
                    localPluginReference,
                    "Drive",
                    "Drive",
                    true,
                    true,
                    "AVAILABLE",
                    "on_install",
                    true,
                )
            }.exceptionOrNull() to "Unknown plugin install policy: AVAILABLE",
            runCatching {
                AgentPluginCatalog(
                    js("new Array(1)").unsafeCast<Array<AgentPluginSummary>>(),
                )
            }.exceptionOrNull() to "plugins must not contain sparse elements",
            runCatching {
                AgentPluginDetail(
                    localPluginSummary,
                    "Drive",
                    emptyArray(),
                    emptyArray(),
                    emptyArray(),
                    js("2147483648").unsafeCast<Int>(),
                )
            }.exceptionOrNull() to "hookCount must be an integer or null",
            runCatching {
                AgentPluginInstallResult(
                    "on_install",
                    js("[{}]").unsafeCast<Array<AgentConnector>>(),
                )
            }.exceptionOrNull() to
                "connectorsNeedingAuthentication[0] must be an AgentConnector",
        ).forEach { (error, message) -> assertEquals(message, error?.message) }

        val sourceMcpArguments = arrayOf("server.js")
        val sourceMcpEnvironment: dynamic = js("({ TOKEN: 'value' })")
        val sourceForwardedEnvironment = arrayOf(AgentMcpEnvironmentVariable("HOME", "local"))
        val localMcpTransport = AgentMcpStdioTransport(
            "node",
            sourceMcpArguments,
            "/workspace",
            sourceMcpEnvironment,
            sourceForwardedEnvironment,
        )
        sourceMcpArguments[0] = "changed"
        sourceMcpEnvironment.TOKEN = "changed"
        sourceForwardedEnvironment[0] = AgentMcpEnvironmentVariable("CHANGED")
        assertEquals(listOf("server.js"), localMcpTransport.arguments.toList())
        assertEquals("value", localMcpTransport.environment.asDynamic().TOKEN as String)
        assertEquals(listOf("HOME"), localMcpTransport.forwardedEnvironment.map { it.name })
        assertTrue(isFrozen(localMcpTransport))
        assertTrue(isFrozen(localMcpTransport.arguments))
        assertTrue(isFrozen(checkNotNull(localMcpTransport.environment)))
        assertTrue(isFrozen(localMcpTransport.forwardedEnvironment))
        assertTrue(isFrozen(localMcpTransport.forwardedEnvironment.single()))

        val localMcpHttpTransport = AgentMcpHttpTransport(
            "https://mcp.example.com",
            "MCP_TOKEN",
            js("({ 'X-Static': 'value' })"),
            js("({ Authorization: 'MCP_AUTH' })"),
            "mcp-headers",
        )
        val localMcpTools: dynamic = js("({})")
        localMcpTools.write = AgentMcpToolConfiguration("prompt")
        val localMcpConfiguration = AgentMcpServerConfiguration(
            name = "remote",
            transport = localMcpHttpTransport,
            authentication = "chat_gpt",
            isEnabled = false,
            isRequired = true,
            supportsParallelToolCalls = true,
            omitToolsFrom = arrayOf("code_mode", "deferred"),
            startupTimeoutSeconds = 3.5,
            toolTimeoutSeconds = 9.0,
            defaultToolApproval = "writes",
            enabledTools = arrayOf("read"),
            disabledTools = emptyArray(),
            scopes = arrayOf("files.read"),
            oauth = AgentMcpOauthConfiguration("client", 9876),
            oauthResource = "https://mcp.example.com/resource",
            tools = localMcpTools,
        )
        assertEquals("remote", localMcpConfiguration.name)
        assertEquals("chat_gpt", localMcpConfiguration.authentication)
        assertEquals("local", localMcpConfiguration.environmentId)
        assertFalse(localMcpConfiguration.isEnabled)
        assertTrue(localMcpConfiguration.isRequired)
        assertTrue(localMcpConfiguration.supportsParallelToolCalls)
        assertEquals(listOf("code_mode", "deferred"), localMcpConfiguration.omitToolsFrom?.toList())
        assertEquals(3.5, localMcpConfiguration.startupTimeoutSeconds)
        assertEquals(9.0, localMcpConfiguration.toolTimeoutSeconds)
        assertEquals("writes", localMcpConfiguration.defaultToolApproval)
        assertEquals(listOf("read"), localMcpConfiguration.enabledTools?.toList())
        assertEquals(emptyList(), localMcpConfiguration.disabledTools?.toList())
        assertEquals(listOf("files.read"), localMcpConfiguration.scopes?.toList())
        assertEquals("client", localMcpConfiguration.oauth?.clientId)
        assertEquals(9876, localMcpConfiguration.oauth?.callbackPort)
        assertEquals("https://mcp.example.com/resource", localMcpConfiguration.oauthResource)
        assertEquals("prompt", localMcpConfiguration.tools.asDynamic().write.approval as String)
        assertTrue(isFrozen(localMcpConfiguration))
        assertTrue(isFrozen(localMcpConfiguration.transport))
        assertTrue(isFrozen(localMcpConfiguration.tools))
        assertTrue(isFrozen(localMcpConfiguration.tools.asDynamic().write.unsafeCast<Any>()))

        val localMcpServer = AgentMcpServer(
            "remote",
            "Remote",
            "oauth",
            localMcpConfiguration,
            "user",
            true,
        )
        assertEquals("oauth", localMcpServer.authStatus)
        assertTrue(localMcpServer.isAuthorized)
        assertTrue(localMcpServer.canRemove)
        assertTrue(isFrozen(localMcpServer))
        assertTrue(isFrozen(checkNotNull(localMcpServer.configuration)))

        val localMcpIntegration = AgentMcpServerIntegration(localMcpServer)
        assertEquals("remote", localMcpIntegration.id)
        assertEquals("Remote", localMcpIntegration.displayName)
        assertEquals("remote", localMcpIntegration.server.name)
        assertTrue(isFrozen(localMcpIntegration))
        assertTrue(isFrozen(localMcpIntegration.server))
        val localAuthorizationState = AgentIntegrationAuthorizationState(
            status = "awaiting_completion",
            target = localMcpIntegration,
        )
        assertEquals("awaiting_completion", localAuthorizationState.status)
        assertIs<AgentMcpServerIntegration>(localAuthorizationState.target)
        assertNull(localAuthorizationState.failure)
        assertTrue(isFrozen(localAuthorizationState))
        assertTrue(isFrozen(checkNotNull(localAuthorizationState.target)))
        assertEquals("idle", AgentIntegrationAuthorizationState().status)
        listOf(
            runCatching {
                AgentMcpServerIntegration(js("({})").unsafeCast<AgentMcpServer>())
            }.exceptionOrNull() to "server must be an AgentMcpServer",
            runCatching {
                AgentIntegrationAuthorizationState(js("({})").unsafeCast<String>())
            }.exceptionOrNull() to "status must be a string",
            runCatching {
                AgentIntegrationAuthorizationState("waiting")
            }.exceptionOrNull() to "Unknown integration authorization status: waiting",
            runCatching {
                AgentIntegrationAuthorizationState(
                    target = js("({})").unsafeCast<AgentIntegration>(),
                )
            }.exceptionOrNull() to
                "target must be an AgentConnectorIntegration, AgentMcpServerIntegration, or null",
        ).forEach { (error, message) -> assertEquals(message, error?.message) }
        listOf(
            runCatching {
                AgentMcpStdioTransport(js("({})").unsafeCast<String>())
            }.exceptionOrNull() to "command must be a string",
            runCatching {
                AgentMcpHttpTransport("http://example.com")
            }.exceptionOrNull() to "MCP HTTP URL must use HTTPS or a loopback HTTP address",
            runCatching {
                AgentMcpServerConfiguration("stdio", localMcpTransport, authentication = "oauth")
            }.exceptionOrNull() to "MCP stdio servers do not support authentication",
            runCatching {
                AgentMcpServer("remote", "Remote", "AUTHORIZED")
            }.exceptionOrNull() to "Unknown MCP auth status: AUTHORIZED",
        ).forEach { (error, message) -> assertEquals(message, error?.message) }

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

        val sourceHookHandler: dynamic = js("({ type: 'command', command: './review', isAsync: true })")
        val localHook = AgentHook(
            key = "hook-local",
            currentHash = "sha256:local",
            isEnabled = true,
            eventName = "preToolUse",
            handler = sourceHookHandler.unsafeCast<AgentHookHandler>(),
            isManaged = false,
            source = "PROJECT",
            sourcePath = "/workspace/.codex/hooks.json",
            timeoutSeconds = javaScriptBigInt("9007199254740993"),
            trustStatus = "untrusted",
            matcher = "Shell",
            statusMessage = "Review commands",
            canUninstall = true,
        )
        sourceHookHandler.command = "changed"
        assertEquals("hook-local", localHook.key)
        assertEquals("sha256:local", localHook.currentHash)
        assertTrue(localHook.isEnabled)
        assertEquals("preToolUse", localHook.eventName)
        assertEquals("command", localHook.handler.asDynamic().type as String)
        assertEquals("./review", localHook.handler.asDynamic().command as String)
        assertTrue(localHook.handler.asDynamic().isAsync as Boolean)
        assertFalse(localHook.isManaged)
        assertEquals("PROJECT", localHook.source)
        assertEquals("/workspace/.codex/hooks.json", localHook.sourcePath)
        assertEquals("9007199254740993", localHook.timeoutSeconds.toString())
        assertEquals("bigint", jsTypeOf(localHook.timeoutSeconds))
        assertEquals("untrusted", localHook.trustStatus)
        assertEquals("Shell", localHook.matcher)
        assertNull(localHook.pluginId)
        assertEquals("Review commands", localHook.statusMessage)
        assertEquals("workspace", localHook.origin)
        assertTrue(localHook.canUninstall)
        assertTrue(localHook.canTrust)
        assertTrue(isFrozen(localHook))
        assertTrue(isFrozen(localHook.handler))
        assertEquals(0, enumerablePropertyCount(localHook))
        assertEquals(setOf("type", "command", "isAsync"), objectKeys(localHook.handler).toSet())

        val sourceHooks = arrayOf(localHook)
        val sourceHookWarnings = arrayOf("warning")
        val sourceHookErrors = arrayOf("error")
        val localHookCatalog = AgentHookCatalog(sourceHooks, sourceHookWarnings, sourceHookErrors)
        sourceHooks[0] = AgentHook(
            "changed", "hash", false, "stop",
            js("({ type: 'prompt' })").unsafeCast<AgentHookHandler>(),
            false, "USER", "/hooks.json", javaScriptBigInt("1"), "trusted",
        )
        sourceHookWarnings[0] = "changed"
        sourceHookErrors[0] = "changed"
        assertEquals(listOf("hook-local"), localHookCatalog.hooks.map(AgentHook::key))
        assertEquals(listOf("warning"), localHookCatalog.warnings.toList())
        assertEquals(listOf("error"), localHookCatalog.errors.toList())
        assertTrue(isFrozen(localHookCatalog))
        assertTrue(isFrozen(localHookCatalog.hooks))
        assertTrue(isFrozen(localHookCatalog.warnings))
        assertTrue(isFrozen(localHookCatalog.errors))
        assertTrue(isFrozen(localHookCatalog.hooks.single()))
        assertTrue(isFrozen(localHookCatalog.hooks.single().handler))

        listOf(
            runCatching {
                AgentHook(
                    "invalid", "hash", true, "stop",
                    js("1").unsafeCast<AgentHookHandler>(), false, "USER", "/hooks.json",
                    javaScriptBigInt("1"), "trusted",
                )
            }.exceptionOrNull() to "handler must be an object",
            runCatching {
                AgentHook(
                    "invalid", "hash", true, "stop",
                    js("({ type: 'command', command: 1, isAsync: false })")
                        .unsafeCast<AgentHookHandler>(),
                    false, "USER", "/hooks.json", javaScriptBigInt("1"), "trusted",
                )
            }.exceptionOrNull() to "handler.command must be a string",
            runCatching {
                AgentHook(
                    "invalid", "hash", true, "stop",
                    js("({ type: 'future' })").unsafeCast<AgentHookHandler>(),
                    false, "USER", "/hooks.json", javaScriptBigInt("1"), "trusted",
                )
            }.exceptionOrNull() to "Unknown hook handler type: future",
            runCatching {
                AgentHook(
                    "invalid", "hash", true, "stop",
                    js("({ type: 'prompt' })").unsafeCast<AgentHookHandler>(),
                    false, "USER", "/hooks.json", js("1").unsafeCast<Long>(), "trusted",
                )
            }.exceptionOrNull() to "timeoutSeconds must be a bigint",
        ).forEach { (error, message) -> assertEquals(message, error?.message) }

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

        val localConversationMessage = CodexMessage(
            id = "message-local",
            clientMessageId = "client-local",
            role = "user",
            text = "Local message",
            collaborationMode = "plan",
            reasoning = "Local reasoning",
            plan = "Local plan",
            shellCommand = "pwd",
            exitCode = 0,
            capabilities = arrayOf("web_search", "web_search"),
            invocations = arrayOf(skillInvocation, pluginInvocation, skillInvocation),
        )
        val sourceConversationMessages = arrayOf(localConversationMessage)
        val localConversation = AgentConversation(localSummary, sourceConversationMessages)
        sourceConversationMessages[0] = CodexMessage(
            id = "changed",
            clientMessageId = null,
            role = "assistant",
            text = "Changed",
            collaborationMode = "default",
            reasoning = null,
            plan = null,
            shellCommand = null,
            exitCode = null,
            capabilities = emptyArray(),
            invocations = emptyArray(),
        )
        assertEquals("thread-local", localConversation.summary.conversationId)
        val localConversationSnapshot = localConversation.messages.single()
        assertEquals("message-local", localConversationSnapshot.id)
        assertEquals("client-local", localConversationSnapshot.clientMessageId)
        assertEquals("user", localConversationSnapshot.role)
        assertEquals("Local message", localConversationSnapshot.text)
        assertEquals("plan", localConversationSnapshot.collaborationMode)
        assertEquals("Local reasoning", localConversationSnapshot.reasoning)
        assertEquals("Local plan", localConversationSnapshot.plan)
        assertEquals("pwd", localConversationSnapshot.shellCommand)
        assertEquals(0, localConversationSnapshot.exitCode)
        assertEquals(listOf("web_search"), localConversationSnapshot.capabilities.toList())
        assertEquals(
            listOf(
                "skill:/skills/review/SKILL.md",
                "plugin:plugin://drive@catalog",
                "skill:/skills/review/SKILL.md",
            ),
            localConversationSnapshot.invocations.map(AgentInvocation::key),
        )
        assertFalse(localConversation.summary === localSummary)
        assertFalse(localConversation.messages === sourceConversationMessages)
        assertFalse(localConversation.messages.single() === localConversationMessage)
        assertFalse(localConversation.messages.single().capabilities === localConversationMessage.capabilities)
        assertFalse(localConversation.messages.single().invocations === localConversationMessage.invocations)
        assertFalse(
            localConversation.messages.single().invocations[0] === localConversationMessage.invocations[0],
        )
        assertTrue(isFrozen(localConversation))
        assertTrue(isFrozen(localConversation.summary))
        assertTrue(isFrozen(localConversation.messages))
        assertTrue(isFrozen(localConversation.messages.single()))
        assertTrue(isFrozen(localConversation.messages.single().capabilities))
        assertTrue(isFrozen(localConversation.messages.single().invocations))
        localConversation.messages.single().invocations.forEach { assertTrue(isFrozen(it)) }
        assertEquals(0, enumerablePropertyCount(localConversation))
        val invalidConversationSummary = runCatching {
            AgentConversation(
                js("({})").unsafeCast<AgentConversationSummary>(),
                emptyArray(),
            )
        }.exceptionOrNull()
        assertEquals("summary must be an AgentConversationSummary", invalidConversationSummary?.message)
        val nonArrayMessages = runCatching {
            AgentConversation(
                localSummary,
                js("({ length: 0 })").unsafeCast<Array<CodexMessage>>(),
            )
        }.exceptionOrNull()
        assertEquals("messages must be an array", nonArrayMessages?.message)
        val sparseMessages = runCatching {
            AgentConversation(localSummary, js("new Array(1)").unsafeCast<Array<CodexMessage>>())
        }.exceptionOrNull()
        assertEquals("messages must not contain sparse elements", sparseMessages?.message)
        val hostileMessage = runCatching {
            AgentConversation(localSummary, js("[{}]").unsafeCast<Array<CodexMessage>>())
        }.exceptionOrNull()
        assertEquals("messages[0] must be a CodexMessage", hostileMessage?.message)
        val forgedCodexMessage = CodexMessage(
            id = "forged",
            clientMessageId = null,
            role = "user",
            text = "Forged",
            collaborationMode = "default",
            reasoning = null,
            plan = null,
            shellCommand = null,
            exitCode = null,
            capabilities = js("({})").unsafeCast<Array<String>>(),
            invocations = emptyArray(),
        )
        val hostileNestedMessage = runCatching {
            AgentConversation(localSummary, arrayOf(forgedCodexMessage))
        }.exceptionOrNull()
        assertEquals("capabilities must be an array", hostileNestedMessage?.message)
        val outOfRangeExitCodeMessage = CodexMessage(
            id = "forged-exit-code",
            clientMessageId = null,
            role = "assistant",
            text = "Forged",
            collaborationMode = "default",
            reasoning = null,
            plan = null,
            shellCommand = null,
            exitCode = js("2147483648").unsafeCast<Int>(),
            capabilities = emptyArray(),
            invocations = emptyArray(),
        )
        val outOfRangeExitCode = runCatching {
            AgentConversation(localSummary, arrayOf(outOfRangeExitCodeMessage))
        }.exceptionOrNull()
        assertEquals("exitCode must be an integer or null", outOfRangeExitCode?.message)

        yield()
        assertEquals(listOf("new"), hostStates.map(CodexHostState::status))
        assertTrue(isFrozen(host.state))
        assertEquals(0, enumerablePropertyCount(host))
        host.start().await()
        awaitCondition { hostStates.lastOrNull()?.status == "workspace_required" }
        val requiredState = host.state
        assertEquals("workspace_required", requiredState.status)
        assertEquals("not_found", requiredState.selectionReason)
        assertEquals("Choose a workspace", requiredState.selectionMessage)
        assertNull(requiredState.workspace)
        assertNull(requiredState.agent)
        assertNull(requiredState.failure)
        assertTrue(isFrozen(requiredState))
        assertEquals(requiredState.selectionReason, hostStates.last().selectionReason)
        assertEquals(requiredState.selectionMessage, hostStates.last().selectionMessage)

        val selection = host.selectWorkspace("/workspace")
        prepareEntered.await()
        awaitCondition { hostStates.lastOrNull()?.status == "preparing" }
        val preparingState = host.state
        assertEquals("preparing", preparingState.status)
        assertEquals("/workspace", preparingState.workspace?.path)
        assertEquals("/workspace", preparingState.workspace?.displayName)
        assertNull(preparingState.agent)
        assertNull(preparingState.selectionReason)
        assertNull(preparingState.selectionMessage)
        assertNull(preparingState.failure)
        assertTrue(isFrozen(preparingState))
        assertTrue(isFrozen(checkNotNull(preparingState.workspace)))
        assertEquals(preparingState.workspace.path, hostStates.last().workspace?.path)
        prepareRelease.complete(Unit)
        selection.await()
        awaitCondition { hostStates.lastOrNull()?.status == "ready" }
        assertEquals("ready", host.state.status)
        assertEquals("/workspace", platform.selectedWorkspacePath)

        val agent = assertIs<CodexAgent>(host.agent)
        val readyState = host.state
        assertSame(agent, readyState.agent)
        assertEquals("/workspace", readyState.workspace?.path)
        assertEquals("/workspace", readyState.workspace?.displayName)
        assertNull(readyState.selectionReason)
        assertNull(readyState.selectionMessage)
        assertNull(readyState.failure)
        assertTrue(isFrozen(readyState))
        assertTrue(isFrozen(checkNotNull(readyState.workspace)))
        assertSame(agent, hostStates.last().agent)
        assertEquals(readyState.workspace.path, hostStates.last().workspace?.path)
        assertEquals("workspace_required", requiredState.status)
        assertEquals("preparing", preparingState.status)
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
        assertNull(conversation.state.conversation)
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
        assertNull(conversationStates.single().conversation)

        conversation.send("hello").await()
        awaitCondition { conversation.state.status == "running_turn" }
        val activeState = conversation.state
        assertNull(activeState.conversation)
        assertEquals(listOf("hello"), activeState.messages.map(CodexMessage::text))
        val pendingMessage = activeState.messages.single()
        assertEquals("default", pendingMessage.collaborationMode)
        assertTrue(pendingMessage.capabilities.isEmpty())
        assertTrue(pendingMessage.invocations.isEmpty())
        assertTrue(isFrozen(pendingMessage.capabilities))
        assertTrue(isFrozen(pendingMessage.invocations))
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
        awaitCondition("Reconciled conversation did not become current") {
            conversation.state.let { it.status == "ready" && it.conversation != null && it.messages.size == 2 }
        }
        awaitCondition("Reconciled conversation was not observed") {
            conversationStates.any { it.conversation != null && it.messages.size == 2 && !it.isTurnActive }
        }
        val messageState = conversation.state
        val messages = messageState.messages
        assertEquals(listOf("user-1", "assistant-1"), messages.map(CodexMessage::id))
        assertEquals(
            listOf(
                "hello\n${CoreCapability.WEB_SEARCH.promptLabel}\n\$review\n@drive\n\nmalformed",
                "world",
            ),
            messages.map(CodexMessage::text),
        )
        assertEquals(listOf("user", "assistant"), messages.map(CodexMessage::role))
        val liveUserMessage = messages[0]
        assertEquals("client-plan", liveUserMessage.clientMessageId)
        assertEquals("plan", liveUserMessage.collaborationMode)
        assertEquals(listOf("web_search"), liveUserMessage.capabilities.toList())
        assertEquals(listOf("review", "drive"), liveUserMessage.invocations.map(AgentInvocation::name))
        assertEquals(
            listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
            liveUserMessage.invocations.map(AgentInvocation::key),
        )
        assertEquals("/skills/review/SKILL.md", assertIs<AgentSkillInvocation>(
            liveUserMessage.invocations[0],
        ).path)
        assertEquals("plugin://drive@catalog", assertIs<AgentPluginInvocation>(
            liveUserMessage.invocations[1],
        ).uri)
        val liveAssistantMessage = messages[1]
        assertEquals("default", liveAssistantMessage.collaborationMode)
        assertTrue(liveAssistantMessage.capabilities.isEmpty())
        assertTrue(liveAssistantMessage.invocations.isEmpty())
        val reconciledConversation = checkNotNull(messageState.conversation)
        assertEquals("thread-js", reconciledConversation.summary.conversationId)
        assertEquals("History title", reconciledConversation.summary.title)
        assertEquals("-9007199254740993", reconciledConversation.summary.updatedAtEpochSeconds.toString())
        assertEquals("bigint", jsTypeOf(reconciledConversation.summary.updatedAtEpochSeconds))
        val reconciledMessages = reconciledConversation.messages
        assertEquals(listOf("user-1", "assistant-1"), reconciledMessages.map(CodexMessage::id))
        assertEquals(listOf("client-plan", null), reconciledMessages.map(CodexMessage::clientMessageId))
        assertEquals(listOf("user", "assistant"), reconciledMessages.map(CodexMessage::role))
        assertEquals(messages.map(CodexMessage::text), reconciledMessages.map(CodexMessage::text))
        assertEquals(listOf("plan", "default"), reconciledMessages.map(CodexMessage::collaborationMode))
        assertEquals(listOf(null, null), reconciledMessages.map(CodexMessage::reasoning))
        assertEquals(listOf(null, null), reconciledMessages.map(CodexMessage::plan))
        assertEquals(listOf(null, null), reconciledMessages.map(CodexMessage::shellCommand))
        assertEquals(listOf(null, null), reconciledMessages.map(CodexMessage::exitCode))
        assertEquals(
            listOf(listOf("web_search"), emptyList()),
            reconciledMessages.map { it.capabilities.toList() },
        )
        assertEquals(
            listOf(listOf("review", "drive"), emptyList()),
            reconciledMessages.map { message -> message.invocations.map(AgentInvocation::name) },
        )
        assertEquals(
            listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
            reconciledMessages[0].invocations.map(AgentInvocation::key),
        )
        assertEquals(
            "/skills/review/SKILL.md",
            assertIs<AgentSkillInvocation>(reconciledMessages[0].invocations[0]).path,
        )
        assertEquals(
            "plugin://drive@catalog",
            assertIs<AgentPluginInvocation>(reconciledMessages[0].invocations[1]).uri,
        )
        assertFalse(reconciledMessages === messages)
        assertFalse(reconciledMessages[0] === messages[0])
        assertTrue(isFrozen(reconciledConversation))
        assertTrue(isFrozen(reconciledConversation.summary))
        assertTrue(isFrozen(reconciledMessages))
        reconciledMessages.forEach { message ->
            assertTrue(isFrozen(message))
            assertTrue(isFrozen(message.capabilities))
            assertTrue(isFrozen(message.invocations))
            message.invocations.forEach { assertTrue(isFrozen(it)) }
        }
        val observedReconciled = checkNotNull(
            conversationStates.last { it.status == "ready" && it.conversation != null }.conversation,
        )
        assertEquals("thread-js", observedReconciled.summary.conversationId)
        assertFalse(observedReconciled === reconciledConversation)
        assertTrue(isFrozen(observedReconciled))
        assertNull(messageState.turnProgress)
        assertTrue(messageState.canStartTurn)
        assertTrue(messageState.canReload)
        assertFalse(messageState.canCancelTurn)
        assertFalse(messageState.canRunShellCommand)
        assertFalse(messageState.isTurnActive)
        assertTrue(isFrozen(messageState))
        assertTrue(isFrozen(messages))
        messages.forEach { message ->
            assertTrue(isFrozen(message))
            assertTrue(isFrozen(message.capabilities))
            assertTrue(isFrozen(message.invocations))
            assertEquals(0, enumerablePropertyCount(message))
            message.invocations.forEach {
                assertTrue(isFrozen(it))
                assertEquals(0, enumerablePropertyCount(it))
            }
        }
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

        conversation.reload().await()
        awaitCondition("Reloaded conversation did not become current") {
            conversation.state.let { it.status == "ready" && it.conversation != null && it.messages.size == 2 }
        }
        assertSame(conversation, agent.activeConversation)
        assertSame(conversation, active.last())
        val reloadedConversation = checkNotNull(conversation.state.conversation)
        val reloadedMessages = conversation.state.messages
        val reloadedUserMessage = reloadedMessages[0]
        assertEquals("plan", reloadedUserMessage.collaborationMode)
        assertEquals(listOf("web_search"), reloadedUserMessage.capabilities.toList())
        assertEquals(listOf("review", "drive"), reloadedUserMessage.invocations.map(AgentInvocation::name))
        assertEquals(
            listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
            reloadedUserMessage.invocations.map(AgentInvocation::key),
        )
        assertFalse(messages === reloadedMessages)
        assertFalse(liveUserMessage === reloadedUserMessage)
        assertFalse(liveUserMessage.capabilities === reloadedUserMessage.capabilities)
        assertFalse(liveUserMessage.invocations === reloadedUserMessage.invocations)
        assertFalse(liveUserMessage.invocations[0] === reloadedUserMessage.invocations[0])
        assertFalse(reconciledConversation === reloadedConversation)
        assertFalse(reconciledConversation.summary === reloadedConversation.summary)
        assertFalse(reconciledMessages === reloadedConversation.messages)
        assertFalse(reconciledMessages[0] === reloadedConversation.messages[0])
        assertEquals("thread-js", reconciledConversation.summary.conversationId)
        assertEquals(listOf("user-1", "assistant-1"), reconciledMessages.map(CodexMessage::id))
        assertTrue(isFrozen(reloadedConversation))
        assertTrue(isFrozen(reloadedConversation.summary))
        assertTrue(isFrozen(reloadedConversation.messages))
        assertTrue(isFrozen(reloadedMessages))
        reloadedMessages.forEach { message ->
            assertTrue(isFrozen(message))
            assertTrue(isFrozen(message.capabilities))
            assertTrue(isFrozen(message.invocations))
            message.invocations.forEach { assertTrue(isFrozen(it)) }
        }

        val readRequestsBeforeInvalid = runtime.threadReadRequests.size
        val blankReadId = runCatching { agent.readConversation("  ").await() }.exceptionOrNull()
        assertEquals("Conversation ID must not be blank", blankReadId?.message)
        val hostileReadId = runCatching {
            agent.readConversation(js("({})").unsafeCast<String>()).await()
        }.exceptionOrNull()
        assertEquals("conversationId must be a string", hostileReadId?.message)
        assertEquals(readRequestsBeforeInvalid, runtime.threadReadRequests.size)

        yield()
        val activeBeforeHistoryRead = agent.activeConversation
        val observedActiveCountBeforeHistoryRead = active.size
        val observedStateCountBeforeHistoryRead = conversationStates.size
        val history = agent.readConversation("thread-history").await()
        assertEquals(readRequestsBeforeInvalid + 1, runtime.threadReadRequests.size)
        val historyReadRequest = runtime.threadReadRequests.last()
        assertEquals(setOf("includeTurns", "threadId"), historyReadRequest.keys)
        assertEquals("thread-history", historyReadRequest["threadId"]?.jsonPrimitive?.content)
        assertEquals("true", historyReadRequest["includeTurns"]?.jsonPrimitive?.content)
        assertEquals("thread-history", history.summary.conversationId)
        assertEquals("History title", history.summary.title)
        assertEquals("-9007199254740993", history.summary.updatedAtEpochSeconds.toString())
        assertEquals("bigint", jsTypeOf(history.summary.updatedAtEpochSeconds))
        assertEquals(listOf("user-1", "assistant-1"), history.messages.map(CodexMessage::id))
        assertEquals(listOf("user", "assistant"), history.messages.map(CodexMessage::role))
        assertEquals(
            listOf(
                "hello\n${CoreCapability.WEB_SEARCH.promptLabel}\n\$review\n@drive\n\nmalformed",
                "world",
            ),
            history.messages.map(CodexMessage::text),
        )
        val historyUserMessage = history.messages[0]
        assertEquals("client-plan", historyUserMessage.clientMessageId)
        assertEquals("plan", historyUserMessage.collaborationMode)
        assertNull(historyUserMessage.reasoning)
        assertNull(historyUserMessage.plan)
        assertNull(historyUserMessage.shellCommand)
        assertNull(historyUserMessage.exitCode)
        assertEquals(listOf("web_search"), historyUserMessage.capabilities.toList())
        assertEquals(listOf("review", "drive"), historyUserMessage.invocations.map(AgentInvocation::name))
        assertEquals(
            listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
            historyUserMessage.invocations.map(AgentInvocation::key),
        )
        assertEquals(
            "/skills/review/SKILL.md",
            assertIs<AgentSkillInvocation>(historyUserMessage.invocations[0]).path,
        )
        assertEquals(
            "plugin://drive@catalog",
            assertIs<AgentPluginInvocation>(historyUserMessage.invocations[1]).uri,
        )
        val historyAssistantMessage = history.messages[1]
        assertNull(historyAssistantMessage.clientMessageId)
        assertEquals("default", historyAssistantMessage.collaborationMode)
        assertNull(historyAssistantMessage.reasoning)
        assertNull(historyAssistantMessage.plan)
        assertNull(historyAssistantMessage.shellCommand)
        assertNull(historyAssistantMessage.exitCode)
        assertTrue(historyAssistantMessage.capabilities.isEmpty())
        assertTrue(historyAssistantMessage.invocations.isEmpty())
        assertTrue(isFrozen(history))
        assertTrue(isFrozen(history.summary))
        assertTrue(isFrozen(history.messages))
        history.messages.forEach { message ->
            assertTrue(isFrozen(message))
            assertTrue(isFrozen(message.capabilities))
            assertTrue(isFrozen(message.invocations))
            message.invocations.forEach { assertTrue(isFrozen(it)) }
        }
        assertEquals(0, enumerablePropertyCount(history))
        yield()
        assertSame(activeBeforeHistoryRead, agent.activeConversation)
        assertEquals(observedActiveCountBeforeHistoryRead, active.size)
        assertEquals(observedStateCountBeforeHistoryRead, conversationStates.size)
        assertEquals(listOf("user-1", "assistant-1"), conversation.state.messages.map(CodexMessage::id))

        runtime.failNextThreadRead = true
        val historyReadFailure = assertIs<CodexError>(
            runCatching { agent.readConversation("thread-history").await() }.exceptionOrNull(),
        )
        assertEquals("conversation_read_failed", historyReadFailure.code)
        assertEquals("conversation read denied", historyReadFailure.message)
        assertTrue(historyReadFailure.recoverable)
        runtime.mismatchNextThreadRead = true
        val mismatchedHistory = assertIs<CodexError>(
            runCatching { agent.readConversation("thread-history").await() }.exceptionOrNull(),
        )
        assertEquals("conversation_read_failed", mismatchedHistory.code)
        assertEquals("Could not read conversation", mismatchedHistory.message)
        assertTrue(mismatchedHistory.recoverable)
        assertSame(activeBeforeHistoryRead, agent.activeConversation)
        assertEquals(observedActiveCountBeforeHistoryRead, active.size)
        assertEquals(observedStateCountBeforeHistoryRead, conversationStates.size)

        conversation.send("retry").await()
        awaitCondition("Retry did not start") { conversation.state.status == "running_turn" }
        val optimisticRetry = conversation.state
        val retryReconciled = checkNotNull(optimisticRetry.conversation)
        assertEquals(listOf("user-1", "assistant-1"), retryReconciled.messages.map(CodexMessage::id))
        assertEquals(3, optimisticRetry.messages.size)
        assertEquals("retry", optimisticRetry.messages.last().text)
        assertNull(optimisticRetry.turnProgress)
        assertTrue(isFrozen(retryReconciled))
        assertTrue(isFrozen(retryReconciled.messages))

        runtime.emitAgentMessageDelta("retained after failure")
        awaitCondition("Retained progress was not projected") {
            conversation.state.turnProgress?.text == "retained after failure"
        }
        runtime.failTurn()
        awaitCondition("Failed conversation state did not become current") {
            conversation.state.status == "failed"
        }
        val failedConversationState = conversation.state
        assertEquals("turn_failed", failedConversationState.failure?.code)
        assertEquals("retained failure", failedConversationState.failure?.message)
        assertEquals("retained after failure", failedConversationState.turnProgress?.text)
        assertEquals(3, failedConversationState.messages.size)
        assertEquals("retry", failedConversationState.messages.last().text)
        val failedReconciled = checkNotNull(failedConversationState.conversation)
        assertEquals(listOf("user-1", "assistant-1"), failedReconciled.messages.map(CodexMessage::id))
        assertFalse(failedReconciled === reloadedConversation)
        assertFalse(failedReconciled.messages === reloadedConversation.messages)
        assertTrue(isFrozen(failedConversationState))
        assertTrue(isFrozen(checkNotNull(failedConversationState.turnProgress)))
        assertTrue(isFrozen(failedReconciled))
        assertTrue(isFrozen(failedReconciled.summary))
        assertTrue(isFrozen(failedReconciled.messages))
        awaitCondition("Failed conversation state was not observed") {
            conversationStates.any {
                it.status == "failed" && it.turnProgress?.text == "retained after failure" &&
                    it.conversation?.messages?.size == 2 && it.messages.size == 3
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

        platform.failNextPrepare = true
        val prepareFailure = assertIs<CodexError>(
            runCatching { host.selectWorkspace("/failed workspace").await() }.exceptionOrNull(),
        )
        assertEquals("runtime_prepare_failed", prepareFailure.code)
        assertEquals("Could not prepare Codex", prepareFailure.message)
        assertTrue(prepareFailure.recoverable)
        awaitCondition { hostStates.lastOrNull()?.status == "failed" }
        val failedState = host.state
        assertEquals("/failed workspace", failedState.workspace?.path)
        assertEquals("/failed workspace", failedState.workspace?.displayName)
        assertNull(failedState.agent)
        assertNull(failedState.selectionReason)
        assertNull(failedState.selectionMessage)
        assertEquals("runtime_prepare_failed", failedState.failure?.code)
        assertEquals("Could not prepare Codex", failedState.failure?.message)
        assertTrue(checkNotNull(failedState.failure).recoverable)
        assertTrue(isFrozen(failedState))
        assertTrue(isFrozen(checkNotNull(failedState.workspace)))
        assertTrue(isFrozen(checkNotNull(failedState.failure)))
        assertEquals(failedState.workspace.path, hostStates.last().workspace?.path)
        assertEquals(failedState.failure.code, hostStates.last().failure?.code)

        host.close().await()
        host.close().await()
        awaitCondition { hostObservation.isClosed && activeObservation.isClosed }
        assertEquals("closed", hostStates.last().status)
        assertTrue(hostObservation.isClosed)
        assertTrue(activeObservation.isClosed)
        assertTrue(runtime.closed)
        hostStates.forEach { state ->
            assertTrue(isFrozen(state))
            state.workspace?.let { assertTrue(isFrozen(it)) }
            state.failure?.let { assertTrue(isFrozen(it)) }
        }

        val restoreFailureRuntime = ApiTestRuntime()
        val restoreFailureHost = wrapCodexHost(CoreHost(
            ApiTestPlatform(
                runtime = restoreFailureRuntime,
                restoreFailure = IllegalStateException("restore denied"),
            ),
            CodexClientInfo("node_test", "Node Test", "test"),
        ))
        val restoreFailureStates = mutableListOf<CodexHostState>()
        val restoreFailureObservation = restoreFailureHost.observeState { restoreFailureStates += it }
        val restoreFailure = assertIs<CodexError>(
            runCatching { restoreFailureHost.start().await() }.exceptionOrNull(),
        )
        assertEquals("workspace_restore_failed", restoreFailure.code)
        assertEquals("Could not restore the Codex workspace", restoreFailure.message)
        assertTrue(restoreFailure.recoverable)
        awaitCondition { restoreFailureStates.lastOrNull()?.status == "failed" }
        val restorationFailedState = restoreFailureHost.state
        assertNull(restorationFailedState.workspace)
        assertNull(restorationFailedState.agent)
        assertNull(restorationFailedState.selectionReason)
        assertNull(restorationFailedState.selectionMessage)
        assertEquals("workspace_restore_failed", restorationFailedState.failure?.code)
        assertTrue(isFrozen(restorationFailedState))
        assertTrue(isFrozen(checkNotNull(restorationFailedState.failure)))
        assertNull(restoreFailureStates.last().workspace)
        assertEquals(restorationFailedState.failure.code, restoreFailureStates.last().failure?.code)
        restoreFailureHost.close().await()
        awaitCondition { restoreFailureObservation.isClosed }
        assertEquals("closed", restoreFailureStates.last().status)
        assertFalse(restoreFailureRuntime.started)

        val skillFixture = createSkillTestFixture()
        val shellRuntime = ApiTestRuntime().apply {
            skillWorkspacePath = skillFixture.workspacePath
            skillManifestPath = skillFixture.sourceManifestPath
            hookInstalledSourcePath = skillFixture.installedHookConfigPath
        }
        val authorizationBrowser = RecordingAuthorizationBrowser()
        val shellHost = wrapCodexHost(CoreHost(
            ApiTestPlatform(shellRuntime, features = setOf(
                CodexRuntimeFeature.SHELL_COMMANDS,
                CodexRuntimeFeature.CONNECTORS,
                CodexRuntimeFeature.SKILLS,
                CodexRuntimeFeature.HOOKS,
                CodexRuntimeFeature.PLUGINS,
                CodexRuntimeFeature.MCP_SERVERS,
            ), workspacePath = skillFixture.workspacePath, authorizationBrowser = authorizationBrowser),
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
            val hooks = shellAgent.hooks
            assertSame(hooks, shellAgent.hooks)
            assertTrue(hooks.isAvailable)
            assertEquals(0, enumerablePropertyCount(hooks))
            val plugins = shellAgent.plugins
            assertSame(plugins, shellAgent.plugins)
            assertTrue(plugins.isAvailable)
            assertEquals(0, enumerablePropertyCount(plugins))
            val mcpServers = shellAgent.mcpServers
            assertSame(mcpServers, shellAgent.mcpServers)
            assertTrue(mcpServers.isAvailable)
            assertEquals(0, enumerablePropertyCount(mcpServers))
            val integrationAuthorization = shellAgent.integrationAuthorization
            assertSame(integrationAuthorization, shellAgent.integrationAuthorization)
            assertEquals(0, enumerablePropertyCount(integrationAuthorization))
            assertEquals("idle", integrationAuthorization.state.status)
            assertNull(integrationAuthorization.state.target)
            assertNull(integrationAuthorization.state.failure)
            assertNull(integrationAuthorization.active)
            assertFalse(integrationAuthorization.isAuthorizing)
            assertTrue(isFrozen(integrationAuthorization.state))

            val authorizationStates = mutableListOf<AgentIntegrationAuthorizationState>()
            val activeAuthorizations = mutableListOf<AgentIntegration?>()
            val authorizingValues = mutableListOf<Boolean>()
            val authorizationStateObservation = integrationAuthorization.observeState(authorizationStates::add)
            val activeAuthorizationObservation = integrationAuthorization.observeActive(activeAuthorizations::add)
            val authorizingObservation = integrationAuthorization.observeAuthorizing(authorizingValues::add)
            awaitCondition {
                authorizationStates.isNotEmpty() && activeAuthorizations.isNotEmpty() &&
                    authorizingValues.isNotEmpty()
            }

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

            val abortedConversationRead = runCatching {
                shellAgent.readConversation(
                    "thread-history",
                    controller.signal.unsafeCast<AbortSignal>(),
                ).await()
            }.exceptionOrNull()
            assertEquals("AbortError", abortedConversationRead?.asDynamic()?.name as String)
            assertTrue(shellRuntime.threadReadRequests.isEmpty())

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
                    hooks.list(controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    hooks.install(
                        skillFixture.hookSourceDirectory,
                        "workspace",
                        controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
                runCatching {
                    hooks.uninstall(localHook, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    hooks.trust(localHook, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
            ).forEach { aborted ->
                assertEquals("AbortError", aborted?.asDynamic()?.name as String)
            }
            assertTrue(shellRuntime.hookListRequests.isEmpty())
            assertTrue(shellRuntime.configBatchWriteRequests.isEmpty())
            assertFalse(nodeFileExists(skillFixture.installedHookConfigPath))

            listOf(
                runCatching {
                    mcpServers.list(controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    mcpServers.add(
                        localMcpConfiguration,
                        controller.signal.unsafeCast<AbortSignal>(),
                    ).await()
                }.exceptionOrNull(),
                runCatching {
                    mcpServers.remove(localMcpServer, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
            ).forEach { aborted ->
                assertEquals("AbortError", aborted?.asDynamic()?.name as String)
            }
            assertTrue(shellRuntime.mcpStatusRequests.isEmpty())
            assertTrue(shellRuntime.mcpReloadRequests.isEmpty())
            val invalidMcpConfiguration = runCatching {
                mcpServers.add(js("({})").unsafeCast<AgentMcpServerConfiguration>()).await()
            }.exceptionOrNull()
            assertEquals(
                "configuration must be an AgentMcpServerConfiguration",
                invalidMcpConfiguration?.message,
            )
            val invalidMcpServer = runCatching {
                mcpServers.remove(js("({})").unsafeCast<AgentMcpServer>()).await()
            }.exceptionOrNull()
            assertEquals("server must be an AgentMcpServer", invalidMcpServer?.message)
            assertTrue(shellRuntime.mcpStatusRequests.isEmpty())
            assertTrue(shellRuntime.mcpReloadRequests.isEmpty())
            assertTrue(shellRuntime.mcpBatchWriteRequests.isEmpty())

            listOf(
                runCatching {
                    plugins.list(signal = controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    plugins.read(localPluginReference, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    plugins.install(localPluginReference, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
                runCatching {
                    plugins.uninstall(localPluginReference, controller.signal.unsafeCast<AbortSignal>()).await()
                }.exceptionOrNull(),
            ).forEach { aborted ->
                assertEquals("AbortError", aborted?.asDynamic()?.name as String)
            }
            assertTrue(shellRuntime.pluginListRequests.isEmpty())
            assertTrue(shellRuntime.pluginInstalledRequests.isEmpty())
            assertTrue(shellRuntime.pluginReadRequests.isEmpty())
            assertTrue(shellRuntime.pluginInstallRequests.isEmpty())
            assertTrue(shellRuntime.pluginUninstallRequests.isEmpty())

            val invalidPluginValue = runCatching {
                plugins.read(js("({})").unsafeCast<AgentPluginReference>()).await()
            }.exceptionOrNull()
            assertEquals("plugin must be an AgentPluginReference", invalidPluginValue?.message)
            val incompletePluginReference = AgentPluginReference("missing", "missing", "catalog")
            val invalidPluginReference = runCatching { plugins.read(incompletePluginReference).await() }
                .exceptionOrNull()
            assertEquals("Remote plugin is missing its catalog identifier", invalidPluginReference?.message)
            assertTrue(shellRuntime.pluginReadRequests.isEmpty())

            shellRuntime.failNextPluginList = true
            val pluginListFailure = assertIs<CodexError>(
                runCatching { plugins.list(forceReload = true).await() }.exceptionOrNull(),
            )
            assertEquals("plugin_list_failed", pluginListFailure.code)
            assertEquals("plugin list denied", pluginListFailure.message)
            assertTrue(pluginListFailure.recoverable)

            val pluginCatalog = plugins.list(forceReload = true).await()
            assertEquals("live", pluginCatalog.freshness)
            assertTrue(pluginCatalog.errors.isEmpty())
            val listedPlugin = pluginCatalog.plugins.single()
            assertEquals("drive@openai-curated", listedPlugin.reference.id)
            assertEquals("drive", listedPlugin.reference.name)
            assertEquals("openai-curated", listedPlugin.reference.marketplaceName)
            assertNull(listedPlugin.reference.marketplacePath)
            assertEquals(REMOTE_PLUGIN_ID, listedPlugin.reference.remotePluginId)
            assertEquals("plugin://drive@openai-curated", listedPlugin.reference.uri)
            assertEquals("Drive", listedPlugin.displayName)
            assertEquals("Files in Drive", listedPlugin.description)
            assertTrue(listedPlugin.isInstalled)
            assertTrue(listedPlugin.isEnabled)
            assertEquals("available", listedPlugin.installPolicy)
            assertEquals("on_install", listedPlugin.authPolicy)
            assertTrue(listedPlugin.isAvailable)
            assertEquals(listOf("Search files", "Share files"), listedPlugin.capabilities.toList())
            assertEquals("#4285f4", listedPlugin.brandColor)
            assertEquals("https://example.com/privacy", listedPlugin.privacyPolicyUrl)
            assertEquals("https://example.com/terms", listedPlugin.termsOfServiceUrl)
            assertEquals("https://example.com", listedPlugin.websiteUrl)
            assertTrue(isFrozen(pluginCatalog))
            assertTrue(isFrozen(pluginCatalog.plugins))
            assertTrue(isFrozen(pluginCatalog.errors))
            assertTrue(isFrozen(listedPlugin))
            assertTrue(isFrozen(listedPlugin.reference))
            assertTrue(isFrozen(listedPlugin.capabilities))
            assertEquals(2, shellRuntime.pluginListRequests.size)
            assertEquals(1, shellRuntime.pluginInstalledRequests.size)
            val availablePluginRequest = shellRuntime.pluginListRequests.last()
            assertEquals(setOf("cwds"), availablePluginRequest.keys)
            assertEquals(
                listOf(skillFixture.workspacePath),
                availablePluginRequest["cwds"]?.jsonArray?.map { it.jsonPrimitive.content },
            )
            val installedPluginRequest = shellRuntime.pluginInstalledRequests.single()
            assertEquals(setOf("cwds"), installedPluginRequest.keys)
            assertEquals(
                listOf(skillFixture.workspacePath),
                installedPluginRequest["cwds"]?.jsonArray?.map { it.jsonPrimitive.content },
            )

            val pluginDetail = plugins.read(listedPlugin.reference).await()
            assertEquals("Complete Drive plugin", pluginDetail.description)
            assertEquals("drive@openai-curated", pluginDetail.summary.reference.id)
            assertEquals("search-drive", pluginDetail.skills.single().name)
            assertEquals("Search Drive", pluginDetail.skills.single().description)
            assertTrue(pluginDetail.skills.single().isEnabled)
            assertEquals("/plugins/drive/search/SKILL.md", pluginDetail.skills.single().path)
            assertEquals("drive", pluginDetail.connectors.single().id)
            assertEquals(listOf("drive-mcp"), pluginDetail.mcpServers.toList())
            assertEquals(1, pluginDetail.hookCount)
            assertTrue(isFrozen(pluginDetail))
            assertTrue(isFrozen(pluginDetail.summary))
            assertTrue(isFrozen(pluginDetail.skills))
            assertTrue(isFrozen(pluginDetail.connectors))
            assertTrue(isFrozen(pluginDetail.mcpServers))
            val pluginReadRequest = shellRuntime.pluginReadRequests.single()
            assertEquals(setOf("pluginName", "remoteMarketplaceName"), pluginReadRequest.keys)
            assertEquals(REMOTE_PLUGIN_ID, pluginReadRequest["pluginName"]?.jsonPrimitive?.content)
            assertEquals("openai-curated", pluginReadRequest["remoteMarketplaceName"]?.jsonPrimitive?.content)

            val pluginInstallResult = plugins.install(listedPlugin.reference).await()
            assertEquals("on_install", pluginInstallResult.authPolicy)
            assertEquals("drive", pluginInstallResult.connectorsNeedingAuthentication.single().id)
            assertNull(pluginInstallResult.message)
            assertTrue(isFrozen(pluginInstallResult))
            assertTrue(isFrozen(pluginInstallResult.connectorsNeedingAuthentication))
            val pluginInstallRequest = shellRuntime.pluginInstallRequests.single()
            assertEquals(setOf("pluginName", "remoteMarketplaceName"), pluginInstallRequest.keys)
            assertEquals(REMOTE_PLUGIN_ID, pluginInstallRequest["pluginName"]?.jsonPrimitive?.content)

            plugins.uninstall(listedPlugin.reference).await()
            assertEquals(
                setOf("pluginId"),
                shellRuntime.pluginUninstallRequests.single().keys,
            )
            assertEquals(
                REMOTE_PLUGIN_ID,
                shellRuntime.pluginUninstallRequests.single()["pluginId"]?.jsonPrimitive?.content,
            )

            shellRuntime.failNextPluginRead = true
            val pluginReadFailure = assertIs<CodexError>(
                runCatching { plugins.read(listedPlugin.reference).await() }.exceptionOrNull(),
            )
            assertEquals("plugin_read_failed", pluginReadFailure.code)
            assertEquals("plugin read denied", pluginReadFailure.message)
            shellRuntime.failNextPluginInstall = true
            val pluginInstallFailure = assertIs<CodexError>(
                runCatching { plugins.install(listedPlugin.reference).await() }.exceptionOrNull(),
            )
            assertEquals("plugin_install_failed", pluginInstallFailure.code)
            assertEquals("plugin install denied", pluginInstallFailure.message)
            shellRuntime.failNextPluginUninstall = true
            val pluginUninstallFailure = assertIs<CodexError>(
                runCatching { plugins.uninstall(listedPlugin.reference).await() }.exceptionOrNull(),
            )
            assertEquals("plugin_uninstall_failed", pluginUninstallFailure.code)
            assertEquals("plugin uninstall denied", pluginUninstallFailure.message)

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

            val hookCatalog = hooks.list().await()
            assertEquals(
                listOf("a-mcp", "m-agent", "p-prompt", "z-command"),
                hookCatalog.hooks.map(AgentHook::key),
            )
            assertEquals(listOf("review warning"), hookCatalog.warnings.toList())
            assertEquals(
                listOf("${skillFixture.workspacePath}/.codex/hooks.json: ignored hook"),
                hookCatalog.errors.toList(),
            )
            val mcpHook = hookCatalog.hooks[0]
            assertEquals("mcp_tool", mcpHook.handler.asDynamic().type as String)
            assertEquals("review-server", mcpHook.handler.asDynamic().server as String)
            assertEquals("review-tool", mcpHook.handler.asDynamic().tool as String)
            assertEquals("plugin", mcpHook.origin)
            assertTrue(mcpHook.canTrust)
            assertEquals("agent", hookCatalog.hooks[1].handler.asDynamic().type as String)
            assertEquals("managed", hookCatalog.hooks[1].origin)
            assertFalse(hookCatalog.hooks[1].canTrust)
            assertEquals("prompt", hookCatalog.hooks[2].handler.asDynamic().type as String)
            assertEquals("user", hookCatalog.hooks[2].origin)
            val commandHook = hookCatalog.hooks[3]
            assertEquals("command", commandHook.handler.asDynamic().type as String)
            assertEquals("./check", commandHook.handler.asDynamic().command as String)
            assertFalse(commandHook.handler.asDynamic().isAsync as Boolean)
            assertEquals("Shell", commandHook.matcher)
            assertEquals("Review shell commands", commandHook.statusMessage)
            assertEquals("workspace", commandHook.origin)
            assertFalse(commandHook.canUninstall)
            assertTrue(commandHook.canTrust)
            assertEquals(1, shellRuntime.hookListRequests.size)
            assertEquals(
                listOf(skillFixture.workspacePath),
                shellRuntime.hookListRequests.single()["cwds"]?.jsonArray?.map { it.jsonPrimitive.content },
            )
            assertTrue(isFrozen(hookCatalog))
            assertTrue(isFrozen(hookCatalog.hooks))
            assertTrue(isFrozen(hookCatalog.warnings))
            assertTrue(isFrozen(hookCatalog.errors))
            hookCatalog.hooks.forEach { hook ->
                assertTrue(isFrozen(hook))
                assertTrue(isFrozen(hook.handler))
            }

            val requestsBeforeInvalidHookInputs = shellRuntime.requestMethods.size
            val invalidHookScope = runCatching {
                hooks.install(skillFixture.hookSourceDirectory, "temporary").await()
            }.exceptionOrNull()
            assertEquals("Unknown installation scope: temporary", invalidHookScope?.message)
            assertEquals(requestsBeforeInvalidHookInputs, shellRuntime.requestMethods.size)
            val unownedHookFailure = assertIs<CodexError>(
                runCatching { hooks.uninstall(commandHook).await() }.exceptionOrNull(),
            )
            assertEquals("hook_uninstall_failed", unownedHookFailure.code)
            assertEquals("Could not uninstall hook", unownedHookFailure.message)
            assertTrue(unownedHookFailure.recoverable)
            assertEquals(requestsBeforeInvalidHookInputs, shellRuntime.requestMethods.size)

            shellRuntime.revealHookAtRequest = shellRuntime.hookListRequests.size + 2
            val installedHook = hooks.install(skillFixture.hookSourceDirectory, "workspace").await()
            assertEquals("fixture-installed", installedHook.key)
            assertEquals(skillFixture.installedHookConfigPath, installedHook.sourcePath)
            assertEquals("workspace", installedHook.origin)
            assertTrue(installedHook.canUninstall)
            assertTrue(installedHook.canTrust)
            assertTrue(isFrozen(installedHook))
            assertTrue(isFrozen(installedHook.handler))
            assertTrue(nodeFileExists(skillFixture.installedHookConfigPath))
            assertTrue(nodeFileExists(skillFixture.installedHookAssetDirectory))

            hooks.trust(installedHook).await()
            val trustRequest = shellRuntime.configBatchWriteRequests.single()
            assertEquals("true", trustRequest["reloadUserConfig"]?.jsonPrimitive?.content)
            val trustEdit = checkNotNull(trustRequest["edits"]).jsonArray.single().jsonObject
            assertEquals("hooks.state", trustEdit["keyPath"]?.jsonPrimitive?.content)
            assertEquals("upsert", trustEdit["mergeStrategy"]?.jsonPrimitive?.content)
            assertEquals(
                installedHook.currentHash,
                trustEdit["value"]?.jsonObject
                    ?.get(installedHook.key)?.jsonObject
                    ?.get("trusted_hash")?.jsonPrimitive?.content,
            )

            shellRuntime.hideHookAtRequest = shellRuntime.hookListRequests.size + 1
            hooks.uninstall(installedHook).await()
            assertFalse(nodeFileExists(skillFixture.installedHookAssetDirectory))

            shellRuntime.failNextHookList = true
            val hookListFailure = assertIs<CodexError>(
                runCatching { hooks.list().await() }.exceptionOrNull(),
            )
            assertEquals("hook_list_failed", hookListFailure.code)
            assertEquals("hook list denied", hookListFailure.message)
            assertTrue(hookListFailure.recoverable)

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

            val listedMcpServers = mcpServers.list().await()
            assertEquals(listOf("configured"), listedMcpServers.map(AgentMcpServer::name))
            val configuredMcpServer = listedMcpServers.single()
            assertEquals("Configured server", configuredMcpServer.displayName)
            assertEquals("bearer_token", configuredMcpServer.authStatus)
            assertTrue(configuredMcpServer.isAuthorized)
            assertEquals("user", configuredMcpServer.origin)
            assertTrue(configuredMcpServer.canRemove)
            val configuredMcp = checkNotNull(configuredMcpServer.configuration)
            val configuredTransport = assertIs<AgentMcpStdioTransport>(configuredMcp.transport)
            assertEquals("node", configuredTransport.command)
            assertEquals(listOf("server.js"), configuredTransport.arguments.toList())
            assertEquals(skillFixture.workspacePath, configuredTransport.workingDirectory)
            assertEquals("value", configuredTransport.environment.asDynamic().TOKEN as String)
            assertEquals(listOf("HOME"), configuredTransport.forwardedEnvironment.map { it.name })
            assertTrue(isFrozen(listedMcpServers))
            assertTrue(isFrozen(configuredMcpServer))
            assertTrue(isFrozen(configuredMcp))
            assertTrue(isFrozen(configuredTransport))
            assertTrue(isFrozen(configuredTransport.arguments))
            assertTrue(isFrozen(checkNotNull(configuredTransport.environment)))
            assertTrue(isFrozen(configuredTransport.forwardedEnvironment))
            assertEquals(1, shellRuntime.mcpStatusRequests.size)
            assertEquals(
                setOf("cwd", "includeLayers"),
                shellRuntime.configReadRequests.last().keys,
            )
            assertEquals(
                skillFixture.workspacePath,
                shellRuntime.configReadRequests.last()["cwd"]?.jsonPrimitive?.content,
            )
            assertEquals(
                "true",
                shellRuntime.configReadRequests.last()["includeLayers"]?.jsonPrimitive?.content,
            )

            shellRuntime.failNextMcpStatus = true
            val mcpListFailure = assertIs<CodexError>(
                runCatching { mcpServers.list().await() }.exceptionOrNull(),
            )
            assertEquals("mcp_server_list_failed", mcpListFailure.code)
            assertEquals("MCP server list denied", mcpListFailure.message)
            assertTrue(mcpListFailure.recoverable)

            val addedMcpServer = mcpServers.add(localMcpConfiguration).await()
            assertEquals("remote", addedMcpServer.name)
            assertEquals("Remote server", addedMcpServer.displayName)
            assertEquals("oauth", addedMcpServer.authStatus)
            assertEquals("user", addedMcpServer.origin)
            assertTrue(addedMcpServer.canRemove)
            assertTrue(addedMcpServer.isAuthorized)
            assertEquals("chat_gpt", addedMcpServer.configuration?.authentication)
            assertIs<AgentMcpHttpTransport>(addedMcpServer.configuration?.transport)
            assertTrue(isFrozen(addedMcpServer))
            assertTrue(isFrozen(checkNotNull(addedMcpServer.configuration)))
            assertEquals(1, shellRuntime.mcpReloadRequests.size)
            val addWrite = shellRuntime.mcpBatchWriteRequests.last()
            assertEquals("mcp_servers.\"remote\"", addWrite["keyPath"]?.jsonPrimitive?.content)
            assertEquals("replace", addWrite["mergeStrategy"]?.jsonPrimitive?.content)
            val writtenMcp = checkNotNull(addWrite["value"]).jsonObject
            assertEquals("https://mcp.example.com", writtenMcp["url"]?.jsonPrimitive?.content)
            assertEquals("chatgpt", writtenMcp["auth"]?.jsonPrimitive?.content)
            assertEquals("local", writtenMcp["environment_id"]?.jsonPrimitive?.content)
            assertEquals("false", writtenMcp["enabled"]?.jsonPrimitive?.content)

            mcpServers.remove(addedMcpServer).await()
            assertEquals(2, shellRuntime.mcpReloadRequests.size)
            assertEquals(JsonNull, shellRuntime.mcpBatchWriteRequests.last()["value"])
            assertEquals(listOf("configured"), mcpServers.list().await().map(AgentMcpServer::name))

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
            val turnStartsBeforeAbort = shellRuntime.turnStartRequests.size
            val requestsBeforeAbort = shellRuntime.requestMethods.size
            val unreadRequest = js(
                "Object.defineProperty({ reads: 0 }, 'prompt', " +
                    "{ get: function () { this.reads += 1; return 'unread'; } })",
            ).unsafeCast<AgentTurnRequest>()
            val abortedRequest = runCatching {
                shellConversation.sendRequest(
                    unreadRequest,
                    controller.signal.unsafeCast<AbortSignal>(),
                ).await()
            }.exceptionOrNull()
            assertEquals("AbortError", abortedRequest?.asDynamic()?.name as String)
            assertEquals(0, unreadRequest.asDynamic().reads as Int)
            assertEquals(turnStartsBeforeAbort, shellRuntime.turnStartRequests.size)
            assertEquals(requestsBeforeAbort, shellRuntime.requestMethods.size)

            val defaultRequest: dynamic = js("({ prompt: 'typed default' })")
            defaultRequest.clientMessageId = null
            defaultRequest.effort = null
            defaultRequest.approvalPreset = null
            defaultRequest.invocations = null
            shellConversation.sendRequest(defaultRequest.unsafeCast<AgentTurnRequest>()).await()
            val defaultTurn = shellRuntime.turnStartRequests.last()
            assertEquals("thread-js", defaultTurn["threadId"]?.jsonPrimitive?.content)
            assertEquals("on-request", defaultTurn["approvalPolicy"]?.jsonPrimitive?.content)
            assertEquals("auto_review", defaultTurn["approvalsReviewer"]?.jsonPrimitive?.content)
            assertEquals(skillFixture.workspacePath, defaultTurn["cwd"]?.jsonPrimitive?.content)
            assertNull(defaultTurn["model"])
            assertNull(defaultTurn["effort"])
            assertNull(defaultTurn["serviceTier"])
            assertNull(defaultTurn["collaborationMode"])
            assertEquals("auto", defaultTurn["summary"]?.jsonPrimitive?.content)
            assertFalse(
                checkNotNull(defaultTurn["clientUserMessageId"]).jsonPrimitive.content
                    .startsWith("codex-agent:plan:"),
            )
            val defaultInput = checkNotNull(defaultTurn["input"]).jsonArray.single().jsonObject
            assertEquals("text", defaultInput["type"]?.jsonPrimitive?.content)
            assertEquals("typed default", defaultInput["text"]?.jsonPrimitive?.content)
            assertNull(defaultInput["text_elements"])
            shellRuntime.completeTurn()
            awaitCondition { shellConversation.state.status == "ready" }

            val sourceCapabilities = arrayOf("web_search", "web_search")
            val sourceInvocations = arrayOf<AgentInvocation>(
                skillInvocation,
                pluginInvocation,
                skillInvocation,
            )
            val customRequest: dynamic = js("({})")
            customRequest.prompt = "typed custom"
            customRequest.clientMessageId = "client-custom"
            customRequest.model = "model-preferred"
            customRequest.effort = "high"
            customRequest.serviceTier = "fast"
            customRequest.approvalPreset = "strict"
            customRequest.capabilities = sourceCapabilities
            customRequest.invocations = sourceInvocations
            customRequest.collaborationMode = "plan"
            shellConversation.sendRequest(customRequest.unsafeCast<AgentTurnRequest>()).await()
            sourceCapabilities[0] = "changed"
            sourceInvocations[0] = pluginInvocation
            val customTurn = shellRuntime.turnStartRequests.last()
            assertEquals("thread-js", customTurn["threadId"]?.jsonPrimitive?.content)
            assertEquals("untrusted", customTurn["approvalPolicy"]?.jsonPrimitive?.content)
            assertEquals("user", customTurn["approvalsReviewer"]?.jsonPrimitive?.content)
            assertEquals("codex-agent:plan:client-custom", customTurn["clientUserMessageId"]?.jsonPrimitive?.content)
            assertEquals(skillFixture.workspacePath, customTurn["cwd"]?.jsonPrimitive?.content)
            assertEquals("high", customTurn["effort"]?.jsonPrimitive?.content)
            assertEquals("model-preferred", customTurn["model"]?.jsonPrimitive?.content)
            assertEquals("fast", customTurn["serviceTier"]?.jsonPrimitive?.content)
            assertEquals("auto", customTurn["summary"]?.jsonPrimitive?.content)
            val customMode = checkNotNull(customTurn["collaborationMode"]).jsonObject
            assertEquals("plan", customMode["mode"]?.jsonPrimitive?.content)
            val customSettings = checkNotNull(customMode["settings"]).jsonObject
            assertEquals("model-preferred", customSettings["model"]?.jsonPrimitive?.content)
            assertEquals("medium", customSettings["reasoning_effort"]?.jsonPrimitive?.content)
            assertNull(customSettings["developer_instructions"])
            val customInput = checkNotNull(customTurn["input"]).jsonArray
            assertEquals(3, customInput.size)
            assertEquals(
                "${CoreCapability.WEB_SEARCH.promptLabel}\n\$review\n@drive\n\ntyped custom",
                customInput[0].jsonObject["text"]?.jsonPrimitive?.content,
            )
            val customTextElement = checkNotNull(
                customInput[0].jsonObject["text_elements"],
            ).jsonArray.single().jsonObject
            assertEquals(CoreCapability.WEB_SEARCH.displayLabel, customTextElement["placeholder"]?.jsonPrimitive?.content)
            val customRange = checkNotNull(customTextElement["byteRange"]).jsonObject
            assertEquals("0", customRange["start"]?.jsonPrimitive?.content)
            assertEquals(
                CoreCapability.WEB_SEARCH.promptLabel.encodeToByteArray().size.toString(),
                customRange["end"]?.jsonPrimitive?.content,
            )
            assertEquals("skill", customInput[1].jsonObject["type"]?.jsonPrimitive?.content)
            assertEquals("review", customInput[1].jsonObject["name"]?.jsonPrimitive?.content)
            assertEquals("/skills/review/SKILL.md", customInput[1].jsonObject["path"]?.jsonPrimitive?.content)
            assertEquals("mention", customInput[2].jsonObject["type"]?.jsonPrimitive?.content)
            assertEquals("drive", customInput[2].jsonObject["name"]?.jsonPrimitive?.content)
            assertEquals("plugin://drive@catalog", customInput[2].jsonObject["path"]?.jsonPrimitive?.content)
            shellRuntime.completeTurn()
            awaitCondition { shellConversation.state.status == "ready" }

            val hostileRequests = listOf(
                js("null").unsafeCast<AgentTurnRequest>() to "request must be an object",
                js("1").unsafeCast<AgentTurnRequest>() to "request must be an object",
                js("({})").unsafeCast<AgentTurnRequest>() to "prompt must be a string",
                js("({ prompt: new String('boxed') })").unsafeCast<AgentTurnRequest>() to
                    "prompt must be a string",
                js("({ prompt: 'x', clientMessageId: {} })").unsafeCast<AgentTurnRequest>() to
                    "clientMessageId must be a string or null",
                js("({ prompt: 'x', model: 1 })").unsafeCast<AgentTurnRequest>() to
                    "model must be a string or null",
                js("({ prompt: 'x', effort: true })").unsafeCast<AgentTurnRequest>() to
                    "effort must be a string or null",
                js("({ prompt: 'x', serviceTier: [] })").unsafeCast<AgentTurnRequest>() to
                    "serviceTier must be a string or null",
                js("({ prompt: 'x', approvalPreset: 'sometimes' })").unsafeCast<AgentTurnRequest>() to
                    "Unknown approval preset: sometimes",
                js("({ prompt: 'x', capabilities: { length: 0 } })").unsafeCast<AgentTurnRequest>() to
                    "capabilities must be an array",
                js("({ prompt: 'x', capabilities: new Array(1) })").unsafeCast<AgentTurnRequest>() to
                    "capabilities must not contain sparse elements",
                js("({ prompt: 'x', capabilities: ['filesystem'] })").unsafeCast<AgentTurnRequest>() to
                    "Unknown agent capability: filesystem",
                js("({ prompt: 'x', invocations: { length: 0 } })").unsafeCast<AgentTurnRequest>() to
                    "invocations must be an array",
                js("({ prompt: 'x', invocations: new Array(1) })").unsafeCast<AgentTurnRequest>() to
                    "invocations must not contain sparse elements",
                js("({ prompt: 'x', invocations: [{}] })").unsafeCast<AgentTurnRequest>() to
                    "invocations[0] must be an AgentSkillInvocation or AgentPluginInvocation",
                js("({ prompt: 'x', collaborationMode: 'pair' })").unsafeCast<AgentTurnRequest>() to
                    "Unknown collaboration mode: pair",
            )
            hostileRequests.forEach { (request, message) ->
                val requestsBeforeInvalid = shellRuntime.turnStartRequests.size
                val methodsBeforeInvalid = shellRuntime.requestMethods.size
                val invalid = runCatching { shellConversation.sendRequest(request).await() }.exceptionOrNull()
                assertEquals(message, invalid?.message)
                assertEquals(requestsBeforeInvalid, shellRuntime.turnStartRequests.size)
                assertEquals(methodsBeforeInvalid, shellRuntime.requestMethods.size)
            }

            val turnStartsBeforeBlank = shellRuntime.turnStartRequests.size
            val methodsBeforeBlank = shellRuntime.requestMethods.size
            val blankFailure = runCatching {
                shellConversation.sendRequest(
                    js("({ prompt: ' ' })").unsafeCast<AgentTurnRequest>(),
                ).await()
            }.exceptionOrNull()
            val blankError = assertIs<CodexError>(blankFailure)
            assertEquals("turn_start_failed", blankError.code)
            assertEquals("Could not start turn", blankError.message)
            assertTrue(blankError.recoverable)
            assertEquals("Prompt must not be blank", blankError.cause?.message)
            assertEquals(turnStartsBeforeBlank, shellRuntime.turnStartRequests.size)
            assertEquals(methodsBeforeBlank, shellRuntime.requestMethods.size)

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

            shellRuntime.connectorAccessible = false
            val connectorAuthorization = integrationAuthorization.authorize(
                AgentConnectorIntegration(customConnector),
            )
            awaitCondition {
                integrationAuthorization.state.status == "awaiting_completion" &&
                    integrationAuthorization.active is AgentConnectorIntegration &&
                    integrationAuthorization.isAuthorizing
            }
            assertEquals("connector-custom", integrationAuthorization.active?.id)
            assertEquals("Custom connector", integrationAuthorization.active?.displayName)
            assertEquals("https://example.com/install", authorizationBrowser.urls.last().value)
            assertEquals("external", authorizationBrowser.urls.last().purpose.name.lowercase())
            assertTrue(isFrozen(integrationAuthorization.state))
            assertTrue(isFrozen(checkNotNull(integrationAuthorization.state.target)))
            shellRuntime.completeConnectorAuthorization()
            connectorAuthorization.await()
            awaitCondition {
                integrationAuthorization.state.status == "authorized" &&
                    integrationAuthorization.active == null && !integrationAuthorization.isAuthorizing
            }
            val authorizedConnector = assertIs<AgentConnectorIntegration>(
                integrationAuthorization.state.target,
            )
            assertTrue(authorizedConnector.connector.isAccessible)
            assertEquals(listOf(false, true, false), authorizingValues.distinctConsecutive())

            val mcpTarget = AgentMcpServerIntegration(
                AgentMcpServer("drive", "Drive MCP", "not_logged_in"),
            )
            val mcpAuthorization = integrationAuthorization.authorize(mcpTarget)
            awaitCondition {
                integrationAuthorization.state.status == "awaiting_completion" &&
                    integrationAuthorization.active is AgentMcpServerIntegration
            }
            assertEquals("drive", shellRuntime.mcpOauthRequests.single()["name"]?.jsonPrimitive?.content)
            assertEquals("thread-js", shellRuntime.mcpOauthRequests.single()["threadId"]?.jsonPrimitive?.content)
            assertEquals("https://accounts.example.com/oauth/drive", authorizationBrowser.urls.last().value)
            shellRuntime.completeMcpAuthorization("drive")
            mcpAuthorization.await()
            awaitCondition { integrationAuthorization.state.status == "authorized" }
            assertEquals("drive", assertIs<AgentMcpServerIntegration>(
                integrationAuthorization.state.target,
            ).server.name)

            val cancelledMcpAuthorization = integrationAuthorization.authorize(mcpTarget)
            awaitCondition { integrationAuthorization.state.status == "awaiting_completion" }
            integrationAuthorization.cancel().await()
            val cancelledAuthorization = runCatching { cancelledMcpAuthorization.await() }.exceptionOrNull()
            assertEquals("AbortError", cancelledAuthorization?.asDynamic()?.name as String)
            awaitCondition {
                integrationAuthorization.state.status == "idle" &&
                    integrationAuthorization.active == null && !integrationAuthorization.isAuthorizing
            }
            assertEquals(3, authorizationBrowser.closedPresentations)

            shellRuntime.failNextMcpOauthLogin = true
            val authorizationFailureValue = runCatching {
                integrationAuthorization.authorize(localMcpIntegration).await()
            }.exceptionOrNull()
            val authorizationFailure = assertIs<CodexError>(
                authorizationFailureValue,
                authorizationFailureValue?.message,
            )
            assertEquals("mcp_authorization_failed", authorizationFailure.code)
            assertEquals("MCP authorization denied", authorizationFailure.message)
            assertEquals("failed", integrationAuthorization.state.status)
            assertEquals("mcp_authorization_failed", integrationAuthorization.state.failure?.code)
            assertTrue(isFrozen(checkNotNull(integrationAuthorization.state.failure)))

            val authorizationRequestsBeforeAbort = shellRuntime.requestMethods.size
            val authorizationAbortController = js("new AbortController()")
            authorizationAbortController.abort()
            val abortedAuthorization = runCatching {
                integrationAuthorization.authorize(
                    mcpTarget,
                    authorizationAbortController.signal.unsafeCast<AbortSignal>(),
                ).await()
            }.exceptionOrNull()
            assertEquals("AbortError", abortedAuthorization?.asDynamic()?.name as String)
            assertEquals(authorizationRequestsBeforeAbort, shellRuntime.requestMethods.size)
            assertTrue(authorizationStates.any { it.status == "awaiting_completion" })
            assertTrue(authorizationStates.all(::isFrozen))
            assertTrue(activeAuthorizations.filterNotNull().all(::isFrozen))

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
            val resumedUserMessage = resumed.state.messages.first()
            assertEquals("plan", resumedUserMessage.collaborationMode)
            assertEquals(listOf("web_search"), resumedUserMessage.capabilities.toList())
            assertEquals(
                listOf("skill:/skills/review/SKILL.md", "plugin:plugin://drive@catalog"),
                resumedUserMessage.invocations.map(AgentInvocation::key),
            )
            assertTrue(isFrozen(resumedUserMessage.capabilities))
            assertTrue(isFrozen(resumedUserMessage.invocations))
            assertEquals("closed", shellConversation.state.status)
            val turnStartsBeforeClosedSend = shellRuntime.turnStartRequests.size
            val requestsBeforeClosedSend = shellRuntime.requestMethods.size
            val closedSend = runCatching {
                shellConversation.sendRequest(
                    js("({ prompt: 'closed' })").unsafeCast<AgentTurnRequest>(),
                ).await()
            }.exceptionOrNull()
            assertEquals("Conversation is closed", closedSend?.message)
            assertEquals(turnStartsBeforeClosedSend, shellRuntime.turnStartRequests.size)
            assertEquals(requestsBeforeClosedSend, shellRuntime.requestMethods.size)
            shellHost.close().await()
            assertSame(connectors, shellAgent.connectors)
            assertSame(models, shellAgent.models)
            assertSame(skills, shellAgent.skills)
            assertSame(hooks, shellAgent.hooks)
            assertSame(plugins, shellAgent.plugins)
            assertSame(mcpServers, shellAgent.mcpServers)
            assertSame(integrationAuthorization, shellAgent.integrationAuthorization)
            val requestsBeforeClosedList = shellRuntime.appListRequests.size
            val conversationRequestsBeforeClosedList = shellRuntime.threadListRequests.size
            val conversationRequestsBeforeClosedRead = shellRuntime.threadReadRequests.size
            val modelRequestsBeforeClosedList = shellRuntime.modelListRequests.size
            val skillRequestsBeforeClosedList = shellRuntime.skillListRequests.size
            val hookRequestsBeforeClosedList = shellRuntime.hookListRequests.size
            val hookWritesBeforeClosed = shellRuntime.configBatchWriteRequests.size
            val pluginRequestsBeforeClosed = listOf(
                shellRuntime.pluginListRequests.size,
                shellRuntime.pluginInstalledRequests.size,
                shellRuntime.pluginReadRequests.size,
                shellRuntime.pluginInstallRequests.size,
                shellRuntime.pluginUninstallRequests.size,
            )
            val mcpStatusBeforeClosed = shellRuntime.mcpStatusRequests.size
            val mcpReloadsBeforeClosed = shellRuntime.mcpReloadRequests.size
            val mcpWritesBeforeClosed = shellRuntime.mcpBatchWriteRequests.size
            val authorizationRequestsBeforeClosed = shellRuntime.requestMethods.size
            val closedList = runCatching { connectors.list().await() }.exceptionOrNull()
            assertEquals("IllegalStateException", closedList?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedList.message)
            assertEquals(requestsBeforeClosedList, shellRuntime.appListRequests.size)
            val closedConversationList = runCatching { shellAgent.listConversations().await() }.exceptionOrNull()
            assertEquals("IllegalStateException", closedConversationList?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedConversationList.message)
            assertEquals(conversationRequestsBeforeClosedList, shellRuntime.threadListRequests.size)
            val closedConversationRead = runCatching {
                shellAgent.readConversation("thread-history").await()
            }.exceptionOrNull()
            assertEquals("IllegalStateException", closedConversationRead?.asDynamic()?.name as String)
            assertEquals("Codex agent is closed", closedConversationRead.message)
            assertEquals(conversationRequestsBeforeClosedRead, shellRuntime.threadReadRequests.size)
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
            listOf(
                runCatching { hooks.list().await() }.exceptionOrNull(),
                runCatching {
                    hooks.install(skillFixture.hookSourceDirectory, "workspace").await()
                }.exceptionOrNull(),
                runCatching { hooks.uninstall(commandHook).await() }.exceptionOrNull(),
                runCatching { hooks.trust(commandHook).await() }.exceptionOrNull(),
            ).forEach { closedHookOperation ->
                assertEquals("IllegalStateException", closedHookOperation?.asDynamic()?.name as String)
                assertEquals("Codex agent is closed", closedHookOperation.message)
            }
            assertEquals(hookRequestsBeforeClosedList, shellRuntime.hookListRequests.size)
            assertEquals(hookWritesBeforeClosed, shellRuntime.configBatchWriteRequests.size)
            listOf(
                runCatching { plugins.list().await() }.exceptionOrNull(),
                runCatching { plugins.read(listedPlugin.reference).await() }.exceptionOrNull(),
                runCatching { plugins.install(listedPlugin.reference).await() }.exceptionOrNull(),
                runCatching { plugins.uninstall(listedPlugin.reference).await() }.exceptionOrNull(),
            ).forEach { closedPluginOperation ->
                assertEquals("IllegalStateException", closedPluginOperation?.asDynamic()?.name as String)
                assertEquals("Codex agent is closed", closedPluginOperation.message)
            }
            assertEquals(
                pluginRequestsBeforeClosed,
                listOf(
                    shellRuntime.pluginListRequests.size,
                    shellRuntime.pluginInstalledRequests.size,
                    shellRuntime.pluginReadRequests.size,
                    shellRuntime.pluginInstallRequests.size,
                    shellRuntime.pluginUninstallRequests.size,
                ),
            )
            listOf(
                runCatching { mcpServers.list().await() }.exceptionOrNull(),
                runCatching { mcpServers.add(localMcpConfiguration).await() }.exceptionOrNull(),
                runCatching { mcpServers.remove(localMcpServer).await() }.exceptionOrNull(),
            ).forEach { closedMcpOperation ->
                assertEquals("IllegalStateException", closedMcpOperation?.asDynamic()?.name as String)
                assertEquals("Codex agent is closed", closedMcpOperation.message)
            }
            assertEquals(mcpStatusBeforeClosed, shellRuntime.mcpStatusRequests.size)
            assertEquals(mcpReloadsBeforeClosed, shellRuntime.mcpReloadRequests.size)
            assertEquals(mcpWritesBeforeClosed, shellRuntime.mcpBatchWriteRequests.size)
            listOf(
                runCatching { integrationAuthorization.authorize(mcpTarget).await() }.exceptionOrNull(),
                runCatching { integrationAuthorization.cancel().await() }.exceptionOrNull(),
            ).forEach { closedAuthorizationOperation ->
                assertEquals("IllegalStateException", closedAuthorizationOperation?.asDynamic()?.name as String)
                assertEquals("Codex agent is closed", closedAuthorizationOperation.message)
            }
            assertEquals(authorizationRequestsBeforeClosed, shellRuntime.requestMethods.size)
            awaitCondition {
                authorizationStateObservation.isClosed && activeAuthorizationObservation.isClosed &&
                    authorizingObservation.isClosed
            }
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
        val chatGptUrl = CodexAuthorizationUrl.chatGpt("https://auth.openai.com/authorize?client=node")
        val externalUrl = CodexAuthorizationUrl.external("http://localhost:8787/callback")
        assertEquals("https://auth.openai.com/authorize?client=node", chatGptUrl.value)
        assertEquals("chat_gpt", chatGptUrl.purpose)
        assertEquals("http://localhost:8787/callback", externalUrl.value)
        assertEquals("external", externalUrl.purpose)
        listOf(chatGptUrl, externalUrl).forEach {
            assertTrue(isFrozen(it))
            assertEquals(0, enumerablePropertyCount(it))
        }
        assertEquals(
            "ChatGPT authorization URL uses an untrusted host",
            runCatching { CodexAuthorizationUrl.chatGpt("https://example.com/login") }
                .exceptionOrNull()?.message,
        )
        assertEquals(
            "Authorization URL is not HTTPS or loopback HTTP",
            runCatching { CodexAuthorizationUrl.external("http://example.com/login") }
                .exceptionOrNull()?.message,
        )
        listOf(
            js("({})").unsafeCast<String>(),
            js("new String('https://auth.openai.com/')").unsafeCast<String>(),
            js("null").unsafeCast<String>(),
        ).forEach { hostile ->
            assertEquals(
                "value must be a string",
                runCatching { CodexAuthorizationUrl.chatGpt(hostile) }.exceptionOrNull()?.message,
            )
            assertEquals(
                "value must be a string",
                runCatching { CodexAuthorizationUrl.external(hostile) }.exceptionOrNull()?.message,
            )
        }

        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        host.start().await()
        val agent = assertIs<CodexAgent>(host.agent)
        val authentication = agent.authentication

        assertSame(authentication, agent.authentication)
        assertEquals(0, enumerablePropertyCount(authentication))
        assertEquals("signed_out", authentication.state.status)
        assertNull(authentication.state.pendingSignInUrl)
        assertNull(authentication.state.deviceVerificationUrl)
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
            states.lastOrNull()?.pendingSignInUrl?.value == "https://auth.openai.com/oauth?state=login-1" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        val pendingSignInUrl = checkNotNull(authentication.state.pendingSignInUrl)
        assertEquals("https://auth.openai.com/oauth?state=login-1", pendingSignInUrl.value)
        assertEquals("chat_gpt", pendingSignInUrl.purpose)
        assertTrue(isFrozen(pendingSignInUrl))
        assertEquals("authenticating", states.last().status)
        assertTrue(authentication.isAuthenticating)

        authentication.cancel().await()
        awaitCondition {
            states.lastOrNull()?.failure?.code == "authentication_failed" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }
        assertEquals("signed_out", authentication.state.status)
        assertEquals("authentication_failed", authentication.state.failure?.code)
        assertNull(authentication.state.pendingSignInUrl)
        assertEquals("signed_out", states.last().status)
        assertTrue(isFrozen(checkNotNull(authentication.state.failure)))
        assertEquals(1, runtime.cancelRequests)

        authentication.authenticate("chatgpt_device_code").await()
        awaitCondition {
            states.lastOrNull()?.deviceUserCode == "ABCD-EFGH" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        val deviceVerificationUrl = checkNotNull(authentication.state.deviceVerificationUrl)
        assertEquals("https://auth.openai.com/device", deviceVerificationUrl.value)
        assertEquals("external", deviceVerificationUrl.purpose)
        assertTrue(isFrozen(deviceVerificationUrl))
        assertEquals("ABCD-EFGH", authentication.state.deviceUserCode)
        assertEquals("https://auth.openai.com/device", states.last().deviceVerificationUrl?.value)
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

private suspend fun awaitCondition(
    message: String = "Condition did not become true",
    condition: () -> Boolean,
) {
    repeat(100) {
        if (condition()) return
        yield()
    }
    assertTrue(condition(), message)
}

private class ApiTestPlatform(
    private val runtime: ApiTestRuntime,
    private val restoreEntered: CompletableDeferred<Unit>? = null,
    private val restoreRelease: CompletableDeferred<Unit>? = null,
    private val features: Set<CodexRuntimeFeature> = emptySet(),
    private val workspacePath: String = "/workspace",
    private val restoreResolution: CodexWorkspaceResolution? = null,
    private val restoreFailure: Throwable? = null,
    private val prepareEntered: CompletableDeferred<Unit>? = null,
    private val prepareRelease: CompletableDeferred<Unit>? = null,
    authorizationBrowser: CodexAuthorizationBrowser =
        CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
) : CodexPlatform {
    var selectedWorkspacePath: String? = null
    var failNextPrepare: Boolean = false

    override val authorizationBrowser: CodexAuthorizationBrowser = authorizationBrowser
    override val workspaceStore: CodexWorkspaceStore = object : CodexWorkspaceStore {
        override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution {
            val path = (selection as CodexPathWorkspaceSelection).path
            selectedWorkspacePath = path
            return CodexWorkspaceResolution.Available(CodexWorkspace(path))
        }

        override suspend fun restore(): CodexWorkspaceResolution {
            restoreEntered?.complete(Unit)
            restoreRelease?.await()
            restoreFailure?.let { throw it }
            return restoreResolution ?: CodexWorkspaceResolution.Available(CodexWorkspace(workspacePath))
        }

        override suspend fun clear(): Unit = Unit
    }

    override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
        prepareEntered?.complete(Unit)
        prepareRelease?.await()
        if (failNextPrepare) {
            failNextPrepare = false
            error("prepare denied")
        }
        return PreparedCodexRuntime(
            runtimeFactory = { runtime },
            workspacePath = workspace.path,
            features = features,
        )
    }
}

private class RecordingAuthorizationBrowser : CodexAuthorizationBrowser {
    val urls: MutableList<io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl> = mutableListOf()
    var closedPresentations: Int = 0

    override fun open(
        url: io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl,
    ): CodexAuthorizationPresentation {
        urls += url
        return CodexAuthorizationPresentation { closedPresentations += 1 }
    }
}

private fun <T> List<T>.distinctConsecutive(): List<T> = filterIndexed { index, value ->
    index == 0 || this[index - 1] != value
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

private fun objectKeys(value: Any): Array<String> = js("Object.keys(value)")

private fun javaScriptBigInt(value: String): Long = js("BigInt(value)").unsafeCast<Long>()

private const val SKILL_FIXTURE_CONTENT =
    "---\nname: fixture-skill\ndescription: Fixture skill\n---\nBinding projection body.\n"
private const val HOOK_FIXTURE_CONTENT =
    "{\"hooks\":{\"PreToolUse\":[{\"matcher\":\"Shell\",\"hooks\":[" +
        "{\"type\":\"command\",\"command\":\"sh scripts/lint.sh\"}]}]}}\n"

private data class SkillTestFixture(
    val root: String,
    val workspacePath: String,
    val sourceDirectory: String,
    val sourceManifestPath: String,
    val installedManifestPath: String,
    val hookSourceDirectory: String,
    val hookSourceConfigPath: String,
    val installedHookConfigPath: String,
    val installedHookAssetDirectory: String,
)

private fun createSkillTestFixture(): SkillTestFixture {
    val fs: dynamic = js("require('node:fs')")
    val os: dynamic = js("require('node:os')")
    val path: dynamic = js("require('node:path')")
    val root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "codex-js-skills-"))) as String
    val workspacePath = path.join(root, "workspace") as String
    val sourceDirectory = path.join(root, "fixture-skill") as String
    val sourceManifestPath = path.join(sourceDirectory, "SKILL.md") as String
    val hookSourceDirectory = path.join(root, "fixture-hook") as String
    val hookSourceConfigPath = path.join(hookSourceDirectory, "hooks.json") as String
    fs.mkdirSync(workspacePath, js("({ recursive: true })"))
    fs.mkdirSync(sourceDirectory, js("({ recursive: true })"))
    fs.mkdirSync(path.join(hookSourceDirectory, "scripts"), js("({ recursive: true })"))
    fs.writeFileSync(sourceManifestPath, SKILL_FIXTURE_CONTENT, "utf8")
    fs.writeFileSync(hookSourceConfigPath, HOOK_FIXTURE_CONTENT, "utf8")
    fs.writeFileSync(path.join(hookSourceDirectory, "scripts", "lint.sh"), "echo lint\n", "utf8")
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
        hookSourceDirectory = hookSourceDirectory,
        hookSourceConfigPath = hookSourceConfigPath,
        installedHookConfigPath = path.join(workspacePath, ".codex", "hooks.json") as String,
        installedHookAssetDirectory = path.join(
            workspacePath,
            ".codex",
            ".codex-agent-hooks",
            "fixture-hook",
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
    val turnStartRequests: MutableList<JsonObject> = mutableListOf()
    val threadReadRequests: MutableList<JsonObject> = mutableListOf()
    var failNextThreadRead: Boolean = false
    var mismatchNextThreadRead: Boolean = false
    val threadListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextThreadList: Boolean = false
    val appListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextAppList: Boolean = false
    var connectorAccessible: Boolean = true
    val pluginListRequests: MutableList<JsonObject> = mutableListOf()
    val pluginInstalledRequests: MutableList<JsonObject> = mutableListOf()
    val pluginReadRequests: MutableList<JsonObject> = mutableListOf()
    val pluginInstallRequests: MutableList<JsonObject> = mutableListOf()
    val pluginUninstallRequests: MutableList<JsonObject> = mutableListOf()
    var failNextPluginList: Boolean = false
    var failNextPluginRead: Boolean = false
    var failNextPluginInstall: Boolean = false
    var failNextPluginUninstall: Boolean = false
    val modelListRequests: MutableList<JsonObject> = mutableListOf()
    val configReadRequests: MutableList<JsonObject> = mutableListOf()
    var failNextModelList: Boolean = false
    var failNextConfigRead: Boolean = false
    var emptyNextModelList: Boolean = false
    val skillListRequests: MutableList<JsonObject> = mutableListOf()
    var failNextSkillList: Boolean = false
    var skillWorkspacePath: String = "/workspace"
    var skillManifestPath: String? = null
    val hookListRequests: MutableList<JsonObject> = mutableListOf()
    val configBatchWriteRequests: MutableList<JsonObject> = mutableListOf()
    val mcpStatusRequests: MutableList<JsonObject> = mutableListOf()
    val mcpReloadRequests: MutableList<JsonObject> = mutableListOf()
    val mcpBatchWriteRequests: MutableList<JsonObject> = mutableListOf()
    var failNextHookList: Boolean = false
    var failNextMcpStatus: Boolean = false
    var failNextMcpOauthLogin: Boolean = false
    val mcpOauthRequests: MutableList<JsonObject> = mutableListOf()
    var hookInstalledSourcePath: String? = null
    var hookVisible: Boolean = false
    var revealHookAtRequest: Int? = null
    var hideHookAtRequest: Int? = null
    var modelPreference: String = "model-preferred"
    var effortPreference: String = "low"
    var serviceTierPreference: String = "fast"
    private val mcpConfigurations: MutableMap<String, JsonObject> = linkedMapOf()
    private var mcpConfigurationVersion: Int = 1
    private var loginAttempts: Int = 0
    private var turnStarts: Int = 0
    private var activeTurnId: String = "turn-js"

    suspend fun completeTurn(): Unit = notify("turn/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turn", completedTurn(activeTurnId))
    })

    suspend fun failTurn(): Unit = notify("turn/completed", buildJsonObject {
        put("threadId", "thread-js")
        putJsonObject("turn") {
            put("id", activeTurnId)
            putJsonArray("items") {}
            put("status", "failed")
            putJsonObject("error") { put("message", "retained failure") }
        }
    })

    suspend fun emitAgentMessageDelta(text: String): Unit = notify("item/agentMessage/delta", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", activeTurnId)
        put("itemId", "assistant-live")
        put("delta", text)
    })

    suspend fun emitPlanUpdated(): Unit = notify("turn/plan/updated", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", activeTurnId)
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
        put("turnId", activeTurnId)
        put("run", hookRun("running", "Running hook", listOf("started")))
    })

    suspend fun emitHookCompleted(): Unit = notify("hook/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", activeTurnId)
        put("run", hookRun("completed", "Complete", listOf("finished", "detached")))
    })

    suspend fun completeConnectorAuthorization(): Unit {
        connectorAccessible = true
        notify("app/list/updated", connectorUpdateResult(connectorAccessible))
    }

    suspend fun completeMcpAuthorization(name: String): Unit =
        notify("mcpServer/oauthLogin/completed", buildJsonObject {
            put("threadId", "thread-js")
            put("name", name)
            put("success", true)
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
                threadReadRequests += params
                when {
                    failNextThreadRead -> {
                        failNextThreadRead = false
                        respondError(id, "conversation read denied")
                    }
                    mismatchNextThreadRead -> {
                        mismatchNextThreadRead = false
                        respond(id, threadReadResult("thread-other"))
                    }
                    else -> respond(
                        id,
                        threadReadResult(checkNotNull(params["threadId"]).jsonPrimitive.content),
                    )
                }
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
                    respond(id, appListResult(cursor, connectorAccessible))
                }
            }
            "plugin/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                pluginListRequests += params
                if (failNextPluginList) {
                    failNextPluginList = false
                    respondError(id, "plugin list denied")
                } else {
                    respond(id, pluginListResult(installed = false))
                }
            }
            "plugin/installed" -> {
                val params = checkNotNull(request["params"]).jsonObject
                pluginInstalledRequests += params
                respond(id, pluginListResult(installed = true))
            }
            "plugin/read" -> {
                val params = checkNotNull(request["params"]).jsonObject
                pluginReadRequests += params
                if (failNextPluginRead) {
                    failNextPluginRead = false
                    respondError(id, "plugin read denied")
                } else {
                    respond(id, pluginDetailResult())
                }
            }
            "plugin/install" -> {
                val params = checkNotNull(request["params"]).jsonObject
                pluginInstallRequests += params
                if (failNextPluginInstall) {
                    failNextPluginInstall = false
                    respondError(id, "plugin install denied")
                } else {
                    respond(id, buildJsonObject {
                        put("authPolicy", "ON_INSTALL")
                        putJsonArray("appsNeedingAuth") { add(pluginConnectorResult()) }
                    })
                }
            }
            "plugin/uninstall" -> {
                val params = checkNotNull(request["params"]).jsonObject
                pluginUninstallRequests += params
                if (failNextPluginUninstall) {
                    failNextPluginUninstall = false
                    respondError(id, "plugin uninstall denied")
                } else {
                    respond(id, buildJsonObject {})
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
            "hooks/list" -> {
                val params = checkNotNull(request["params"]).jsonObject
                hookListRequests += params
                if (hookListRequests.size == revealHookAtRequest) hookVisible = true
                if (hookListRequests.size == hideHookAtRequest) hookVisible = false
                if (failNextHookList) {
                    failNextHookList = false
                    respondError(id, "hook list denied")
                } else {
                    respond(
                        id,
                        hookListResult(
                            skillWorkspacePath,
                            hookInstalledSourcePath.takeIf { hookVisible },
                        ),
                    )
                }
            }
            "config/read" -> {
                val params = checkNotNull(request["params"]).jsonObject
                configReadRequests += params
                if (failNextConfigRead) {
                    failNextConfigRead = false
                    respondError(id, "model preferences denied")
                } else {
                    respond(id, configReadResult())
                }
            }
            "config/batchWrite" -> {
                val params = checkNotNull(request["params"]).jsonObject
                configBatchWriteRequests += params
                checkNotNull(params["edits"]).jsonArray.forEach { element ->
                    val edit = element.jsonObject
                    val keyPath = edit["keyPath"]?.jsonPrimitive?.content.orEmpty()
                    if (keyPath.startsWith("mcp_servers.\"")) {
                        mcpBatchWriteRequests += edit
                        val name = keyPath.removePrefix("mcp_servers.\"").removeSuffix("\"")
                        val value = checkNotNull(edit["value"])
                        if (value == JsonNull) {
                            mcpConfigurations.remove(name)
                        } else {
                            mcpConfigurations[name] = value.jsonObject
                        }
                        mcpConfigurationVersion += 1
                    }
                }
                respond(id, buildJsonObject {
                    put("filePath", "/tmp/codex/config.toml")
                    put("status", "ok")
                    put("version", mcpConfigurationVersion.toString())
                })
            }
            "config/mcpServer/reload" -> {
                mcpReloadRequests += checkNotNull(request["params"]).jsonObject
                respond(id, buildJsonObject {})
            }
            "mcpServerStatus/list" -> {
                ensureMcpConfiguration()
                val params = checkNotNull(request["params"]).jsonObject
                mcpStatusRequests += params
                if (failNextMcpStatus) {
                    failNextMcpStatus = false
                    respondError(id, "MCP server list denied")
                } else {
                    respond(id, buildJsonObject {
                        putJsonArray("data") {
                            mcpConfigurations.keys.sorted().forEach { name ->
                                add(buildJsonObject {
                                    put("name", name)
                                    put("authStatus", if (name == "configured") "bearerToken" else "oAuth")
                                    putJsonArray("resourceTemplates") {}
                                    putJsonArray("resources") {}
                                    putJsonObject("tools") {}
                                    putJsonObject("serverInfo") {
                                        put("name", name)
                                        put("title", if (name == "configured") {
                                            "Configured server"
                                        } else {
                                            "Remote server"
                                        })
                                        put("version", "1")
                                    }
                                })
                            }
                        }
                    })
                }
            }
            "mcpServer/oauth/login" -> {
                val params = checkNotNull(request["params"]).jsonObject
                mcpOauthRequests += params
                if (failNextMcpOauthLogin) {
                    failNextMcpOauthLogin = false
                    respondError(id, "MCP authorization denied")
                } else {
                    respond(id, buildJsonObject {
                        put(
                            "authorizationUrl",
                            "https://accounts.example.com/oauth/${params["name"]?.jsonPrimitive?.content}",
                        )
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
            "turn/start" -> {
                turnStartRequests += checkNotNull(request["params"]).jsonObject
                activeTurnId = "turn-js-${++turnStarts}"
                respond(id, turnStartResult(activeTurnId))
            }
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

    private fun ensureMcpConfiguration(): Unit {
        if (mcpConfigurations.isNotEmpty()) return
        mcpConfigurations["configured"] = buildJsonObject {
            put("command", "node")
            putJsonArray("args") { add(JsonPrimitive("server.js")) }
            put("cwd", skillWorkspacePath)
            putJsonObject("env") { put("TOKEN", "value") }
            putJsonArray("env_vars") { add(JsonPrimitive("HOME")) }
            put("environment_id", "local")
            put("enabled", true)
            put("required", false)
            put("supports_parallel_tool_calls", false)
        }
    }

    private fun configReadResult(): JsonObject {
        ensureMcpConfiguration()
        return buildJsonObject {
            putJsonObject("config") {
                put("model", modelPreference)
                put("model_reasoning_effort", effortPreference)
                put("service_tier", serviceTierPreference)
                putJsonObject("mcp_servers") {
                    mcpConfigurations.forEach { (name, configuration) -> put(name, configuration) }
                }
            }
            putJsonObject("origins") {
                mcpConfigurations.keys.forEach { name ->
                    putJsonObject("mcp_servers.$name.url") {
                        putJsonObject("name") {
                            put("type", "user")
                            put("file", "/tmp/codex/config.toml")
                        }
                        put("version", mcpConfigurationVersion.toString())
                    }
                }
            }
            putJsonArray("layers") {
                add(buildJsonObject {
                    putJsonObject("config") {
                        putJsonObject("mcp_servers") {
                            mcpConfigurations.forEach { (name, configuration) -> put(name, configuration) }
                        }
                    }
                    putJsonObject("name") {
                        put("type", "user")
                        put("file", "/tmp/codex/config.toml")
                    }
                    put("version", mcpConfigurationVersion.toString())
                })
            }
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

private fun hookListResult(workspacePath: String, installedSourcePath: String?): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("cwd", workspacePath)
            putJsonArray("warnings") {
                add(JsonPrimitive("review warning"))
                add(JsonPrimitive("review warning"))
            }
            putJsonArray("errors") {
                add(buildJsonObject {
                    put("path", "$workspacePath/.codex/hooks.json")
                    put("message", "ignored hook")
                })
            }
            putJsonArray("hooks") {
                add(hookMetadata(
                    key = "z-command",
                    handlerType = "command",
                    source = "project",
                    sourcePath = "$workspacePath/.codex/hooks.json",
                    trustStatus = "untrusted",
                    matcher = "Shell",
                    statusMessage = "Review shell commands",
                ))
                add(hookMetadata(
                    key = "a-mcp",
                    handlerType = "mcpTool",
                    source = "plugin",
                    sourcePath = "/plugins/review/hooks.json",
                    trustStatus = "modified",
                    pluginId = "review-plugin",
                ))
                add(hookMetadata(
                    key = "m-agent",
                    handlerType = "agent",
                    source = "system",
                    sourcePath = "/etc/codex/hooks.json",
                    trustStatus = "managed",
                    isManaged = true,
                ))
                add(hookMetadata(
                    key = "p-prompt",
                    handlerType = "prompt",
                    source = "user",
                    sourcePath = "/home/test/.codex/hooks.json",
                    trustStatus = "trusted",
                ))
                add(hookMetadata(
                    key = "z-command",
                    handlerType = "command",
                    source = "project",
                    sourcePath = "$workspacePath/.codex/hooks.json",
                    trustStatus = "untrusted",
                ))
                if (installedSourcePath != null) {
                    add(hookMetadata(
                        key = "fixture-installed",
                        handlerType = "command",
                        source = "project",
                        sourcePath = installedSourcePath,
                        trustStatus = "untrusted",
                    ))
                }
            }
        })
    }
}

private fun hookMetadata(
    key: String,
    handlerType: String,
    source: String,
    sourcePath: String,
    trustStatus: String,
    matcher: String? = null,
    pluginId: String? = null,
    statusMessage: String? = null,
    isManaged: Boolean = false,
): JsonObject = buildJsonObject {
    put("currentHash", "sha256:$key")
    put("displayOrder", 0)
    put("enabled", true)
    put("eventName", "preToolUse")
    put("handlerType", handlerType)
    put("isManaged", isManaged)
    put("key", key)
    put("source", source)
    put("sourcePath", sourcePath)
    put("timeoutSec", 10)
    put("trustStatus", trustStatus)
    matcher?.let { put("matcher", it) }
    pluginId?.let { put("pluginId", it) }
    statusMessage?.let { put("statusMessage", it) }
    when (handlerType) {
        "command" -> put("command", "./check")
        "mcpTool" -> {
            put("server", "review-server")
            put("tool", "review-tool")
        }
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
    put(
        "thread",
        threadResult(
            turns = buildJsonArray { add(completedTurn()) },
            threadId = threadId,
            name = "History title",
            updatedAt = -9_007_199_254_740_993L,
        ),
    )
}

private const val REMOTE_PLUGIN_ID = "plugin_remote_drive"

private fun pluginListResult(installed: Boolean): JsonObject = buildJsonObject {
    putJsonArray("marketplaces") {
        add(buildJsonObject {
            put("name", "openai-curated")
            putJsonArray("plugins") { add(pluginSummaryResult(installed)) }
        })
    }
    putJsonArray("marketplaceLoadErrors") {}
}

private fun pluginSummaryResult(installed: Boolean): JsonObject = buildJsonObject {
    put("id", "drive@openai-curated")
    put("remotePluginId", REMOTE_PLUGIN_ID)
    put("name", "drive")
    put("installed", installed)
    put("enabled", true)
    put("installPolicy", "AVAILABLE")
    put("authPolicy", "ON_INSTALL")
    put("availability", "AVAILABLE")
    putJsonObject("source") { put("type", "remote") }
    putJsonObject("interface") {
        put("displayName", "Drive")
        put("shortDescription", "Files in Drive")
        put("brandColor", "#4285f4")
        put("privacyPolicyUrl", "https://example.com/privacy")
        put("termsOfServiceUrl", "https://example.com/terms")
        put("websiteUrl", "https://example.com")
        putJsonArray("capabilities") {
            add(JsonPrimitive("Search files"))
            add(JsonPrimitive("Share files"))
        }
        putJsonArray("screenshotUrls") {}
        putJsonArray("screenshots") {}
    }
}

private fun pluginConnectorResult(): JsonObject = buildJsonObject {
    put("id", "drive")
    put("name", "Drive")
    put("description", "Files")
    put("installUrl", "https://accounts.example.com/oauth")
    put("isAccessible", true)
    put("isEnabled", true)
}

private fun pluginDetailResult(): JsonObject = buildJsonObject {
    putJsonObject("plugin") {
        put("marketplaceName", "openai-curated")
        put("summary", pluginSummaryResult(installed = true))
        put("description", "Complete Drive plugin")
        putJsonArray("skills") {
            add(buildJsonObject {
                put("name", "search-drive")
                put("description", "Search Drive")
                put("enabled", true)
                put("path", "/plugins/drive/search/SKILL.md")
            })
        }
        putJsonArray("apps") { add(pluginConnectorResult()) }
        putJsonArray("appTemplates") {}
        putJsonArray("mcpServers") { add(JsonPrimitive("drive-mcp")) }
        putJsonArray("hooks") {
            add(buildJsonObject {
                put("eventName", "preToolUse")
                put("key", "drive-check")
            })
        }
    }
}

private fun appListResult(cursor: String?, isAccessible: Boolean = true): JsonObject = buildJsonObject {
    putJsonArray("data") {
        when (cursor) {
            null -> add(buildJsonObject {
                put("id", "connector-custom")
                put("name", "Custom connector")
                put("description", "Custom description")
                put("installUrl", "https://example.com/install")
                put("isAccessible", isAccessible)
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

private fun connectorUpdateResult(isAccessible: Boolean): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("id", "connector-custom")
            put("name", "Custom connector")
            put("description", "Custom description")
            put("installUrl", "https://example.com/install")
            put("isAccessible", isAccessible)
            put("isEnabled", false)
            putJsonArray("pluginDisplayNames") {
                add(JsonPrimitive("Plugin one"))
                add(JsonPrimitive("Plugin two"))
            }
        })
    }
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

private fun turnStartResult(turnId: String): JsonObject = buildJsonObject {
    putJsonObject("turn") {
        put("id", turnId)
        putJsonArray("items") {}
        put("status", "inProgress")
    }
}

private fun completedTurn(turnId: String = "turn-js"): JsonObject = buildJsonObject {
    put("id", turnId)
    putJsonArray("items") {
        add(buildJsonObject {
            put("id", "user-1")
            put("type", "userMessage")
            put("clientId", "codex-agent:plan:client-plan")
            putJsonArray("content") {
                add(buildJsonObject {
                    put("type", "text")
                    put(
                        "text",
                        "${CoreCapability.WEB_SEARCH.promptLabel}\n\$review\n@drive\n\nhello",
                    )
                    putJsonArray("text_elements") {
                        add(buildJsonObject {
                            putJsonObject("byteRange") {
                                put("start", 0)
                                put("end", CoreCapability.WEB_SEARCH.promptLabel.encodeToByteArray().size)
                            }
                            put("placeholder", CoreCapability.WEB_SEARCH.displayLabel)
                        })
                    }
                })
                add(buildJsonObject {
                    put("type", "text")
                    put(
                        "text",
                        "${CoreCapability.WEB_SEARCH.promptLabel}\n\$review\n@drive\n\nmalformed",
                    )
                    putJsonArray("text_elements") {
                        add(buildJsonObject {
                            putJsonObject("byteRange") {
                                put("start", 0)
                                put("end", 1)
                            }
                            put("placeholder", CoreCapability.WEB_SEARCH.displayLabel)
                        })
                    }
                })
                add(buildJsonObject {
                    put("type", "skill")
                    put("name", "review")
                    put("path", "/skills/review/SKILL.md")
                })
                add(buildJsonObject {
                    put("type", "mention")
                    put("name", "drive")
                    put("path", "plugin://drive@catalog")
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
