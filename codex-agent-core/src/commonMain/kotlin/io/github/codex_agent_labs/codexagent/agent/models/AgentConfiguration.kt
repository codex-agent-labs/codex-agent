package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.AppServerClientMethods
import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.ConfigReadParams
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

internal suspend fun CodexAgentClient.readModelPreferencesAction(
    workingDirectory: String,
): AgentModelPreferences {
    val config = connection.request(
        AppServerClientMethods.ConfigRead,
        ConfigReadParams(cwd = workingDirectory),
    ).config.jsonObject
    return AgentModelPreferences(
        modelId = config.stringOrNull("model"),
        effort = config.stringOrNull("model_reasoning_effort"),
        serviceTierId = config.stringOrNull("service_tier"),
    )
}

private fun Map<String, kotlinx.serialization.json.JsonElement>.stringOrNull(key: String): String? =
    get(key)?.jsonPrimitive?.contentOrNull
