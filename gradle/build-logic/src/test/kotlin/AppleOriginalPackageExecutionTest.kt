import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Pure retained-execution tests with simulated original tools; no Apple process is invoked. */
class AppleOriginalPackageExecutionTest {
    @Test
    fun `replays complete original observations after historical paths are gone`() {
        Fixture().use { fixture ->
            assertFalse(fixture.originalContext.scratchDirectory.exists())
            assertFalse(fixture.originalContext.workDirectory.exists())
            assertFalse(fixture.originalContext.sourceSnapshot.exists())
            assertFalse(fixture.originalContext.binaryFrameworks.exists())
            fixture.verify()
            fixture.assertInputsUnchanged()
        }
    }

    @Test
    fun `replays merged process bytes with original UTF8 replacement semantics`() {
        Fixture().use { fixture ->
            val raw = byteArrayOf(0, -1, -128)
            fixture.event("07-device-strip/combined.bin").writeBytes(raw)
            fixture.refreshExecutionBinding()
            fixture.verify()
            assertContentEquals(raw, fixture.event("07-device-strip/combined.bin").readBytes())
        }
    }

    @Test
    fun `rejects changed process metadata and streams after same execution rebinding`() {
        listOf(
            "ordinal", "quoted-schema", "quoted-ordinal", "quoted-exit", "environment", "toolchain",
        ).forEach { mutation ->
            Fixture().use { fixture ->
                fixture.verify(fixture.content.root.resolve("baseline-$mutation"))
                when (mutation) {
                    "ordinal" -> fixture.rewriteExecution("00-toolchain-before-xcode") {
                        JsonObject(it + ("ordinal" to JsonPrimitive(1)))
                    }
                    "quoted-schema" -> fixture.rewriteExecution("00-toolchain-before-xcode") {
                        JsonObject(it + ("schemaVersion" to JsonPrimitive("1")))
                    }
                    "quoted-ordinal" -> fixture.rewriteExecution("00-toolchain-before-xcode") {
                        JsonObject(it + ("ordinal" to JsonPrimitive("0")))
                    }
                    "quoted-exit" -> fixture.rewriteExecution("00-toolchain-before-xcode") {
                        JsonObject(it + ("exitCode" to JsonPrimitive("0")))
                    }
                    "environment" -> fixture.rewriteExecution("00-toolchain-before-xcode") {
                        val environment = it.releaseObject("environment")
                        JsonObject(it + ("environment" to JsonObject(
                            environment + ("LC_ALL" to JsonPrimitive("X")),
                        )))
                    }
                    "toolchain" -> {
                        fixture.event("00-toolchain-before-xcode/combined.bin")
                            .writeText("Xcode 0.0\nBuild version WRONG\n")
                        fixture.refreshExecutionBinding()
                    }
                }
                val cause = when (mutation) {
                    "ordinal", "environment" -> "metadata changed"
                    "toolchain" -> "Unexpected Xcode version"
                    else -> "integer is not numeric"
                }
                expectCausalFailure(cause) { fixture.verify() }
            }
        }
    }

    @Test
    fun `same execution binding rejects changed strip and normalized effects`() {
        listOf("07-device-strip/effect.bin", "08-device-normalize/effect.bin").forEach { relative ->
            Fixture().use { fixture ->
                fixture.verify(fixture.content.root.resolve("baseline-${relative.substringBefore('/')}"))
                fixture.event(relative).appendText("changed")
                expectCausalFailure("input binding changed") { fixture.verify() }
            }
        }
    }

    @Test
    fun `rejects changed authenticated package source and compatibility inputs`() {
        listOf("product", "binary", "source", "compatibility").forEach { mutation ->
            Fixture().use { fixture ->
                fixture.verify(fixture.content.root.resolve("baseline-$mutation"))
                when (mutation) {
                    "product" -> fixture.content.writePackageArchive(mapOf(
                        "Package.swift" to "changed\n".toByteArray(),
                    ))
                    "binary" -> fixture.binary.resolve(
                        "ios-arm64/CodexAgent.framework/CodexAgent",
                    ).appendBytes(byteArrayOf(1))
                    "source" -> fixture.source.resolve(
                        "codex-agent-runtime-ios/apple/Sources/CodexAgent/CodexAgent.swift",
                    ).appendText("changed")
                    "compatibility" -> fixture.content.compatibility.appendText("changed")
                }
                expectCausalFailure("input binding changed") { fixture.verify() }
            }
        }
    }

    @Test
    fun `requires fresh disjoint replay work`() {
        Fixture().use { fixture ->
            fixture.verify(fixture.content.root.resolve("baseline-stale"))
            fixture.work.mkdirs()
            fixture.work.resolve("user-marker").writeText("keep")
            expectCausalFailure("work must be fresh") { fixture.verify() }
            assertContentEquals("keep".toByteArray(), fixture.work.resolve("user-marker").readBytes())
        }
        Fixture().use { fixture ->
            fixture.verify(fixture.content.root.resolve("baseline-overlap"))
            expectCausalFailure("overlaps an input") {
                fixture.verify(fixture.evidence.resolve("work"))
            }
        }
    }

    private class Fixture : AutoCloseable {
        val content = AppleBinaryPackageContentFixture()
        private val history = content.root.resolve("history")
        private val historySource = history.resolve("source")
        private val historyBinary = history.resolve("binary")
        private val historyScratch = history.resolve("scratch").apply { mkdirs() }
        private val historyWork = history.resolve("work")
        private val historyDeveloper = history.resolve("developer").apply { mkdirs() }
        val evidence = content.root.resolve("execution")
        val source = content.root.resolve("current-source")
        val binary = content.root.resolve("current-binary")
        val work = content.root.resolve("pure-replay")
        val originalContext = ApplePackageExecutionContext(
            historyScratch,
            historyWork,
            historySource,
            historyBinary,
            historyDeveloper,
        )
        private val initialProduct: Map<String, String>
        private val initialSource: Map<String, String>
        private val initialBinary: Map<String, String>
        private val initialCompatibility: ByteArray
        private val expectedOriginalInputs = linkedMapOf<String, Map<String, String>>()

        init {
            populateInputs(historySource, historyBinary)
            recordOriginalExecution()
            expectedOriginalInputs.putAll(mapOf(
                "execution" to digests(evidence),
                "product" to digests(content.product),
                "binary" to digests(historyBinary),
                "source" to digests(historySource),
                "compatibility" to mapOf(
                    "sdk-compatibility.json" to content.compatibility.releaseDigest(),
                ),
            ))
            copyReleaseTree(historySource, source)
            copyReleaseTree(historyBinary, binary)
            history.deleteRecursively()
            initialProduct = digests(content.product)
            initialSource = digests(source)
            initialBinary = digests(binary)
            initialCompatibility = content.compatibility.readBytes()
        }

        fun event(relative: String) = evidence.resolve(relative)

        fun rewriteExecution(relative: String, transform: (JsonObject) -> JsonObject) {
            val file = event("$relative/execution.json")
            file.atomicWriteJson(transform(file.readReleaseObject()))
            refreshExecutionBinding()
        }

        fun refreshExecutionBinding() {
            expectedOriginalInputs["execution"] = digests(evidence)
        }

        fun verify(replayWork: File = work) = verifyOriginalApplePackageExecution(
            evidence,
            content.product,
            "0.2.0",
            binary,
            source,
            content.compatibility,
            replayWork,
            originalContext,
            expectedOriginalInputs.mapValues { (_, inventory) -> inventory.toMap() },
            "26.6",
            "17F113",
            "6.3.3",
        )

        fun assertInputsUnchanged() {
            assertContentEquals(initialCompatibility, content.compatibility.readBytes())
            kotlin.test.assertEquals(initialProduct, digests(content.product))
            kotlin.test.assertEquals(initialSource, digests(source))
            kotlin.test.assertEquals(initialBinary, digests(binary))
        }

        private fun recordOriginalExecution() {
            val slices = mapOf("ios-arm64" to "ios-arm64", "ios-simulator-arm64" to "ios-arm64-simulator")
            val recorder = ApplePackageExecutionRecorder(evidence, originalContext)
            fun toolchain() {
                recorder.record(recorder.expectedCommand(), 0, "Xcode 26.6\nBuild version 17F113\n".toByteArray())
                recorder.record(recorder.expectedCommand(), 0, "Apple Swift version 6.3.3\n".toByteArray())
            }
            toolchain()
            verifyAppleBinaryPackageReplay(
                content.product,
                "0.2.0",
                historyBinary,
                historySource,
                content.compatibility,
                historyWork,
                listOf(historyScratch.path, historyWork.path, historySource.path),
                capture = { command ->
                    val output = when {
                        command.first() == "/usr/bin/xcodebuild" -> {
                            val destination = File(command.last())
                            slices.forEach { (target, slice) ->
                                copyReleaseTree(historyBinary.resolve("$target/CodexAgent.framework"),
                                    destination.resolve("$slice/CodexAgent.framework"))
                            }
                            content.expectedXCFramework.resolve("Info.plist")
                                .copyTo(destination.resolve("Info.plist"))
                            ""
                        }
                        command.getOrNull(1) == "lipo" -> "arm64"
                        command.getOrNull(1) == "strip" -> {
                            File(command[6]).copyTo(File(command[5])); ""
                        }
                        command.getOrNull(1) == "libtool" -> {
                            File(command[5]).copyTo(File(command.last())); ""
                        }
                        command.getOrNull(2) == "CFBundleSupportedPlatforms.0" ->
                            if ("ios-simulator-arm64" in command.last()) "iPhoneSimulator" else "iPhoneOS"
                        command.getOrNull(1) == "-extract" -> "[]"
                        command.getOrNull(1) == "-replace" -> ""
                        else -> error("Unexpected fixture command: $command")
                    }
                    recorder.record(command, 0, output.toByteArray())
                    output
                },
                scan = { command ->
                    recorder.record(command, 1, byteArrayOf())
                    1 to ""
                },
            )
            toolchain()
            recorder.finish()
        }

        private fun populateInputs(sourceRoot: File, binaryRoot: File) {
            val apple = sourceRoot.resolve("codex-agent-runtime-ios/apple")
            mapOf("ios-arm64" to "ios-arm64", "ios-simulator-arm64" to "ios-arm64-simulator")
                .forEach { (target, slice) ->
                    val framework = binaryRoot.resolve("$target/CodexAgent.framework")
                    copyReleaseTree(content.expectedXCFramework.resolve("$slice/CodexAgent.framework"), framework)
                    framework.resolve("PrivacyInfo.xcprivacy").delete()
                }
            listOf("Sources", "Tests").forEach {
                copyReleaseTree(content.expectedPackage.resolve(it), apple.resolve(it))
            }
            apple.resolve("TestApp/project.txt").apply { parentFile.mkdirs(); writeText("fixture app") }
            content.expectedPackage.resolve("Package.swift").copyTo(apple.resolve("Package.swift"))
            mapOf(
                "LICENSE.txt" to "LICENSE",
                "THIRD_PARTY_NOTICES.md" to "THIRD_PARTY_NOTICES.md",
                "openai-codex-LICENSE.txt" to "legal/openai-codex/openai-codex-LICENSE.txt",
                "openai-codex-NOTICE.txt" to "legal/openai-codex/openai-codex-NOTICE.txt",
            ).forEach { (from, to) ->
                sourceRoot.resolve(to).also { destination ->
                    destination.parentFile.mkdirs()
                    content.expectedPackage.resolve(from).copyTo(destination)
                }
            }
        }

        private fun digests(root: File) =
            verifiedRegularFiles(root).mapValues { (_, file) -> file.releaseDigest() }

        override fun close() = content.close()
    }
}

private fun expectCausalFailure(message: String, block: () -> Unit) {
    val failure = assertFailsWith<IllegalStateException>(message, block)
    assertTrue(message in failure.message.orEmpty(), "Expected '$message' in '${failure.message}'")
}
