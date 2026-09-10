import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Synthetic retention fixtures, not compiler, XCTest, or CI source authentication. */
class AppleVerifiedDistributionExportTest {
    @Test
    fun `export preserves originals and separates exact raw closure from unchanged products`() = fixture { f ->
        val before = f.inventory(f.source)
        f.export()
        val verified = verifyAppleVerifiedDistribution(f.output, f.external.resolve("native-evidence"), f.identity)
        assertEquals(appleVerifiedArtifactNames("0.2.0"), verified.artifacts.keys)
        f.artifacts.forEach { (path, original) ->
            assertContentEquals(original.readBytes(), f.output.resolve(path).readBytes())
        }
        assertEquals(f.execution.keys, verifiedRegularFiles(f.external).keys)
        f.execution.forEach { (path, original) ->
            assertContentEquals(original.readBytes(), f.external.resolve(path).readBytes())
        }
        assertEquals(0L, f.external.resolve("compiler-raw/stderr.bin").length())
        assertFalse(verifiedRegularFiles(f.output).keys.any { it.startsWith("compiler-raw/") })
        val distribution = f.inventory(f.output)
        f.export()
        assertEquals(distribution, f.inventory(f.output))
        assertEquals(before, f.inventory(f.source))
    }

    @Test
    fun `missing crosspaired and unsafe originals preserve previous outputs`() = fixture { f ->
        f.export()
        val before = f.inventory(f.output)
        val external = f.inventory(f.external)
        val compatibility = f.execution.getValue("sdk-compatibility.json")
        val original = compatibility.readBytes()
        compatibility.writeText("different compatibility")
        assertFailsWith<IllegalStateException> { f.export() }
        compatibility.writeBytes(original)
        assertEquals(before, f.inventory(f.output))
        assertEquals(external, f.inventory(f.external))
        val originalConsumer = f.execution.getValue("consumer/swift.swift")
        val consumer = originalConsumer.readBytes()
        originalConsumer.delete()
        assertFailsWith<IllegalStateException> { f.export() }
        originalConsumer.writeBytes(consumer)
        assertFailsWith<IllegalStateException> {
            f.export(f.execution + ("../escape" to originalConsumer))
        }
        assertEquals(before, f.inventory(f.output))
        assertEquals(external, f.inventory(f.external))
        assertFalse(f.build.resolve("escape").exists())
    }

    @Test
    fun `output input overlap and symbolic input ancestors reject before cleanup`() = fixture { f ->
        f.export()
        val before = f.inventory(f.output)
        val external = f.inventory(f.external)
        assertFailsWith<IllegalStateException> {
            f.export(f.execution + ("alias" to f.output.resolve(f.artifacts.keys.first())))
        }
        val link = f.root.resolve("source-link")
        Files.createSymbolicLink(link.toPath(), f.source.toPath())
        assertFailsWith<IllegalStateException> {
            f.export(f.execution + ("alias" to link.resolve("source/Package.swift")))
        }
        assertEquals(before, f.inventory(f.output))
        assertEquals(external, f.inventory(f.external))
        assertTrue(f.execution.getValue("source/Package.swift").isFile)
    }

    private fun fixture(block: (Originals) -> Unit) {
        val root = createTempDirectory("apple-original-export").toFile().canonicalFile
        try { block(Originals(root)) } finally { deleteReleaseTree(root) }
    }

    private class Originals(val root: File) {
        val source = root.resolve("original").apply { mkdirs() }
        val build = root.resolve("build").apply { mkdirs() }
        val output = build.resolve("apple-verified-distribution")
        val external = build.resolve("apple-verified-distribution-execution")
        private val compatibility = "{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n".toByteArray()
        private fun file(path: String, bytes: ByteArray = path.toByteArray()) = source.resolve(path).apply {
            parentFile.mkdirs(); writeBytes(bytes)
        }
        private fun zip(name: String, paths: List<String>) = file(name).apply {
            ZipOutputStream(outputStream()).use { zip -> paths.forEach { path ->
                zip.putNextEntry(ZipEntry(path)); zip.write(compatibility); zip.closeEntry()
            } }
        }
        private val xcarchive = zip("CodexAgent-0.2.0.xcframework.zip", listOf("ios-arm64", "ios-arm64-simulator").map {
            "CodexAgent.xcframework/$it/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json"
        })
        val artifacts = listOf(xcarchive,
            zip("CodexAgentPackage-0.2.0.zip", listOf("META-INF/codex-agent/sdk-compatibility.json")),
            file("CodexAgent-0.2.0.xcframework.zip.sha256", (xcarchive.releaseDigest() + "\n").toByteArray()),
        ).associateBy(File::getName)
        private val reports = appleVerifiedReportLayout.keys.associateWith { file(it) }
        private val toolchain = appleVerifiedToolchainLayout.keys.associateWith { file(it) }
        private val receipts = mapOf(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT to file(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT))
        private val native = (appleRustSliceSpecs.flatMap { listOf(it.archiveName, it.proofName) } +
            IOS_NATIVE_TESTS_PROOF).associateWith { file("native-evidence/$it") }
        private val roots = listOf("compiler-raw", "xcframework", "xcresult", "xctest-package", "xctest-products", "xctest-raw")
            .associateWith { prefix -> file("$prefix/original.bin", byteArrayOf(-1, 0, 10)).parentFile } +
            ("native-evidence" to source.resolve("native-evidence"))
        val execution: Map<String, File> = linkedMapOf(
            "source/Package.swift" to file("source/Package.swift"),
            "source/native-provenance.json" to file("source/native-provenance.json"),
            "sdk-compatibility.json" to file("sdk-compatibility.json", compatibility),
            "canonical/api.json" to file("canonical/api.json"),
            "canonical/coverage.json" to file("canonical/coverage.json"),
            "consumer/swift.swift" to file("consumer/swift.swift"),
            "consumer/objective-c.m" to file("consumer/objective-c.m"),
            "compiler-raw/stderr.bin" to file("compiler-raw/stderr.bin", byteArrayOf()),
        ) + roots.flatMap { (prefix, directory) ->
            verifiedRegularFiles(directory).map { (path, original) -> "$prefix/$path" to original }
        }.toMap()
        val identity = AppleVerifiedDistributionIdentity(
            "1".repeat(40), "2".repeat(40), "0.2.0",
            execution.getValue("source/native-provenance.json").releaseDigest(),
            execution.getValue("source/Package.swift").releaseDigest(),
            receipts.getValue(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseDigest(),
            execution.getValue("sdk-compatibility.json").releaseDigest(),
        )
        fun inventory(directory: File) = verifiedRegularFiles(directory).mapValues { (_, file) -> file.releaseDigest() }
        fun export(files: Map<String, File> = execution) = exportAppleVerifiedOriginals(
            identity, artifacts, reports, toolchain, receipts, native, files, roots, build, output, external,
        )
    }
}
