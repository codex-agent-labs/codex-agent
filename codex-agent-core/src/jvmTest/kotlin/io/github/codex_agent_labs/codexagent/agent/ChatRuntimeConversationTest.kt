package io.github.codex_agent_labs.codexagent.agent

import okio.FileSystem
import okio.Path.Companion.toPath
import io.github.codex_agent_labs.codexagent.agent.*
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeConversationTest {
    @Test
    @CoversApi(
        "api-v1:CodexConversations#function:delete#sha256:3af3631ad3f078ddbf5a7c39df8ef167e8914b38c7f0a2633fbd1a5674389c12",
        "api-v1:CodexConversations#function:rename#sha256:475295b9b72372dc547fae8305ea357f7a717893e8b20e939bcb411609a9dc0f",
        "api-v1:ConversationId#constructor:<init>#sha256:573c9f03f57af8d9112e9a13b5dd3164a81b475100890f5e7c2b2c69f1c8a3bc",
        "api-v1:ConversationId#property:value#sha256:0517eb1ae6bf106cf1c3d2387f07ec2c0b4e7e63be2b493ed1b5218d01a06762",
    )
    fun renamesAndDeletesConversationsThroughStableThreadMethods(): Unit = runBlocking {
        var renameParams: JsonObject? = null
        var deleteParams: JsonObject? = null
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/name/set" -> {
                    renameParams = message.params
                    server.respond(message.id, buildJsonObject {})
                }

                "thread/delete" -> {
                    deleteParams = message.params
                    server.respond(message.id, buildJsonObject {})
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = conversationAgent(client, this, "/workspace")
        try {
            agent.start()
            val conversationId = ConversationId("thread-history")
            agent.conversations.rename(conversationId, "  Useful name  ")
            agent.conversations.delete(conversationId)

            assertEquals("thread-history", checkNotNull(renameParams).requiredString("threadId"))
            assertEquals("Useful name", checkNotNull(renameParams).requiredString("name"))
            assertEquals("thread-history", checkNotNull(deleteParams).requiredString("threadId"))
        } finally {
            agent.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentConversationState#property:effort#sha256:d6b7ff63849619bd7e804a661dc484d66b62ca8a29784fe4c07b4283634ccf3c",
        "api-v1:AgentConversationState#property:serviceTier#sha256:41afa72749b7b4cdefbe5aab387fdea406809da83414ffa4785345cc3bbb383e",
        "api-v1:AgentMessage#property:exitCode#sha256:204e80e84e3172390259bfbf5b152a28f79964aeccb5abf52c2dadfb39b11e40",
        "api-v1:AgentMessage#property:shellCommand#sha256:300fec4e5c7d56b70433ffa0bdecb8ca01b100922f6deb16c99758411e7becea",
        "api-v1:CodexConversation#function:runShellCommand#sha256:0a565993c6dd159232001e575726277da2541ddc343e265f80b5ace047755ed4",
        "api-v1:CodexConversations#function:open#sha256:c41f6e2953cf5f81aa26c029d6c037c77437cc7b3afaf8e0680a3c81af5e7d21",
    )
    fun runsALeadingBangThroughTheNativeUserShellStream(): Unit = runBlocking {
        val transcriptDirectory = Files.createTempDirectory("shell-transcript-test").toFile()
        var startParams: JsonObject? = null
        var shellParams: JsonObject? = null
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> {
                    startParams = message.params
                    server.respond(
                        message.id,
                        buildJsonObject { putJsonObject("thread") { put("id", "thread-shell") } },
                    )
                }

                "thread/shellCommand" -> {
                    shellParams = message.params
                    server.respond(message.id, buildJsonObject {})
                    server.notify(
                        "item/started",
                        buildJsonObject {
                            put("threadId", "thread-shell")
                            put("turnId", "turn-shell")
                            putJsonObject("item") {
                                put("command", "printf 'one\\ntwo\\n'")
                                put("commandActions", buildJsonArray {})
                                put("cwd", "/storage/emulated/0/Documents")
                                put("id", "command-shell")
                                put("type", "commandExecution")
                                put("source", "userShell")
                                put("status", "inProgress")
                            }
                        },
                    )
                    server.notify(
                        "item/commandExecution/outputDelta",
                        buildJsonObject {
                            put("threadId", "thread-shell")
                            put("turnId", "turn-shell")
                            put("itemId", "command-shell")
                            put("delta", "one\ntwo\n")
                        },
                    )
                    server.notify(
                        "item/completed",
                        buildJsonObject {
                            put("threadId", "thread-shell")
                            put("turnId", "turn-shell")
                            putJsonObject("item") {
                                put("command", "printf 'one\\ntwo\\n'")
                                put("commandActions", buildJsonArray {})
                                put("cwd", "/storage/emulated/0/Documents")
                                put("id", "command-shell")
                                put("type", "commandExecution")
                                put("source", "userShell")
                                put("status", "completed")
                                put("aggregatedOutput", "one\ntwo\n")
                                put("exitCode", 0)
                            }
                        },
                    )
                    server.notify(
                        "turn/completed",
                        buildJsonObject {
                            put("threadId", "thread-shell")
                            putJsonObject("turn") {
                                put("id", "turn-shell")
                                put("status", "completed")
                            }
                        },
                    )
                }

                "thread/list" -> server.respond(
                    message.id,
                    page(listOf(thread("thread-shell", null, "", 30)), null),
                )

                "thread/read" -> server.respond(
                    message.id,
                    buildJsonObject {
                        put("thread", thread(
                            id = "thread-shell",
                            name = null,
                            preview = "",
                            updatedAt = 30,
                            turns = buildJsonArray {
                                add(buildJsonObject {
                                    put("id", "turn-shell")
                                    put("items", buildJsonArray {})
                                    put("status", "completed")
                                })
                            },
                        ))
                    },
                )
            }
        }
        val client = CodexAgentClient(
            { process },
            requestTimeoutMillis = 1_000,
            shellTranscriptDirectory = transcriptDirectory.absolutePath.toPath(),
            fileSystem = FileSystem.SYSTEM,
        )
        val agent = conversationAgent(client, this, "/storage/emulated/0/Documents")
        try {
            agent.start()
            val conversation = agent.conversations.open()
            val session = checkNotNull(conversation.state.value.conversationId)
            conversation.process(
                AgentEvent.ConversationOpened(
                    session,
                    model = "runtime-model",
                    effort = "xhigh",
                    serviceTier = "fast",
                ),
            )
            assertEquals("runtime-model", conversation.state.value.model)
            assertEquals("xhigh", conversation.state.value.effort)
            assertEquals("fast", conversation.state.value.serviceTier)
            val events = async {
                withTimeout(1_000) {
                    client.events.filter {
                        it is AgentEvent.ShellOutputDelta ||
                            it is AgentEvent.ShellCommandCompleted ||
                            it is AgentEvent.TurnCompleted
                    }.take(3).toList()
                }
            }

            conversation.runShellCommand("printf 'one\\ntwo\\n'")

            assertEquals("/storage/emulated/0/Documents", checkNotNull(startParams).requiredString("cwd"))
            assertEquals("thread-shell", checkNotNull(shellParams).requiredString("threadId"))
            assertEquals("printf 'one\\ntwo\\n'", checkNotNull(shellParams).requiredString("command"))
            val received = events.await()
            assertEquals("one\ntwo\n", assertIs<AgentEvent.ShellOutputDelta>(received[0]).text)
            assertEquals(0, assertIs<AgentEvent.ShellCommandCompleted>(received[1]).exitCode)
            assertIs<AgentEvent.TurnCompleted>(received[2])

            assertEquals("!printf 'one\\ntwo\\n'", agent.conversations.list().single().title)
            val history = agent.conversations.read(session)
            assertEquals(listOf(AgentMessageRole.USER, AgentMessageRole.ASSISTANT), history.messages.map { it.role })
            assertEquals("!printf 'one\\ntwo\\n'", history.messages[0].text)
            assertEquals("printf 'one\\ntwo\\n'", history.messages[1].shellCommand)
            assertEquals("one\ntwo\n", history.messages[1].text)
            assertEquals(0, history.messages[1].exitCode)
        } finally {
            agent.close()
            transcriptDirectory.deleteRecursively()
        }
    }

}

private fun conversationAgent(
    client: CodexAgentClient,
    scope: CoroutineScope,
    workingDirectory: String,
): CodexAgent = CodexAgent(
    workspace = CodexWorkspace(workingDirectory),
    workingDirectory = workingDirectory,
    features = CodexRuntimeFeature.entries.toSet(),
    client = client,
    parentScope = scope,
    authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
)
