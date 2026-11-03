import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** Content comparison fixtures only; they provide no producer, receipt, host, or replay authority. */
class AppleBinaryPackageContentTest {
    @Test
    fun `accepts exact package and decorated XCFramework without changing private snapshots`() =
        fixture().use { fixture ->
            val before = fixture.inputDigests()

            fixture.verify()

            assertEquals(before, fixture.inputDigests())
            assertEquals(fixture.packageDigests(), fixture.extractedPackageDigests())
            assertEquals(
                fixture.xcframeworkDigests().keys + fixture.compatibilityPaths,
                fixture.extractedXCFrameworkDigests().keys,
            )
        }

    @Test
    fun `rejects native header source and privacy content drift`() {
        listOf("native", "header", "source", "privacy").forEach { mutation ->
            fixture().use { fixture ->
                when (mutation) {
                    "source" -> fixture.writePackageArchive(
                        overrides = mapOf("Sources/CodexAgent/CodexAgent.swift" to "changed\n".toByteArray()),
                    )
                    else -> fixture.writeSwiftArchive(
                        overrides = mapOf(fixture.pathFor(mutation) to "changed\n".toByteArray()),
                    )
                }

                assertFailsWith<IllegalStateException>(mutation) { fixture.verify() }
            }
        }
    }

    @Test
    fun `rejects missing extra and changed compatibility decoration`() {
        listOf("missing", "extra", "drift").forEach { mutation ->
            fixture().use { fixture ->
                when (mutation) {
                    "missing" -> fixture.writeSwiftArchive(omitted = setOf(fixture.compatibilityPaths.last()))
                    "extra" -> fixture.writeSwiftArchive(
                        extras = mapOf("unexpected/sdk-compatibility.json" to fixture.compatibility.readBytes()),
                    )
                    else -> fixture.writeSwiftArchive(
                        overrides = mapOf(fixture.compatibilityPaths.last() to "changed\n".toByteArray()),
                    )
                }

                assertFailsWith<IllegalStateException>(mutation) { fixture.verify() }
            }
        }
    }

    @Test
    fun `rejects incomplete product preexisting or overlapping work and unsafe archive entries`() {
        fixture().use { fixture ->
            fixture.product.resolve("extra").writeText("extra")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        fixture().use { fixture ->
            fixture.product.resolve("CodexAgentPackage-0.2.0.zip").delete()
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        fixture().use { fixture ->
            fixture.work.mkdirs()
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        fixture().use { fixture ->
            assertFailsWith<IllegalStateException> { fixture.verify(work = fixture.expectedPackage.resolve("work")) }
        }
        fixture().use { fixture ->
            fixture.writePackageArchive(extras = mapOf("../escape" to "unsafe\n".toByteArray()))
            assertFailsWith<IllegalStateException> { fixture.verify() }
            assertEquals(false, fixture.root.resolve("escape").exists())
        }
    }
}

internal class AppleBinaryPackageContentFixture : AutoCloseable {
    val root = createTempDirectory("apple-binary-package-content").toFile().canonicalFile
    val product = root.resolve("product").apply { mkdirs() }
    val expectedPackage = root.resolve("expected-package").apply { mkdirs() }
    val expectedXCFramework = root.resolve("expected-xcframework").apply { mkdirs() }
    val compatibility = root.resolve("sdk-compatibility.json")
    val work = root.resolve("work")
    private val version = "0.2.0"
    private val appleArchive = product.resolve("CodexAgentPackage-$version.zip")
    private val swiftArchive = product.resolve("CodexAgent-$version.xcframework.zip")
    private val checksum = product.resolve("CodexAgent-$version.xcframework.zip.sha256")
    val compatibilityPaths = listOf("ios-arm64", "ios-arm64-simulator").map { slice ->
        "$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json"
    }

    init {
        compatibility.writeText("{\"schemaVersion\":1,\"sdkVersion\":\"$version\"}\n")
        expectedXCFramework.resolve("Info.plist").writeText("xcframework-info\n")
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            val framework = expectedXCFramework.resolve("$slice/CodexAgent.framework")
            mapOf(
                "CodexAgent" to "native:$slice\n",
                "Headers/CodexAgent.h" to "header:$slice\n",
                "Modules/module.modulemap" to "module:$slice\n",
                "Info.plist" to "framework-info:$slice\n",
                "PrivacyInfo.xcprivacy" to "privacy\n",
            ).forEach { (path, bytes) -> framework.resolve(path).writeFixture(bytes.toByteArray()) }
        }
        expectedPackage.resolve("Package.swift").writeText("// swift-tools-version: 6.0\n")
        expectedPackage.resolve("Sources/CodexAgent/CodexAgent.swift").writeFixture("source\n".toByteArray())
        expectedPackage.resolve("Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy").writeFixture("privacy\n".toByteArray())
        expectedPackage.resolve("Tests/Example.swift").writeFixture("test source\n".toByteArray())
        listOf("LICENSE.txt", "THIRD_PARTY_NOTICES.md", "openai-codex-LICENSE.txt", "openai-codex-NOTICE.txt").forEach {
            expectedPackage.resolve(it).writeText("legal:$it\n")
        }
        expectedPackage.resolve("META-INF/codex-agent/sdk-compatibility.json")
            .writeFixture(compatibility.readBytes())
        verifiedRegularFiles(expectedXCFramework).forEach { (path, source) ->
            expectedPackage.resolve("CodexAgent.xcframework/$path").writeFixture(source.readBytes())
        }
        writePackageArchive()
        writeSwiftArchive()
    }

    fun pathFor(kind: String) = when (kind) {
        "native" -> "ios-arm64/CodexAgent.framework/CodexAgent"
        "header" -> "ios-arm64/CodexAgent.framework/Headers/CodexAgent.h"
        else -> "ios-arm64-simulator/CodexAgent.framework/PrivacyInfo.xcprivacy"
    }

    fun writePackageArchive(
        overrides: Map<String, ByteArray> = emptyMap(),
        extras: Map<String, ByteArray> = emptyMap(),
    ) {
        val entries = verifiedRegularFiles(expectedPackage).mapValues { (path, file) ->
            overrides[path] ?: file.readBytes()
        } + extras
        writeZip(appleArchive, entries)
    }

    fun writeSwiftArchive(
        overrides: Map<String, ByteArray> = emptyMap(),
        omitted: Set<String> = emptySet(),
        extras: Map<String, ByteArray> = emptyMap(),
    ) {
        val entries = buildMap {
            verifiedRegularFiles(expectedXCFramework).forEach { (path, file) ->
                put("CodexAgent.xcframework/$path", overrides[path] ?: file.readBytes())
            }
            compatibilityPaths.filterNot(omitted::contains).forEach { path ->
                put("CodexAgent.xcframework/$path", overrides[path] ?: compatibility.readBytes())
            }
            putAll(extras)
        }
        writeZip(swiftArchive, entries)
        checksum.writeText("${swiftArchive.releaseDigest()}\n")
    }

    fun verify(work: File = this.work) = verifyAppleBinaryPackageArchives(
        product,
        version,
        expectedPackage,
        expectedXCFramework,
        compatibility,
        work,
    )

    fun inputDigests() = mapOf(
        "product" to treeDigests(product),
        "package" to packageDigests(),
        "xcframework" to xcframeworkDigests(),
        "compatibility" to mapOf(compatibility.name to compatibility.releaseDigest()),
    )

    fun packageDigests() = treeDigests(expectedPackage)
    fun xcframeworkDigests() = treeDigests(expectedXCFramework)
    fun extractedPackageDigests() = treeDigests(work.resolve("package"))
    fun extractedXCFrameworkDigests() = treeDigests(work.resolve("xcframework"))

    override fun close() {
        root.deleteRecursively()
    }

    private fun treeDigests(directory: File) =
        verifiedRegularFiles(directory).mapValues { (_, file) -> file.releaseDigest() }

    private fun File.writeFixture(contents: ByteArray) {
        parentFile.mkdirs()
        writeBytes(contents)
    }

    private fun writeZip(file: File, entries: Map<String, ByteArray>) {
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

private fun fixture() = AppleBinaryPackageContentFixture()
