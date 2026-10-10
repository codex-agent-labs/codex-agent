import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.jetbrains.org.objectweb.asm.ClassWriter
import org.jetbrains.org.objectweb.asm.Handle
import org.jetbrains.org.objectweb.asm.Opcodes
import org.jetbrains.org.objectweb.asm.Type

class CrossLanguageJavaBindingParityEvidenceTest {
    @Test
    fun `current 556 capability matrix satisfies exactly the Java slice`() = withFixture { fixture ->
        val evidence = fixture.derive()

        assertEquals(556, evidence.projectionClaims.size)
        assertEquals(576, evidence.publicSymbols.size)
        assertEquals(7, evidence.bindingTests.size)
        assertEquals(javaBindingTestIds.toSet(), evidence.bindingTests.map(CrossLanguageBindingTestEvidence::testId)
            .filter(javaBindingTestIds::contains).toSet())
        assertEquals(CrossLanguageBindingScenario.entries, evidence.scenarioEvidence.map(CrossLanguageScenarioEvidence::scenario))
        assertTrue(evidence.projectionClaims.all {
            it.executedTests.size == 1 &&
                it.executedTests.single().endsWith("#ordinaryAndHostStructurePassed") &&
                it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(6_116, evidence.parityReport.obligations.size)
        assertEquals(556, evidence.javaObligations.size)
        assertTrue(evidence.javaObligations.all {
            it.applicable && it.status == CrossLanguageObligationStatus.SATISFIED
        })
        assertEquals(2_224, evidence.parityReport.obligations.count {
            it.status == CrossLanguageObligationStatus.MISSING
        })
        assertEquals(3_336, evidence.parityReport.obligations.count {
            it.status == CrossLanguageObligationStatus.PENDING
        })
        assertEquals(fixture.compiledTests.crossLanguageTreeDigest(), evidence.digests.compiledTestsSha256)
        assertEquals(fixture.results.crossLanguageTreeDigest(), evidence.digests.testResultsSha256)
    }

    @Test
    fun `uses the exact six Java tests and stable fourteen scenario mapping`() {
        assertEquals(EXPECTED_TEST_METHODS, javaBindingTestIds.map { it.substringAfter('#') }.toSet())
        assertEquals(
            EXPECTED_SCENARIO_METHODS,
            javaBindingScenarioMappings.associate { mapping ->
                mapping.scenario to mapping.testIds.map { it.substringAfter('#') }.toSet()
            },
        )
    }

    @Test
    fun `rejects a missing Java test result`() = withFixture { fixture ->
        fixture.writeResults(javaBindingTestIds.dropLast(1).associateWith { CanonicalTestStatus.PASSED })

        assertFailure("was not executed") { fixture.derive() }
    }

    @Test
    fun `rejects a skipped Java test result`() = withFixture { fixture ->
        fixture.writeResults(javaBindingTestIds.associateWith { testId ->
            if (testId == javaBindingTestIds.first()) CanonicalTestStatus.SKIPPED else CanonicalTestStatus.PASSED
        })

        assertFailure("was skipped") { fixture.derive() }
    }

    @Test
    fun `rejects a missing or non JUnit compiled Java test`() = withFixture { fixture ->
        fixture.writeCompiledTests(methods = EXPECTED_TEST_METHODS - EXPECTED_TEST_METHODS.last())
        assertFailure("inventory is not exact") { fixture.derive() }

        fixture.writeCompiledTests(annotatedMethods = EXPECTED_TEST_METHODS - EXPECTED_TEST_METHODS.first())
        assertFailure("missing one @Test annotation") { fixture.derive() }
    }

    @Test
    fun `rejects a stale Java test in the scenario contract`() = withFixture { fixture ->
        val mappings = javaBindingScenarioMappings.mapIndexed { index, mapping ->
            if (index == 0) mapping.copy(testIds = listOf("removed.JavaTest#stale")) else mapping
        }

        assertFailure("stale tests") { fixture.derive(mappings = mappings) }
    }

    @Test
    fun `rejects a missing shared scenario`() = withFixture { fixture ->
        assertFailure("not an exact one-per-scenario inventory") {
            fixture.derive(mappings = javaBindingScenarioMappings.dropLast(1))
        }
    }

    @Test
    fun `rejects a missing structural capability`() = withFixture { fixture ->
        assertFailure("does not match the canonical API") {
            fixture.derive(structural = structuralEvidence(CAPABILITIES.dropLast(1)))
        }
    }

    @Test
    fun `exceptional projection requires a compiled and passed Java test reference`() = withFixture { fixture ->
        val target = JavaBindingMethodTarget("sample/Projection", "loadAsync", listOf("()V"))
        val claim = JavaBindingCapabilityClaim(
            capabilityKey = CAPABILITIES.first(),
            publicSymbols = listOf("method:sample/Projection#loadAsync()V"),
            proofKind = JavaBindingProofKind.TEST_REFERENCED,
            testReferenceTargets = listOf(target),
        )
        val structural = structuralEvidence(CAPABILITIES).copy(
            capabilityClaims = listOf(claim) + structuralEvidence(CAPABILITIES).capabilityClaims.drop(1),
        )

        assertFailure("not referenced by a compiled binding test") { fixture.derive(structural = structural) }

        val referencingTest = javaBindingTestIds.first().substringAfter('#')
        fixture.writeCompiledTests(references = mapOf(referencingTest to listOf(target)))
        val evidence = fixture.derive(structural = structural)
        val projection = evidence.projectionClaims.single { it.capabilityKey == claim.capabilityKey }
        assertEquals(listOf(javaBindingTestIds.first()), projection.executedTests)
        assertTrue(projection.sharedScenarios.isNotEmpty())

        fixture.writeCompiledTests(
            references = mapOf(
                referencingTest to listOf(JavaBindingMethodTarget(target.owner, target.name, listOf("(I)V"))),
            ),
        )
        assertFailure("not referenced by a compiled binding test") { fixture.derive(structural = structural) }

        fixture.writeCompiledTests(lambdaReferences = mapOf(referencingTest to listOf(target)))
        assertEquals(
            listOf(javaBindingTestIds.first()),
            fixture.derive(structural = structural).projectionClaims
                .single { it.capabilityKey == claim.capabilityKey }.executedTests,
        )
    }

    @Test
    fun `Java schema three receipt preserves every binding record and digest`() = withFixture { fixture ->
        val evidence = fixture.derive()
        val receipt = buildJavaBindingParityReceipt(
            KotlinBindingDigestEvidence(
                artifactSha256 = "e".repeat(64),
                apiReportSha256 = "f".repeat(64),
                canonicalCoverageSha256 = "0".repeat(64),
                compiledTestsSha256 = "1".repeat(64),
                testResultsSha256 = "2".repeat(64),
            ),
            evidence,
        )

        val file = fixture.results.resolve("java-binding-receipt.json")
        writeCrossLanguageBindingReceipt(file, receipt)
        val decoded = readCrossLanguageBindingReceipt(file)
        verifyJavaBindingParityReceipt(decoded, receipt)

        assertEquals(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA, decoded.toJson().releaseInt("schema"))
        assertEquals(CrossLanguageBinding.JAVA, decoded.language)
        assertEquals(CrossLanguageBindingPhase.M8, decoded.phase)
        assertEquals(CrossLanguageBindingCanonicalIdentity("f".repeat(64), "0".repeat(64)), decoded.canonical)
        assertEquals(
            mapOf(
                "android-runtime-aar" to "d".repeat(64),
                "core-android-aar" to "b".repeat(64),
                "core-jvm-jar" to "a".repeat(64),
                "desktop-runtime-jar" to "c".repeat(64),
            ),
            decoded.artifacts.associate { it.id to it.sha256 },
        )
        assertEquals(evidence.digests.compiledTestsSha256, decoded.testProgramSha256)
        assertEquals(evidence.digests.testResultsSha256, decoded.testResultsSha256)
        assertEquals(evidence.publicSymbols.sorted(), decoded.publicSymbols)
        assertEquals(576, decoded.publicSymbols.size)
        assertEquals(556, decoded.projectionClaims.size)
        assertEquals(7, decoded.bindingTests.size)
        assertEquals(evidence.bindingTests.sortedBy { it.testId }, decoded.bindingTests)
        assertTrue(decoded.bindingTests.all { it.status == CrossLanguageBindingTestStatus.PASSED })
        assertEquals(javaBindingTestIds.toSet(), decoded.bindingTests.map { it.testId }
            .filter(javaBindingTestIds::contains).toSet())
        assertEquals(14, decoded.scenarioEvidence.size)
        assertEquals(CrossLanguageBindingScenario.entries.toSet(), decoded.scenarioEvidence
            .map(CrossLanguageScenarioEvidence::scenario).toSet())
        assertTrue(decoded.projectionClaims.all { claim ->
            claim.publicSymbols.isNotEmpty() && claim.executedTests.isNotEmpty() &&
                claim.sharedScenarios.isNotEmpty()
        })
        assertTrue(decoded.applicabilityExclusions.isEmpty())

        val forged = decoded.copy(
            canonical = decoded.canonical.copy(apiReportSha256 = "9".repeat(64)),
        )
        assertFailure("does not match freshly recomputed evidence") {
            verifyJavaBindingParityReceipt(forged, receipt)
        }
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("java-binding-parity-evidence").toFile()
        try {
            block(Fixture(root))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun assertFailure(expected: String, block: () -> Unit) {
        val failure = assertFailsWith<IllegalStateException>(block = block)
        assertTrue(expected in failure.message.orEmpty(), failure.message.orEmpty())
    }

    private class Fixture(root: File) {
        val compiledTests = root.resolve("compiled-java-tests").apply { mkdirs() }
        val results = root.resolve("test-results").apply { mkdirs() }

        init {
            writeCompiledTests()
            writeResults(javaBindingTestIds.associateWith { CanonicalTestStatus.PASSED })
        }

        fun writeCompiledTests(
            methods: Set<String> = EXPECTED_TEST_METHODS,
            annotatedMethods: Set<String> = methods,
            references: Map<String, List<JavaBindingMethodTarget>> = emptyMap(),
            lambdaReferences: Map<String, List<JavaBindingMethodTarget>> = emptyMap(),
        ) {
            val writer = ClassWriter(ClassWriter.COMPUTE_MAXS)
            writer.visit(
                Opcodes.V17,
                Opcodes.ACC_PUBLIC,
                JAVA_TEST_INTERNAL_NAME,
                null,
                "java/lang/Object",
                null,
            )
            methods.sorted().forEach { methodName ->
                val method = writer.visitMethod(Opcodes.ACC_PUBLIC, methodName, "()V", null, null)
                if (methodName in annotatedMethods) {
                    method.visitAnnotation("Lorg/junit/jupiter/api/Test;", true).visitEnd()
                }
                method.visitCode()
                references[methodName].orEmpty().forEach { target ->
                    method.visitMethodInsn(
                        Opcodes.INVOKESTATIC,
                        target.owner,
                        target.name,
                        target.descriptors.single(),
                        false,
                    )
                }
                lambdaReferences[methodName].orEmpty().forEachIndexed { index, _ ->
                    val helper = "lambda\$$methodName\$$index"
                    method.visitInvokeDynamicInsn(
                        "run",
                        "()Ljava/lang/Runnable;",
                        LAMBDA_METAFACTORY,
                        Type.getMethodType("()V"),
                        Handle(Opcodes.H_INVOKESTATIC, JAVA_TEST_INTERNAL_NAME, helper, "()V", false),
                        Type.getMethodType("()V"),
                    )
                    method.visitInsn(Opcodes.POP)
                }
                method.visitInsn(Opcodes.RETURN)
                method.visitMaxs(0, 1)
                method.visitEnd()
            }
            lambdaReferences.forEach { (methodName, targets) ->
                targets.forEachIndexed { index, target ->
                    val helper = writer.visitMethod(
                        Opcodes.ACC_PRIVATE or Opcodes.ACC_STATIC or Opcodes.ACC_SYNTHETIC,
                        "lambda\$$methodName\$$index",
                        "()V",
                        null,
                        null,
                    )
                    helper.visitCode()
                    helper.visitMethodInsn(
                        Opcodes.INVOKESTATIC,
                        target.owner,
                        target.name,
                        target.descriptors.single(),
                        false,
                    )
                    helper.visitInsn(Opcodes.RETURN)
                    helper.visitMaxs(0, 0)
                    helper.visitEnd()
                }
            }
            writer.visitEnd()
            compiledTests.resolve("$JAVA_TEST_INTERNAL_NAME.class").also { classFile ->
                classFile.parentFile.mkdirs()
                classFile.writeBytes(writer.toByteArray())
            }
        }

        fun derive(
            capabilities: List<String> = CAPABILITIES,
            coverage: List<String> = capabilities,
            structural: CrossLanguageJavaBindingStructuralEvidence = structuralEvidence(capabilities),
            mappings: List<JavaBindingScenarioMapping> = javaBindingScenarioMappings,
        ): CrossLanguageJavaBindingParityEvidence = deriveCrossLanguageJavaBindingParityEvidence(
            capabilities,
            coverage,
            structural,
            compiledTests,
            results,
            mappings,
        )

        fun writeResults(statuses: Map<String, CanonicalTestStatus>) {
            results.resolve("TEST-java-binding.xml").writeText(buildString {
                append("<testsuite name=\"java-binding\">")
                statuses.forEach { (testId, status) ->
                    val (className, methodName) = testId.split('#', limit = 2)
                    append("<testcase classname=\"").append(className)
                        .append("\" name=\"").append(methodName).append("\"")
                    when (status) {
                        CanonicalTestStatus.PASSED -> append("/>")
                        CanonicalTestStatus.SKIPPED -> append("><skipped/></testcase>")
                        CanonicalTestStatus.FAILED -> append("><failure/></testcase>")
                    }
                }
                append("</testsuite>")
            })
        }
    }

    private companion object {
        val CAPABILITIES = (0 until 556).map { index -> "canonical-capability-$index" }
        const val JAVA_TEST_INTERNAL_NAME =
            "io/github/codex_agent_labs/codexagent/agent/CodexJavaApiTest"
        val LAMBDA_METAFACTORY = Handle(
            Opcodes.H_INVOKESTATIC,
            "java/lang/invoke/LambdaMetafactory",
            "metafactory",
            "(Ljava/lang/invoke/MethodHandles\$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;" +
                "Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)" +
                "Ljava/lang/invoke/CallSite;",
            false,
        )

        fun structuralEvidence(capabilities: List<String>) = CrossLanguageJavaBindingStructuralEvidence(
            digests = JavaBindingArtifactDigests(
                coreJvmJarSha256 = "a".repeat(64),
                coreAndroidAarSha256 = "b".repeat(64),
                desktopRuntimeJarSha256 = "c".repeat(64),
                androidRuntimeAarSha256 = "d".repeat(64),
            ),
            capabilityClaims = capabilities.mapIndexed { index, capability ->
                JavaBindingCapabilityClaim(
                    capability,
                    buildList {
                        add("method:sample/Owner#$index()V")
                        if (index < 20) add("field:sample/Owner#value$index:I")
                    },
                )
            },
        )

        val EXPECTED_TEST_METHODS = setOf(
            "canonicalHostAgentConversationLifecycleIsJavaFriendly",
            "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
            "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            "structuredFailuresAndFutureCancellationPreserveCanonicalSemantics",
            "cancellingCloseFutureDoesNotCancelCanonicalCleanup",
            "observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken",
        )

        val EXPECTED_SCENARIO_METHODS = mapOf(
            CrossLanguageBindingScenario.ASYNC_SUCCESS to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
            CrossLanguageBindingScenario.ASYNC_FAILURE to setOf(
                "structuredFailuresAndFutureCancellationPreserveCanonicalSemantics",
                "observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
            CrossLanguageBindingScenario.CANCELLATION to setOf(
                "structuredFailuresAndFutureCancellationPreserveCanonicalSemantics",
                "cancellingCloseFutureDoesNotCancelCanonicalCleanup",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
            ),
            CrossLanguageBindingScenario.STATE_CURRENT_VALUE to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
            ),
            CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
            ),
            CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken",
            ),
            CrossLanguageBindingScenario.TERMINAL_DELIVERY to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "cancellingCloseFutureDoesNotCancelCanonicalCleanup",
                "observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken",
            ),
            CrossLanguageBindingScenario.STRUCTURED_FAILURE to setOf(
                "structuredFailuresAndFutureCancellationPreserveCanonicalSemantics",
            ),
            CrossLanguageBindingScenario.IDENTITY to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
            ),
            CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "cancellingCloseFutureDoesNotCancelCanonicalCleanup",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
            CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "cancellingCloseFutureDoesNotCancelCanonicalCleanup",
            ),
            CrossLanguageBindingScenario.NULLABILITY to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
            CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
            CrossLanguageBindingScenario.VALUE_CONVERSION to setOf(
                "canonicalHostAgentConversationLifecycleIsJavaFriendly",
                "structuredFailuresAndFutureCancellationPreserveCanonicalSemantics",
                "controllerFuturesProjectAuthenticationInteractionsAndCancellation",
                "catalogAndResourceFuturesProjectValuesOptionalsAndOwnership",
            ),
        )
    }
}
