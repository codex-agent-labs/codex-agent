package io.github.codex_agent_labs.codexmobile.agent

import okio.FileSystem
import okio.Path.Companion.toPath
import io.github.codex_agent_labs.codexmobile.agent.*
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import kotlin.test.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.serialization.json.*

class ChatRuntimeConversationTest {
    @Test
    @CoversApi(
        "api-v1:CodexConversations#function:delete#sha256:9abbc524804d1a2ac7db4d6cfa15a8a7bccc700d52e1a98f3a6dc719a6f9d1ce",
        "api-v1:CodexConversations#function:rename#sha256:263dcc880a285f9e7eeb87568c21ea2434039ff4d4c27412c7ae07857524a430",
        "api-v1:ConversationId#constructor:<init>#sha256:9d99d061ecf0a53892277568e9139bd83e1f5cc70b1a9725943f892e99723bd3",
        "api-v1:ConversationId#property:value#sha256:d0c5dcf6402ad6595ff8b063d896bbb1d2c818322353860f18edfb17c84e1dfa",
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
        "api-v1:AgentConversationState#property:effort#sha256:5fb05c7a99e115040c5e78a5a8d0fd07881f90c40de2b6a6c742c7e4c97dd339",
        "api-v1:AgentConversationState#property:serviceTier#sha256:354d7581863e58160a2d2326c860f8b24ac0a756f4e9af4cfa9ee1280303e2ff",
        "api-v1:AgentMessage#property:exitCode#sha256:3fe9c0366cafaf7c8f4421cdce352d39a4819129a0fc3ae12a200ee29986b244",
        "api-v1:AgentMessage#property:shellCommand#sha256:068278fc175125cca7b504871949bbd47c67520bb9199d7921d9e2d75219e036",
        "api-v1:CodexConversation#function:runShellCommand#sha256:6aea2a29171d1a0a2bf6d2c3b75922974e46d40f71208ef1fae0853e069c72b7",
        "api-v1:CodexConversations#function:open#sha256:2cbc20c9a6736f949b22bbf561b339e133aab3af537c3089b752fa82442f3d0c",
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
