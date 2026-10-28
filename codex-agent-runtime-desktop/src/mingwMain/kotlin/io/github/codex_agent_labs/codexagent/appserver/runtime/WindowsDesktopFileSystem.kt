@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.appserver.runtime

import okio.FileMetadata
import okio.FileSystem
import okio.ForwardingFileSystem
import okio.IOException
import okio.Path
import okio.Path.Companion.toPath
import platform.windows.CreateSymbolicLinkW
import platform.windows.ERROR_FILE_NOT_FOUND
import platform.windows.ERROR_PATH_NOT_FOUND
import platform.windows.FILE_ATTRIBUTE_DIRECTORY
import platform.windows.FILE_ATTRIBUTE_REPARSE_POINT
import platform.windows.GetFileAttributesW
import platform.windows.GetLastError
import platform.windows.INVALID_FILE_ATTRIBUTES
import platform.windows.SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE
import platform.windows.SYMBOLIC_LINK_FLAG_DIRECTORY

internal actual val desktopFileSystem: FileSystem = WindowsDesktopFileSystem

private object WindowsDesktopFileSystem : ForwardingFileSystem(FileSystem.SYSTEM) {
    override fun metadataOrNull(path: Path): FileMetadata? {
        val attributes = path.windowsAttributesOrNull() ?: return null
        if (!attributes.has(FILE_ATTRIBUTE_REPARSE_POINT)) return delegate.metadataOrNull(path)
        return FileMetadata(
            isDirectory = attributes.has(FILE_ATTRIBUTE_DIRECTORY),
            symlinkTarget = REPARSE_POINT_MARKER,
        )
    }

    override fun list(dir: Path): List<Path> {
        if (dir.windowsAttributesOrNull()?.has(FILE_ATTRIBUTE_REPARSE_POINT) == true) {
            throw IOException("Refusing to follow Windows reparse point '$dir'")
        }
        return super.list(dir)
    }

    override fun listOrNull(dir: Path): List<Path>? {
        if (dir.windowsAttributesOrNull()?.has(FILE_ATTRIBUTE_REPARSE_POINT) == true) return null
        return super.listOrNull(dir)
    }

    override fun createSymlink(source: Path, target: Path) {
        val sourceParent = source.parent
            ?: throw IOException("Symbolic-link source has no parent: '$source'")
        val resolvedTarget = if (target.isAbsolute) target else sourceParent / target
        val targetAttributes = resolvedTarget.windowsAttributesOrNull()
            ?: throw IOException("Symbolic-link target is unavailable: '$resolvedTarget'")
        val flags = SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE.toUInt() or
            if (targetAttributes.has(FILE_ATTRIBUTE_DIRECTORY)) {
                SYMBOLIC_LINK_FLAG_DIRECTORY.toUInt()
            } else {
                0U
            }
        val error = if (CreateSymbolicLinkW(source.toString(), target.toString(), flags) != 0.toUByte()) {
            null
        } else {
            GetLastError().toInt()
        }
        if (error != null) {
            throw IOException("Could not create symbolic link '$source' (Windows error $error)")
        }
    }
}

private fun Path.windowsAttributesOrNull(): UInt? {
    val attributes = GetFileAttributesW(toString())
    if (attributes != INVALID_FILE_ATTRIBUTES) return attributes
    when (val error = GetLastError().toInt()) {
        ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND -> return null
        else -> throw IOException("Could not inspect '$this' (Windows error $error)")
    }
}

private fun UInt.has(attribute: Int): Boolean = this and attribute.toUInt() != 0U

private val REPARSE_POINT_MARKER = ".".toPath()
