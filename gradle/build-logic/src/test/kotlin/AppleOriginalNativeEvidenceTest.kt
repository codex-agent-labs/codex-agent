import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/** Synthetic archives and observations only; this never invokes Apple or Rust tools. */
class AppleOriginalNativeEvidenceTest {
    @Test
    fun `mixed original producers must match the selected binary source and observations`() {
        val root = createTempDirectory("original-native-replay").toFile()
        try {
            val source = root.resolve("source").apply { mkdir() }
            val native = source.resolve("codex-agent-runtime-ios/native")
            val selected = listOf(
                "patches/0001-uninitialized-in-process-host.patch", "patches/0002-locked-ios-bridge.patch",
                "patches/0003-pinned-ios-sqlite.patch", "sqlite/0001-ios-filesystem-probes.patch",
                "include/codex_agent_ios.h", "bridge/Cargo.toml", "bridge/src/lib.rs",
            ).map { name -> native.resolve(name).apply { parentFile.mkdirs(); writeText("synthetic $name\n") } }
            val provenance = native.resolve("provenance.json")
            File("../../codex-agent-runtime-ios/native/provenance.json").copyTo(provenance)
            val settings = appleRustCompilerSettingsFromProvenance(provenance.readReleaseObject())
            val inputs = selected.toSet() + provenance
            val inputHash = appleNativeInputDigest(source, inputs)
            val evidence = root.resolve("evidence").apply { mkdir() }
            val toolchains = root.resolve("toolchains").apply { mkdir() }
            val xcode = "Xcode 26.6\nBuild version 17F113\n"
            val swift = "Apple Swift version 6.3.3 (synthetic)\n"
            val rust = "rustc ${settings.getValue("rustToolchain")}\nrelease: ${settings.getValue("rustToolchain")}\nhost: aarch64-apple-darwin"
            val producers = mapOf(
                "ios-rust-device" to ("1".repeat(40) to "2".repeat(40)),
                "ios-rust-simulator" to ("3".repeat(40) to "4".repeat(40)),
                "ios-native-tests" to ("5".repeat(40) to "6".repeat(40)),
            )
            appleRustSliceSpecs.forEach { spec ->
                val device = spec.target == IOS_DEVICE_RUST_TARGET
                val (commit, tree) = producers.getValue(if (device) "ios-rust-device" else "ios-rust-simulator")
                val sdk = if (device) "iphoneos" else "iphonesimulator"
                val apple = "xcode=${xcode.trim()}\nsdk=$sdk\nversion=26.6\nbuild=23F1"
                val archive = evidence.resolve(spec.archiveName).apply { writeText("!<arch>\nsynthetic\n") }
                evidence.resolve(spec.proofName).atomicWriteJson(buildAppleRustSliceProof(spec, archive,
                    AppleRustEvidenceIdentity(commit, tree, inputHash, provenance.releaseDigest(),
                        appleCompilerSettingsDigest(settings), settings.getValue("rustToolchain"), "required",
                        rust.byteInputStream().releaseDigest(), apple.byteInputStream().releaseDigest(),
                        xcode.byteInputStream().releaseDigest(), swift.byteInputStream().releaseDigest())))
                toolchains.resolve(spec.proofName.removeSuffix("-proof.json") + "-toolchain.json")
                    .atomicWriteJson(buildJsonObject {
                        put("schemaVersion", JsonPrimitive(1)); put("candidateCommit", JsonPrimitive(commit))
                        put("candidateTree", JsonPrimitive(tree)); put("target", JsonPrimitive(spec.target))
                        put("rustCompilerIdentity", JsonPrimitive(rust)); put("appleToolchainIdentity", JsonPrimitive(apple))
                        put("xcodeVersion", JsonPrimitive(xcode)); put("swiftVersion", JsonPrimitive(swift))
                    })
            }
            val tests = producers.getValue("ios-native-tests")
            evidence.resolve(IOS_NATIVE_TESTS_PROOF).atomicWriteJson(buildAppleNativeTestsProof(
                AppleNativeTestsIdentity(tests.first, tests.second, inputHash, provenance.releaseDigest(),
                    settings.getValue("rustToolchain"), "not-required"),
                listOf(
                    AppleNativeTestCommand(":codex-agent-runtime-ios:testCodexIosBridge",
                        listOf("test", "--locked", "-p", "codex-agent-ios-bridge", "--lib")),
                    AppleNativeTestCommand(":codex-agent-runtime-ios:testCodexIosDirectToolMode",
                        listOf("test", "--locked", "-p", "codex-core", "--lib",
                            "ios_runtime_forces_direct_tools_for_code_mode_only_models")),
                ),
            ))
            fun verify() = verifyOriginalAppleNativeEvidence(evidence, source, toolchains, producers,
                "aarch64-apple-darwin", "26.6", "17F113", "6.3.3")
            verify()
            runReleaseTooling(arrayOf(
                "verify-original-apple-native-evidence", "--evidence-directory", evidence.path,
                "--source-snapshot", source.path, "--toolchain-directory", toolchains.path,
                "--rust-host", "aarch64-apple-darwin", "--xcode-version", "26.6",
                "--xcode-build", "17F113", "--swift-version", "6.3.3",
                "--device-commit", "1".repeat(40), "--device-tree", "2".repeat(40),
                "--simulator-commit", "3".repeat(40), "--simulator-tree", "4".repeat(40),
                "--tests-commit", "5".repeat(40), "--tests-tree", "6".repeat(40),
            ))
            val linked = root.resolve("linked-toolchains")
            java.nio.file.Files.createSymbolicLink(linked.toPath(), toolchains.toPath())
            assertFailsWith<IllegalStateException> {
                verifyOriginalAppleNativeEvidence(evidence, source, linked, producers,
                    "aarch64-apple-darwin", "26.6", "17F113", "6.3.3")
            }
            for (file in listOf(selected.first(), provenance, evidence.resolve(appleRustSliceSpecs[0].archiveName))) {
                val original = file.readBytes()
                file.appendText("tampered")
                assertFailsWith<Exception> { verify() }
                file.writeBytes(original)
                verify()
            }
            val observations = toolchains.listFiles()!!.first()
            val original = observations.readText()
            observations.writeText(original.replace("26.6", "26.5"))
            assertFailsWith<IllegalStateException> { verify() }
            observations.writeText(original)
            val extra = source.resolve("extra").apply { writeText("unselected") }
            assertFailsWith<IllegalStateException> { verify() }
            extra.delete()
            assertFailsWith<IllegalStateException> {
                verifyOriginalAppleNativeEvidence(evidence, source, toolchains,
                    producers + ("ios-rust-device" to producers.getValue("ios-rust-simulator")),
                    "aarch64-apple-darwin", "26.6", "17F113", "6.3.3")
            }
            verify()
        } finally {
            root.deleteRecursively()
        }
    }
}
