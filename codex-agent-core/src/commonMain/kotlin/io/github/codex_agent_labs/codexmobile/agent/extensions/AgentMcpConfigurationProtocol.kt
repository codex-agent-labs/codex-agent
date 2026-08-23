package io.github.codex_agent_labs.codexmobile.agent

import io.github.codex_agent_labs.codexmobile.appserver.client.AppServerRpcException
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.AppServerClientMethods
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigBatchWriteParams
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigEdit
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceEnterpriseManagedConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceLegacyManagedConfigTomlFromFileConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceLegacyManagedConfigTomlFromMdmConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceMdmConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceProjectConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceSystemConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerSourceUserConfigLayerSource
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigReadParams
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigReadResponse
import io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.MergeStrategy
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

internal suspend fun CodexAgentClient.listMcpServersWithConfigurationAction(
    workingDirectory: String,
): List<AgentMcpServer> {
    val statuses = listMcpServerStatusesAction().associateBy(AgentMcpServer::name)
    val snapshot = readMcpSnapshot(workingDirectory)
    return (statuses.keys + snapshot.configurations.keys).sorted().map { name ->
        val status = statuses[name] ?: AgentMcpServer(name, name, AgentMcpAuthStatus.UNKNOWN)
        val origin = snapshot.originOf(name)
        status.copy(
            configuration = snapshot.configurations[name],
            origin = origin,
            canRemove = snapshot.userValue(name) != null,
        )
    }
}

internal suspend fun CodexAgentClient.addMcpServerAction(
    configuration: AgentMcpServerConfiguration,
    workingDirectory: String,
): AgentMcpServer {
    val snapshot = readMcpSnapshot(workingDirectory)
    require(configuration.name !in snapshot.configuredNames) {
        "MCP server '${configuration.name}' already exists"
    }
    require(listMcpServerStatusesAction().none { it.name == configuration.name }) {
        "MCP server '${configuration.name}' already exists"
    }
    val writtenValue = configuration.toJson()
    val writtenVersion = try {
        writeMcpConfiguration(
            name = configuration.name,
            value = writtenValue,
            expectedVersion = snapshot.userVersion,
        )
    } catch (error: Throwable) {
        if (error is AppServerRpcException) throw error
        recoverAmbiguousMcpWrite(
            name = configuration.name,
            previousUserValue = snapshot.userValue(configuration.name),
            writtenUserValue = writtenValue,
            workingDirectory = workingDirectory,
            description = "MCP server '${configuration.name}' installation",
            error = error,
        )
    }
    try {
        connection.request(AppServerClientMethods.ConfigMcpServerReload, Unit)
        check(readMcpSnapshot(workingDirectory).userValue(configuration.name) == writtenValue) {
            "Codex did not retain MCP server '${configuration.name}' in the active user configuration"
        }
        return listMcpServersWithConfigurationAction(workingDirectory)
            .singleOrNull { it.name == configuration.name }
            ?: error("Codex did not discover MCP server '${configuration.name}'")
    } catch (error: Throwable) {
        rollbackMcpConfiguration(
            name = configuration.name,
            previousUserValue = snapshot.userValue(configuration.name),
            expectedVersion = writtenVersion,
            workingDirectory = workingDirectory,
            description = "MCP server '${configuration.name}' installation",
            error = error,
        )
    }
}

internal suspend fun CodexAgentClient.removeMcpServerAction(
    server: AgentMcpServer,
    workingDirectory: String,
) {
    val snapshot = readMcpSnapshot(workingDirectory)
    require(server.name in snapshot.configuredNames) { "MCP server '${server.name}' is unavailable" }
    require(snapshot.userValue(server.name) != null) {
        "Only MCP servers in the active user configuration can be removed"
    }
    val writtenVersion = try {
        writeMcpConfiguration(server.name, JsonNull, snapshot.userVersion)
    } catch (error: Throwable) {
        if (error is AppServerRpcException) throw error
        recoverAmbiguousMcpWrite(
            name = server.name,
            previousUserValue = snapshot.userValue(server.name),
            writtenUserValue = null,
            workingDirectory = workingDirectory,
            description = "MCP server '${server.name}' removal",
            error = error,
        )
    }
    try {
        connection.request(AppServerClientMethods.ConfigMcpServerReload, Unit)
        check(readMcpSnapshot(workingDirectory).userValue(server.name) == null) {
            "Codex still reports MCP server '${server.name}' in the active user configuration"
        }
    } catch (error: Throwable) {
        rollbackMcpConfiguration(
            name = server.name,
            previousUserValue = snapshot.userValue(server.name),
            expectedVersion = writtenVersion,
            workingDirectory = workingDirectory,
            description = "MCP server '${server.name}' removal",
            error = error,
        )
    }
}

private suspend fun CodexAgentClient.readMcpSnapshot(workingDirectory: String): McpSnapshot {
    val response = connection.request(
        AppServerClientMethods.ConfigRead,
        ConfigReadParams(cwd = workingDirectory, includeLayers = true),
    )
    val configured = response.config.jsonObject["mcp_servers"]
        ?.let { it as? JsonObject }
        .orEmpty()
    val configurations = configured.mapNotNull { (name, value) ->
            runCatching { value.jsonObject.toMcpConfiguration(name) }.getOrNull()?.let { name to it }
        }
        .toMap()
    val userLayer = response.layers.orEmpty()
        .firstOrNull { it.name is ConfigLayerSourceUserConfigLayerSource }
    val userConfigurations = (userLayer?.config as? JsonObject)?.get("mcp_servers") as? JsonObject
    return McpSnapshot(
        configurations = configurations,
        configuredNames = configured.keys,
        origins = response.origins,
        userConfigurations = userConfigurations.orEmpty(),
        userVersion = userLayer?.version,
    )
}

private suspend fun CodexAgentClient.writeMcpConfiguration(
    name: String,
    value: JsonElement,
    expectedVersion: String?,
): String = connection.request(
    AppServerClientMethods.ConfigBatchWrite,
    ConfigBatchWriteParams(
        edits = listOf(
            ConfigEdit(
                keyPath = "mcp_servers.${name.asConfigKeyPathSegment()}",
                mergeStrategy = MergeStrategy.REPLACE,
                value = value,
            ),
        ),
        expectedVersion = expectedVersion,
        reloadUserConfig = true,
    ),
).version

private suspend fun CodexAgentClient.recoverAmbiguousMcpWrite(
    name: String,
    previousUserValue: JsonElement?,
    writtenUserValue: JsonElement?,
    workingDirectory: String,
    description: String,
    error: Throwable,
): Nothing {
    val recoveryFailure = mutableListOf<Throwable>()
    val current = withContext(NonCancellable) {
        runCatching { readMcpSnapshot(workingDirectory) }
            .onFailure(recoveryFailure::add)
            .getOrNull()
    } ?: throwPartialMcpChange(description, error, recoveryFailure)
    return when (current.userValue(name)) {
        previousUserValue -> throwRestoredMcpFailure(description, error)
        writtenUserValue -> current.userVersion?.let { version ->
            rollbackMcpConfiguration(
                name = name,
                previousUserValue = previousUserValue,
                expectedVersion = version,
                workingDirectory = workingDirectory,
                description = description,
                error = error,
            )
        } ?: throwPartialMcpChange(
            description,
            error,
            listOf(IllegalStateException("$description recovery could not prove the active user version")),
        )
        else -> throwPartialMcpChange(
            description,
            error,
            listOf(IllegalStateException("$description recovery found a concurrent configuration change")),
        )
    }
}

private suspend fun CodexAgentClient.rollbackMcpConfiguration(
    name: String,
    previousUserValue: JsonElement?,
    expectedVersion: String,
    workingDirectory: String,
    description: String,
    error: Throwable,
): Nothing {
    val rollbackFailures = mutableListOf<Throwable>()
    val rollbackIncomplete = withContext(NonCancellable) {
        runCatching { writeMcpConfiguration(name, previousUserValue ?: JsonNull, expectedVersion) }
            .exceptionOrNull()?.let(rollbackFailures::add)
        val reloadFailed = runCatching {
            connection.request(AppServerClientMethods.ConfigMcpServerReload, Unit)
        }.exceptionOrNull()?.also(rollbackFailures::add) != null
        val restoreFailed = runCatching {
            check(readMcpSnapshot(workingDirectory).userValue(name) == previousUserValue) {
                "$description rollback did not restore the prior user configuration"
            }
        }.exceptionOrNull()?.also(rollbackFailures::add) != null
        reloadFailed || restoreFailed
    }
    if (rollbackIncomplete) {
        throwPartialMcpChange(description, error, rollbackFailures)
    }
    throwRestoredMcpFailure(description, error, rollbackFailures)
}

private fun throwRestoredMcpFailure(
    description: String,
    error: Throwable,
    rollbackFailures: List<Throwable> = emptyList(),
): Nothing {
    if (error is CancellationException) {
        rollbackFailures.forEach(error::addSuppressed)
        throw error
    }
    throw AgentResourceInstallationException(
        "$description failed; the prior configuration was restored",
        error,
    ).apply { rollbackFailures.forEach(this::addSuppressed) }
}

private fun throwPartialMcpChange(
    description: String,
    error: Throwable,
    rollbackFailures: List<Throwable>,
): Nothing = throw AgentResourcePartialChangeException(
    "$description failed and rollback was incomplete",
    error,
).apply { rollbackFailures.forEach(this::addSuppressed) }

private data class McpSnapshot(
    val configurations: Map<String, AgentMcpServerConfiguration>,
    val configuredNames: Set<String>,
    val origins: Map<String, io.github.codex_agent_labs.codexmobile.appserver.protocol.generated.ConfigLayerMetadata>,
    val userConfigurations: Map<String, JsonElement>,
    val userVersion: String?,
) {
    fun userValue(name: String): JsonElement? = userConfigurations[name]

    fun originOf(name: String): AgentResourceOrigin {
        val prefix = "mcp_servers.$name"
        val sources = origins.filterKeys { it == prefix || it.startsWith("$prefix.") }
            .values.map { it.name }
        if (sources.isEmpty()) return AgentResourceOrigin.UNKNOWN
        val mapped = sources.map(ConfigLayerSource::toResourceOrigin).toSet()
        return when {
            mapped == setOf(AgentResourceOrigin.USER) -> AgentResourceOrigin.USER
            mapped == setOf(AgentResourceOrigin.WORKSPACE) -> AgentResourceOrigin.WORKSPACE
            AgentResourceOrigin.MANAGED in mapped -> AgentResourceOrigin.MANAGED
            else -> AgentResourceOrigin.UNKNOWN
        }
    }
}

private fun ConfigLayerSource.toResourceOrigin(): AgentResourceOrigin = when (this) {
    is ConfigLayerSourceUserConfigLayerSource -> AgentResourceOrigin.USER
    is ConfigLayerSourceProjectConfigLayerSource -> AgentResourceOrigin.WORKSPACE
    is ConfigLayerSourceMdmConfigLayerSource,
    is ConfigLayerSourceSystemConfigLayerSource,
    is ConfigLayerSourceEnterpriseManagedConfigLayerSource,
    is ConfigLayerSourceLegacyManagedConfigTomlFromFileConfigLayerSource,
    is ConfigLayerSourceLegacyManagedConfigTomlFromMdmConfigLayerSource,
    -> AgentResourceOrigin.MANAGED
    else -> AgentResourceOrigin.UNKNOWN
}

private fun String.asConfigKeyPathSegment(): String = buildString(length + 2) {
    append('"')
    this@asConfigKeyPathSegment.forEach { character ->
        if (character == '\\' || character == '"') append('\\')
        append(character)
    }
    append('"')
}

internal fun AgentMcpServerConfiguration.toJson(): JsonObject = buildJsonObject {
    when (val value = transport) {
        is AgentMcpTransport.Stdio -> {
            put("command", value.command)
            put("args", value.arguments.toJsonArray())
            value.workingDirectory?.let { put("cwd", it) }
            value.environment?.let { put("env", it.toJsonObject()) }
            if (value.forwardedEnvironment.isNotEmpty()) {
                put("env_vars", buildJsonArray {
                    value.forwardedEnvironment.forEach { variable ->
                        if (variable.source == null) {
                            add(JsonPrimitive(variable.name))
                        } else {
                            add(buildJsonObject {
                                put("name", variable.name)
                                put("source", variable.source.name.lowercase())
                            })
                        }
                    }
                })
            }
        }
        is AgentMcpTransport.Http -> {
            put("url", value.url)
            value.bearerTokenEnvironmentVariable?.let { put("bearer_token_env_var", it) }
            value.headers?.let { put("http_headers", it.toJsonObject()) }
            value.environmentHeaders?.let { put("env_http_headers", it.toJsonObject()) }
            value.headersHelper?.let { put("http_headers_helper", it) }
            if (authentication == AgentMcpAuthentication.CHAT_GPT) put("auth", "chatgpt")
            oauth?.let { oauth ->
                put("oauth", buildJsonObject {
                    oauth.clientId?.let { put("client_id", it) }
                    oauth.callbackPort?.let { put("callback_port", JsonPrimitive(it)) }
                })
            }
            oauthResource?.let { put("oauth_resource", it) }
        }
    }
    put("environment_id", environmentId)
    put("enabled", isEnabled)
    put("required", isRequired)
    put("supports_parallel_tool_calls", supportsParallelToolCalls)
    omitToolsFrom?.let { values ->
        put("omit_tools_from", values.map { it.name.lowercase() }.toJsonArray())
    }
    startupTimeoutSeconds?.let { put("startup_timeout_sec", it) }
    toolTimeoutSeconds?.let { put("tool_timeout_sec", it) }
    defaultToolApproval?.let { put("default_tools_approval_mode", it.name.lowercase()) }
    enabledTools?.let { put("enabled_tools", it.toJsonArray()) }
    disabledTools?.let { put("disabled_tools", it.toJsonArray()) }
    scopes?.let { put("scopes", it.toJsonArray()) }
    if (tools.isNotEmpty()) {
        put("tools", buildJsonObject {
            tools.forEach { (name, value) ->
                put(name, buildJsonObject {
                    value.approval?.let { put("approval_mode", it.name.lowercase()) }
                })
            }
        })
    }
}

internal fun JsonObject.toMcpConfiguration(name: String): AgentMcpServerConfiguration {
    val command = string("command")
    val url = string("url")
    require((command == null) != (url == null)) { "MCP server '$name' must configure exactly one transport" }
    fun rejectFields(transport: String, vararg fields: String) {
        fields.firstOrNull { get(it) != null && get(it) != JsonNull }?.let { field ->
            throw IllegalArgumentException("$field is not supported for $transport")
        }
    }
    val transport = command?.let {
        rejectFields(
            "stdio",
            "url",
            "bearer_token",
            "bearer_token_env_var",
            "http_headers",
            "env_http_headers",
            "http_headers_helper",
            "auth",
            "oauth",
            "oauth_resource",
        )
        AgentMcpTransport.Stdio(
            command = it,
            arguments = strings("args").orEmpty(),
            workingDirectory = string("cwd"),
            environment = stringMap("env"),
            forwardedEnvironment = (get("env_vars") as? JsonArray).orEmpty().mapNotNull { item ->
                when (item) {
                    is JsonPrimitive -> item.contentOrNull?.let(::AgentMcpEnvironmentVariable)
                    is JsonObject -> item.string("name")?.let { variableName ->
                        AgentMcpEnvironmentVariable(
                            variableName,
                            item.string("source")?.let { enumValueOf<AgentMcpEnvironmentSource>(it.uppercase()) },
                        )
                    }
                    else -> null
                }
            },
        )
    } ?: run {
        rejectFields("streamable_http", "command", "args", "env", "env_vars", "cwd", "bearer_token")
        AgentMcpTransport.Http(
            url = requireNotNull(url),
            bearerTokenEnvironmentVariable = string("bearer_token_env_var"),
            headers = stringMap("http_headers"),
            environmentHeaders = stringMap("env_http_headers"),
            headersHelper = string("http_headers_helper"),
        )
    }
    return AgentMcpServerConfiguration(
        name = name,
        transport = transport,
        authentication = when (val authentication = string("auth")) {
            null -> null
            "oauth" -> AgentMcpAuthentication.OAUTH
            "chatgpt" -> AgentMcpAuthentication.CHAT_GPT
            else -> throw IllegalArgumentException("Unsupported MCP authentication '$authentication'")
        },
        environmentId = string("environment_id") ?: "local",
        isEnabled = boolean("enabled") ?: true,
        isRequired = boolean("required") ?: false,
        supportsParallelToolCalls = boolean("supports_parallel_tool_calls") ?: false,
        omitToolsFrom = strings("omit_tools_from")?.map { value ->
            enumValueOf<AgentMcpToolExposureSurface>(value.uppercase())
        },
        startupTimeoutSeconds = double("startup_timeout_sec"),
        toolTimeoutSeconds = double("tool_timeout_sec"),
        defaultToolApproval = string("default_tools_approval_mode")?.toApproval(),
        enabledTools = strings("enabled_tools"),
        disabledTools = strings("disabled_tools"),
        scopes = strings("scopes"),
        oauth = (get("oauth") as? JsonObject)?.let { value ->
            AgentMcpOauthConfiguration(value.string("client_id"), value.int("callback_port"))
        },
        oauthResource = string("oauth_resource"),
        tools = (get("tools") as? JsonObject).orEmpty().mapNotNull { (toolName, value) ->
            (value as? JsonObject)?.let { tool ->
                toolName to AgentMcpToolConfiguration(tool.string("approval_mode")?.toApproval())
            }
        }.toMap(),
    )
}

private fun JsonObject.string(name: String): String? = get(name)?.jsonPrimitive?.contentOrNull
private fun JsonObject.boolean(name: String): Boolean? = get(name)?.jsonPrimitive?.booleanOrNull
private fun JsonObject.double(name: String): Double? = get(name)?.jsonPrimitive?.doubleOrNull
private fun JsonObject.int(name: String): Int? = get(name)?.jsonPrimitive?.intOrNull
private fun JsonObject.strings(name: String): List<String>? = (get(name) as? JsonArray)?.mapNotNull {
    it.jsonPrimitive.contentOrNull
}
private fun JsonObject.stringMap(name: String): Map<String, String>? = (get(name) as? JsonObject)?.mapNotNull {
    (key, value) -> value.jsonPrimitive.contentOrNull?.let { key to it }
}?.toMap()
private fun List<String>.toJsonArray(): JsonArray = buildJsonArray {
    this@toJsonArray.forEach { add(JsonPrimitive(it)) }
}
private fun Map<String, String>.toJsonObject(): JsonObject = buildJsonObject {
    this@toJsonObject.forEach { (name, value) -> put(name, JsonPrimitive(value)) }
}
private fun String.toApproval(): AgentMcpToolApproval? =
    AgentMcpToolApproval.entries.firstOrNull { it.name.equals(this, ignoreCase = true) }
