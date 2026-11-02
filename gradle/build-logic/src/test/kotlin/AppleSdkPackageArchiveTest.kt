import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.FileTime
import java.util.zip.ZipFile
import java.util.TimeZone
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Synthetic encoder/owner controls only; no Apple tools, product package or approved host identity. */
class AppleSdkPackageArchiveTest {
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
            val loader = org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream::class.java.classLoader
            val pom = "META-INF/maven/org.apache.commons/commons-compress/pom.properties"
            val names = (listOf(pom) + listOf("ZipArchiveEntry", "ZipArchiveOutputStream", "ZipUtil")
                .map { "org/apache/commons/compress/archivers/zip/$it.class" }).sorted()
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
        val root = createTempDirectory("apple-package-control-").toFile().canonicalFile
        val timezone = TimeZone.getDefault()
        try { action(root) } finally { TimeZone.setDefault(timezone); root.deleteRecursively() }
    }


    @Test
    fun `real Zip task and standalone writer produce identical canonical bytes`() = withRoot { root ->
        val source = root.resolve("source").also { it.mkdirs() }
        val names = listOf("z.txt", "nested/" + "long-".repeat(30) + "ü.swift")
        names.forEach { name -> source.resolve(name).apply { parentFile.mkdirs(); writeText(name + "\n") } }
        val files = verifiedRegularFiles(source).mapKeys { "CodexAgent.xcframework/${it.key}" }
        val direct = root.resolve("direct.zip")
        TimeZone.setDefault(TimeZone.getTimeZone("Pacific/Auckland"))
        writeAppleSdkZip(files, direct)
        val project = ProjectBuilder.builder().withProjectDir(root).build()
        val task = project.tasks.create("packAppleFixture", CanonicalAppleZip::class.java).apply {
            from(source) { into("CodexAgent.xcframework") }
            archiveFileName.set("task.zip")
            destinationDirectory.set(root)
            archivePolicy.set(writePolicy(root))
            isPreserveFileTimestamps = false
            isReproducibleFileOrder = true
        }
        files.values.forEach {
            Files.setLastModifiedTime(it.toPath(), FileTime.fromMillis(1_700_000_000_000L))
            it.setExecutable(true)
        }
        TimeZone.setDefault(TimeZone.getTimeZone("America/Los_Angeles"))
        task.actions.forEach { it.execute(task) }
        assertContentEquals(direct.readBytes(), task.archiveFile.get().asFile.readBytes())
        ZipFile(direct).use { zip ->
            val entries = zip.entries().asSequence().toList()
            assertEquals(entries.map { it.name }.sorted(), entries.map { it.name })
            assertEquals(files.keys, entries.filterNot { it.isDirectory }.map { it.name }.toSet())
            entries.filterNot { it.isDirectory }.forEach { entry ->
                assertEquals(8, entry.method)
                assertContentEquals(files.getValue(entry.name).readBytes(), zip.getInputStream(entry).readBytes())
            }
        }
        val repeat = root.resolve("repeat.zip")
        TimeZone.setDefault(TimeZone.getTimeZone("UTC"))
        writeAppleSdkZip(files, repeat)
        assertContentEquals(direct.readBytes(), repeat.readBytes())
    }

    @Test
    fun `encoder rejects traversal collisions symlinks and empty inputs`() = withRoot { root ->
        val regular = root.resolve("input").also { it.writeText("fixture") }
        for (files in listOf(mapOf("../outside" to regular), mapOf("a" to regular, "a/b" to regular), emptyMap())) {
            val output = root.resolve("bad.zip")
            assertFailsWith<IllegalStateException> { writeAppleSdkZip(files, output) }
            assertFalse(output.exists())
        }
        val link = root.resolve("alias")
        Files.createSymbolicLink(link.toPath(), regular.toPath())
        assertFailsWith<IllegalStateException> { writeAppleSdkZip(mapOf("value" to link), root.resolve("bad.zip")) }
    }

    @Test
    fun `policy rejects wrong runtime and codec before tools and checks owning exit`() = withRoot { root ->
        val runtime = fixturePolicy.releaseObject("javaRuntime")
        val wrong = JsonObject(fixturePolicy + ("javaRuntime" to JsonObject(runtime +
            ("runtimeVersion" to JsonPrimitive("different JVM")))))
        val policy = writePolicy(root, wrong)
        val work = root.resolve("work")
        val output = root.resolve("output")
        assertFailsWith<IllegalStateException> {
            AppleSdkPackageMain.main(arrayOf("0.8.0", root.path, root.path, root.resolve("input").path,
                work.path, output.path, root.path, "26.6", "17F1", "6.2", policy.path))
        }
        assertFalse(work.exists()); assertFalse(output.exists())
        val codec = fixturePolicy.releaseObject("commonsCompress")
        writePolicy(root, JsonObject(fixturePolicy + ("commonsCompress" to JsonObject(codec +
            ("version" to JsonPrimitive("different codec"))))))
        var invoked = false
        assertFailsWith<IllegalStateException> { withAppleArchivePolicy(policy) { invoked = true } }
        assertFalse(invoked)
        writePolicy(root)
        assertFailsWith<IllegalStateException> { withAppleArchivePolicy(policy) { policy.appendText(" ") } }
    }
}
