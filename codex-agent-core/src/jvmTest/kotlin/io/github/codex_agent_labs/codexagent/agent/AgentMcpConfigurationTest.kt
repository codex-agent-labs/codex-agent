package io.github.codex_agent_labs.codexagent.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class AgentMcpConfigurationTest {
    @CoversApi(
        "api-v1:AgentMcpAuthentication#enum-entry:CHAT_GPT#sha256:2d75faedd0318afd085ccfe2d37bd08278e73ab63b840fc974969f11d44fe586",
        "api-v1:AgentMcpAuthentication#enum-entry:OAUTH#sha256:4ba59066e3060fbbaaaf75f4ef3c5da53dccb8713f652f6e76ef4e6fd4a4a5c6",
        "api-v1:AgentMcpEnvironmentSource#enum-entry:REMOTE#sha256:2d058e2805b3127ed58deb66c3f3f515df372478885c51b0d0677dc43a4dcba3",
        "api-v1:AgentMcpEnvironmentVariable#constructor:<init>#sha256:999f023b8f021232a48f702010713ff96cc752fe56d3827f6ff42aa623c900e9",
        "api-v1:AgentMcpEnvironmentVariable#property:name#sha256:206629ac6a729667168c2785afee674526efdccb9bffb29fbfac9c5915538511",
        "api-v1:AgentMcpEnvironmentVariable#property:source#sha256:c85add79466a8a8a499bb6728ec4b9c1e531a9a1570eac152c49e857eb82d049",
        "api-v1:AgentMcpOauthConfiguration#constructor:<init>#sha256:b225cfede5338c995d91bcb4b0ebe29f6c8f355707be9aa6b8780339ebe285f0",
        "api-v1:AgentMcpOauthConfiguration#property:callbackPort#sha256:cf814cd56994cc811cc29ec6ea35df4f812b8644c2ea0e5f54ab85bd27b70d75",
        "api-v1:AgentMcpOauthConfiguration#property:clientId#sha256:d64ee715f7b5643d5e5bc372ae1ea9e8f8147a5a585ab73540eb193591e6b146",
        "api-v1:AgentMcpServerConfiguration#constructor:<init>#sha256:effcddb7b6f7ad9f764c6dc6d0428f27d3b880685c2b2eba1915d2230e689708",
        "api-v1:AgentMcpServerConfiguration#property:authentication#sha256:3232abf88e0176598cae3636ab233f73eca2aef859cdce35a6d05b798d09a2eb",
        "api-v1:AgentMcpServerConfiguration#property:defaultToolApproval#sha256:19c6fd3c2321f189f6eb7d315209a6122bc532f1a96bbe8a00bdff2981d00a87",
        "api-v1:AgentMcpServerConfiguration#property:disabledTools#sha256:05157511ecfaf93353eb1cdb34ba2440b684b2a0cff415020120b7a5959b8197",
        "api-v1:AgentMcpServerConfiguration#property:enabledTools#sha256:9efe1f2ff9ee24732ab69f470246bc8910350c1dc6582a1b5aa0ebfe04b7f033",
        "api-v1:AgentMcpServerConfiguration#property:environmentId#sha256:174fe156b68148138fa767e1b42469a9a8d56376774ec95233e4b05d6aa0a05b",
        "api-v1:AgentMcpServerConfiguration#property:isEnabled#sha256:a68b0b8b95703644d1096a46509ac6468bfd6f157bee60a5bd4b1f7433cc495a",
        "api-v1:AgentMcpServerConfiguration#property:isRequired#sha256:16cceac9e3a555d56d8895907f419abe2c04a1016994bde53e74d62ea9513dd7",
        "api-v1:AgentMcpServerConfiguration#property:name#sha256:9ecb9724464edf526d39203389d7e2f329b665f58e516fea7747c4eab7480442",
        "api-v1:AgentMcpServerConfiguration#property:oauthResource#sha256:cba04f291c5cc9f887c683a44f3380e2b63eaf669b8537bef8c76f2181d77190",
        "api-v1:AgentMcpServerConfiguration#property:oauth#sha256:a242aae122414b7094b67b1ab809a4199c375c8b7786c0e75c6d4a8aa7699ee7",
        "api-v1:AgentMcpServerConfiguration#property:omitToolsFrom#sha256:ad2bf35e62fa6eec4601b667494fea040985092329ccf8fa58f0141d73f273c6",
        "api-v1:AgentMcpServerConfiguration#property:scopes#sha256:f7e35335d2a63d9682f13a40c6aaecf6e18b6f53482e19e2574763f82e661b70",
        "api-v1:AgentMcpServerConfiguration#property:startupTimeoutSeconds#sha256:3671447182f1416f601ffc1efb11129c69eee8c1830a5d454704109644bfc7cb",
        "api-v1:AgentMcpServerConfiguration#property:supportsParallelToolCalls#sha256:7f11bd0219a45cbb2f07982d04015e01a974887b004687547862ae2cfa18b25c",
        "api-v1:AgentMcpServerConfiguration#property:toolTimeoutSeconds#sha256:caa14cfaeaae9935e6c91cc31babf8bfd90a994e31b804127a2e7b78936b105e",
        "api-v1:AgentMcpServerConfiguration#property:tools#sha256:327aabcf090ea0a09a29d3e78c14e65bda8cfd7b03cf66494d7e21d3eb38a097",
        "api-v1:AgentMcpServerConfiguration#property:transport#sha256:f1aab3e789c19d41e5ac1d0a84cf7dbf6dbc156fdf6ebac74f01f2220af544ca",
        "api-v1:AgentMcpToolApproval#enum-entry:PROMPT#sha256:5ecc83a9401519eb03282bb18ecb5f478b5c345db6985d92b353501b993eb1ed",
        "api-v1:AgentMcpToolApproval#enum-entry:WRITES#sha256:d658f9746858b1a24a42047542e90aed7f2c9802f900f2ab96c204f7981b29cb",
        "api-v1:AgentMcpToolConfiguration#constructor:<init>#sha256:c65cb710c5392dcbe6c72429ca1b632f0f3e77290907bc111d9a8c34cb4f4a3c",
        "api-v1:AgentMcpToolConfiguration#property:approval#sha256:782f6804a9156ded5c1ad8a9566710fa0571e61e24fa66e1166d75183671d03d",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:CODE_MODE#sha256:f007717bf3bbdd72658a88bca1d3cf5431822ecddb0dc450570dbcbcfb83dae6",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:DEFERRED#sha256:66b60ad138bc4bb03365a1bfa2cd5177076619a55aa0e4bcabbc4bac993fbaa4",
        "api-v1:AgentMcpTransport.Http#constructor:<init>#sha256:7a6130f23b39e98dee83a8a3febb6b3d15fd52ff3fbd09ca7505bc9c16d140ea",
        "api-v1:AgentMcpTransport.Http#property:bearerTokenEnvironmentVariable#sha256:48e39cb36bb9a738ad681953e4587c152f6450d08578e68fc01c6982b3127e5c",
        "api-v1:AgentMcpTransport.Http#property:environmentHeaders#sha256:6bcf0f99d41ffc6606a9a5d2eb7ce991976dc0ad450cb6be92d7f035db09059e",
        "api-v1:AgentMcpTransport.Http#property:headersHelper#sha256:76016954745480fe05791aad078bf1a6550cfae82e93d07f0ccec449d8bcb6a3",
        "api-v1:AgentMcpTransport.Http#property:headers#sha256:0cbb23b3d90f78d33a4933452257079121c12c51897528c4400765cc65b2e203",
        "api-v1:AgentMcpTransport.Http#property:url#sha256:4ce1ab11496ffced8cb2ebca9d327ca451059078b12f91967ca0b6dd21a64b48",
        "api-v1:AgentMcpTransport.Stdio#constructor:<init>#sha256:e07b747d5f5dbb60a1fa531922f739d0baf0f57ada80c1be99dba663b90ff2dc",
        "api-v1:AgentMcpTransport.Stdio#property:arguments#sha256:73ae79ae42dfb46d6fd3a642743e97fc47a3c85bc8a129526a97bab894f98d9c",
        "api-v1:AgentMcpTransport.Stdio#property:command#sha256:3d6da18a19fca6ec409bd901c79e8ec0cf75cfc597186e08b713606d585b094a",
        "api-v1:AgentMcpTransport.Stdio#property:environment#sha256:2c17175222a9e16f1e2295a80976111f41e4ab72af5ab2310fb007f02b72eb99",
        "api-v1:AgentMcpTransport.Stdio#property:forwardedEnvironment#sha256:63ed45c2d1ea57bb85ab4739963bb5378428771e1450e6409df81ba93f86f653",
        "api-v1:AgentMcpTransport.Stdio#property:workingDirectory#sha256:624bedb57f339bfe5212bf0cbb09ee4177bbf7e8f70d4dedf4bbcf3eaa376357",
    )
    @Test
    fun typedConfigurationRoundTripsEverySupportedField() {
        val expected = AgentMcpServerConfiguration(
            name = "remote",
            transport = AgentMcpTransport.Http(
                url = "https://mcp.example.com",
                bearerTokenEnvironmentVariable = "MCP_TOKEN",
                headers = mapOf("X-Static" to "value"),
                environmentHeaders = mapOf("Authorization" to "MCP_AUTH"),
                headersHelper = "mcp-headers",
            ),
            authentication = AgentMcpAuthentication.CHAT_GPT,
            environmentId = "local",
            isEnabled = false,
            isRequired = true,
            supportsParallelToolCalls = true,
            omitToolsFrom = listOf(
                AgentMcpToolExposureSurface.CODE_MODE,
                AgentMcpToolExposureSurface.DEFERRED,
            ),
            startupTimeoutSeconds = 3.5,
            toolTimeoutSeconds = 9.0,
            defaultToolApproval = AgentMcpToolApproval.WRITES,
            enabledTools = listOf("read"),
            disabledTools = emptyList(),
            scopes = listOf("files.read"),
            oauth = AgentMcpOauthConfiguration("client", 9876),
            oauthResource = "https://mcp.example.com/resource",
            tools = mapOf("write" to AgentMcpToolConfiguration(AgentMcpToolApproval.PROMPT)),
        )

        assertEquals(expected, expected.toJson().toMcpConfiguration(expected.name))

        val stdio = AgentMcpServerConfiguration(
            name = "local",
            transport = AgentMcpTransport.Stdio(
                command = "node",
                arguments = listOf("server.js"),
                workingDirectory = "/workspace",
                environment = mapOf("STATIC" to "value"),
                forwardedEnvironment = listOf(
                    AgentMcpEnvironmentVariable("HOME"),
                    AgentMcpEnvironmentVariable("REMOTE_TOKEN", AgentMcpEnvironmentSource.REMOTE),
                ),
            ),
        )
        val stdioJson = stdio.toJson()
        assertEquals(buildJsonObject {
            put("command", "node")
            putJsonArray("args") { add(JsonPrimitive("server.js")) }
            put("cwd", "/workspace")
            putJsonObject("env") { put("STATIC", "value") }
            putJsonArray("env_vars") {
                add(JsonPrimitive("HOME"))
                add(buildJsonObject {
                    put("name", "REMOTE_TOKEN")
                    put("source", "remote")
                })
            }
            put("environment_id", "local")
            put("enabled", true)
            put("required", false)
            put("supports_parallel_tool_calls", false)
        }, stdioJson)
        assertEquals(stdio, stdioJson.toMcpConfiguration(stdio.name))
        assertNull(stdioJson.toMcpConfiguration(stdio.name).authentication)

        val defaultHttp = AgentMcpServerConfiguration(
            "default-http",
            AgentMcpTransport.Http("https://mcp.example.com"),
        )
        assertFalse("auth" in defaultHttp.toJson())
        assertFalse("auth" in defaultHttp.copy(authentication = AgentMcpAuthentication.OAUTH).toJson())
        assertNull(defaultHttp.toJson().toMcpConfiguration(defaultHttp.name).authentication)
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "invalid-stdio",
                AgentMcpTransport.Stdio("mcp"),
                authentication = AgentMcpAuthentication.OAUTH,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "invalid-stdio",
                AgentMcpTransport.Stdio("mcp"),
                oauth = AgentMcpOauthConfiguration(clientId = "client"),
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "invalid-stdio",
                AgentMcpTransport.Stdio("mcp"),
                oauthResource = "https://mcp.example.com/resource",
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "remote-helper",
                AgentMcpTransport.Http("https://mcp.example.com", headersHelper = "headers"),
                environmentId = "remote",
            )
        }
        assertFailsWith<IllegalArgumentException> {
            buildJsonObject {
                put("command", "mcp")
                put("auth", "oauth")
            }.toMcpConfiguration("invalid-stdio")
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpTransport.Http("http://localhost.evil.example/mcp")
        }
        assertFailsWith<IllegalArgumentException> { AgentMcpTransport.Http("https:///missing-host") }
        assertFailsWith<IllegalArgumentException> { AgentMcpTransport.Http("https://?missing-host") }
        assertFailsWith<IllegalArgumentException> { AgentMcpTransport.Http("https://mcp.example.com:invalid") }
        assertFailsWith<IllegalArgumentException> { AgentMcpTransport.Http("https://%ZZ") }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration("invalid.name", AgentMcpTransport.Stdio("mcp"))
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "infinite-startup",
                AgentMcpTransport.Stdio("mcp"),
                startupTimeoutSeconds = Double.POSITIVE_INFINITY,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "infinite-tool",
                AgentMcpTransport.Stdio("mcp"),
                toolTimeoutSeconds = Double.POSITIVE_INFINITY,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "overflowing-startup",
                AgentMcpTransport.Stdio("mcp"),
                startupTimeoutSeconds = Double.MAX_VALUE,
            )
        }
        assertFailsWith<IllegalArgumentException> {
            AgentMcpServerConfiguration(
                "overflowing-tool",
                AgentMcpTransport.Stdio("mcp"),
                toolTimeoutSeconds = Double.MAX_VALUE,
            )
        }
        AgentMcpTransport.Http("https://mcp.example.com:443/path")
        AgentMcpTransport.Http("http://[::1]:8080/mcp")
    }

    @CoversApi(
        "api-v1:AgentMcpServer#property:canRemove#sha256:a343bfe41fa24831246fa32bf7f5ebc19a7904e819fc7d615f3d7c156bc6e3be",
        "api-v1:AgentMcpServer#property:configuration#sha256:5ec562040c6af4148025ef39b700f9fde04b77b7af099b3b4f96f6b494a08f11",
        "api-v1:AgentMcpServer#property:name#sha256:5d9e26aee9403ddadafc5d792c24615f31c98573226d48314fe1b4e91ee891e1",
        "api-v1:AgentMcpServer#property:origin#sha256:25884a9ce3da4e023652e7d7a570bbe9d3454e259a928f4173518d0c9d0ec9ec",
        "api-v1:AgentResourceOrigin#enum-entry:WORKSPACE#sha256:689e3e945a510ea716121f024ac4175be3c864b9e50f7649353d40903b754558",
        "api-v1:CodexMcpServers#function:add#sha256:ae0fba56d8e257280ebfa5140b73ae26d54022576071415b7795050dcbd16099",
        "api-v1:CodexMcpServers#function:list#sha256:33638679a8e8f8fd42edee41377d3d84e5e8c1d7ea3aff73398582645ede8b43",
        "api-v1:CodexMcpServers#function:remove#sha256:72ccb61addfdfd77141740657354dcfd7aa3a762de77c64faeef9f621cccf820",
    )
    @Test
    fun appServerAddsAndRemovesOnlyFreshlyProvenUserConfiguration(): Unit = runBlocking {
        val inherited = AgentMcpServerConfiguration(
            "inherited",
            AgentMcpTransport.Stdio("base-command"),
        ).toJson()
        val profileOverride = AgentMcpServerConfiguration(
            "layered",
            AgentMcpTransport.Stdio("profile-command"),
        ).toJson()
        val baseConfigurations = linkedMapOf(
            "base-only" to inherited,
            "layered" to inherited,
        )
        val userConfigurations = linkedMapOf("layered" to profileOverride)
        val configurations = linkedMapOf(
            "managed" to AgentMcpServerConfiguration(
                "managed",
                AgentMcpTransport.Http("https://managed.example.com"),
            ).toJson(),
            "base-only" to inherited,
            "layered" to profileOverride,
        )
        val origins = mutableMapOf(
            "managed" to "project",
            "base-only" to "user",
            "layered" to "user",
        )
        val statusOnly = setOf("plugin")
        val writes = mutableListOf<String>()
        var version = 1
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "config/read" -> server.respond(
                    message.id,
                    configResponse(
                        configurations,
                        origins,
                        version,
                        userConfigurations,
                        baseConfigurations,
                    ),
                )
                "config/batchWrite" -> {
                    val edit = message.params.requiredArray("edits").single().jsonObject
                    val keyPath = edit.requiredString("keyPath")
                    writes += keyPath
                    val name = keyPath.removePrefix("mcp_servers.\"").removeSuffix("\"")
                        .replace("\\\"", "\"").replace("\\\\", "\\")
                    val value = edit.getValue("value")
                    if (value == JsonNull) {
                        userConfigurations.remove(name)
                        baseConfigurations[name]?.let { base ->
                            configurations[name] = base
                            origins[name] = "user"
                        } ?: run {
                            configurations.remove(name)
                            origins.remove(name)
                        }
                    } else {
                        val written = value.jsonObject
                        userConfigurations[name] = written
                        configurations[name] = written
                        origins[name] = "user"
                    }
                    version += 1
                    server.respond(message.id, buildJsonObject {
                        put("filePath", "/codex/config.toml")
                        put("status", "ok")
                        put("version", version.toString())
                    })
                }
                "config/mcpServer/reload" -> server.respond(message.id, buildJsonObject {})
                "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {
                        (configurations.keys + statusOnly).forEach { name ->
                            add(buildJsonObject {
                                put("name", name)
                                put("authStatus", "unsupported")
                            })
                        }
                    }
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val agent = CodexAgent(
            workspace = CodexWorkspace("/workspace"),
            workingDirectory = "/workspace",
            features = setOf(CodexRuntimeFeature.MCP_SERVERS),
            client = client,
            parentScope = this,
            authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        try {
            agent.start()
            val baseOnly = agent.mcpServers.list().single { it.name == "base-only" }
            assertEquals(AgentResourceOrigin.USER, baseOnly.origin)
            assertFalse(baseOnly.canRemove)
            assertFailsWith<IllegalArgumentException> { client.removeMcpServer(baseOnly, "/workspace") }
            assertTrue(writes.isEmpty())

            val layered = agent.mcpServers.list().single { it.name == "layered" }
            assertTrue(layered.canRemove)
            client.removeMcpServer(layered, "/workspace")
            val revealedBase = agent.mcpServers.list().single { it.name == "layered" }
            assertEquals(inherited, revealedBase.configuration?.toJson())
            assertEquals(AgentResourceOrigin.USER, revealedBase.origin)
            assertFalse(revealedBase.canRemove)

            val managed = agent.mcpServers.list().single { it.name == "managed" }
            assertEquals(AgentResourceOrigin.WORKSPACE, managed.origin)
            assertFalse(managed.canRemove)
            assertFailsWith<IllegalArgumentException> { client.removeMcpServer(managed, "/workspace") }
            assertEquals(1, writes.size)

            assertFailsWith<IllegalArgumentException> {
                client.addMcpServer(
                    AgentMcpServerConfiguration("plugin", AgentMcpTransport.Stdio("plugin-mcp")),
                    "/workspace",
                )
            }
            assertEquals(1, writes.size)

            val configuration = AgentMcpServerConfiguration(
                "new-server",
                AgentMcpTransport.Stdio("mcp", listOf("serve")),
            )
            val added = agent.mcpServers.add(configuration)
            assertEquals(configuration, added.configuration)
            assertEquals(AgentResourceOrigin.USER, added.origin)
            assertTrue(added.canRemove)
            assertEquals("mcp_servers.\"new-server\"", writes[1])

            agent.mcpServers.remove(added)
            assertNull(agent.mcpServers.list().singleOrNull { it.name == added.name })
            assertEquals(3, writes.size)
        } finally {
            agent.close()
        }
    }

    @Test
    fun ambiguousWriteFailureRollsBackOnlyTheExactActiveUserValue(): Unit = runBlocking {
        val configurations = linkedMapOf<String, JsonObject>()
        val origins = mutableMapOf<String, String>()
        val expectedVersions = mutableListOf<String?>()
        val concurrentValue = AgentMcpServerConfiguration(
            "concurrent",
            AgentMcpTransport.Stdio("other-writer"),
        ).toJson()
        var version = 1
        var writes = 0
        var replaceBeforeRecoveryRead = false
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "config/read" -> {
                    if (replaceBeforeRecoveryRead) {
                        configurations["concurrent"] = concurrentValue
                        version += 1
                        replaceBeforeRecoveryRead = false
                    }
                    server.respond(message.id, configResponse(configurations, origins, version))
                }
                "config/batchWrite" -> {
                    val edit = message.params.requiredArray("edits").single().jsonObject
                    expectedVersions += message.params.optionalString("expectedVersion")
                    val name = edit.requiredString("keyPath")
                        .removePrefix("mcp_servers.\"").removeSuffix("\"")
                    val value = edit.getValue("value")
                    if (value == JsonNull) {
                        configurations.remove(name)
                        origins.remove(name)
                    } else {
                        configurations[name] = value.jsonObject
                        origins[name] = "user"
                    }
                    version += 1
                    writes += 1
                    if (writes == 3) replaceBeforeRecoveryRead = true
                    if (writes == 2) {
                        server.respond(message.id, buildJsonObject {
                            put("filePath", "/codex/config.toml")
                            put("status", "ok")
                            put("version", version.toString())
                        })
                    }
                }
                "config/mcpServer/reload" -> server.respond(message.id, buildJsonObject {})
                "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {}
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        try {
            client.connection.ensureStarted(timeoutMillis = 1_000)
            assertFailsWith<AgentResourceInstallationException> {
                client.addMcpServer(
                    AgentMcpServerConfiguration("ambiguous", AgentMcpTransport.Stdio("mcp")),
                    "/workspace",
                )
            }
            assertFalse("ambiguous" in configurations)
            assertEquals(listOf<String?>("1", "2"), expectedVersions)
            assertEquals(2, writes)

            assertFailsWith<AgentResourcePartialChangeException> {
                client.addMcpServer(
                    AgentMcpServerConfiguration("concurrent", AgentMcpTransport.Stdio("ours")),
                    "/workspace",
                )
            }
            assertEquals(concurrentValue, configurations["concurrent"])
            assertEquals(listOf<String?>("1", "2", "3"), expectedVersions)
            assertEquals(3, writes)
        } finally {
            client.close()
        }
    }

    @Test
    fun addDoesNotClaimAConcurrentSameNameReplacement(): Unit = runBlocking {
        val configurations = linkedMapOf<String, JsonObject>()
        val userConfigurations = linkedMapOf<String, JsonObject>()
        val origins = mutableMapOf<String, String>()
        val replacement = AgentMcpServerConfiguration(
            "raced",
            AgentMcpTransport.Stdio("other-writer"),
        ).toJson()
        val expectedVersions = mutableListOf<String?>()
        var version = 1
        var reloads = 0
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "config/read" -> server.respond(
                    message.id,
                    configResponse(configurations, origins, version, userConfigurations),
                )
                "config/batchWrite" -> {
                    val expectedVersion = message.params.optionalString("expectedVersion")
                    expectedVersions += expectedVersion
                    if (expectedVersion != version.toString()) {
                        server.respondError(message.id, "configuration version changed")
                    } else {
                        val edit = message.params.requiredArray("edits").single().jsonObject
                        val value = edit.getValue("value").jsonObject
                        configurations["raced"] = value
                        userConfigurations["raced"] = value
                        origins["raced"] = "user"
                        version += 1
                        server.respond(message.id, buildJsonObject {
                            put("filePath", "/codex/config.toml")
                            put("status", "ok")
                            put("version", version.toString())
                        })
                    }
                }
                "config/mcpServer/reload" -> {
                    if (++reloads == 1) {
                        configurations["raced"] = replacement
                        userConfigurations["raced"] = replacement
                        version += 1
                    }
                    server.respond(message.id, buildJsonObject {})
                }
                "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {}
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        try {
            assertFailsWith<AgentResourcePartialChangeException> {
                client.addMcpServer(
                    AgentMcpServerConfiguration("raced", AgentMcpTransport.Stdio("ours")),
                    "/workspace",
                )
            }
            assertEquals(replacement, userConfigurations["raced"])
            assertEquals(listOf<String?>("1", "2"), expectedVersions)
            assertEquals(2, reloads)
        } finally {
            client.close()
        }
    }

    @Test
    fun cancellationAfterWriteRestoresConfigurationAndRemainsCancellation(): Unit = runBlocking {
        val configurations = linkedMapOf<String, JsonObject>()
        val origins = mutableMapOf<String, String>()
        val firstReload = CompletableDeferred<Unit>()
        var version = 1
        var reloads = 0
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "config/read" -> server.respond(
                    message.id,
                    configResponse(configurations, origins, version),
                )
                "config/batchWrite" -> {
                    val edit = message.params.requiredArray("edits").single().jsonObject
                    val name = edit.requiredString("keyPath")
                        .removePrefix("mcp_servers.\"").removeSuffix("\"")
                    val value = edit.getValue("value")
                    if (value == JsonNull) {
                        configurations.remove(name)
                        origins.remove(name)
                    } else {
                        configurations[name] = value.jsonObject
                        origins[name] = "user"
                    }
                    version += 1
                    server.respond(message.id, buildJsonObject {
                        put("filePath", "/codex/config.toml")
                        put("status", "ok")
                        put("version", version.toString())
                    })
                }
                "config/mcpServer/reload" -> if (++reloads == 1) {
                    firstReload.complete(Unit)
                } else {
                    server.respond(message.id, buildJsonObject {})
                }
                "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {}
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        try {
            val operation = async {
                client.addMcpServer(
                    AgentMcpServerConfiguration("cancelled", AgentMcpTransport.Stdio("mcp")),
                    "/workspace",
                )
            }
            firstReload.await()
            operation.cancel(CancellationException("cancel test"))
            assertFailsWith<CancellationException> { operation.await() }
            assertFalse("cancelled" in configurations)
            assertEquals(2, reloads)
        } finally {
            client.close()
        }
    }

    @Test
    fun reloadFailuresRestoreExactUserConfigurationOrReportPartialChange(): Unit = runBlocking {
        val effectiveOwned = AgentMcpServerConfiguration(
            "owned",
            AgentMcpTransport.Stdio("old-command"),
            isEnabled = false,
        ).toJson()
        val exactOwned = buildJsonObject { put("command", "old-command") }
        val configurations = linkedMapOf("owned" to effectiveOwned)
        val userConfigurations = linkedMapOf("owned" to exactOwned)
        val origins = mutableMapOf("owned" to "user")
        val writes = mutableListOf<Pair<JsonElement, String?>>()
        var version = 1
        var reload = 0
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "config/read" -> server.respond(
                    message.id,
                    configResponse(
                        configurations,
                        origins,
                        version,
                        userConfigurations,
                        baseUserConfigurations = mapOf(
                            "owned" to buildJsonObject { put("command", "base-command") },
                        ),
                    ),
                )
                "config/batchWrite" -> {
                    val edit = message.params.requiredArray("edits").single().jsonObject
                    val expectedVersion = message.params.optionalString("expectedVersion")
                    val value = edit.getValue("value")
                    writes += value to expectedVersion
                    if (expectedVersion != version.toString()) {
                        server.respondError(message.id, "configuration version changed")
                    } else {
                        val name = edit.requiredString("keyPath")
                            .removePrefix("mcp_servers.\"").removeSuffix("\"")
                        if (value == JsonNull) {
                            configurations.remove(name)
                            userConfigurations.remove(name)
                            origins.remove(name)
                        } else {
                            configurations[name] = value.jsonObject
                            userConfigurations[name] = value.jsonObject
                            origins[name] = "user"
                        }
                        version += 1
                        server.respond(message.id, buildJsonObject {
                            put("filePath", "/codex/config.toml")
                            put("status", "ok")
                            put("version", version.toString())
                        })
                    }
                }
                "config/mcpServer/reload" -> when (++reload) {
                    1 -> server.respondError(message.id, "reload failed")
                    3 -> {
                        version += 1 // An unrelated writer wins before rollback.
                        server.respondError(message.id, "reload failed after concurrent write")
                    }
                    else -> server.respond(message.id, buildJsonObject {})
                }
                "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                    putJsonArray("data") {
                        configurations.keys.forEach { name ->
                            add(buildJsonObject {
                                put("name", name)
                                put("authStatus", "unsupported")
                            })
                        }
                    }
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        try {
            val owned = client.listMcpServers("/workspace").single()
            val restored = assertFailsWith<AgentResourceInstallationException> {
                client.removeMcpServer(owned, "/workspace")
            }
            assertFalse(restored is AgentResourcePartialChangeException)
            assertEquals(exactOwned, userConfigurations.getValue("owned"))
            assertEquals(JsonNull to "1", writes[0])
            assertEquals(exactOwned to "2", writes[1])

            assertFailsWith<AgentResourcePartialChangeException> {
                client.addMcpServer(
                    AgentMcpServerConfiguration("new", AgentMcpTransport.Stdio("new-command")),
                    "/workspace",
                )
            }
            assertTrue("new" in userConfigurations)
            assertEquals("3", writes[2].second)
            assertEquals(JsonNull to "4", writes[3])
            assertEquals(4, reload)
        } finally {
            client.close()
        }
    }
}

private fun configResponse(
    configurations: Map<String, JsonObject>,
    origins: Map<String, String>,
    version: Int,
    userConfigurations: Map<String, JsonObject> = configurations.filterKeys { origins[it] == "user" },
    baseUserConfigurations: Map<String, JsonObject> = emptyMap(),
): JsonObject = buildJsonObject {
    putJsonObject("config") {
        putJsonObject("mcp_servers") {
            configurations.forEach { (name, configuration) -> put(name, configuration) }
        }
    }
    putJsonObject("origins") {
        origins.forEach { (name, source) ->
            putJsonObject("mcp_servers.$name.url") {
                putJsonObject("name") {
                    put("type", source)
                    when (source) {
                        "user" -> put("file", "/codex/config.toml")
                        "project" -> put("dotCodexFolder", "/workspace/.codex")
                    }
                }
                put("version", version.toString())
            }
        }
    }
    putJsonArray("layers") {
        add(buildJsonObject {
            putJsonObject("config") {
                putJsonObject("mcp_servers") {
                    userConfigurations.forEach { (name, configuration) -> put(name, configuration) }
                }
            }
            putJsonObject("name") {
                put("type", "user")
                put(
                    "file",
                    if (baseUserConfigurations.isEmpty()) "/codex/config.toml" else "/codex/profiles/active.toml",
                )
                if (baseUserConfigurations.isNotEmpty()) put("profile", "active")
            }
            put("version", version.toString())
        })
        if (baseUserConfigurations.isNotEmpty()) {
            add(buildJsonObject {
                putJsonObject("config") {
                    putJsonObject("mcp_servers") {
                        baseUserConfigurations.forEach { (name, configuration) -> put(name, configuration) }
                    }
                }
                putJsonObject("name") {
                    put("type", "user")
                    put("file", "/codex/config.toml")
                }
                put("version", "base-version")
            })
        }
    }
}

private fun FakeCodexRuntime.respondError(id: Long?, message: String) {
    sendRaw(buildJsonObject {
        put("id", requireNotNull(id))
        putJsonObject("error") {
            put("code", -32000)
            put("message", message)
        }
    }.toString())
}
