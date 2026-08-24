package io.github.codex_agent_labs.codexmobile.agent

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
        "api-v1:AgentAuthenticationState#property:pendingSignInUrl#sha256:6170ce8e38f54ca68b8119b71d7d3e1b009107dca96496a0bd295e3fb60d38e8",
        "api-v1:AgentAuthenticationState#property:status#sha256:765f074f73dd717a2f7fad25644b91c6287d52c9187ca38dcdf5b59b452a0c83",
        "api-v1:AgentAuthenticationStatus#enum-entry:AUTHENTICATED#sha256:053207144c81be6df2c3be6e79a98cd4c7a89877eb1c5288e8251d19aca269e6",
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
        "api-v1:AgentAuthenticationState#property:failure#sha256:1f0788690bf5f86cd971fd4dffd298b4ac33fa009fb503a7414a6831757864c7",
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
        "api-v1:AgentAuthenticationState#constructor:<init>#sha256:93ba33d45997555d340fff46bc63343e3fb4689a6cbd05f0806b9e2a024c9bf2",
        "api-v1:AgentAuthenticationStatus#enum-entry:AUTHENTICATING#sha256:1a6e1dfd3618cd83f83cf5215e68356e03464bae1de32c14a1bb09d22c5c97f2",
        "api-v1:CodexAuthentication#function:authenticate#sha256:5270ef1969feacb0aa737a62cb2a0babc02a7ea1eec4ce206bdad895d1ba8a74",
        "api-v1:CodexAuthentication#property:isAuthenticated#sha256:948fbccda2efac02f4b6e4c14cf048c4ee3202ca8511e4296f16779b278a3d40",
        "api-v1:CodexAuthentication#property:isAuthenticating#sha256:7303de5b50da5aa7109a10175920f355b2dbaccc8e40782a019e3c9dfdd6973d",
        "api-v1:CodexAuthentication#property:state#sha256:70002c53c0e792518c6b3272a282913c7589e10653a369c212853797209601f2",
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
        "api-v1:AgentAuthenticationState#property:deviceUserCode#sha256:404ec2cf06f874b03b3bf8f65a7ee3d91670644a30951e26cd01574a877f198a",
        "api-v1:AgentAuthenticationState#property:deviceVerificationUrl#sha256:7a2c1af3419c46dfbeec0dd822ce94d6092eaffa7e265162b55d02ccccda16b0",
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
        "api-v1:CodexAuthentication#function:signOut#sha256:5ab21c9aeb86f51ad07fa5358114d7b12f0d36bfa131d6ed09ca60cb504d038c",
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
        "api-v1:AgentAuthenticationStatus#enum-entry:SIGNED_OUT#sha256:3f56325b04ac2bcb0d3fa74a8a80095dc313f06c5926f856cf4af041cbe14ccf",
        "api-v1:CodexAuthentication#function:cancel#sha256:6774f15170d7cc61a1cb1625fb842b8f63c6831bc0b3df96477a2ef3e16ae902",
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
