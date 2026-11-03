import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

/** Fresh package staging only; these fixtures grant no receipt, host, compiler, XCTest, or provenance authority. */
class AppleBinaryPackageStageTaskTest {
    @Test
    fun `stages the exact fresh package artifacts and preserves every input`() = fixture().use { fixture ->
        val before = fixture.inputDigests()
        fixture.output.apply { mkdirs() }.resolve("stale").writeText("remove")

        fixture.stage()

        assertEquals(before, fixture.inputDigests())
        assertEquals(before.filterKeys { it != "sdk-compatibility.json" }, fixture.outputDigests())
        assertFalse(fixture.work.exists())
    }

    @Test
    fun `rejects checksum and compatibility drift before replacing an existing output`() {
        listOf("checksum", "missing", "extra", "bytes", "version").forEach { mutation ->
            fixture().use { fixture ->
                fixture.output.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
                when (mutation) {
                    "checksum" -> fixture.checksum.writeText("0".repeat(64) + "\n")
                    "missing" -> fixture.writeSwiftArchive(includeSimulator = false)
                    "extra" -> fixture.writeSwiftArchive(extraCompatibility = true)
                    "bytes" -> fixture.writeSwiftArchive(simulatorCompatibility = "different\n")
                    else -> fixture.rewriteCompatibility("0.3.0")
                }

                assertFailsWith<IllegalStateException>(mutation) { fixture.stage() }
                assertEquals("preserved", fixture.output.resolve("sentinel").readText(), mutation)
            }
        }
    }

    @Test
    fun `rejects wrong empty nonregular and symbolic inputs`(): Unit = fixture().use { fixture ->
        val wrongName = fixture.inputs.resolve("wrong.zip").apply {
            writeBytes(fixture.applePackage.readBytes())
        }
        assertFailsWith<IllegalStateException> { fixture.stage(applePackage = wrongName) }

        val empty = fixture.inputs.resolve("empty.json").apply { writeBytes(byteArrayOf()) }
        assertFailsWith<IllegalStateException> { fixture.stage(compatibility = empty) }

        val directory = fixture.inputs.resolve("directory").apply { mkdirs() }
        assertFailsWith<IllegalStateException> { fixture.stage(compatibility = directory) }

        val symbolic = fixture.root.resolve("compatibility-link.json").toPath()
        Files.createSymbolicLink(symbolic, fixture.compatibility.toPath())
        assertFailsWith<IllegalStateException> { fixture.stage(compatibility = symbolic.toFile()) }

        val symbolicParent = fixture.root.resolve("symbolic-input-parent").toPath()
        Files.createSymbolicLink(symbolicParent, fixture.inputs.toPath())
        assertFailsWith<IllegalStateException> {
            fixture.stage(compatibility = symbolicParent.resolve(fixture.compatibility.name).toFile())
        }
    }

    @Test
    fun `rejects unowned overlapping and symbolic destinations without deleting inputs`() = fixture().use { fixture ->
        val before = fixture.inputDigests()
        assertFailsWith<IllegalStateException> {
            fixture.stage(output = fixture.root.resolve("unowned"))
        }
        assertFailsWith<IllegalStateException> {
            fixture.stage(work = fixture.output, output = fixture.output)
        }
        assertFailsWith<IllegalStateException> {
            fixture.stage(output = fixture.inputs)
        }
        val symbolicOutput = fixture.owned.resolve("symbolic-output")
        fixture.owned.mkdirs()
        Files.createSymbolicLink(symbolicOutput.toPath(), fixture.root.resolve("unowned-target").toPath())
        assertFailsWith<IllegalStateException> { fixture.stage(output = symbolicOutput) }
        assertEquals(before, fixture.inputDigests())
    }
}

private class AppleBinaryPackageStageFixture : AutoCloseable {
    val root = createTempDirectory("apple-binary-package-stage").toFile().canonicalFile
    val inputs = root.resolve("inputs").apply { mkdirs() }
    val owned = root.resolve("owned")
    val work = owned.resolve("work")
    val output = owned.resolve("output")
    private val version = "0.2.0"
    val applePackage = inputs.resolve("CodexAgentPackage-$version.zip")
    val swiftPackage = inputs.resolve("CodexAgent-$version.xcframework.zip")
    val checksum = inputs.resolve("CodexAgent-$version.xcframework.zip.sha256")
    val compatibility = inputs.resolve("sdk-compatibility.json")

    init {
        rewriteCompatibility(version)
    }

    fun rewriteCompatibility(sdkVersion: String) {
        compatibility.writeText("{\"schemaVersion\":1,\"sdkVersion\":\"$sdkVersion\"}\n")
        writeAppleArchive()
        writeSwiftArchive()
    }

    private fun writeAppleArchive() = writeZip(
        applePackage,
        listOf("META-INF/codex-agent/sdk-compatibility.json" to compatibility.readBytes()),
    )

    fun writeSwiftArchive(
        includeSimulator: Boolean = true,
        extraCompatibility: Boolean = false,
        simulatorCompatibility: String? = null,
    ) {
        val entries = mutableListOf(
            "CodexAgent.xcframework/ios-arm64/CodexAgent.framework/META-INF/codex-agent/" +
                "sdk-compatibility.json" to compatibility.readBytes(),
        )
        if (includeSimulator) entries += Pair(
            "CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/META-INF/codex-agent/" +
                "sdk-compatibility.json",
            simulatorCompatibility?.toByteArray() ?: compatibility.readBytes(),
        )
        if (extraCompatibility) entries += Pair(
            "extra/sdk-compatibility.json",
            compatibility.readBytes(),
        )
        writeZip(swiftPackage, entries)
        checksum.writeText("${swiftPackage.releaseDigest()}\n")
    }

    fun inputDigests() = linkedMapOf(
        applePackage.name to applePackage.releaseDigest(),
        swiftPackage.name to swiftPackage.releaseDigest(),
        checksum.name to checksum.releaseDigest(),
        compatibility.name to compatibility.releaseDigest(),
    )

    fun outputDigests() = verifiedRegularFiles(output).mapValues { (_, file) -> file.releaseDigest() }

    fun stage(
        applePackage: File = this.applePackage,
        swiftPackage: File = this.swiftPackage,
        checksum: File = this.checksum,
        compatibility: File = this.compatibility,
        work: File = this.work,
        output: File = this.output,
    ) = stageAppleBinaryPackageArtifacts(
        applePackage, swiftPackage, checksum, compatibility, version, owned, work, output,
    )

    override fun close() {
        root.deleteRecursively()
    }

    private fun writeZip(file: File, entries: List<Pair<String, ByteArray>>) {
        file.parentFile.mkdirs()
        ZipOutputStream(file.outputStream()).use { archive ->
            entries.forEach { (name, contents) ->
                archive.putNextEntry(ZipEntry(name).apply { time = 0L })
                archive.write(contents)
                archive.closeEntry()
            }
        }
    }
}

private fun fixture() = AppleBinaryPackageStageFixture()
