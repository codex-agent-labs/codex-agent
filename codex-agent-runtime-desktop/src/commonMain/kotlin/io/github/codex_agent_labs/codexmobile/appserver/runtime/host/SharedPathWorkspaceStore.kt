package io.github.codex_agent_labs.codexmobile.appserver.runtime.host

import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceStore
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

internal class SharedPathWorkspaceStore(
    dataDirectory: String,
    private val files: ExternalHostFiles,
) : CodexWorkspaceStore {
    private val dataDirectory = dataDirectory
    private val selectionFile get() = files.joinPath(dataDirectory, "workspace.json")

    override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution = stateLock.withLock {
        if (selection !is CodexPathWorkspaceSelection) return@withLock required(
            CodexWorkspaceSelectionReason.INVALID_SELECTION,
            "This host requires a filesystem workspace path.",
        )
        val resolution = resolve(selection.path)
        if (resolution is CodexWorkspaceResolution.Available) persist(resolution.workspace.path)
        resolution
    }

    override suspend fun restore(): CodexWorkspaceResolution = stateLock.withLock {
        val metadata = files.metadataOrNull(selectionFile)
            ?: return@withLock required(CodexWorkspaceSelectionReason.NOT_SELECTED, "Select a workspace.")
        if (!metadata.regularFile || metadata.symbolicLink || metadata.size !in 1..MAX_SELECTION_BYTES) {
            return@withLock corruptSelection()
        }
        val path = runCatching {
            val primitive = Json.parseToJsonElement(
                files.readFileSnapshot(selectionFile, MAX_SELECTION_BYTES).decodeToString(),
            ).jsonPrimitive
            require(primitive.isString) { "Workspace selection must be a JSON string" }
            primitive.content
        }.getOrElse { return@withLock corruptSelection() }
        resolve(path)
    }

    override suspend fun clear(): Unit = stateLock.withLock {
        val metadata = files.metadataOrNull(selectionFile) ?: return@withLock
        require(!metadata.directory) { "The saved workspace selection is not a file" }
        files.deleteFile(selectionFile)
    }

    fun resolve(path: String): CodexWorkspaceResolution {
        if (path.isBlank() || '\u0000' in path || !files.isAbsolute(path)) return required(
            CodexWorkspaceSelectionReason.INVALID_SELECTION,
            "Workspace path must be a valid absolute path.",
        )
        if (files.metadataOrNull(path) == null) return required(
            CodexWorkspaceSelectionReason.NOT_FOUND,
            "Workspace directory is unavailable.",
        )
        val canonical = runCatching { files.canonicalize(path) }.getOrElse {
            return required(CodexWorkspaceSelectionReason.ACCESS_REVOKED, "Workspace access is unavailable.")
        }
        if (files.metadataOrNull(canonical)?.directory != true) return required(
            CodexWorkspaceSelectionReason.INVALID_SELECTION,
            "Workspace path is not a directory.",
        )
        if (runCatching { files.list(canonical) }.isFailure) return required(
            CodexWorkspaceSelectionReason.ACCESS_REVOKED,
            "Workspace access is unavailable; select it again.",
        )
        return CodexWorkspaceResolution.Available(
            CodexWorkspace(canonical, files.baseName(canonical).ifBlank { canonical }),
        )
    }

    private fun persist(path: String) {
        files.createDirectories(dataDirectory)
        val bytes = JsonPrimitive(path).toString().encodeToByteArray()
        val temporary = files.joinPath(dataDirectory, ".workspace-${hostToken()}.tmp")
        var failure: Throwable? = null
        try {
            files.writeNewFile(temporary, bytes)
            try {
                files.atomicReplace(temporary, selectionFile)
            } catch (replace: Throwable) {
                val committed = runCatching {
                    val metadata = files.metadataOrNull(selectionFile)
                    metadata?.let { it.regularFile && !it.symbolicLink && it.size == bytes.size.toLong() } == true &&
                        files.readFileSnapshot(selectionFile, bytes.size.toLong()).contentEquals(bytes)
                }.getOrDefault(false)
                if (!committed) throw replace
            }
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            try {
                if (files.metadataOrNull(temporary) != null) {
                    files.deleteFile(temporary)
                }
            } catch (cleanup: Throwable) {
                if (failure == null) throw cleanup
                failure.addSuppressed(cleanup)
            }
        }
    }

    private fun corruptSelection() = required(
        CodexWorkspaceSelectionReason.INVALID_SELECTION,
        "The saved workspace selection is corrupt; select it again.",
    )

    private fun required(reason: CodexWorkspaceSelectionReason, message: String) =
        CodexWorkspaceResolution.SelectionRequired(reason, message)

    private companion object {
        const val MAX_SELECTION_BYTES = 16 * 1024L
        // ponytail: one process-wide lock; shard by canonical data root only if contention is measured.
        val stateLock = Mutex()
    }
}

private fun hostToken(): String = kotlin.random.Random.nextLong().toString().replace('-', '0')
