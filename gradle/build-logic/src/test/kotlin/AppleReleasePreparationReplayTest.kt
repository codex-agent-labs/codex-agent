import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Shared-transform checks with simulated tools; not Apple compiler or host evidence. */
class AppleReleasePreparationReplayTest {
    @Test
    fun `replay uses exact ordered transformations and preserves original inputs`() {
        fixture { assembled, release, privacy ->
            val before = assembled.crossLanguageTreeDigest()
            val commands = mutableListOf<List<String>>()
            val scans = mutableListOf<List<String>>()
            prepareAppleReleaseXCFramework(assembled, release, privacy, listOf("/private-builder"),
                capture = { command ->
                    commands += command
                    simulate(command)
                },
                scan = { command -> scans += command; 1 to "" },
            )
            val first = release.crossLanguageTreeDigest()
            assertEquals(before, assembled.crossLanguageTreeDigest())
            assertEquals(6, commands.size)
            slices.forEachIndexed { index, slice ->
                val framework = release.resolve("$slice/CodexAgent.framework")
                val archive = framework.resolve("CodexAgent")
                assertEquals(stripReleaseArchiveCommand(archive, framework.resolve("CodexAgent.stripped")), commands[index * 2])
                assertEquals(libtoolNormalizeCommand(framework.resolve("CodexAgent.stripped"),
                    framework.resolve("CodexAgent.normalized")), commands[index * 2 + 1])
                assertEquals(pathPrefixScanCommand(archive, listOf("/private-builder")), scans[index])
                assertEquals("normalized:stripped:original-$slice", archive.readText())
                assertEquals("header-$slice", framework.resolve("Headers/CodexAgent.h").readText())
                assertEquals(privacy.readText(), framework.resolve("PrivacyInfo.xcprivacy").readText())
                assertFalse(framework.resolve("CodexAgent.stripped").exists())
                assertFalse(framework.resolve("CodexAgent.normalized").exists())
            }
            assertEquals("[{\"LibraryIdentifier\":\"a\"},{\"LibraryIdentifier\":\"z\"}]", release.resolve("Info.plist").readText())
            release.resolve("stale").writeText("old")
            prepareAppleReleaseXCFramework(assembled, release, privacy, listOf("/private-builder"), ::simulate) { 1 to "" }
            assertEquals(first, release.crossLanguageTreeDigest())
            assertEquals(before, assembled.crossLanguageTreeDigest())
        }
    }

    @Test
    fun `failed tools and path scans fail closed and clean transient archive files`() {
        listOf("strip", "libtool", "scan-match", "scan-error", "plist").forEach { failure ->
            fixture { assembled, release, privacy ->
                val before = assembled.crossLanguageTreeDigest()
                assertFailsWith<IllegalStateException>(failure) {
                    prepareAppleReleaseXCFramework(assembled, release, privacy, listOf("/private-builder"),
                        capture = { command ->
                            if (command.getOrNull(1) == failure || (failure == "plist" && command.first() == "/usr/bin/plutil")) {
                                error("simulated process failure")
                            }
                            simulate(command)
                        },
                        scan = { if (failure == "scan-match") 0 to "" else if (failure == "scan-error") 2 to "scan failed" else 1 to "" },
                    )
                }
                assertEquals(before, assembled.crossLanguageTreeDigest())
                assertFalse(release.walkTopDown().any { it.name.endsWith(".stripped") || it.name.endsWith(".normalized") })
            }
        }
    }

    private fun simulate(command: List<String>): String = when {
        command.getOrNull(1) == "strip" -> {
            File(command[5]).writeText("stripped:" + File(command[6]).readText()); ""
        }
        command.getOrNull(1) == "libtool" -> {
            File(command.last()).writeText("normalized:" + File(command[5]).readText()); ""
        }
        command.getOrNull(1) == "-extract" -> "[{\"LibraryIdentifier\":\"z\"},{\"LibraryIdentifier\":\"a\"}]"
        command.getOrNull(1) == "-replace" -> {
            File(command.last()).writeText(command[4]); ""
        }
        else -> error("Unexpected command: $command")
    }

    private fun fixture(block: (File, File, File) -> Unit) {
        val root = createTempDirectory("apple-preparation-replay-").toFile()
        try {
            val assembled = root.resolve("assembled").apply { mkdirs() }
            slices.forEach { slice ->
                val framework = assembled.resolve("$slice/CodexAgent.framework").apply { mkdirs() }
                framework.resolve("CodexAgent").writeText("original-$slice")
                framework.resolve("Headers").mkdirs()
                framework.resolve("Headers/CodexAgent.h").writeText("header-$slice")
            }
            assembled.resolve("Info.plist").writeText("original plist")
            val privacy = root.resolve("PrivacyInfo.xcprivacy").apply { writeText("privacy") }
            block(assembled, root.resolve("release"), privacy)
        } finally {
            assertTrue(root.deleteRecursively())
        }
    }

    private val slices = listOf("ios-arm64", "ios-arm64-simulator")
}
