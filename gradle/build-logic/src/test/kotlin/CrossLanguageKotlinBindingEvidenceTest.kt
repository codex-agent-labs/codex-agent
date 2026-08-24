import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class CrossLanguageKotlinBindingEvidenceTest {
    @Test
    fun `writes canonical universal Kotlin receipt without projection or exclusion records`() = withFixture { fixture ->
        val evidence = fixture.derive()
        val expected = buildKotlinBindingParityReceipt(evidence)

        writeCrossLanguageBindingReceipt(fixture.parityReceipt, expected)
        val actual = readCrossLanguageBindingReceipt(fixture.parityReceipt)
        verifyKotlinBindingParityReceipt(actual, expected)

        assertEquals(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA, actual.toJson().releaseInt("schema"))
        assertEquals(CrossLanguageBindingPhase.M7_5, actual.phase)
        assertEquals(CrossLanguageBinding.KOTLIN, actual.language)
        assertEquals(evidence.digests.apiReportSha256, actual.canonical.apiReportSha256)
        assertEquals(evidence.digests.canonicalCoverageSha256, actual.canonical.coverageReceiptSha256)
        assertEquals(
            listOf(CrossLanguageBindingArtifactIdentity("kotlin-public-api", evidence.digests.artifactSha256)),
            actual.artifacts,
        )
        assertEquals(evidence.digests.compiledTestsSha256, actual.testProgramSha256)
        assertEquals(evidence.digests.testResultsSha256, actual.testResultsSha256)
        assertEquals(MEMBERS, actual.publicSymbols)
        assertEquals(
            evidence.bindingTests.sortedBy(CrossLanguageBindingTestEvidence::testId),
            actual.bindingTests,
        )
        assertTrue(actual.bindingTests.all { it.status == CrossLanguageBindingTestStatus.PASSED })
        assertEquals(
            evidence.scenarioEvidence.associate { it.scenario to it.testIds },
            actual.scenarioEvidence.associate { it.scenario to it.testIds },
        )
        assertTrue(actual.projectionClaims.isEmpty())
        assertTrue(actual.applicabilityExclusions.isEmpty())
        assertFailsWith<IllegalStateException> {
            verifyKotlinBindingParityReceipt(actual.copy(publicSymbols = actual.publicSymbols.dropLast(1)), expected)
        }
    }

    @Test
    fun `derives every capability and all closed scenarios from bound successful evidence`() = withFixture { fixture ->
        val evidence = fixture.derive()

        assertEquals(MEMBERS, evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey))
        assertTrue(evidence.capabilityClaims.all { it.publicSymbol == it.capabilityKey })
        assertEquals(
            CrossLanguageBindingScenario.entries,
            evidence.scenarioEvidence.map(CrossLanguageScenarioEvidence::scenario),
        )
        assertTrue(evidence.bindingTests.all { it.status == CrossLanguageBindingTestStatus.PASSED })
        assertEquals(fixture.artifact.releaseDigest(), evidence.digests.artifactSha256)
        assertEquals(fixture.report.releaseDigest(), evidence.digests.apiReportSha256)
        assertEquals(fixture.receipt.releaseDigest(), evidence.digests.canonicalCoverageSha256)
        assertEquals("a".repeat(64), evidence.digests.compiledTestsSha256)
        assertEquals("b".repeat(64), evidence.digests.testResultsSha256)
    }

    @Test
    fun `rejects incomplete unknown duplicate conflicting and stale scenario mappings`() = withFixture { fixture ->
        val first = kotlinBindingScenarioMappings.first()
        val cases = listOf(
            kotlinBindingScenarioMappings.drop(1),
            kotlinBindingScenarioMappings + KotlinBindingScenarioMapping("unknown", PASSED_TEST_IDS.first()),
            kotlinBindingScenarioMappings + first,
            kotlinBindingScenarioMappings + first.copy(canonicalTestIds = listOf(PASSED_TEST_IDS.last())),
            kotlinBindingScenarioMappings.map {
                if (it == first) it.copy(canonicalTestIds = listOf("removed.Test#stale")) else it
            },
            kotlinBindingScenarioMappings.map {
                if (it == first) it.copy(canonicalTestIds = listOf("*"))
                else it
            },
            kotlinBindingScenarioMappings.map {
                if (it == first) it.copy(canonicalTestIds = listOf(PASSED_TEST_IDS.first(), PASSED_TEST_IDS.first()))
                else it
            },
        )

        cases.forEach { mappings ->
            assertFailsWith<IllegalStateException> { fixture.derive(mappings) }
        }
    }

    @Test
    fun `rejects failed stale malformed and digest mismatched coverage receipts`() = withFixture { fixture ->
        fixture.writeReceipt(result = "failed")
        assertFailsWith<IllegalStateException> { fixture.derive() }

        fixture.writeReceipt(reportDigest = "0".repeat(64))
        assertFailsWith<IllegalStateException> { fixture.derive() }

        fixture.writeReceipt(members = MEMBERS.dropLast(1))
        assertFailsWith<IllegalStateException> { fixture.derive() }

        fixture.writeReceipt(extraClaimTestId = "removed.Test#stale", extraClaimMember = "removed-member")
        assertFailsWith<IllegalStateException> { fixture.derive() }

        fixture.writeReceipt(compiledTestsDigest = "not-a-digest")
        assertFailsWith<IllegalStateException> { fixture.derive() }
    }

    @Test
    fun `rejects absent duplicate malformed and mismatched JVM artifact targets`() = withFixture { fixture ->
        val digest = fixture.artifact.releaseDigest()
        listOf(
            emptyList(),
            listOf("jvm-classes" to digest, "jvm-classes" to digest),
            listOf("jvm" to digest),
            listOf("jvm-classes" to "not-a-digest"),
            listOf("jvm-classes" to "0".repeat(64)),
        ).forEach { targets ->
            fixture.writeReport(targets)
            fixture.writeReceipt()
            assertFailsWith<IllegalStateException> { fixture.derive() }
        }
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("kotlin-binding-evidence").toFile()
        try {
            val fixture = Fixture(root)
            fixture.writeReport()
            fixture.writeReceipt()
            block(fixture)
        } finally {
            root.deleteRecursively()
        }
    }

    private class Fixture(root: File) {
        val artifact = root.resolve("codex-agent.jar").apply { writeText("artifact") }
        val report = root.resolve("canonical-api.json")
        val receipt = root.resolve("canonical-coverage.json")
        val parityReceipt = root.resolve("kotlin-parity.json")

        fun derive(
            mappings: List<KotlinBindingScenarioMapping> = kotlinBindingScenarioMappings,
        ): CrossLanguageKotlinBindingEvidence = deriveCrossLanguageKotlinBindingEvidence(
            artifact,
            report,
            receipt,
            mappings,
        )

        fun writeReport(
            targets: List<Pair<String, String>> = listOf("jvm-classes" to artifact.releaseDigest()),
        ) {
            report.writeText(buildJsonObject {
                put("schema", JsonPrimitive(1))
                put("libraryUniqueName", JsonPrimitive("codex-agent-core"))
                put("markerAnnotation", JsonPrimitive("CodexBindingApi"))
                put("signatureVersion", JsonPrimitive(1))
                put("boundaryTypes", buildJsonArray {})
                put("memberExclusionAnnotation", JsonPrimitive("CodexBindingApiKotlinOnly"))
                put("excludedReachableTypes", buildJsonArray {})
                put("excludedMemberKeys", buildJsonArray {})
                put("dataClassMetadataAvailable", JsonPrimitive(true))
                put("dataClassNames", buildJsonArray {})
                put("owners", buildJsonArray {
                    add(buildJsonObject {
                        put("name", JsonPrimitive("sample/Owner"))
                        put("members", buildJsonArray { MEMBERS.forEach { add(JsonPrimitive(it)) } })
                    })
                })
                put("targets", buildJsonArray {
                    targets.forEach { (kind, sha256) ->
                        add(buildJsonObject {
                            put("kind", JsonPrimitive(kind))
                            put("sha256", JsonPrimitive(sha256))
                        })
                    }
                })
            }.toString())
        }

        fun writeReceipt(
            result: String = "passed",
            reportDigest: String = report.releaseDigest(),
            members: List<String> = MEMBERS,
            extraClaimTestId: String? = null,
            extraClaimMember: String? = null,
            compiledTestsDigest: String = "a".repeat(64),
        ) {
            val claims = PASSED_TEST_IDS.mapIndexed { index, testId ->
                testId to listOf(MEMBERS[index % MEMBERS.size])
            }.toMutableList()
            extraClaimTestId?.let { claims += it to listOf(checkNotNull(extraClaimMember)) }
            receipt.writeText(buildJsonObject {
                put("schema", JsonPrimitive(1))
                put("result", JsonPrimitive(result))
                put("kotlinCompilerVersion", JsonPrimitive("2.3.10"))
                put("canonicalTestTask", JsonPrimitive(":codex-agent-core:jvmTest"))
                put("apiReportSha256", JsonPrimitive(reportDigest))
                put("compiledTestsSha256", JsonPrimitive(compiledTestsDigest))
                put("testResultsSha256", JsonPrimitive("b".repeat(64)))
                put("members", buildJsonArray { members.forEach { add(JsonPrimitive(it)) } })
                put("claims", buildJsonArray {
                    claims.forEach { (testId, claimedMembers) ->
                        add(buildJsonObject {
                            put("testId", JsonPrimitive(testId))
                            put("members", buildJsonArray {
                                claimedMembers.forEach { add(JsonPrimitive(it)) }
                            })
                        })
                    }
                })
            }.toString())
        }
    }

    private companion object {
        val MEMBERS = listOf(
            "common|owner=sample/Owner|kind=function|abi=sample/Owner.second|second(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]",
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.first|{}first[0]|propertyKind=VAL|type=kotlin/String!!",
        )
        val PASSED_TEST_IDS = kotlinBindingScenarioMappings
            .flatMap(KotlinBindingScenarioMapping::canonicalTestIds)
            .distinct()
            .sorted()
    }
}
