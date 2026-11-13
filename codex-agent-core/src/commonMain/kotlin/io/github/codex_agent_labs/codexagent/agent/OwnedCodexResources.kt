package io.github.codex_agent_labs.codexagent.agent

import kotlin.random.Random
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import okio.Path
import okio.Path.Companion.toPath

internal class OwnedCodexResources(
    initialRoots: CodexInstallationRoots,
    private val fileSystem: AgentFileStore,
) {
    private var roots = initialRoots

    fun resolveCodexHome(codexHome: String) {
        val home = codexHome.toPath(normalize = true)
        roots = roots.copy(
            userSkillsRoot = roots.userSkillsRoot ?: home / "skills",
            userHooksFile = roots.userHooksFile ?: home / "hooks.json",
        )
    }

    suspend fun installSkill(
        directory: String,
        scope: AgentInstallationScope,
        reload: suspend () -> AgentSkillCatalog,
    ): AgentSkill {
        val source = validatedSourceDirectory(directory)
        val manifest = source / SKILL_MANIFEST
        requireRegularNonEmptyFile(manifest, "A skill bundle must contain a non-empty SKILL.md")
        validateSkillManifest(fileSystem.readUtf8(manifest))
        val name = validResourceName(source.name)
        val destination = safeRoot(skillRoot(scope)) / name
        installOwnedDirectory(source, destination, ResourceKind.SKILL, scope, setOf(OWNERSHIP_MARKER))
        return try {
            val expected = (destination / SKILL_MANIFEST).toString()
            reload().skills.singleOrNull { it.path.toPath(normalize = true).toString() == expected }
                ?.copy(canUninstall = true)
                ?: throw AgentResourceInstallationException("Codex did not discover the installed skill '$name'")
        } catch (error: Throwable) {
            rollbackInstalledDirectory(destination, "skill '$name'", error)
        }
    }

    suspend fun uninstallSkill(
        skill: AgentSkill,
        reload: suspend () -> AgentSkillCatalog,
    ) {
        val manifest = skill.path.toPath(normalize = true)
        require(manifest.name == SKILL_MANIFEST) { "Skill path must point to SKILL.md" }
        val directory = checkNotNull(manifest.parent) { "Skill path must have a parent directory" }
        val marker = readMarker(directory / OWNERSHIP_MARKER)
        require(marker.kind == ResourceKind.SKILL && marker.resourceName == directory.name) {
            "Only skills installed by this library can be uninstalled"
        }
        verifyOwnedDirectory(directory, marker)
        val expectedRoot = safeRoot(skillRoot(marker.scope))
        require(directory.parent == expectedRoot) { "Skill ownership marker does not match its installation root" }
        removeOwnedDirectory(directory, "skill '${directory.name}'") {
            check(reload().skills.none { it.path.toPath(normalize = true) == manifest }) {
                "Codex still reports the uninstalled skill '${directory.name}'"
            }
        }
    }

    fun ownsSkill(skill: AgentSkill): Boolean = runCatching {
        val manifest = skill.path.toPath(normalize = true)
        val directory = manifest.parent ?: return@runCatching false
        val marker = readMarker(directory / OWNERSHIP_MARKER)
        verifyOwnedDirectory(directory, marker)
        marker.kind == ResourceKind.SKILL &&
            marker.resourceName == directory.name &&
            directory.parent == safeRoot(skillRoot(marker.scope))
    }.getOrDefault(false)

    suspend fun installHook(
        directory: String,
        scope: AgentInstallationScope,
        reload: suspend () -> AgentHookCatalog,
    ): AgentHook {
        val source = validatedSourceDirectory(directory)
        val sourceConfig = source / HOOKS_MANIFEST
        requireRegularNonEmptyFile(sourceConfig, "A hook bundle must contain a non-empty hooks.json")
        val bundleName = validResourceName(source.name)
        val sourcePayload = parseSingleHook(fileSystem.readUtf8(sourceConfig))
        val assets = collectFiles(source).filterNot { it.relative == HOOKS_MANIFEST || it.relative == OWNERSHIP_MARKER }
        val targetConfig = hookFile(scope)
        val configDirectory = safeRoot(checkNotNull(targetConfig.parent) { "Hooks file must have a parent" })
        val assetRoot = safeRoot(configDirectory / HOOK_ASSETS_DIRECTORY)
        val destination = assetRoot / bundleName
        require(fileSystem.metadata(destination) == null) { "Hook bundle '$bundleName' is already installed" }

        val installedPayload = rewriteHookAssets(sourcePayload, assets.map(OwnedFile::relative), destination)
        val oldConfig = fileSystem.metadata(targetConfig)?.let {
            require(it.isRegularFile && !it.isSymbolicLink) { "Hooks target must be a regular file" }
            fileSystem.readUtf8(targetConfig)
        }
        val previousCatalog = reload()
        val merged = mergeHook(oldConfig, installedPayload)

        installOwnedDirectory(
            source = source,
            destination = destination,
            kind = ResourceKind.HOOK,
            scope = scope,
            excludedNames = setOf(HOOKS_MANIFEST, OWNERSHIP_MARKER),
            hookPayload = installedPayload,
        )
        try {
            fileSystem.writeUtf8Atomically(targetConfig, renderJson(merged))
        } catch (error: Throwable) {
            rollbackInstalledDirectory(destination, "hook '$bundleName'", error)
        }

        return try {
            val oldKeys = previousCatalog.hooks.mapTo(mutableSetOf(), AgentHook::key)
            val matches = reload().hooks.filter { it.sourcePath.toPath(normalize = true) == targetConfig && it.key !in oldKeys }
            val installed = matches.singleOrNull()
                ?: throw AgentResourceInstallationException("Codex did not discover exactly one installed hook '$bundleName'")
            val markerPath = destination / OWNERSHIP_MARKER
            writeMarker(markerPath, readMarker(markerPath).copy(hookKey = installed.key))
            installed.copy(canUninstall = true)
        } catch (error: Throwable) {
            rollbackHookInstall(targetConfig, oldConfig, destination, bundleName, error)
        }
    }

    suspend fun uninstallHook(
        hook: AgentHook,
        reload: suspend () -> AgentHookCatalog,
    ) {
        val targetConfig = hook.sourcePath.toPath(normalize = true)
        val scope = AgentInstallationScope.entries.singleOrNull { runCatching { hookFile(it) == targetConfig }.getOrDefault(false) }
            ?: throw IllegalArgumentException("Only hooks installed in a writable user or workspace scope can be uninstalled")
        val assetRoot = existingSafeRoot(checkNotNull(targetConfig.parent) / HOOK_ASSETS_DIRECTORY)
        val owned = runCatching { fileSystem.list(assetRoot) }.getOrDefault(emptyList()).firstNotNullOfOrNull { directory ->
            runCatching {
                val metadata = fileSystem.metadata(directory)
                require(metadata?.isDirectory == true && !metadata.isSymbolicLink)
                directory to readMarker(directory / OWNERSHIP_MARKER)
            }.getOrNull()
                ?.takeIf { (_, marker) -> marker.kind == ResourceKind.HOOK && marker.scope == scope && marker.hookKey == hook.key }
        } ?: throw IllegalArgumentException("Only hooks installed by this library can be uninstalled")
        val directory = owned.first
        val marker = owned.second
        verifyOwnedDirectory(directory, marker)
        val payload = checkNotNull(marker.hookPayload) { "Hook ownership marker is incomplete" }
        val oldConfig = fileSystem.readUtf8(targetConfig)
        val updated = removeHook(oldConfig, payload)
        val tombstone = temporarySibling(directory, "remove")
        fileSystem.atomicMove(directory, tombstone)
        var cleanupStarted = false
        try {
            fileSystem.writeUtf8Atomically(targetConfig, renderJson(updated))
            check(reload().hooks.none { it.key == hook.key }) { "Codex still reports the uninstalled hook '${hook.key}'" }
            cleanupStarted = true
            fileSystem.deleteRecursively(tombstone)
        } catch (error: Throwable) {
            val rollbackFailures = mutableListOf<Throwable>()
            runCatching { fileSystem.writeUtf8Atomically(targetConfig, oldConfig) }.exceptionOrNull()?.let(rollbackFailures::add)
            runCatching { fileSystem.atomicMove(tombstone, directory) }.exceptionOrNull()?.let(rollbackFailures::add)
            if (cleanupStarted || rollbackFailures.isNotEmpty()) {
                throw AgentResourcePartialChangeException(
                    "Hook '${hook.key}' could not be uninstalled and rollback was incomplete",
                    error,
                )
            }
            throw installationFailure("Could not uninstall hook '${hook.key}'", error)
        }
    }

    fun ownsHook(hook: AgentHook): Boolean = runCatching {
        val target = hook.sourcePath.toPath(normalize = true)
        val scope = AgentInstallationScope.entries.singleOrNull {
            runCatching { hookFile(it) == target }.getOrDefault(false)
        } ?: return@runCatching false
        val assetRoot = existingSafeRoot(checkNotNull(target.parent) / HOOK_ASSETS_DIRECTORY)
        // ponytail: hook catalogs are small; index ownership markers only if this scan becomes measurable.
        fileSystem.list(assetRoot).any { directory ->
            runCatching {
                val metadata = fileSystem.metadata(directory)
                require(metadata?.isDirectory == true && !metadata.isSymbolicLink)
                readMarker(directory / OWNERSHIP_MARKER)
            }.getOrNull()?.let { marker ->
                verifyOwnedDirectory(directory, marker)
                marker.kind == ResourceKind.HOOK && marker.scope == scope && marker.hookKey == hook.key
            } == true
        }
    }.getOrDefault(false)

    private fun installOwnedDirectory(
        source: Path,
        destination: Path,
        kind: ResourceKind,
        scope: AgentInstallationScope,
        excludedNames: Set<String>,
        hookPayload: JsonObject? = null,
    ) {
        require(fileSystem.metadata(destination) == null) { "${kind.label} '${destination.name}' already exists" }
        val parent = safeRoot(checkNotNull(destination.parent))
        val staging = temporarySibling(destination, "stage")
        try {
            fileSystem.createDirectories(staging)
            val files = copyDirectory(source, staging, excludedNames)
            writeMarker(
                staging / OWNERSHIP_MARKER,
                OwnershipMarker(kind, destination.name, scope, hookPayload, files = files),
            )
            fileSystem.atomicMove(staging, destination)
        } catch (error: Throwable) {
            val cleanup = runCatching { fileSystem.deleteRecursively(staging) }.exceptionOrNull()
            if (cleanup != null) {
                throw AgentResourcePartialChangeException(
                    "${kind.label} '${destination.name}' could not be installed and staging cleanup failed",
                    error,
                )
            }
            throw installationFailure("Could not install ${kind.label} '${destination.name}'", error)
        }
        check(destination.parent == parent)
    }

    private suspend fun removeOwnedDirectory(
        directory: Path,
        description: String,
        reload: suspend () -> Unit,
    ) {
        val tombstone = temporarySibling(directory, "remove")
        fileSystem.atomicMove(directory, tombstone)
        var cleanupStarted = false
        try {
            reload()
            cleanupStarted = true
            fileSystem.deleteRecursively(tombstone)
        } catch (error: Throwable) {
            val rollback = runCatching { fileSystem.atomicMove(tombstone, directory) }.exceptionOrNull()
            if (cleanupStarted || rollback != null) {
                throw AgentResourcePartialChangeException("$description removal failed and rollback was incomplete", error)
            }
            throw installationFailure("Could not uninstall $description", error)
        }
    }

    private fun rollbackInstalledDirectory(destination: Path, description: String, error: Throwable): Nothing {
        val cleanup = runCatching { fileSystem.deleteRecursively(destination) }.exceptionOrNull()
        if (cleanup != null) {
            throw AgentResourcePartialChangeException("$description installation failed and rollback was incomplete", error)
        }
        throw installationFailure("Could not install $description", error)
    }

    private fun rollbackHookInstall(
        targetConfig: Path,
        oldConfig: String?,
        destination: Path,
        bundleName: String,
        error: Throwable,
    ): Nothing {
        val failures = mutableListOf<Throwable>()
        runCatching {
            if (oldConfig == null) fileSystem.delete(targetConfig)
            else fileSystem.writeUtf8Atomically(targetConfig, oldConfig)
        }.exceptionOrNull()?.let(failures::add)
        runCatching { fileSystem.deleteRecursively(destination) }.exceptionOrNull()?.let(failures::add)
        if (failures.isNotEmpty()) {
            throw AgentResourcePartialChangeException(
                "Hook '$bundleName' installation failed and rollback was incomplete",
                error,
            )
        }
        throw installationFailure("Could not install hook '$bundleName'", error)
    }

    private fun validatedSourceDirectory(directory: String): Path {
        require(directory.isNotBlank() && '\u0000' !in directory) { "Installation directory must not be blank" }
        val input = directory.toPath(normalize = true)
        require(input.isAbsolute) { "Installation directory must be absolute" }
        val metadata = fileSystem.metadata(input)
        require(metadata?.isDirectory == true && !metadata.isSymbolicLink) {
            "Installation source must be a directory and must not be a symbolic link"
        }
        val canonical = fileSystem.canonicalize(input)
        collectFiles(canonical)
        return canonical
    }

    private fun safeRoot(root: Path): Path {
        require(root.isAbsolute) { "Installation root must be absolute" }
        val normalized = root.toString().toPath(normalize = true)
        var component: Path? = normalized
        while (component != null) {
            fileSystem.metadata(component)?.let { metadata ->
                require(metadata.isDirectory && !metadata.isSymbolicLink) {
                    "Installation root components must be directories and must not be symbolic links"
                }
            }
            component = component.parent
        }
        fileSystem.createDirectories(normalized)
        return existingSafeRoot(normalized)
    }

    private fun existingSafeRoot(root: Path): Path {
        require(root.isAbsolute) { "Installation root must be absolute" }
        val metadata = requireNotNull(fileSystem.metadata(root)) { "Installation root is unavailable" }
        require(metadata.isDirectory && !metadata.isSymbolicLink) { "Installation root must be a directory" }
        val canonical = fileSystem.canonicalize(root)
        require(canonical == root.toString().toPath(normalize = true)) {
            "Installation root must not traverse symbolic links"
        }
        return canonical
    }

    private fun collectFiles(source: Path): List<OwnedFile> {
        val result = mutableListOf<OwnedFile>()
        fun visit(directory: Path, prefix: String) {
            fileSystem.list(directory).sortedBy(Path::name).forEach { child ->
                require(child.name != "." && child.name != "..") { "Resource path traversal is not allowed" }
                val relative = if (prefix.isEmpty()) child.name else "$prefix/${child.name}"
                require(relative.toPath(normalize = true).toString() == relative) { "Resource path traversal is not allowed" }
                val metadata = checkNotNull(fileSystem.metadata(child)) { "Resource changed while being validated" }
                require(!metadata.isSymbolicLink) { "Symbolic links are not allowed in installed resources" }
                when {
                    metadata.isDirectory -> visit(child, relative)
                    metadata.isRegularFile -> result += OwnedFile(child, relative)
                    else -> throw IllegalArgumentException("Only regular files and directories can be installed")
                }
            }
        }
        visit(source, "")
        return result
    }

    private fun copyDirectory(source: Path, destination: Path, excludedNames: Set<String>): List<String> =
        collectFiles(source).filterNot { it.relative in excludedNames }.map { file ->
            val metadata = fileSystem.metadata(file.path)
            require(metadata?.isRegularFile == true && !metadata.isSymbolicLink) {
                "Resource changed while being copied"
            }
            val target = destination / file.relative
            fileSystem.createDirectories(checkNotNull(target.parent))
            fileSystem.writeBytesAtomically(target, fileSystem.readBytes(file.path))
            file.relative
        }

    private fun verifyOwnedDirectory(directory: Path, marker: OwnershipMarker) {
        val actual = collectFiles(directory).mapTo(mutableSetOf(), OwnedFile::relative)
        val expected = (marker.files + OWNERSHIP_MARKER).toSet()
        require(actual == expected) { "Owned resource contents changed after installation" }
    }

    private fun requireRegularNonEmptyFile(path: Path, message: String) {
        val metadata = fileSystem.metadata(path)
        require(metadata?.isRegularFile == true && !metadata.isSymbolicLink && fileSystem.size(path)?.let { it > 0 } == true) {
            message
        }
        runCatching { fileSystem.readUtf8(path) }.getOrElse {
            throw IllegalArgumentException("${path.name} must be valid UTF-8", it)
        }
    }

    private fun validateSkillManifest(value: String) {
        val lines = value.replace("\r\n", "\n").lines()
        require(lines.firstOrNull() == "---") { "SKILL.md must start with YAML frontmatter" }
        val end = lines.drop(1).indexOf("---").let { if (it < 0) -1 else it + 1 }
        require(end > 1) { "SKILL.md frontmatter is not closed" }
        val fields = lines.subList(1, end).mapNotNull { line ->
            val separator = line.indexOf(':')
            if (separator <= 0) null else line.substring(0, separator).trim() to line.substring(separator + 1).trim()
        }.toMap()
        require(fields["name"].orEmpty().isNotBlank()) { "SKILL.md frontmatter must contain name" }
        require(fields["description"].orEmpty().isNotBlank()) { "SKILL.md frontmatter must contain description" }
    }

    private fun parseSingleHook(value: String): JsonObject {
        val root = runCatching { INSTALLATION_JSON.parseToJsonElement(value).jsonObject }.getOrElse {
            throw IllegalArgumentException("hooks.json must contain a JSON object", it)
        }
        require(root.keys.all { it == "description" || it == "hooks" }) { "hooks.json contains unsupported top-level fields" }
        root["description"]?.let { require(it is JsonPrimitive && it.isString) { "Hook description must be a string" } }
        val hooks = root["hooks"]?.jsonObject ?: throw IllegalArgumentException("hooks.json must contain hooks")
        require(hooks.keys.singleOrNull() in HOOK_EVENTS) { "A hook bundle must contain exactly one supported event" }
        val event = hooks.entries.single()
        val groups = event.value.jsonArray
        require(groups.size == 1) { "A hook bundle must contain exactly one matcher group" }
        val group = groups.single().jsonObject
        require(group.keys.all { it == "matcher" || it == "hooks" }) { "Hook matcher group contains unsupported fields" }
        group["matcher"]?.let {
            require(it == JsonNull || it is JsonPrimitive && it.isString) { "Hook matcher must be a string or null" }
        }
        val handlers = group["hooks"]?.jsonArray ?: throw IllegalArgumentException("Hook matcher group must contain hooks")
        require(handlers.size == 1) { "A hook bundle must contain exactly one handler" }
        validateHookHandler(event.key, handlers.single().jsonObject)
        return JsonObject(mapOf(event.key to JsonArray(listOf(group))))
    }

    private fun validateHookHandler(event: String, handler: JsonObject) {
        val type = handler["type"]?.jsonPrimitive?.contentOrNull
            ?: throw IllegalArgumentException("Hook handler type is required")
        when (type) {
            "command" -> {
                requireString(handler, "command")
                handler["commandWindows"]?.let { require(it is JsonPrimitive && it.isString) }
                handler["async"]?.let { require(it.jsonPrimitive.booleanOrNull != null) }
                handler["statusMessage"]?.let { require(it is JsonPrimitive && it.isString) }
                listOf("timeout", "additionalContextLimit").forEach { name ->
                    handler[name]?.let { require(it.jsonPrimitive.longOrNull?.let { number -> number >= 0 } == true) }
                }
            }
            "mcp_tool" -> {
                require(event != "SessionEnd") { "SessionEnd MCP tool hooks are not supported by Codex 0.149" }
                requireString(handler, "server")
                requireString(handler, "tool")
                handler["input"]?.let {
                    require(it is JsonObject && !containsNull(it)) { "MCP hook input must be a non-null JSON object" }
                }
                handler["timeout"]?.let { require(it.jsonPrimitive.longOrNull?.let { number -> number >= 0 } == true) }
                handler["statusMessage"]?.let { require(it is JsonPrimitive && it.isString) }
            }
            "prompt", "agent" -> throw IllegalArgumentException("$type hooks are not supported by Codex 0.149")
            else -> throw IllegalArgumentException("Unsupported hook handler type '$type'")
        }
    }

    private fun rewriteHookAssets(payload: JsonObject, assets: List<String>, destination: Path): JsonObject {
        if (assets.isEmpty()) return payload
        fun rewrite(element: JsonElement, key: String? = null): JsonElement = when (element) {
            is JsonObject -> JsonObject(element.mapValues { (name, value) -> rewrite(value, name) })
            is JsonArray -> JsonArray(element.map { rewrite(it) })
            is JsonPrimitive -> if (element.isString && key in setOf("command", "commandWindows")) {
                var command = element.content
                val replacements = mutableListOf<Pair<String, String>>()
                assets.sortedByDescending(String::length).forEachIndexed { index, relative ->
                    val installed = (destination / relative).toString()
                    val quoted = if (key == "commandWindows") "\"$installed\"" else "'${installed.replace("'", "'\\''")}'"
                    val reference = "./$relative".takeIf(command::contains) ?: relative
                    val token = "__CODEX_AGENT_HOOK_ASSET_${index}__"
                    command = when {
                        "'$reference'" in command -> command.replace("'$reference'", token)
                        "\"$reference\"" in command -> command.replace("\"$reference\"", token)
                        else -> command.replace(reference, token)
                    }
                    replacements += token to quoted
                }
                replacements.forEach { (token, quoted) -> command = command.replace(token, quoted) }
                JsonPrimitive(command)
            } else element
        }
        return rewrite(payload).jsonObject
    }

    private fun mergeHook(oldConfig: String?, payload: JsonObject): JsonObject {
        val root = oldConfig?.let { parseTargetHooks(it) } ?: buildJsonObject { put("hooks", buildJsonObject {}) }
        val hooks = root["hooks"]?.jsonObject.orEmpty()
        val event = payload.entries.single()
        val existing = hooks[event.key]?.jsonArray.orEmpty()
        val group = event.value.jsonArray.single()
        require(group !in existing) { "An identical hook is already configured" }
        return JsonObject(root + ("hooks" to JsonObject(hooks + (event.key to JsonArray(existing + group)))))
    }

    private fun removeHook(oldConfig: String, payload: JsonObject): JsonObject {
        val root = parseTargetHooks(oldConfig)
        val hooks = root["hooks"]?.jsonObject.orEmpty()
        val event = payload.entries.single()
        val expected = event.value.jsonArray.single()
        val existing = hooks[event.key]?.jsonArray.orEmpty()
        require(existing.count { it == expected } == 1) { "Owned hook configuration was modified or removed" }
        val remaining = existing.filterNot { it == expected }
        val updatedHooks = if (remaining.isEmpty()) hooks - event.key else hooks + (event.key to JsonArray(remaining))
        return JsonObject(root + ("hooks" to JsonObject(updatedHooks)))
    }

    private fun parseTargetHooks(value: String): JsonObject {
        val root = runCatching { INSTALLATION_JSON.parseToJsonElement(value).jsonObject }.getOrElse {
            throw IllegalArgumentException("Existing hooks.json is malformed", it)
        }
        require(root["hooks"] == null || root["hooks"] is JsonObject) { "Existing hooks.json has an invalid hooks field" }
        return root
    }

    private fun writeMarker(path: Path, marker: OwnershipMarker) {
        val body = buildJsonObject {
            put("formatVersion", OWNERSHIP_FORMAT_VERSION)
            put("kind", marker.kind.name.lowercase())
            put("resourceName", marker.resourceName)
            put("scope", marker.scope.name.lowercase())
            marker.hookPayload?.let { put("hookPayload", it) }
            marker.hookKey?.let { put("hookKey", it) }
            put("files", buildJsonArray { marker.files.sorted().forEach { add(JsonPrimitive(it)) } })
        }
        fileSystem.writeUtf8Atomically(path, renderJson(body))
    }

    private fun readMarker(path: Path): OwnershipMarker {
        val metadata = fileSystem.metadata(path)
        require(metadata?.isRegularFile == true && !metadata.isSymbolicLink) { "Resource ownership marker is missing" }
        val root = INSTALLATION_JSON.parseToJsonElement(fileSystem.readUtf8(path)).jsonObject
        require(root["formatVersion"]?.jsonPrimitive?.longOrNull == OWNERSHIP_FORMAT_VERSION.toLong()) {
            "Unsupported resource ownership marker"
        }
        return OwnershipMarker(
            kind = enumValueOf(root.getValue("kind").jsonPrimitive.content.uppercase()),
            resourceName = validResourceName(root.getValue("resourceName").jsonPrimitive.content),
            scope = AgentInstallationScope.entries.single { scope ->
                scope.name.equals(root.getValue("scope").jsonPrimitive.content, ignoreCase = true)
            },
            hookPayload = root["hookPayload"] as? JsonObject,
            hookKey = root["hookKey"]?.jsonPrimitive?.contentOrNull,
            files = root["files"]?.jsonArray?.map { it.jsonPrimitive.content }.orEmpty(),
        )
    }

    private fun temporarySibling(path: Path, purpose: String): Path {
        val parent = checkNotNull(path.parent)
        repeat(20) {
            val candidate = parent / ".${path.name}.codex-agent-$purpose-${Random.nextLong().toULong()}"
            if (fileSystem.metadata(candidate) == null) return candidate
        }
        throw AgentResourceInstallationException("Could not allocate temporary resource storage")
    }

    private fun validResourceName(name: String): String {
        require(RESOURCE_NAME.matches(name)) { "Resource directory name is invalid" }
        return name
    }

    private fun skillRoot(scope: AgentInstallationScope): Path = when (scope) {
        AgentInstallationScope.User -> roots.userSkillsRoot
        AgentInstallationScope.Workspace -> roots.workspaceSkillsRoot
    } ?: throw AgentResourceInstallationException("${scope.name.lowercase()} skill installation is unavailable")

    private fun hookFile(scope: AgentInstallationScope): Path = when (scope) {
        AgentInstallationScope.User -> roots.userHooksFile
        AgentInstallationScope.Workspace -> roots.workspaceHooksFile
    } ?: throw AgentResourceInstallationException("${scope.name.lowercase()} hook installation is unavailable")

    private fun renderJson(value: JsonElement): String = INSTALLATION_JSON.encodeToString(JsonElement.serializer(), value) + "\n"

    private fun requireString(value: JsonObject, name: String) {
        require(value[name]?.jsonPrimitive?.contentOrNull?.isNotBlank() == true) { "Hook $name must be a non-empty string" }
    }

    private fun containsNull(value: JsonElement): Boolean = when (value) {
        JsonNull -> true
        is JsonArray -> value.any(::containsNull)
        is JsonObject -> value.values.any(::containsNull)
        else -> false
    }

    private fun installationFailure(message: String, error: Throwable): Throwable = when (error) {
        is CancellationException, is AgentResourceInstallationException -> error
        else -> AgentResourceInstallationException(message, error)
    }

    private data class OwnedFile(val path: Path, val relative: String)

    private data class OwnershipMarker(
        val kind: ResourceKind,
        val resourceName: String,
        val scope: AgentInstallationScope,
        val hookPayload: JsonObject? = null,
        val hookKey: String? = null,
        val files: List<String> = emptyList(),
    )

    private enum class ResourceKind(val label: String) {
        SKILL("skill"),
        HOOK("hook"),
    }

    private companion object {
        const val SKILL_MANIFEST = "SKILL.md"
        const val HOOKS_MANIFEST = "hooks.json"
        const val OWNERSHIP_MARKER = ".codex-agent-owned.json"
        const val HOOK_ASSETS_DIRECTORY = ".codex-agent-hooks"
        const val OWNERSHIP_FORMAT_VERSION = 1
        val RESOURCE_NAME = Regex("[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
        val HOOK_EVENTS = setOf(
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "PreCompact",
            "PostCompact",
            "SessionStart",
            "SessionEnd",
            "UserPromptSubmit",
            "SubagentStart",
            "SubagentStop",
            "Stop",
        )
        val INSTALLATION_JSON = Json { prettyPrint = true }
    }
}
