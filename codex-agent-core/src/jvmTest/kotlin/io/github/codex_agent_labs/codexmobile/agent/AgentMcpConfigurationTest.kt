package io.github.codex_agent_labs.codexmobile.agent

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
        "api-v1:AgentMcpAuthentication#enum-entry:CHAT_GPT#sha256:7c29d87446cfcc25e694ac555c8f9349e62a72f6884568233776e2dea708fd90",
        "api-v1:AgentMcpAuthentication#enum-entry:OAUTH#sha256:5ffd448a6bef75d0773c93e7250b6308f43ce35262fd15fa6fc243406f4a971a",
        "api-v1:AgentMcpEnvironmentSource#enum-entry:REMOTE#sha256:6f5abdbe115733f4b06fa9e6652b6e6ed03d721494d32a2cee5b175c41b686e7",
        "api-v1:AgentMcpEnvironmentVariable#constructor:<init>#sha256:ea74c05c30ff971d6bb50db0c983226e6a654fc633b2e3c05fa81f9674b944fe",
        "api-v1:AgentMcpEnvironmentVariable#property:name#sha256:003523da58dea2f1596dddfc9159e7f1dc2014fa870c04e469e871fd95a06764",
        "api-v1:AgentMcpEnvironmentVariable#property:source#sha256:09e7df0ab056f5c4104e1bb1362f72748a8d818a5c2d39de23621c223340ed15",
        "api-v1:AgentMcpOauthConfiguration#constructor:<init>#sha256:715a75cd09cd83bb0d48a13df89067a5d5aca7e251d61d60d775ab20abefac0b",
        "api-v1:AgentMcpOauthConfiguration#property:callbackPort#sha256:96843847ccb2184a8ab7c776098c1eef617d4381e940b41f62cbfdd3e4b9bb60",
        "api-v1:AgentMcpOauthConfiguration#property:clientId#sha256:b9277346f58cc0c0b2df0d8d37fc54143e6dc4f5ba7b77e3e2dfae55b589d67c",
        "api-v1:AgentMcpServerConfiguration#constructor:<init>#sha256:4b864ebb4893ef4f62208bb11164ca3ddefedd140608b6dfa432b4a06fa9e887",
        "api-v1:AgentMcpServerConfiguration#property:authentication#sha256:b8682413c1d1207d2d03b4c9eb58968fcf1b5a28647d96777d67ac8538cf37df",
        "api-v1:AgentMcpServerConfiguration#property:defaultToolApproval#sha256:128a963ba75013de7281aee0d25d7d70cc82010c58bbc1350e19851eeb6cdd80",
        "api-v1:AgentMcpServerConfiguration#property:disabledTools#sha256:63c57851cf6edb6d44ff9867b686f6935100c9b5ab4ed662968f653259c49506",
        "api-v1:AgentMcpServerConfiguration#property:enabledTools#sha256:509184dea46858a7b68cc3ec47ebf3ab9a055c83992ca8c19d62da943c1955d6",
        "api-v1:AgentMcpServerConfiguration#property:environmentId#sha256:16f0780aac56f94386444b517ed76470a54465499992bd11146514293853908c",
        "api-v1:AgentMcpServerConfiguration#property:isEnabled#sha256:cc1b16d5daf8712530ee1973c3fad143eb0b105b1dab1954d7d39ffe1b7552ed",
        "api-v1:AgentMcpServerConfiguration#property:isRequired#sha256:47a893b96e3987a4fd67bb7706992f2e5a31fba890e48f87b0382de5b9ec9035",
        "api-v1:AgentMcpServerConfiguration#property:name#sha256:49d9384bd7f721d5cbc6f5c1f03e52f37dcb770590e19a849c7064ad72af95be",
        "api-v1:AgentMcpServerConfiguration#property:oauthResource#sha256:3d1f298bb5bac5f264af0dbc12a4deb3cda3c409b9af39763bb9bc61877f14c2",
        "api-v1:AgentMcpServerConfiguration#property:oauth#sha256:f825ef95964b770e3c547a1817bc413a1e48a876a76f7a7c396537b640728b77",
        "api-v1:AgentMcpServerConfiguration#property:omitToolsFrom#sha256:02446000a0cde67dc5ec62e2a41622fddc7b415dbef8766336dc620d598d6133",
        "api-v1:AgentMcpServerConfiguration#property:scopes#sha256:0119d0f8e8b9c78a9ba670414a31433f2895545a20fbe9a39024b12ae9776c9b",
        "api-v1:AgentMcpServerConfiguration#property:startupTimeoutSeconds#sha256:0a850713cd56b8009fee37ac1eab8488dc10e2ba334acde31899fe71cf817118",
        "api-v1:AgentMcpServerConfiguration#property:supportsParallelToolCalls#sha256:3e75f95ab4a7fd3cfff3133a47b93c49e97ad3da4ef5513ab087bcda5e0795f6",
        "api-v1:AgentMcpServerConfiguration#property:toolTimeoutSeconds#sha256:8ee9c359fd8d1b159d3d210a46a659c45b9cd9ac59f42e0c09993654ee5115fd",
        "api-v1:AgentMcpServerConfiguration#property:tools#sha256:24c0d1ec0dff6d92a0c830b9f6674bc9a55a6000843f11a9e434cec600252559",
        "api-v1:AgentMcpServerConfiguration#property:transport#sha256:6168f7549db54360fc4f2436e04efb8715c015b62bc11ab73e67b8c99e08b9a8",
        "api-v1:AgentMcpToolApproval#enum-entry:PROMPT#sha256:9a9f57c969983e49dbe83184d434e95784b20fa658a255f0e5d73d5f1b13b773",
        "api-v1:AgentMcpToolApproval#enum-entry:WRITES#sha256:c993d37fa559178612e16396f57a30f879a5a8aaf3f5d5d30c4d428bd57ae9c3",
        "api-v1:AgentMcpToolConfiguration#constructor:<init>#sha256:125558327201be74c63f39b2c1ad57491d2dfed66598ae9603c13d411fda6dd2",
        "api-v1:AgentMcpToolConfiguration#property:approval#sha256:179f9b1e8479dae94304e7099ac59a532fff01a62d867730a19ad9359453a2e1",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:CODE_MODE#sha256:60654a57ebc2cce80f9ba4dbd0342a993c4562cea56d09b3f77abc99af4eaf5a",
        "api-v1:AgentMcpToolExposureSurface#enum-entry:DEFERRED#sha256:7a2936b6f895da33b3f34e8a9c7117fba6555c08d1959634c03384c83eace6db",
        "api-v1:AgentMcpTransport.Http#constructor:<init>#sha256:ecb975d784d743096723db3351a2b9928ee9ab0be3731df1b31ef864d0aaf5cd",
        "api-v1:AgentMcpTransport.Http#property:bearerTokenEnvironmentVariable#sha256:c0c9fd204d621f2e5d88589bf3062632761ee4538a977b20d21a80bc739d7cac",
        "api-v1:AgentMcpTransport.Http#property:environmentHeaders#sha256:b7818e73fc0022126aaf797a58406fb55fbb9a049b9e9b6c9f3867e1aff50a9b",
        "api-v1:AgentMcpTransport.Http#property:headersHelper#sha256:3b5fe3aaa9301586e233995737669a20adeea553b0b9e8199fae811efe17d36d",
        "api-v1:AgentMcpTransport.Http#property:headers#sha256:b94366bcaf233efd4567705443fb8082747f6462f1e5e3cb02ac510da0d0c53e",
        "api-v1:AgentMcpTransport.Http#property:url#sha256:7d8e4370787e318016ba13a082330909ce4fc0b5d4bbc0c716d28d4efef58395",
        "api-v1:AgentMcpTransport.Stdio#constructor:<init>#sha256:0b9250abde38881acd18041df79ec627352f1b759b8bda225eae5deae1a4d25a",
        "api-v1:AgentMcpTransport.Stdio#property:arguments#sha256:0810e92eb5a55b64a8b94a5a24b3088fa9004e8da69f75adfa9f561d926a56c9",
        "api-v1:AgentMcpTransport.Stdio#property:command#sha256:fbde7940f09b6d946e4093a29f4c9ab8891ac30ef69d514766f3569a26ec1451",
        "api-v1:AgentMcpTransport.Stdio#property:environment#sha256:4aced20260dea06c3592312eca71c2bd963946048b77704922bb83df68a26d3a",
        "api-v1:AgentMcpTransport.Stdio#property:forwardedEnvironment#sha256:40a34f03fe00ce49a04850af59c0f7b75312941bf096b95c57175b5f4e421ef5",
        "api-v1:AgentMcpTransport.Stdio#property:workingDirectory#sha256:ccf2c3340a6cba8015f7ecc562a2a5b2a6cf490d997aa5392e5d3deaacd9744e",
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
        "api-v1:AgentMcpServer#property:canRemove#sha256:3790fa4bf425e1b3420cb30ad1bc7f9ac855f0993acbcc044f0d111bd2349c48",
        "api-v1:AgentMcpServer#property:configuration#sha256:fd4d7437ddaf39ea039879c8a317e7df840f18cdae6f35f5ddfbd764cbf584c7",
        "api-v1:AgentMcpServer#property:name#sha256:8a11daa4a66dd2a54c1c798d095649d7db0eb724c49601ca2e3aeb8f9a40aae7",
        "api-v1:AgentMcpServer#property:origin#sha256:ac33f5e8a13ffc08ae14854311995e06cf94943914bf7f74ecff463ce50a7749",
        "api-v1:AgentResourceOrigin#enum-entry:WORKSPACE#sha256:f92ee726d345e108fa396a706de0087a17b3f04718f051ca25be1e463d5c8d3b",
        "api-v1:CodexMcpServers#function:add#sha256:816e235211895ebffb0107daa644ac908e2a52674fd65ef7415384a343647b07",
        "api-v1:CodexMcpServers#function:list#sha256:99c94452c1184fa58b3200809790612692bc7b729e8a54e3da251cb0f44062f5",
        "api-v1:CodexMcpServers#function:remove#sha256:9e62c524a65d17e2707420d37a923c449512460db7ec0466817139777e771da5",
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
