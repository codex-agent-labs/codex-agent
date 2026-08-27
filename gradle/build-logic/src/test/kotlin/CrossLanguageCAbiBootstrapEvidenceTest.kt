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
    fun `derives the exact reviewed 226 capability bootstrap slice`() {
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
        assertEquals(226, keys.size)
        assertEquals(keys.sorted(), keys)
        assertEquals(keys.size, keys.distinct().size)
        assertEquals(SELECTED_CAPABILITY_KEYS.sorted(), keys)
        assertEquals(C_ABI_BOOTSTRAP_CAPABILITY_SHA256, keys.sortedNewlineSha256())
        assertEquals(330, complement.size)
        assertEquals((DUMMY_CAPABILITY_KEYS + ABSENT_FACTORY_AND_CLIENT_INFO_KEYS).sorted(), complement)
        ABSENT_FACTORY_AND_CLIENT_INFO_KEYS.forEach { key ->
            assertFalse(key in keys, key)
        }
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
                    .replace(DUMMY_CAPABILITY_KEYS.first(), "$selected|duplicate-signature=true"))
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
            ).forEach { (property, fixture) ->
                val assignment = generator.substringAfter("$property.set(").substringBefore("\n    )")
                assertTrue(fixture in assignment, "C bootstrap $property is not wired to $fixture")
            }
            val producer = File("src/main/kotlin/CrossLanguageCAbiBootstrapEvidence.kt").readText()
            listOf(
                "\"c11-ordinary-enums\"",
                "\"c11-form-hook-values\"",
                "\"c11-invocation-auth-values\"",
                "put(\"milestone\", JsonPrimitive(\"D095\"))",
            ).forEach { contract ->
                assertTrue(contract in producer, "Missing D095 C bootstrap producer contract: $contract")
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
            SELECTED_CAPABILITY_KEYS + DUMMY_CAPABILITY_KEYS + ABSENT_FACTORY_AND_CLIENT_INFO_KEYS
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

        val SELECTED_CAPABILITY_KEYS =
            D093_SELECTED_CAPABILITY_KEYS + D094_SELECTED_CAPABILITY_KEYS + D095_SELECTED_CAPABILITY_KEYS

        val DUMMY_CAPABILITY_KEYS = (0 until 325).map(::dummyCapabilityKey)

        val ABSENT_FACTORY_AND_CLIENT_INFO_KEYS = listOf(
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.<init>|<init>(kotlin.String;kotlin.String;kotlin.String){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false,REGULAR:kotlin/String!!:default=false:vararg=false]",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.name|{}name[0]|propertyKind=VAL|type=kotlin/String!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.title|{}title[0]|propertyKind=VAL|type=kotlin/String!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo|kind=property|abi=io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo.version|{}version[0]|propertyKind=VAL|type=kotlin/String!!",
            "common|owner=io.github.codex_agent_labs.codexmobile.agent/CodexHost|kind=constructor|abi=io.github.codex_agent_labs.codexmobile.agent/CodexHost.<init>|<init>(io.github.codex_agent_labs.codexmobile.agent.CodexPlatform;io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo){}[0]|return=io.github.codex_agent_labs.codexmobile.agent/CodexHost|suspend=false|parameters=[REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexPlatform!!:default=false:vararg=false,REGULAR:io.github.codex_agent_labs.codexmobile.agent/CodexClientInfo!!:default=false:vararg=false]",
        )

        fun dummyCapabilityKey(index: Int): String {
            val owner = "test.fixture/DummyCapability${index.toString().padStart(3, '0')}"
            return "common|owner=$owner|kind=property|abi=$owner.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!"
        }
    }
}
