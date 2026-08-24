@file:JvmName("AndroidCodex")

package io.github.codex_agent_labs.codexmobile.agent.runtime

import android.content.Context
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexStorageRoots

public fun createHost(context: Context, clientInfo: CodexClientInfo): CodexHost =
    CodexHost(AndroidCodexPlatform(context), clientInfo)

public fun createHost(
    context: Context,
    clientInfo: CodexClientInfo,
    storageRoots: CodexStorageRoots,
): CodexHost = CodexHost(AndroidCodexPlatform(context, storageRoots), clientInfo)
