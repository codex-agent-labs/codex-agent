@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentHook
import io.github.codex_agent_labs.codexagent.agent.AgentHookHandler
import io.github.codex_agent_labs.codexagent.agent.AgentHookTrustStatus
import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthentication
import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexagent.agent.AgentMcpOauthConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServer
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServerConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolApproval
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolExposureSurface
import io.github.codex_agent_labs.codexagent.agent.AgentMcpTransport
import io.github.codex_agent_labs.codexagent.agent.AgentModel
import io.github.codex_agent_labs.codexagent.agent.AgentPluginReference
import io.github.codex_agent_labs.codexagent.agent.AgentResolution
import io.github.codex_agent_labs.codexagent.agent.AgentResourceOrigin
import io.github.codex_agent_labs.codexagent.agent.AgentSkill
import io.github.codex_agent_labs.codexagent.agent.AgentSkillScope
import io.github.codex_agent_labs.codexagent.agent.AgentServiceTier
import io.github.codex_agent_labs.codexagent.agent.CodexAgent
import io.github.codex_agent_labs.codexagent.agent.CodexHost
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexPlatform
import io.github.codex_agent_labs.codexagent.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import okio.FileSystem
import okio.Path
import okio.Path.Companion.toPath

class CodexAgentCSuspendCatalogOperationsTest {
    @Test
    fun modelsListReturnsFreshOrderedDuplicates(): Unit = catalogTest { graph ->
        val models = graph.service(CodexAgentCHandleKind.MODELS, ::codexAgentAgentModels)
        val result = graph.operation(
            inspect = { operation ->
                val count = alloc<ULongVar>()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationModelsCount(graph.context, operation, count.ptr),
                )
                assertEquals(5uL, count.value)
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationModelAt(graph.context, operation, 1uL, output)
                }
            },
        ) { out -> codexAgentModelsList(graph.context, models, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.MODELS, result.valueKind)
        val values = result.value as List<*>
        assertEquals(
            listOf("first", "preferred", "default", "duplicate", "duplicate"),
            values.map { (it as AgentModel).id },
        )
        assertFalse(values[3] === values[4])
    }

    @Test
    fun modelsResolveHonorsExactResolution(): Unit = catalogTest { graph ->
        val models = graph.service(CodexAgentCHandleKind.MODELS, ::codexAgentAgentModels)
        val result = graph.operation(
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationModel(graph.context, operation, output)
                }
            },
        ) { out -> codexAgentModelsResolve(graph.context, models, 2, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.MODEL, result.valueKind)
        assertEquals("first", (result.value as AgentModel).id)
    }

    @Test
    fun modelsResolveEffortCopiesModelBeforeLaunch(): Unit = catalogTest { graph ->
        val models = graph.service(CodexAgentCHandleKind.MODELS, ::codexAgentAgentModels)
        val input = graph.snapshot(CodexAgentCModelSnapshot(catalogModel("input")))
        val result = graph.operation(
            afterStart = { graph.releaseSnapshot(input) },
            inspect = { operation ->
                assertEquals("default-effort", copyCatalogOperationString(graph.context, operation))
            },
        ) { out -> codexAgentModelsResolveEffort(graph.context, models, input, 1, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.STRING, result.valueKind)
        assertEquals("default-effort", result.value)
    }

    @Test
    fun modelsResolveServiceTierDistinguishesPresentAndAbsent(): Unit = catalogTest { graph ->
        val models = graph.service(CodexAgentCHandleKind.MODELS, ::codexAgentAgentModels)
        val present = graph.snapshot(CodexAgentCModelSnapshot(catalogModel("present")))
        val absent = graph.snapshot(CodexAgentCModelSnapshot(catalogModel("absent", withTier = false)))
        val presentResult = graph.operation(inspect = { operation ->
            val hasTier = alloc<IntVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationHasServiceTier(graph.context, operation, hasTier.ptr),
            )
            assertEquals(1, hasTier.value)
            assertCatalogOperationSnapshot(graph.context) { output ->
                codexAgentOperationServiceTier(graph.context, operation, output)
            }
        }) { out ->
            codexAgentModelsResolveServiceTier(graph.context, models, present, 1, null, null, out)
        }
        val absentResult = graph.operation(inspect = { operation ->
            val hasTier = alloc<IntVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationHasServiceTier(graph.context, operation, hasTier.ptr),
            )
            assertEquals(0, hasTier.value)
        }) { out ->
            codexAgentModelsResolveServiceTier(graph.context, models, absent, 1, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.SERVICE_TIER, presentResult.valueKind)
        assertEquals("default-tier", (presentResult.value as AgentServiceTier).id)
        assertEquals(CodexAgentCOperationValueKind.SERVICE_TIER, absentResult.valueKind)
        assertNull(absentResult.value)
    }

    @Test
    fun skillsListCopiesFlagAndCatalog(): Unit = catalogTest { graph ->
        val skills = graph.service(CodexAgentCHandleKind.SKILLS, ::codexAgentAgentSkills)
        val result = graph.operation(
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationSkillCatalog(graph.context, operation, output)
                }
            },
        ) { out -> codexAgentSkillsList(graph.context, skills, 1, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.SKILL_CATALOG, result.valueKind)
        val catalog = result.value as io.github.codex_agent_labs.codexagent.agent.AgentSkillCatalog
        assertEquals(listOf("catalog-read"), catalog.skills.map(AgentSkill::name))
        assertTrue(graph.fixture.additionalRequests.single { it.first == "skills/list" }.second["forceReload"]!!.jsonPrimitive.boolean)
    }

    @Test
    fun skillsReadCopiesPathAndOffset(): Unit = catalogTest { graph ->
        val skills = graph.service(CodexAgentCHandleKind.SKILLS, ::codexAgentAgentSkills)
        graph.agent.skills.list()
        memScoped {
            val path = utf8(CATALOG_SKILL_PATH.toString())
            val result = graph.operation(inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationSkillChunk(graph.context, operation, output)
                }
            }) { out ->
                codexAgentSkillsRead(graph.context, skills, path, 2, null, null, out)
            }
            assertEquals(CodexAgentCOperationValueKind.SKILL_CHUNK, result.valueKind)
            val chunk = result.value as io.github.codex_agent_labs.codexagent.agent.AgentSkillChunk
            assertEquals(CATALOG_SKILL_TEXT.drop(2), chunk.content)
            assertNull(chunk.nextOffset)
        }
    }

    @Test
    fun skillsInstallReturnsFreshOwnedSkill(): Unit = catalogTest { graph ->
        val bundle = graph.protocol.createSkillBundle()
        val skills = graph.service(CodexAgentCHandleKind.SKILLS, ::codexAgentAgentSkills)
        memScoped {
            val directory = utf8(bundle.toString())
            val result = graph.operation(inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationSkill(graph.context, operation, output)
                }
            }) { out ->
                codexAgentSkillsInstall(graph.context, skills, directory, 0, null, null, out)
            }
            assertEquals(CodexAgentCOperationValueKind.SKILL, result.valueKind)
            assertEquals(bundle.name, (result.value as AgentSkill).name)
        }
    }

    @Test
    fun skillsUninstallIsUnitAndConsumesCopiedInput(): Unit = catalogTest { graph ->
        val bundle = graph.protocol.createSkillBundle()
        val skills = graph.service(CodexAgentCHandleKind.SKILLS, ::codexAgentAgentSkills)
        val installed = memScoped {
            val directory = utf8(bundle.toString())
            graph.operation { out ->
                codexAgentSkillsInstall(graph.context, skills, directory, 0, null, null, out)
            }.value as AgentSkill
        }
        val input = graph.snapshot(CodexAgentCSkillSnapshot(installed))
        val result = graph.operation(afterStart = { graph.releaseSnapshot(input) }) { out ->
            codexAgentSkillsUninstall(graph.context, skills, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.NONE, result.valueKind)
        assertNull(result.value)
    }

    @Test
    fun hooksListReturnsFreshCatalog(): Unit = catalogTest { graph ->
        val hooks = graph.service(CodexAgentCHandleKind.HOOKS, ::codexAgentAgentHooks)
        val result = graph.operation(
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationHookCatalog(graph.context, operation, output)
                }
            },
        ) { out -> codexAgentHooksList(graph.context, hooks, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.HOOK_CATALOG, result.valueKind)
        val catalog = result.value as io.github.codex_agent_labs.codexagent.agent.AgentHookCatalog
        assertEquals(listOf("catalog-hook"), catalog.hooks.map(AgentHook::key))
    }

    @Test
    fun hooksInstallReturnsFreshOwnedHook(): Unit = catalogTest { graph ->
        val bundle = graph.protocol.createHookBundle()
        val hooks = graph.service(CodexAgentCHandleKind.HOOKS, ::codexAgentAgentHooks)
        memScoped {
            val directory = utf8(bundle.toString())
            val result = graph.operation(inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationHook(graph.context, operation, output)
                }
            }) { out ->
                codexAgentHooksInstall(graph.context, hooks, directory, 0, null, null, out)
            }
            assertEquals(CodexAgentCOperationValueKind.HOOK, result.valueKind)
            assertEquals("installed-${bundle.name}", (result.value as AgentHook).key)
        }
    }

    @Test
    fun hooksUninstallIsUnitAndConsumesCopiedInput(): Unit = catalogTest { graph ->
        val bundle = graph.protocol.createHookBundle()
        val hooks = graph.service(CodexAgentCHandleKind.HOOKS, ::codexAgentAgentHooks)
        val installed = memScoped {
            val directory = utf8(bundle.toString())
            graph.operation { out ->
                codexAgentHooksInstall(graph.context, hooks, directory, 0, null, null, out)
            }.value as AgentHook
        }
        val input = graph.snapshot(CodexAgentCHookSnapshot(installed))
        val result = graph.operation(afterStart = { graph.releaseSnapshot(input) }) { out ->
            codexAgentHooksUninstall(graph.context, hooks, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.NONE, result.valueKind)
    }

    @Test
    fun hooksTrustIsUnitAndCopiesHook(): Unit = catalogTest { graph ->
        val hooks = graph.service(CodexAgentCHandleKind.HOOKS, ::codexAgentAgentHooks)
        val input = graph.snapshot(CodexAgentCHookSnapshot(catalogHook("trusted-hook", "sha256:trusted")))
        val result = graph.operation(afterStart = { graph.releaseSnapshot(input) }) { out ->
            codexAgentHooksTrust(graph.context, hooks, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.NONE, result.valueKind)
        val write = graph.fixture.additionalRequests.single { it.first == "config/batchWrite" }.second
        assertTrue(write.toString().contains("sha256:trusted"))
    }

    @Test
    fun pluginsListCopiesFlagAndCatalog(): Unit = catalogTest { graph ->
        val plugins = graph.service(CodexAgentCHandleKind.PLUGINS, ::codexAgentAgentPlugins)
        graph.agent.plugins.list(forceReload = true)
        graph.fixture.additionalRequests.clear()
        val result = graph.operation(
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationPluginCatalog(graph.context, operation, output)
                }
            },
        ) { out -> codexAgentPluginsList(graph.context, plugins, 1, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.PLUGIN_CATALOG, result.valueKind)
        val catalog = result.value as io.github.codex_agent_labs.codexagent.agent.AgentPluginCatalog
        assertEquals(listOf("drive@market"), catalog.plugins.map { it.reference.id })
        val requests = graph.fixture.additionalRequests.filter { it.first in setOf("plugin/list", "plugin/installed") }
        assertEquals(listOf("plugin/list", "plugin/installed"), requests.map { it.first })
        val expectedParams = buildJsonObject {
            putJsonArray("cwds") { add(JsonPrimitive(graph.fixture.workspace.path)) }
        }
        assertEquals(listOf(expectedParams, expectedParams), requests.map { it.second })
    }

    @Test
    fun pluginsReadReturnsFreshDetail(): Unit = catalogTest { graph ->
        val plugins = graph.service(CodexAgentCHandleKind.PLUGINS, ::codexAgentAgentPlugins)
        val input = graph.pluginReference()
        val result = graph.operation(
            afterStart = { graph.releaseSnapshot(input) },
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationPluginDetail(graph.context, operation, output)
                }
            },
        ) { out ->
            codexAgentPluginsRead(graph.context, plugins, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.PLUGIN_DETAIL, result.valueKind)
        val detail = result.value as io.github.codex_agent_labs.codexagent.agent.AgentPluginDetail
        assertEquals("drive@market", detail.summary.reference.id)
    }

    @Test
    fun pluginsInstallReturnsFreshResult(): Unit = catalogTest { graph ->
        val plugins = graph.service(CodexAgentCHandleKind.PLUGINS, ::codexAgentAgentPlugins)
        val input = graph.pluginReference()
        val result = graph.operation(
            afterStart = { graph.releaseSnapshot(input) },
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationPluginInstallResult(graph.context, operation, output)
                }
            },
        ) { out ->
            codexAgentPluginsInstall(graph.context, plugins, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.PLUGIN_INSTALL_RESULT, result.valueKind)
        val installed = result.value as io.github.codex_agent_labs.codexagent.agent.AgentPluginInstallResult
        assertEquals(listOf("drive"), installed.connectorsNeedingAuthentication.map { it.id })
    }

    @Test
    fun pluginsUninstallIsUnitAndCopiesReference(): Unit = catalogTest { graph ->
        val plugins = graph.service(CodexAgentCHandleKind.PLUGINS, ::codexAgentAgentPlugins)
        val input = graph.pluginReference()
        val result = graph.operation(afterStart = { graph.releaseSnapshot(input) }) { out ->
            codexAgentPluginsUninstall(graph.context, plugins, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.NONE, result.valueKind)
        assertNull(result.value)
    }

    @Test
    fun connectorsListPreservesOrderAndDuplicates(): Unit = catalogTest { graph ->
        val connectors = graph.service(CodexAgentCHandleKind.CONNECTORS, ::codexAgentAgentConnectors)
        val result = graph.operation(inspect = { operation ->
            val count = alloc<ULongVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationConnectorsCount(graph.context, operation, count.ptr),
            )
            assertEquals(2uL, count.value)
            assertCatalogOperationSnapshot(graph.context) { output ->
                codexAgentOperationConnectorAt(graph.context, operation, 1uL, output)
            }
        }) { out ->
            codexAgentConnectorsList(graph.context, connectors, 1, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.CONNECTORS, result.valueKind)
        val values = result.value as List<*>
        assertEquals(listOf("drive", "drive"), values.map { (it as io.github.codex_agent_labs.codexagent.agent.AgentConnector).id })
        assertFalse(values[0] === values[1])
        val request = graph.fixture.additionalRequests.single { it.first == "app/list" }.second
        assertTrue(request.getValue("forceRefetch").jsonPrimitive.boolean)
    }

    @Test
    fun mcpServersListReturnsFreshOrderedServers(): Unit = catalogTest { graph ->
        graph.protocol.putMcp("alpha")
        graph.protocol.putMcp("beta")
        val servers = graph.service(CodexAgentCHandleKind.MCP_SERVERS, ::codexAgentAgentMcpServers)
        val result = graph.operation(
            inspect = { operation ->
                val count = alloc<ULongVar>()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationMcpServersCount(graph.context, operation, count.ptr),
                )
                assertEquals(2uL, count.value)
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationMcpServerAt(graph.context, operation, 1uL, output)
                }
            },
        ) { out -> codexAgentMcpServersList(graph.context, servers, null, null, out) }
        assertEquals(CodexAgentCOperationValueKind.MCP_SERVERS, result.valueKind)
        assertEquals(listOf("alpha", "beta"), (result.value as List<*>).map { (it as AgentMcpServer).name })
    }

    @Test
    fun mcpServersAddCopiesConfigurationAndReturnsServer(): Unit = catalogTest { graph ->
        val servers = graph.service(CodexAgentCHandleKind.MCP_SERVERS, ::codexAgentAgentMcpServers)
        val configuration = AgentMcpServerConfiguration(
            name = "added-rich",
            transport = AgentMcpTransport.Http(
                url = "https://mcp.example.com/rich",
                bearerTokenEnvironmentVariable = "MCP_TOKEN",
                headers = linkedMapOf("X-Header-A" to "alpha", "X-Header-B" to "beta"),
                environmentHeaders = linkedMapOf("Authorization" to "MCP_AUTH", "X-Env" to "MCP_ENV"),
                headersHelper = "mcp-headers-helper",
            ),
            authentication = AgentMcpAuthentication.CHAT_GPT,
            environmentId = "local",
            isEnabled = false,
            isRequired = true,
            supportsParallelToolCalls = true,
            omitToolsFrom = listOf(
                AgentMcpToolExposureSurface.CODE_MODE,
                AgentMcpToolExposureSurface.DIRECT,
            ),
            startupTimeoutSeconds = 0.25,
            toolTimeoutSeconds = 19.75,
            defaultToolApproval = AgentMcpToolApproval.WRITES,
            enabledTools = listOf("read", "read", "write"),
            disabledTools = emptyList(),
            scopes = listOf("scope-a", "scope-b"),
            oauth = AgentMcpOauthConfiguration("client-rich", 49152),
            oauthResource = "resource://rich",
            tools = linkedMapOf(
                "read" to AgentMcpToolConfiguration(AgentMcpToolApproval.PROMPT),
                "write" to AgentMcpToolConfiguration(AgentMcpToolApproval.APPROVE),
            ),
        )
        val input = graph.snapshot(
            CodexAgentCMcpServerConfigurationSnapshot(configuration),
        )
        val result = graph.operation(
            afterStart = { graph.releaseSnapshot(input) },
            inspect = { operation ->
                assertCatalogOperationSnapshot(graph.context) { output ->
                    codexAgentOperationMcpServer(graph.context, operation, output)
                }
            },
        ) { out ->
            codexAgentMcpServersAdd(graph.context, servers, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.MCP_SERVER, result.valueKind)
        val server = result.value as AgentMcpServer
        assertEquals("added-rich", server.name)
        assertEquals(configuration, server.configuration)
    }

    @Test
    fun mcpServersRemoveIsUnitAndCopiesServer(): Unit = catalogTest { graph ->
        graph.protocol.putMcp("remove-me")
        val servers = graph.service(CodexAgentCHandleKind.MCP_SERVERS, ::codexAgentAgentMcpServers)
        val input = graph.snapshot(
            CodexAgentCMcpServerSnapshot(
                AgentMcpServer(
                    "remove-me",
                    "remove-me",
                    AgentMcpAuthStatus.UNSUPPORTED,
                    graph.protocol.mcpConfiguration("remove-me"),
                    AgentResourceOrigin.USER,
                    true,
                ),
            ),
        )
        val result = graph.operation(afterStart = { graph.releaseSnapshot(input) }) { out ->
            codexAgentMcpServersRemove(graph.context, servers, input, null, null, out)
        }
        assertEquals(CodexAgentCOperationValueKind.NONE, result.valueKind)
        assertFalse(graph.protocol.hasMcp("remove-me"))
    }

    @Test
    fun operationsFailClosedCancelAndHoldTargetLease(): Unit = runBlocking {
        val protocol = CatalogProtocol()
        val graph = createCatalogGraph(protocol)
        val otherContext = handleRegistry.createContext().requiredCatalogValue()
        try {
            memScoped {
                val models = graph.service(CodexAgentCHandleKind.MODELS, ::codexAgentAgentModels)
                val skills = graph.service(CodexAgentCHandleKind.SKILLS, ::codexAgentAgentSkills)
                val output = emptyHandle().also { it.value = graph.agentHandle }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentModelsList(graph.context, models, null, null, output.ptr),
                )
                assertEquals(graph.agentHandle, output.value)
                output.value = null
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentModelsList(otherContext, models, null, null, output.ptr),
                )
                assertNull(output.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentModelsList(graph.context, skills, null, null, output.ptr),
                )
                assertNull(output.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentModelsList(graph.context, null, null, null, output.ptr),
                )
                assertNull(output.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentModelsResolve(graph.context, models, 99, null, null, output.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentSkillsList(graph.context, skills, 2, null, null, output.ptr),
                )

                protocol.malformedMethod = "model/list"
                val failure = graph.operation(expectedStatus = CODEX_AGENT_STATUS_OPERATION_FAILED) { out ->
                    codexAgentModelsList(graph.context, models, null, null, out)
                }
                assertEquals(CODEX_AGENT_STATUS_OPERATION_FAILED, failure.status)
                assertNotNull(failure.failure)

                protocol.malformedMethod = null
                protocol.blockedMethod = "model/list"
                val operation = emptyHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentModelsList(graph.context, models, null, null, operation.ptr),
                )
                graph.releaseService(models, CodexAgentCHandleKind.MODELS)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(graph.context, operation.value))
                val cancelled = awaitCatalogResult(graph.context, assertNotNull(operation.value))
                assertEquals(CODEX_AGENT_STATUS_CANCELLED, cancelled.status)
                destroyCatalogOperation(graph.context, operation.ptr)

                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    handleRegistry.invalidateChildren(
                        graph.context,
                        graph.agentHandle,
                        CodexAgentCHandleKind.AGENT,
                    ),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentSkillsList(graph.context, skills, 0, null, null, output.ptr),
                )
                assertNull(output.value)
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            graph.close()
        }
    }
}

private data class CatalogGraph(
    val fixture: NativeCodexBehaviorFixture,
    val protocol: CatalogProtocol,
    val runtime: CodexAgentCContextRuntime,
    val context: COpaquePointer,
    val hostHandle: COpaquePointer,
    val agentHandle: COpaquePointer,
    val host: CodexAgentCHost,
    val agent: CodexAgent,
) {
    private val services = mutableMapOf<COpaquePointer, CodexAgentCHandleKind>()
    private val snapshots = mutableSetOf<COpaquePointer>()

    fun service(kind: CodexAgentCHandleKind, accessor: CatalogServiceAccessor): COpaquePointer = memScoped {
        val output = emptyHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, accessor(context, agentHandle, output.ptr))
        assertNotNull(output.value).also { services[it] = kind }
    }

    fun snapshot(value: CodexAgentCSnapshot): COpaquePointer = createSnapshot(context, value).requiredCatalogValue()
        .also(snapshots::add)

    fun pluginReference(): COpaquePointer = snapshot(
        CodexAgentCPluginReferenceSnapshot(
            AgentPluginReference("drive@market", "drive", "market", remotePluginId = "remote-drive"),
        ),
    )

    suspend fun operation(
        expectedStatus: Int = CODEX_AGENT_STATUS_OK,
        afterStart: () -> Unit = {},
        inspect: MemScope.(COpaquePointer) -> Unit = {},
        start: (CPointer<COpaquePointerVar>) -> Int,
    ): CodexAgentCOperationResult = memScoped {
        val output = emptyHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, start(output.ptr))
        afterStart()
        val operation = assertNotNull(output.value)
        val result = awaitCatalogResult(context, operation)
        val terminal = alloc<IntVar>()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationResult(context, operation, terminal.ptr))
        assertEquals(result.status, terminal.value)
        assertEquals(expectedStatus, result.status)
        inspect(operation)
        destroyCatalogOperation(context, output.ptr)
        result
    }

    fun releaseSnapshot(snapshot: COpaquePointer) {
        if (snapshots.remove(snapshot)) {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.release(context, snapshot, CodexAgentCHandleKind.SNAPSHOT))
        }
    }

    fun releaseService(service: COpaquePointer, kind: CodexAgentCHandleKind) {
        if (services.remove(service) != null) {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.release(context, service, kind))
        }
    }

    suspend fun close() {
        services.toList().forEach { (handle, kind) ->
            handleRegistry.release(context, handle, kind)
        }
        services.clear()
        snapshots.toList().forEach { handle ->
            handleRegistry.release(context, handle, CodexAgentCHandleKind.SNAPSHOT)
        }
        snapshots.clear()
        host.core.close()
        handleRegistry.release(context, agentHandle, CodexAgentCHandleKind.AGENT)
        handleRegistry.semanticClose(context, hostHandle, CodexAgentCHandleKind.HOST) { CODEX_AGENT_STATUS_OK }
        handleRegistry.release(context, hostHandle, CodexAgentCHandleKind.HOST)
        assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(context))
        runtime.cancel()
        protocol.close()
    }
}

private class CatalogProtocol {
    var blockedMethod: String? = null
    var malformedMethod: String? = null
    private val mcpConfigurations = linkedMapOf<String, JsonObject>()
    private val createdPaths = mutableSetOf<Path>()
    private var configVersion = 1

    suspend fun response(method: String, params: JsonObject): JsonObject? {
        if (method == blockedMethod) return null
        if (method == malformedMethod) return buildJsonObject {}
        return when (method) {
            "model/list" -> modelResponse()
            "config/read" -> mcpConfigurationResponse()
            "skills/list" -> skillsResponse()
            "hooks/list" -> hooksResponse()
            "config/batchWrite" -> batchWrite(params)
            "plugin/list" -> pluginList(installed = false)
            "plugin/installed" -> pluginList(installed = true)
            "plugin/read" -> pluginDetail()
            "plugin/install" -> buildJsonObject {
                put("authPolicy", "ON_INSTALL")
                putJsonArray("appsNeedingAuth") { add(connector()) }
            }
            "plugin/uninstall", "config/mcpServer/reload" -> buildJsonObject {}
            "app/list" -> buildJsonObject {
                putJsonArray("data") { add(connector()); add(connector()) }
            }
            "mcpServerStatus/list" -> buildJsonObject {
                putJsonArray("data") {
                    mcpConfigurations.keys.forEach { name ->
                        add(buildJsonObject {
                            put("name", name)
                            put("authStatus", "unsupported")
                            putJsonArray("resourceTemplates") {}
                            putJsonArray("resources") {}
                            putJsonObject("tools") {}
                        })
                    }
                }
            }
            else -> null
        }
    }

    fun createSkillBundle(): Path {
        val root = uniquePath("skill")
        FileSystem.SYSTEM.createDirectories(root)
        FileSystem.SYSTEM.write(root / "SKILL.md") {
            writeUtf8("---\nname: ${root.name}\ndescription: Catalog skill\n---\n")
        }
        createdPaths += root
        createdPaths += USER_SKILLS_ROOT / root.name
        return root
    }

    fun createHookBundle(): Path {
        val root = uniquePath("hook")
        FileSystem.SYSTEM.createDirectories(root)
        FileSystem.SYSTEM.write(root / "hooks.json") {
            writeUtf8("""{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"true"}]}]}}""")
        }
        createdPaths += root
        createdPaths += USER_HOOK_ASSETS / root.name
        createdPaths += USER_HOOKS_FILE
        return root
    }

    fun putMcp(name: String) {
        mcpConfigurations[name] = mcpJson(name)
    }

    fun hasMcp(name: String): Boolean = name in mcpConfigurations

    fun mcpConfiguration(name: String): AgentMcpServerConfiguration =
        AgentMcpServerConfiguration(name, AgentMcpTransport.Stdio(name))

    fun close() {
        createdPaths.sortedByDescending { it.toString().length }.forEach {
            runCatching { FileSystem.SYSTEM.deleteRecursively(it, mustExist = false) }
        }
    }

    private fun uniquePath(kind: String): Path =
        "/tmp/codex-agent-catalog-$kind-${Random.nextLong().toULong()}".toPath()

    private fun skillsResponse(): JsonObject = buildJsonObject {
        putJsonArray("data") {
            add(buildJsonObject {
                put("cwd", "/workspace")
                putJsonArray("errors") {}
                putJsonArray("skills") {
                    add(skillEntry("catalog-read", CATALOG_SKILL_PATH, "system"))
                    FileSystem.SYSTEM.listOrNull(USER_SKILLS_ROOT).orEmpty().forEach { directory ->
                        val manifest = directory / "SKILL.md"
                        if (FileSystem.SYSTEM.metadata(manifest)?.isRegularFile == true) {
                            add(skillEntry(directory.name, manifest, "user"))
                        }
                    }
                }
            })
        }
    }

    private fun hooksResponse(): JsonObject = buildJsonObject {
        putJsonArray("data") {
            add(buildJsonObject {
                put("cwd", "/workspace")
                putJsonArray("warnings") {}
                putJsonArray("errors") {}
                putJsonArray("hooks") {
                    add(hookEntry("catalog-hook", "/workspace/.codex/hooks.json"))
                    FileSystem.SYSTEM.listOrNull(USER_HOOK_ASSETS).orEmpty().forEach { directory ->
                        if (FileSystem.SYSTEM.metadata(directory / ".codex-agent-owned.json")?.isRegularFile == true) {
                            add(hookEntry("installed-${directory.name}", USER_HOOKS_FILE.toString()))
                        }
                    }
                }
            })
        }
    }

    private fun batchWrite(params: JsonObject): JsonObject {
        val edit = params.getValue("edits").jsonArray.single().jsonObject
        val keyPath = edit.getValue("keyPath").jsonPrimitive.content
        if (keyPath.startsWith("mcp_servers.")) {
            val name = keyPath.removePrefix("mcp_servers.").removeSurrounding("\"")
            val value = edit.getValue("value")
            if (value == JsonNull) mcpConfigurations.remove(name) else mcpConfigurations[name] = value.jsonObject
        }
        configVersion += 1
        return buildJsonObject {
            put("filePath", "/tmp/codex-native-fixture/config.toml")
            put("status", "ok")
            put("version", configVersion.toString())
        }
    }

    private fun mcpConfigurationResponse(): JsonObject = buildJsonObject {
        putJsonObject("config") {
            put("model", "preferred")
            put("model_reasoning_effort", "preferred-effort")
            put("service_tier", "preferred-tier")
            putJsonObject("mcp_servers") {
                mcpConfigurations.forEach { (name, configuration) -> put(name, configuration) }
            }
        }
        putJsonObject("origins") {
            mcpConfigurations.keys.forEach { name ->
                putJsonObject("mcp_servers.$name.command") {
                    putJsonObject("name") { put("type", "user"); put("file", "/tmp/config.toml") }
                    put("version", configVersion.toString())
                }
            }
        }
        putJsonArray("layers") {
            add(buildJsonObject {
                putJsonObject("config") {
                    putJsonObject("mcp_servers") {
                        mcpConfigurations.forEach { (name, configuration) -> put(name, configuration) }
                    }
                }
                putJsonObject("name") { put("type", "user"); put("file", "/tmp/config.toml") }
                put("version", configVersion.toString())
            })
        }
    }
}

private suspend fun createCatalogGraph(protocol: CatalogProtocol = CatalogProtocol()): CatalogGraph {
    FileSystem.SYSTEM.createDirectories(CATALOG_SKILL_PATH.parent!!)
    FileSystem.SYSTEM.write(CATALOG_SKILL_PATH) { writeUtf8(CATALOG_SKILL_TEXT) }
    val fixture = NativeCodexBehaviorFixture(
        features = setOf(
            CodexRuntimeFeature.SKILLS,
            CodexRuntimeFeature.HOOKS,
            CodexRuntimeFeature.PLUGINS,
            CodexRuntimeFeature.CONNECTORS,
            CodexRuntimeFeature.MCP_SERVERS,
        ),
        additionalResponse = protocol::response,
    )
    val runtime = CodexAgentCContextRuntime()
    val context = handleRegistry.createContext(runtime).requiredCatalogValue()
    val platform = object : CodexPlatform by fixture.platform {
        override suspend fun prepare(workspace: CodexWorkspace) = fixture.platform.prepare(workspace).let { prepared ->
            prepared.copy(
                installationRoots = prepared.installationRoots.copy(
                    userSkillsRoot = USER_SKILLS_ROOT,
                    userHooksFile = USER_HOOKS_FILE,
                ),
            )
        }
    }
    val host = CodexAgentCHost(CodexHost(platform, fixture.clientInfo), runtime)
    val hostHandle = handleRegistry.createEntry(context, CodexAgentCHandleKind.HOST, host).requiredCatalogValue()
    host.core.selectWorkspace(CodexPathWorkspaceSelection(fixture.workspace.path))
    val agent = (host.core.lifecycleState.value as CodexHostState.Ready).agent
    val agentHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.AGENT,
        CodexAgentCAgent(agent, host),
        hostHandle,
        CodexAgentCHandleKind.HOST,
    ).requiredCatalogValue()
    return CatalogGraph(fixture, protocol, runtime, context, hostHandle, agentHandle, host, agent)
}

private fun catalogTest(block: suspend (CatalogGraph) -> Unit): Unit = runBlocking {
    val graph = createCatalogGraph()
    try {
        block(graph)
    } finally {
        graph.close()
    }
}

private suspend fun awaitCatalogResult(
    context: COpaquePointer,
    operation: COpaquePointer,
): CodexAgentCOperationResult = withTimeout(5_000) {
    while (true) {
        val result = queryCodexAgentCOperation(context, operation)
        when (result.status) {
            CODEX_AGENT_STATUS_OK -> return@withTimeout assertNotNull(result.value)
            CODEX_AGENT_STATUS_NOT_READY -> yield()
            else -> error("operation query failed with ${result.status}")
        }
    }
    error("unreachable")
}

private suspend fun destroyCatalogOperation(context: COpaquePointer, operation: CPointer<COpaquePointerVar>) {
    withTimeout(5_000) {
        while (true) {
            when (val status = codexAgentOperationDestroy(context, operation)) {
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                CODEX_AGENT_STATUS_BUSY -> yield()
                else -> error("operation destroy failed with $status")
            }
        }
    }
    assertNull(operation.pointed.value)
}

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredCatalogValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}

private fun MemScope.emptyHandle(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.assertCatalogOperationSnapshot(
    context: COpaquePointer,
    getter: (CPointer<COpaquePointerVar>) -> Int,
) {
    val output = emptyHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, getter(output.ptr))
    assertNotNull(output.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, output.ptr))
    assertNull(output.value)
}

private fun MemScope.copyCatalogOperationString(context: COpaquePointer, operation: COpaquePointer): String {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        codexAgentOperationStringCopy(context, operation, null, 0uL, required.ptr),
    )
    val bytes = allocArray<UByteVar>(required.value.toInt())
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentOperationStringCopy(context, operation, bytes, required.value, required.ptr),
    )
    return ByteArray(required.value.toInt()) { bytes[it].toByte() }.decodeToString()
}

private fun MemScope.utf8(value: String): CPointer<codex_agent_string_view> {
    val encoded = value.encodeToByteArray()
    val bytes = if (encoded.isEmpty()) null else allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> checkNotNull(bytes)[index] = byte.toUByte() }
    return alloc<codex_agent_string_view>().also {
        it.data = bytes
        it.size = encoded.size.toULong()
    }.ptr
}

private fun catalogModel(id: String, withTier: Boolean = true): AgentModel = AgentModel(
    id,
    id,
    "model",
    listOf("first-effort", "preferred-effort", "default-effort"),
    "default-effort",
    true,
    if (withTier) {
        listOf(
            AgentServiceTier("first-tier", "First", "First tier"),
            AgentServiceTier("preferred-tier", "Preferred", "Preferred tier"),
            AgentServiceTier("default-tier", "Default", "Default tier"),
        )
    } else {
        emptyList()
    },
    if (withTier) "default-tier" else null,
)

private fun catalogHook(key: String, hash: String): AgentHook = AgentHook(
    key,
    hash,
    true,
    "stop",
    AgentHookHandler.Command("true", false),
    false,
    "USER",
    USER_HOOKS_FILE.toString(),
    10,
    AgentHookTrustStatus.UNTRUSTED,
)

private fun modelResponse(): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(modelEntry("first", false))
        add(modelEntry("preferred", false))
        add(modelEntry("default", true))
        add(modelEntry("duplicate", false))
        add(modelEntry("duplicate", false))
    }
}

private fun modelEntry(id: String, isDefault: Boolean): JsonObject = buildJsonObject {
    put("id", "$id-wire")
    put("model", id)
    put("displayName", id)
    put("description", "model")
    put("hidden", false)
    put("defaultReasoningEffort", "default-effort")
    put("isDefault", isDefault)
    putJsonArray("supportedReasoningEfforts") {
        add(buildJsonObject { put("reasoningEffort", "first-effort"); put("description", "First") })
        add(buildJsonObject { put("reasoningEffort", "preferred-effort"); put("description", "Preferred") })
        add(buildJsonObject { put("reasoningEffort", "default-effort"); put("description", "Default") })
    }
    putJsonArray("serviceTiers") {
        add(buildJsonObject { put("id", "first-tier"); put("name", "First"); put("description", "First tier") })
        add(buildJsonObject {
            put("id", "preferred-tier")
            put("name", "Preferred")
            put("description", "Preferred tier")
        })
        add(buildJsonObject { put("id", "default-tier"); put("name", "Default"); put("description", "Default tier") })
    }
    put("defaultServiceTier", "default-tier")
}

private fun skillEntry(name: String, path: Path, scope: String): JsonObject = buildJsonObject {
    put("name", name)
    put("description", name)
    put("enabled", true)
    put("path", path.toString())
    put("scope", scope)
}

private fun hookEntry(key: String, sourcePath: String): JsonObject = buildJsonObject {
    put("currentHash", "sha256:$key")
    put("displayOrder", 0)
    put("enabled", true)
    put("eventName", "stop")
    put("handlerType", "command")
    put("isManaged", false)
    put("key", key)
    put("source", if (sourcePath == USER_HOOKS_FILE.toString()) "user" else "project")
    put("sourcePath", sourcePath)
    put("timeoutSec", 10)
    put("trustStatus", "untrusted")
    put("command", "true")
}

private fun pluginList(installed: Boolean): JsonObject = buildJsonObject {
    putJsonArray("marketplaceLoadErrors") {}
    putJsonArray("marketplaces") {
        add(buildJsonObject {
            put("name", "market")
            putJsonArray("plugins") { add(pluginSummary(installed)) }
        })
    }
}

private fun pluginSummary(installed: Boolean): JsonObject = buildJsonObject {
    put("id", "drive@market")
    put("remotePluginId", "remote-drive")
    put("name", "drive")
    put("installed", installed)
    put("enabled", true)
    put("installPolicy", "AVAILABLE")
    put("authPolicy", "ON_INSTALL")
    put("availability", "AVAILABLE")
    putJsonObject("source") { put("type", "remote") }
    putJsonObject("interface") {
        put("displayName", "Drive")
        put("shortDescription", "Drive files")
        putJsonArray("capabilities") { add(JsonPrimitive("search")) }
        putJsonArray("screenshotUrls") {}
        putJsonArray("screenshots") {}
    }
}

private fun pluginDetail(): JsonObject = buildJsonObject {
    putJsonObject("plugin") {
        put("marketplaceName", "market")
        put("summary", pluginSummary(installed = true))
        putJsonArray("skills") {}
        putJsonArray("apps") { add(connector()) }
        putJsonArray("appTemplates") {}
        putJsonArray("mcpServers") { add(JsonPrimitive("drive")) }
        putJsonArray("hooks") {}
    }
}

private fun connector(): JsonObject = buildJsonObject {
    put("id", "drive")
    put("name", "Drive")
    put("description", "Files")
    put("isAccessible", false)
    put("isEnabled", true)
    putJsonArray("pluginDisplayNames") { add(JsonPrimitive("Drive")) }
}

private fun mcpJson(name: String): JsonObject = buildJsonObject {
    put("command", name)
    putJsonArray("args") {}
}

private typealias CatalogServiceAccessor = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<COpaquePointerVar>?,
) -> Int

private val CATALOG_SKILL_PATH = "/tmp/codex-agent-catalog-read/SKILL.md".toPath()
private const val CATALOG_SKILL_TEXT = "catalog skill"
private val USER_SKILLS_ROOT = "/private/tmp/codex-native-fixture/skills".toPath()
private val USER_HOOKS_FILE = "/private/tmp/codex-native-fixture/hooks.json".toPath()
private val USER_HOOK_ASSETS = "/private/tmp/codex-native-fixture/.codex-agent-hooks".toPath()
