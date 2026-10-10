import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Synthetic immutable snapshots only; these tests grant no receipt, producer, source, or host authority. */
class AppleValidationBindingReplayTest {
    @Test
    fun `replays exact selected package and retained binding evidence without changing inputs`() = fixture().use {
        val before = it.inputDigests()

        it.verify()

        assertEquals(before, it.inputDigests())
    }

    @Test
    fun `rejects retained package canonical consumer and semantic replay drift without rewriting inputs`() {
        val mutations: List<Pair<String, (AppleValidationBindingReplayFixture) -> Unit>> = listOf(
            "Retained Apple validation XCFramework differs" to
                { it.evidence.resolve("xcframework/ios-arm64/CodexAgent.framework/CodexAgent")
                    .appendText("changed\n") },
            "Retained Apple validation xctest-package differs" to
                { it.evidence.resolve("xctest-package/Package.swift").appendText("// changed\n") },
            "Retained Apple validation device-package differs" to
                { it.evidence.resolve("device-package/Package.swift").appendText("// changed\n") },
            "canonical or consumer input differs" to
                { it.evidence.resolve("canonical/canonical-api.json").appendText(" ") },
            "canonical or consumer input differs" to
                { it.evidence.resolve("consumer/CodexFailureSwiftConsumer.swift").appendText("// changed\n") },
            "Swift package test statuses changed" to { file ->
                val tests = file.evidence.resolve("xctest-raw/attempt-0/tests/stdout.bin")
                tests.writeText(tests.readText().replaceFirst("Passed", "Failed"))
            },
            "Original Apple binding evidence differs" to
                { it.evidence.resolve("reports/binding-evidence.json")
                    .atomicWriteJson(JsonObject(emptyMap())) },
        )
        mutations.forEach { (expected, mutate) ->
            fixture().use { fixture ->
                fixture.verifyBaseline()
                mutate(fixture)
                val changed = fixture.inputDigests()
                assertReplayFailure(expected) { fixture.verify() }
                assertEquals(changed, fixture.inputDigests(), expected)
            }
        }
    }

    @Test
    fun `rejects caller expectation product work and ancestry violations without rewriting inputs`() {
        val mutations: List<Pair<String, (AppleValidationBindingReplayFixture) -> Unit>> = listOf(
            "canonical or consumer input differs" to { it.canonicalApi.appendText(" ") },
            "canonical or consumer input differs" to
                { it.consumers.resolve("CodexFailureObjectiveCConsumer.m").appendText("// changed\n") },
            "Apple SDK compatibility digest mismatch" to
                { it.compatibility.writeText("{\"schemaVersion\":1,\"sdkVersion\":\"0.2.1\"}\n") },
            "Retained Apple validation xctest-package differs" to { it.mutateProductPackage() },
        )
        mutations.forEach { (expected, mutate) ->
            fixture().use { fixture ->
                fixture.verifyBaseline()
                mutate(fixture)
                val changed = fixture.inputDigests()
                assertReplayFailure(expected) { fixture.verify() }
                assertEquals(changed, fixture.inputDigests(), expected)
            }
        }
        fixture().use { fixture ->
            fixture.verifyBaseline()
            val marker = fixture.work.resolve("owned").apply { parentFile.mkdirs(); writeText("owned\n") }
            assertReplayFailure("work directory must be fresh") { fixture.verify() }
            assertEquals("owned\n", marker.readText())
        }
        fixture().use { fixture ->
            fixture.verifyBaseline()
            assertReplayFailure("private snapshot overlaps an input") {
                fixture.verify(work = fixture.evidence.resolve("work"))
            }
        }
        fixture().use { fixture ->
            fixture.verifyBaseline()
            assertReplayFailure("private snapshot overlaps an input") {
                fixture.verify(canonicalApi = fixture.evidence.resolve("canonical/canonical-api.json"))
            }
        }
    }
}

private class AppleValidationBindingReplayFixture : AutoCloseable {
    private val original = OriginalAppleExecutionFixture()
    val root = original.root
    val evidence = original.execution
    val product = root.resolve("selected-product").apply { mkdirs() }
    val compatibility = root.resolve("expected/sdk-compatibility-binding.json")
    val canonicalApi = root.resolve("expected/canonical-api.json")
    private val canonicalCoverage = root.resolve("expected/canonical-coverage.json")
    val consumers = root.resolve("expected/consumers")
    val work = root.resolve("binding-replay-work")
    private val selectedPackage = root.resolve("selected-package").apply { mkdirs() }
    private val version = "0.2.0"
    private val compatibilityPaths = listOf("ios-arm64", "ios-arm64-simulator").map { slice ->
        "$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json"
    }

    init {
        compatibility.parentFile.mkdirs()
        compatibility.writeText("{\"schemaVersion\":1,\"sdkVersion\":\"$version\"}\n")
        evidence.resolve("canonical/canonical-api.json").copyTo(canonicalApi)
        evidence.resolve("canonical/canonical-coverage.json").copyTo(canonicalCoverage)
        copyReleaseTree(evidence.resolve("consumer"), consumers)
        compatibilityPaths.forEach { path -> evidence.resolve("xcframework/$path").writeFixture(compatibility.readBytes()) }

        selectedPackage.resolve("Package.swift").writeFixture("// selected package\n".toByteArray())
        selectedPackage.resolve("META-INF/codex-agent/sdk-compatibility.json").writeFixture(compatibility.readBytes())
        verifiedRegularFiles(evidence.resolve("xcframework")).filterKeys { it !in compatibilityPaths }
            .forEach { (path, source) ->
                selectedPackage.resolve("CodexAgent.xcframework/$path").writeFixture(source.readBytes())
            }
        evidence.resolve("xctest-package").deleteRecursively()
        copyReleaseTree(selectedPackage, evidence.resolve("xctest-package"))
        copyReleaseTree(selectedPackage, evidence.resolve("device-package"))
        rewriteCompilerEvidence()
        rewriteBindingEvidence()
        copyRetainedReports()
        writeProduct(selectedPackage)
    }

    fun verify(
        work: File = this.work,
        canonicalApi: File = this.canonicalApi,
    ) = verifyAppleValidationBindingReplay(
        evidence, product, version, compatibility, canonicalApi, canonicalCoverage, consumers, work,
    )

    fun verifyBaseline() = verify(work = root.resolve("baseline-work"))

    fun inputDigests(): Map<String, Map<String, String>> = mapOf(
        "evidence" to evidence.digests(),
        "product" to product.digests(),
        "compatibility" to mapOf(compatibility.name to compatibility.releaseDigest()),
        "canonical-api" to mapOf(canonicalApi.name to canonicalApi.releaseDigest()),
        "canonical-coverage" to mapOf(canonicalCoverage.name to canonicalCoverage.releaseDigest()),
        "consumers" to consumers.digests(),
    )

    fun mutateProductPackage() {
        selectedPackage.resolve("Package.swift").appendText("// changed selected package\n")
        writeZip(product.resolve("CodexAgentPackage-$version.zip"), selectedPackage, "")
    }

    private fun rewriteCompilerEvidence() {
        val report = original.compilerEvidence.readReleaseObject()
        val artifacts = report.releaseObject("artifacts")
        val targets = report.releaseArray("targets").map { value ->
            val target = value as JsonObject
            val framework = evidence.resolve(
                "xcframework/${target.releaseString("name")}/CodexAgent.framework",
            )
            JsonObject(target + ("frameworkSha256" to JsonPrimitive(framework.crossLanguageTreeDigest())))
        }
        original.compilerEvidence.atomicWriteJson(JsonObject(report + mapOf(
            "artifacts" to JsonObject(artifacts + (
                "xcframeworkSha256" to JsonPrimitive(evidence.resolve("xcframework").crossLanguageTreeDigest())
            )),
            "targets" to JsonArray(targets),
        )))
    }

    private fun rewriteBindingEvidence() {
        val canonical = readCrossLanguageCanonicalApiEvidence(
            evidence.resolve("canonical/canonical-api.json"), evidence.resolve("canonical/canonical-coverage.json"),
        )
        val compiler = original.compilerEvidence.readReleaseObject()
        val xctestFile = original.distribution.resolve("reports/swift-authentication-tests-summary.json")
        val xctest = xctestFile.readReleaseObject()
        val xcframework = evidence.resolve("xcframework")
        val digests = AppleBindingInputDigests(
            original.compilerEvidence.releaseDigest(),
            xcframework.crossLanguageTreeDigest(),
            evidence.resolve("consumer/CodexFailureSwiftConsumer.swift").releaseDigest(),
            evidence.resolve("consumer/CodexFailureObjectiveCConsumer.m").releaseDigest(),
            xctestFile.releaseDigest(),
            evidence.resolve("xcresult").crossLanguageTreeDigest(),
            evidence.resolve("xctest-package").crossLanguageTreeDigest(),
            listOf("ios-arm64", "ios-arm64-simulator").associateWith { slice ->
                val framework = xcframework.resolve("$slice/CodexAgent.framework")
                AppleBindingTargetDigests(
                    framework.crossLanguageTreeDigest(), framework.resolve("CodexAgent").releaseDigest(),
                    framework.resolve("Headers/CodexAgent.h").releaseDigest(),
                    framework.resolve("Modules/module.modulemap").releaseDigest(),
                )
            },
        )
        val binding = deriveCrossLanguageAppleBindingEvidence(canonical, compiler, xctest, digests)
        val bindingFile = original.distribution.resolve("reports/cross-language-api/apple/binding-evidence.json")
        bindingFile.atomicWriteJson(binding)
        mapOf(
            CrossLanguageBinding.SWIFT to "reports/cross-language-api/bindings/swift-parity.json",
            CrossLanguageBinding.OBJECTIVE_C to "reports/cross-language-api/bindings/objective-c-parity.json",
        ).forEach { (language, path) ->
            writeCrossLanguageBindingReceipt(
                original.distribution.resolve(path),
                buildAppleBindingParityReceipt(binding, language, digests, bindingFile.releaseDigest()),
            )
        }
    }

    private fun copyRetainedReports() {
        mapOf(
            original.compilerEvidence to "compiler-evidence.json",
            original.distribution.resolve("reports/swift-authentication-tests-summary.json") to "xctest-summary.json",
            original.distribution.resolve("reports/cross-language-api/apple/binding-evidence.json") to
                "binding-evidence.json",
            original.distribution.resolve("reports/cross-language-api/bindings/swift-parity.json") to
                "swift-parity.json",
            original.distribution.resolve("reports/cross-language-api/bindings/objective-c-parity.json") to
                "objective-c-parity.json",
        ).forEach { (source, name) ->
            val destination = evidence.resolve("reports/$name")
            destination.parentFile.mkdirs()
            source.copyTo(destination)
        }
    }

    private fun writeProduct(selectedPackage: File) {
        val packageArchive = product.resolve("CodexAgentPackage-$version.zip")
        val swiftArchive = product.resolve("CodexAgent-$version.xcframework.zip")
        writeZip(packageArchive, selectedPackage, "")
        writeZip(
            swiftArchive, evidence.resolve("xcframework"), "CodexAgent.xcframework/", compatibilityPaths,
        )
        product.resolve("CodexAgent-$version.xcframework.zip.sha256")
            .writeText("${swiftArchive.releaseDigest()}\n")
    }

    override fun close() {
        original.close()
    }
}

private fun File.digests() = verifiedRegularFiles(this).mapValues { (_, file) -> file.releaseDigest() }

private fun File.writeFixture(contents: ByteArray) {
    parentFile.mkdirs()
    writeBytes(contents)
}

private fun writeZip(archive: File, source: File, prefix: String, orderedLast: List<String> = emptyList()) {
    ZipOutputStream(archive.outputStream()).use { output ->
        val files = verifiedRegularFiles(source)
        (files.keys.filterNot(orderedLast::contains).sorted() + orderedLast).forEach { path ->
            val file = files.getValue(path)
            output.putNextEntry(ZipEntry("$prefix$path").apply { time = 0L })
            file.inputStream().use { it.copyTo(output) }
            output.closeEntry()
        }
    }
}

private fun fixture() = AppleValidationBindingReplayFixture()

private fun assertReplayFailure(expected: String, block: () -> Unit) {
    val failure = assertFailsWith<IllegalStateException>(block = block)
    assertTrue(failure.message?.contains(expected) == true, failure.message)
}
