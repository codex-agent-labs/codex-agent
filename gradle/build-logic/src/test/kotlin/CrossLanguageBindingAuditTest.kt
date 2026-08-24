import kotlin.io.path.createTempFile
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

class CrossLanguageBindingAuditTest {
    @Test
    fun `materializes Kotlin and Java proof with every remaining active and future pair`() {
        val receipts = receipts(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA, members = FULL_MEMBER_SET)
        val digests = receiptDigests(receipts)
        val audit = buildCrossLanguageBindingAudit(
            CrossLanguageBindingPhase.M7_5,
            FULL_MEMBER_SET,
            CANONICAL,
            receipts,
            digests,
        )

        assertEquals("incomplete", audit.result)
        assertEquals(6_116, audit.summary.total)
        assertEquals(2_780, audit.summary.active)
        assertEquals(3_336, audit.summary.pending)
        assertEquals(1_112, audit.summary.satisfied)
        assertEquals(1_668, audit.summary.missing)
        assertEquals(1_710, audit.errors.size)
        assertEquals(1_668, audit.errors.count { it.startsWith("Missing active binding projection ") })
        assertEquals(42, audit.errors.count { "shared scenario evidence" in it })
        assertEquals(digests, audit.languageReceiptSha256)
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
    fun `same boundary accepts the immediate five receipt gate without activating future languages`() {
        val receipts = receipts(
            CrossLanguageBinding.KOTLIN,
            CrossLanguageBinding.JAVA,
            CrossLanguageBinding.SWIFT,
            CrossLanguageBinding.OBJECTIVE_C,
            CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
        )
        val audit = buildCrossLanguageBindingAudit(
            CrossLanguageBindingPhase.M7_5,
            MEMBERS,
            CANONICAL,
            receipts,
            receiptDigests(receipts),
        )

        assertEquals("complete", audit.result)
        assertEquals(55, audit.summary.total)
        assertEquals(25, audit.summary.active)
        assertEquals(30, audit.summary.pending)
        assertEquals(25, audit.summary.satisfied)
        assertEquals(0, audit.summary.missing)
        assertTrue(audit.errors.isEmpty())
    }

    @Test
    fun `rejects receipt identity phase activation canonical and Kotlin surface mismatches`() {
        val receipts = receipts(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA)
        val digests = receiptDigests(receipts)
        val kotlin = receipts.getValue(CrossLanguageBinding.KOTLIN)
        val java = receipts.getValue(CrossLanguageBinding.JAVA)
        val failures = listOf<() -> Unit>(
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL, mapOf(CrossLanguageBinding.JAVA to java),
                    mapOf(CrossLanguageBinding.JAVA to digests.getValue(CrossLanguageBinding.JAVA)),
                )
            },
            {
                val inactive = receipt(CrossLanguageBinding.C_ABI)
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL,
                    receipts + (CrossLanguageBinding.C_ABI to inactive),
                    digests + (CrossLanguageBinding.C_ABI to "9".repeat(64)),
                )
            },
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL,
                    mapOf(CrossLanguageBinding.KOTLIN to kotlin, CrossLanguageBinding.JAVA to
                        receipt(CrossLanguageBinding.SWIFT)),
                    digests,
                )
            },
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL,
                    receipts + (CrossLanguageBinding.JAVA to java.copy(phase = CrossLanguageBindingPhase.M8)),
                    digests,
                )
            },
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL,
                    receipts + (CrossLanguageBinding.JAVA to java.copy(
                        canonical = CANONICAL.copy(apiReportSha256 = "0".repeat(64)),
                    )),
                    digests,
                )
            },
            { buildCrossLanguageBindingAudit(PHASE, MEMBERS, CANONICAL, receipts, digests - CrossLanguageBinding.JAVA) },
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL, receipts,
                    digests + (CrossLanguageBinding.JAVA to "not-a-digest"),
                )
            },
            {
                buildCrossLanguageBindingAudit(
                    PHASE, MEMBERS, CANONICAL,
                    receipts + (CrossLanguageBinding.KOTLIN to kotlin.copy(publicSymbols = MEMBERS.dropLast(1))),
                    digests,
                )
            },
        )
        failures.forEach { failure -> assertFailsWith<IllegalStateException> { failure() } }
    }

    @Test
    fun `sole evaluator keeps stale and failed receipt evidence incomplete`() {
        val java = receipt(CrossLanguageBinding.JAVA)
        val staleClaim = java.projectionClaims.first().copy(capabilityKey = "common|owner=stale/Owner|kind=function|abi=stale")
        val staleJava = java.copy(projectionClaims = listOf(staleClaim) + java.projectionClaims.drop(1))
        val failedJava = java.copy(bindingTests = java.bindingTests.map {
            it.copy(status = CrossLanguageBindingTestStatus.FAILED)
        })

        listOf(
            staleJava to listOf(
                "Stale projection claim java:${staleClaim.capabilityKey}",
                "Missing active binding projection java:${MEMBERS.first()}",
            ),
            failedJava to listOf(
                "Unknown or non-passed java scenario test",
                "Missing java shared scenario evidence",
                "Missing active binding projection java:",
            ),
        ).forEach { (invalidJava, expectedErrors) ->
            val receipts = mapOf(
                CrossLanguageBinding.KOTLIN to receipt(CrossLanguageBinding.KOTLIN),
                CrossLanguageBinding.JAVA to invalidJava,
            )
            val audit = buildCrossLanguageBindingAudit(
                PHASE,
                MEMBERS,
                CANONICAL,
                receipts,
                receiptDigests(receipts),
            )
            assertEquals("incomplete", audit.result)
            expectedErrors.forEach { expected ->
                assertTrue(audit.errors.any { expected in it }, "Missing corruption error: $expected")
            }
        }
    }

    @Test
    fun `audit preserves narrow exclusion applicability and reason from a universal receipt`() {
        val reason = "Platform factory is external."
        val java = receipt(CrossLanguageBinding.JAVA).let { receipt ->
            receipt.copy(
                projectionClaims = receipt.projectionClaims.drop(1),
                applicabilityExclusions = listOf(
                    CrossLanguageApplicabilityExclusion(MEMBERS.first(), receipt.language, reason),
                ),
            )
        }
        val receipts = mapOf(
            CrossLanguageBinding.KOTLIN to receipt(CrossLanguageBinding.KOTLIN),
            CrossLanguageBinding.JAVA to java,
        )

        val audit = buildCrossLanguageBindingAudit(
            PHASE,
            MEMBERS,
            CANONICAL,
            receipts,
            receiptDigests(receipts),
        )
        val excluded = audit.obligations.single {
            it.language == CrossLanguageBinding.JAVA && it.capabilityKey == MEMBERS.first()
        }

        assertEquals(CrossLanguageObligationStatus.EXCLUDED, excluded.parityStatus)
        assertEquals(CrossLanguageBindingObligationState.EXCLUDED, excluded.obligationState)
        assertEquals(false, excluded.applicable)
        assertEquals(reason, excluded.exclusionReason)
    }

    @Test
    fun `strict audit reader binds universal receipts and rejects any stale record`() {
        val receipts = receipts(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA)
        val digests = receiptDigests(receipts)
        val audit = buildCrossLanguageBindingAudit(PHASE, MEMBERS, CANONICAL, receipts, digests)
        val path = createTempFile("binding-audit", ".json").toFile()
        try {
            path.atomicWriteJson(audit.toJson())
            assertEquals(
                audit,
                readCrossLanguageBindingAudit(path, PHASE, MEMBERS, CANONICAL, receipts, digests),
            )

            val root = audit.toJson()
            val obligations = root.releaseArray("obligations")
            val receiptIdentities = root.releaseObject("languageReceiptSha256")
            val corruptions = listOf(
                JsonObject(root + ("schema" to JsonPrimitive(2))),
                JsonObject(root + ("apiReportSha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("obligations" to JsonArray(obligations.drop(1)))),
                JsonObject(root + ("summary" to JsonObject(root.releaseObject("summary") +
                    ("total" to JsonPrimitive(0))))),
                JsonObject(root + ("errors" to JsonArray(emptyList()))),
                JsonObject(root + ("obligations" to JsonArray(obligations.reversed()))),
                JsonObject(root + ("languageReceiptSha256" to JsonObject(
                    receiptIdentities + ("java" to JsonPrimitive("0".repeat(64))),
                ))),
                JsonObject(root + ("languageReceiptSha256" to JsonObject(receiptIdentities - "java"))),
            )
            corruptions.forEach { corruption ->
                path.atomicWriteJson(corruption)
                assertFailsWith<IllegalStateException> {
                    readCrossLanguageBindingAudit(path, PHASE, MEMBERS, CANONICAL, receipts, digests)
                }
            }

            path.atomicWriteJson(audit.toJson())
            val canonical = path.readText()
            listOf(
                audit.toJson().toString(),
                canonical.removeSuffix("\n"),
                canonical.replaceFirst(
                    "  \"result\": \"incomplete\",",
                    "  \"result\": \"incomplete\",\n  \"result\": \"incomplete\",",
                ),
            ).forEach { noncanonical ->
                path.writeText(noncanonical)
                assertFailsWith<IllegalStateException> {
                    readCrossLanguageBindingAudit(path, PHASE, MEMBERS, CANONICAL, receipts, digests)
                }
            }
        } finally {
            path.delete()
        }
    }

    private fun receipts(
        vararg languages: CrossLanguageBinding,
        members: List<String> = MEMBERS,
    ): Map<CrossLanguageBinding, CrossLanguageBindingReceipt> =
        languages.associateWith { language -> receipt(language, members) }

    private fun receipt(
        language: CrossLanguageBinding,
        members: List<String> = MEMBERS,
    ): CrossLanguageBindingReceipt {
        val testId = "sample.${language.name}BindingTest#projection"
        val symbols = if (language == CrossLanguageBinding.KOTLIN) members else members.mapIndexed { index, _ ->
            "method:sample/${language.name}Owner#$index()V"
        }
        return CrossLanguageBindingReceipt(
            phase = PHASE,
            language = language,
            canonical = CANONICAL,
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
            projectionClaims = if (language == CrossLanguageBinding.KOTLIN) emptyList() else members.mapIndexed {
                    index, member ->
                CrossLanguageProjectionClaim(
                    capabilityKey = member,
                    language = language,
                    publicSymbols = listOf(symbols[index]),
                    executedTests = listOf(testId),
                    sharedScenarios = CrossLanguageBindingScenario.entries,
                )
            },
            applicabilityExclusions = emptyList(),
        )
    }

    private fun receiptDigests(
        receipts: Map<CrossLanguageBinding, CrossLanguageBindingReceipt>,
    ): Map<CrossLanguageBinding, String> = receipts.keys.withIndex().associate { (index, language) ->
        language to (index + 4).toString(16).repeat(64)
    }

    private companion object {
        val PHASE = CrossLanguageBindingPhase.M7_5
        val CANONICAL = CrossLanguageBindingCanonicalIdentity("a".repeat(64), "b".repeat(64))
        val MEMBERS = listOf(
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.first",
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.second",
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.third",
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.fourth",
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.fifth",
        )
        val FULL_MEMBER_SET = (0 until 556).map { index ->
            "common|owner=sample/Owner$index|kind=property|abi=sample/Owner$index.value"
        }
    }
}
