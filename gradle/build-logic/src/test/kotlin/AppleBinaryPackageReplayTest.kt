import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** Simulated assembly tools test wiring and byte binding, never actual host/compiler acceptance. */
class AppleBinaryPackageReplayTest {
    @Test
    fun `replays from originals and rejects changed original binary or source`() {
        listOf("none", "binary", "source", "late-binary").forEach { mutation ->
            AppleBinaryPackageContentFixture().use { fixture ->
                val sources = fixture.root.resolve("sources")
                val apple = sources.resolve("codex-agent-runtime-ios/apple")
                val binary = fixture.root.resolve("binary")
                val slices = mapOf("ios-arm64" to "ios-arm64", "ios-simulator-arm64" to "ios-arm64-simulator")
                slices.forEach { (target, slice) ->
                    val raw = binary.resolve("$target/CodexAgent.framework")
                    copyReleaseTree(fixture.expectedXCFramework.resolve("$slice/CodexAgent.framework"), raw)
                    raw.resolve("PrivacyInfo.xcprivacy").delete()
                }
                listOf("Sources", "Tests").forEach {
                    copyReleaseTree(fixture.expectedPackage.resolve(it), apple.resolve(it))
                }
                apple.resolve("TestApp").mkdirs()
                apple.resolve("TestApp/project.txt").writeText("fixture app")
                fixture.expectedPackage.resolve("Package.swift").copyTo(apple.resolve("Package.swift"))
                mapOf("LICENSE.txt" to "LICENSE", "THIRD_PARTY_NOTICES.md" to "THIRD_PARTY_NOTICES.md",
                    "openai-codex-LICENSE.txt" to "legal/openai-codex/openai-codex-LICENSE.txt",
                    "openai-codex-NOTICE.txt" to "legal/openai-codex/openai-codex-NOTICE.txt").forEach { (from, to) ->
                    val destination = sources.resolve(to)
                    destination.parentFile.mkdirs()
                    fixture.expectedPackage.resolve(from).copyTo(destination)
                }
                val rawBinary = binary.resolve("ios-arm64/CodexAgent.framework/CodexAgent")
                if (mutation == "binary") rawBinary.appendText("changed")
                if (mutation == "source") apple.resolve("Sources/CodexAgent/CodexAgent.swift").appendText("changed")
                val commands = mutableListOf<List<String>>()
                val work = fixture.root.resolve("replay")
                val scratch = fixture.root.resolve("scratch").apply { mkdirs() }
                val developer = fixture.root.resolve("developer").apply { mkdirs() }
                val evidence = fixture.root.resolve("execution-evidence")
                val recorder = ApplePackageExecutionRecorder(evidence,
                    ApplePackageExecutionContext(scratch, work, sources, binary, developer))
                fun toolchainObservations() {
                    recorder.record(listOf("/usr/bin/xcodebuild", "-version"), 0,
                        "Xcode 26.6\nBuild version 17F113\n".toByteArray())
                    recorder.record(listOf("/usr/bin/xcrun", "swift", "--version"), 0,
                        "Apple Swift version 6.3.3\n".toByteArray())
                }
                val replay = {
                    toolchainObservations()
                    verifyAppleBinaryPackageReplay(fixture.product, "0.2.0", binary, sources,
                        fixture.compatibility, work, listOf(scratch.path, work.path, sources.path),
                        capture = { command ->
                            commands += command
                            val output = when {
                                command.first() == "/usr/bin/xcodebuild" -> {
                                    val output = File(command.last())
                                    slices.forEach { (target, slice) ->
                                        copyReleaseTree(binary.resolve("$target/CodexAgent.framework"), output.resolve("$slice/CodexAgent.framework"))
                                    }
                                    fixture.expectedXCFramework.resolve("Info.plist").copyTo(output.resolve("Info.plist"))
                                    ""
                                }
                                command.getOrNull(1) == "lipo" -> "arm64"
                                command.getOrNull(1) == "strip" -> { File(command[6]).copyTo(File(command[5])); "" }
                                command.getOrNull(1) == "libtool" -> { File(command[5]).copyTo(File(command.last())); "" }
                                command.getOrNull(2) == "CFBundleSupportedPlatforms.0" ->
                                    if ("ios-simulator-arm64" in command.last()) "iPhoneSimulator" else "iPhoneOS"
                                command.getOrNull(1) == "-extract" -> "[]"
                                command.getOrNull(1) == "-replace" -> {
                                    if (mutation == "late-binary") rawBinary.appendText("late change")
                                    ""
                                }
                                else -> error("Unexpected command $command")
                            }
                            recorder.record(command, 0, output.toByteArray())
                            output
                        }, scan = { command ->
                            recorder.record(command, 1, byteArrayOf())
                            1 to ""
                        },
                    )
                    toolchainObservations()
                    recorder.finish()
                }
                if (mutation == "none") replay() else assertFailsWith<IllegalStateException>(mutation) { replay() }
                assertEquals(1, commands.count { it.first() == "/usr/bin/xcodebuild" })
                assertTrue(commands.none { command -> command.any { it in setOf("compile", "test", "archive", "-emit-library") } })
            }
        }
    }
}
