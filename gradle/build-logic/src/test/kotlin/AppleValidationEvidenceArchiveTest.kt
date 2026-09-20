import java.io.File
import java.nio.file.Files
import java.time.LocalDateTime
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

/** Archive transport fixtures only; archive membership grants no evidence or producer authority. */
class AppleValidationEvidenceArchiveTest {
    @Test
    fun `preserves exact raw trees and files deterministically`() = fixture().use { fixture ->
        val first = fixture.root.resolve("first.zip")
        val second = fixture.root.resolve("second.zip")
        val roots = linkedMapOf(
            "reports/compiler.json" to fixture.compilerReport,
            "xctest-raw" to fixture.xctest,
        )

        writeAppleValidationEvidenceArchive(roots, first)
        writeAppleValidationEvidenceArchive(roots.reversed(), second)

        assertContentEquals(first.readBytes(), second.readBytes())
        ZipFile(first).use { archive ->
            val entries = archive.entries().asSequence().toList()
            assertEquals(
                listOf(
                    "reports/compiler.json",
                    "xctest-raw/_CodeSignature/CodeResources",
                    "xctest-raw/attempt-0/.hidden",
                    "xctest-raw/attempt-0/execution.json",
                    "xctest-raw/attempt-0/stderr.bin",
                    "xctest-raw/attempt-0/stdout.bin",
                    "xctest-raw/attempt-0/with space+plus.txt",
                    "xctest-raw/\ue000.txt",
                    "xctest-raw/\ud800\udc00.txt",
                ),
                entries.map { it.name },
            )
            assertEquals(false, entries.any { it.isDirectory })
            assertEquals(entries.map { LocalDateTime.of(1980, 1, 1, 0, 0) }, entries.map { it.timeLocal })
            assertContentEquals(ByteArray(0), archive.getInputStream(archive.getEntry(
                "xctest-raw/attempt-0/stdout.bin",
            )).readBytes())
            assertContentEquals(ByteArray(0), archive.getInputStream(archive.getEntry(
                "xctest-raw/attempt-0/stderr.bin",
            )).readBytes())
            assertContentEquals(fixture.compilerReport.readBytes(), archive.getInputStream(archive.getEntry(
                "reports/compiler.json",
            )).readBytes())
        }
    }

    @Test
    fun `rejects unsafe names key-space collisions and empty directories`(): Unit = fixture().use { fixture ->
        listOf("", "/raw", "raw/", "raw//file", "raw/../file", "raw/./file", "raw\\file").forEach { name ->
            assertFailsWith<IllegalStateException>(name) {
                writeAppleValidationEvidenceArchive(mapOf(name to fixture.compilerReport), fixture.output(name.hashCode()))
            }
        }
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(
                mapOf("reports" to fixture.compilerReport, "reports/compiler.json" to fixture.otherReport),
                fixture.output(1),
            )
        }
        val empty = fixture.root.resolve("empty").apply { mkdirs() }
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(mapOf("empty" to empty), fixture.output(2))
        }
    }

    @Test
    fun `rejects symbolic overlapping and nonregular sources`(): Unit = fixture().use { fixture ->
        val link = fixture.root.resolve("report-link")
        Files.createSymbolicLink(link.toPath(), fixture.compilerReport.toPath())
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(mapOf("report.json" to link), fixture.output(3))
        }
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(
                mapOf("raw" to fixture.xctest, "record.json" to fixture.xctest.resolve("attempt-0/execution.json")),
                fixture.output(4),
            )
        }
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(
                mapOf("raw" to fixture.xctest),
                fixture.xctest.resolve("archive.zip"),
            )
        }
    }

    @Test
    fun `rejects stale or symbolic output without modifying it`() = fixture().use { fixture ->
        val stale = fixture.output(5).apply { writeText("owned\n") }
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(mapOf("report.json" to fixture.compilerReport), stale)
        }
        assertEquals("owned\n", stale.readText())

        val target = fixture.root.resolve("target").apply { mkdirs() }
        val linkedParent = fixture.root.resolve("linked-parent")
        Files.createSymbolicLink(linkedParent.toPath(), target.toPath())
        val linkedOutput = linkedParent.resolve("evidence.zip")
        assertFailsWith<IllegalStateException> {
            writeAppleValidationEvidenceArchive(mapOf("report.json" to fixture.compilerReport), linkedOutput)
        }
        assertFalse(target.resolve("evidence.zip").exists())
    }
}

private class AppleValidationEvidenceArchiveFixture : AutoCloseable {
    val root = createTempDirectory("apple-validation-evidence-archive").toFile().canonicalFile
    val compilerReport = root.resolve("compiler.json").apply { writeBytes(byteArrayOf(0, 1, 2, -1)) }
    val otherReport = root.resolve("other.json").apply { writeText("{}\n") }
    val xctest = root.resolve("xctest").apply {
        resolve("attempt-0").mkdirs()
        resolve("attempt-0/execution.json").writeText("{\"schemaVersion\":1}\n")
        resolve("attempt-0/stdout.bin").writeBytes(ByteArray(0))
        resolve("attempt-0/stderr.bin").writeBytes(ByteArray(0))
        resolve("attempt-0/.hidden").writeText("hidden\n")
        resolve("attempt-0/with space+plus.txt").writeText("safe\n")
        resolve("_CodeSignature").mkdirs()
        resolve("_CodeSignature/CodeResources").writeText("signature\n")
        resolve("\ue000.txt").writeText("high BMP\n")
        resolve("\ud800\udc00.txt").writeText("non-BMP\n")
    }

    fun output(index: Int) = root.resolve("output-$index.zip")

    override fun close() {
        root.deleteRecursively()
    }
}

private fun fixture() = AppleValidationEvidenceArchiveFixture()

private fun <K, V> Map<K, V>.reversed(): Map<K, V> = entries.reversed().associate { it.toPair() }
