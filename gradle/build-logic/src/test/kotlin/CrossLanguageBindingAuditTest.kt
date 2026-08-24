import kotlin.io.path.createTempFile
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class CrossLanguageBindingAuditTest {
    @Test
    fun `materializes Kotlin proof and every active missing and future pending pair`() {
        val audit = buildCrossLanguageBindingAudit(evidence(FULL_MEMBER_SET))

        assertEquals("incomplete", audit.result)
        assertEquals(6_039, audit.summary.total)
        assertEquals(2_745, audit.summary.active)
        assertEquals(3_294, audit.summary.pending)
        assertEquals(549, audit.summary.satisfied)
        assertEquals(2_196, audit.summary.missing)
        assertTrue(audit.obligations.filter { it.language == CrossLanguageBinding.KOTLIN }.all {
            it.parityStatus == CrossLanguageObligationStatus.SATISFIED
        })
        assertTrue(audit.obligations.filter { it.language == CrossLanguageBinding.C_ABI }.all {
            it.parityStatus == CrossLanguageObligationStatus.PENDING
        })
        assertTrue(audit.errors.any { "Missing active binding projection java:" in it })
        assertTrue(audit.errors.none { "Missing active binding projection kotlin:" in it })
    }

    @Test
    fun `strict audit reader binds live inputs and rejects incomplete or stale records`() {
        val audit = buildCrossLanguageBindingAudit(evidence())
        val path = createTempFile("binding-audit", ".json").toFile()
        try {
            path.writeText(audit.toJson().toString())
            assertEquals(
                audit,
                readCrossLanguageBindingAudit(path, evidence()),
            )

            val root = audit.toJson()
            val obligations = root.releaseArray("obligations")
            val forgedStatus = obligations.mapIndexed { index, value ->
                if (index != 2) {
                    value
                } else {
                    JsonObject((value as JsonObject) + ("parityStatus" to JsonPrimitive("satisfied")))
                }
            }
            val forgedStatusSummary = JsonObject(root.releaseObject("summary") + mapOf(
                "satisfied" to JsonPrimitive(audit.summary.satisfied + 1),
                "missing" to JsonPrimitive(audit.summary.missing - 1),
            ))
            val corruptions = listOf(
                JsonObject(root + ("apiReportSha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("obligations" to JsonArray(obligations.drop(1)))),
                JsonObject(root + ("summary" to JsonObject(root.releaseObject("summary") +
                    ("total" to JsonPrimitive(0))))),
                JsonObject(root + ("errors" to JsonArray(emptyList()))),
                JsonObject(root + ("obligations" to JsonArray(obligations.reversed()))),
                JsonObject(root + mapOf(
                    "obligations" to JsonArray(forgedStatus),
                    "summary" to forgedStatusSummary,
                )),
                JsonObject(root + ("errors" to JsonArray(listOf(JsonPrimitive("forged error"))))),
            )
            corruptions.forEach { corruption ->
                path.writeText(corruption.toString())
                assertFailsWith<IllegalStateException> {
                    readCrossLanguageBindingAudit(path, evidence())
                }
            }
        } finally {
            path.delete()
        }
    }

    @Test
    fun `Kotlin pass receipt rejects stale inputs and incomplete scenarios`() {
        val path = createTempFile("kotlin-binding-parity", ".json").toFile()
        try {
            val expectedScenarios = CrossLanguageBindingScenario.entries.map { scenario ->
                CrossLanguageScenarioEvidence(
                    CrossLanguageBinding.KOTLIN,
                    scenario,
                    listOf("sample.Test#${scenario.id}"),
                )
            }
            fun write(
                auditDigest: String = "f".repeat(64),
                includeAllScenarios: Boolean = true,
                forgedTestId: Boolean = false,
            ) {
                path.writeText(buildJsonObject {
                    put("schema", JsonPrimitive(1))
                    put("result", JsonPrimitive("passed"))
                    put("language", JsonPrimitive("kotlin"))
                    put("phase", JsonPrimitive("M7_5"))
                    put("apiReportSha256", JsonPrimitive(API_DIGEST))
                    put("canonicalCoverageSha256", JsonPrimitive(COVERAGE_DIGEST))
                    put("bindingAuditSha256", JsonPrimitive(auditDigest))
                    put("publicArtifactSha256", JsonPrimitive(ARTIFACT_DIGEST))
                    put("compiledTestsSha256", JsonPrimitive("d".repeat(64)))
                    put("testResultsSha256", JsonPrimitive("e".repeat(64)))
                    put("capabilityCount", JsonPrimitive(MEMBERS.size))
                    put("scenarios", buildJsonArray {
                        val scenarios = if (includeAllScenarios) {
                            CrossLanguageBindingScenario.entries
                        } else {
                            CrossLanguageBindingScenario.entries.dropLast(1)
                        }
                        scenarios.forEachIndexed { index, scenario ->
                            add(buildJsonObject {
                                put("id", JsonPrimitive(scenario.id))
                                put("testIds", buildJsonArray {
                                    val testId = if (forgedTestId && index == 0) {
                                        "sample.Test#forged"
                                    } else {
                                        "sample.Test#${scenario.id}"
                                    }
                                    add(JsonPrimitive(testId))
                                })
                            })
                        }
                    })
                }.toString())
            }
            fun verify() = verifyKotlinBindingParityReceipt(
                path,
                API_DIGEST,
                COVERAGE_DIGEST,
                "f".repeat(64),
                ARTIFACT_DIGEST,
                "d".repeat(64),
                "e".repeat(64),
                MEMBERS.size,
                expectedScenarios,
            )

            write()
            verify()
            write(auditDigest = "0".repeat(64))
            assertFailsWith<IllegalStateException> { verify() }
            write(includeAllScenarios = false)
            assertFailsWith<IllegalStateException> { verify() }
            write(forgedTestId = true)
            assertFailsWith<IllegalStateException> { verify() }
        } finally {
            path.delete()
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
            capabilityClaims = members.map { member ->
                KotlinBindingCapabilityClaim(member, member)
            },
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

    private companion object {
        val API_DIGEST = "a".repeat(64)
        val COVERAGE_DIGEST = "b".repeat(64)
        val ARTIFACT_DIGEST = "c".repeat(64)
        val MEMBERS = listOf(
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.first",
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.second",
        )
        val FULL_MEMBER_SET = (0 until 549).map { index ->
            "common|owner=sample/Owner$index|kind=property|abi=sample/Owner$index.value"
        }
    }
}
