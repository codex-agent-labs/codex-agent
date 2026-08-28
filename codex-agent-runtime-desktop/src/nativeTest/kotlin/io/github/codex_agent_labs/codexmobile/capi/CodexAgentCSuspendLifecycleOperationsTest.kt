@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegration
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.sizeOf
import kotlinx.cinterop.staticCFunction
import kotlinx.cinterop.value
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

class CodexAgentCSuspendLifecycleOperationsTest {
    @Test
    fun hostStartCompletesCanonicalOperationAndHoldsTargetThroughCallback(): Unit = runBlocking {
        val fixture = lifecycleFixture()
        memScoped {
            val contextSlot = newContext()
            val context = assertNotNull(contextSlot.value)
            val hostSlot = alloc<COpaquePointerVar>().also {
                it.value = installLifecycleHost(context, fixture)
            }
            assertSuccessfulLifecycleLaunch(context, hostSlot, LifecycleTarget.HOST) { callback, userData, output ->
                codexAgentHostStart(context, hostSlot.value, callback, userData, output)
            }
            closeLifecycleHost(context, assertNotNull(hostSlot.value))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, hostSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }

    @Test
    fun authenticationAuthenticateCopiesAndExecutesEveryMethodVariant(): Unit = runBlocking {
        AuthenticationVariant.entries.forEach { variant ->
            val fixture = lifecycleFixture()
            withReadyLifecycleGraph(fixture) { graph ->
                val methodSlot = createAuthenticationMethod(graph.context, variant)
                assertSuccessfulLifecycleLaunch(
                    graph.context,
                    graph.authenticationSlot,
                    LifecycleTarget.AUTHENTICATION,
                    afterLaunch = {
                        destroyAuthenticationMethod(graph.context, variant, methodSlot)
                        assertNull(methodSlot.value)
                    },
                ) { callback, userData, output ->
                    when (variant) {
                        AuthenticationVariant.API_KEY -> codexAgentAuthenticationAuthenticateApiKey(
                            graph.context,
                            graph.authenticationSlot.value,
                            methodSlot.value,
                            callback,
                            userData,
                            output,
                        )

                        AuthenticationVariant.BROWSER -> codexAgentAuthenticationAuthenticateChatGptBrowser(
                            graph.context,
                            graph.authenticationSlot.value,
                            methodSlot.value,
                            callback,
                            userData,
                            output,
                        )

                        AuthenticationVariant.DEVICE_CODE -> codexAgentAuthenticationAuthenticateChatGptDeviceCode(
                            graph.context,
                            graph.authenticationSlot.value,
                            methodSlot.value,
                            callback,
                            userData,
                            output,
                        )
                    }
                }
                val login = fixture.additionalRequests.single { it.first == "account/login/start" }.second
                assertEquals(variant.protocolType, login.getValue("type").jsonPrimitive.content)
                if (variant == AuthenticationVariant.API_KEY) {
                    assertEquals(API_KEY, login.getValue("apiKey").jsonPrimitive.content)
                }
            }
        }
    }

    @Test
    fun authenticationCancelCompletesCanonicalOperation(): Unit = runBlocking {
        val fixture = lifecycleFixture()
        withReadyLifecycleGraph(fixture) { graph ->
            val method = createAuthenticationMethod(graph.context, AuthenticationVariant.BROWSER)
            launchWithoutCallback(graph.context) { output ->
                codexAgentAuthenticationAuthenticateChatGptBrowser(
                    graph.context,
                    graph.authenticationSlot.value,
                    method.value,
                    null,
                    null,
                    output,
                )
            }
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.BROWSER, method)

            assertSuccessfulLifecycleLaunch(
                graph.context,
                graph.authenticationSlot,
                LifecycleTarget.AUTHENTICATION,
            ) { callback, userData, output ->
                codexAgentAuthenticationCancel(
                    graph.context,
                    graph.authenticationSlot.value,
                    callback,
                    userData,
                    output,
                )
            }
            assertTrue(fixture.additionalRequests.any { it.first == "account/login/cancel" })
        }
    }

    @Test
    fun authenticationSignOutCompletesCanonicalOperation(): Unit = runBlocking {
        val fixture = lifecycleFixture()
        withReadyLifecycleGraph(fixture) { graph ->
            assertSuccessfulLifecycleLaunch(
                graph.context,
                graph.authenticationSlot,
                LifecycleTarget.AUTHENTICATION,
            ) { callback, userData, output ->
                codexAgentAuthenticationSignOut(
                    graph.context,
                    graph.authenticationSlot.value,
                    callback,
                    userData,
                    output,
                )
            }
            assertEquals(1, fixture.additionalRequests.count { it.first == "account/logout" })
        }
    }

    @Test
    fun integrationAuthorizationAuthorizeCopiesAndExecutesBothTargetVariants(): Unit = runBlocking {
        val fixture = lifecycleFixture(
            features = setOf(CodexRuntimeFeature.CONNECTORS, CodexRuntimeFeature.MCP_SERVERS),
        )
        withReadyLifecycleGraph(fixture) { graph ->
            val connector = createIntegration(
                graph.context,
                AgentIntegration.Connector(
                    AgentConnector(
                        id = CONNECTOR_ID,
                        name = "Drive",
                        isAccessible = true,
                        pluginNames = listOf("drive-plugin"),
                    ),
                ),
            )
            assertSuccessfulLifecycleLaunch(
                graph.context,
                graph.authorizationSlot,
                LifecycleTarget.AUTHORIZATION,
                afterLaunch = {
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, connector.ptr))
                    assertNull(connector.value)
                },
            ) { callback, userData, output ->
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    connector.value,
                    callback,
                    userData,
                    output,
                )
            }

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAgentIntegrationAuthorization(
                    graph.context,
                    graph.agentSlot.value,
                    graph.authorizationSlot.ptr,
                ),
            )
            assertNotNull(graph.authorizationSlot.value)

            val mcp = createIntegration(
                graph.context,
                AgentIntegration.McpServer(
                    AgentMcpServer(MCP_NAME, "Drive MCP", AgentMcpAuthStatus.NOT_LOGGED_IN),
                ),
            )
            assertSuccessfulLifecycleLaunch(
                graph.context,
                graph.authorizationSlot,
                LifecycleTarget.AUTHORIZATION,
                afterLaunch = {
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, mcp.ptr))
                    assertNull(mcp.value)
                    awaitRequest(fixture, "mcpServer/oauth/login")
                    fixture.notify(
                        "mcpServer/oauthLogin/completed",
                        buildJsonObject { put("name", MCP_NAME); put("success", true) },
                    )
                },
            ) { callback, userData, output ->
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    mcp.value,
                    callback,
                    userData,
                    output,
                )
            }
            assertTrue(fixture.additionalRequests.any { it.first == "app/list" })
            assertTrue(fixture.additionalRequests.any { it.first == "mcpServer/oauth/login" })
        }
    }

    @Test
    fun integrationAuthorizationCancelCompletesCanonicalOperation(): Unit = runBlocking {
        val fixture = lifecycleFixture(
            features = setOf(CodexRuntimeFeature.MCP_SERVERS),
        )
        withReadyLifecycleGraph(fixture) { graph ->
            val target = createIntegration(
                graph.context,
                AgentIntegration.McpServer(
                    AgentMcpServer(MCP_NAME, "Drive MCP", AgentMcpAuthStatus.NOT_LOGGED_IN),
                ),
            )
            val authorize = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    target.value,
                    null,
                    null,
                    authorize.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, target.ptr))
            awaitRequest(fixture, "mcpServer/oauth/login")

            assertSuccessfulLifecycleLaunch(
                graph.context,
                graph.authorizationSlot,
                LifecycleTarget.AUTHORIZATION,
            ) { callback, userData, output ->
                codexAgentIntegrationAuthorizationCancel(
                    graph.context,
                    graph.authorizationSlot.value,
                    callback,
                    userData,
                    output,
                )
            }
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitLifecycleResult(graph.context, authorize.value))
            destroyLifecycleOperation(graph.context, authorize.ptr)
        }
    }

    @Test
    fun synchronousTargetPreparationFailureReleasesEveryLeaseAndKeepsOutputEmpty(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val created = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            PreparationFailureTarget,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, created.status)
        val target = assertNotNull(created.value)
        val output = alloc<COpaquePointerVar>().also { it.value = null }

        assertEquals(
            CODEX_AGENT_STATUS_INTERNAL_ERROR,
            startCodexAgentCTargetOperation<PreparationFailureTarget>(
                context,
                target,
                CodexAgentCHandleKind.HOST,
                null,
                null,
                output.ptr,
                runtime = { error("injected target preparation failure") },
                execute = { CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK) },
            ),
        )
        assertNull(output.value)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            handleRegistry.abandonOpenEntry(context, target, CodexAgentCHandleKind.HOST),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
    }

    @Test
    fun lifecycleLaunchersRejectInvalidHandlesAndPreserveOccupiedOutputs(): Unit = runBlocking {
        val fixture = lifecycleFixture(
            features = setOf(CodexRuntimeFeature.CONNECTORS),
        )
        withReadyLifecycleGraph(fixture) { graph ->
            val otherContextSlot = newContext()
            val otherContext = assertNotNull(otherContextSlot.value)
            val apiKey = createAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY)
            val browser = createAuthenticationMethod(graph.context, AuthenticationVariant.BROWSER)
            val device = createAuthenticationMethod(graph.context, AuthenticationVariant.DEVICE_CODE)
            val integration = createIntegration(
                graph.context,
                AgentIntegration.Connector(AgentConnector(CONNECTOR_ID, "Drive", isAccessible = true)),
            )
            val staleHost = alloc<COpaquePointerVar>().also {
                it.value = null
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRetain(graph.context, graph.hostSlot.value, it.ptr))
            }
            val staleHostValue = assertNotNull(staleHost.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(graph.context, staleHost.ptr))
            val staleAuthentication = retainedAuthentication(
                graph.context,
                assertNotNull(graph.authenticationSlot.value),
            )
            val staleAuthenticationValue = assertNotNull(staleAuthentication.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationRelease(graph.context, staleAuthentication.ptr))
            val staleAuthorization = alloc<COpaquePointerVar>().also {
                it.value = null
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationRetain(
                        graph.context,
                        graph.authorizationSlot.value,
                        it.ptr,
                    ),
                )
            }
            val staleAuthorizationValue = assertNotNull(staleAuthorization.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationRelease(graph.context, staleAuthorization.ptr),
            )
            val cases = listOf(
                InvalidLaunchCase(
                    "host_start",
                    graph.hostSlot,
                    graph.authenticationSlot,
                    staleHostValue,
                ) { context, target, output ->
                    codexAgentHostStart(context, target, null, null, output)
                },
                InvalidLaunchCase(
                    "authenticate_api_key",
                    graph.authenticationSlot,
                    graph.hostSlot,
                    staleAuthenticationValue,
                ) { context, target, output ->
                    codexAgentAuthenticationAuthenticateApiKey(context, target, apiKey.value, null, null, output)
                },
                InvalidLaunchCase(
                    "authenticate_browser",
                    graph.authenticationSlot,
                    graph.hostSlot,
                    staleAuthenticationValue,
                ) { context, target, output ->
                    codexAgentAuthenticationAuthenticateChatGptBrowser(
                        context,
                        target,
                        browser.value,
                        null,
                        null,
                        output,
                    )
                },
                InvalidLaunchCase(
                    "authenticate_device",
                    graph.authenticationSlot,
                    graph.hostSlot,
                    staleAuthenticationValue,
                ) { context, target, output ->
                    codexAgentAuthenticationAuthenticateChatGptDeviceCode(
                        context,
                        target,
                        device.value,
                        null,
                        null,
                        output,
                    )
                },
                InvalidLaunchCase(
                    "authentication_cancel",
                    graph.authenticationSlot,
                    graph.hostSlot,
                    staleAuthenticationValue,
                ) { context, target, output ->
                    codexAgentAuthenticationCancel(context, target, null, null, output)
                },
                InvalidLaunchCase(
                    "authentication_sign_out",
                    graph.authenticationSlot,
                    graph.hostSlot,
                    staleAuthenticationValue,
                ) { context, target, output ->
                    codexAgentAuthenticationSignOut(context, target, null, null, output)
                },
                InvalidLaunchCase(
                    "authorization_authorize",
                    graph.authorizationSlot,
                    graph.hostSlot,
                    staleAuthorizationValue,
                ) { context, target, output ->
                    codexAgentIntegrationAuthorizationAuthorize(context, target, integration.value, null, null, output)
                },
                InvalidLaunchCase(
                    "authorization_cancel",
                    graph.authorizationSlot,
                    graph.hostSlot,
                    staleAuthorizationValue,
                ) { context, target, output ->
                    codexAgentIntegrationAuthorizationCancel(context, target, null, null, output)
                },
            )
            cases.forEach { case ->
                val occupied = alloc<COpaquePointerVar>().also { it.value = graph.hostSlot.value }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    case.launch(graph.context, case.target.value, occupied.ptr),
                    case.name,
                )
                assertEquals(graph.hostSlot.value, occupied.value, case.name)
                occupied.value = null
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    case.launch(null, case.target.value, occupied.ptr),
                    case.name,
                )
                assertNull(occupied.value, case.name)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    case.launch(graph.context, null, occupied.ptr),
                    case.name,
                )
                assertNull(occupied.value, case.name)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    case.launch(graph.context, case.target.value, null),
                    case.name,
                )
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    case.launch(otherContext, case.target.value, occupied.ptr),
                    case.name,
                )
                assertNull(occupied.value, case.name)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    case.launch(graph.context, case.wrongType.value, occupied.ptr),
                    case.name,
                )
                assertNull(occupied.value, case.name)
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    case.launch(graph.context, case.staleTarget, occupied.ptr),
                    case.name,
                )
                assertNull(occupied.value, case.name)
            }

            val output = alloc<COpaquePointerVar>().also { it.value = null }
            val staleMethod = createAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY)
            val staleMethodValue = assertNotNull(staleMethod.value)
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY, staleMethod)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationAuthenticateApiKey(
                    graph.context,
                    graph.authenticationSlot.value,
                    staleMethodValue,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationAuthenticateApiKey(
                    graph.context,
                    graph.authenticationSlot.value,
                    graph.hostSlot.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            listOf(
                codexAgentAuthenticationAuthenticateApiKey(
                    graph.context,
                    graph.authenticationSlot.value,
                    null,
                    null,
                    null,
                    output.ptr,
                ),
                codexAgentAuthenticationAuthenticateChatGptBrowser(
                    graph.context,
                    graph.authenticationSlot.value,
                    null,
                    null,
                    null,
                    output.ptr,
                ),
                codexAgentAuthenticationAuthenticateChatGptDeviceCode(
                    graph.context,
                    graph.authenticationSlot.value,
                    null,
                    null,
                    null,
                    output.ptr,
                ),
            ).forEach {
                assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, it)
                assertNull(output.value)
            }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationAuthenticateChatGptBrowser(
                    graph.context,
                    graph.authenticationSlot.value,
                    apiKey.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationAuthenticateChatGptDeviceCode(
                    graph.context,
                    graph.authenticationSlot.value,
                    browser.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    null,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    graph.hostSlot.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            val staleIntegration = createIntegration(
                graph.context,
                AgentIntegration.Connector(AgentConnector("stale", "Stale", isAccessible = true)),
            )
            val staleIntegrationValue = assertNotNull(staleIntegration.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationDestroy(graph.context, staleIntegration.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationAuthorizationAuthorize(
                    graph.context,
                    graph.authorizationSlot.value,
                    staleIntegrationValue,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            destroyAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY, apiKey)
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.BROWSER, browser)
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.DEVICE_CODE, device)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, integration.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        }
    }

    @Test
    fun lifecycleOperationsPublishFailureCancellationAndQuiescentDestroy(): Unit = runBlocking {
        val failureFixture = NativeCodexBehaviorFixture(
            additionalResponse = { method, _ ->
                when (method) {
                    "account/read" -> buildJsonObject {}
                    else -> lifecycleResponse(method, buildJsonObject {})
                }
            },
        )
        withReadyLifecycleGraph(failureFixture) { graph ->
            val method = createAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY)
            val operation = alloc<COpaquePointerVar>().also { it.value = null }
            val observer = LifecycleOperationObserver(
                operation.ptr,
                graph.authenticationSlot.ptr,
                LifecycleTarget.AUTHENTICATION,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationAuthenticateApiKey(
                    graph.context,
                    graph.authenticationSlot.value,
                    method.value,
                    lifecycleOperationCallback,
                    observer.userData,
                    operation.ptr,
                ),
            )
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY, method)
            receiveLifecycleCallback(observer, graph.context, operation.value)
            assertEquals(CODEX_AGENT_STATUS_OPERATION_FAILED, awaitLifecycleResult(graph.context, operation.value))
            val failure = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationFailure(graph.context, operation.value, failure.ptr))
            assertNotNull(failure.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(graph.context, failure.ptr))
            destroyLifecycleOperation(graph.context, operation.ptr)
            observer.dispose()
        }

        val cancellationFixture = NativeCodexBehaviorFixture(
            additionalResponse = { method, params ->
                if (method == "account/read") null else lifecycleResponse(method, params)
            },
        )
        withReadyLifecycleGraph(cancellationFixture) { graph ->
            val method = createAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY)
            val operation = alloc<COpaquePointerVar>().also { it.value = null }
            val observer = LifecycleOperationObserver(
                operation.ptr,
                graph.authenticationSlot.ptr,
                LifecycleTarget.AUTHENTICATION,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationAuthenticateApiKey(
                    graph.context,
                    graph.authenticationSlot.value,
                    method.value,
                    lifecycleOperationCallback,
                    observer.userData,
                    operation.ptr,
                ),
            )
            destroyAuthenticationMethod(graph.context, AuthenticationVariant.API_KEY, method)
            awaitRequest(cancellationFixture, "account/read")
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(graph.context, operation.value))
            receiveLifecycleCallback(observer, graph.context, operation.value)
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitLifecycleResult(graph.context, operation.value))
            destroyLifecycleOperation(graph.context, operation.ptr)
            assertEquals(1, observer.callbacks.load())
            observer.dispose()
        }
    }
}

private enum class AuthenticationVariant(val protocolType: String) {
    API_KEY("apiKey"),
    BROWSER("chatgpt"),
    DEVICE_CODE("chatgptDeviceCode"),
}

private enum class LifecycleTarget { HOST, AUTHENTICATION, AUTHORIZATION }

private object PreparationFailureTarget

private data class LifecycleOperationEvent(
    val context: COpaquePointer?,
    val operation: COpaquePointer?,
    val userData: COpaquePointer?,
    val publishedOperation: COpaquePointer?,
    val releaseStatus: Int,
    val publishedTarget: COpaquePointer?,
)

private class LifecycleOperationObserver(
    val output: CPointer<COpaquePointerVar>,
    val target: CPointer<COpaquePointerVar>,
    val targetKind: LifecycleTarget,
) {
    val callbacks = AtomicInt(0)
    val events = Channel<LifecycleOperationEvent>(Channel.UNLIMITED)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun dispose() = reference.dispose()
}

private val lifecycleOperationCallback = staticCFunction {
        context: COpaquePointer?,
        operation: COpaquePointer?,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<LifecycleOperationObserver>().get()
    observer.callbacks.addAndFetch(1)
    val releaseStatus = when (observer.targetKind) {
        LifecycleTarget.HOST -> codexAgentHostRelease(context, observer.target)
        LifecycleTarget.AUTHENTICATION -> codexAgentAuthenticationRelease(context, observer.target)
        LifecycleTarget.AUTHORIZATION -> codexAgentIntegrationAuthorizationRelease(context, observer.target)
    }
    observer.events.trySend(
        LifecycleOperationEvent(
            context,
            operation,
            userData,
            observer.output.pointed.value,
            releaseStatus,
            observer.target.pointed.value,
        ),
    )
    Unit
}

private data class ReadyLifecycleGraph(
    val contextSlot: COpaquePointerVar,
    val context: COpaquePointer,
    val hostSlot: COpaquePointerVar,
    val agentSlot: COpaquePointerVar,
    val authenticationSlot: COpaquePointerVar,
    val authorizationSlot: COpaquePointerVar,
)

private data class InvalidLaunchCase(
    val name: String,
    val target: COpaquePointerVar,
    val wrongType: COpaquePointerVar,
    val staleTarget: COpaquePointer,
    val launch: (COpaquePointer?, COpaquePointer?, CPointer<COpaquePointerVar>?) -> Int,
)

private fun lifecycleFixture(
    features: Set<CodexRuntimeFeature> = emptySet(),
): NativeCodexBehaviorFixture = NativeCodexBehaviorFixture(
    features = features,
    additionalResponse = ::lifecycleResponse,
)

private fun lifecycleResponse(method: String, params: JsonObject): JsonObject? = when (method) {
    "account/read" -> buildJsonObject {
        put("account", JsonNull)
        put("requiresOpenaiAuth", true)
    }

    "account/login/start" -> when (params.getValue("type").jsonPrimitive.content) {
        "apiKey" -> buildJsonObject { put("type", "apiKey") }
        "chatgpt" -> buildJsonObject {
            put("type", "chatgpt")
            put("loginId", LOGIN_ID)
            put("authUrl", "https://auth.openai.com/browser")
        }

        "chatgptDeviceCode" -> buildJsonObject {
            put("type", "chatgptDeviceCode")
            put("loginId", LOGIN_ID)
            put("verificationUrl", "https://auth.example.com/device")
            put("userCode", "ABCD-EFGH")
        }

        else -> error("unexpected authentication type")
    }

    "account/login/cancel" -> buildJsonObject { put("status", "canceled") }
    "account/logout" -> buildJsonObject {}
    "app/list" -> buildJsonObject {
        putJsonArray("data") {
            add(buildJsonObject {
                put("id", CONNECTOR_ID)
                put("name", "Drive")
                put("description", "Files")
                put("isAccessible", true)
                put("isEnabled", true)
            })
        }
    }

    "mcpServer/oauth/login" -> buildJsonObject {
        put("authorizationUrl", "https://auth.example.com/mcp")
    }

    else -> null
}

private suspend fun withReadyLifecycleGraph(
    fixture: NativeCodexBehaviorFixture,
    block: suspend MemScope.(ReadyLifecycleGraph) -> Unit,
) {
    memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val hostSlot = alloc<COpaquePointerVar>().also { it.value = installLifecycleHost(context, fixture) }
        selectLifecycleWorkspace(context, assertNotNull(hostSlot.value), fixture.workspace.path)
        val state = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, hostSlot.value, state.ptr))
        val agentSlot = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHostStateAgent(context, hostSlot.value, state.value, agentSlot.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, state.ptr))
        val authenticationSlot = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAgentAuthentication(context, agentSlot.value, authenticationSlot.ptr),
        )
        val authorizationSlot = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAgentIntegrationAuthorization(context, agentSlot.value, authorizationSlot.ptr),
        )
        val graph = ReadyLifecycleGraph(
            contextSlot,
            context,
            hostSlot,
            agentSlot,
            authenticationSlot,
            authorizationSlot,
        )
        try {
            block(graph)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationRelease(context, authenticationSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationRelease(context, authorizationSlot.ptr),
            )
            closeLifecycleHost(context, assertNotNull(hostSlot.value))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(context, agentSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, hostSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }
}

private fun MemScope.newContext(): COpaquePointerVar = alloc<COpaquePointerVar>().also {
    it.value = null
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
}

private fun installLifecycleHost(
    context: COpaquePointer,
    fixture: NativeCodexBehaviorFixture,
): COpaquePointer {
    val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
    val runtime = contextLease.payload as CodexAgentCContextRuntime
    assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())
    val created = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        CodexAgentCHost(fixture.createHost(), runtime),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    return assertNotNull(created.value)
}

private suspend fun MemScope.selectLifecycleWorkspace(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        writeLifecycleUtf8(it.path, path)
    }
    launchWithoutCallback(context) { output ->
        codexAgentHostSelectWorkspace(context, host, selection.ptr, null, null, output)
    }
}

private suspend fun MemScope.closeLifecycleHost(context: COpaquePointer, host: COpaquePointer) {
    launchWithoutCallback(context) { output ->
        codexAgentHostClose(context, host, null, null, output)
    }
}

private suspend fun MemScope.launchWithoutCallback(
    context: COpaquePointer,
    launch: (CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(CODEX_AGENT_STATUS_OK, launch(operation.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, awaitLifecycleResult(context, operation.value))
    destroyLifecycleOperation(context, operation.ptr)
}

private suspend fun MemScope.assertSuccessfulLifecycleLaunch(
    context: COpaquePointer,
    target: COpaquePointerVar,
    targetKind: LifecycleTarget,
    afterLaunch: suspend () -> Unit = {},
    launch: (CodexAgentCOperationCallback?, COpaquePointer?, CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = alloc<COpaquePointerVar>().also { it.value = null }
    val observer = LifecycleOperationObserver(operation.ptr, target.ptr, targetKind)
    val targetValue = assertNotNull(target.value)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        launch(lifecycleOperationCallback, observer.userData, operation.ptr),
    )
    assertNotNull(operation.value)
    afterLaunch()
    val event = receiveLifecycleCallback(observer, context, operation.value)
    when (targetKind) {
        LifecycleTarget.HOST -> {
            assertEquals(CODEX_AGENT_STATUS_BUSY, event.releaseStatus)
            assertEquals(targetValue, event.publishedTarget)
        }

        LifecycleTarget.AUTHENTICATION,
        LifecycleTarget.AUTHORIZATION -> {
            assertEquals(CODEX_AGENT_STATUS_OK, event.releaseStatus)
            assertNull(event.publishedTarget)
        }
    }
    val completed = withTimeout(TIMEOUT_MILLIS) {
        val result = alloc<IntVar>()
        while (true) {
            when (val status = codexAgentOperationResult(context, operation.value, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                else -> error("operation result query failed with $status")
            }
        }
        error("unreachable")
    }
    assertEquals(CODEX_AGENT_STATUS_OK, completed)
    destroyLifecycleOperation(context, operation.ptr)
    assertEquals(1, observer.callbacks.load())
    observer.dispose()
}

private suspend fun receiveLifecycleCallback(
    observer: LifecycleOperationObserver,
    context: COpaquePointer,
    operation: COpaquePointer?,
): LifecycleOperationEvent = withTimeout(TIMEOUT_MILLIS) {
    observer.events.receive().also {
        assertEquals(context, it.context)
        assertEquals(operation, it.operation)
        assertEquals(operation, it.publishedOperation)
        assertEquals(observer.userData, it.userData)
    }
}

private suspend fun awaitLifecycleResult(context: COpaquePointer, operation: COpaquePointer?): Int =
    withTimeout(TIMEOUT_MILLIS) {
        memScoped {
            val result = alloc<IntVar>()
            while (true) {
                when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                    CODEX_AGENT_STATUS_NOT_READY -> yield()
                    CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                    else -> error("operation result query failed with $status")
                }
            }
            error("unreachable")
        }
    }

private suspend fun destroyLifecycleOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentOperationDestroy(context, operation)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("operation destroy failed with $status")
            }
        }
    }
    assertNull(operation.pointed.value)
}

private fun MemScope.createAuthenticationMethod(
    context: COpaquePointer,
    variant: AuthenticationVariant,
): COpaquePointerVar = alloc<COpaquePointerVar>().also { slot ->
    slot.value = null
    val status = when (variant) {
        AuthenticationVariant.API_KEY -> {
            val value = alloc<codex_agent_string_view>().also { writeLifecycleUtf8(it, API_KEY) }
            codexAgentAuthenticationMethodApiKeyCreate(context, value.ptr, slot.ptr)
        }

        AuthenticationVariant.BROWSER -> codexAgentAuthenticationMethodChatGptBrowserCreate(context, slot.ptr)
        AuthenticationVariant.DEVICE_CODE -> codexAgentAuthenticationMethodChatGptDeviceCodeCreate(context, slot.ptr)
    }
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    assertNotNull(slot.value)
}

private fun destroyAuthenticationMethod(
    context: COpaquePointer,
    variant: AuthenticationVariant,
    slot: COpaquePointerVar,
) {
    val status = when (variant) {
        AuthenticationVariant.API_KEY -> codexAgentAuthenticationMethodApiKeyDestroy(context, slot.ptr)
        AuthenticationVariant.BROWSER -> codexAgentAuthenticationMethodChatGptBrowserDestroy(context, slot.ptr)
        AuthenticationVariant.DEVICE_CODE -> codexAgentAuthenticationMethodChatGptDeviceCodeDestroy(context, slot.ptr)
    }
    assertEquals(CODEX_AGENT_STATUS_OK, status)
}

private fun MemScope.createIntegration(
    context: COpaquePointer,
    value: AgentIntegration,
): COpaquePointerVar = alloc<COpaquePointerVar>().also { slot ->
    val created = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.SNAPSHOT,
        CodexAgentCIntegrationSnapshot(value),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    slot.value = assertNotNull(created.value)
}

private fun MemScope.retainedAuthentication(
    context: COpaquePointer,
    authentication: COpaquePointer,
): COpaquePointerVar = alloc<COpaquePointerVar>().also {
    it.value = null
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationRetain(context, authentication, it.ptr))
}

private suspend fun awaitRequest(fixture: NativeCodexBehaviorFixture, method: String) {
    withTimeout(TIMEOUT_MILLIS) {
        while (fixture.additionalRequests.none { it.first == method }) yield()
    }
}

private fun MemScope.writeLifecycleUtf8(target: codex_agent_string_view, value: String) {
    val bytes = value.encodeToByteArray()
    target.size = bytes.size.toULong()
    target.data = allocArray<UByteVar>(bytes.size).also { buffer ->
        bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    }
}

private const val API_KEY = "sk-native-copy-proof"
private const val LOGIN_ID = "native-login"
private const val CONNECTOR_ID = "drive"
private const val MCP_NAME = "drive-mcp"
private const val TIMEOUT_MILLIS = 10_000L
