package io.github.codex_agent_labs.codexmobile.agent

import okio.FileSystem
import okio.Path.Companion.toPath
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.*
import io.github.codex_agent_labs.codexmobile.agent.*
import java.io.File
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class PluginCatalogProtocolTest : SkillsPluginsProtocolTestBase() {
    @CoversApi(
        "api-v1:AgentConnector#property:id#sha256:d2a70084792adbad6ba0a191fbaf2d53973d852dd219b92523ccbc449f4984d8",
        "api-v1:AgentConnector#property:isAccessible#sha256:3de52c0684d79bd13f450803ed317320ecbb29342fa63956cf96c1c01dcfe86e",
        "api-v1:AgentPluginDetail#property:connectors#sha256:d90b334bb62d93accbd2af0d79ab7171627af537c0595e11d16980cfcb0215b2",
        "api-v1:AgentPluginInstallResult#property:connectorsNeedingAuthentication#sha256:a90e0efa15ce975ed9f2b3c6578c15c95af2d7c27b1d32ae6d18af59c63ce8aa",
        "api-v1:AgentPluginReference#property:remotePluginId#sha256:308f4e87e74872fd7265fc5ec704ab740992a0fbd0ee94a0274f00e22207f92b",
        "api-v1:AgentPluginSummary#property:isInstalled#sha256:624c44a48f0477e526e46867aea4c524caa30730f3e3e99971b41d4afbc1ac67",
        "api-v1:AgentPluginSummary#property:reference#sha256:3d00a1a8c42d645608154aa36aa424ab97a4fb81f74ee215c8a160be3e26eeea",
        "api-v1:AgentSkill#property:name#sha256:5179b1b326402cfff9a476e64f461b9bb8c57f94f750d5bb1304b0b30d5e87db",
        "api-v1:AgentSkillCatalog#property:skills#sha256:1236827bf6eb253ae51a9271fc5b5db41767f8f61cdc28281d6c5af8237c9c4b",
        "api-v1:CodexConnectors#function:list#sha256:a0c9ff8462bfbe18c79183138e826bb59f8a382577532551dd7cf0026f214b2a",
        "api-v1:CodexConnectors#property:isAvailable#sha256:88d72c72af4c4dad9127f7e0d3f97dca6a9107ff7be56329dcd71c6ae9c19528",
        "api-v1:CodexMcpServers#property:isAvailable#sha256:6e0822d5e8c059db1f4aa5d2d2414cbad8ed10d2fe2f797ea8fbd45859df9135",
        "api-v1:CodexPlugins#function:install#sha256:79ea3b44dba7378fc0898da4cb4a7c5bd4fe6eb451834abbd7fb34e4a693b1b3",
        "api-v1:CodexPlugins#function:list#sha256:7167fd4d5db6763fb5b06469efa5bb8b8f9b0d1897ab6e0c1e04334ee2d128e2",
        "api-v1:CodexPlugins#function:read#sha256:3262a5b50d68ce0c7d154f58bccd7e146bce3e96f7f138a21e7978c8f8044d5d",
        "api-v1:CodexPlugins#function:uninstall#sha256:d0b5300754623c6cd47020d1369a597089c60244498c6c3d5c03b6bdb513f1ec",
        "api-v1:CodexPlugins#property:isAvailable#sha256:c2e5824beb9328a2f90513c6f388e1953a619b74e4e9f141e6f3b33501d1d8c7",
        "api-v1:CodexSkills#function:list#sha256:e2629df3b435cfc68cafb2ece5cb080993bb99987d66a51f4ff9e74d9688d145",
    )
    @Test
    fun usesPinnedAppServerCapabilityEndpoints(): Unit = runBlocking {
        val methods = mutableListOf<String>()
        var skillWrite: Boolean? = null
        var pluginWrite: String? = null
        var pluginReadName: String? = null
        var pluginInstallName: String? = null
        var pluginUninstallId: String? = null
        val process = FakeCodexRuntime { message, server ->
            message.method?.let(methods::add)
            when (message.method) {
                "initialize" -> {
                    val capabilities = message.objectValue["params"]!!.jsonObject["capabilities"]!!.jsonObject
                    assertTrue(capabilities["experimentalApi"]!!.jsonPrimitive.content.toBoolean())
                    assertFalse(capabilities["mcpServerOpenaiFormElicitation"]!!.jsonPrimitive.content.toBoolean())
                    server.respond(message.id, buildJsonObject {})
                }
                "skills/list" -> server.respond(message.id, skillsResponse())
                "skills/config/write" -> {
                    skillWrite = message.objectValue["params"]!!.jsonObject["enabled"]!!.jsonPrimitive.content.toBoolean()
                    server.respond(message.id, buildJsonObject { put("effectiveEnabled", true) })
                }
                "plugin/list" -> server.respond(message.id, pluginList(installed = false))
                "plugin/installed" -> server.respond(message.id, pluginList(installed = true))
                "plugin/read" -> {
                    pluginReadName = message.objectValue["params"]!!.jsonObject["pluginName"]!!.jsonPrimitive.content
                    server.respond(message.id, pluginDetail())
                }
                "plugin/install" -> {
                    pluginInstallName = message.objectValue["params"]!!.jsonObject["pluginName"]!!.jsonPrimitive.content
                    server.respond(
                        message.id,
                        buildJsonObject {
                            put("authPolicy", "ON_INSTALL")
                            putJsonArray("appsNeedingAuth") { add(connector()) }
                        },
                    )
                }
                "plugin/uninstall" -> {
                    pluginUninstallId = message.objectValue["params"]!!.jsonObject["pluginId"]!!.jsonPrimitive.content
                    server.respond(message.id, buildJsonObject {})
                }
                "config/value/write" -> {
                    pluginWrite = message.objectValue["params"]!!.jsonObject["keyPath"]!!.jsonPrimitive.content
                    server.respond(message.id, buildJsonObject {})
                }
                "app/list" -> server.respond(
                    message.id,
                    buildJsonObject { putJsonArray("data") { add(connector()) } },
                )
                "mcpServerStatus/list" -> server.respond(
                    message.id,
                    buildJsonObject {
                        putJsonArray("data") {
                            add(buildJsonObject {
                                put("name", "codex_apps")
                                put("authStatus", "oAuth")
                            })
                            add(buildJsonObject {
                                put("name", "drive")
                                put("authStatus", "notLoggedIn")
                            })
                        }
                    },
                )
                "config/read" -> server.respond(
                    message.id,
                    buildJsonObject {
                        putJsonObject("config") {
                            putJsonObject("mcp_servers") {
                                putJsonObject("drive") { put("url", "https://mcp.example.com") }
                            }
                        }
                        putJsonObject("origins") {
                            putJsonObject("mcp_servers.drive.url") {
                                putJsonObject("name") {
                                    put("type", "user")
                                    put("file", "/tmp/config.toml")
                                }
                                put("version", "1")
                            }
                        }
                    },
                )
                "mcpServer/oauth/login" -> server.respond(
                    message.id,
                    buildJsonObject { put("authorizationUrl", "https://accounts.example.com/oauth") },
                )
            }
        }
        val client = CodexAgentClient(
            { process },
            requestTimeoutMillis = 1_000,
            fileSystem = FileSystem.SYSTEM,
        )
        val agent = catalogAgent(client, this)
        try {
            agent.start()
            assertTrue(agent.plugins.isAvailable)
            assertTrue(agent.connectors.isAvailable)
            assertTrue(agent.mcpServers.isAvailable)
            assertEquals("review", agent.skills.list().skills.single().name)
            client.setSkillEnabled("/skills/review/SKILL.md", true)
            assertFalse(client.listAvailablePlugins("/workspace").plugins.single().isInstalled)
            val plugin = agent.plugins.list().plugins.single()
            assertTrue(plugin.isInstalled)
            assertEquals("drive", agent.plugins.read(plugin.reference).connectors.single().id)
            assertEquals("drive", agent.plugins.install(plugin.reference).connectorsNeedingAuthentication.single().id)
            agent.plugins.uninstall(plugin.reference)
            client.setPluginEnabled(plugin.reference.id, true)
            assertTrue(agent.connectors.list().single().isAccessible)
            assertEquals("drive", agent.mcpServers.list().single().name)
            assertEquals("https://accounts.example.com/oauth", client.startMcpOauth("drive"))
            assertEquals(true, skillWrite)
            assertEquals("plugins.drive@openai-curated.enabled", pluginWrite)
            assertEquals(REMOTE_PLUGIN_ID, pluginReadName)
            assertEquals(REMOTE_PLUGIN_ID, pluginInstallName)
            assertEquals(REMOTE_PLUGIN_ID, pluginUninstallId)
            listOf("skills/list", "plugin/list", "plugin/installed", "plugin/read", "plugin/install", "app/list")
                .forEach { assertTrue(it in methods) }
        } finally {
            agent.close()
        }
    }

    @CoversApi(
        "api-v1:AgentSkillChunk#property:content#sha256:2671c1e322c677430a171ee2eeece774f6faa000bc7692f6c4adda1563e1912e",
        "api-v1:AgentSkillChunk#property:nextOffset#sha256:07905e415013a7f6ad8207ed6570b93ddd764bfda245b9e69a68c2e95a476371",
        "api-v1:CodexSkills#function:read#sha256:61741b94ce4f58f2d11408b5dacacdf8ac47e856ae82ecb5d2cba97b82340604",
    )
    @Test
    fun readsLongSkillSourceWithoutSplittingUtf8Characters(): Unit = runBlocking {
        val source = File.createTempFile("codex-skill-", ".md")
        val expected = "a".repeat(32 * 1024 - 1) + "€" + "tail"
        source.writeText(expected)
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "skills/list" -> server.respond(message.id, skillsResponse(source.absolutePath))
            }
        }
        val client = CodexAgentClient(
            { process },
            requestTimeoutMillis = 1_000,
            fileSystem = FileSystem.SYSTEM,
        )
        val agent = catalogAgent(client, this)
        try {
            agent.start()
            agent.skills.list()
            val actual = buildString {
                var offset: Long? = 0
                while (offset != null) {
                    val chunk = agent.skills.read(source.absolutePath, offset)
                    append(chunk.content)
                    offset = chunk.nextOffset
                }
            }
            assertEquals(expected, actual)
        } finally {
            agent.close()
            source.delete()
        }
    }

    @Test
    fun availablePluginDiscoveryServesCacheAndKeepsStaleDataAfterRefreshFailure(): Unit = runBlocking {
        val cache = Files.createTempDirectory("plugin-cache-").toFile()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "plugin/list" -> server.respond(message.id, pluginList(installed = false))
            }
        }
        CodexAgentClient(
            { process },
            requestTimeoutMillis = 1_000,
            pluginCacheDirectory = cache.absolutePath.toPath(),
            fileSystem = FileSystem.SYSTEM,
        ).use { client ->
            assertEquals(AgentCatalogFreshness.LIVE, client.listAvailablePlugins("/workspace").freshness)
        }

        val cached = CodexAgentClient(
            runtimeFactory = { error("Network should not be used for cached discovery") },
            requestTimeoutMillis = 100,
            pluginCacheDirectory = cache.absolutePath.toPath(),
            fileSystem = FileSystem.SYSTEM,
        )
        try {
            assertEquals(AgentCatalogFreshness.FRESH_CACHE, cached.listAvailablePlugins("/workspace").freshness)
            cache.listFiles().orEmpty().single { it.name.endsWith(".timestamp") }.writeText("0")
            assertEquals(AgentCatalogFreshness.STALE_CACHE, cached.listAvailablePlugins("/workspace").freshness)
            val fallback = cached.listAvailablePlugins("/workspace", forceRefresh = true)
            assertEquals(AgentCatalogFreshness.STALE_CACHE, fallback.freshness)
            assertTrue(fallback.plugins.isNotEmpty())
            assertTrue(fallback.errors.isNotEmpty())
        } finally {
            cached.close()
            cache.deleteRecursively()
        }
    }

    @Test
    fun pluginCacheIdentityIncludesTheFullClientIdentity() {
        val first = CodexAgentClient(
            runtimeFactory = { error("must not start") },
            clientName = "third_party",
            clientTitle = "First App",
            pluginCacheDirectory = "/cache".toPath(),
            fileSystem = FileSystem.SYSTEM,
        )
        val second = CodexAgentClient(
            runtimeFactory = { error("must not start") },
            clientName = "third_party",
            clientTitle = "Second App",
            pluginCacheDirectory = "/cache".toPath(),
            fileSystem = FileSystem.SYSTEM,
        )
        try {
            assertNotEquals(
                first.pluginCacheFileAction("/workspace", "available"),
                second.pluginCacheFileAction("/workspace", "available"),
            )
        } finally {
            first.close()
            second.close()
        }
    }

    @Test
    fun availablePluginDiscoveryRetriesAnEmptyCatalogWhileTheMarketplaceBecomesReady(): Unit = runBlocking {
        var requests = 0
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "plugin/list" -> {
                    requests++
                    server.respond(
                        message.id,
                        if (requests == 1) emptyPluginList() else pluginList(installed = false),
                    )
                }
            }
        }

        CodexAgentClient(
            runtimeFactory = { process },
            requestTimeoutMillis = 1_000,
            emptyPluginCatalogRetryDelaysMillis = listOf(0),
        ).use { client ->
            assertTrue(client.listAvailablePlugins("/workspace").plugins.isNotEmpty())
            assertEquals(2, requests)
        }
    }

    @Test
    fun installedPluginsPreserveMarketplaceRefreshFailures(): Unit = runBlocking {
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "plugin/installed" -> server.respond(
                    message.id,
                    buildJsonObject {
                        putJsonArray("marketplaces") {
                            add(buildJsonObject {
                                put("name", "openai-curated")
                                putJsonArray("plugins") { add(pluginSummary(installed = true)) }
                            })
                        }
                        putJsonArray("marketplaceLoadErrors") {
                            add(buildJsonObject { put("message", "Stream Closed") })
                        }
                    },
                )
            }
        }

        CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000).use { client ->
            val catalog = client.listInstalledPlugins("/workspace")
            assertTrue(catalog.plugins.single().isInstalled)
            assertEquals(listOf("Stream Closed"), catalog.errors)
        }
    }

    @Test
    fun installedPluginRefreshAcceptsAnAuthoritativeEmptyResponse(): Unit = runBlocking {
        val cache = Files.createTempDirectory("installed-plugin-cache-").toFile()
        val populated = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "plugin/installed" -> server.respond(message.id, pluginList(installed = true))
            }
        }
        CodexAgentClient(
            { populated },
            requestTimeoutMillis = 1_000,
            pluginCacheDirectory = cache.absolutePath.toPath(),
            fileSystem = FileSystem.SYSTEM,
        ).use { client ->
            assertTrue(client.listInstalledPlugins("/workspace").plugins.single().isInstalled)
        }

        val empty = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "plugin/installed" -> server.respond(message.id, emptyPluginList())
            }
        }
        CodexAgentClient(
            { empty },
            requestTimeoutMillis = 1_000,
            pluginCacheDirectory = cache.absolutePath.toPath(),
            fileSystem = FileSystem.SYSTEM,
        ).use { client ->
            val catalog = client.listInstalledPlugins("/workspace", forceRefresh = true)
            assertEquals(AgentCatalogFreshness.LIVE, catalog.freshness)
            assertTrue(catalog.plugins.isEmpty())
            assertTrue(catalog.errors.isEmpty())
        }
        cache.deleteRecursively()
    }

}

private fun catalogAgent(client: CodexAgentClient, scope: CoroutineScope): CodexAgent = CodexAgent(
    workspace = CodexWorkspace("/workspace"),
    workingDirectory = "/workspace",
    features = CodexRuntimeFeature.entries.toSet(),
    client = client,
    parentScope = scope,
    authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
)
