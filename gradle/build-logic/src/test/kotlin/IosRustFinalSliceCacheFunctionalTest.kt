import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.gradle.testkit.runner.BuildResult
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class IosRustFinalSliceCacheFunctionalTest {
    @Test
    fun `final Rust slices restore without Cargo and isolate target invalidation`() {
        val project = createTempDirectory("ios-rust-final-slice-cache").toFile()
        try {
            val fakeBin = project.resolve("fake-bin").apply { mkdirs() }
            val testKitDirectory = project.resolve("gradle-user-home")
            val cargoInvocations = project.resolve("cargo-invocations.txt")
            writeFakeRustTools(fakeBin)
            project.resolve("native/input.txt").apply { parentFile.mkdirs(); writeText("native-input") }
            project.resolve("native/patch.txt").writeText("native-patch")
            project.resolve("settings.gradle.kts").writeText("rootProject.name = \"ios-rust-cache-test\"\n")
            project.resolve("gradle.properties").writeText("org.gradle.caching=true\n")
            writeBuild(project, fakeBin, cargoInvocations, "device-sdk-1")

            val first = run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(TaskOutcome.SUCCESS, first.task(":$DEVICE_TASK")?.outcome)
            assertEquals(TaskOutcome.SUCCESS, first.task(":$SIMULATOR_TASK")?.outcome)
            val deviceArchive = archive(project, DEVICE_TARGET)
            val simulatorArchive = archive(project, SIMULATOR_TARGET)
            val deviceBytes = deviceArchive.readBytes()
            val simulatorBytes = simulatorArchive.readBytes()
            assertEquals(mapOf(DEVICE_TARGET to 1, SIMULATOR_TARGET to 1), invocationCounts(cargoInvocations))

            project.resolve("build/rust").deleteRecursively()
            project.resolve("src/commonMain/kotlin/Unrelated.kt")
                .apply { parentFile.mkdirs(); writeText("internal const val unrelated = 1\n") }
            project.resolve("Sources/Wrapper.swift")
                .apply { parentFile.mkdirs(); writeText("internal let unrelated = 1\n") }
            val restored = run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(TaskOutcome.FROM_CACHE, restored.task(":$DEVICE_TASK")?.outcome)
            assertEquals(TaskOutcome.FROM_CACHE, restored.task(":$SIMULATOR_TASK")?.outcome)
            assertContentEquals(deviceBytes, deviceArchive.readBytes())
            assertContentEquals(simulatorBytes, simulatorArchive.readBytes())
            assertEquals(mapOf(DEVICE_TARGET to 1, SIMULATOR_TARGET to 1), invocationCounts(cargoInvocations))

            writeBuild(project, fakeBin, cargoInvocations, "device-sdk-2")
            project.resolve("build/rust").deleteRecursively()
            val invalidated = run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(TaskOutcome.SUCCESS, invalidated.task(":$DEVICE_TASK")?.outcome)
            assertEquals(TaskOutcome.FROM_CACHE, invalidated.task(":$SIMULATOR_TASK")?.outcome)
            assertEquals(mapOf(DEVICE_TARGET to 2, SIMULATOR_TARGET to 1), invocationCounts(cargoInvocations))

            project.resolve("native/input.txt").writeText("changed-native-input")
            run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(mapOf(DEVICE_TARGET to 3, SIMULATOR_TARGET to 2), invocationCounts(cargoInvocations))

            project.resolve("native/patch.txt").writeText("changed-native-patch")
            run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(mapOf(DEVICE_TARGET to 4, SIMULATOR_TARGET to 3), invocationCounts(cargoInvocations))

            writeBuild(project, fakeBin, cargoInvocations, "device-sdk-2", rustFlag = "-Copt-level=1")
            run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(mapOf(DEVICE_TARGET to 5, SIMULATOR_TARGET to 4), invocationCounts(cargoInvocations))

            writeBuild(
                project,
                fakeBin,
                cargoInvocations,
                "device-sdk-2",
                rustToolchain = "fixture-2",
                rustFlag = "-Copt-level=1",
            )
            run(project, testKitDirectory, fakeBin, true, DEVICE_TASK, SIMULATOR_TASK)
            assertEquals(mapOf(DEVICE_TARGET to 6, SIMULATOR_TARGET to 5), invocationCounts(cargoInvocations))

            deviceArchive.delete()
            val cacheDisabled = run(project, testKitDirectory, fakeBin, false, DEVICE_TASK)
            assertEquals(TaskOutcome.SUCCESS, cacheDisabled.task(":$DEVICE_TASK")?.outcome)
            assertEquals(mapOf(DEVICE_TARGET to 7, SIMULATOR_TARGET to 5), invocationCounts(cargoInvocations))
            assertTrue(deviceArchive.isFile)
        } finally {
            project.deleteRecursively()
        }
    }

    private fun writeBuild(
        project: File,
        fakeBin: File,
        cargoInvocations: File,
        deviceIdentity: String,
        rustToolchain: String = "fixture",
        rustFlag: String = "-Copt-level=0",
    ) {
        val toolPath = "${fakeBin.absolutePath}${File.pathSeparator}${System.getenv("PATH")}"
        val retainedEnvironment =
            "mapOf(\"PATH\" to ${quoted(toolPath)}, \"CARGO_HOME\" to " +
                "${quoted(project.resolve("cargo-home").absolutePath)})"
        project.resolve("build.gradle.kts").writeText(
            """
            plugins { id("codexagent.codex-runtime") }

            tasks.register<CachedPinnedCargoTask>("$DEVICE_TASK") {
                toolchain.set("$rustToolchain")
                workingDirectory.set(layout.projectDirectory.dir("native"))
                sourceInputs.from(
                    layout.projectDirectory.file("native/input.txt"),
                    layout.projectDirectory.file("native/patch.txt"),
                )
                cargoTargetDirectory.set(layout.buildDirectory.dir("rust"))
                cargoArguments.set(listOf("build", "--target", "$DEVICE_TARGET"))
                retainedEnvironment.putAll($retainedEnvironment)
                extraEnvironment.put("CARGO_INVOCATIONS", ${quoted(cargoInvocations.absolutePath)})
                rustcArguments.set(listOf("$rustFlag"))
                rustCompilerIdentity.set("rustc-fixture")
                appleToolchainIdentity.set("$deviceIdentity")
                archiveOutput.set(layout.buildDirectory.file("rust/$DEVICE_TARGET/release/$LIBRARY"))
            }

            tasks.register<CachedPinnedCargoTask>("$SIMULATOR_TASK") {
                toolchain.set("$rustToolchain")
                workingDirectory.set(layout.projectDirectory.dir("native"))
                sourceInputs.from(
                    layout.projectDirectory.file("native/input.txt"),
                    layout.projectDirectory.file("native/patch.txt"),
                )
                cargoTargetDirectory.set(layout.buildDirectory.dir("rust"))
                cargoArguments.set(listOf("build", "--target", "$SIMULATOR_TARGET"))
                retainedEnvironment.putAll($retainedEnvironment)
                extraEnvironment.put("CARGO_INVOCATIONS", ${quoted(cargoInvocations.absolutePath)})
                rustcArguments.set(listOf("$rustFlag"))
                rustCompilerIdentity.set("rustc-fixture")
                appleToolchainIdentity.set("simulator-sdk-1")
                archiveOutput.set(layout.buildDirectory.file("rust/$SIMULATOR_TARGET/release/$LIBRARY"))
            }
            """.trimIndent(),
        )
    }

    private fun run(
        project: File,
        testKitDirectory: File,
        fakeBin: File,
        buildCache: Boolean,
        vararg tasks: String,
    ): BuildResult = GradleRunner.create()
        .withProjectDir(project)
        .withTestKitDir(testKitDirectory)
        .withPluginClasspath()
        .withEnvironment(System.getenv() + ("PATH" to "${fakeBin.absolutePath}${File.pathSeparator}${System.getenv("PATH")}"))
        .withArguments(
            if (buildCache) "--build-cache" else "--no-build-cache",
            "--console=plain",
            "--stacktrace",
            *tasks,
        )
        .build()

    private fun writeFakeRustTools(directory: File) {
        writeExecutable(
            directory.resolve("rustup"),
            listOf(
                "#!/bin/sh",
                "set -eu",
                "tool=",
                "for value in \"\$@\"; do tool=\"\$value\"; done",
                "printf '%s\\n' \"\$(dirname \"\$0\")/\$tool\"",
            ),
        )
        writeExecutable(
            directory.resolve("cargo"),
            listOf(
                "#!/bin/sh",
                "set -eu",
                "target=",
                "take_target=0",
                "for value in \"\$@\"; do",
                "  if [ \"\$take_target\" = 1 ]; then target=\"\$value\"; take_target=0; fi",
                "  if [ \"\$value\" = --target ]; then take_target=1; fi",
                "done",
                "test -n \"\$target\"",
                "printf '%s\\n' \"\$target\" >> \"\$CARGO_INVOCATIONS\"",
                "mkdir -p \"\$CARGO_TARGET_DIR/\$target/release\"",
                "printf 'archive:%s\\n' \"\$target\" > \"\$CARGO_TARGET_DIR/\$target/release/$LIBRARY\"",
            ),
        )
        listOf("rustc", "rustdoc").forEach { name ->
            writeExecutable(directory.resolve(name), listOf("#!/bin/sh", "exit 0"))
        }
    }

    private fun writeExecutable(file: File, lines: List<String>) {
        file.writeText(lines.joinToString("\n", postfix = "\n"))
        assertTrue(file.setExecutable(true), "Could not make ${file.name} executable")
    }

    private fun archive(project: File, target: String) = project.resolve("build/rust/$target/release/$LIBRARY")

    private fun invocationCounts(file: File) = file.readLines().groupingBy(String::trim).eachCount()

    private fun quoted(value: String) = "\"${value.replace("\\", "\\\\").replace("\"", "\\\"")}\""

    private companion object {
        const val DEVICE_TASK = "buildFixtureDeviceRust"
        const val SIMULATOR_TASK = "buildFixtureSimulatorRust"
        const val DEVICE_TARGET = "aarch64-apple-ios"
        const val SIMULATOR_TARGET = "aarch64-apple-ios-sim"
        const val LIBRARY = "libcodex_agent_ios_bridge.a"
    }
}
