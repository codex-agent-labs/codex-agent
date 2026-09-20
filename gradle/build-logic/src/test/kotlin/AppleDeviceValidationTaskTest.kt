import java.io.File
import java.io.OutputStream
import java.lang.reflect.Proxy
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Action
import org.gradle.process.ExecOperations
import org.gradle.process.ExecResult
import org.gradle.process.ExecSpec

/** Mock-process fixtures only; they do not claim native Xcode or Apple host acceptance. */
class AppleDeviceValidationTaskTest {
    @Test
    fun `command is the fixed legacy device archive recipe`() = fixture().use { fixture ->
        assertEquals(listOf(
            "/usr/bin/xcodebuild",
            "-project", "CodexAgentTestApp.xcodeproj",
            "-scheme", "CodexAgentTestApp",
            "-configuration", "Release",
            "-destination", "generic/platform=iOS",
            "-derivedDataPath", fixture.work.resolve("derived-data").absolutePath,
            "-archivePath", fixture.work.resolve("CodexAgentTestApp.xcarchive").absolutePath,
            "ARCHS=arm64", "CODE_SIGNING_ALLOWED=NO", "SKIP_INSTALL=NO", "clean", "archive",
        ), appleDeviceValidationCommand(fixture.work))
    }

    @Test
    fun `successful mock preserves inputs archive and real raw capture triplet`() = fixture().use { fixture ->
        val before = fixture.inputDigests()
        val operations = fixture.operations(exitCode = 0)

        fixture.verify(operations)

        assertEquals(before, fixture.inputDigests())
        assertTrue(fixture.archive.resolve("Products/Application.bin").isFile)
        val raw = fixture.work.resolve("raw/xcodebuild")
        assertEquals(setOf("execution.json", "stdout.bin", "stderr.bin"), verifiedRegularFiles(raw).keys)
        assertContentEquals(byteArrayOf(0, -1, 10), raw.resolve("stdout.bin").readBytes())
        assertContentEquals(byteArrayOf(), raw.resolve("stderr.bin").readBytes())
        val execution = raw.resolve("execution.json").readReleaseObject()
        assertEquals("0", execution.getValue("exitCode").toString())
        assertEquals(
            kotlinx.serialization.json.JsonPrimitive(fixture.developerDirectory.absolutePath),
            execution.releaseObject("environment").getValue("DEVELOPER_DIR"),
        )
        assertEquals(
            kotlinx.serialization.json.JsonPrimitive(fixture.testApplication.absolutePath),
            execution.getValue("workingDirectory"),
        )
    }

    @Test
    fun `nonzero and launch failure retain raw captures before rejection`() {
        for (launchFailure in listOf(false, true)) fixture().use { fixture ->
            val failure = assertFailsWith<IllegalStateException> {
                fixture.verify(fixture.operations(exitCode = 65, launchFailure = launchFailure))
            }
            assertTrue(if (launchFailure) "synthetic launch failure" in failure.message.orEmpty()
                else "failed (65)" in failure.message.orEmpty())
            val raw = fixture.work.resolve("raw/xcodebuild")
            assertEquals(setOf("execution.json", "stdout.bin", "stderr.bin"), verifiedRegularFiles(raw).keys)
            assertEquals(if (launchFailure) "null" else "65",
                raw.resolve("execution.json").readReleaseObject().getValue("exitCode").toString())
        }
    }

    @Test
    fun `rejects unsafe empty stale overlapping and nonsibling inputs without mutation`() {
        listOf("empty", "symlink", "stale", "overlap", "layout").forEach { mutation ->
            fixture().use { fixture ->
                val before = fixture.inputDigests()
                when (mutation) {
                    "empty" -> fixture.packageDirectory.resolve("Sources/Client.swift").writeBytes(byteArrayOf())
                    "symlink" -> Files.createSymbolicLink(
                        fixture.packageDirectory.resolve("Sources/Linked.swift").toPath(),
                        fixture.packageDirectory.resolve("Sources/Client.swift").toPath(),
                    )
                    "stale" -> fixture.work.apply { mkdirs() }.resolve("marker").writeText("preserve\n")
                    else -> Unit
                }
                val work = if (mutation == "overlap") fixture.packageDirectory.resolve("work") else fixture.work
                val packageRoot = if (mutation == "layout") fixture.root.resolve("other-package").also {
                    fixture.packageDirectory.copyRecursively(it)
                } else fixture.packageDirectory
                assertFailsWith<IllegalStateException>(mutation) {
                    verifyAppleDeviceConsumer(
                        fixture.testApplication, packageRoot, fixture.developerDirectory, work, fixture.operations(),
                    )
                }
                if (mutation == "stale") assertEquals("preserve\n", fixture.work.resolve("marker").readText())
                if (mutation in setOf("stale", "overlap", "layout")) assertEquals(before, fixture.inputDigests())
            }
        }
    }

    @Test
    fun `late input mutation is rejected after captured process evidence`() = fixture().use { fixture ->
        val operations = fixture.operations(afterConfiguration = {
            fixture.packageDirectory.resolve("Package.swift").appendText("// changed\n")
        })

        assertFailsWith<IllegalStateException> { fixture.verify(operations) }

        assertTrue(fixture.work.resolve("raw/xcodebuild/execution.json").isFile)
    }
}

private class AppleDeviceValidationFixture : AutoCloseable {
    val root = createTempDirectory("apple-device-validation").toFile().canonicalFile
    private val staged = root.resolve("staged")
    val testApplication = staged.resolve("CodexAgentTestApp")
    val packageDirectory = staged.resolve("CodexAgentPackage")
    val developerDirectory = root.resolve("Developer").apply { mkdirs() }
    val work = root.resolve("work")
    val archive = work.resolve("CodexAgentTestApp.xcarchive")

    init {
        testApplication.resolve("CodexAgentTestApp.xcodeproj/project.pbxproj").fixture("project\n")
        testApplication.resolve("Sources/App.swift").fixture("app\n")
        packageDirectory.resolve("Package.swift").fixture("// swift-tools-version: 6.0\n")
        packageDirectory.resolve("Sources/Client.swift").fixture("client\n")
    }

    fun operations(
        exitCode: Int = 0,
        launchFailure: Boolean = false,
        afterConfiguration: () -> Unit = {},
    ): ExecOperations {
        var stdout: OutputStream? = null
        var stderr: OutputStream? = null
        var workingDirectory: File? = null
        val spec = Proxy.newProxyInstance(
            ExecSpec::class.java.classLoader,
            arrayOf(ExecSpec::class.java),
        ) { _, method, arguments ->
            when (method.name) {
                "setStandardOutput" -> stdout = arguments!![0] as OutputStream
                "setErrorOutput" -> stderr = arguments!![0] as OutputStream
                "workingDir", "setWorkingDir" -> workingDirectory = arguments!![0] as File
                "getWorkingDir" -> return@newProxyInstance workingDirectory ?: root
            }
            null
        } as ExecSpec
        return Proxy.newProxyInstance(
            ExecOperations::class.java.classLoader,
            arrayOf(ExecOperations::class.java),
        ) { _, method, arguments ->
            check(method.name == "exec")
            @Suppress("UNCHECKED_CAST")
            (arguments!![0] as Action<ExecSpec>).execute(spec)
            stdout!!.write(byteArrayOf(0, -1, 10))
            stderr!!.write(byteArrayOf())
            afterConfiguration()
            if (launchFailure) error("synthetic launch failure")
            if (exitCode == 0) archive.resolve("Products/Application.bin").fixture("archive\n")
            Proxy.newProxyInstance(
                ExecResult::class.java.classLoader,
                arrayOf(ExecResult::class.java),
            ) { _, call, _ ->
                check(call.name == "getExitValue")
                exitCode
            } as ExecResult
        } as ExecOperations
    }

    fun verify(processes: ExecOperations) =
        verifyAppleDeviceConsumer(testApplication, packageDirectory, developerDirectory, work, processes)

    fun inputDigests() = mapOf(
        "test-application" to testApplication.digests(),
        "package" to packageDirectory.digests(),
    )

    override fun close() {
        root.deleteRecursively()
    }
}

private fun File.fixture(contents: String) {
    parentFile.mkdirs()
    writeText(contents)
}

private fun File.digests() = verifiedRegularFiles(this).mapValues { (_, file) -> file.releaseDigest() }

private fun fixture() = AppleDeviceValidationFixture()
