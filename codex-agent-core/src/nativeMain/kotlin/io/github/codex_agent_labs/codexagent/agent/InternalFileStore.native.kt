package io.github.codex_agent_labs.codexagent.agent

import okio.FileSystem

internal actual val systemAgentFileStore: AgentFileStore = FileSystem.SYSTEM.asAgentFileStore()
