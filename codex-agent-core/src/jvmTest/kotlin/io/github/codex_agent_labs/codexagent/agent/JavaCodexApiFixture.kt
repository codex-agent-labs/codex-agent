@file:JvmName("JavaCodexApiFixture")

package io.github.codex_agent_labs.codexagent.agent

import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import okio.FileSystem

public fun selectableHost(): CodexHost = javaHost(CodexRuntimeFeature.entries.toSet())

public fun hostWithoutRuntimeFeatures(): CodexHost = javaHost(emptySet())

public fun facadeFixture(): JavaFacadeFixture {
    val root = Files.createTempDirectory("codex-java-facade-")
    val skill = root.resolve("SKILL.md")
    Files.writeString(skill, "---\nname: review\ndescription: Review code\n---\n")
    lateinit var runtime: FakeCodexRuntime
    runtime = FakeCodexRuntime { message, server ->
        when (message.method) {
            "initialize" -> server.respond(message.id, buildJsonObject {})
            "account/read" -> server.respond(message.id, buildJsonObject {
                put("account", JsonNull)
                put("requiresOpenaiAuth", true)
            })
            "account/login/start" -> {
                val type = message.params.requiredString("type")
                server.respond(message.id, if (type == "apiKey") {
                    buildJsonObject { put("type", "apiKey") }
                } else {
                    buildJsonObject {
                        put("type", "chatgpt")
                        put("loginId", "java-login")
                        put("authUrl", "https://auth.openai.com/oauth?state=java-login")
                    }
                })
            }
            "account/login/cancel" -> {
                server.notify("account/login/completed", buildJsonObject {
                    put("loginId", "java-login")
                    put("success", false)
                    put("error", "cancelled")
                })
                server.respond(message.id, buildJsonObject { put("status", "canceled") })
            }
            "account/logout" -> server.respond(message.id, buildJsonObject {})
            "thread/resume" -> server.respond(message.id, buildJsonObject {
                putJsonObject("thread") { put("id", "thread-1") }
            })
            "thread/list" -> server.respond(message.id, page(
                listOf(
                    thread("thread-a", "First", "First", 2),
                    thread("thread-b", "Second", "Second", 1),
                ),
                null,
            ))
            "thread/read" -> {
                val id = message.params.requiredString("threadId")
                server.respond(message.id, buildJsonObject {
                    put("thread", thread(id, "Read $id", "Read $id", 3))
                })
            }
            "thread/name/set", "thread/delete" -> server.respond(message.id, buildJsonObject {})
            "model/list" -> server.respond(message.id, javaModelResponse())
            "skills/list" -> server.respond(message.id, buildJsonObject {
                putJsonArray("data") {
                    add(buildJsonObject {
                        put("cwd", "/workspace")
                        putJsonArray("errors") {}
                        putJsonArray("skills") {
                            add(buildJsonObject {
                                put("name", "review")
                                put("description", "Review code")
                                put("enabled", true)
                                put("path", skill.toString())
                                put("scope", "system")
                                putJsonObject("dependencies") {
                                    putJsonArray("tools") {
                                        add(buildJsonObject { put("type", "command"); put("value", "git") })
                                        add(buildJsonObject { put("type", "command"); put("value", "rg") })
                                    }
                                }
                            })
                        }
                    })
                }
            })
            "hooks/list" -> server.respond(message.id, javaHooksResponse())
            "config/batchWrite" -> server.respond(message.id, buildJsonObject {
                put("filePath", root.resolve("config.toml").toString())
                put("status", "ok")
                put("version", "2")
            })
            "plugin/list" -> server.respond(message.id, javaPluginList(installed = false))
            "plugin/installed" -> server.respond(message.id, javaPluginList(installed = true))
            "plugin/read" -> server.respond(message.id, javaPluginDetail())
            "plugin/install" -> server.respond(message.id, buildJsonObject {
                put("authPolicy", "ON_INSTALL")
                putJsonArray("appsNeedingAuth") { add(javaConnector(isAccessible = false)) }
            })
            "plugin/uninstall" -> server.respond(message.id, buildJsonObject {})
            "app/list" -> server.respond(message.id, buildJsonObject {
                putJsonArray("data") { add(javaConnector(isAccessible = false)) }
            })
            "mcpServerStatus/list" -> server.respond(message.id, buildJsonObject {
                putJsonArray("data") {
                    add(buildJsonObject {
                        put("name", "drive")
                        put("authStatus", "notLoggedIn")
                    })
                }
            })
            "config/read" -> server.respond(message.id, javaConfigurationResponse())
            null -> Unit
        }
    }
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    val client = CodexAgentClient(
        { runtime },
        requestTimeoutMillis = 1_000,
        fileSystem = FileSystem.SYSTEM,
    )
    val agent = CodexAgent(
        workspace = CodexWorkspace("/workspace"),
        workingDirectory = "/workspace",
        features = CodexRuntimeFeature.entries.toSet(),
        client = client,
        parentScope = scope,
        authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
    )
    return JavaFacadeFixture(agent, client, runtime, scope, root)
}

public fun cancellableHost(): JavaCancellationFixture {
    val entered = CountDownLatch(1)
    val cancelled = AtomicBoolean(false)
    val workspace = CodexWorkspace("/workspace")
    val platform = object : CodexPlatform {
        override val authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
        override val workspaceStore = object : CodexWorkspaceStore {
            override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution =
                CodexWorkspaceResolution.Available(workspace)

            override suspend fun restore(): CodexWorkspaceResolution = CodexWorkspaceResolution.Available(workspace)

            override suspend fun clear(): Unit = Unit
        }

        override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
            entered.countDown()
            try {
                awaitCancellation()
            } finally {
                cancelled.set(true)
            }
        }
    }
    return JavaCancellationFixture(
        CodexHost(platform, CodexClientInfo("java_test", "Java Test", "test")),
        entered,
        cancelled,
    )
}

public fun closeCancellationHost(): JavaCloseCancellationFixture {
    val prepareEntered = CountDownLatch(1)
    val releasePrepare = CountDownLatch(1)
    val workspace = CodexWorkspace("/workspace")
    val runtime = FakeCodexRuntime { message, server ->
        if (message.method == "initialize") server.respond(message.id, buildJsonObject {})
    }
    val platform = object : CodexPlatform {
        override val authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
        override val workspaceStore = object : CodexWorkspaceStore {
            override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution =
                CodexWorkspaceResolution.Available(workspace)

            override suspend fun restore(): CodexWorkspaceResolution = CodexWorkspaceResolution.Available(workspace)

            override suspend fun clear(): Unit = Unit
        }

        override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
            prepareEntered.countDown()
            releasePrepare.await()
            return PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = CodexRuntimeFeature.entries.toSet(),
            )
        }
    }
    return JavaCloseCancellationFixture(
        CodexHost(platform, CodexClientInfo("java_test", "Java Test", "test")),
        prepareEntered,
        releasePrepare,
    )
}

public data class JavaCancellationFixture(
    public val host: CodexHost,
    public val entered: CountDownLatch,
    public val cancelled: AtomicBoolean,
)

public data class JavaCloseCancellationFixture(
    public val host: CodexHost,
    public val prepareEntered: CountDownLatch,
    public val releasePrepare: CountDownLatch,
)

public class JavaFacadeFixture internal constructor(
    public val agent: CodexAgent,
    private val client: CodexAgentClient,
    private val runtime: FakeCodexRuntime,
    private val scope: CoroutineScope,
    private val root: java.nio.file.Path,
) : AutoCloseable {
    public val missingDirectory: String = root.resolve("missing").toString()
    public val noTierModel: AgentModel = AgentModel(
        id = "no-tier",
        displayName = "No tier",
        description = "No service tiers",
        supportedEfforts = listOf("medium"),
        defaultEffort = "medium",
        isDefault = false,
    )

    public fun start(): Unit = runBlocking {
        agent.start()
        client.openConversation(ConversationId("thread-1"))
    }

    public fun publishInteractions() {
        runBlocking { client.openConversation(ConversationId("thread-1")) }
        runtime.request(201, "item/commandExecution/requestApproval", javaApprovalRequest("First approval"))
        runtime.request(202, "item/commandExecution/requestApproval", javaApprovalRequest("Second approval"))
        runtime.request(203, "mcpServer/elicitation/request", javaUrlElicitation(203))
        runtime.request(204, "mcpServer/elicitation/request", javaUrlElicitation(204))
    }

    override fun close() {
        runBlocking { agent.close() }
        scope.cancel()
        root.toFile().deleteRecursively()
    }
}

private fun javaHost(features: Set<CodexRuntimeFeature>): CodexHost {
    val workspace = CodexWorkspace("/workspace")
    val runtime = FakeCodexRuntime { message, server ->
        when (message.method) {
            "initialize" -> server.respond(message.id, buildJsonObject {})
            "thread/start" -> server.respond(message.id, buildJsonObject {
                putJsonObject("thread") { put("id", "thread-1") }
            })
            "thread/read" -> server.respond(message.id, buildJsonObject {
                putJsonObject("thread") {
                    put("id", "thread-1")
                    putJsonArray("turns") {
                        add(buildJsonObject {
                            put("id", "turn-history")
                            putJsonArray("items") {
                                add(plainUserMessage("user-1", "client-1", "First message"))
                                add(buildJsonObject {
                                    put("id", "assistant-1")
                                    put("type", "agentMessage")
                                    put("phase", "final_answer")
                                    put("text", "Second message")
                                })
                            }
                        })
                    }
                }
            })
            "turn/start" -> {
                server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-1") }
                })
                server.notify("item/agentMessage/delta", buildJsonObject {
                    put("threadId", "thread-1")
                    put("turnId", "turn-1")
                    put("itemId", "item-1")
                    put("delta", "Working")
                })
            }
            "turn/interrupt" -> {
                server.respond(message.id, buildJsonObject {})
                server.notify("turn/completed", buildJsonObject {
                    put("threadId", "thread-1")
                    putJsonObject("turn") {
                        put("id", "turn-1")
                        put("status", "completed")
                    }
                })
            }
        }
    }
    val store = object : CodexWorkspaceStore {
        override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution =
            CodexWorkspaceResolution.Available(workspace)

        override suspend fun restore(): CodexWorkspaceResolution = CodexWorkspaceResolution.SelectionRequired(
            CodexWorkspaceSelectionReason.NOT_SELECTED,
            "Select a workspace",
        )

        override suspend fun clear(): Unit = Unit
    }
    val platform = object : CodexPlatform {
        override val authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
        override val workspaceStore: CodexWorkspaceStore = store

        override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime = PreparedCodexRuntime(
            runtimeFactory = { runtime },
            workspacePath = workspace.path,
            features = features,
        )
    }
    return CodexHost(platform, CodexClientInfo("java_test", "Java Test", "test"))
}

private fun javaModelResponse(): JsonObject {
    val preferred = buildJsonObject {
        model("preferred-catalog", "preferred", "Preferred", "medium", true).forEach(::put)
        putJsonArray("serviceTiers") {
            add(buildJsonObject {
                put("id", "free")
                put("name", "Free")
                put("description", "Standard")
            })
            add(buildJsonObject {
                put("id", "fast")
                put("name", "Fast")
                put("description", "Faster")
            })
        }
        put("defaultServiceTier", "free")
    }
    return page(
        listOf(
            preferred,
            model("other-catalog", "other", "Other", "low", false),
        ),
        null,
    )
}

private fun javaHooksResponse(): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("cwd", "/workspace")
            putJsonArray("warnings") {}
            putJsonArray("errors") {}
            putJsonArray("hooks") {
                add(buildJsonObject {
                    put("currentHash", "sha256:java")
                    put("displayOrder", 0)
                    put("enabled", true)
                    put("eventName", "preToolUse")
                    put("handlerType", "command")
                    put("isManaged", false)
                    put("key", "java-hook")
                    put("source", "project")
                    put("sourcePath", "/workspace/.codex/hooks.json")
                    put("timeoutSec", 10)
                    put("trustStatus", "untrusted")
                    put("command", "./check")
                })
            }
        })
    }
}

private fun javaPluginList(installed: Boolean): JsonObject = buildJsonObject {
    putJsonArray("marketplaceLoadErrors") {}
    putJsonArray("marketplaces") {
        add(buildJsonObject {
            put("name", "openai-curated")
            putJsonArray("plugins") { add(javaPluginSummary(installed)) }
        })
    }
}

private fun javaPluginSummary(installed: Boolean): JsonObject = buildJsonObject {
    put("id", "drive@openai-curated")
    put("remotePluginId", "plugin_java_drive")
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
        putJsonArray("capabilities") {
            add(JsonPrimitive("Search files"))
            add(JsonPrimitive("Read files"))
        }
        putJsonArray("screenshotUrls") {}
        putJsonArray("screenshots") {}
    }
}

private fun javaPluginDetail(): JsonObject = buildJsonObject {
    putJsonObject("plugin") {
        put("marketplaceName", "openai-curated")
        put("summary", javaPluginSummary(installed = true))
        putJsonArray("skills") {}
        putJsonArray("apps") { add(javaConnector(isAccessible = false)) }
        putJsonArray("appTemplates") {}
        putJsonArray("mcpServers") { add(JsonPrimitive("drive")) }
        putJsonArray("hooks") {}
    }
}

private fun javaConnector(isAccessible: Boolean): JsonObject = buildJsonObject {
    put("id", "drive")
    put("name", "Drive")
    put("description", "Files")
    put("installUrl", "https://accounts.example.com/oauth")
    put("isAccessible", isAccessible)
    put("isEnabled", true)
    putJsonArray("pluginDisplayNames") {
        add(JsonPrimitive("Drive"))
        add(JsonPrimitive("OpenAI curated"))
    }
}

private fun javaConfigurationResponse(): JsonObject = buildJsonObject {
    putJsonObject("config") {
        put("model", "preferred")
        put("model_reasoning_effort", "low")
        put("service_tier", "fast")
        putJsonObject("mcp_servers") {
            putJsonObject("drive") {
                put("url", "https://mcp.example.com")
                putJsonObject("http_headers") {
                    put("X-First", "one")
                    put("X-Second", "two")
                }
                putJsonArray("enabled_tools") {
                    add(JsonPrimitive("search"))
                    add(JsonPrimitive("read"))
                }
            }
        }
    }
    putJsonObject("origins") {}
}

private fun javaApprovalRequest(reason: String): JsonObject = buildJsonObject {
    put("itemId", "item-1")
    put("startedAtMs", 1)
    put("threadId", "thread-1")
    put("turnId", "turn-1")
    put("command", "git status")
    put("reason", reason)
}

private fun javaUrlElicitation(id: Int): JsonObject = buildJsonObject {
    put("serverName", "example")
    put("threadId", "thread-1")
    put("elicitationId", "elicitation-$id")
    put("message", "Sign in $id")
    put("url", "https://accounts.example.com/authorize")
    put("turnId", "turn-1")
    put("mode", "url")
}
