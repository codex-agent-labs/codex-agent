import io.github.codex_agent_labs.codexagent.agent.runtime.IosCodexCredentialProtection
import io.github.codex_agent_labs.codexagent.agent.runtime.IosCodexPlatform

fun iosPlatform(sandbox: String) = IosCodexPlatform(
    sandboxRootPath = sandbox,
    credentialProtection = IosCodexCredentialProtection.WHEN_UNLOCKED,
)
