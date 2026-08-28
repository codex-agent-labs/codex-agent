import java.io.File
import java.security.MessageDigest
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class CrossLanguageCAbiBootstrapEvidenceTest {
    @Test
    fun `derives the exact reviewed 556 capability bootstrap slice`() {
        val inputs = validInputs()
        val claims = inputs.derive()
        val keys = claims.map(CAbiBootstrapClaim::capabilityKey)
        val complement = (inputs.canonicalKeys.toSet() - keys.toSet()).sorted()

        assertEquals(556, inputs.canonicalKeys.size)
        assertEquals(inputs.canonicalKeys.sorted(), inputs.canonicalKeys)
        assertEquals(inputs.canonicalKeys.size, inputs.canonicalKeys.distinct().size)
        assertEquals(35, D093_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D093_SELECTED_CAPABILITY_KEYS.sorted(), D093_SELECTED_CAPABILITY_KEYS)
        assertEquals(92, D094_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D094_SELECTED_CAPABILITY_KEYS.sorted(), D094_SELECTED_CAPABILITY_KEYS)
        assertEquals(D094_SELECTED_CAPABILITY_KEYS.size, D094_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "888cedac1e8a2c82aa4235aa0c14bd8059b3db9022f79d07af3886a4e437684f",
            D094_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(99, D095_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D095_SELECTED_CAPABILITY_KEYS.sorted(), D095_SELECTED_CAPABILITY_KEYS)
        assertEquals(D095_SELECTED_CAPABILITY_KEYS.size, D095_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "e87f5192c05027d72b1e4ffc02dc5b606fc017963b093a5e7ff65e6e88589916",
            D095_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(86, D096_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D096_SELECTED_CAPABILITY_KEYS.sorted(), D096_SELECTED_CAPABILITY_KEYS)
        assertEquals(D096_SELECTED_CAPABILITY_KEYS.size, D096_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "49d9c0aaba65280b04c86891a5250f9d14b460474138f22bbf1a68ea3f99a524",
            D096_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(16, D097_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D097_SELECTED_CAPABILITY_KEYS.sorted(), D097_SELECTED_CAPABILITY_KEYS)
        assertEquals(D097_SELECTED_CAPABILITY_KEYS.size, D097_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "9c7ee7cc01795927def9c7963481c30688daa9c752ef88bb1df0cb47897dc2c8",
            D097_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(30, D098_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D098_SELECTED_CAPABILITY_KEYS.sorted(), D098_SELECTED_CAPABILITY_KEYS)
        assertEquals(D098_SELECTED_CAPABILITY_KEYS.size, D098_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "0739cd6fd48e293295fceacb9f430c815e370183fb7756b0802c0e8bb2e09a66",
            D098_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(95, D099_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D099_SELECTED_CAPABILITY_KEYS.sorted(), D099_SELECTED_CAPABILITY_KEYS)
        assertEquals(D099_SELECTED_CAPABILITY_KEYS.size, D099_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "b23b3e4ee3158dfa197cbd0c2a01dbec0ab5fed0ed24ef8a9d858453b7f7d2a4",
            D099_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(103, D099_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(D099_RESIDUAL_CAPABILITY_KEYS.sorted(), D099_RESIDUAL_CAPABILITY_KEYS)
        assertEquals(D099_RESIDUAL_CAPABILITY_KEYS.size, D099_RESIDUAL_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "9e31abc62c8d9467f6c6bbbc968232d4baf0ea235b07c32433c8137d07ddc89b",
            D099_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(34, D100_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D100_SELECTED_CAPABILITY_KEYS.sorted(), D100_SELECTED_CAPABILITY_KEYS)
        assertEquals(D100_SELECTED_CAPABILITY_KEYS.size, D100_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "9056436c25104def413ce181993056a7f8556fb99a253dc7cdf7def4fb28c9df",
            D100_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(69, D100_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(D100_RESIDUAL_CAPABILITY_KEYS.sorted(), D100_RESIDUAL_CAPABILITY_KEYS)
        assertEquals(D100_RESIDUAL_CAPABILITY_KEYS.size, D100_RESIDUAL_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "d988dd9cbb08608eba9baeed54117339d841e214ff541bab6c55a1aa5745de6e",
            D100_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(16, D101_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D101_SELECTED_CAPABILITY_KEYS.sorted(), D101_SELECTED_CAPABILITY_KEYS)
        assertEquals(D101_SELECTED_CAPABILITY_KEYS.size, D101_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "63c2ea93d0f5de29a7a55c71f5933cb7264972eab8c8b671ecb0c5de1bf46971",
            D101_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(53, D101_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(D101_RESIDUAL_CAPABILITY_KEYS.sorted(), D101_RESIDUAL_CAPABILITY_KEYS)
        assertEquals(D101_RESIDUAL_CAPABILITY_KEYS.size, D101_RESIDUAL_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "eecec6ce94c507f538327a97ae39af8ffeaa55e05be76826734150ddf1dd1ada",
            D101_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(33, D102_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D102_SELECTED_CAPABILITY_KEYS.sorted(), D102_SELECTED_CAPABILITY_KEYS)
        assertEquals(D102_SELECTED_CAPABILITY_KEYS.size, D102_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "0c1a7c4b5455d562901f9f0670c481c0f60ff31b764a97da4f2e24cecdab165e",
            D102_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(20, D102_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(D102_RESIDUAL_CAPABILITY_KEYS.sorted(), D102_RESIDUAL_CAPABILITY_KEYS)
        assertEquals(D102_RESIDUAL_CAPABILITY_KEYS.size, D102_RESIDUAL_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "ccbff2236a8ca8372a7eb1f68e7a4cdc3da2b8b68ced43054bac8d315dd97b37",
            D102_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(16, D103_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D103_SELECTED_CAPABILITY_KEYS.sorted(), D103_SELECTED_CAPABILITY_KEYS)
        assertEquals(D103_SELECTED_CAPABILITY_KEYS.size, D103_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "2ee3c3b3f45f6673bd03abb7afd91f5f799a79c05c7d6bb3e98085e9008df276",
            D103_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(4, D103_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(D103_RESIDUAL_CAPABILITY_KEYS.sorted(), D103_RESIDUAL_CAPABILITY_KEYS)
        assertEquals(D103_RESIDUAL_CAPABILITY_KEYS.size, D103_RESIDUAL_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "3bac94763a42300c5638e043f8277dad6940b81e37c996793ebca16152546549",
            D103_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(4, D104_SELECTED_CAPABILITY_KEYS.size)
        assertEquals(D104_SELECTED_CAPABILITY_KEYS.sorted(), D104_SELECTED_CAPABILITY_KEYS)
        assertEquals(D104_SELECTED_CAPABILITY_KEYS.size, D104_SELECTED_CAPABILITY_KEYS.distinct().size)
        assertEquals(
            "3bac94763a42300c5638e043f8277dad6940b81e37c996793ebca16152546549",
            D104_SELECTED_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(0, D104_RESIDUAL_CAPABILITY_KEYS.size)
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            D104_RESIDUAL_CAPABILITY_KEYS.sortedNewlineSha256(),
        )
        assertEquals(556, keys.size)
        assertEquals(keys.sorted(), keys)
        assertEquals(keys.size, keys.distinct().size)
        assertEquals(SELECTED_CAPABILITY_KEYS.sorted(), keys)
        assertEquals(C_ABI_BOOTSTRAP_CAPABILITY_SHA256, keys.sortedNewlineSha256())
        assertEquals(
            "f0b7217e2d302f331829437ce0dd4f54d72ec8503770b6e71f82e68612809651",
            keys.sortedNewlineSha256(),
        )
        assertEquals(0, complement.size)
        assertEquals(D104_RESIDUAL_CAPABILITY_KEYS, complement)
        assertTrue(HOST_CONSTRUCTOR_KEY in keys)
        assertFalse(HOST_CONSTRUCTOR_KEY in complement)
        assertTrue(claims.all { claim ->
            claim.headerReferences.isNotEmpty() && claim.consumerReferences.isNotEmpty() &&
                claim.publicSymbols.isNotEmpty() && claim.nativeTestIds.isNotEmpty()
        })
    }

    @Test
    fun `rejects drift or missing evidence in every exact claim dimension`() {
        val valid = validInputs()
        val firstSpec = cAbiBootstrapClaimSpecs.first()
        val selected = SELECTED_CAPABILITY_KEYS.first()
        val headerReference = firstSpec.headerReferences.first()
        val consumerReference = firstSpec.consumerReferences.first()
        val publicSymbol = firstSpec.publicSymbols.first()
        val nativeTest = firstSpec.nativeTestIds.first()
        val cases = listOf(
            FailureCase("signature mutation", "capability signature drift") { inputs ->
                inputs.copy(canonicalKeys = inputs.canonicalKeys
                    .replace(selected, selected.replace("CodexFailure?", "CodexFailure!!")))
            },
            FailureCase("missing selected key", "exact canonical C ABI capability") { inputs ->
                inputs.copy(canonicalKeys = inputs.canonicalKeys
                    .replace(selected, dummyCapabilityKey(900)))
            },
            FailureCase("stale selected identity", "exact canonical C ABI capability") { inputs ->
                inputs.copy(canonicalKeys = inputs.canonicalKeys.replace(
                    selected,
                    selected.replace("/AgentConversationState.failure|", "/AgentConversationState.removedFailure|"),
                ))
            },
            FailureCase("duplicate canonical identity", "exact canonical C ABI capability") { inputs ->
                inputs.copy(canonicalKeys = inputs.canonicalKeys
                    .replace(SELECTED_CAPABILITY_KEYS.last(), "$selected|duplicate-signature=true"))
            },
            FailureCase("missing public header reference", "Missing C ABI public header reference") { inputs ->
                inputs.copy(headerText = inputs.headerText.withoutLine(headerReference))
            },
            FailureCase("longer header identifier", "Missing C ABI public header reference") { inputs ->
                inputs.copy(headerText = inputs.headerText.replace(headerReference, headerReference + "Extra"))
            },
            FailureCase("missing compiled consumer reference", "Missing compiled C consumer reference") { inputs ->
                inputs.copy(consumerText = inputs.consumerText.withoutLine(consumerReference))
            },
            FailureCase("missing exported symbol", "Missing exported C ABI symbol") { inputs ->
                inputs.copy(exportedSymbols = inputs.exportedSymbols - publicSymbol)
            },
            FailureCase("missing passed Native test", "Missing passed Native C ABI test") { inputs ->
                inputs.copy(passedNativeTestIds = inputs.passedNativeTestIds - nativeTest)
            },
            FailureCase("duplicate claim identity", "claim specifications are missing or duplicated") { inputs ->
                inputs.copy(claimSpecs = inputs.claimSpecs.dropLast(1) + inputs.claimSpecs.first())
            },
            FailureCase("duplicate spec evidence", "empty or duplicate evidence") { inputs ->
                inputs.copy(claimSpecs = inputs.claimSpecs.mapIndexed { index, spec ->
                    if (index == 0) {
                        spec.copy(headerReferences = spec.headerReferences + spec.headerReferences.first())
                    } else {
                        spec
                    }
                })
            },
        )

        cases.forEach { case ->
            val failure = assertFailsWith<IllegalStateException>(case.name) {
                case.mutate(valid).derive()
            }
            assertTrue(case.expectedMessage in failure.message.orEmpty(),
                "${case.name}: ${failure.message}")
        }
    }

    @Test
    fun `canonical prerequisite failure deletes stale C bootstrap evidence first`() {
        val root = createTempDirectory("c-abi-bootstrap-preflight").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("""
                rootProject.name = "c-abi-bootstrap-preflight"
                include(":core", ":desktop")
            """.trimIndent())
            root.resolve("core").mkdirs()
            root.resolve("core/build.gradle.kts").writeText("""
                plugins { base }
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs")
                tasks.configureEach {
                    if (name !in setOf(
                            preflight.name,
                            "invalidateCodexAgentCAbiBootstrapEvidence",
                        )
                    ) {
                        mustRunAfter(preflight)
                    }
                }
                val failingPrerequisite = tasks.register("failingCanonicalCoverage") {
                    doLast { throw GradleException("intentional canonical coverage failure") }
                }
                tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(preflight, failingPrerequisite)
                }
            """.trimIndent())
            root.resolve("desktop").mkdirs()
            root.resolve("desktop/build.gradle.kts").writeText("""
                plugins { base }
                val evidence = layout.buildDirectory.file(
                    "reports/cross-language-api/c-abi/bootstrap-evidence.json",
                )
                val consumers = layout.buildDirectory.dir("c-abi-bootstrap/consumers")
                val preflight = tasks.register<Delete>("invalidateCodexAgentCAbiBootstrapEvidence") {
                    delete(evidence, consumers)
                }
                tasks.configureEach {
                    if (name !in setOf(
                            preflight.name,
                            "invalidateJavaScriptTypeScriptBindingParityOutput",
                        )
                    ) {
                        mustRunAfter(preflight)
                    }
                }
                project(":core").tasks.matching {
                    it.name == "invalidateCrossLanguageBindingParityOutputs"
                }.configureEach {
                    dependsOn(preflight)
                }
                val link = tasks.register("linkReleaseSharedMacosArm64")
                val nativeTest = tasks.register("macosArm64Test")
                tasks.register("generateCodexAgentCAbiBootstrapEvidence") {
                    dependsOn(
                        preflight,
                        ":core:verifyCrossLanguageApiCoverage",
                        link,
                        nativeTest,
                    )
                }
            """.trimIndent())
            val staleEvidence = root.resolve(
                "desktop/build/reports/cross-language-api/c-abi/bootstrap-evidence.json",
            ).apply {
                parentFile.mkdirs()
                writeText("stale observed evidence")
            }
            val staleConsumer = root.resolve(
                "desktop/build/c-abi-bootstrap/consumers/stale-consumer",
            ).apply {
                parentFile.mkdirs()
                writeText("stale compiler state")
            }

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(":desktop:generateCodexAgentCAbiBootstrapEvidence", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":desktop:invalidateCodexAgentCAbiBootstrapEvidence")?.outcome,
                result.output,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":core:failingCanonicalCoverage")?.outcome)
            assertTrue("intentional canonical coverage failure" in result.output)
            assertFalse(staleEvidence.exists())
            assertFalse(staleConsumer.exists())

            val wiring = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
            val generator = wiring.substringAfter(
                "tasks.register<GenerateCAbiBootstrapEvidenceTask>(\"generateCodexAgentCAbiBootstrapEvidence\")",
            ).substringBefore("\n}\n\nval nodeRuntimeEvidenceRunnerArchive")
            listOf(
                "reports/cross-language-api/c-abi/bootstrap-evidence.json",
                "c-abi-bootstrap/consumers",
                "tasks.register<Delete>(",
                "delete(cAbiBootstrapEvidenceFile, cAbiBootstrapConsumerOutput)",
                "mustRunAfter(invalidateCAbiBootstrapEvidence)",
                "rootProject.findProject(\":codex-agent-core\")",
                "dependsOn(invalidateCAbiBootstrapEvidence)",
            ).forEach { contract ->
                assertTrue(contract in wiring, "Missing C bootstrap preflight contract: $contract")
            }
            listOf(
                "invalidateCAbiBootstrapEvidence",
                "\":codex-agent-core:verifyCrossLanguageApiCoverage\"",
                "\"linkReleaseSharedMacosArm64\"",
                "\"macosArm64Test\"",
                "canonical-api.json",
                "canonical-coverage.json",
                "native/c-api/include/codex_agent.h",
                "src/nativeInterop/cinterop/codex_agent_c.def",
                "native/c-api/exports/macos.exports",
                "native/c-api/consumer/codex_agent_abi_smoke.c",
                "native/c-api/consumer/codex_agent_header_smoke.cpp",
                "native/c-api/consumer/codex_agent_lifecycle_compile.c",
                "native/c-api/consumer/codex_agent_lifecycle_compile.cpp",
                "native/c-api/consumer/codex_agent_conversation_values_compile.c",
                "native/c-api/consumer/codex_agent_configuration_values_compile.c",
                "native/c-api/consumer/codex_agent_resource_values_compile.c",
                "native/c-api/consumer/codex_agent_ordinary_enums_compile.c",
                "native/c-api/consumer/codex_agent_form_hook_values_compile.c",
                "native/c-api/consumer/codex_agent_invocation_auth_values_compile.c",
                "native/c-api/consumer/codex_agent_progress_list_values_compile.c",
                "native/c-api/consumer/codex_agent_resource_list_values_compile.c",
                "native/c-api/consumer/codex_agent_list_leaf_values_compile.c",
                "native/c-api/consumer/codex_agent_mcp_transport_values_compile.c",
                "native/c-api/consumer/codex_agent_integration_values_compile.c",
                "native/c-api/consumer/codex_agent_mcp_server_values_compile.c",
                "native/c-api/consumer/codex_agent_mcp_server_configuration_values_compile.c",
                "native/c-api/consumer/codex_agent_integration_mcp_values_compile.c",
                "native/c-api/consumer/codex_agent_conversation_aggregate_values_compile.c",
                "native/c-api/consumer/codex_agent_elicitation_interaction_values_compile.c",
                "native/c-api/consumer/codex_agent_hook_catalog_values_compile.c",
                "native/c-api/consumer/codex_agent_integration_state_values_compile.c",
                "native/c-api/consumer/codex_agent_authentication_configuration_values_compile.c",
                "native/c-api/consumer/codex_agent_elicitation_behavior_values_compile.c",
                "native/c-api/consumer/codex_agent_sealed_base_property_values_compile.c",
                "native/c-api/consumer/codex_agent_root_value_accessors_compile.c",
                "native/c-api/consumer/codex_agent_suspend_operations_compile.c",
                "native/c-api/consumer/codex_agent_state_flows_compile.c",
                "bin/macosArm64/releaseShared/libcodex_agent.dylib",
                "bin/macosArm64/releaseShared/libcodex_agent_api.h",
                "bin/macosArm64/debugTest/test.kexe",
                "test-results/macosArm64Test",
                "consumerOutputDirectory.set(cAbiBootstrapConsumerOutput)",
                "evidenceFile.set(cAbiBootstrapEvidenceFile)",
            ).forEach { contract ->
                assertTrue(contract in generator, "Missing C bootstrap generator contract: $contract")
            }
            listOf(
                "ordinaryEnumsCConsumer" to "codex_agent_ordinary_enums_compile.c",
                "formHookValuesCConsumer" to "codex_agent_form_hook_values_compile.c",
                "invocationAuthValuesCConsumer" to "codex_agent_invocation_auth_values_compile.c",
                "progressListValuesCConsumer" to "codex_agent_progress_list_values_compile.c",
                "resourceListValuesCConsumer" to "codex_agent_resource_list_values_compile.c",
                "listLeafValuesCConsumer" to "codex_agent_list_leaf_values_compile.c",
                "mcpTransportValuesCConsumer" to "codex_agent_mcp_transport_values_compile.c",
                "integrationValuesCConsumer" to "codex_agent_integration_values_compile.c",
                "mcpServerValuesCConsumer" to "codex_agent_mcp_server_values_compile.c",
                "mcpServerConfigurationValuesCConsumer" to
                    "codex_agent_mcp_server_configuration_values_compile.c",
                "integrationMcpValuesCConsumer" to "codex_agent_integration_mcp_values_compile.c",
                "conversationAggregateValuesCConsumer" to
                    "codex_agent_conversation_aggregate_values_compile.c",
                "elicitationInteractionValuesCConsumer" to
                    "codex_agent_elicitation_interaction_values_compile.c",
                "hookCatalogValuesCConsumer" to "codex_agent_hook_catalog_values_compile.c",
                "integrationStateValuesCConsumer" to "codex_agent_integration_state_values_compile.c",
                "authenticationConfigurationValuesCConsumer" to
                    "codex_agent_authentication_configuration_values_compile.c",
                "elicitationBehaviorValuesCConsumer" to
                    "codex_agent_elicitation_behavior_values_compile.c",
                "sealedBasePropertyValuesCConsumer" to
                    "codex_agent_sealed_base_property_values_compile.c",
                "rootValueAccessorsCConsumer" to "codex_agent_root_value_accessors_compile.c",
                "serviceHandlesCConsumer" to "codex_agent_service_handles_compile.c",
                "suspendOperationsCConsumer" to "codex_agent_suspend_operations_compile.c",
                "stateFlowsCConsumer" to "codex_agent_state_flows_compile.c",
                "interactionIdentityCConsumer" to "codex_agent_interaction_identity_compile.c",
            ).forEach { (property, fixture) ->
                val assignment = generator.substringAfter("$property.set(").substringBefore("\n    )")
                assertTrue(fixture in assignment, "C bootstrap $property is not wired to $fixture")
            }
            val producer = File("src/main/kotlin/CrossLanguageCAbiBootstrapEvidence.kt").readText()
            listOf(
                "\"c11-ordinary-enums\"",
                "\"c11-form-hook-values\"",
                "\"c11-invocation-auth-values\"",
                "\"c11-progress-list-values\"",
                "\"c11-resource-list-values\"",
                "\"c11-list-leaf-values\"",
                "\"c11-mcp-transport-values\"",
                "\"c11-integration-values\"",
                "\"c11-mcp-server-values\"",
                "\"c11-mcp-server-configuration-values\"",
                "\"c11-integration-mcp-values\"",
                "\"c11-conversation-aggregate-values\"",
                "\"c11-elicitation-interaction-values\"",
                "\"c11-hook-catalog-values\"",
                "\"c11-integration-state-values\"",
                "\"c11-authentication-configuration-values\"",
                "\"c11-elicitation-behavior-values\"",
                "\"c11-sealed-base-property-values\"",
                "\"c11-root-value-accessors\"",
                "\"c11-service-handles\"",
                "\"c11-suspend-operations\"",
                "\"c11-state-flows\"",
                "\"c11-interaction-identity\"",
                "C_ELICITATION_BEHAVIOR_RECLAMATION_TEST in passedTests",
                "C_HOST_FACTORY_INVALID_TEST in passedTests",
                "rows.size == 777",
                "put(\"milestone\", JsonPrimitive(\"D104\"))",
            ).forEach { contract ->
                assertTrue(contract in producer, "Missing D104 C bootstrap producer contract: $contract")
            }
            val coreWiring = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
            assertTrue("\"invalidateCodexAgentCAbiBootstrapEvidence\"" in coreWiring)
        } finally {
            root.deleteRecursively()
        }
    }

    private data class FailureCase(
        val name: String,
        val expectedMessage: String,
        val mutate: (Inputs) -> Inputs,
    )

    private data class Inputs(
        val canonicalKeys: List<String>,
        val headerText: String,
        val consumerText: String,
        val exportedSymbols: Set<String>,
        val passedNativeTestIds: Set<String>,
        val claimSpecs: List<CAbiBootstrapClaimSpec>,
    ) {
        fun derive(): List<CAbiBootstrapClaim> = deriveCAbiBootstrapClaims(
            canonicalKeys = canonicalKeys,
            headerText = headerText,
            consumerText = consumerText,
            exportedSymbols = exportedSymbols,
            passedNativeTestIds = passedNativeTestIds,
            claimSpecs = claimSpecs,
        )
    }

    private fun validInputs(): Inputs = Inputs(
        canonicalKeys = (
            SELECTED_CAPABILITY_KEYS + D104_RESIDUAL_CAPABILITY_KEYS
        ).sorted(),
        headerText = cAbiBootstrapClaimSpecs.flatMap(CAbiBootstrapClaimSpec::headerReferences)
            .distinct().joinToString("\n"),
        consumerText = cAbiBootstrapClaimSpecs.flatMap(CAbiBootstrapClaimSpec::consumerReferences)
            .distinct().joinToString("\n"),
        exportedSymbols = cAbiBootstrapClaimSpecs.flatMap(CAbiBootstrapClaimSpec::publicSymbols).toSet(),
        passedNativeTestIds = cAbiBootstrapClaimSpecs.flatMap(CAbiBootstrapClaimSpec::nativeTestIds).toSet(),
        claimSpecs = cAbiBootstrapClaimSpecs,
    )

    private fun List<String>.replace(old: String, new: String): List<String> =
        map { if (it == old) new else it }.sorted()

    private fun String.withoutLine(line: String): String =
        lineSequence().filterNot(line::equals).joinToString("\n")

    private fun List<String>.sortedNewlineSha256(): String = MessageDigest.getInstance("SHA-256")
        .digest(sorted().joinToString(separator = "", transform = { "$it\n" }).encodeToByteArray())
        .joinToString("") { byte -> "%02x".format(byte) }

    private companion object {
        val D093_SELECTED_CAPABILITY_KEYS = listOf(
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure?",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.CANCELLING_TURN|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.CLOSED|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.FAILED|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.NEW|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.OPENING|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.READY|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.RELOADING|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.RUNNING_TURN|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus.STARTING_TURN|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.conversations|{}conversations[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexConversations!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.open|open(io.github.codex_agent_labs.codexmobile.agent.ConversationId?;io.github.codex_agent_labs.codexmobile.agent.AgentConversationSettings){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexConversation!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings!!:default=true:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.active|{}active[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/CodexConversation?>!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.cancelTurn|cancelTurn(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.close|close(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.send|send(kotlin.String){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConversationState!!>!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexFailure.code|{}code[0]|propertyKind=VAL|type=kotlin/String!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexFailure.isRecoverable|{}isRecoverable[0]|propertyKind=VAL|type=kotlin/Boolean!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexFailure.message|{}message[0]|propertyKind=VAL|type=kotlin/String!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Closed|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Closed|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace?;io.github.codex_agent_labs.codexmobile.agent.CodexFailure){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace?:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.New|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.New|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Ready|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Ready.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexAgent){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Ready|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAgent!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Ready|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Ready.agent|{}agent[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAgent!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Restoring|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Restoring|null[0]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution.SelectionRequired){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.close|close(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.selectWorkspace|selectWorkspace(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelection!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.lifecycleState|{}lifecycleState[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/CodexHostState!!>!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPathWorkspaceSelection|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPathWorkspaceSelection.<init>|<init>(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexPathWorkspaceSelection|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPathWorkspaceSelection|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPathWorkspaceSelection.path|{}path[0]|propertyKind=VAL|type=kotlin/String!!",
        )

        val D094_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset.ASK_ME|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset.AUTO_REVIEW|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset.NEVER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset.STRICT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCapability|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCapability.WEB_SEARCH|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCapability|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCapability.displayLabel|{}displayLabel[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCapability|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCapability.icon|{}icon[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCapability|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCapability.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCapability|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCapability.promptLabel|{}promptLabel[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String;kotlin.Long){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Long!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary.updatedAtEpochSeconds|{}updatedAtEpochSeconds[0]|propertyKind=VAL|type=kotlin/Long!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue.<init>|<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationReason){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue.fieldName|{}fieldName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue.reason|{}reason[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.ABOVE_MAXIMUM|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.BELOW_MINIMUM|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.DUPLICATE_SELECTION|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.INVALID_FORMAT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.INVALID_SELECTION|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.INVALID_TYPE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.MISSING_REQUIRED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.NON_FINITE_NUMBER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.NON_INTEGER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationReason.UNKNOWN_FIELD|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption.<init>|<init>(kotlin.String;kotlin.String;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption.description|{}description[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormOption.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource.LOCAL|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource.REMOTE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable.<init>|<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentSource?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable.source|{}source[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration.<init>|<init>(kotlin.String?;kotlin.Int?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration|suspend=false|parameters=[REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/Int?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration.callbackPort|{}callbackPort[0]|propertyKind=VAL|type=kotlin/Int?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration.clientId|{}clientId[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval.APPROVE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval.AUTO|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval.PROMPT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval.WRITES|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolApproval?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration.approval|{}approval[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus.COMPLETED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus.IN_PROGRESS|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus.PENDING|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep.<init>|<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentPlanStepStatus){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStepStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep.text|{}text[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String?;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.marketplaceName|{}marketplaceName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.marketplacePath|{}marketplacePath[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.remotePluginId|{}remotePluginId[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference.uri|{}uri[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill.<init>|<init>(kotlin.String;kotlin.String;kotlin.Boolean;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill.path|{}path[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier.<init>|<init>(kotlin.String;kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk.<init>|<init>(kotlin.String;kotlin.Long?;kotlin.Long){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Long?:default=false:vararg=false,REGULAR:kotlin/Long!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk.content|{}content[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk.nextOffset|{}nextOffset[0]|propertyKind=VAL|type=kotlin/Long?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk.totalBytes|{}totalBytes[0]|propertyKind=VAL|type=kotlin/Long!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.ADMIN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.PLUGIN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.REPO|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.SYSTEM|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.USER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexFailure.<init>|<init>(kotlin.String;kotlin.String;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.Available|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.Available.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.Available|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.Available|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.Available.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired.message|{}message[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired.reason|{}reason[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason.ACCESS_REVOKED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason.INVALID_SELECTION|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason.NOT_FOUND|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceSelectionReason.NOT_SELECTED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace.<init>|<init>(kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace.path|{}path[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/ConversationId|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/ConversationId.<init>|<init>(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/ConversationId|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/ConversationId|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/ConversationId.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D095_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision.ACCEPT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision.DECLINE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus.AUTHENTICATED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus.AUTHENTICATING|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus.SIGNED_OUT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness.FRESH_CACHE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness.LIVE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness.STALE_CACHE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode.DEFAULT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode.PLAN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction.ACCEPT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction.CANCEL|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction.DECLINE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.BOOLEAN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.INTEGER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.MULTI_SELECT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.NUMBER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.SINGLE_SELECT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType.STRING|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat.DATE_TIME|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat.DATE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat.EMAIL|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat.URI|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.BooleanValue|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.BooleanValue.<init>|<init>(kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.BooleanValue|suspend=false|parameters=[REGULAR:kotlin/Boolean!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.BooleanValue|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.BooleanValue.value|{}value[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Number|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Number.<init>|<init>(kotlin.Double){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Number|suspend=false|parameters=[REGULAR:kotlin/Double!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Number|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Number.value|{}value[0]|propertyKind=VAL|type=kotlin/Double!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Text|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Text.<init>|<init>(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Text|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Text|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.Text.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Agent|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Agent|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command.<init>|<init>(kotlin.String;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command.command|{}command[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Command.isAsync|{}isAsync[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool.<init>|<init>(kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool.server|{}server[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.McpTool.tool|{}tool[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Prompt|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler.Prompt|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus.BLOCKED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus.COMPLETED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus.FAILED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus.RUNNING|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus.STOPPED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus.MANAGED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus.MODIFIED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus.TRUSTED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus.UNTRUSTED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope.User|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope.Workspace|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus.AUTHORIZED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus.FAILED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus.IDLE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus.STARTING|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin.<init>|<init>(kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin.key|{}key[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Plugin.uri|{}uri[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill.<init>|<init>(kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill.key|{}key[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.Skill.path|{}path[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus.BEARER_TOKEN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus.NOT_LOGGED_IN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus.OAUTH|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus.UNKNOWN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus.UNSUPPORTED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication.CHAT_GPT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication.OAUTH|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface.CODE_MODE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface.DEFERRED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface.DIRECT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole.ASSISTANT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole.USER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval.<init>|<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval.details|{}details[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval.requestId|{}requestId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy.ON_INSTALL|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy.ON_USE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy.AVAILABLE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy.INSTALLED_BY_DEFAULT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy.NOT_AVAILABLE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResolution|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResolution.Default|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResolution|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResolution.First|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResolution|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResolution.Preferred|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin.MANAGED|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin.PLUGIN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin.UNKNOWN|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin.USER|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin.WORKSPACE|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity.RUNNING_COMMAND|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity.WRITING_FILES|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ApiKey|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ApiKey.<init>|<init>(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ApiKey|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ApiKey|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ApiKey.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ChatGptBrowser|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ChatGptBrowser|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ChatGptDeviceCode|kind=object|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod.ChatGptDeviceCode|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose.CHAT_GPT|null[0]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose|kind=enum-entry|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose.EXTERNAL|null[0]
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D096_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String?;kotlin.Boolean;kotlin.Boolean;kotlin.collections.List<kotlin.String>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.installUrl|{}installUrl[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.isAccessible|{}isAccessible[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConnector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConnector.pluginNames|{}pluginNames[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation.<init>|<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationIssue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation.isValid|{}isValid[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation.issues|{}issues[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidationIssue!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.TextList|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.TextList.<init>|<init>(kotlin.collections.List<kotlin.String>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.TextList|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.TextList|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue.TextList.value|{}value[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentHookRunStatus;kotlin.String?;kotlin.collections.List<kotlin.String>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.details|{}details[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.eventName|{}eventName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.handlerType|{}handlerType[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.statusMessage|{}statusMessage[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentHookRunStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.collections.List<kotlin.String>;kotlin.String;kotlin.Boolean;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier>;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentModel|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier!!>!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.defaultEffort|{}defaultEffort[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.defaultServiceTier|{}defaultServiceTier[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.isDefault|{}isDefault[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.serviceTiers|{}serviceTiers[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentModel|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentModel.supportedEfforts|{}supportedEfforts[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress.<init>|<init>(kotlin.String?;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPlanStep>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress|suspend=false|parameters=[REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress.explanation|{}explanation[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress.steps|{}steps[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPlanStep!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog.<init>|<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary>;kotlin.collections.List<kotlin.String>;io.github.codex_agent_labs.codexmobile.agent.AgentCatalogFreshness){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary!!>!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog.errors|{}errors[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog.freshness|{}freshness[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentCatalogFreshness!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog.plugins|{}plugins[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary;kotlin.String;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPluginSkill>;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentConnector>;kotlin.collections.List<kotlin.String>;kotlin.Int){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill!!>!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=false:vararg=false,REGULAR:kotlin/Int!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.connectors|{}connectors[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.hookCount|{}hookCount[0]|propertyKind=VAL|type=kotlin/Int!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.mcpServers|{}mcpServers[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.skills|{}skills[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPluginSkill!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail.summary|{}summary[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentConnector>;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult.authPolicy|{}authPolicy[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult.connectorsNeedingAuthentication|{}connectorsNeedingAuthentication[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult.message|{}message[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference;kotlin.String;kotlin.String;kotlin.Boolean;kotlin.Boolean;io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallPolicy;io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy;kotlin.Boolean;kotlin.collections.List<kotlin.String>;kotlin.String?;kotlin.String?;kotlin.String?;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.authPolicy|{}authPolicy[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPluginAuthPolicy!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.brandColor|{}brandColor[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.capabilities|{}capabilities[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.installPolicy|{}installPolicy[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallPolicy!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.isInstalled|{}isInstalled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.privacyPolicyUrl|{}privacyPolicyUrl[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.reference|{}reference[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.termsOfServiceUrl|{}termsOfServiceUrl[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPluginSummary.websiteUrl|{}websiteUrl[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog.<init>|<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentSkill>;kotlin.collections.List<kotlin.String>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!>!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog.errors|{}errors[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog.skills|{}skills[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentSkillScope;kotlin.Boolean;kotlin.String?;kotlin.collections.List<kotlin.String>;kotlin.Boolean;io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.brandColor|{}brandColor[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.canUninstall|{}canUninstall[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.dependencies|{}dependencies[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.description|{}description[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.origin|{}origin[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.path|{}path[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentSkill|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentSkill.scope|{}scope[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentSkillScope!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.<init>|<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentPlanProgress?;kotlin.String;kotlin.Int?;io.github.codex_agent_labs.codexmobile.agent.AgentWorkActivity?;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentHookActivity>;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|suspend=false|parameters=[REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress?:default=true:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/Int?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity!!>!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.commentary|{}commentary[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.hookActivities|{}hookActivities[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentHookActivity!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.isTruncated|{}isTruncated[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.planProgress|{}planProgress[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentPlanProgress?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.plan|{}plan[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.reasoning|{}reasoning[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.shellExitCode|{}shellExitCode[0]|propertyKind=VAL|type=kotlin/Int?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.shellOutput|{}shellOutput[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.text|{}text[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress.workActivity|{}workActivity[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentWorkActivity?
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D097_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentConnector){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector.connector|{}connector[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.Connector.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.<init>|<init>(kotlin.String;kotlin.String?;kotlin.collections.Map<kotlin.String,kotlin.String>?;kotlin.collections.Map<kotlin.String,kotlin.String>?;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.bearerTokenEnvironmentVariable|{}bearerTokenEnvironmentVariable[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.environmentHeaders|{}environmentHeaders[0]|propertyKind=VAL|type=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.headersHelper|{}headersHelper[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.headers|{}headers[0]|propertyKind=VAL|type=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Http.url|{}url[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.<init>|<init>(kotlin.String;kotlin.collections.List<kotlin.String>;kotlin.String?;kotlin.collections.Map<kotlin.String,kotlin.String>?;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentVariable>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.arguments|{}arguments[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.command|{}command[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.environment|{}environment[0]|propertyKind=VAL|type=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.forwardedEnvironment|{}forwardedEnvironment[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentVariable!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport.Stdio.workingDirectory|{}workingDirectory[0]|propertyKind=VAL|type=kotlin/String?
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D098_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.McpServer.server|{}server[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.<init>|<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentMcpTransport;io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthentication?;kotlin.String;kotlin.Boolean;kotlin.Boolean;kotlin.Boolean;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolExposureSurface>?;kotlin.Double?;kotlin.Double?;io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolApproval?;kotlin.collections.List<kotlin.String>?;kotlin.collections.List<kotlin.String>?;kotlin.collections.List<kotlin.String>?;io.github.codex_agent_labs.codexmobile.agent.AgentMcpOauthConfiguration?;kotlin.String?;kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolConfiguration>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication?:default=true:vararg=false,REGULAR:kotlin/String!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface!!>?:default=true:vararg=false,REGULAR:kotlin/Double?:default=true:vararg=false,REGULAR:kotlin/Double?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.authentication|{}authentication[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthentication?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.defaultToolApproval|{}defaultToolApproval[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolApproval?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.disabledTools|{}disabledTools[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.enabledTools|{}enabledTools[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.environmentId|{}environmentId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.isRequired|{}isRequired[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.oauthResource|{}oauthResource[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.oauth|{}oauth[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpOauthConfiguration?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.omitToolsFrom|{}omitToolsFrom[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolExposureSurface!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.scopes|{}scopes[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.startupTimeoutSeconds|{}startupTimeoutSeconds[0]|propertyKind=VAL|type=kotlin/Double?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.supportsParallelToolCalls|{}supportsParallelToolCalls[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.toolTimeoutSeconds|{}toolTimeoutSeconds[0]|propertyKind=VAL|type=kotlin/Double?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.tools|{}tools[0]|propertyKind=VAL|type=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpToolConfiguration!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration.transport|{}transport[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpTransport!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.<init>|<init>(kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthStatus;io.github.codex_agent_labs.codexmobile.agent.AgentMcpServerConfiguration?;io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.authStatus|{}authStatus[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpAuthStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.canRemove|{}canRemove[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.configuration|{}configuration[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.isAuthorized|{}isAuthorized[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer.origin|{}origin[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D099_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus;io.github.codex_agent_labs.codexmobile.agent.ConversationId?;io.github.codex_agent_labs.codexmobile.agent.AgentConversation?;io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress;kotlin.String?;kotlin.String?;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.CodexFailure?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentConversationStatus!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentConversation?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.canCancelTurn|{}canCancelTurn[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.canReload|{}canReload[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.canStartTurn|{}canStartTurn[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.conversation|{}conversation[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentConversation?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.effort|{}effort[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.model|{}model[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.serviceTier|{}serviceTier[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationState.turnProgress|{}turnProgress[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversation|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversation.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentConversationSummary;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentMessage>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversation|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMessage!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversation.messages|{}messages[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMessage!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversation.summary|{}summary[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentElicitationAction;kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentFormValue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction!!:default=false:vararg=false,REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.action|{}action[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationAction!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.content|{}content[0]|propertyKind=VAL|type=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.<init>|<init>(kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentFormField>?;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormField!!>?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.form|{}form[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormField!!>?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.message|{}message[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.requestId|{}requestId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.serverName|{}serverName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.url|{}url[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.<init>|<init>(kotlin.String;kotlin.String;kotlin.String?;kotlin.Boolean;io.github.codex_agent_labs.codexmobile.agent.AgentFormFieldType;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentFormOption>;io.github.codex_agent_labs.codexmobile.agent.AgentFormValue?;kotlin.Double?;kotlin.Double?;io.github.codex_agent_labs.codexmobile.agent.AgentFormStringFormat?;kotlin.Long?;kotlin.Long?;kotlin.Long?;kotlin.Long?;kotlin.Boolean;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormOption!!>!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue?:default=true:vararg=false,REGULAR:kotlin/Double?:default=true:vararg=false,REGULAR:kotlin/Double?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat?:default=true:vararg=false,REGULAR:kotlin/Long?:default=true:vararg=false,REGULAR:kotlin/Long?:default=true:vararg=false,REGULAR:kotlin/Long?:default=true:vararg=false,REGULAR:kotlin/Long?:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.allowsOther|{}allowsOther[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.defaultValue|{}defaultValue[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentFormValue?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.description|{}description[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.format|{}format[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentFormStringFormat?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.isRequired|{}isRequired[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.isSecret|{}isSecret[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.maximumLength|{}maximumLength[0]|propertyKind=VAL|type=kotlin/Long?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.maximumSelections|{}maximumSelections[0]|propertyKind=VAL|type=kotlin/Long?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.maximum|{}maximum[0]|propertyKind=VAL|type=kotlin/Double?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.minimumLength|{}minimumLength[0]|propertyKind=VAL|type=kotlin/Long?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.minimumSelections|{}minimumSelections[0]|propertyKind=VAL|type=kotlin/Long?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.minimum|{}minimum[0]|propertyKind=VAL|type=kotlin/Double?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.options|{}options[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormOption!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.type|{}type[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentFormFieldType!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog.<init>|<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentHook>;kotlin.collections.List<kotlin.String>;kotlin.collections.List<kotlin.String>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!>!!:default=false:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog.errors|{}errors[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog.hooks|{}hooks[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog.warnings|{}warnings[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.<init>|<init>(kotlin.String;kotlin.String;kotlin.Boolean;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler;kotlin.Boolean;kotlin.String;kotlin.String;kotlin.Long;io.github.codex_agent_labs.codexmobile.agent.AgentHookTrustStatus;kotlin.String?;kotlin.String?;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.AgentResourceOrigin;kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHook|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler!!:default=false:vararg=false,REGULAR:kotlin/Boolean!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Long!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!:default=true:vararg=false,REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.canTrust|{}canTrust[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.canUninstall|{}canUninstall[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.currentHash|{}currentHash[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.eventName|{}eventName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.handler|{}handler[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentHookHandler!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.isEnabled|{}isEnabled[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.isManaged|{}isManaged[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.key|{}key[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.matcher|{}matcher[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.origin|{}origin[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentResourceOrigin!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.pluginId|{}pluginId[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.sourcePath|{}sourcePath[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.source|{}source[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.statusMessage|{}statusMessage[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.timeoutSeconds|{}timeoutSeconds[0]|propertyKind=VAL|type=kotlin/Long!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentHook|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentHook.trustStatus|{}trustStatus[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentHookTrustStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentIntegrationAuthorizationStatus;io.github.codex_agent_labs.codexmobile.agent.AgentIntegration?;io.github.codex_agent_labs.codexmobile.agent.CodexFailure?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentIntegration?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState.target|{}target[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.<init>|<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPendingInteraction>;kotlin.collections.Set<kotlin.String>;io.github.codex_agent_labs.codexmobile.agent.CodexFailure?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|suspend=false|parameters=[REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction!!>!!:default=true:vararg=false,REGULAR:kotlin.collections/Set<INVARIANT:kotlin/String!!>!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.pending|{}pending[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.resolvingRequestIds|{}resolvingRequestIds[0]|propertyKind=VAL|type=kotlin.collections/Set<INVARIANT:kotlin/String!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.<init>|<init>(kotlin.String;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.AgentMessageRole;kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentCollaborationMode;kotlin.String?;kotlin.String?;kotlin.String?;kotlin.Int?;kotlin.collections.Set<io.github.codex_agent_labs.codexmobile.agent.AgentCapability>;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentInvocation>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String?:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/Int?:default=true:vararg=false,REGULAR:kotlin.collections/Set<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentCapability!!>!!:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInvocation!!>!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.capabilities|{}capabilities[0]|propertyKind=VAL|type=kotlin.collections/Set<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentCapability!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.clientMessageId|{}clientMessageId[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.collaborationMode|{}collaborationMode[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.exitCode|{}exitCode[0]|propertyKind=VAL|type=kotlin/Int?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.invocations|{}invocations[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInvocation!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.plan|{}plan[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.reasoning|{}reasoning[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.role|{}role[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.shellCommand|{}shellCommand[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentMessage|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentMessage.text|{}text[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentElicitation){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitation!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation.elicitation|{}elicitation[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation.requestId|{}requestId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.<init>|<init>(kotlin.String;kotlin.String?;kotlin.String?;kotlin.String?;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset;kotlin.collections.Set<io.github.codex_agent_labs.codexmobile.agent.AgentCapability>;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentInvocation>;io.github.codex_agent_labs.codexmobile.agent.AgentCollaborationMode){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!:default=true:vararg=false,REGULAR:kotlin.collections/Set<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentCapability!!>!!:default=true:vararg=false,REGULAR:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInvocation!!>!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.approvalPreset|{}approvalPreset[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.capabilities|{}capabilities[0]|propertyKind=VAL|type=kotlin.collections/Set<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentCapability!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.clientMessageId|{}clientMessageId[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.collaborationMode|{}collaborationMode[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.effort|{}effort[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.invocations|{}invocations[0]|propertyKind=VAL|type=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInvocation!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.model|{}model[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.prompt|{}prompt[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest.serviceTier|{}serviceTier[0]|propertyKind=VAL|type=kotlin/String?
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D099_RESIDUAL_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationStatus;io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl?;io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl?;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.CodexFailure?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.deviceUserCode|{}deviceUserCode[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.deviceVerificationUrl|{}deviceVerificationUrl[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.pendingSignInUrl|{}pendingSignInUrl[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.approvalPreset|{}approvalPreset[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.serviceTier|{}serviceTier[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion.cancel|cancel(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion.decline|decline(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.accepts|accepts(io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse){}[0]|return=kotlin/Boolean!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.accept|accept(kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentFormValue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.initialValues|initialValues(){}[0]|return=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.validate|validate(kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentFormValue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation!!|suspend=false|parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.accepts|accepts(io.github.codex_agent_labs.codexmobile.agent.AgentFormValue?){}[0]|return=kotlin/Boolean!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue?:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.isResolving|isResolving(io.github.codex_agent_labs.codexmobile.agent.AgentPendingInteraction){}[0]|return=kotlin/Boolean!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.pendingFor|pendingFor(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction!!>!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.key|{}key[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction.requestId|{}requestId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.authentication|{}authentication[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.connectors|{}connectors[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.hooks|{}hooks[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexHooks!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.integrationAuthorization|{}integrationAuthorization[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.interactions|{}interactions[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.mcpServers|{}mcpServers[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.models|{}models[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexModels!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.plugins|{}plugins[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.skills|{}skills[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexSkills!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.authenticate|authenticate(io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.cancel|cancel(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.signOut|signOut(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.isAuthenticated|{}isAuthenticated[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.isAuthenticating|{}isAuthenticating[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion.chatGpt|chatGpt(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl!!|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion.external|external(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl!!|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.purpose|{}purpose[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.<init>|<init>(kotlin.String;kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.version|{}version[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors.list|list(kotlin.Boolean){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.delete|delete(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.read|read(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversation!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.rename|rename(io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.reload|reload(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.runShellCommand|runShellCommand(kotlin.String){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.send|send(io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.activeTurnProgress|{}activeTurnProgress[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress?>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canCancelTurn|{}canCancelTurn[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canReload|{}canReload[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canRunShellCommand|{}canRunShellCommand[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canStartTurn|{}canStartTurn[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.currentMessages|{}currentMessages[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMessage!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.isTurnActive|{}isTurnActive[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.install|install(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHook!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.list|list(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.trust|trust(io.github.codex_agent_labs.codexmobile.agent.AgentHook){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentHook){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired.requirement|{}requirement[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexPlatform;io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHost|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexPlatform!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.start|start(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.authorize|authorize(0:0){0§<io.github.codex_agent_labs.codexmobile.agent.AgentIntegration>}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:^A1:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.cancel|cancel(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.active|{}active[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentIntegration?>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.isAuthorizing|{}isAuthorizing[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.openUrl|openUrl(io.github.codex_agent_labs.codexmobile.agent.AgentPendingElicitation){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.resolve|resolve(io.github.codex_agent_labs.codexmobile.agent.AgentPendingApproval;io.github.codex_agent_labs.codexmobile.agent.AgentApprovalDecision){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.resolve|resolve(io.github.codex_agent_labs.codexmobile.agent.AgentPendingElicitation;io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.approvals|{}approvals[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.elicitations|{}elicitations[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.add|add(io.github.codex_agent_labs.codexmobile.agent.AgentMcpServerConfiguration){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.remove|remove(io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolveEffort|resolveEffort(io.github.codex_agent_labs.codexmobile.agent.AgentModel;io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=kotlin/String!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolveServiceTier|resolveServiceTier(io.github.codex_agent_labs.codexmobile.agent.AgentModel;io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier?|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolve|resolve(io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentModel!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.install|install(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.list|list(kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.read|read(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.install|install(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.list|list(kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.read|read(kotlin.String;kotlin.Long){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Long!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentSkill){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D100_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationStatus;io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl?;io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl?;kotlin.String?;io.github.codex_agent_labs.codexmobile.agent.CodexFailure?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus!!:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexFailure?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.deviceUserCode|{}deviceUserCode[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.deviceVerificationUrl|{}deviceVerificationUrl[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.failure|{}failure[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexFailure?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.pendingSignInUrl|{}pendingSignInUrl[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState.status|{}status[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationStatus!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset;kotlin.String?){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!:default=true:vararg=false,REGULAR:kotlin/String?:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.approvalPreset|{}approvalPreset[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/AgentApprovalPreset!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentConversationSettings.serviceTier|{}serviceTier[0]|propertyKind=VAL|type=kotlin/String?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion.cancel|cancel(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse.Companion.decline|decline(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.accepts|accepts(io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse){}[0]|return=kotlin/Boolean!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.accept|accept(kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentFormValue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationResponse!!|suspend=false|parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.initialValues|initialValues(){}[0]|return=kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!|suspend=false|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentElicitation.validate|validate(kotlin.collections.Map<kotlin.String,io.github.codex_agent_labs.codexmobile.agent.AgentFormValue>){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentElicitationValidation!!|suspend=false|parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue!!>!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentFormField|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentFormField.accepts|accepts(io.github.codex_agent_labs.codexmobile.agent.AgentFormValue?){}[0]|return=kotlin/Boolean!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentFormValue?:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.displayName|{}displayName[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentIntegration.id|{}id[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState.pendingFor|pendingFor(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction!!>!!|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.key|{}key[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentInvocation.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction.conversationId|{}conversationId[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/ConversationId!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/AgentPendingInteraction.requestId|{}requestId[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion.chatGpt|chatGpt(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl!!|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.Companion.external|external(kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl!!|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.purpose|{}purpose[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationPurpose!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthorizationUrl.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.<init>|<init>(kotlin.String;kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.version|{}version[0]|propertyKind=VAL|type=kotlin/String!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Failed.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace?
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.Preparing.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHostState.WorkspaceRequired.requirement|{}requirement[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspaceResolution.SelectionRequired!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D100_RESIDUAL_CAPABILITY_KEYS =
            (D099_RESIDUAL_CAPABILITY_KEYS - D100_SELECTED_CAPABILITY_KEYS.toSet()).sorted()

        val D101_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.authentication|{}authentication[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.connectors|{}connectors[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.hooks|{}hooks[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexHooks!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.integrationAuthorization|{}integrationAuthorization[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.interactions|{}interactions[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.mcpServers|{}mcpServers[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.models|{}models[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexModels!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.plugins|{}plugins[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.skills|{}skills[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexSkills!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAgent|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAgent.workspace|{}workspace[0]|propertyKind=VAL|type=io.github.codex_agent_labs.codexmobile.agent/CodexWorkspace!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexPlatform;io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHost|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexPlatform!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.isAvailable|{}isAvailable[0]|propertyKind=VAL|type=kotlin/Boolean!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D101_RESIDUAL_CAPABILITY_KEYS =
            (D100_RESIDUAL_CAPABILITY_KEYS - D101_SELECTED_CAPABILITY_KEYS.toSet()).sorted()

        val D102_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.authenticate|authenticate(io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexAuthenticationMethod!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.cancel|cancel(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.signOut|signOut(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConnectors.list|list(kotlin.Boolean){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConnector!!>!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.delete|delete(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentConversationSummary!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.read|read(io.github.codex_agent_labs.codexmobile.agent.ConversationId){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentConversation!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversations|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversations.rename|rename(io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/ConversationId!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.reload|reload(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.runShellCommand|runShellCommand(kotlin.String){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.send|send(io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentTurnRequest!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.install|install(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHook!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.list|list(){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentHookCatalog!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.trust|trust(io.github.codex_agent_labs.codexmobile.agent.AgentHook){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHooks|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHooks.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentHook){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentHook!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.start|start(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.authorize|authorize(0:0){0§<io.github.codex_agent_labs.codexmobile.agent.AgentIntegration>}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:^A1:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.cancel|cancel(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.add|add(io.github.codex_agent_labs.codexmobile.agent.AgentMcpServerConfiguration){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServerConfiguration!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexMcpServers.remove|remove(io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentMcpServer!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.list|list(){}[0]|return=kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!>!!|suspend=true|parameters=[]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolveEffort|resolveEffort(io.github.codex_agent_labs.codexmobile.agent.AgentModel;io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=kotlin/String!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolveServiceTier|resolveServiceTier(io.github.codex_agent_labs.codexmobile.agent.AgentModel;io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentServiceTier?|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentModel!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexModels|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexModels.resolve|resolve(io.github.codex_agent_labs.codexmobile.agent.AgentResolution){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentModel!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentResolution!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.install|install(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginInstallResult!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.list|list(kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginCatalog!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.read|read(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentPluginDetail!!|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexPlugins.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentPluginReference!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.install|install(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope!!:default=false:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.list|list(kotlin.Boolean){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillCatalog!!|suspend=true|parameters=[REGULAR:kotlin/Boolean!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.read|read(kotlin.String;kotlin.Long){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/AgentSkillChunk!!|suspend=true|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/Long!!:default=true:vararg=false]
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexSkills|kind=function|abi=io.github.codex_agent_labs.codexmobile.agent/CodexSkills.uninstall|uninstall(io.github.codex_agent_labs.codexmobile.agent.AgentSkill){}[0]|return=kotlin/Unit|suspend=true|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/AgentSkill!!:default=false:vararg=false]
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D102_RESIDUAL_CAPABILITY_KEYS =
            (D101_RESIDUAL_CAPABILITY_KEYS - D102_SELECTED_CAPABILITY_KEYS.toSet()).sorted()

        val D103_SELECTED_CAPABILITY_KEYS = """
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.isAuthenticated|{}isAuthenticated[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.isAuthenticating|{}isAuthenticating[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexAuthentication.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentAuthenticationState!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.activeTurnProgress|{}activeTurnProgress[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentTurnProgress?>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canCancelTurn|{}canCancelTurn[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canReload|{}canReload[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canRunShellCommand|{}canRunShellCommand[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.canStartTurn|{}canStartTurn[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.currentMessages|{}currentMessages[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentMessage!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexConversation|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexConversation.isTurnActive|{}isTurnActive[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.active|{}active[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentIntegration?>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.isAuthorizing|{}isAuthorizing[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexIntegrationAuthorization.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentIntegrationAuthorizationState!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.approvals|{}approvals[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingApproval!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.elicitations|{}elicitations[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentPendingElicitation!!>!!>!!
            common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexInteractions.state|{}state[0]|propertyKind=VAL|type=kotlinx.coroutines.flow/StateFlow<INVARIANT:io.github.codex_agent_labs.codexmobile.agent/AgentInteractionState!!>!!
        """.trimIndent().lineSequence().filter(String::isNotBlank).toList()

        val D103_RESIDUAL_CAPABILITY_KEYS =
            (D102_RESIDUAL_CAPABILITY_KEYS - D103_SELECTED_CAPABILITY_KEYS.toSet()).sorted()

        val D104_SELECTED_CAPABILITY_KEYS = D103_RESIDUAL_CAPABILITY_KEYS

        val D104_RESIDUAL_CAPABILITY_KEYS =
            (D103_RESIDUAL_CAPABILITY_KEYS - D104_SELECTED_CAPABILITY_KEYS.toSet()).sorted()

        val SELECTED_CAPABILITY_KEYS =
            D093_SELECTED_CAPABILITY_KEYS + D094_SELECTED_CAPABILITY_KEYS + D095_SELECTED_CAPABILITY_KEYS +
                D096_SELECTED_CAPABILITY_KEYS + D097_SELECTED_CAPABILITY_KEYS + D098_SELECTED_CAPABILITY_KEYS +
                D099_SELECTED_CAPABILITY_KEYS + D100_SELECTED_CAPABILITY_KEYS + D101_SELECTED_CAPABILITY_KEYS +
                D102_SELECTED_CAPABILITY_KEYS + D103_SELECTED_CAPABILITY_KEYS + D104_SELECTED_CAPABILITY_KEYS

        const val HOST_CONSTRUCTOR_KEY =
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=constructor|" +
                "abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.<init>|" +
                "<init>(io.github.codex_agent_labs.codexmobile.agent.CodexPlatform;" +
                "io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo){}[0]|" +
                "return=io.github.codex_agent_labs.codexmobile.agent/CodexHost|suspend=false|" +
                "parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexPlatform!!:" +
                "default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/" +
                "CodexClientInfo!!:default=false:vararg=false]"

        fun dummyCapabilityKey(index: Int): String {
            val owner = "test.fixture/DummyCapability${index.toString().padStart(3, '0')}"
            return "common|owner=$owner|kind=property|abi=$owner.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!"
        }
    }
}
