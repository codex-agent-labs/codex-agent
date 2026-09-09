import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/** Synthetic proof-bound archives; no Apple compiler, XCTest, or product receipt acceptance. */
class AppleSdkDistributionPackageTaskTest {
    @Test
    fun `artifact stage preserves exact original archives`() = fixture().use { fixture ->
        val before = fixture.originalDigests()
        val expectedValidation = fixture.expectedValidationDigests()
        fixture.output.apply { mkdirs() }.resolve("stale").writeText("remove")
        fixture.validationOutput.apply { mkdirs() }.resolve("stale").writeText("remove")
        fixture.stage()
        assertEquals(before, fixture.originalDigests())
        assertEquals(fixture.productDigests(), fixture.outputDigests())
        assertEquals(expectedValidation, fixture.validationDigests())
    }

    @Test
    fun `transported product and external evidence rerun the full Apple verifier`() = fixture().use { fixture ->
        fixture.prepareFullClosure()
        fixture.stage()
        val before = fixture.transportedDigests()
        fixture.verifyTransported()
        assertEquals(before, fixture.transportedDigests())
    }

    @Test
    fun `caller expectations bind exact compatibility and original distribution proof`() = fixture().use { fixture ->
        fixture.prepareFullClosure()
        fixture.stage()
        val before = fixture.originalDigests() + fixture.transportedDigests()
        fixture.verifyTransportedWithCallerExpectations()
        assertEquals(before, fixture.originalDigests() + fixture.transportedDigests())
    }

    @Test
    fun `standalone packaged tool verifies the complete caller-bound Apple closure`() = fixture().use { fixture ->
        fixture.prepareFullClosure()
        fixture.stage()
        val before = fixture.originalDigests() + fixture.transportedDigests()
        fixture.verifyUsingPackagedTool()
        assertEquals(before, fixture.originalDigests() + fixture.transportedDigests())
    }

    @Test
    fun `Apple package staging rejects unsupported compression before codec loading`() = fixture().use { fixture ->
        fixture.unsupportedFrameworkCompression()
        fixture.prepareFullClosure()
        val failure = assertFailsWith<IllegalStateException> { fixture.stage() }
        assertTrue("archive entry is unsafe or duplicated" in failure.message.orEmpty())
    }

    @Test
    fun `caller expectation crosspairs and partial authority reject without changing inputs`() {
        listOf("compatibility", "proof", "partial").forEach { mutation -> fixture().use { fixture ->
            fixture.prepareFullClosure()
            fixture.stage()
            val before = fixture.originalDigests() + fixture.transportedDigests()
            if (mutation == "partial") fixture.seedVerificationWork()
            assertFailsWith<IllegalStateException>(mutation) {
                when (mutation) {
                    "compatibility" -> fixture.verifyTransportedWithCallerExpectations(
                        compatibility = fixture.differentExpectedCompatibility(),
                    )
                    "proof" -> fixture.verifyTransportedWithCallerExpectations(
                        proof = fixture.differentExpectedProof(),
                    )
                    else -> fixture.verifyTransportedWithCallerExpectations(proof = null)
                }
            }
            assertEquals(before, fixture.originalDigests() + fixture.transportedDigests(), mutation)
            if (mutation == "partial") assertTrue(fixture.verificationWorkSentinel().isFile)
        } }
    }

    @Test
    fun `transported verifier rejects input work aliases without deletion`() = fixture().use { fixture ->
        fixture.prepareFullClosure()
        fixture.stage()
        val before = fixture.transportedDigests()
        assertFailsWith<IllegalStateException> { fixture.verifyWithProductAsWork() }
        assertEquals(before, fixture.transportedDigests())
    }

    @Test
    fun `transported verifier rejects product proof receipt native and semantic crosspairs`() {
        listOf(
            "product", "proof", "original-receipt", "current-receipt", "native", "semantic",
            "extra", "duplicate-product", "version",
        ).forEach {
            mutation -> fixture().use { fixture ->
                fixture.prepareFullClosure()
                fixture.stage()
                fixture.mutateTransported(mutation)
                val before = fixture.transportedDigests()
                assertFailsWith<IllegalStateException>(mutation) {
                    fixture.verifyTransported(if (mutation == "version") "0.2.1" else "0.2.0")
                }
                assertEquals(before, fixture.transportedDigests(), mutation)
            }
        }
    }

    @Test
    fun `artifact stage rejects crosspaired compatibility and stale checksum before publication`() {
        listOf("framework", "compatibility", "checksum", "missing").forEach { mutation ->
            fixture().use { fixture ->
                fixture.output.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
                fixture.validationOutput.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
                when (mutation) {
                    "framework" -> fixture.rewritePackage("different-device-binary")
                    "compatibility" -> fixture.rewritePackage(compatibility = "different")
                    "checksum" -> fixture.rewriteChecksum("0".repeat(64) + "\n")
                    else -> fixture.removePackageArchive()
                }
                if (mutation != "missing") fixture.rebindProof()
                assertFailsWith<IllegalStateException>(mutation) { fixture.stage() }
                assertEquals("preserved", fixture.output.resolve("sentinel").readText())
                assertEquals("preserved", fixture.validationOutput.resolve("sentinel").readText())
            }
        }
    }

    @Test
    fun `artifact stage rejects unsafe output aliases without deleting an input`() = fixture().use { fixture ->
        val before = fixture.originalDigests()
        assertFailsWith<IllegalStateException> {
            fixture.stageWithEvidenceOutput()
        }
        assertEquals(before, fixture.originalDigests())
    }

    @Test
    fun `external validation handoff cannot overlap product or source inputs`() = fixture().use { fixture ->
        val before = fixture.originalDigests()
        listOf(fixture.output, fixture.evidence).forEach { unsafe ->
            assertFailsWith<IllegalStateException> { fixture.stage(validation = unsafe) }
            assertEquals(before, fixture.originalDigests())
        }
    }

    @Test
    fun `missing native closure preserves both prior outputs`() {
        listOf("evidence", "receipt").forEach { missing -> fixture().use { fixture ->
            fixture.output.apply { mkdirs() }.resolve("sentinel").writeText("product")
            fixture.validationOutput.apply { mkdirs() }.resolve("sentinel").writeText("validation")
            if (missing == "evidence") fixture.removeNativeEvidence() else fixture.removeNativeReceipt()
            assertFailsWith<IllegalStateException>(missing) { fixture.stage() }
            assertEquals("product", fixture.output.resolve("sentinel").readText())
            assertEquals("validation", fixture.validationOutput.resolve("sentinel").readText())
        } }
    }

    @Test
    fun `artifact stage rejects unowned output symbolic parents and swapped compatibility without deletion`() {
        listOf(
            "unowned", "symlink-output", "symlink-dotdot-output",
            "symlink-input", "symlink-dotdot-input", "swapped",
        ).forEach { mutation -> fixture().use { fixture ->
            val destination = when (mutation) {
                "unowned" -> fixture.unownedOutput
                "symlink-output" -> fixture.symbolicOutput()
                "symlink-dotdot-output" -> fixture.symbolicDotDotOutput()
                else -> fixture.output
            }
            destination.parentFile.mkdirs()
            destination.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
            assertFailsWith<IllegalStateException>(mutation) {
                when (mutation) {
                    "swapped" -> fixture.stage(compatibility = fixture.receipt)
                    "symlink-input" -> fixture.stage(compatibility = fixture.symbolicCompatibility())
                    "symlink-dotdot-input" -> fixture.stage(compatibility = fixture.symbolicDotDotCompatibility())
                    else -> fixture.stage(output = destination)
                }
            }
            assertEquals("preserved", destination.resolve("sentinel").readText())
            assertTrue(fixture.receipt.isFile)
        } }
    }

    @Test
    fun `registration requires full imported verification and does not build a framework`() {
        val source = File("src/main/kotlin/IosVerifiedDistributionRegistration.kt").readText()
        val registration = source.substringAfter(
            "tasks.register<StageImportedAppleSdkPackageArtifactsTask>",
        ).substringBefore("tasks.named<StageCodexAgentAppleDistributionTask>")
        assertTrue("dependsOn(validate)" in registration)
        assertTrue("verificationReceipt.set(validate.flatMap" in registration)
        assertTrue("sdkCompatibility.set(it)" in registration)
        assertTrue("nativeEvidenceDirectory.set(nativeEvidence)" in registration)
        assertTrue("nativeEvidenceReceipt.set(nativeReceipt)" in registration)
        assertTrue("validationEvidenceDirectory.set" in registration)
        val transported = registration.substringAfter(
            "tasks.register<VerifyTransportedAppleSdkPackageClosureTask>",
        )
        assertTrue("\"verifyTransportedCodexAgentIosSdkPackageClosure\"" in transported)
        assertTrue("dependsOn(sdkPackageArtifacts)" in transported)
        assertTrue("productDirectory.set(sdkPackageArtifacts.flatMap { it.outputDirectory })" in transported)
        assertTrue(
            "validationEvidenceDirectory.set(sdkPackageArtifacts.flatMap { it.validationEvidenceDirectory })" in transported,
        )
        assertTrue("version.set(project.version.toString())" in transported)
        assertTrue("ownedBuildDirectory.set(sdkPackageArtifactRoot)" in transported)
        assertTrue("transported-verification-work" in transported)
        assertFalse("prepareCodexAgentReleaseXCFramework" in registration)
        assertFalse("assembleCodexAgentReleaseXCFramework" in registration)
        assertFalse("compileKotlin" in registration)
        assertFalse("packageCodexAgent" in transported)
    }
}

private class AppleSdkPackageFixture : AutoCloseable {
    private val root = createTempDirectory("apple-sdk-package-stage").toFile().canonicalFile
    private val owned = root.resolve("owned").apply { mkdirs() }
    val evidence = root.resolve("evidence").apply { mkdirs() }
    val receipt = root.resolve("receipt.json")
    private val nativeEvidence = root.resolve("native-evidence").apply { mkdirs() }
    private val nativeReceipt = root.resolve("current-native-evidence-receipt.json").apply {
        writeText("current native receipt")
    }
    private val compatibility = root.resolve("sdk-compatibility.json").apply {
        writeText("{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n")
    }
    private val work = owned.resolve("work")
    private val verifyWork = owned.resolve("verify-work")
    val output = owned.resolve("output")
    val validationOutput = owned.resolve("validation-evidence")
    val unownedOutput = root.resolve("unowned/output")
    private val packageArchive = evidence.resolve("CodexAgentPackage-0.2.0.zip")
    private val frameworkArchive = evidence.resolve("CodexAgent-0.2.0.xcframework.zip")
    private val checksum = evidence.resolve("CodexAgent-0.2.0.xcframework.zip.sha256")
    private val frameworkMembers = buildMap {
        put("CodexAgent.xcframework/Info.plist", "plist")
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            val framework = "CodexAgent.xcframework/$slice/CodexAgent.framework"
            put("$framework/CodexAgent", "binary:$slice")
            put("$framework/Headers/CodexAgent.h", "header")
            put("$framework/Modules/module.modulemap", "module")
            put("$framework/Info.plist", "framework plist")
            put("$framework/PrivacyInfo.xcprivacy", "privacy")
            put("$framework/META-INF/codex-agent/sdk-compatibility.json", compatibility.readText())
        }
    }

    init {
        evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).apply {
            parentFile.mkdirs()
            writeText("original native receipt")
        }
        nativeEvidence.resolve(IOS_NATIVE_TESTS_PROOF).writeText("native test evidence")
        writeZip(frameworkArchive, frameworkMembers)
        rewritePackage()
        checksum.writeText("${frameworkArchive.releaseDigest()}\n")
        rebindProof()
    }

    fun stage(
        output: File = this.output,
        compatibility: File = this.compatibility,
        validation: File = validationOutput,
    ) =
        stageImportedAppleSdkPackageArtifacts(
            evidence, receipt, compatibility, nativeEvidence, nativeReceipt,
            "0.2.0", owned, work, output, validation,
        )

    fun stageWithEvidenceOutput() = stageImportedAppleSdkPackageArtifacts(
        evidence, receipt, compatibility, nativeEvidence, nativeReceipt,
        "0.2.0", root, work, evidence, validationOutput,
    )

    fun verifyTransported(version: String = "0.2.0") = verifyTransportedAppleSdkPackageClosure(
        output, validationOutput, version, owned, verifyWork,
    )

    fun verifyTransportedWithCallerExpectations(
        compatibility: File? = this.compatibility,
        proof: File? = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF),
    ) = verifyTransportedAppleSdkPackageClosure(
        output, validationOutput, "0.2.0", owned, verifyWork, compatibility, proof,
    )

    fun verifyUsingPackagedTool() {
        val java = File(System.getProperty("java.home"), "bin/${if (System.getProperty("os.name").startsWith("Windows")) "java.exe" else "java"}")
        val jar = checkNotNull(System.getProperty("codexAgent.releaseToolingJar"))
        val process = ProcessBuilder(
            java.path, "-jar", jar, "verify-transported-apple-sdk-package-closure",
            "--product-directory", output.path,
            "--validation-evidence-directory", validationOutput.path,
            "--version", "0.2.0",
            "--owned-build-directory", owned.path,
            "--work-directory", verifyWork.path,
            "--expected-sdk-compatibility", compatibility.path,
            "--expected-distribution-proof", evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).path,
        ).directory(root).redirectErrorStream(true).start()
        val log = process.inputStream.bufferedReader().use { it.readText() }
        val exit = process.waitFor()
        assertEquals(0, exit, log)
    }

    fun unsupportedFrameworkCompression() {
        val bytes = frameworkArchive.readBytes()
        val central = (0..bytes.size - 12).first { index ->
            bytes[index] == 0x50.toByte() && bytes[index + 1] == 0x4b.toByte() &&
                bytes[index + 2] == 0x01.toByte() && bytes[index + 3] == 0x02.toByte()
        }
        bytes[central + 10] = 12 // BZIP2: not an accepted Apple package method.
        bytes[central + 11] = 0
        frameworkArchive.writeBytes(bytes)
        checksum.writeText("${frameworkArchive.releaseDigest()}\n")
    }

    fun verifyWithProductAsWork() = verifyTransportedAppleSdkPackageClosure(
        output, validationOutput, "0.2.0", owned, output,
    )

    fun transportedDigests() = buildMap {
        verifiedRegularFiles(output).forEach { (path, file) -> put("product/$path", file.releaseDigest()) }
        verifiedRegularFiles(validationOutput).forEach { (path, file) -> put("validation/$path", file.releaseDigest()) }
    }

    fun seedVerificationWork() = verificationWorkSentinel().apply {
        parentFile.mkdirs()
        writeText("preserved")
    }

    fun verificationWorkSentinel() = verifyWork.resolve("sentinel")

    fun differentExpectedCompatibility() = root.resolve("different-sdk-compatibility.json").apply {
        writeText("{\"schemaVersion\":1,\"sdkVersion\":\"0.2.1\"}\n")
    }

    fun differentExpectedProof() = root.resolve("different-verified-distribution-proof.json").apply {
        val original = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).readReleaseObject()
        atomicWriteJson(JsonObject(original + ("candidateTree" to JsonPrimitive("9".repeat(40)))))
    }

    fun symbolicOutput(): File {
        val link = owned.resolve("linked")
        Files.createSymbolicLink(link.toPath(), root.resolve("unowned").apply { mkdirs() }.toPath())
        return link.resolve("output")
    }

    fun symbolicDotDotOutput(): File {
        val link = owned.resolve("linked-dotdot")
        Files.createSymbolicLink(link.toPath(), owned.resolve("child").apply { mkdirs() }.toPath())
        return link.resolve("../output")
    }

    fun symbolicCompatibility(): File {
        val link = root.resolve("linked-input")
        Files.createSymbolicLink(link.toPath(), root.toPath())
        return link.resolve("sdk-compatibility.json")
    }

    fun symbolicDotDotCompatibility(): File {
        val link = root.resolve("linked-input-dotdot")
        Files.createSymbolicLink(link.toPath(), root.resolve("input-child").apply { mkdirs() }.toPath())
        return link.resolve("../sdk-compatibility.json")
    }

    fun rewritePackage(deviceBinary: String = "binary:ios-arm64", compatibility: String = this.compatibility.readText()) {
        val packageFramework = frameworkMembers.toMutableMap().apply {
            this["CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent"] = deviceBinary
            keys.filter { it.endsWith("sdk-compatibility.json") }.forEach { remove(it) }
        }
        writeZip(packageArchive, packageFramework + mapOf(
            "Package.swift" to "// package",
            "Sources/CodexAgent.swift" to "public struct CodexAgent {}",
            "Tests/CodexAgentTests.swift" to "// test",
            "LICENSE.txt" to "license",
            "THIRD_PARTY_NOTICES.md" to "notices",
            "openai-codex-LICENSE.txt" to "codex license",
            "openai-codex-NOTICE.txt" to "codex notice",
            "META-INF/codex-agent/sdk-compatibility.json" to compatibility,
        ))
    }

    fun rewriteChecksum(contents: String) = checksum.writeText(contents)
    fun removePackageArchive() = packageArchive.delete().let { }
    fun removeNativeEvidence() = nativeEvidence.resolve(IOS_NATIVE_TESTS_PROOF).delete().let { }
    fun removeNativeReceipt() = nativeReceipt.delete().let { }

    fun prepareFullClosure() {
        appleVerifiedReportLayout.keys.forEach { path ->
            evidence.resolve(path).apply { parentFile.mkdirs(); writeText("report:$path") }
        }
        appleVerifiedToolchainLayout.keys.forEach { path ->
            evidence.resolve(path).apply { parentFile.mkdirs(); writeText("toolchain:$path") }
        }
        val nativeNames = appleRustSliceSpecs.flatMap { listOf(it.archiveName, it.proofName) } + IOS_NATIVE_TESTS_PROOF
        nativeNames.forEach { path -> nativeEvidence.resolve(path).writeText("native:$path") }
        evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).writeText(
            nativeReceiptJson("1".repeat(40), "2".repeat(40)),
        )
        nativeReceipt.writeText(nativeReceiptJson("3".repeat(40), "4".repeat(40)))
        val files = verifiedRegularFiles(evidence)
        val identity = AppleVerifiedDistributionIdentity(
            "1".repeat(40), "2".repeat(40), "0.2.0",
            "6".repeat(64), "7".repeat(64),
            evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseDigest(),
            compatibility.releaseDigest(),
        )
        evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).atomicWriteJson(
            buildAppleVerifiedDistributionProof(
                identity,
                files.filterKeys { it in artifactNames },
                files.filterKeys { it in appleVerifiedReportLayout },
                files.filterKeys { it in appleVerifiedToolchainLayout },
                verifiedRegularFiles(nativeEvidence),
                mapOf(
                    IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT to
                        evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT),
                ),
            ),
        )
        writeImportReceipt()
    }

    fun mutateTransported(mutation: String) {
        val distribution = validationOutput.resolve("verified-distribution")
        val currentReceipt = validationOutput.resolve("receipts/current-ios-native-evidence.json")
        when (mutation) {
            "product" -> output.resolve(packageArchive.name).appendText("changed")
            "proof" -> distribution.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).let { proof ->
                val value = proof.readReleaseObject()
                proof.atomicWriteJson(JsonObject(value + ("version" to JsonPrimitive("0.2.1"))))
            }
            "original-receipt" -> distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).appendText("changed")
            "current-receipt" -> currentReceipt.appendText("changed")
            "native" -> validationOutput.resolve("current-native-evidence/$IOS_NATIVE_TESTS_PROOF").appendText("changed")
            "semantic" -> {
                currentReceipt.writeText(nativeReceiptJson(
                    "3".repeat(40), "4".repeat(40), nativeInputs = "9".repeat(64),
                ))
                val imported = validationOutput.resolve("receipts/verified-distribution-import.json")
                val value = imported.readReleaseObject()
                imported.atomicWriteJson(JsonObject(value + (
                    "currentNativeEvidenceReceiptSha256" to JsonPrimitive(currentReceipt.releaseDigest())
                )))
            }
            "extra" -> validationOutput.resolve("extra").writeText("unexpected")
            "duplicate-product" -> {
                val valid = output.resolve(packageArchive.name).readBytes()
                validationOutput.resolve("verified-distribution/${packageArchive.name}").writeBytes(valid)
                output.resolve(packageArchive.name).appendText("changed")
            }
        }
    }

    fun rebindProof() {
        val proof = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
        proof.atomicWriteJson(buildJsonObject {
            put("candidateCommit", JsonPrimitive("1".repeat(40)))
            put("candidateTree", JsonPrimitive("2".repeat(40)))
            put("nativeEvidenceReceiptSha256", JsonPrimitive(
                evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseDigest(),
            ))
            put("artifacts", buildJsonArray {
                listOf(packageArchive, frameworkArchive, checksum).forEach { file -> add(buildJsonObject {
                    put("fileName", JsonPrimitive(file.name))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                }) }
            })
            put("reports", buildJsonArray { })
            put("toolchain", buildJsonArray { })
            put("receipts", buildJsonArray {
                add(evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseRecord(
                    IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT,
                ))
            })
            put("nativeEvidence", buildJsonArray {
                verifiedRegularFiles(nativeEvidence).forEach { (path, file) -> add(file.releaseRecord(path)) }
            })
        })
        writeImportReceipt()
    }

    private fun writeImportReceipt() {
        val proof = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
        receipt.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(2))
            put("protocol", JsonPrimitive("codex-agent-ios-verified-distribution-import-v2"))
            put("result", JsonPrimitive("passed"))
            put("producerCommit", JsonPrimitive("1".repeat(40)))
            put("producerTree", JsonPrimitive("2".repeat(40)))
            put("consumerCommit", JsonPrimitive("3".repeat(40)))
            put("consumerTree", JsonPrimitive("4".repeat(40)))
            put("sourceProofSha256", JsonPrimitive(proof.releaseDigest()))
            put("originalNativeEvidenceReceiptSha256", JsonPrimitive(
                evidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseDigest(),
            ))
            put("currentNativeEvidenceReceiptSha256", JsonPrimitive(nativeReceipt.releaseDigest()))
        })
    }

    private fun nativeReceiptJson(commit: String, tree: String, nativeInputs: String = "5".repeat(64)) =
        buildJsonObject {
            put("schemaVersion", JsonPrimitive(2))
            put("protocol", JsonPrimitive("codex-agent-ios-native-evidence-v2"))
            put("result", JsonPrimitive("passed"))
            put("candidateCommit", JsonPrimitive(commit))
            put("candidateTree", JsonPrimitive(tree))
            put("cleanCheckout", JsonPrimitive(true))
            put("nativeInputsSha256", JsonPrimitive(nativeInputs))
            put("nativeProvenanceSha256", JsonPrimitive("6".repeat(64)))
            put("compilerSettingsSha256", JsonPrimitive("7".repeat(64)))
            put("rustToolchain", JsonPrimitive("1.95.0"))
            put("rustSrcComponent", JsonPrimitive("required"))
            put("rustCompilerIdentitySha256", JsonPrimitive("8".repeat(64)))
            put("xcodeVersionSha256", JsonPrimitive("9".repeat(64)))
            put("swiftVersionSha256", JsonPrimitive("a".repeat(64)))
            put("nativeTestsProofSha256", JsonPrimitive("b".repeat(64)))
            put("slices", buildJsonArray { })
        }.toString()

    private val artifactNames get() = setOf(packageArchive.name, frameworkArchive.name, checksum.name)

    fun originalDigests() = buildMap {
        verifiedRegularFiles(evidence).forEach { (path, file) ->
            put("distribution/$path", file.releaseDigest())
        }
        verifiedRegularFiles(nativeEvidence).forEach { (path, file) ->
            put("native/$path", file.releaseDigest())
        }
        put("import-receipt", receipt.releaseDigest())
        put("current-native-receipt", nativeReceipt.releaseDigest())
        put("sdk-compatibility", compatibility.releaseDigest())
    }

    fun productDigests() = artifactNames.associateWith { evidence.resolve(it).releaseDigest() }

    fun expectedValidationDigests() = buildMap {
        verifiedRegularFiles(evidence).filterKeys { it !in artifactNames }.forEach { (path, file) ->
            put("verified-distribution/$path", file.releaseDigest())
        }
        verifiedRegularFiles(nativeEvidence).forEach { (path, file) ->
            put("current-native-evidence/$path", file.releaseDigest())
        }
        put("receipts/verified-distribution-import.json", receipt.releaseDigest())
        put("receipts/current-ios-native-evidence.json", nativeReceipt.releaseDigest())
    }

    fun outputDigests() = verifiedRegularFiles(output).mapValues { it.value.releaseDigest() }
    fun validationDigests() = verifiedRegularFiles(validationOutput).mapValues { it.value.releaseDigest() }

    private fun writeZip(file: File, members: Map<String, String>) {
        ZipOutputStream(file.outputStream()).use { archive -> members.forEach { (path, contents) ->
            archive.putNextEntry(ZipEntry(path))
            archive.write(contents.toByteArray())
            archive.closeEntry()
        } }
    }

    override fun close() = root.deleteRecursively().let { }
}

private fun fixture() = AppleSdkPackageFixture()
