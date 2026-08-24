package io.github.codex_agent_labs.codexmobile.agent

import io.github.codex_agent_labs.codexmobile.agent.*
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeCatalogTest {
    @Test
    @CoversApi(
        "api-v1:AgentConversation#constructor:<init>#sha256:dce0cb1df0721886483f36b10188c68dc30da59dc5897b8cc56c9881481cd02a",
        "api-v1:AgentConversation#property:messages#sha256:ec4ab7f1cd6c5e9e51aad72cf396c2b4ed3495e931dfffce16e4661fab51b5ba",
        "api-v1:AgentConversation#property:summary#sha256:7d04545672468f7cb72dbc349907411a5c81da6102b8e605eb642cb8b27613c8",
        "api-v1:AgentConversationSummary#property:title#sha256:3f82e73246faab76bd205c12a8d86f32dab7c6219f2c47a7239f251dbe008a6b",
        "api-v1:AgentMessage#constructor:<init>#sha256:225e872372d6ae6e633c6c09767872c83fad723c7f0dc8f5029920f7e8e642af",
        "api-v1:AgentMessage#property:capabilities#sha256:f6a12c09f95d67d014e675f1397c3434a27128009b02d98f98bc0d673a05b1be",
        "api-v1:AgentMessage#property:clientMessageId#sha256:c7a070ade6fae6dfba4fd536295d027f4ba04e5de7880f79c4b65b99557b1dc1",
        "api-v1:AgentMessage#property:id#sha256:afb157b852b5c70e15d8694413406ace35ee0474c8a41fbec6b58a0d78ab2782",
        "api-v1:AgentMessage#property:reasoning#sha256:6780b5717fe23c5256f76ce78de9022a3fba90c89890ab5ad931932ea71c5bf5",
        "api-v1:AgentMessage#property:role#sha256:96aeea245fefc14aad24d4adc95c38ceab95ba6354a646c2ea42e3ab2aa4a60f",
        "api-v1:AgentMessage#property:text#sha256:8a1c07531b508badf5035d96c6feb250629a24e2c72989978360920f5c8107e9",
        "api-v1:AgentMessageRole#enum-entry:ASSISTANT#sha256:f369c4f0e47685b440320333006c0c058783ee2a55f2b9c554839a8d9a0df128",
        "api-v1:AgentMessageRole#enum-entry:USER#sha256:5572c10ccfb5180d31c30ba322e62f73ce28013434d77ee9e6fe416e076fe895",
        "api-v1:CodexConversations#function:list#sha256:b0b75955bb49081d2882e4fc537e10ea81992ec455b501d92f924cdb31d40426",
        "api-v1:CodexConversations#function:read#sha256:f52aa196ce38b2b247245fdee6cc7baea79e63e5d42fc06b2bee91b000e86a65",
        "api-v1:CodexModels#function:list#sha256:98a0156446a4f7d8f7cac4e4e9ff4cd095bf73cdb0ee99ddb20ee7f69f2f722f",
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
