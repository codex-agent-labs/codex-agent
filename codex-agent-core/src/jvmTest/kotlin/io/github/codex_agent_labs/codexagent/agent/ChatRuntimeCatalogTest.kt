package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.agent.*
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeCatalogTest {
    @Test
    @CoversApi(
        "api-v1:AgentConversation#constructor:<init>#sha256:0bd0c7d721cb696207cf1442eb548e47c787c7362131952f95f8a28a0c8fcea4",
        "api-v1:AgentConversation#property:messages#sha256:792d1aa2e45cea202b51dc0dae82890ec6b1e9b53f84ab1b16ff654640e4fd60",
        "api-v1:AgentConversation#property:summary#sha256:887b73578491b20f31dabf8c8815b7b9342655507758e607112b702ac2d7cf37",
        "api-v1:AgentConversationSummary#property:title#sha256:049f60bdbda00787570a5f628a1b460c5231fcc77c9665ccd87f48f78182f65a",
        "api-v1:AgentMessage#constructor:<init>#sha256:466810d88e42d01b849923538401c9225d190d23a7b8dc32473a8189ce9ad1e3",
        "api-v1:AgentMessage#property:capabilities#sha256:3fcaaba3855781930e3751ef1ed5dabc0210a15486710ed3ff50769b9741de74",
        "api-v1:AgentMessage#property:clientMessageId#sha256:1429546c4e4745f3bbe63825f4a38a37acc13d99ae44222e31d68ae282429878",
        "api-v1:AgentMessage#property:id#sha256:b42ca538b713192e2daa6839f32b885977dc58848c8dbf3531f0fc8ad3d4f228",
        "api-v1:AgentMessage#property:reasoning#sha256:bdac0fe9f5cc930aa85747073f7cb515d3008f50695c64efe64ea1ad5ca4c4dd",
        "api-v1:AgentMessage#property:role#sha256:6c95395404c8ea59d5e8b6952d89668542f06586a96c36f46ed6bd11c538f893",
        "api-v1:AgentMessage#property:text#sha256:5fad6e91ee2b5f6a8edfdd7f796a34050241c323c9d2483bafe0bedad442bbc6",
        "api-v1:AgentMessageRole#enum-entry:ASSISTANT#sha256:ff544c6452a430ab94a22ce3212265c7fa76869978c9099f0f13925cc2b70215",
        "api-v1:AgentMessageRole#enum-entry:USER#sha256:89678bbeb0d454fb7e8329acfdec1129d7a3ffed09feedfe86baefe5f9926d2d",
        "api-v1:CodexConversations#function:list#sha256:cd355b6d92275871c0c1447a4c893aead42cedd4d33c4f773bdec78c38395d32",
        "api-v1:CodexConversations#function:read#sha256:cc5feddef7c27b9394a5a447fcb9762ad58a9f64b05c794a026dd375f8695a79",
        "api-v1:CodexModels#function:list#sha256:d8fa8c8e00fde50ed21a94f438f61b40aad54aae1dd10d5f065af12f76478959",
    )
    fun discoversPagedModelsAndConversationHistoryFromAppServerProtocol(): Unit = runBlocking {
        val modelCursors = mutableListOf<String?>()
        val threadCursors = mutableListOf<String?>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "model/list" -> {
                    val cursor = message.params.optionalString("cursor")
                    modelCursors += cursor
                    server.respond(
                        message.id,
                        page(
                            data = listOf(
                                if (cursor == null) model("catalog-a", "runtime-a", "Model A", "low", true)
                                else model("catalog-b", "runtime-b", "Model B", "xhigh", false),
                            ),
                            nextCursor = if (cursor == null) "models-2" else null,
                        ),
                    )
                }

                "thread/list" -> {
                    assertEquals("updated_at", message.params.requiredString("sortKey"))
                    assertEquals("desc", message.params.requiredString("sortDirection"))
                    val cursor = message.params.optionalString("cursor")
                    threadCursors += cursor
                    server.respond(
                        message.id,
                        page(
                            data = listOf(
                                if (cursor == null) thread("thread-a", "Pinned title", "ignored", 20)
                                else thread(
                                    "thread-b",
                                    null,
                                    "${AgentCapability.WEB_SEARCH.promptLabel}\n\nSecond title\nbody",
                                    10,
                                ),
                            ),
                            nextCursor = if (cursor == null) "threads-2" else null,
                        ),
                    )
                }

                "thread/read" -> {
                    assertEquals("thread-b", message.params.requiredString("threadId"))
                    assertTrue(message.params.requiredBoolean("includeTurns"))
                    server.respond(
                        message.id,
                        buildJsonObject {
                            put(
                                "thread",
                                thread(
                                    id = "thread-b",
                                    name = null,
                                    preview = "${AgentCapability.WEB_SEARCH.promptLabel}\n\nQuestion",
                                    updatedAt = 10,
                                    turns = buildJsonArray {
                                        add(
                                            buildJsonObject {
                                                put(
                                                    "items",
                                                    buildJsonArray {
                                                        add(taggedUserMessage("user-1", "client-1", "Question"))
                                                        add(
                                                            buildJsonObject {
                                                                put("id", "reasoning-1")
                                                                put("type", "reasoning")
                                                                put("summary", buildJsonArray {
                                                                    add(JsonPrimitive("Checked the sources"))
                                                                })
                                                            },
                                                        )
                                                        add(
                                                            buildJsonObject {
                                                                put("id", "search-1")
                                                                put("type", "webSearch")
                                                                put("query", "Question")
                                                            },
                                                        )
                                                        add(
                                                            buildJsonObject {
                                                                put("id", "commentary-1")
                                                                put("type", "agentMessage")
                                                                put("phase", "commentary")
                                                                put("text", "Checking the result")
                                                            },
                                                        )
                                                        add(
                                                            buildJsonObject {
                                                                put("id", "codex-1")
                                                                put("type", "agentMessage")
                                                                put("phase", "final_answer")
                                                                put("text", "Answer")
                                                            },
                                                        )
                                                    },
                                                )
                                            },
                                        )
                                    },
                                ),
                            )
                        },
                    )
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = CodexAgent(
            workspace = CodexWorkspace("/workspace"),
            workingDirectory = "/workspace",
            features = CodexRuntimeFeature.entries.toSet(),
            client = client,
            parentScope = this,
            authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        try {
            agent.start()
            val models = agent.models.list()
            assertEquals(listOf(null, "models-2"), modelCursors)
            assertEquals(listOf("runtime-a", "runtime-b"), models.map { it.id })
            assertEquals(listOf("low", "medium"), models.first().supportedEfforts)
            assertEquals("low", models.first().defaultEffort)
            assertTrue(models.first().isDefault)

            val summaries = agent.conversations.list()
            assertEquals(listOf(null, "threads-2"), threadCursors)
            assertEquals(listOf("Pinned title", "Second title"), summaries.map { it.title })

            val conversation = agent.conversations.read(ConversationId("thread-b"))
            assertEquals("Question", conversation.summary.title)
            assertEquals(2, conversation.messages.size)
            val user = conversation.messages[0]
            assertEquals("user-1", user.id)
            assertEquals("client-1", user.clientMessageId)
            assertEquals(AgentMessageRole.USER, user.role)
            assertEquals("Question", user.text)
            assertEquals(setOf(AgentCapability.WEB_SEARCH), user.capabilities)
            assertEquals(AgentMessageRole.ASSISTANT, conversation.messages[1].role)
            assertEquals("Answer", conversation.messages[1].text)
            assertEquals("Checked the sources\n\nChecking the result", conversation.messages[1].reasoning)
        } finally {
            agent.close()
        }
    }

}
