package io.github.codex_agent_labs.codexagent.agent

import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

class AuthenticationControllerTest {
    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationState#property:pendingSignInUrl#sha256:bf30019f451375b387668190350d0a0ebd092218fa1ae1d758b6415f0b8c6fc5",
        "api-v1:AgentAuthenticationState#property:status#sha256:13b30bd56de316553934b5bee5b015b4f913bc283aea9085fb4ee2edcaf17a71",
        "api-v1:AgentAuthenticationStatus#enum-entry:AUTHENTICATED#sha256:00efae599e736d1f8fbe900f029ca88fb327c811365a56455674cd170db337b0",
    )
    fun throwingPresentationCleanupDoesNotStopLaterAuthenticationEvents() = runBlocking {
        val runtime = FakeCodexRuntime { _, _ -> Unit }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        var opened = 0
        val session = AuthenticationController(
            client,
            this,
            CodexAuthorizationBrowser {
                opened += 1
                if (opened == 1) {
                    CodexAuthorizationPresentation { error("close failed") }
                } else {
                    CodexAuthorizationPresentation.None
                }
            },
        )
        try {
            client.eventsChannel.send(AgentEvent.AuthenticationRequired("https://auth.openai.com/first"))
            withTimeout(1_000) { session.state.first { it.pendingSignInUrl?.value?.endsWith("/first") == true } }
            client.eventsChannel.send(AgentEvent.Authenticated)
            withTimeout(1_000) { session.state.first { it.status == AgentAuthenticationStatus.AUTHENTICATED } }

            client.eventsChannel.send(AgentEvent.AuthenticationRequired("https://auth.openai.com/second"))
            withTimeout(1_000) { session.state.first { it.pendingSignInUrl?.value?.endsWith("/second") == true } }
            assertEquals(2, opened)
        } finally {
            session.close()
            client.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationState#property:failure#sha256:42202205b890d0f1e19530fc17459aec45e9d5c6db12fd09204931225844cc45",
    )
    fun authenticationFailureDoesNotFailConversationOrClearInteractions(): Unit = runBlocking {
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val authentication = AuthenticationController(client, this)
        val interactions = InteractionController(client, this)
        val conversation = CodexConversation(
            client,
            this,
            "/workspace",
            CodexRuntimeFeature.entries.toSet(),
            CodexConversation::closeOwned,
        )
        try {
            val conversationId = conversation.open()
            client.eventsChannel.send(
                AgentEvent.ApprovalRequested(
                    conversationId,
                    "approval-1",
                    "Review",
                    "Details",
                ),
            )
            withTimeout(1_000) { interactions.state.first { it.pending.size == 1 } }

            client.applyLoginCompletion(LoginCompletion("login-1", false, "Access denied"))
            withTimeout(1_000) { authentication.state.first { it.failure?.message == "Access denied" } }

            assertFalse(authentication.isAuthenticated.value)
            assertFalse(authentication.isAuthenticating.value)
            assertEquals(AgentConversationStatus.READY, conversation.state.value.status)
            assertEquals(1, interactions.state.value.pending.size)
        } finally {
            conversation.close()
            interactions.close()
            authentication.close()
            client.close()
        }
    }

    @Test
    fun authenticatingAgainWhileAuthenticatedKeepsTheStableState(): Unit = runBlocking {
        val accountReads = AtomicInteger()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/read" -> {
                    accountReads.incrementAndGet()
                    server.respond(
                        message.id,
                        buildJsonObject {
                            putJsonObject("account") { put("type", "chatgpt") }
                            put("requiresOpenaiAuth", true)
                        },
                    )
                }
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val controller = AuthenticationController(client, this)
        try {
            controller.authenticate()
            withTimeout(1_000) {
                controller.state.first { it.status == AgentAuthenticationStatus.AUTHENTICATED }
            }

            controller.authenticate()

            assertEquals(AgentAuthenticationStatus.AUTHENTICATED, controller.state.value.status)
            assertEquals(1, accountReads.get())
        } finally {
            controller.close()
            client.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationState#constructor:<init>#sha256:33df9f4ed08dabf6c26c2002e817d25749cf28fcf033b1e810eb3e6ab8721571",
        "api-v1:AgentAuthenticationStatus#enum-entry:AUTHENTICATING#sha256:3beea75af547ef1d78b2fc511901e4c8e8af425d3e2762dfdb617a4a7d99cc7d",
        "api-v1:CodexAuthentication#function:authenticate#sha256:d242858340cc25c73a15142be09c6f9498a9b01a12fb1e0c2f04c04af73600e6",
        "api-v1:CodexAuthentication#property:isAuthenticated#sha256:1c5f83c236a26c398b592f07104a3b6bc93e112dcd8325a6f5959940927fe58c",
        "api-v1:CodexAuthentication#property:isAuthenticating#sha256:3fc5f1ed32bebb487e1c841a69028716c799a1069fa6ac4d151676c0ad6a154c",
        "api-v1:CodexAuthentication#property:state#sha256:32af33b0043262af9de1bd0e8964ca0c130a81160537e702bbfcbf17e950ec10",
    )
    fun browserAuthenticationOpensAndClosesTheValidatedPresentation() = runBlocking {
        lateinit var runtime: FakeCodexRuntime
        var opened: CodexAuthorizationUrl? = null
        var presentationClosed = false
        runtime = authenticationRuntime { loginId ->
            buildJsonObject {
                put("type", "chatgpt")
                put("loginId", loginId)
                put("authUrl", "https://auth.openai.com/oauth?state=$loginId")
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val agent = authenticationAgent(
            client,
            this,
            CodexAuthorizationBrowser { url ->
                opened = url
                CodexAuthorizationPresentation { presentationClosed = true }
            },
        )
        try {
            agent.start()
            val session = agent.authentication
            assertFalse(session.isAuthenticated.value)
            assertFalse(session.isAuthenticating.value)
            session.authenticate()
            withTimeout(1_000) { session.state.first { it.pendingSignInUrl != null } }
            assertFalse(session.isAuthenticated.value)
            assertTrue(session.isAuthenticating.value)
            assertEquals("https://auth.openai.com/oauth?state=login-1", opened?.value)

            runtime.notify(
                "account/login/completed",
                buildJsonObject {
                    put("loginId", "login-1")
                    put("success", true)
                },
            )
            withTimeout(1_000) {
                session.state.first { it.status == AgentAuthenticationStatus.AUTHENTICATED }
            }
            assertTrue(session.isAuthenticated.value)
            assertFalse(session.isAuthenticating.value)
            assertTrue(presentationClosed)
        } finally {
            agent.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationState#property:deviceUserCode#sha256:0cdd227e00e5af6d51a3378aabaa9025ac34c660db62952258414990081bce5c",
        "api-v1:AgentAuthenticationState#property:deviceVerificationUrl#sha256:f9995c9c35bd05cafd2a2c9b45c7495a1d9840e711a039a4e0a7045cd1426c61",
    )
    fun deviceCodeAuthenticationProjectsTheLiveFacadeState() = runBlocking {
        val runtime = authenticationRuntime { loginId ->
            buildJsonObject {
                put("type", "chatgptDeviceCode")
                put("loginId", loginId)
                put("userCode", "ABCD-EFGH")
                put("verificationUrl", "https://auth.openai.com/device")
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val agent = authenticationAgent(client, this)
        try {
            agent.start()
            val session = agent.authentication
            session.authenticate(CodexAuthenticationMethod.ChatGptDeviceCode)
            val state = withTimeout(1_000) {
                session.state.first { it.deviceUserCode == "ABCD-EFGH" }
            }

            assertEquals("ABCD-EFGH", state.deviceUserCode)
            assertEquals("https://auth.openai.com/device", state.deviceVerificationUrl?.value)
        } finally {
            agent.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:CodexAuthentication#function:signOut#sha256:6283e0e71576b343125a1c3ce58f144f74528e587659a856e65c28c75cc44153",
    )
    fun signOutUsesTheLiveFacadeAndPublishesSignedOutState() = runBlocking {
        val logoutRequests = AtomicInteger()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/read" -> server.respond(
                    message.id,
                    buildJsonObject {
                        putJsonObject("account") { put("type", "chatgpt") }
                        put("requiresOpenaiAuth", true)
                    },
                )
                "account/logout" -> {
                    logoutRequests.incrementAndGet()
                    server.respond(message.id, buildJsonObject {})
                }
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val agent = authenticationAgent(client, this)
        try {
            agent.start()
            val session = agent.authentication
            session.authenticate()
            withTimeout(1_000) {
                session.state.first { it.status == AgentAuthenticationStatus.AUTHENTICATED }
            }

            session.signOut()

            assertEquals(1, logoutRequests.get())
            assertEquals(AgentAuthenticationStatus.SIGNED_OUT, session.state.value.status)
            assertFalse(session.isAuthenticated.value)
        } finally {
            agent.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentAuthenticationStatus#enum-entry:SIGNED_OUT#sha256:55d323d72fe3c40d329051499cd58064d1f70b99c3234f198e271159cefd9eea",
        "api-v1:CodexAuthentication#function:cancel#sha256:abd4e766df80e4e4dd0894248d03955eb1ebf6f9be35ac7fa9d4f20070ef9b16",
    )
    fun cancelThenRetryUsesANewGenerationWithoutAStaleFailure() = runBlocking {
        val attempts = AtomicInteger()
        val runtime = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "account/read" -> server.respond(message.id, signedOutAccount())
                "account/login/start" -> {
                    val loginId = "login-${attempts.incrementAndGet()}"
                    server.respond(
                        message.id,
                        buildJsonObject {
                            put("type", "chatgpt")
                            put("loginId", loginId)
                            put("authUrl", "https://auth.openai.com/oauth?state=$loginId")
                        },
                    )
                }
                "account/login/cancel" -> {
                    val loginId = message.objectValue["params"]!!.jsonObject["loginId"]!!.jsonPrimitive.content
                    server.notify(
                        "account/login/completed",
                        buildJsonObject {
                            put("loginId", loginId)
                            put("success", false)
                            put("error", "cancelled")
                        },
                    )
                    server.respond(message.id, buildJsonObject { put("status", "canceled") })
                }
            }
        }
        val client = CodexAgentClient({ runtime }, requestTimeoutMillis = 1_000)
        val agent = authenticationAgent(client, this)
        try {
            agent.start()
            val session = agent.authentication
            session.authenticate()
            withTimeout(1_000) { session.state.first { it.pendingSignInUrl != null } }
            assertTrue(session.isAuthenticating.value)
            session.cancel()
            assertEquals(AgentAuthenticationStatus.SIGNED_OUT, session.state.value.status)
            assertFalse(session.isAuthenticated.value)
            assertFalse(session.isAuthenticating.value)

            session.authenticate()
            withTimeout(1_000) {
                session.state.first {
                    it.status == AgentAuthenticationStatus.AUTHENTICATING &&
                        it.pendingSignInUrl?.value?.contains("login-2") == true
                }
            }
            assertTrue(session.isAuthenticating.value)
            assertEquals(2, attempts.get())
        } finally {
            agent.close()
        }
    }
}

private fun authenticationAgent(
    client: CodexAgentClient,
    scope: CoroutineScope,
    browser: CodexAuthorizationBrowser = CodexAuthorizationBrowser {
        CodexAuthorizationPresentation.None
    },
): CodexAgent = CodexAgent(
    workspace = CodexWorkspace("/workspace"),
    workingDirectory = "/workspace",
    features = emptySet(),
    client = client,
    parentScope = scope,
    authorizationBrowser = browser,
)

private fun authenticationRuntime(response: (String) -> kotlinx.serialization.json.JsonObject): FakeCodexRuntime {
    val attempts = AtomicInteger()
    return FakeCodexRuntime { message, server ->
        when (message.method) {
            "initialize" -> server.respond(message.id, buildJsonObject {})
            "account/read" -> server.respond(message.id, signedOutAccount())
            "account/login/start" -> server.respond(message.id, response("login-${attempts.incrementAndGet()}"))
        }
    }
}

private fun signedOutAccount() = buildJsonObject {
    put("account", JsonNull)
    put("requiresOpenaiAuth", true)
}
