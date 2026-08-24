import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

class CrossLanguageBindingReceiptTest {
    @Test
    fun `schema three round trips every evaluator record with receipt language injected`() = withReceipt { file ->
        val expected = receipt()
        writeCrossLanguageBindingReceipt(file, expected)

        val actual = readCrossLanguageBindingReceipt(file)

        assertEquals(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA, actual.toJson().releaseInt("schema"))
        assertEquals(CrossLanguageBinding.JAVA, actual.language)
        assertTrue(actual.bindingTests.all { it.language == actual.language })
        assertTrue(actual.scenarioEvidence.all { it.language == actual.language })
        assertTrue(actual.projectionClaims.all { it.language == actual.language })
        assertTrue(actual.applicabilityExclusions.all { it.language == actual.language })
        assertEquals(ARTIFACTS.sortedBy(CrossLanguageBindingArtifactIdentity::id), actual.artifacts)
        assertEquals(SYMBOLS.sorted(), actual.publicSymbols)
        assertEquals(TESTS.sorted(), actual.bindingTests.map(CrossLanguageBindingTestEvidence::testId))
        assertEquals(CrossLanguageBindingScenario.entries.map(CrossLanguageBindingScenario::id).sorted(),
            actual.scenarioEvidence.map { it.scenario.id })
        assertTrue(file.readText().endsWith("\n"))
    }

    @Test
    fun `requires the exact top level and nested field sets`() = withReceipt { file ->
        val root = receipt().toJson()
        listOf(
            JsonObject(root - "result"),
            JsonObject(root + ("unexpected" to JsonPrimitive(true))),
            root.replaceObject("canonical") { JsonObject(it - "apiReportSha256") },
            root.replaceObject("canonical") { JsonObject(it + ("unexpected" to JsonPrimitive("value"))) },
            root.replaceFirstArrayObject("artifacts") { JsonObject(it - "sha256") },
            root.replaceFirstArrayObject("tests") { JsonObject(it + ("unexpected" to JsonPrimitive("value"))) },
            root.replaceFirstArrayObject("scenarios") { JsonObject(it - "testIds") },
            root.replaceFirstArrayObject("claims") { JsonObject(it - "executedTests") },
            root.replaceFirstArrayObject("exclusions") { JsonObject(it - "reason") },
        ).forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFails { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `rejects duplicate records and noncanonical ordering`() = withReceipt { file ->
        val root = receipt().toJson()
        val duplicates = listOf(
            root.replaceArray("artifacts") { it + it.first() },
            root.replaceArray("publicSymbols") { it + it.first() },
            root.replaceArray("tests") { it + it.first() },
            root.replaceArray("scenarios") { it + it.first() },
            root.replaceArray("claims") { it + it.first() },
            root.replaceArray("exclusions") { it + it.first() },
            root.replaceFirstArrayObject("scenarios") { scenario ->
                scenario.replaceArray("testIds") { it + it.first() }
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("publicSymbols") { it + it.first() }
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("executedTests") { it + it.first() }
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("sharedScenarios") { it + it.first() }
            },
        )
        duplicates.forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFails { readCrossLanguageBindingReceipt(file) }
        }

        listOf("artifacts", "publicSymbols", "tests", "scenarios", "claims", "exclusions").forEach { name ->
            file.atomicWriteJson(root.replaceArray(name) { it.reversed() })
            assertFailure("not canonically encoded") { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `requires exact canonical and producer digests`() = withReceipt { file ->
        val root = receipt().toJson()
        listOf(
            root.replaceObject("canonical") {
                JsonObject(it + ("apiReportSha256" to JsonPrimitive("A".repeat(64))))
            },
            root.replaceObject("canonical") {
                JsonObject(it + ("coverageReceiptSha256" to JsonPrimitive("a".repeat(63))))
            },
            JsonObject(root + ("testProgramSha256" to JsonPrimitive("not-a-digest"))),
            JsonObject(root + ("testResultsSha256" to JsonPrimitive("0".repeat(65)))),
            root.replaceFirstArrayObject("artifacts") {
                JsonObject(it + ("sha256" to JsonPrimitive("g".repeat(64))))
            },
        ).forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFailure("SHA-256") { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `rejects unknown language phase status and scenarios`() = withReceipt { file ->
        val root = receipt().toJson()
        listOf(
            JsonObject(root + ("language" to JsonPrimitive("java-ish"))),
            JsonObject(root + ("phase" to JsonPrimitive("M7.5"))),
            root.replaceFirstArrayObject("tests") {
                JsonObject(it + ("status" to JsonPrimitive("disabled")))
            },
            root.replaceFirstArrayObject("scenarios") {
                JsonObject(it + ("id" to JsonPrimitive("future-scenario")))
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("sharedScenarios") { listOf(JsonPrimitive("future-scenario")) }
            },
        ).forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFails { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `rejects blank wildcard and malformed exact records`() = withReceipt { file ->
        val root = receipt().toJson()
        listOf(
            root.replaceFirstArrayObject("artifacts") { JsonObject(it + ("id" to JsonPrimitive(" "))) },
            root.replaceArray("publicSymbols") { listOf(JsonPrimitive("symbol:*")) + it.drop(1) },
            root.replaceFirstArrayObject("tests") { JsonObject(it + ("id" to JsonPrimitive(" test "))) },
            root.replaceFirstArrayObject("claims") {
                JsonObject(it + ("capabilityKey" to JsonPrimitive("common|owner=*")))
            },
            root.replaceFirstArrayObject("exclusions") {
                JsonObject(it + ("reason" to JsonPrimitive("*")))
            },
            root.replaceFirstArrayObject("exclusions") {
                JsonObject(it + ("reason" to JsonPrimitive("Internal\tcontrol")))
            },
        ).forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFails { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `binds scenario and claim references to receipt inventories`() = withReceipt { file ->
        val root = receipt().toJson()
        listOf(
            root.replaceFirstArrayObject("scenarios") { scenario ->
                scenario.replaceArray("testIds") { listOf(JsonPrimitive("stale.Test#missing")) }
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("publicSymbols") { listOf(JsonPrimitive("method:stale/Owner#missing()V")) }
            },
            root.replaceFirstArrayObject("claims") { claim ->
                claim.replaceArray("executedTests") { listOf(JsonPrimitive("stale.Test#missing")) }
            },
            root.replaceArray("scenarios") { it.dropLast(1) },
        ).forEach { invalid ->
            file.atomicWriteJson(invalid)
            assertFailure(if (invalid === root) "stale" else "") { readCrossLanguageBindingReceipt(file) }
        }
    }

    @Test
    fun `rejects conflicting claims and exclusions`() = withReceipt { file ->
        val root = receipt().toJson()
        val claimKey = (root.releaseArray("claims").first() as JsonObject).releaseString("capabilityKey")
        val invalid = root.replaceFirstArrayObject("exclusions") {
            JsonObject(it + ("capabilityKey" to JsonPrimitive(claimKey)))
        }
        file.atomicWriteJson(invalid)

        assertFailure("conflict") { readCrossLanguageBindingReceipt(file) }
    }

    @Test
    fun `Kotlin alone may carry no projection claims or exclusions`() = withReceipt { file ->
        val kotlin = receipt(CrossLanguageBinding.KOTLIN).copy(
            projectionClaims = emptyList(),
            applicabilityExclusions = emptyList(),
        )
        writeCrossLanguageBindingReceipt(file, kotlin)
        assertTrue(readCrossLanguageBindingReceipt(file).projectionClaims.isEmpty())

        assertFailure("must not carry") {
            writeCrossLanguageBindingReceipt(
                file,
                kotlin.copy(projectionClaims = receipt(CrossLanguageBinding.KOTLIN).projectionClaims),
            )
        }
        assertFailure("must not carry") {
            writeCrossLanguageBindingReceipt(
                file,
                kotlin.copy(applicabilityExclusions = receipt(CrossLanguageBinding.KOTLIN).applicabilityExclusions),
            )
        }
        val java = receipt().copy(projectionClaims = emptyList(), applicabilityExclusions = emptyList())
        assertFailure("Non-Kotlin") { writeCrossLanguageBindingReceipt(file, java) }
    }

    @Test
    fun `canonical byte reader rejects compact missing-newline and duplicate-key JSON`() = withReceipt { file ->
        val receipt = receipt()
        writeCrossLanguageBindingReceipt(file, receipt)
        val canonical = file.readText()

        file.writeText(receipt.toJson().toString())
        assertFailure("not canonically encoded") { readCrossLanguageBindingReceipt(file) }

        file.writeText(canonical.removeSuffix("\n"))
        assertFailure("not canonically encoded") { readCrossLanguageBindingReceipt(file) }

        file.writeText(canonical.replaceFirst(
            "\"result\": \"passed\",",
            "\"result\": \"passed\",\n    \"result\": \"passed\",",
        ))
        assertFails { readCrossLanguageBindingReceipt(file) }
    }

    private fun receipt(language: CrossLanguageBinding = CrossLanguageBinding.JAVA): CrossLanguageBindingReceipt {
        val tests = TESTS.map { id ->
            CrossLanguageBindingTestEvidence(language, id, CrossLanguageBindingTestStatus.PASSED)
        }
        return CrossLanguageBindingReceipt(
            phase = CrossLanguageBindingPhase.M7_5,
            language = language,
            canonical = CrossLanguageBindingCanonicalIdentity("a".repeat(64), "b".repeat(64)),
            artifacts = ARTIFACTS,
            testProgramSha256 = "c".repeat(64),
            testResultsSha256 = "d".repeat(64),
            publicSymbols = SYMBOLS,
            bindingTests = tests,
            scenarioEvidence = CrossLanguageBindingScenario.entries.map { scenario ->
                CrossLanguageScenarioEvidence(language, scenario, listOf(TESTS.first()))
            },
            projectionClaims = listOf(
                CrossLanguageProjectionClaim(
                    CAPABILITY,
                    language,
                    listOf(SYMBOLS.first()),
                    listOf(TESTS.first()),
                    listOf(CrossLanguageBindingScenario.ASYNC_SUCCESS),
                ),
                CrossLanguageProjectionClaim(
                    SECOND_CAPABILITY,
                    language,
                    listOf(SYMBOLS.last()),
                    listOf(TESTS.last()),
                    listOf(CrossLanguageBindingScenario.STATE_CURRENT_VALUE),
                ),
            ),
            applicabilityExclusions = listOf(
                CrossLanguageApplicabilityExclusion(EXCLUDED_CAPABILITY, language, "Platform factory is external."),
                CrossLanguageApplicabilityExclusion(
                    SECOND_EXCLUDED_CAPABILITY,
                    language,
                    "Runtime selection is host-owned.",
                ),
            ),
        )
    }

    private fun withReceipt(block: (File) -> Unit) {
        val directory = createTempDirectory("binding-receipt").toFile()
        try {
            block(directory.resolve("receipt.json"))
        } finally {
            directory.deleteRecursively()
        }
    }

    private fun assertFailure(message: String, block: () -> Unit) {
        val failure = assertFails(block)
        if (message.isNotEmpty()) {
            assertTrue(message in failure.message.orEmpty(), failure.stackTraceToString())
        }
    }

    private fun JsonObject.replaceArray(
        name: String,
        transform: (List<kotlinx.serialization.json.JsonElement>) -> List<kotlinx.serialization.json.JsonElement>,
    ): JsonObject = JsonObject(this + (name to JsonArray(transform(releaseArray(name)))))

    private fun JsonObject.replaceObject(name: String, transform: (JsonObject) -> JsonObject): JsonObject =
        JsonObject(this + (name to transform(releaseObject(name))))

    private fun JsonObject.replaceFirstArrayObject(
        name: String,
        transform: (JsonObject) -> JsonObject,
    ): JsonObject = replaceArray(name) { values ->
        listOf(transform(values.first() as JsonObject)) + values.drop(1)
    }

    private companion object {
        const val CAPABILITY = "common|owner=sample/Owner|kind=function|abi=sample/Owner.run"
        const val SECOND_CAPABILITY = "common|owner=sample/Owner|kind=function|abi=sample/Owner.close"
        const val EXCLUDED_CAPABILITY = "common|owner=sample/Owner|kind=property|abi=sample/Owner.host"
        const val SECOND_EXCLUDED_CAPABILITY =
            "common|owner=sample/Owner|kind=property|abi=sample/Owner.runtime"
        val ARTIFACTS = listOf(
            CrossLanguageBindingArtifactIdentity("runtime", "2".repeat(64)),
            CrossLanguageBindingArtifactIdentity("core", "1".repeat(64)),
        )
        val SYMBOLS = listOf(
            "method:sample/Owner#runAsync()Ljava/util/concurrent/CompletionStage;",
            "method:sample/Owner#close()V",
        )
        val TESTS = listOf("sample.BindingTest#projection", "sample.BindingTest#lifecycle")
    }
}
