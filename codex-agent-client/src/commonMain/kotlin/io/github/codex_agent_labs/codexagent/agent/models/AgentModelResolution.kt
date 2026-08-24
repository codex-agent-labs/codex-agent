package io.github.codex_agent_labs.codexagent.agent

public enum class AgentResolution {
    Preferred,
    Default,
    First,
}

public class AgentModelUnavailableException : Exception("No Codex models are available")

internal fun List<AgentModel>.resolveModel(
    resolution: AgentResolution,
    preferredId: String?,
): AgentModel = when (resolution) {
    AgentResolution.Preferred -> preferredId?.let { id -> firstOrNull { it.id == id } }
        ?: firstOrNull(AgentModel::isDefault)
        ?: firstOrNull()
    AgentResolution.Default -> firstOrNull(AgentModel::isDefault) ?: firstOrNull()
    AgentResolution.First -> firstOrNull()
} ?: throw AgentModelUnavailableException()

internal fun AgentModel.resolveEffort(
    resolution: AgentResolution,
    preferredEffort: String?,
): String = when (resolution) {
    AgentResolution.Preferred -> preferredEffort?.takeIf(supportedEfforts::contains)
        ?: defaultEffort
    AgentResolution.Default -> defaultEffort
    AgentResolution.First -> supportedEfforts.firstOrNull() ?: defaultEffort
}

internal fun AgentModel.resolveServiceTier(
    resolution: AgentResolution,
    preferredTierId: String?,
): AgentServiceTier? {
    if (serviceTiers.isEmpty()) return null
    return when (resolution) {
        AgentResolution.Preferred -> preferredTierId?.let { id -> serviceTiers.firstOrNull { it.id == id } }
            ?: defaultServiceTier?.let { id -> serviceTiers.firstOrNull { it.id == id } }
            ?: serviceTiers.first()
        AgentResolution.Default -> defaultServiceTier?.let { id -> serviceTiers.firstOrNull { it.id == id } }
            ?: serviceTiers.first()
        AgentResolution.First -> serviceTiers.first()
    }
}
