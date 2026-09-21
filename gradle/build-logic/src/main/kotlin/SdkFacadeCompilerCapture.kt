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
    return """
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
        check(value.keys == setOf("schemaVersion", "target", "task", "taskClass", "family", "kotlinVersion",
            "agpVersion", "javaExecutable", "nativeHome", "arguments", "tools", "inputs", "outcome")) {
            "Unknown or missing compiler capture fields"
        }
        check(value["schemaVersion"] == JsonPrimitive(1) && text(value, "target") == target && text(value, "task") == task &&
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
        } else check(value["nativeHome"] == JsonNull && tools["native"] == JsonNull) { "Unexpected native compiler family" }
        if (target == "android") { check(expectedAgpVersion.isNotBlank()); inventory(tools["android"]) }
        else check(tools["android"] == JsonNull) { "Unexpected Android compiler family" }
        inventory(value["inputs"])
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
