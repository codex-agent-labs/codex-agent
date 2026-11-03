import java.io.File
import java.security.MessageDigest
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.gradle.testkit.runner.GradleRunner

/** Synthetic observations exercise replay, not actual Kotlin/AGP/native or hosted execution. */
internal fun facadeCompilerCaptureFixture(target: String = "jvm", kotlinVersion: String = "2.3.10"): JsonObject {
    fun inventory(vararg paths: String): JsonObject {
        val rows = paths.sorted().map { path -> buildJsonObject {
            put("path", path); put("bytes", 3); put("sha256", "a".repeat(64))
        } }
        val encoded = paths.sorted().joinToString("") { "$it\u00003\u0000${"a".repeat(64)}\n" }
        val digest = MessageDigest.getInstance("SHA-256").digest(encoded.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        return buildJsonObject { put("files", JsonArray(rows)); put("sha256", digest) }
    }
    val family = when (target) { "jvm", "android" -> "jvm"; "node-js", "node-wasm" -> "js"; else -> "native" }
    val type = when (family) { "native" -> "KotlinNativeCompile"; "js" -> "Kotlin2JsCompile"; else -> "KotlinCompile" }
    val task = sdkFacadeConsumerCompileTasks.getValue(target)
    val konanTarget = when (target) {
        "windows-x64" -> "mingw_x64"
        "ios-simulator-arm64" -> "ios_simulator_arm64"
        else -> target.replace('-', '_')
    }
    return buildJsonObject {
        put("schemaVersion", if (family == "native") 2 else 1); put("target", target); put("task", task)
        put("taskClass", "org.jetbrains.kotlin.gradle.tasks.$type"); put("family", family)
        put("kotlinVersion", kotlinVersion)
        put("agpVersion", if (target == "android") JsonPrimitive("9.2.1") else JsonNull)
        put("javaExecutable", "/jdk/bin/java")
        put("nativeHome", if (family == "native") JsonPrimitive("/konan") else JsonNull)
        if (family == "native") put("nativeSelection", buildJsonObject {
            put("dataDirectory", "/selected-data"); put("dependenciesDirectory", "/selected-data/dependencies")
            put("host", "macos_arm64")
            put("target", konanTarget)
            put("fingerprint", inventory("/konan/konan/compiler.fingerprint"))
            put("dependencies", JsonArray(listOf("libffi", "llvm").map { name -> buildJsonObject {
                val root = "/selected-data/dependencies/$name"
                put("name", name); put("root", root)
                put("inventory", inventory("$root/bin/tool"))
                put("symlinks", JsonArray(listOf(buildJsonObject { put("path", "$root/bin/alias"); put("target", "tool") })))
            } }))
        })
        put("arguments", JsonArray((if (family == "native") listOf("-target", konanTarget)
            else listOf("-version")).map(::JsonPrimitive)))
        put("tools", buildJsonObject {
            put("implementation", inventory("/cache/kotlin-gradle-plugin.jar"))
            put("compiler", inventory(if (family == "native") "/konan/konan/lib/kotlin-native-compiler-embeddable.jar"
                else "/cache/kotlin-compiler-embeddable-$kotlinVersion.jar"))
            put("compilerPlugins", inventory())
            put("java", inventory("/jdk/bin/java", "/jdk/release"))
            put("native", if (family == "native") inventory("/konan/konan/lib/kotlin-native-compiler-embeddable.jar",
                "/konan/konan/konan.properties") else JsonNull)
            put("android", if (target == "android") inventory("/cache/gradle-9.2.1.jar") else JsonNull)
        })
        put("inputs", inventory("/consumer/src/commonMain/kotlin/Consumer.kt"))
        put("outcome", buildJsonObject {
            put("task", task); put("didWork", true); put("upToDate", false); put("skipped", false)
            put("skipMessage", JsonNull); put("failure", JsonNull)
        })
    }
}

class SdkFacadeCompilerCaptureTest {
    @Test
    fun `all eleven target families replay without reading original tool paths`() = fixture { file ->
        sdkFacadeConsumerCompileTasks.keys.forEach { target ->
            file.atomicWriteJson(facadeCompilerCaptureFixture(target))
            verifySdkFacadeCompilerCapture(file, target, "2.3.10", "9.2.1")
        }
    }

    @Test
    fun `unknown missing foreign family and version observations reject`() = fixture { file ->
        val original = facadeCompilerCaptureFixture()
        val mutations = listOf(
            original + ("extra" to JsonPrimitive(true)), original - "tools",
            original + ("target" to JsonPrimitive("android")), original + ("task" to JsonPrimitive("help")),
            original + ("family" to JsonPrimitive("native")), original + ("taskClass" to JsonPrimitive("org.gradle.api.DefaultTask")),
            original + ("kotlinVersion" to JsonPrimitive("2.2.0")), original + ("agpVersion" to JsonPrimitive("9.2.1")),
            original + ("nativeHome" to JsonPrimitive("/konan")), original + ("arguments" to JsonArray(emptyList())),
            original + ("outcome" to JsonNull), original + ("javaExecutable" to JsonPrimitive("/different/bin/java")),
        )
        mutations.forEach { value ->
            file.atomicWriteJson(JsonObject(value))
            assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "jvm", "2.3.10", "9.2.1") }
        }
        file.atomicWriteJson(facadeCompilerCaptureFixture("android"))
        assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "android", "2.3.10", "9.1.0") }
    }

    @Test
    fun `inventory tampering and missing required compiler families reject`() = fixture { file ->
        val original = facadeCompilerCaptureFixture()
        val tools = original.getValue("tools") as JsonObject
        val compiler = tools.getValue("compiler") as JsonObject
        val changedDigest = JsonObject(compiler + ("sha256" to JsonPrimitive("b".repeat(64))))
        val mutations = listOf(
            JsonObject(tools - "compiler"), JsonObject(tools + ("compiler" to JsonNull)),
            JsonObject(tools + ("native" to compiler)),
            JsonObject(tools + ("compiler" to changedDigest)),
        )
        mutations.forEach { value ->
            file.atomicWriteJson(JsonObject(original + ("tools" to value)))
            assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "jvm", "2.3.10", "9.2.1") }
        }
    }

    @Test
    fun `task state preserves existing up-to-date semantics and rejects no-source and failures`() = fixture { file ->
        val original = facadeCompilerCaptureFixture()
        val outcome = original.getValue("outcome") as JsonObject
        fun verify(changes: Map<String, JsonElement>) {
            file.atomicWriteJson(JsonObject(original + ("outcome" to JsonObject(outcome + changes))))
            verifySdkFacadeCompilerCapture(file, "jvm", "2.3.10", "9.2.1")
        }
        verify(mapOf("didWork" to JsonPrimitive(false), "upToDate" to JsonPrimitive(true),
            "skipped" to JsonPrimitive(true), "skipMessage" to JsonPrimitive("UP-TO-DATE")))
        assertFailsWith<IllegalStateException> { verify(mapOf("didWork" to JsonPrimitive(false),
            "skipped" to JsonPrimitive(true), "skipMessage" to JsonPrimitive("NO-SOURCE"))) }
        assertFailsWith<IllegalStateException> { verify(mapOf("failure" to JsonPrimitive("compiler failed"))) }
    }

    @Test
    fun `script uses exact selected getters and supports lexical Windows output`() {
        val path = "C:\\worker\\compiler-inputs.json"
        val script = sdkFacadeCompilerCaptureScript("windows-x64", path)
        assertTrue(script.contains("getDefaultCompilerClasspath\\\$kotlin_gradle_plugin_common"))
        assertTrue(script.contains("getSerializedCompilerArguments"))
        assertTrue(script.contains("getKonanHome"))
        assertTrue(script.contains("getKonanDataDir"))
        assertTrue(script.contains("getKonanTarget\\\$kotlin_gradle_plugin_common"))
        assertTrue(script.contains("getDependencies"))
        assertTrue(script.contains("compiler.fingerprint"))
        assertTrue(script.contains("path.toRealPath().startsWith(root.toPath())"))
        assertTrue(script.contains("codexCompilerSnapshot(task) == codexCompilerBefore"))
        assertTrue(script.contains("C:\\\\worker\\\\compiler-inputs.json"))
        assertEquals(script, sdkFacadeCompilerCaptureScript("windows-x64", path))
        assertFailsWith<IllegalStateException> { sdkFacadeCompilerCaptureScript("jvm", "/tmp/../capture") }
    }

    @Test
    fun `non-native generated script retains schema one without native extension`() {
        listOf("jvm", "android", "node-js", "node-wasm").forEach { target ->
            val script = sdkFacadeCompilerCaptureScript(target, "/original/compiler-inputs.json")
            assertTrue(script.contains("\"schemaVersion\" to 1,"))
            assertFalse(script.contains("nativeSelection"))
            assertFalse(script.contains("fun codexNativeSelection"))
        }
    }

    @Test
    fun `native v1 is retained diagnostic evidence not complete new replay`() = fixture { file ->
        val original = facadeCompilerCaptureFixture("macos-arm64")
        file.atomicWriteJson(JsonObject(original - "nativeSelection" + ("schemaVersion" to JsonPrimitive(1))))
        val before = file.readBytes()
        assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "macos-arm64", "2.3.10", "9.2.1") }
        assertTrue(before.contentEquals(file.readBytes()))
    }

    @Test
    fun `native selection requires exact paths fingerprints targets and sorted unique dependencies`() = fixture { file ->
        val original = facadeCompilerCaptureFixture("macos-arm64")
        val selection = original.getValue("nativeSelection") as JsonObject
        val dependencies = selection.getValue("dependencies") as JsonArray
        val first = dependencies.first() as JsonObject
        val mutations = listOf(
            selection - "fingerprint", selection + ("extra" to JsonNull),
            selection + ("dataDirectory" to JsonPrimitive("/different")),
            selection + ("dependenciesDirectory" to JsonPrimitive("/selected-data/../dependencies")),
            selection + ("host" to JsonPrimitive("arbitrary-host")),
            selection + ("target" to JsonPrimitive("ios_arm64")),
            selection + ("fingerprint" to first.getValue("inventory")),
            selection + ("dependencies" to JsonArray(emptyList())),
            selection + ("dependencies" to JsonArray(dependencies.reversed())),
            selection + ("dependencies" to JsonArray(listOf(first, first))),
            selection + ("dependencies" to JsonArray(listOf(JsonObject(first + ("name" to JsonPrimitive("../foreign")))))),
            selection + ("dependencies" to JsonArray(listOf(JsonObject(first + ("root" to JsonPrimitive("/unselected/cache")))))),
        )
        mutations.forEach { changed ->
            file.atomicWriteJson(JsonObject(original + ("nativeSelection" to JsonObject(changed))))
            assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "macos-arm64", "2.3.10", "9.2.1") }
        }
    }

    @Test
    fun `native symbolic links cannot escape dangle cycle or overlap regular inputs`() = fixture { file ->
        val original = facadeCompilerCaptureFixture("macos-arm64")
        val selection = original.getValue("nativeSelection") as JsonObject
        val dependencies = selection.getValue("dependencies") as JsonArray
        val first = dependencies.first() as JsonObject
        val root = (first.getValue("root") as JsonPrimitive).content
        fun link(path: String, target: String) = buildJsonObject { put("path", path); put("target", target) }
        val mutations = listOf(
            listOf(link("$root/bin/alias", "/outside")),
            listOf(link("$root/bin/alias", "../../outside")),
            listOf(link("$root/bin/alias", "C:\\outside")),
            listOf(link("$root/bin/alias", "missing")),
            listOf(link("$root/bin/alias", "alias")),
            listOf(link("$root/bin/alias", "alias/../tool")),
            listOf(link("$root/bin/alias", "second"), link("$root/bin/second", "alias")),
            listOf(link("$root/bin/tool", "alias")),
            listOf(link("$root/bin", "bin/tool")),
            listOf(link("/other/alias", "tool")),
            listOf(link("$root/bin/alias", "tool"), link("$root/bin/alias", "tool")),
        )
        mutations.forEach { links ->
            val changed = JsonObject(first + ("symlinks" to JsonArray(links)))
            file.atomicWriteJson(JsonObject(original + ("nativeSelection" to JsonObject(selection +
                ("dependencies" to JsonArray(listOf(changed, dependencies[1])))))))
            assertFailsWith<IllegalStateException> { verifySdkFacadeCompilerCapture(file, "macos-arm64", "2.3.10", "9.2.1") }
        }
    }

    @Test
    fun `native selected directory arguments bind both flag forms and reject overrides`() = fixture { file ->
        val original = facadeCompilerCaptureFixture("macos-arm64")
        fun verify(arguments: List<String>) {
            file.atomicWriteJson(JsonObject(original + ("arguments" to JsonArray(
                (listOf("-target", "macos_arm64") + arguments).map(::JsonPrimitive)))))
            verifySdkFacadeCompilerCapture(file, "macos-arm64", "2.3.10", "9.2.1")
        }
        verify(listOf("-Xkonan-data-dir=/selected-data", "-Xkonan-home", "/konan"))
        verify(listOf("-Xkonan-data-dir", "/selected-data", "-Xkonan-home=/konan"))
        listOf(listOf("-Xkonan-data-dir"), listOf("-Xkonan-data-dir=/other"),
            listOf("-Xkonan-data-dir=/selected-data", "-Xkonan-data-dir", "/selected-data"),
            listOf("-Xkonan-home", "/other"), listOf("-Xoverride-konan-properties=llvmHome=/other"),
            listOf("-Xoverride-konan-properties", "llvmHome=/other"), listOf("-Xkonan-properties=/other")
        ).forEach { arguments -> assertFailsWith<IllegalStateException> { verify(arguments) } }
    }

    @Test
    fun `native serialized target is required exactly once and matches task selection`() = fixture { file ->
        val original = facadeCompilerCaptureFixture("macos-arm64")
        fun verify(arguments: List<String>) {
            file.atomicWriteJson(JsonObject(original + ("arguments" to JsonArray(arguments.map(::JsonPrimitive)))))
            verifySdkFacadeCompilerCapture(file, "macos-arm64", "2.3.10", "9.2.1")
        }
        verify(listOf("-target", "macos_arm64"))
        verify(listOf("-target=macos_arm64"))
        listOf(listOf("-version"), listOf("-target"), listOf("-target="),
            listOf("-target", "ios_arm64"), listOf("-target=ios_arm64"),
            listOf("-target=macos_arm64", "-target", "macos_arm64"),
            listOf("-target", "macos_arm64", "-target", "ios_arm64")
        ).forEach { arguments -> assertFailsWith<IllegalStateException> { verify(arguments) } }
        val script = sdkFacadeCompilerCaptureScript("macos-arm64", "/original/compiler-inputs.json")
        assertTrue(script.contains("\"-target\" to targetName"))
        assertTrue(script.contains("if (flag == \"-target\") indexes.size == 1"))
    }

    @Test
    fun `generated script compiles offline and refuses a task without actual Kotlin inputs`() {
        val root = createTempDirectory("facade-compiler-script-").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"compiler-script-check\"\n")
            root.resolve("build.gradle.kts").writeText("tasks.register(\"compileKotlinJvm\")\n")
            val output = root.resolve("compiler-inputs.json")
            val script = root.resolve("capture.init.gradle.kts").apply {
                writeText(sdkFacadeCompilerCaptureScript("jvm", output))
            }
            fun runner(task: String) = GradleRunner.create().withProjectDir(root).withArguments(
                task, "--offline", "--no-configuration-cache", "--console=plain", "--init-script", script.path)
            runner("help").build()
            assertFalse(output.exists())
            runner("compileKotlinJvm").buildAndFail()
            assertFalse(output.exists())
            // Compile the native-only extension too, without configuring KGP or
            // invoking any compiler or downloading native dependencies.
            script.writeText(sdkFacadeCompilerCaptureScript("macos-arm64", output))
            runner("help").build()
            assertFalse(output.exists())
        } finally { root.deleteRecursively() }
    }

    private fun fixture(block: (File) -> Unit) {
        val root = createTempDirectory("facade-compiler-capture-").toFile().canonicalFile
        try { block(root.resolve("compiler-inputs.json")) } finally { root.deleteRecursively() }
    }
}
