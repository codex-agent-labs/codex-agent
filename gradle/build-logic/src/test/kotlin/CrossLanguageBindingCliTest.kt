import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class CrossLanguageBindingCliTest {
    @Test
    fun `complete file gate writes the strict all-language audit`() = withFixture { fixture ->
        val audit = fixture.writeCompleteAudit()

        assertEquals("complete", audit.result)
        assertEquals(22, audit.summary.total)
        assertEquals(10, audit.summary.active)
        assertEquals(12, audit.summary.pending)
        assertEquals(10, audit.summary.satisfied)
        assertTrue(audit.errors.isEmpty())
        assertTrue(fixture.output.isFile)
    }

    @Test
    fun `file gate deletes stale output and rejects missing swapped noncanonical digest and phase evidence`() {
        listOf<(CrossLanguageBindingCliFixture) -> Unit>(
            { it.receipt(CrossLanguageBinding.SWIFT).delete() },
            { it.swapReceipts(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA) },
            { it.makeReceiptNoncanonical(CrossLanguageBinding.OBJECTIVE_C) },
            { it.rewriteCoverage(testResultsSha256 = "9".repeat(64)) },
            { it.writeReceipt(CrossLanguageBinding.JAVA, phase = CrossLanguageBindingPhase.M8) },
            { it.rewriteCoverage(apiReportSha256 = "0".repeat(64)) },
            { it.receiptDirectory.resolve("decoy.json").writeText("{}\n") },
        ).forEach { corrupt ->
            withFixture { fixture ->
                corrupt(fixture)
                fixture.output.apply {
                    parentFile.mkdirs()
                    writeText("stale passed audit")
                }

                assertFailsWith<IllegalStateException> { fixture.writeCompleteAudit() }
                assertFalse(fixture.output.exists())
            }
        }
    }

    @Test
    fun `file gate emits only an incomplete diagnostic when a valid active receipt omits capability parity`() =
        withFixture { fixture ->
            fixture.writeReceipt(
                CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
                claimedMembers = fixture.members.dropLast(1),
            )
            fixture.output.writeText("stale passed audit")

            val failure = assertFailsWith<IllegalStateException> { fixture.writeCompleteAudit() }

            assertTrue("Missing active binding projection javascript-typescript:" in failure.message.orEmpty())
            assertEquals("incomplete", fixture.output.readReleaseObject().releaseString("result"))
            assertFalse("stale passed audit" in fixture.output.readText())
        }

    @Test
    fun `later phases require the newly active language and advance every carried receipt`() = withFixture { fixture ->
        assertFailsWith<IllegalStateException> { fixture.writeCompleteAudit(CrossLanguageBindingPhase.M8) }

        CrossLanguageBinding.entries.filter { it.isActive(CrossLanguageBindingPhase.M8) }.forEach { language ->
            fixture.writeReceipt(language, phase = CrossLanguageBindingPhase.M8)
        }
        val audit = fixture.writeCompleteAudit(CrossLanguageBindingPhase.M8)

        assertEquals(12, audit.summary.active)
        assertEquals(10, audit.summary.pending)
        assertEquals(12, audit.summary.satisfied)
        assertTrue(audit.errors.isEmpty())
    }

    private fun withFixture(block: (CrossLanguageBindingCliFixture) -> Unit) {
        val root = createTempDirectory("binding-cli").toFile()
        try {
            block(CrossLanguageBindingCliFixture(root))
        } finally {
            root.deleteRecursively()
        }
    }
}

internal class CrossLanguageBindingCliFixture(val root: File) {
    val apiReport: File = root.resolve("canonical-api.json")
    val coverageReceipt: File = root.resolve("canonical-coverage.json")
    val receiptDirectory: File = root.resolve("receipts")
    val output: File = root.resolve("binding-obligations-m7_5.json")
    val members = listOf(
        "common|owner=sample/Owner|kind=function|abi=sample/Owner.first",
        "common|owner=sample/Owner|kind=property|abi=sample/Owner.second",
    )

    init {
        writeApiReport()
        rewriteCoverage()
        CrossLanguageBinding.entries.filter { it.isActive(CrossLanguageBindingPhase.M7_5) }
            .forEach { language -> writeReceipt(language) }
    }

    fun receipt(language: CrossLanguageBinding): File =
        receiptDirectory.resolve("${language.id}-parity.json")

    fun writeReceipt(
        language: CrossLanguageBinding,
        phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        claimedMembers: List<String> = members,
    ) {
        val testId = "sample.${language.name}BindingTest#projection"
        val symbols = if (language == CrossLanguageBinding.KOTLIN) members else members.mapIndexed { index, _ ->
            "method:sample/${language.name}Owner#$index()V"
        }
        writeCrossLanguageBindingReceipt(
            receipt(language),
            CrossLanguageBindingReceipt(
                phase = phase,
                language = language,
                canonical = CrossLanguageBindingCanonicalIdentity(
                    apiReport.releaseDigest(),
                    coverageReceipt.releaseDigest(),
                ),
                artifacts = listOf(
                    CrossLanguageBindingArtifactIdentity("${language.id}-artifact", "1".repeat(64)),
                ),
                testProgramSha256 = "2".repeat(64),
                testResultsSha256 = "3".repeat(64),
                publicSymbols = symbols,
                bindingTests = listOf(
                    CrossLanguageBindingTestEvidence(language, testId, CrossLanguageBindingTestStatus.PASSED),
                ),
                scenarioEvidence = CrossLanguageBindingScenario.entries.map { scenario ->
                    CrossLanguageScenarioEvidence(language, scenario, listOf(testId))
                },
                projectionClaims = if (language == CrossLanguageBinding.KOTLIN) emptyList() else
                    claimedMembers.map { member ->
                        val index = members.indexOf(member).also { check(it >= 0) }
                        CrossLanguageProjectionClaim(
                            capabilityKey = member,
                            language = language,
                            publicSymbols = listOf(symbols[index]),
                            executedTests = listOf(testId),
                            sharedScenarios = CrossLanguageBindingScenario.entries,
                        )
                    },
                applicabilityExclusions = emptyList(),
            ),
        )
    }

    fun swapReceipts(first: CrossLanguageBinding, second: CrossLanguageBinding) {
        val firstFile = receipt(first)
        val secondFile = receipt(second)
        val firstBytes = firstFile.readBytes()
        firstFile.writeBytes(secondFile.readBytes())
        secondFile.writeBytes(firstBytes)
    }

    fun makeReceiptNoncanonical(language: CrossLanguageBinding) {
        val file = receipt(language)
        file.writeText(readCrossLanguageBindingReceipt(file).toJson().toString())
    }

    fun rewriteCoverage(
        apiReportSha256: String = apiReport.releaseDigest(),
        testResultsSha256: String = "5".repeat(64),
    ) {
        coverageReceipt.atomicWriteJson(canonicalCoverage(apiReportSha256, testResultsSha256))
    }

    fun writeCompleteAudit(
        phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
    ): CrossLanguageBindingAudit = writeCompleteCrossLanguageBindingAudit(
        phase = phase,
        apiReport = apiReport,
        canonicalCoverageReceipt = coverageReceipt,
        receiptDirectory = receiptDirectory,
        auditFile = output,
    )

    fun cliArguments(): Array<String> = arrayOf(
        "audit-cross-language-bindings",
        "--phase", CrossLanguageBindingPhase.M7_5.name,
        "--api-report", apiReport.absolutePath,
        "--coverage-receipt", coverageReceipt.absolutePath,
        "--receipts", receiptDirectory.absolutePath,
        "--output", output.absolutePath,
    )

    private fun writeApiReport() {
        apiReport.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2))
            put("libraryUniqueName", JsonPrimitive("codex-agent-core"))
            put("markerAnnotation", JsonPrimitive("sample.CodexBindingApi"))
            put("signatureVersion", JsonPrimitive(2))
            put("boundaryTypes", JsonArray(emptyList()))
            put("memberExclusionAnnotation", JsonPrimitive("sample.CodexBindingApiKotlinOnly"))
            put("excludedReachableTypes", JsonArray(emptyList()))
            put("excludedMemberKeys", JsonArray(emptyList()))
            put("dataClassMetadataAvailable", JsonPrimitive(true))
            put("dataClassNames", JsonArray(emptyList()))
            put("owners", buildJsonArray {
                add(buildJsonObject {
                    put("name", JsonPrimitive("sample/Owner"))
                    put("capabilities", members.toJsonArray())
                })
            })
            put("targets", buildJsonArray {
                listOf("native", "wasm", "jvm-classes").forEachIndexed { index, kind ->
                    add(buildJsonObject {
                        put("kind", JsonPrimitive(kind))
                        put("sha256", JsonPrimitive((index + 6).toString().repeat(64)))
                    })
                }
            })
        })
    }

    private fun canonicalCoverage(apiReportSha256: String, testResultsSha256: String) = buildJsonObject {
        put("schema", JsonPrimitive(2))
        put("result", JsonPrimitive("passed"))
        put("kotlinCompilerVersion", JsonPrimitive("2.3.10"))
        put("canonicalTestTask", JsonPrimitive(":codex-agent-core:jvmTest"))
        put("apiReportSha256", JsonPrimitive(apiReportSha256))
        put("compiledTestsSha256", JsonPrimitive("4".repeat(64)))
        put("testResultsSha256", JsonPrimitive(testResultsSha256))
        put("capabilities", members.toJsonArray())
        put("claims", buildJsonArray {
            add(buildJsonObject {
                put("testId", JsonPrimitive("sample.CanonicalTest#behavior"))
                put("capabilities", members.toJsonArray())
            })
        })
    }

    private fun List<String>.toJsonArray(): JsonArray = JsonArray(map(::JsonPrimitive))
}
