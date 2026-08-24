@file:JvmName("JavaCodexApiFixture")

package io.github.codex_agent_labs.codexmobile.agent

import java.util.concurrent.CountDownLatch
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.awaitCancellation
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

public fun selectableHost(): CodexHost = javaHost(CodexRuntimeFeature.entries.toSet())

public fun hostWithoutRuntimeFeatures(): CodexHost = javaHost(emptySet())

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
                    putJsonArray("turns") {}
                }
            })
            "turn/start" -> server.respond(message.id, buildJsonObject {
                putJsonObject("turn") { put("id", "turn-1") }
            })
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
