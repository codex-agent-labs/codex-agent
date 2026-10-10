import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlinx.serialization.json.JsonNull
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class ApplePackageExecutionEvidenceTest {
    @Test
    fun `records exact ordered merged observations and declared effects`() {
        Fixture().use { fixture ->
            val recorder = fixture.recorder()
            fixture.recordComplete(recorder)
            recorder.finish()

            val files = verifiedRegularFiles(fixture.evidence)
            assertEquals(17, files.keys.count { it.endsWith("/execution.json") })
            assertEquals(17, files.keys.count { it.endsWith("/combined.bin") })
            assertEquals("assembled", files.getValue(
                "06-assemble-xcframework/effect/Info.plist",
            ).readText())
            assertEquals("device-normalized", files.getValue("08-device-normalize/effect.bin").readText())
            val execution = fixture.evidence.resolve("09-device-path-scan/execution.json").readReleaseObject()
            assertEquals("stderr-merged-into-stdout", execution.releaseString("streamMode"))
            assertEquals(1, execution.releaseInt("exitCode"))
        }
    }

    @Test
    fun `preserves empty and binary merged stream observations exactly`() {
        Fixture().use { fixture ->
            val empty = byteArrayOf()
            val binary = byteArrayOf(0, -1, -128, 10, 13)
            val recorder = fixture.recorder()
            fixture.recordComplete(recorder, mapOf(
                ApplePackageExecutionStep.TOOLCHAIN_BEFORE_XCODE to empty,
                ApplePackageExecutionStep.TOOLCHAIN_BEFORE_SWIFT to binary,
            ))
            recorder.finish()

            assertContentEquals(empty, fixture.evidence.resolve(
                "00-toolchain-before-xcode/combined.bin",
            ).readBytes())
            assertContentEquals(binary, fixture.evidence.resolve(
                "01-toolchain-before-swift/combined.bin",
            ).readBytes())
        }
    }

    @Test
    fun `rejects wrong order and retains a failed raw observation`() {
        Fixture().use { fixture ->
            val recorder = fixture.recorder()
            assertFailsWith<IllegalStateException> {
                recorder.record(listOf("/usr/bin/xcrun", "swift", "--version"), 0, byteArrayOf())
            }
            assertTrue(verifiedRegularFiles(fixture.evidence).isEmpty())

            val command = recorder.expectedCommand()
            assertFailsWith<IllegalStateException> { recorder.record(command, 9, "failed".toByteArray()) }
            assertEquals("failed", fixture.evidence.resolve(
                "00-toolchain-before-xcode/combined.bin",
            ).readText())
            assertEquals(9, fixture.evidence.resolve(
                "00-toolchain-before-xcode/execution.json",
            ).readReleaseObject().releaseInt("exitCode"))
        }
    }

    @Test
    fun `retains null launch failure and rejects incomplete evidence`() {
        Fixture().use { fixture ->
            val recorder = fixture.recorder()
            val command = recorder.expectedCommand()
            assertFailsWith<IllegalStateException> {
                recorder.record(command, null, byteArrayOf(0, -1))
            }
            assertContentEquals(byteArrayOf(0, -1), fixture.evidence.resolve(
                "00-toolchain-before-xcode/combined.bin",
            ).readBytes())
            assertEquals(JsonNull, fixture.evidence.resolve(
                "00-toolchain-before-xcode/execution.json",
            ).readReleaseObject()["exitCode"])
            assertFailsWith<IllegalStateException> { recorder.finish() }
        }
    }

    @Test
    fun `finish rejects changed bytes and inventory without rewriting original effects`() {
        listOf("execution", "combined", "effect", "added", "removed").forEach { mutation ->
            Fixture().use { fixture ->
                val recorder = fixture.recorder()
                fixture.recordComplete(recorder)
                recorder.finish()
                val original = fixture.work.resolve(
                    "release/CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent.normalized",
                )
                val originalBytes = original.readBytes()
                when (mutation) {
                    "execution" -> fixture.evidence.resolve(
                        "00-toolchain-before-xcode/execution.json",
                    ).appendText("changed")
                    "combined" -> fixture.evidence.resolve(
                        "00-toolchain-before-xcode/combined.bin",
                    ).appendBytes(byteArrayOf(1))
                    "effect" -> fixture.evidence.resolve(
                        "08-device-normalize/effect.bin",
                    ).appendBytes(byteArrayOf(1))
                    "added" -> fixture.evidence.resolve("unexpected.bin").writeText("unexpected")
                    "removed" -> fixture.evidence.resolve(
                        "08-device-normalize/effect.bin",
                    ).delete()
                }
                assertFailsWith<IllegalStateException>(mutation) { recorder.finish() }
                assertContentEquals(originalBytes, original.readBytes(), mutation)
            }
        }
    }

    @Test
    fun `requires fresh disjoint normalized evidence`() {
        Fixture().use { fixture ->
            fixture.evidence.mkdirs()
            assertFailsWith<IllegalStateException> { fixture.recorder() }
        }
        Fixture().use { fixture ->
            assertFailsWith<IllegalStateException> {
                fixture.recorder(fixture.work.resolve("evidence"))
            }
        }
    }

    private class Fixture : AutoCloseable {
        val root = createTempDirectory("apple-package-execution-").toFile().canonicalFile
        val scratch = root.resolve("scratch").apply { mkdirs() }
        val work = root.resolve("work")
        val source = root.resolve("source").apply { mkdirs() }
        val binary = root.resolve("binary").apply { mkdirs() }
        val developer = root.resolve("developer").apply { mkdirs() }
        val evidence = root.resolve("evidence")

        fun recorder(output: File = evidence) = ApplePackageExecutionRecorder(
            output,
            ApplePackageExecutionContext(scratch, work, source, binary, developer),
        )

        fun recordComplete(
            recorder: ApplePackageExecutionRecorder,
            combinedOverrides: Map<ApplePackageExecutionStep, ByteArray> = emptyMap(),
        ) {
            ApplePackageExecutionStep.entries.forEach { step ->
                when (step) {
                    ApplePackageExecutionStep.ASSEMBLE_XCFRAMEWORK ->
                        work.resolve("assembled/CodexAgent.xcframework/Info.plist").also {
                            it.parentFile.mkdirs(); it.writeText("assembled")
                        }
                    ApplePackageExecutionStep.DEVICE_STRIP -> effect(
                        "release/CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent.stripped",
                        "device-stripped",
                    )
                    ApplePackageExecutionStep.DEVICE_NORMALIZE -> effect(
                        "release/CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent.normalized",
                        "device-normalized",
                    )
                    ApplePackageExecutionStep.SIMULATOR_STRIP -> effect(
                        "release/CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/CodexAgent.stripped",
                        "simulator-stripped",
                    )
                    ApplePackageExecutionStep.SIMULATOR_NORMALIZE -> effect(
                        "release/CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/CodexAgent.normalized",
                        "simulator-normalized",
                    )
                    ApplePackageExecutionStep.REWRITE_AVAILABLE_LIBRARIES ->
                        effect("release/CodexAgent.xcframework/Info.plist", "rewritten")
                    else -> Unit
                }
                val combined = combinedOverrides[step] ?: when (step) {
                    ApplePackageExecutionStep.AVAILABLE_LIBRARIES -> "[]"
                    else -> step.directoryName
                }.toByteArray()
                recorder.record(recorder.expectedCommand(), step.expectedExitCode, combined)
            }
        }

        private fun effect(relative: String, contents: String) {
            work.resolve(relative).also { it.parentFile.mkdirs(); it.writeText(contents) }
        }

        override fun close() = root.deleteRecursively().let { Unit }
    }
}
