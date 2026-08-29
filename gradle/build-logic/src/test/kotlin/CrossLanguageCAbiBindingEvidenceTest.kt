import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class CrossLanguageCAbiBindingEvidenceTest {
    @Test
    fun `production expectations remain frozen at D104 closure`() {
        assertEquals(1, C_ABI_BOOTSTRAP_SCHEMA)
        assertEquals("codex-agent-c-abi-bootstrap-evidence-v1", C_ABI_BOOTSTRAP_PROTOCOL)
        assertEquals(556, C_ABI_BINDING_CAPABILITY_COUNT)
        assertEquals(777, C_ABI_BINDING_PUBLIC_SYMBOL_COUNT)
        assertEquals(7, C_ABI_BINDING_ARTIFACT_COUNT)
        assertEquals(
            setOf(
                "c-abi-bootstrap",
                "c-abi-scenarios",
                "c-abi-package-macos-arm64",
                "c-abi-package-macos-x64",
                "c-abi-package-linux-arm64",
                "c-abi-package-linux-x64",
                "c-abi-package-windows-x64",
            ),
            C_ABI_BINDING_ARTIFACT_IDS,
        )
        assertEquals(
            "9a73e6d5b49ae052b236cb432f380b3f342d68760655e04369c31d4724d2d4a9",
            C_ABI_BINDING_CAPABILITY_SHA256,
        )
        val mappings = productionCrossLanguageCAbiScenarioMappings()
        assertEquals(14, mappings.size)
        assertEquals(231, mappings.sumOf { it.testIds.size })
        assertEquals(138, mappings.flatMap { it.testIds }.distinct().size)
    }

    @Test
    fun `derives and re-reads schema three M8 C ABI evidence without family inference`() = withFixture { fixture ->
        val output = fixture.directory.resolve("binding-receipt.json")

        val receipt = writeCrossLanguageCAbiBindingReceipt(output, fixture.input())

        assertEquals(CrossLanguageBindingPhase.M8, receipt.phase)
        assertEquals(CrossLanguageBinding.C_ABI, receipt.language)
        assertEquals(2, receipt.projectionClaims.size)
        assertEquals(3, receipt.publicSymbols.size)
        assertEquals(0, receipt.applicabilityExclusions.size)
        assertTrue(receipt.bindingTests.all { it.status == CrossLanguageBindingTestStatus.PASSED })
        assertEquals(listOf(TEST_A), receipt.projectionClaims.single { it.capabilityKey == CAPABILITY_A }.executedTests)
        assertEquals(listOf(TEST_B), receipt.projectionClaims.single { it.capabilityKey == CAPABILITY_B }.executedTests)
        assertEquals(
            CrossLanguageBindingScenario.entries.filterIndexed { index, _ -> index % 2 == 0 }.toSet(),
            receipt.projectionClaims.single { it.capabilityKey == CAPABILITY_A }.sharedScenarios.toSet(),
        )
        assertEquals(
            CrossLanguageBindingScenario.entries.filterIndexed { index, _ -> index % 2 != 0 }.toSet(),
            receipt.projectionClaims.single { it.capabilityKey == CAPABILITY_B }.sharedScenarios.toSet(),
        )
        val root = output.readReleaseObject()
        assertEquals(3, root.releaseInt("schema"))
        assertEquals("passed", root.releaseString("result"))
        assertEquals("M8", root.releaseString("phase"))
        assertEquals("c-abi", root.releaseString("language"))
        assertEquals(receipt, readCrossLanguageBindingReceipt(output))
    }

    @Test
    fun `writes and re-reads canonical scenario proof bound to live bootstrap and Native evidence`() =
        withFixture { fixture ->
            val proof = fixture.writeScenarioProof()

            assertEquals(fixture.scenarioMappings.sortedBy { it.scenario.id }, proof.mappings)
            assertEquals("4".repeat(64), proof.testProgramSha256)
            assertEquals("5".repeat(64), proof.testResultsSha256)
            val root = fixture.scenarioProof.readReleaseObject()
            assertEquals(C_ABI_SCENARIO_PROOF_SCHEMA, root.releaseInt("schemaVersion"))
            assertEquals(C_ABI_SCENARIO_PROOF_ARTIFACT_ID, root.releaseString("artifactId"))
            assertEquals("passed", root.releaseString("result"))
            assertEquals(fixture.bootstrap.releaseDigest(), root.releaseString("bootstrapSha256"))
            assertEquals(
                crossLanguageCAbiCapabilitySha256(CAPABILITIES),
                root.releaseString("capabilitySha256"),
            )
            assertEquals(proof, fixture.readScenarioProof())
        }

    @Test
    fun `scenario proof rejects stale malformed duplicate unsorted and noncanonical evidence`() =
        withFixture { fixture ->
            fixture.writeScenarioProof()
            val root = fixture.scenarioProof.readReleaseObject()
            listOf(
                JsonObject(root - "result"),
                JsonObject(root + ("unexpected" to JsonPrimitive(true))),
                JsonObject(root + ("schemaVersion" to JsonPrimitive(2))),
                JsonObject(root + ("artifactId" to JsonPrimitive("c-abi-scenarios-v2"))),
                JsonObject(root + ("result" to JsonPrimitive("observed"))),
                JsonObject(root + ("bootstrapSha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("capabilitySha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("nativeTestSourcesSha256" to JsonPrimitive("0".repeat(64)))),
                JsonObject(root + ("nativeTestResultsSha256" to JsonPrimitive("0".repeat(64)))),
                root.replaceCAbiArray("scenarios") { it.reversed() },
                root.replaceCAbiArray("scenarios") { it + it.first() },
                root.replaceFirstCAbiArrayObject("scenarios") {
                    JsonObject(it + ("id" to JsonPrimitive("unknown-scenario")))
                },
                root.replaceFirstCAbiArrayObject("scenarios") {
                    it.replaceCAbiArray("testIds") {
                        listOf(JsonPrimitive(TEST_B), JsonPrimitive(TEST_A))
                    }
                },
                root.replaceFirstCAbiArrayObject("scenarios") {
                    it.replaceCAbiArray("testIds") { emptyList() }
                },
            ).forEach(fixture::assertScenarioProofRejected)

            fixture.scenarioProof.writeText(
                releaseJson.encodeToString(
                    kotlinx.serialization.json.JsonElement.serializer(),
                    root,
                ) + "\n\n",
            )
            assertFails { fixture.readScenarioProof() }

            fixture.writeScenarioProof()
            fixture.bootstrap.atomicWriteJson(
                fixture.bootstrapRoot.replaceCAbiObject("artifacts") {
                    JsonObject(it + ("nativeTestResultsSha256" to JsonPrimitive("9".repeat(64))))
                },
            )
            assertFails { fixture.readScenarioProof() }
        }

    @Test
    fun `requires exact bootstrap schema protocol identity and field sets`() = withFixture { fixture ->
        val root = fixture.bootstrapRoot
        listOf(
            JsonObject(root + ("schemaVersion" to JsonPrimitive(2))),
            JsonObject(root + ("protocol" to JsonPrimitive("codex-agent-c-abi-bootstrap-evidence-v2"))),
            JsonObject(root + ("result" to JsonPrimitive("passed"))),
            JsonObject(root + ("milestone" to JsonPrimitive("D105"))),
            JsonObject(root + ("language" to JsonPrimitive("c"))),
            JsonObject(root - "toolchain"),
            JsonObject(root + ("unexpected" to JsonPrimitive(true))),
            root.replaceCAbiObject("canonical") { JsonObject(it - "nativeTargetSha256") },
            root.withClangVersion(""),
            root.withClangVersion(" clang version fixture\nTarget: fixture"),
            root.withClangVersion("clang version *\nTarget: fixture"),
            root.withClangVersion("clang version fixture\u0000\nTarget: fixture"),
            root.withClangVersion("clang version fixture\t\nTarget: fixture"),
            root.replaceCAbiObject("artifacts") { JsonObject(it + ("unexpected" to JsonPrimitive("value"))) },
            root.replaceFirstCAbiArrayObject("compilerConsumers") { JsonObject(it - "executed") },
            root.replaceFirstCAbiArrayObject("nativeTests") { JsonObject(it + ("unexpected" to JsonPrimitive(true))) },
            root.replaceFirstCAbiArrayObject("claims") { JsonObject(it - "consumerReferences") },
        ).forEach { invalid -> fixture.assertBootstrapRejected(invalid) }
    }

    @Test
    fun `rejects residual missing duplicated stale or inconsistent capability inventories`() = withFixture { fixture ->
        val root = fixture.bootstrapRoot
        listOf(
            root.replaceCAbiObject("canonical") {
                JsonObject(it + ("capabilityCount" to JsonPrimitive(3)))
            },
            root.replaceCAbiObject("canonical") {
                JsonObject(it + ("observedCapabilityCount" to JsonPrimitive(1)))
            },
            root.replaceCAbiObject("canonical") {
                JsonObject(it + ("observedCapabilitySha256" to JsonPrimitive("0".repeat(64))))
            },
            root.replaceCAbiObject("canonical") { canonical ->
                canonical.replaceCAbiArray("observedCapabilityKeys") { listOf(it.last(), it.first()) }
            },
            root.replaceCAbiObject("canonical") { canonical ->
                canonical.replaceCAbiArray("observedCapabilityKeys") { it + it.first() }
            },
            root.replaceCAbiObject("canonical") { canonical ->
                canonical.replaceCAbiArray("missingCapabilityKeys") { listOf(JsonPrimitive("residual")) }
            },
            root.replaceCAbiArray("claims") { it.dropLast(1) },
            root.replaceCAbiArray("claims") { it + it.first() },
        ).forEach { invalid -> fixture.assertBootstrapRejected(invalid) }

        fixture.bootstrap.atomicWriteJson(root)
        assertFails { deriveCrossLanguageCAbiBindingReceipt(fixture.input(expectedCapabilityCount = 3)) }
        assertFails {
            deriveCrossLanguageCAbiBindingReceipt(
                fixture.input(expectedCapabilitySha256 = "0".repeat(64)),
            )
        }
    }

    @Test
    fun `rejects weakened public symbol claim and native test evidence`() = withFixture { fixture ->
        val root = fixture.bootstrapRoot
        listOf(
            root.replaceCAbiArray("linkedPublicSymbols") { it + it.first() },
            root.replaceCAbiArray("linkedPublicSymbols") { it.dropLast(1) },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("publicSymbols") { listOf(JsonPrimitive("codex_agent_stale")) }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("headerReferences") { emptyList() }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("consumerReferences") { it + it.first() }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("headerReferences") {
                    listOf(JsonPrimitive("codex_agent_a"), JsonPrimitive("codex_agent_bogus_header"))
                }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("consumerReferences") {
                    listOf(JsonPrimitive("codex_agent_a"), JsonPrimitive("codex_agent_bogus_consumer"))
                }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("nativeTestIds") { listOf(JsonPrimitive("missing.Test")) }
            },
            root.replaceFirstCAbiArrayObject("claims") { claim ->
                claim.replaceCAbiArray("nativeTestIds") { listOf(JsonPrimitive("Family*")) }
            },
            root.replaceFirstCAbiArrayObject("nativeTests") { test ->
                JsonObject(test + ("status" to JsonPrimitive("failed")))
            },
            root.replaceCAbiArray("nativeTests") { it + it.first() },
        ).forEach { invalid -> fixture.assertBootstrapRejected(invalid) }

        fixture.bootstrap.atomicWriteJson(root)
        assertFails { deriveCrossLanguageCAbiBindingReceipt(fixture.input(expectedPublicSymbolCount = 4)) }
    }

    @Test
    fun `requires one exact nonempty passed claim-owned mapping for all fourteen scenarios`() = withFixture { fixture ->
        val mappings = fixture.scenarioMappings
        listOf(
            mappings.dropLast(1),
            mappings + mappings.first(),
            mappings.mapIndexed { index, mapping -> if (index == 0) mapping.copy(testIds = emptyList()) else mapping },
            mappings.mapIndexed { index, mapping ->
                if (index == 0) mapping.copy(testIds = listOf(TEST_A, TEST_A)) else mapping
            },
            mappings.mapIndexed { index, mapping ->
                if (index == 0) mapping.copy(testIds = listOf("missing.Test")) else mapping
            },
            mappings.mapIndexed { index, mapping ->
                if (index == 0) mapping.copy(testIds = listOf("Family*")) else mapping
            },
            mappings.map { it.copy(testIds = listOf(TEST_A)) },
        ).forEach { invalid ->
            assertFails { deriveCrossLanguageCAbiBindingReceipt(fixture.input(scenarioMappings = invalid)) }
        }

        val familyTest = "BehaviorTest.family"
        val withUnownedPassedTest = fixture.bootstrapRoot.replaceCAbiArray("nativeTests") { tests ->
            (tests + buildJsonObject {
                put("testId", JsonPrimitive(familyTest))
                put("status", JsonPrimitive("passed"))
            }).sortedBy { (it as JsonObject).releaseString("testId") }
        }
        fixture.bootstrap.atomicWriteJson(withUnownedPassedTest)
        val familyMappings = mappings.mapIndexed { index, mapping ->
            if (index == 0) mapping.copy(testIds = listOf(familyTest)) else mapping
        }
        assertFails {
            deriveCrossLanguageCAbiBindingReceipt(fixture.input(scenarioMappings = familyMappings))
        }
    }

    @Test
    fun `requires the frozen complete unique artifact inventory and explicit exact result digests`() =
        withFixture { fixture ->
            val artifacts = fixture.artifacts
            listOf(
                artifacts.dropLast(1),
                artifacts.dropLast(1) + artifacts.first(),
                artifacts.mapIndexed { index, artifact ->
                    if (index == 0) artifact.copy(id = "artifact*") else artifact
                },
                artifacts.mapIndexed { index, artifact ->
                    if (index == 0) artifact.copy(sha256 = "A".repeat(64)) else artifact
                },
            ).forEach { invalid ->
                assertFails { deriveCrossLanguageCAbiBindingReceipt(fixture.input(artifactIdentities = invalid)) }
            }
            assertFails {
                deriveCrossLanguageCAbiBindingReceipt(fixture.input(testProgramSha256 = "program"))
            }
            assertFails {
                deriveCrossLanguageCAbiBindingReceipt(fixture.input(testResultsSha256 = "F".repeat(64)))
            }
        }

    private fun withFixture(block: (Fixture) -> Unit) {
        val directory = createTempDirectory("c-abi-binding-evidence-").toFile()
        try {
            block(Fixture(directory))
        } finally {
            directory.deleteRecursively()
        }
    }

    private class Fixture(val directory: File) {
        val bootstrap = directory.resolve("bootstrap-evidence.json")
        val scenarioProof = directory.resolve("scenario-proof.json")
        val scenarioMappings = CrossLanguageBindingScenario.entries.mapIndexed { index, scenario ->
            CrossLanguageCAbiScenarioMapping(scenario, listOf(if (index % 2 == 0) TEST_A else TEST_B))
        }
        val artifacts = listOf(
            "c-abi-bootstrap",
            "c-abi-scenarios",
            "c-abi-package-macos-arm64",
            "c-abi-package-macos-x64",
            "c-abi-package-linux-x64",
            "c-abi-package-linux-arm64",
            "c-abi-package-windows-x64",
        ).mapIndexed { index, id ->
            CrossLanguageBindingArtifactIdentity(id, (index + 1).toString().repeat(64))
        }
        val bootstrapRoot: JsonObject = bootstrapRoot().also { bootstrap.atomicWriteJson(it) }

        fun input(
            scenarioMappings: List<CrossLanguageCAbiScenarioMapping> = this.scenarioMappings,
            artifactIdentities: List<CrossLanguageBindingArtifactIdentity> = artifacts,
            testProgramSha256: String = "3".repeat(64),
            testResultsSha256: String = "4".repeat(64),
            expectedCapabilityCount: Int = 2,
            expectedPublicSymbolCount: Int = 3,
            expectedCapabilitySha256: String = crossLanguageCAbiCapabilitySha256(CAPABILITIES),
        ) = CrossLanguageCAbiBindingEvidenceInput(
            bootstrapEvidence = bootstrap,
            scenarioMappings = scenarioMappings,
            artifactIdentities = artifactIdentities,
            testProgramSha256 = testProgramSha256,
            testResultsSha256 = testResultsSha256,
            expectedCapabilityCount = expectedCapabilityCount,
            expectedPublicSymbolCount = expectedPublicSymbolCount,
            expectedCapabilitySha256 = expectedCapabilitySha256,
        )

        fun assertBootstrapRejected(root: JsonObject) {
            bootstrap.atomicWriteJson(root)
            assertFails { deriveCrossLanguageCAbiBindingReceipt(input()) }
        }

        fun writeScenarioProof(): CrossLanguageCAbiScenarioProof = writeCrossLanguageCAbiScenarioProof(
            scenarioProof,
            bootstrap,
            scenarioMappings,
            expectedCapabilityCount = 2,
            expectedPublicSymbolCount = 3,
            expectedCapabilitySha256 = crossLanguageCAbiCapabilitySha256(CAPABILITIES),
        )

        fun readScenarioProof(): CrossLanguageCAbiScenarioProof = readCrossLanguageCAbiScenarioProof(
            scenarioProof,
            bootstrap,
            expectedCapabilityCount = 2,
            expectedPublicSymbolCount = 3,
            expectedCapabilitySha256 = crossLanguageCAbiCapabilitySha256(CAPABILITIES),
        )

        fun assertScenarioProofRejected(root: JsonObject) {
            scenarioProof.atomicWriteJson(root)
            assertFails { readScenarioProof() }
        }
    }

    private companion object {
        const val CAPABILITY_A = "common|owner=example/A|kind=function|abi=example/A.a|{}a[0]"
        const val CAPABILITY_B = "common|owner=example/B|kind=property|abi=example/B.b|{}b[0]"
        const val TEST_A = "ExampleBehaviorTest.a"
        const val TEST_B = "ExampleBehaviorTest.b"
        val CAPABILITIES = listOf(CAPABILITY_A, CAPABILITY_B)
        val SYMBOLS = listOf("codex_agent_a", "codex_agent_a_value", "codex_agent_b")

        fun bootstrapRoot(): JsonObject = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive(C_ABI_BOOTSTRAP_PROTOCOL))
            put("result", JsonPrimitive("observed"))
            put("milestone", JsonPrimitive("D104"))
            put("language", JsonPrimitive("c-abi"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive("a".repeat(64)))
                put("coverageReceiptSha256", JsonPrimitive("b".repeat(64)))
                put("nativeTargetSha256", JsonPrimitive("c".repeat(64)))
                put("capabilityCount", JsonPrimitive(2))
                put("observedCapabilityCount", JsonPrimitive(2))
                put("observedCapabilitySha256", JsonPrimitive(crossLanguageCAbiCapabilitySha256(CAPABILITIES)))
                put("observedCapabilityKeys", CAPABILITIES.toCAbiJsonArray())
                put("missingCapabilityKeys", JsonArray(emptyList()))
            })
            put("toolchain", buildJsonObject {
                put("clang", JsonPrimitive("/usr/bin/clang"))
                put("clangCpp", JsonPrimitive("/usr/bin/clang++"))
                put("clangVersion", JsonPrimitive("clang version fixture\nTarget: fixture\nThread model: posix"))
                put("macosSdk", JsonPrimitive("/sdk"))
            })
            put("artifacts", buildJsonObject {
                put("reviewedHeaderSha256", JsonPrimitive("d".repeat(64)))
                put("cinteropDefinitionSha256", JsonPrimitive("e".repeat(64)))
                put("exportPolicySha256", JsonPrimitive("f".repeat(64)))
                put("generatedHeaderSha256", JsonPrimitive("0".repeat(64)))
                put("releaseLibrarySha256", JsonPrimitive("1".repeat(64)))
                put("nativeTestExecutableSha256", JsonPrimitive("2".repeat(64)))
                put("nativeMainSourcesSha256", JsonPrimitive("3".repeat(64)))
                put("nativeTestSourcesSha256", JsonPrimitive("4".repeat(64)))
                put("nativeTestResultsSha256", JsonPrimitive("5".repeat(64)))
                put("fileIdentity", JsonPrimitive("fixture-library"))
                put("installName", JsonPrimitive("@rpath/libfixture.dylib"))
            })
            put("compilerConsumers", buildJsonArray {
                add(buildJsonObject {
                    put("id", JsonPrimitive("fixture-c-consumer"))
                    put("sourceSha256", JsonPrimitive("6".repeat(64)))
                    put("artifactSha256", JsonPrimitive("7".repeat(64)))
                    put("executed", JsonPrimitive(true))
                })
            })
            put("linkedPublicSymbols", SYMBOLS.toCAbiJsonArray())
            put("nativeTests", buildJsonArray {
                listOf(TEST_A, TEST_B).forEach { testId ->
                    add(buildJsonObject {
                        put("testId", JsonPrimitive(testId))
                        put("status", JsonPrimitive("passed"))
                    })
                }
            })
            put("claims", buildJsonArray {
                add(claim(CAPABILITY_A, listOf("codex_agent_a", "codex_agent_a_value"), TEST_A))
                add(claim(CAPABILITY_B, listOf("codex_agent_b"), TEST_B))
            })
        }

        fun claim(capabilityKey: String, symbols: List<String>, testId: String): JsonObject = buildJsonObject {
            put("capabilityKey", JsonPrimitive(capabilityKey))
            put("headerReferences", symbols.toCAbiJsonArray())
            put("consumerReferences", symbols.toCAbiJsonArray())
            put("publicSymbols", symbols.toCAbiJsonArray())
            put("nativeTestIds", listOf(testId).toCAbiJsonArray())
        }
    }
}

private fun Iterable<String>.toCAbiJsonArray(): JsonArray = JsonArray(map { JsonPrimitive(it) })

private fun JsonObject.replaceCAbiObject(name: String, transform: (JsonObject) -> JsonObject): JsonObject =
    JsonObject(this + (name to transform(this[name] as JsonObject)))

private fun JsonObject.replaceCAbiArray(
    name: String,
    transform: (List<kotlinx.serialization.json.JsonElement>) -> List<kotlinx.serialization.json.JsonElement>,
): JsonObject = JsonObject(this + (name to JsonArray(transform((this[name] as JsonArray).toList()))))

private fun JsonObject.replaceFirstCAbiArrayObject(
    name: String,
    transform: (JsonObject) -> JsonObject,
): JsonObject = replaceCAbiArray(name) { values ->
    listOf(transform(values.first() as JsonObject)) + values.drop(1)
}

private fun JsonObject.withClangVersion(value: String): JsonObject = replaceCAbiObject("toolchain") {
    JsonObject(it + ("clangVersion" to JsonPrimitive(value)))
}
