package io.github.codex_agent_labs.codexmobile.agent

import io.github.codex_agent_labs.codexmobile.agent.*
import io.github.codex_agent_labs.codexmobile.agent.deriveConversationTitle
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeSnapshotTest {
    @Test
    @CoversApi(
        "api-v1:AgentCapability#enum-entry:WEB_SEARCH#sha256:1f69e8ac345dd20c59938bd931dd7f58d11c852928124e4b3dd9e2054601bc2b",
        "api-v1:AgentCapability#property:displayLabel#sha256:1eb83f5dd24fba44b3cdfd579ff86397ef3cc9a87550938088ca1c06a8f2fc88",
        "api-v1:AgentCapability#property:promptLabel#sha256:e76c2e3add354f198c0a845788bf35e95366f61868f87d8dcfb793b95cb8e085",
        "api-v1:AgentCollaborationMode#enum-entry:PLAN#sha256:ec0e7395b27d5e890c396ea4e39af43f49b093b933ee9062c83fc9c07a754e4d",
        "api-v1:AgentTurnRequest#constructor:<init>#sha256:f239ced2f216272eab0ac284ba496933a54fbd8738573b0de23b7fa6daed088b",
        "api-v1:AgentTurnRequest#property:capabilities#sha256:5758329ccf4ec39faa17d8344084f00352de2b1783a418d3bfd1935e7f0ae67a",
        "api-v1:AgentTurnRequest#property:clientMessageId#sha256:fac4e245a34b40652146ef90b221319d1323bc7628223ca7100e88a06b588bd7",
        "api-v1:AgentTurnRequest#property:collaborationMode#sha256:8ab5141b553277847ee99061fdf0bded5c1b4fee5815ffbca92827ff8c2c4151",
        "api-v1:AgentTurnRequest#property:effort#sha256:4139cb14507732ed0becd2c3e99c7e22202473d69191c77c51c51e0daa86f929",
        "api-v1:AgentTurnRequest#property:model#sha256:259579d0ac00ebdd63e6e84f6dfc5fd914a99ca82b446c36f756979e15cf8fa5",
        "api-v1:AgentTurnRequest#property:prompt#sha256:64fec772b8f5850b995a6fb5215dcfc2a3940606941c2ff8438a538b9942a4e7",
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
