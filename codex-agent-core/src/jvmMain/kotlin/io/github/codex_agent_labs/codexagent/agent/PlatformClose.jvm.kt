package io.github.codex_agent_labs.codexagent.agent

import kotlinx.coroutines.runBlocking

internal actual fun CodexAgentClient.closeAction() = runBlocking { closeSuspendingAction() }
