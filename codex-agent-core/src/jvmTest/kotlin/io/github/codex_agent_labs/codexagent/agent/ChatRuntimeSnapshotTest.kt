package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.agent.*
import io.github.codex_agent_labs.codexagent.agent.deriveConversationTitle
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeSnapshotTest {
    @Test
    @CoversApi(
        "api-v1:AgentCapability#enum-entry:WEB_SEARCH#sha256:5b624036bdca5939e44390745157d1cbfdb2a317a4d80c048e2653ec6007496e",
        "api-v1:AgentCapability#property:displayLabel#sha256:94f53aff26ce48952297c76eef571c0634cb12d9d1c5cfeb223635fde12eedb7",
        "api-v1:AgentCapability#property:promptLabel#sha256:803d92f6c4f5de7f17fc44d3a43d0c1afde50d9185ed4375513bb70180d8ddc2",
        "api-v1:AgentCollaborationMode#enum-entry:PLAN#sha256:c3ed0df001f578fa0f0c10c576f1acb2b4f7de23730901b89bde00dc6c2438ce",
        "api-v1:AgentTurnRequest#constructor:<init>#sha256:ffc4984122d037edb0e685a397cdf25782bebdad4c3538fe6a777ed384d5086e",
        "api-v1:AgentTurnRequest#property:capabilities#sha256:9b19e68cec46931d89a445a903417c447f990bc4681f969ba58cddb50bd6f91f",
        "api-v1:AgentTurnRequest#property:clientMessageId#sha256:2c95f570a18ca4f28cff20a5d3d4ffec111908c95e97f609c34f463ad5cb96a5",
        "api-v1:AgentTurnRequest#property:collaborationMode#sha256:816bc071954ac49e01a02000593e9e23227472b74350eaf522e1370f42eefde3",
        "api-v1:AgentTurnRequest#property:effort#sha256:f66a56a02b511da0ebbd11127d49b6f2cdc255f3ee7be3d099356e8ad79d9730",
        "api-v1:AgentTurnRequest#property:model#sha256:affbf80382e102d0830e4bf32eca083efab9e9b9c1e4cb1e57791c2f69ab2cf4",
        "api-v1:AgentTurnRequest#property:prompt#sha256:21efad966dca478904a48e7010f67e9545b20c8418f8b783fa85d9d8583719ed",
    )
    fun resumesSettingsAndSnapshotsAStructuredWebSearchTurn(): Unit = runBlocking {
        var resumeParams: JsonObject? = null
        var turnParams: JsonObject? = null
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> {
                    resumeParams = message.params
                    server.respond(
                        message.id,
                        buildJsonObject {
                            putJsonObject("thread") { put("id", "thread-1") }
                            put("model", "runtime-model")
                        },
                    )
                }

                "turn/start" -> {
                    turnParams = message.params
                    server.respond(
                        message.id,
                        buildJsonObject { putJsonObject("turn") { put("id", "turn-1") } },
                    )
                    server.notify(
                        "item/reasoning/summaryTextDelta",
                        buildJsonObject {
                            put("threadId", "thread-1")
                            put("turnId", "turn-1")
                            put("itemId", "reasoning-1")
                            put("summaryIndex", 0)
                            put("delta", "Inspecting")
                        },
                    )
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        try {
            val opened = async {
                withTimeout(1_000) { client.events.filterIsInstance<AgentEvent.ConversationOpened>().first() }
            }
            client.openConversation(ConversationId("thread-1"))
            assertEquals(
                AgentEvent.ConversationOpened(ConversationId("thread-1"), "runtime-model", null),
                opened.await(),
            )

            val resume = checkNotNull(resumeParams)
            assertEquals("thread-1", resume.requiredString("threadId"))
            val config = resume["config"]!!.jsonObject
            assertEquals("live", config.requiredString("web_search"))
            assertTrue(
                config["tools"]!!.jsonObject["experimental_request_user_input"]!!
                    .jsonObject.requiredBoolean("enabled"),
            )
            val features = config["features"]!!.jsonObject
            assertFalse("web_search_request" in features)
            assertFalse("web_search_cached" in features)
            assertFalse(features.requiredBoolean("standalone_web_search"))

            val reasoning = async {
                withTimeout(1_000) {
                    client.events.filterIsInstance<AgentEvent.ReasoningSummaryDelta>().first()
                }
            }
            client.sendTurn(
                ConversationId("thread-1"),
                AgentTurnRequest(
                    prompt = "Find the current answer",
                    clientMessageId = "client-message-1",
                    model = "runtime-model-next",
                    effort = "xhigh",
                    capabilities = setOf(AgentCapability.WEB_SEARCH),
                    collaborationMode = AgentCollaborationMode.PLAN,
                ),
                "/storage/emulated/0/Documents",
            )

            val turn = checkNotNull(turnParams)
            assertEquals("codex-agent:plan:client-message-1", turn.requiredString("clientUserMessageId"))
            assertEquals("runtime-model-next", turn.requiredString("model"))
            assertEquals("xhigh", turn.requiredString("effort"))
            assertEquals("/storage/emulated/0/Documents", turn.requiredString("cwd"))
            assertEquals("auto", turn.requiredString("summary"))
            val collaborationMode = turn["collaborationMode"]!!.jsonObject
            assertEquals("plan", collaborationMode.requiredString("mode"))
            val modeSettings = collaborationMode["settings"]!!.jsonObject
            assertEquals("runtime-model-next", modeSettings.requiredString("model"))
            assertEquals("medium", modeSettings.requiredString("reasoning_effort"))
            assertFalse("developer_instructions" in modeSettings)
            assertEquals("Inspecting", reasoning.await().text)
            val input = turn["input"]!!.jsonArray.single().jsonObject
            val expectedText = "${AgentCapability.WEB_SEARCH.promptLabel}\n\nFind the current answer"
            assertEquals(expectedText, input.requiredString("text"))
            val element = input["text_elements"]!!.jsonArray.single().jsonObject
            assertEquals(AgentCapability.WEB_SEARCH.displayLabel, element.requiredString("placeholder"))
            val range = element["byteRange"]!!.jsonObject
            assertEquals(0, range.requiredInt("start"))
            assertEquals(
                AgentCapability.WEB_SEARCH.promptLabel.toByteArray(StandardCharsets.UTF_8).size,
                range.requiredInt("end"),
            )
        } finally {
            client.close()
        }
    }

    @Test
    fun derivesOneBoundedTitleFromExplicitNameOrFirstUserLine() {
        assertEquals("Named", deriveConversationTitle("  Named  ", "ignored"))
        assertEquals("First line", deriveConversationTitle(null, "\n First line \nsecond"))
        assertEquals("New chat", deriveConversationTitle(null, " \n "))
        assertEquals("abcd", deriveConversationTitle(null, "abcdef", maxLength = 4))
    }
}
