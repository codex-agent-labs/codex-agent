@file:JvmName("AndroidCodex")

package io.github.codex_agent_labs.codexagent.agent.runtime

import android.content.Context
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexHost
import io.github.codex_agent_labs.codexagent.agent.CodexStorageRoots

public fun createHost(context: Context, clientInfo: CodexClientInfo): CodexHost =
    CodexHost(AndroidCodexPlatform(context), clientInfo)

public fun createHost(
    context: Context,
    clientInfo: CodexClientInfo,
    storageRoots: CodexStorageRoots,
): CodexHost = CodexHost(AndroidCodexPlatform(context, storageRoots), clientInfo)
