import kotlin.io.path.createTempFile
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

class CrossLanguageBindingAuditTest {
    @Test
    fun `materializes Kotlin and Java proof with every remaining active and future pair`() {
        val audit = buildCrossLanguageBindingAudit(
            evidence(FULL_MEMBER_SET),
            javaEvidence(FULL_MEMBER_SET),
            RECEIPTS,
        )

        assertEquals("incomplete", audit.result)
        assertEquals(6_039, audit.summary.total)
        assertEquals(2_745, audit.summary.active)
        assertEquals(3_294, audit.summary.pending)
        assertEquals(1_098, audit.summary.satisfied)
        assertEquals(1_647, audit.summary.missing)
        assertEquals(RECEIPTS, audit.languageReceiptSha256)
        for (language in listOf(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA)) {
            assertTrue(audit.obligations.filter { it.language == language }.all {
                it.parityStatus == CrossLanguageObligationStatus.SATISFIED
            })
            assertTrue(audit.errors.none { "Missing active binding projection ${language.id}:" in it })
        }
        assertTrue(audit.obligations.filter { it.language == CrossLanguageBinding.C_ABI }.all {
            it.parityStatus == CrossLanguageObligationStatus.PENDING
        })
        assertTrue(audit.errors.any { "Missing active binding projection swift:" in it })
    }

    @Test
    fun `strict audit reader binds both receipts and rejects any stale record`() {
        val kotlin = evidence()
        val java = javaEvidence()
        val audit = buildCrossLanguageBindingAudit(kotlin, java, RECEIPTS)
        val path = createTempFile("binding-audit", ".json").toFile()
        try {
            path.writeText(audit.toJson().toString())
            assertEquals(audit, readCrossLanguageBindingAudit(path, kotlin, java, RECEIPTS))

            val root = audit.toJson()
            val obligations = root.releaseArray("obligations")
            val receipts = root.releaseObject("languageReceiptSha256")
            val corruptions = listOf(
                JsonObject(root + ("apiReportSha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("obligations" to JsonArray(obligations.drop(1)))),
                JsonObject(root + ("summary" to JsonObject(root.releaseObject("summary") +
                    ("total" to JsonPrimitive(0))))),
                JsonObject(root + ("errors" to JsonArray(emptyList()))),
                JsonObject(root + ("obligations" to JsonArray(obligations.reversed()))),
                JsonObject(root + ("languageReceiptSha256" to JsonObject(
                    receipts + ("java" to JsonPrimitive("0".repeat(64))),
                ))),
                JsonObject(root + ("languageReceiptSha256" to JsonObject(receipts - "java"))),
            )
            corruptions.forEach { corruption ->
                path.writeText(corruption.toString())
                assertFailsWith<IllegalStateException> {
                    readCrossLanguageBindingAudit(path, kotlin, java, RECEIPTS)
                }
            }
        } finally {
            path.delete()
        }
    }

    @Test
    fun `Kotlin pass receipt is independent and exact`() {
        val expected = buildKotlinBindingParityReceipt(evidence())
        verifyKotlinBindingParityReceipt(expected, expected)

        assertEquals(2, (expected.getValue("schema") as JsonPrimitive).content.toInt())
        assertFalse("bindingAuditSha256" in expected)
        listOf(
            JsonObject(expected + ("result" to JsonPrimitive("forged"))),
            JsonObject(expected + ("apiReportSha256" to JsonPrimitive("0".repeat(64)))),
            JsonObject(expected + ("scenarios" to JsonArray(expected.releaseArray("scenarios").dropLast(1)))),
        ).forEach { forged ->
            assertFailsWith<IllegalStateException> {
                verifyKotlinBindingParityReceipt(forged, expected)
            }
        }
    }

    private fun evidence(members: List<String> = MEMBERS): CrossLanguageKotlinBindingEvidence {
        val testIds = CrossLanguageBindingScenario.entries.associateWith { scenario ->
            "sample.BindingTest#${scenario.name.lowercase()}"
        }
        return CrossLanguageKotlinBindingEvidence(
            digests = KotlinBindingDigestEvidence(
                artifactSha256 = ARTIFACT_DIGEST,
                apiReportSha256 = API_DIGEST,
                canonicalCoverageSha256 = COVERAGE_DIGEST,
                compiledTestsSha256 = "d".repeat(64),
                testResultsSha256 = "e".repeat(64),
            ),
            capabilityClaims = members.map { member -> KotlinBindingCapabilityClaim(member, member) },
            bindingTests = testIds.values.map { testId ->
                CrossLanguageBindingTestEvidence(
                    CrossLanguageBinding.KOTLIN,
                    testId,
                    CrossLanguageBindingTestStatus.PASSED,
                )
            },
            scenarioEvidence = CrossLanguageBindingScenario.entries.map { scenario ->
                CrossLanguageScenarioEvidence(
                    CrossLanguageBinding.KOTLIN,
                    scenario,
                    listOf(testIds.getValue(scenario)),
                )
            },
        )
    }

    private fun javaEvidence(members: List<String> = MEMBERS): CrossLanguageJavaBindingParityEvidence {
        val testId = "sample.JavaBindingTest#projection"
        val symbols = members.mapIndexed { index, _ -> "method:sample/Owner#$index()V" }
        val tests = listOf(
            CrossLanguageBindingTestEvidence(
                CrossLanguageBinding.JAVA,
                testId,
                CrossLanguageBindingTestStatus.PASSED,
            ),
        )
        val scenarios = CrossLanguageBindingScenario.entries.map { scenario ->
            CrossLanguageScenarioEvidence(CrossLanguageBinding.JAVA, scenario, listOf(testId))
        }
        val claims = members.mapIndexed { index, member ->
            CrossLanguageProjectionClaim(
                capabilityKey = member,
                language = CrossLanguageBinding.JAVA,
                publicSymbols = listOf(symbols[index]),
                executedTests = listOf(testId),
                sharedScenarios = CrossLanguageBindingScenario.entries,
            )
        }
        val parity = evaluateCrossLanguageBindingParity(
            CrossLanguageBindingParityInput(
                phase = CrossLanguageBindingPhase.M7_5,
                capabilityKeys = members,
                canonicalCoverageKeys = members,
                projectionClaims = claims,
                publicSymbols = mapOf(CrossLanguageBinding.JAVA to symbols),
                bindingTests = tests,
                scenarioEvidence = scenarios,
            ),
        )
        return CrossLanguageJavaBindingParityEvidence(
            digests = JavaBindingParityDigests(
                JavaBindingArtifactDigests(
                    "1".repeat(64),
                    "2".repeat(64),
                    "3".repeat(64),
                    "4".repeat(64),
                ),
                "5".repeat(64),
                "6".repeat(64),
            ),
            projectionClaims = claims,
            publicSymbols = symbols,
            bindingTests = tests,
            scenarioEvidence = scenarios,
            parityReport = parity,
        )
    }

    private companion object {
        val API_DIGEST = "a".repeat(64)
        val COVERAGE_DIGEST = "b".repeat(64)
        val ARTIFACT_DIGEST = "c".repeat(64)
        val RECEIPTS = mapOf(
            CrossLanguageBinding.KOTLIN to "7".repeat(64),
            CrossLanguageBinding.JAVA to "8".repeat(64),
        )
        val MEMBERS = listOf(
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.first",
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.second",
        )
        val FULL_MEMBER_SET = (0 until 549).map { index ->
            "common|owner=sample/Owner$index|kind=property|abi=sample/Owner$index.value"
        }
    }
}
