package io.github.codex_agent_labs.codexmobile.agent

import okio.Path

public enum class AgentInstallationScope {
    User,
    Workspace,
}

public enum class AgentResourceOrigin {
    USER,
    WORKSPACE,
    PLUGIN,
    MANAGED,
    UNKNOWN,
}

public data class CodexInstallationRoots(
    public val userSkillsRoot: Path? = null,
    public val workspaceSkillsRoot: Path? = null,
    public val userHooksFile: Path? = null,
    public val workspaceHooksFile: Path? = null,
)

public open class AgentResourceInstallationException internal constructor(
    message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

public class AgentResourcePartialChangeException internal constructor(
    message: String,
    cause: Throwable? = null,
) : AgentResourceInstallationException(message, cause)
