import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.FileTime
import java.util.zip.GZIPInputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.gradle.testfixtures.ProjectBuilder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

class JavaScriptSdkPackageTest {
    companion object {
        // A local control fixture, never an approved production runtime identity.
        private val fixturePolicy: JsonObject by lazy {
            val home = File(System.getProperty("java.home")).canonicalFile
            val mac = System.getProperty("os.name") == "Mac OS X"
            val suffix = if (mac) ".dylib" else ".so"
            fun record(name: String, bytes: ByteArray) = JsonObject(mapOf(
                "relativePath" to JsonPrimitive(name), "bytes" to JsonPrimitive(bytes.size),
                "sha256" to JsonPrimitive("sha256:" + bytes.inputStream().releaseDigest()),
            ))
            val paths = listOf("bin/java", "lib/modules", "release", "lib/libjava$suffix",
                "lib/libjli$suffix", "lib/libzip$suffix", "lib/server/libjvm$suffix").sorted()
            val loader = org.apache.commons.compress.archivers.tar.TarArchiveOutputStream::class.java.classLoader
            val pom = "META-INF/maven/org.apache.commons/commons-compress/pom.properties"
            val names = (listOf(pom) + listOf("TarArchiveEntry", "TarArchiveOutputStream", "TarUtils")
                .map { "org/apache/commons/compress/archivers/tar/$it.class" }).sorted()
            val properties = java.util.Properties().apply { loader.getResourceAsStream(pom)!!.use { load(it) } }
            JsonObject(mapOf(
                "schemaVersion" to JsonPrimitive(1),
                "javaArchiveSha256" to JsonPrimitive("sha256:" + "0".repeat(64)),
                "runner" to JsonObject(mapOf("os" to JsonPrimitive(if (mac) "macOS" else "Linux"),
                    "arch" to JsonPrimitive(if (System.getProperty("os.arch") in setOf("aarch64", "arm64")) "ARM64" else "X64"))),
                "javaRuntime" to JsonObject(mapOf(
                    "arch" to JsonPrimitive(System.getProperty("os.arch")),
                    "binarySha256" to JsonPrimitive("sha256:" + home.resolve("bin/java").releaseDigest()),
                    "runtimeVersion" to JsonPrimitive(System.getProperty("java.runtime.version")),
                    "vendor" to JsonPrimitive(System.getProperty("java.vendor")),
                    "vendorVersion" to JsonPrimitive(System.getProperty("java.vendor.version", "")),
                    "vmName" to JsonPrimitive(System.getProperty("java.vm.name")),
                    "vmVersion" to JsonPrimitive(System.getProperty("java.vm.version")),
                )),
                "javaFiles" to JsonArray(paths.map { name -> JsonObject(mapOf(
                    "relativePath" to JsonPrimitive(name), "bytes" to JsonPrimitive(home.resolve(name).length()),
                    "sha256" to JsonPrimitive("sha256:" + home.resolve(name).releaseDigest()),
                )) }),
                "commonsCompress" to JsonObject(mapOf("version" to JsonPrimitive(properties.getProperty("version")),
                    "resources" to JsonArray(names.map { record(it, loader.getResourceAsStream(it)!!.use { stream -> stream.readBytes() }) }))),
            ))
        }
    }

    private fun writePolicy(root: File, value: JsonObject = fixturePolicy): File {
        fun canonical(element: JsonElement): JsonElement = when (element) {
            is JsonObject -> JsonObject(element.toSortedMap().mapValues { canonical(it.value) })
            is JsonArray -> JsonArray(element.map(::canonical))
            else -> element
        }
        return root.resolve("codec-policy.json").also {
            it.writeText(Json.encodeToString(JsonElement.serializer(), canonical(value)) + "\n")
        }
    }

    private fun withRoot(action: (File) -> Unit) {
        val root = createTempDirectory("javascript-package-control-").toFile().canonicalFile
        try { action(root) } finally { root.deleteRecursively() }
    }

    @Test
    fun `archive task and direct producer share the same deterministic writer`() = withRoot { root ->
        val stage = root.resolve("stage").also { it.mkdirs() }
        val names = listOf("empty.txt", "dist/entry.js", "nested/" + "long-".repeat(30) + "ü.json")
        names.reversed().forEach { name ->
            stage.resolve(name).apply { parentFile.mkdirs(); writeText(if (name == "empty.txt") "" else name) }
        }
        val direct = root.resolve("direct.tgz")
        writeJavaScriptSdkArchive(stage, direct)
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "packFixture", PackageJavaScriptSdkTask::class.java,
        ).apply {
            stageDirectory.set(stage)
            archiveFile.set(root.resolve("task.tgz"))
            archivePolicyFile.set(writePolicy(root))
        }
        verifiedRegularFiles(stage).values.forEach { file ->
            Files.setLastModifiedTime(file.toPath(), FileTime.fromMillis(1_700_000_000_000L))
            file.setExecutable(true)
        }
        task.archive()
        assertContentEquals(direct.readBytes(), task.archiveFile.get().asFile.readBytes())
        assertTrue(javaScriptArchiveEncoderIdentity().startsWith("org.apache.commons.compress.archivers.tar.TarArchiveOutputStream|"))
        assertFalse("unavailable" in javaScriptArchiveEncoderIdentity())
        val captured = linkedMapOf<String, ByteArray>()
        TarArchiveInputStream(GZIPInputStream(direct.inputStream()), Charsets.UTF_8.name()).use { input ->
            while (true) {
                val entry = input.nextEntry ?: break
                assertTrue(entry.isFile)
                assertEquals(420, entry.mode)
                assertEquals(0L, entry.longUserId)
                assertEquals(0L, entry.longGroupId)
                assertEquals("", entry.userName)
                assertEquals("", entry.groupName)
                assertEquals(315_532_800_000L, entry.modTime.time)
                captured[entry.name] = input.readBytes()
            }
        }
        assertEquals(names.sorted().map { "package/$it" }, captured.keys.toList())
        names.forEach { name -> assertContentEquals(stage.resolve(name).readBytes(), captured.getValue("package/$name")) }
        assertContentEquals(byteArrayOf(0, 0, 0, 0), direct.readBytes().copyOfRange(4, 8))
    }

    @Test
    fun `runtime policy rejects mismatches before output and detects lifetime change`() = withRoot { root ->
        val stage = root.resolve("stage").also { it.mkdirs() }
        stage.resolve("value.txt").writeText("fixture")
        val output = root.resolve("output.tgz")
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "policyFixture", PackageJavaScriptSdkTask::class.java,
        ).apply { stageDirectory.set(stage); archiveFile.set(output) }
        val runtime = fixturePolicy.releaseObject("javaRuntime")
        val wrongRuntime = JsonObject(fixturePolicy + ("javaRuntime" to JsonObject(runtime +
            ("runtimeVersion" to JsonPrimitive("not-the-running-JVM")))))
        task.archivePolicyFile.set(writePolicy(root, wrongRuntime))
        assertFailsWith<IllegalStateException> { task.archive() }
        assertFalse(output.exists())
        val regular = root.resolve("input.json").also { it.writeText("{}\n") }
        val work = root.resolve("private-work")
        assertFailsWith<IllegalStateException> {
            JavaScriptSdkPackageMain.main(arrayOf("0.8.0", stage.path, stage.path,
                regular.path, regular.path, regular.path, regular.path, work.path, output.path,
                task.archivePolicyFile.get().asFile.path))
        }
        assertFalse(work.exists())
        assertFalse(output.exists())
        val codec = fixturePolicy.releaseObject("commonsCompress")
        val wrongCodec = JsonObject(fixturePolicy + ("commonsCompress" to JsonObject(codec +
            ("version" to JsonPrimitive("not-the-loaded-codec")))))
        task.archivePolicyFile.set(writePolicy(root, wrongCodec))
        assertFailsWith<IllegalStateException> { task.archive() }
        assertFalse(output.exists())
        val policy = writePolicy(root)
        policy.appendText(" ")
        var invoked = false
        assertFailsWith<IllegalStateException> { withJavaScriptArchivePolicy(policy) { invoked = true } }
        assertFalse(invoked)
        writePolicy(root)
        assertFailsWith<IllegalStateException> {
            withJavaScriptArchivePolicy(policy) { policy.appendText(" ") }
        }
    }

    @Test
    fun `staging preserves package files and removes only obsolete staged files`() = withRoot { root ->
        val compiled = root.resolve("adapter").also { it.mkdirs() }
        compiled.resolve("codex-agent-codex-agent-runtime-desktop.js").writeText("export const value = 1;\n")
        compiled.resolve("entry.js.map").writeText("{}\n")
        compiled.resolve("private.d.ts").writeText("not shipped from the adapter")
        val sources = root.resolve("sources").also { it.mkdirs() }
        listOf("index.cjs", "index.mjs", "index.d.ts", "README.md").forEach { sources.resolve(it).writeText(it) }
        sources.resolve("package.json.template").writeText("{\"version\": \"@VERSION@\"}\n")
        val license = root.resolve("LICENSE").also { it.writeText("license\n") }
        val notices = root.resolve("THIRD_PARTY_NOTICES.md").also { it.writeText("notices\n") }
        val compatibility = root.resolve("sdk-compatibility.json").also { it.writeText("{}\n") }
        val destination = root.resolve("package").also { it.mkdirs() }
        destination.resolve("obsolete.txt").writeText("old task output")
        stageJavaScriptSdkPackage(compiled, sources, license, notices, compatibility, "0.8.0", destination)
        assertEquals(setOf("dist/codex-agent-codex-agent-runtime-desktop.js", "dist/entry.js.map",
            "index.cjs", "index.mjs", "index.d.ts", "README.md", "package.json", "LICENSE",
            "THIRD_PARTY_NOTICES.md", "META-INF/codex-agent/sdk-compatibility.json"),
            verifiedRegularFiles(destination).keys)
        assertEquals("{\"version\": \"0.8.0\"}\n", destination.resolve("package.json").readText())
        assertContentEquals(compatibility.readBytes(), destination.resolve("META-INF/codex-agent/sdk-compatibility.json").readBytes())
        assertEquals("not shipped from the adapter", compiled.resolve("private.d.ts").readText())
        assertFailsWith<IllegalStateException> {
            stageJavaScriptSdkPackage(compiled, sources, license, notices, compatibility, "0.8.0", sources)
        }
    }

    @Test
    fun `archive rejects symbolic inputs unsafe names and overlapping output`() = withRoot { root ->
        val stage = root.resolve("stage").also { it.mkdirs() }
        stage.resolve("value.txt").writeText("original\n")
        assertFailsWith<IllegalStateException> { writeJavaScriptSdkArchive(stage, stage.resolve("output.tgz")) }
        stage.resolve("bad\nname").writeText("invalid path")
        assertFailsWith<IllegalStateException> { writeJavaScriptSdkArchive(stage, root.resolve("invalid.tgz")) }
        assertFalse(root.resolve("invalid.tgz").exists())
        stage.resolve("bad\nname").delete()
        Files.createSymbolicLink(stage.resolve("linked.txt").toPath(), stage.resolve("value.txt").toPath())
        assertFailsWith<IllegalStateException> { writeJavaScriptSdkArchive(stage, root.resolve("linked.tgz")) }
        assertFalse(root.resolve("linked.tgz").exists())
    }
}
