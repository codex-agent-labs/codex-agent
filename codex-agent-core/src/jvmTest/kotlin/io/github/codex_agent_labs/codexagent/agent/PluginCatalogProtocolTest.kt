package io.github.codex_agent_labs.codexagent.agent

import okio.FileSystem
import okio.Path.Companion.toPath
import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.*
import io.github.codex_agent_labs.codexagent.agent.*
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
        "api-v1:AgentConnector#property:id#sha256:592f538290e554ca41d548a6c554bf287a0d0635dbf2fb77bc29ac08e12eebff",
        "api-v1:AgentConnector#property:isAccessible#sha256:f3c7d145a7cbe925a97882332b579de33357d200af0357f351f909b22420d587",
        "api-v1:AgentPluginDetail#property:connectors#sha256:04b9d3aa6a4b40afbedb1214d39695aafd92a29cd5788b0e1d618cd17215b2bb",
        "api-v1:AgentPluginInstallResult#property:connectorsNeedingAuthentication#sha256:e4c2f2e9fad216b27d941101a67314191b5b6e7facabddc0ac308a6e6ba32783",
        "api-v1:AgentPluginReference#property:remotePluginId#sha256:34dcd08d9cd3a323cb2212c76d19bb7332bf738d034af9316cf08f202059395a",
        "api-v1:AgentPluginSummary#property:isInstalled#sha256:ff6ede1da437b1c328474a2d5702a281ae28378eb1289ccc3dd382d7e5b5bdd9",
        "api-v1:AgentPluginSummary#property:reference#sha256:c995e55f3ddce1a64c54f4e30ed8f73bd6e0d9b29ab8768afec220738ad33eec",
        "api-v1:AgentSkill#property:name#sha256:9824b3ea2ade8cb4103f712ef6ce4ed09db5ea4186b08e47bf9f1bcd8057a3e5",
        "api-v1:AgentSkillCatalog#property:skills#sha256:f73896f3e9e02fbfab067a170f6048dea6d7752e99ee545362b14fe7a1feae96",
        "api-v1:CodexConnectors#function:list#sha256:071de35726da61101b674c5be1707b4e89ce99c6131959a8bf710e3e7148df19",
        "api-v1:CodexConnectors#property:isAvailable#sha256:a60859d681449f941857ff0567d42da65b398226006c166fc345d3617919b892",
        "api-v1:CodexMcpServers#property:isAvailable#sha256:175c5e64ebccb511cef6373c6b9c9f46a37a96f81e5127da117809b17a189700",
        "api-v1:CodexPlugins#function:install#sha256:a180f731c90b192270b231a1fcfa3e0e06a09840ddd9de3cd1cb942ec0a069e8",
        "api-v1:CodexPlugins#function:list#sha256:5bf93f0b91a388aec5335fb231e19b48a33740612b98c295ef4944bcb23c30e4",
        "api-v1:CodexPlugins#function:read#sha256:267b074dcc756f4c6b06a1927566762278586aa4c8e1603f7c9f1c267bbb672b",
        "api-v1:CodexPlugins#function:uninstall#sha256:686b2c60431a56ebc03366c94eed8d96a73440f38a9cd0af6913fc88b2d3baad",
        "api-v1:CodexPlugins#property:isAvailable#sha256:d1895c72061eadbd0b43800f0ff409270a87a8f6eeb50d41de19808b461ab41c",
        "api-v1:CodexSkills#function:list#sha256:8d21e6d81769031b4adddf2e32cd6a24814d0fc73c63144748f85f7b3a3634d0",
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
        "api-v1:AgentSkillChunk#property:content#sha256:05477483828911d7f56b3aa7a96f43579c68de331002ca3b1558d96ca45f2db4",
        "api-v1:AgentSkillChunk#property:nextOffset#sha256:a38d6952a6bdda8aa4c705a9f6bf520731cfe7ea12c314226a1f4fa39d38e509",
        "api-v1:CodexSkills#function:read#sha256:fd3f7b74e507f264b52598d9a19f04948705b2bc476a831e213923cf9937602d",
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
