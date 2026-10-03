import java.io.File
import java.security.MessageDigest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.longOrNull

/** External observations only: no compiler/tool-policy, original-host or receipt admission. */
internal fun sdkFacadeCompilerCaptureScript(target: String, output: File): String =
    sdkFacadeCompilerCaptureScript(target, output.absolutePath)

/** Original paths are lexical, including Windows paths replayed on another operating system. */
internal fun sdkFacadeCompilerCaptureScript(target: String, output: String): String {
    val task = sdkFacadeConsumerCompileTasks[target] ?: error("Unsupported facade compiler target")
    requireFacadeCompilerPath(output)
    fun literal(value: String) = JsonPrimitive(value).toString().replace("$", "\\$")
    val script = """
        // Selected task inputs, not a compiler invocation or reviewed tool-policy attestation.
        val codexCompilerTarget = ${literal(target)}
        val codexCompilerTask = ${literal(task)}
        val codexCompilerFile = java.io.File(${literal(output)})
        fun codexCompilerHash(bytes: ByteArray): String = java.security.MessageDigest.getInstance("SHA-256")
            .digest(bytes).joinToString("") { "%02x".format(it) }
        fun codexCompilerSafe(file: java.io.File) {
            var current: java.io.File? = file.absoluteFile
            while (current != null) {
                check(!java.nio.file.Files.isSymbolicLink(current.toPath())) { "Symbolic compiler evidence/input" }
                current = current.parentFile
            }
        }
        fun codexCompilerInventory(roots: Collection<java.io.File>): Map<String, Any> {
            val files = roots.flatMap { root ->
                codexCompilerSafe(root)
                check(root.exists()) { "Missing selected compiler input: " + root }
                if (root.isDirectory) root.walkTopDown().onEnter { codexCompilerSafe(it); true }
                    .filter { !it.isDirectory }.toList() else listOf(root)
            }.distinctBy { it.absolutePath }.sortedBy { it.absolutePath }
            val rows = files.map { file ->
                codexCompilerSafe(file)
                check(file.isFile && file.absolutePath.none(Char::isISOControl)) { "Unsafe compiler input" }
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                file.inputStream().use { stream ->
                    val buffer = ByteArray(65536)
                    while (true) { val count = stream.read(buffer); if (count < 0) break; digest.update(buffer, 0, count) }
                }
                linkedMapOf<String, Any>("path" to file.absolutePath, "bytes" to file.length(),
                    "sha256" to digest.digest().joinToString("") { "%02x".format(it) })
            }
            val encoded = rows.joinToString("") { it.getValue("path").toString() + "\u0000" +
                it.getValue("bytes") + "\u0000" + it.getValue("sha256") + "\n" }
            return linkedMapOf("files" to rows, "sha256" to codexCompilerHash(encoded.toByteArray(Charsets.UTF_8)))
        }
        fun codexCompilerGet(value: Any, method: String): Any =
            value.javaClass.methods.single { it.name == method && it.parameterCount == 0 && !it.isBridge }.invoke(value)
                ?: error("Missing selected compiler property: " + method)
        fun codexCompilerProvider(value: Any): Any = if (value is org.gradle.api.provider.Provider<*>)
            value.get() ?: error("Missing selected compiler provider") else value
        fun codexCompilerFiles(value: Any): Set<java.io.File> =
            (value as org.gradle.api.file.FileCollection).files
        fun codexCompilerArtifact(type: Class<*>): java.io.File =
            java.io.File(type.protectionDomain.codeSource.location.toURI()).also {
                check(it.isFile) { "Compiler implementation is not an artifact" }
            }
        fun codexCompilerManifest(file: java.io.File, key: String): String = java.util.jar.JarFile(file).use {
            it.manifest?.mainAttributes?.getValue(key) ?: error("Missing compiler artifact version")
        }
        fun codexCompilerSnapshot(task: org.gradle.api.Task): Map<String, Any?> {
            val native = codexCompilerTarget !in listOf("jvm", "android", "node-js", "node-wasm")
            val family = if (native) "native" else if (codexCompilerTarget.startsWith("node-")) "js" else "jvm"
            val expectedClass = "org.jetbrains.kotlin.gradle.tasks." + when (family) {
                "native" -> "KotlinNativeCompile"; "js" -> "Kotlin2JsCompile"; else -> "KotlinCompile"
            }
            val hierarchy = generateSequence(task.javaClass as Class<*>?) { it.superclass }.toList()
            val implementation = hierarchy.single { it.name == expectedClass }
            val nativeHome = if (native) java.io.File(codexCompilerProvider(codexCompilerGet(task, "getKonanHome")).toString()) else null
            val compiler = if (native) setOf(nativeHome!!.resolve("konan/lib/kotlin-native-compiler-embeddable.jar"))
                else codexCompilerFiles(codexCompilerGet(task, "getDefaultCompilerClasspath\${'$'}kotlin_gradle_plugin_common"))
            val versionJar = compiler.single { it.name == "kotlin-native-compiler-embeddable.jar" ||
                it.name.matches(Regex("kotlin-compiler-embeddable-[0-9].*\\.jar")) }
            val compilerVersion = codexCompilerManifest(versionJar, "Implementation-Version").substringBefore("-release-")
            val plugins = codexCompilerFiles(codexCompilerGet(task,
                if (native) "getCompilerPluginClasspath" else "getPluginClasspath"))
            val javaExecutable = if (native) java.io.File(System.getProperty("java.home"),
                if (System.getProperty("os.name").startsWith("Windows")) "bin/java.exe" else "bin/java") else {
                val toolchain = codexCompilerProvider(codexCompilerGet(task, "getDefaultKotlinJavaToolchain\${'$'}kotlin_gradle_plugin_common"))
                (codexCompilerProvider(codexCompilerGet(toolchain, "getJavaExecutable\${'$'}kotlin_gradle_plugin_common"))
                    as org.gradle.api.file.RegularFile).asFile
            }
            val javaHome = javaExecutable.parentFile.parentFile
            val javaFiles = listOf(javaExecutable, javaHome.resolve("release")) +
                listOf(javaHome.resolve("lib/modules")).filter { it.exists() }
            val android = if (codexCompilerTarget == "android") {
                val plugin = task.project.plugins.getPlugin("com.android.kotlin.multiplatform.library")
                val pluginClass = generateSequence(plugin.javaClass as Class<*>?) { it.superclass }
                    .first { !it.name.endsWith("_Decorated") }
                codexCompilerArtifact(pluginClass)
            } else null
            val arguments = codexCompilerGet(task, "getSerializedCompilerArguments") as List<*>
            check(arguments.all { it is String }) { "Malformed actual compiler arguments" }
            return linkedMapOf(
                "schemaVersion" to 1, "target" to codexCompilerTarget, "task" to codexCompilerTask,
                "taskClass" to expectedClass, "family" to family, "kotlinVersion" to compilerVersion,
                "agpVersion" to android?.let { codexCompilerManifest(it, "Plugin-Version") },
                "javaExecutable" to javaExecutable.absolutePath, "nativeHome" to nativeHome?.absolutePath,
                "arguments" to arguments,
                "tools" to linkedMapOf(
                    "implementation" to codexCompilerInventory(listOf(codexCompilerArtifact(implementation))),
                    "compiler" to codexCompilerInventory(compiler), "compilerPlugins" to codexCompilerInventory(plugins),
                    "java" to codexCompilerInventory(javaFiles),
                    "native" to nativeHome?.let { codexCompilerInventory(listOf(it.resolve("konan/lib"), it.resolve("konan/konan.properties"))) },
                    "android" to android?.let { codexCompilerInventory(listOf(it)) }),
                "inputs" to codexCompilerInventory(task.inputs.files.files))
        }
        var codexCompilerBefore: Map<String, Any?>? = null
        fun codexCompilerWrite(value: Map<String, Any?>) {
            codexCompilerSafe(codexCompilerFile)
            val bytes = (groovy.json.JsonOutput.toJson(value) + "\n").toByteArray(Charsets.UTF_8)
            java.nio.file.Files.newByteChannel(codexCompilerFile.toPath(), java.nio.file.StandardOpenOption.CREATE,
                java.nio.file.StandardOpenOption.WRITE, java.nio.file.StandardOpenOption.TRUNCATE_EXISTING,
                java.nio.file.LinkOption.NOFOLLOW_LINKS).use { channel ->
                val buffer = java.nio.ByteBuffer.wrap(bytes); while (buffer.hasRemaining()) channel.write(buffer)
            }
        }
        gradle.taskGraph.beforeTask(object : org.gradle.api.Action<org.gradle.api.Task> {
            override fun execute(task: org.gradle.api.Task) {
                if (task.project == gradle.rootProject && task.name == codexCompilerTask) {
                    check(codexCompilerBefore == null && !codexCompilerFile.exists()) { "Compiler capture must be fresh" }
                    codexCompilerBefore = codexCompilerSnapshot(task)
                    codexCompilerWrite(codexCompilerBefore!! + ("outcome" to null))
                }
            }
        })
        gradle.taskGraph.afterTask(object : org.gradle.api.Action<org.gradle.api.Task> {
            override fun execute(task: org.gradle.api.Task) {
                if (task.project == gradle.rootProject && task.name == codexCompilerTask) {
                    check(codexCompilerSnapshot(task) == codexCompilerBefore) { "Selected compiler inputs changed during task" }
                    val state = task.state
                    codexCompilerWrite(codexCompilerBefore!! + ("outcome" to linkedMapOf(
                        "task" to task.name, "didWork" to state.didWork, "upToDate" to state.upToDate,
                        "skipped" to state.skipped, "skipMessage" to state.skipMessage, "failure" to state.failure?.toString())))
                }
            }
        })
    """.trimIndent() + "\n"
    // Preserve schema-1 non-native emitted bytes. Native source now emits a
    // distinct schema; historical native schema 1 is not complete new evidence.
    return if (target in setOf("jvm", "android", "node-js", "node-wasm")) script
        else sdkFacadeNativeCompilerScript(script)
}

private fun sdkFacadeNativeCompilerScript(script: String): String {
    val helpers = """
        fun codexNativeSelection(task: org.gradle.api.Task, home: java.io.File,
                arguments: List<*>, classes: ClassLoader): Map<String, Any> {
            check(arguments.none { value ->
                val flag = value.toString().substringBefore('=')
                flag in setOf("-Xoverride-konan-properties", "-Xkonan-properties", "-Xkonan-profile", "-Xoverride-konan-properties-file", "-Xllvm-variant")
            }) { "Unsupported native compiler property or directory override" }
            fun directory(file: java.io.File): java.io.File {
                codexCompilerSafe(file)
                check(file.isAbsolute && file.isDirectory && file.absoluteFile == file.canonicalFile) {
                    "Native selection directory must be exact and nonsymbolic"
                }
                return file
            }
            val data = directory(java.io.File(codexCompilerProvider(codexCompilerGet(task, "getKonanDataDir")).toString()))
            directory(home)
            val target = codexCompilerGet(task, "getKonanTarget\${'$'}kotlin_gradle_plugin_common")
            val targetName = codexCompilerGet(target, "getName").toString()
            for ((flag, expected) in mapOf("-Xkonan-data-dir" to data.absolutePath, "-Xkonan-home" to home.absolutePath,
                    "-kotlin-home" to home.absolutePath, "-target" to targetName)) {
                val indexes = arguments.indices.filter { arguments[it].toString().substringBefore('=') == flag }
                check(if (flag == "-target") indexes.size == 1 else indexes.size <= 1) {
                    "Missing or duplicate native selection argument"
                }
                for (index in indexes) {
                    val argument = arguments[index].toString()
                    val selected = if ('=' in argument) argument.substringAfter('=') else arguments.getOrNull(index + 1)
                    check(selected == expected) { "Native argument differs from task selection" }
                }
            }
            val distributionClass = classes.loadClass("org.jetbrains.kotlin.konan.target.Distribution")
            val distribution = distributionClass.constructors.single { it.parameterCount == 5 }
                .newInstance(home.absolutePath, false, data.absolutePath, null, null)
            val dependencies = directory(java.io.File(codexCompilerGet(distribution, "getDependenciesDir").toString()))
            check(dependencies == data.resolve("dependencies")) { "Unexpected selected native dependency directory" }
            val managerClass = classes.loadClass("org.jetbrains.kotlin.konan.target.PlatformManager")
            val manager = managerClass.getConstructor(distributionClass).newInstance(distribution)
            val loader = managerClass.methods.single { it.name == "loader" && it.parameterCount == 1 }.invoke(manager, target)
            val hostPlatform = codexCompilerGet(manager, "getHostPlatform")
            val host = codexCompilerGet(codexCompilerGet(hostPlatform, "getTarget"), "getName").toString()
            fun selectedRoot(path: String): java.io.File {
                val root = directory(java.io.File(path))
                check(root.parentFile == dependencies && root.name.matches(Regex("[A-Za-z0-9_.-]+")) &&
                    root.name !in setOf(".", "..")) { "Native dependency is outside the selected directory" }
                return root
            }
            val names = codexCompilerGet(loader, "getDependencies") as List<*>
            check(names.all { it is String && it.matches(Regex("[A-Za-z0-9_.-]+")) && it !in setOf(".", "..") }) {
                "Unsafe selected native dependency name"
            }
            val absolute = loader.javaClass.methods.single { it.name == "absolute" && it.parameterCount == 1 }
            val llvm = selectedRoot(codexCompilerGet(loader, "getAbsoluteLlvmHome").toString())
            val libffi = selectedRoot(absolute.invoke(loader, codexCompilerGet(loader, "getLibffiDir")).toString())
            val roots = (names.map { selectedRoot(dependencies.resolve(it.toString()).absolutePath) } + llvm + libffi)
                .distinctBy { it.name }.sortedBy { it.name }
            check(roots.isNotEmpty()) { "Missing selected native dependencies" }
            val rows = roots.map { root ->
                val regular = mutableListOf<java.io.File>()
                val links = mutableListOf<Map<String, String>>()
                java.nio.file.Files.walk(root.toPath()).use { entries ->
                    entries.sorted().forEach { path ->
                        check(path.toString().none(Char::isISOControl)) { "Unsafe native dependency path" }
                        if (java.nio.file.Files.isSymbolicLink(path)) {
                            val link = java.nio.file.Files.readSymbolicLink(path)
                            check(!link.isAbsolute && link.toString().isNotEmpty() && link.toString().none(Char::isISOControl) &&
                                path.parent.resolve(link).normalize().startsWith(root.toPath()) &&
                                path.toRealPath().startsWith(root.toPath())) { "Unsafe native dependency symbolic link" }
                            links.add(linkedMapOf("path" to path.toString(), "target" to link.toString()))
                        } else if (!java.nio.file.Files.isDirectory(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                            check(java.nio.file.Files.isRegularFile(path, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
                                "Unsupported native dependency entry"
                            }
                            regular.add(path.toFile())
                        }
                    }
                }
                check(regular.isNotEmpty()) { "Empty selected native dependency" }
                linkedMapOf<String, Any>("name" to root.name, "root" to root.absolutePath,
                    "inventory" to codexCompilerInventory(regular), "symlinks" to links.sortedBy { it.getValue("path") })
            }
            return linkedMapOf("dataDirectory" to data.absolutePath, "dependenciesDirectory" to dependencies.absolutePath,
                "host" to host, "target" to targetName,
                "fingerprint" to codexCompilerInventory(listOf(home.resolve("konan/compiler.fingerprint"))),
                "dependencies" to rows)
        }
    """.trimIndent() + "\n"
    return script.replace("fun codexCompilerSnapshot(", helpers + "fun codexCompilerSnapshot(")
        .replace("\"schemaVersion\" to 1,", "\"schemaVersion\" to 2, \"nativeSelection\" to codexNativeSelection(task, nativeHome!!, arguments, implementation.classLoader),")
}

private fun requireFacadeCompilerPath(value: String) {
    check(value.isNotEmpty() && value.none(Char::isISOControl)) { "Invalid original compiler path" }
    val unc = value.startsWith("\\\\")
    val windows = unc || Regex("^[A-Za-z]:\\\\").containsMatchIn(value)
    val separator = if (windows) '\\' else '/'
    check(if (windows) '/' !in value else value.startsWith('/') && '\\' !in value) { "Compiler path must be absolute" }
    val parts = value.drop(if (unc) 2 else if (windows) 3 else 1).split(separator)
    check((!unc || parts.size >= 3) && parts.all { it.isNotEmpty() && it != "." && it != ".." }) {
        "Compiler path must be normalized"
    }
}

/**
 * Replays authenticated raw structure, observed inventory hashes and source-version comparisons.
 * Does not read original absolute paths or authenticate their contents against reviewed tool pins.
 * Complete Core compiler/JDK/native policy and original execution authority remain caller obligations.
 */
internal fun verifySdkFacadeCompilerCapture(file: File, target: String, kotlinVersion: String, expectedAgpVersion: String) {
    requireApplePackagePathWithoutSymlinks(file, "facade compiler capture")
    val before = file.readBytes()
    val value = file.readReleaseObject()
    val observedRows = mutableMapOf<String, JsonObject>()
    val observedLinks = mutableSetOf<String>()
    fun text(obj: JsonObject, key: String): String {
        val primitive = obj[key] as? JsonPrimitive ?: error("Missing compiler capture field: $key")
        check(primitive.isString && primitive.content.isNotEmpty()) { "Malformed compiler capture field: $key" }
        return primitive.content
    }
    fun inventory(element: kotlinx.serialization.json.JsonElement?, allowEmpty: Boolean = false): List<String> {
        val obj = element as? JsonObject ?: error("Missing selected compiler inventory")
        check(obj.keys == setOf("files", "sha256")) { "Unknown compiler inventory fields" }
        val rows = obj["files"] as? JsonArray ?: error("Missing compiler inventory rows")
        check(allowEmpty || rows.isNotEmpty()) { "Empty selected compiler inventory" }
        val paths = mutableListOf<String>()
        val encoded = rows.joinToString("") { row ->
            val item = row as? JsonObject ?: error("Invalid compiler inventory row")
            check(item.keys == setOf("path", "bytes", "sha256")) { "Unknown compiler inventory row fields" }
            val path = text(item, "path").also(::requireFacadeCompilerPath)
            val size = (item["bytes"] as? JsonPrimitive)?.takeUnless { it.isString }?.longOrNull
            check(size != null && size >= 0) { "Invalid compiler input byte count" }
            val digest = text(item, "sha256")
            check(digest.matches(Regex("[0-9a-f]{64}"))) { "Invalid compiler input digest" }
            val previous = observedRows.putIfAbsent(path, item)
            check(previous == null || previous == item) { "Contradictory selected compiler input inventories" }
            paths.add(path)
            "$path\u0000$size\u0000$digest\n"
        }
        check(paths == paths.distinct().sorted()) { "Compiler inventory must be sorted and unique" }
        val digest = MessageDigest.getInstance("SHA-256").digest(encoded.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        check(text(obj, "sha256") == digest) { "Compiler inventory digest mismatch" }
        return paths
    }
    try {
        val task = sdkFacadeConsumerCompileTasks[target] ?: error("Unsupported facade compiler target")
        val family = when (target) { "jvm", "android" -> "jvm"; "node-js", "node-wasm" -> "js"; else -> "native" }
        val type = when (family) { "native" -> "KotlinNativeCompile"; "js" -> "Kotlin2JsCompile"; else -> "KotlinCompile" }
        val native = family == "native"
        check(value.keys == (setOf("schemaVersion", "target", "task", "taskClass", "family", "kotlinVersion",
            "agpVersion", "javaExecutable", "nativeHome", "arguments", "tools", "inputs", "outcome") +
            if (native) setOf("nativeSelection") else emptySet())) {
            "Unknown or missing compiler capture fields"
        }
        check(value["schemaVersion"] == JsonPrimitive(if (native) 2 else 1) && text(value, "target") == target && text(value, "task") == task &&
            text(value, "family") == family && text(value, "taskClass") == "org.jetbrains.kotlin.gradle.tasks.$type") {
            "Compiler capture target or task family differs"
        }
        check(kotlinVersion.isNotBlank() && text(value, "kotlinVersion") == kotlinVersion) { "Selected Kotlin version differs from original source" }
        check(value["agpVersion"] == if (target == "android") JsonPrimitive(expectedAgpVersion) else JsonNull) {
            "Selected AGP version differs from original source"
        }
        val arguments = value["arguments"] as? JsonArray ?: error("Missing actual compiler arguments")
        check(arguments.isNotEmpty() && arguments.all { it is JsonPrimitive && it.isString && '\u0000' !in it.content }) {
            "Invalid actual compiler arguments"
        }
        val tools = value["tools"] as? JsonObject ?: error("Missing selected compiler tools")
        check(tools.keys == setOf("implementation", "compiler", "compilerPlugins", "java", "native", "android")) {
            "Unknown or missing selected compiler families"
        }
        inventory(tools["implementation"])
        val compiler = inventory(tools["compiler"])
        check(compiler.any { it.substringAfterLast('/').substringAfterLast('\\').let { name ->
            if (family == "native") name == "kotlin-native-compiler-embeddable.jar"
            else name == "kotlin-compiler-embeddable-$kotlinVersion.jar"
        } }) { "Selected compiler artifact is missing" }
        inventory(tools["compilerPlugins"], allowEmpty = true)
        val java = text(value, "javaExecutable").also(::requireFacadeCompilerPath)
        val javaPaths = inventory(tools["java"])
        val javaSeparator = if ('\\' in java) '\\' else '/'
        val javaHome = java.substringBeforeLast(javaSeparator).substringBeforeLast(javaSeparator)
        check(java in javaPaths && "$javaHome${javaSeparator}release" in javaPaths) { "Selected Java launcher/runtime is not inventoried" }
        if (family == "native") {
            val home = text(value, "nativeHome").also(::requireFacadeCompilerPath)
            val separator = if ('\\' in home) "\\" else "/"
            val nativePaths = inventory(tools["native"])
            check(nativePaths.all { it.startsWith(home + separator) } &&
                "$home${separator}konan${separator}konan.properties" in nativePaths && compiler.all { it in nativePaths }) {
                "Native compiler inventory is outside selected distribution"
            }
            val selection = value["nativeSelection"] as? JsonObject ?: error("Native schema 1 lacks selected dependency evidence")
            check(selection.keys == setOf("dataDirectory", "dependenciesDirectory", "host", "target", "fingerprint", "dependencies")) {
                "Unknown native selection fields"
            }
            val data = text(selection, "dataDirectory").also(::requireFacadeCompilerPath)
            val dependenciesRoot = text(selection, "dependenciesDirectory").also(::requireFacadeCompilerPath)
            check(dependenciesRoot == data + separator + "dependencies") { "Native dependency directory differs from selected data directory" }
            val argumentValues = arguments.map { (it as JsonPrimitive).content }
            check(argumentValues.none { it.substringBefore('=') in setOf("-Xoverride-konan-properties",
                "-Xkonan-properties", "-Xkonan-profile", "-Xoverride-konan-properties-file", "-Xllvm-variant") }) { "Unsupported native property override" }
            for ((flag, expected) in mapOf("-Xkonan-data-dir" to data, "-Xkonan-home" to home,
                    "-kotlin-home" to home, "-target" to text(selection, "target"))) {
                val indexes = argumentValues.indices.filter { argumentValues[it].substringBefore('=') == flag }
                check(if (flag == "-target") indexes.size == 1 else indexes.size <= 1) {
                    "Missing or duplicate native selection argument"
                }
                indexes.forEach { index ->
                    val argument = argumentValues[index]
                    val selected = if ('=' in argument) argument.substringAfter('=') else argumentValues.getOrNull(index + 1)
                    check(selected == expected) { "Native argument differs from selection" }
                }
            }
            val konanTarget = when (target) {
                "ios-simulator-arm64" -> "ios_simulator_arm64"
                "windows-x64" -> "mingw_x64"
                else -> target.replace('-', '_')
            }
            check(text(selection, "target") == konanTarget && text(selection, "host") in
                setOf("macos_arm64", "macos_x64", "linux_x64", "linux_arm64", "mingw_x64")) { "Invalid native host or target selection" }
            check(inventory(selection["fingerprint"]) == listOf("$home${separator}konan${separator}compiler.fingerprint")) {
                "Native compiler fingerprint differs from selected distribution"
            }
            val records = selection["dependencies"] as? JsonArray ?: error("Missing native dependencies")
            check(records.isNotEmpty()) { "Empty selected native dependencies" }
            val names = records.map { record ->
                val dependency = record as? JsonObject ?: error("Invalid native dependency")
                check(dependency.keys == setOf("name", "root", "inventory", "symlinks")) { "Unknown native dependency fields" }
                val name = text(dependency, "name")
                check(name.matches(Regex("[A-Za-z0-9_.-]+")) && name !in setOf(".", "..")) { "Unsafe native dependency name" }
                val root = text(dependency, "root").also(::requireFacadeCompilerPath)
                check(root == dependenciesRoot + separator + name) { "Native dependency root differs from selection" }
                val files = inventory(dependency["inventory"])
                check(files.all { it.startsWith(root + separator) }) { "Native dependency inventory escapes its root" }
                val links = dependency["symlinks"] as? JsonArray ?: error("Missing native symbolic link inventory")
                val linkMap = linkedMapOf<String, String>()
                links.forEach { item ->
                    val link = item as? JsonObject ?: error("Invalid native symbolic link")
                    check(link.keys == setOf("path", "target")) { "Unknown native symbolic link fields" }
                    val path = text(link, "path").also(::requireFacadeCompilerPath)
                    check(path.startsWith(root + separator) && path !in files && path !in observedRows && observedLinks.add(path) &&
                        linkMap.put(path, text(link, "target")) == null) { "Invalid native symbolic link path" }
                }
                check(linkMap.keys.toList() == linkMap.keys.sorted()) { "Native symbolic links must be sorted" }
                check(files.none { file -> linkMap.keys.any { file.startsWith(it + separator) } } &&
                    linkMap.keys.none { link -> linkMap.keys.any { it != link && link.startsWith(it + separator) } }) {
                    "Native inventory traverses a symbolic link"
                }
                fun resolveLink(path: String, visited: Set<String>): String {
                    check(path !in visited) { "Cyclic native symbolic link" }
                    val targetPath = linkMap.getValue(path)
                    check(targetPath.none(Char::isISOControl) && !targetPath.startsWith('/') && !targetPath.startsWith('\\') &&
                        !Regex("^[A-Za-z]:").containsMatchIn(targetPath) &&
                        (if (separator == "\\") '/' !in targetPath else '\\' !in targetPath)) { "Unsafe native symbolic link target" }
                    var resolved = path.substringBeforeLast(separator)
                    targetPath.split(separator).forEach { part ->
                        when (part) {
                            "", "." -> Unit
                            ".." -> {
                                check(resolved != root) { "Native symbolic link escapes dependency" }
                                resolved = resolved.substringBeforeLast(separator)
                            }
                            else -> {
                                resolved += separator + part
                                if (resolved in linkMap) resolved = resolveLink(resolved, visited + path)
                            }
                        }
                    }
                    check(resolved == root || resolved in files || files.any { it.startsWith(resolved + separator) }) {
                        "Native symbolic link target is not inventoried"
                    }
                    return resolved
                }
                linkMap.keys.forEach { resolveLink(it, emptySet()) }
                name
            }
            check(names == names.distinct().sorted()) { "Native dependencies must be sorted and unique" }
        } else check(value["nativeHome"] == JsonNull && tools["native"] == JsonNull) { "Unexpected native compiler family" }
        if (target == "android") { check(expectedAgpVersion.isNotBlank()); inventory(tools["android"]) }
        else check(tools["android"] == JsonNull) { "Unexpected Android compiler family" }
        inventory(value["inputs"])
        check(observedRows.keys.none { file -> observedLinks.any { link ->
            file == link || file.startsWith(link + if ('\\' in link) "\\" else "/")
        } }) { "Compiler input inventory traverses a native symbolic link" }
        val outcome = value["outcome"] as? JsonObject ?: error("Compiler task did not complete")
        check(outcome.keys == setOf("task", "didWork", "upToDate", "skipped", "skipMessage", "failure") &&
            text(outcome, "task") == task && outcome["failure"] == JsonNull &&
            listOf("didWork", "upToDate", "skipped").all {
                (outcome[it] as? JsonPrimitive)?.takeUnless { field -> field.isString }?.booleanOrNull != null
            } &&
            (outcome["skipMessage"] == JsonNull || (outcome["skipMessage"] as? JsonPrimitive)?.isString == true) &&
            (outcome["didWork"] == JsonPrimitive(true) || outcome["upToDate"] == JsonPrimitive(true))) {
            "Selected compiler task did not satisfy the existing successful execution predicate"
        }
    } finally {
        requireApplePackagePathWithoutSymlinks(file, "facade compiler capture")
        check(file.readBytes().contentEquals(before)) { "Compiler capture changed during replay" }
    }
}
