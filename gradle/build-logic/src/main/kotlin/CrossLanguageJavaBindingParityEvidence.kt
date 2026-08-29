import java.io.File
import java.nio.file.Files
import org.jetbrains.org.objectweb.asm.AnnotationVisitor
import org.jetbrains.org.objectweb.asm.ClassReader
import org.jetbrains.org.objectweb.asm.ClassVisitor
import org.jetbrains.org.objectweb.asm.Handle
import org.jetbrains.org.objectweb.asm.MethodVisitor
import org.jetbrains.org.objectweb.asm.Opcodes

internal data class JavaBindingParityDigests(
    val artifactDigests: JavaBindingArtifactDigests,
    val compiledTestsSha256: String,
    val testResultsSha256: String,
)

internal data class JavaBindingScenarioMapping(
    val scenario: CrossLanguageBindingScenario,
    val testIds: List<String>,
)

internal data class CrossLanguageJavaBindingParityEvidence(
    val digests: JavaBindingParityDigests,
    val projectionClaims: List<CrossLanguageProjectionClaim>,
    val publicSymbols: List<String>,
    val bindingTests: List<CrossLanguageBindingTestEvidence>,
    val scenarioEvidence: List<CrossLanguageScenarioEvidence>,
    val parityReport: CrossLanguageBindingParityReport,
) {
    val javaObligations: List<CrossLanguageBindingObligation> =
        parityReport.obligations.filter { it.language == CrossLanguageBinding.JAVA }
}

private const val JAVA_BINDING_TEST_CLASS =
    "io.github.codex_agent_labs.codexagent.agent.CodexJavaApiTest#"
private const val JAVA_BINDING_TEST_INTERNAL_NAME =
    "io/github/codex_agent_labs/codexagent/agent/CodexJavaApiTest"
private const val JAVA_STRUCTURAL_VERIFIER_TEST_ID =
    "build-logic.CrossLanguageJavaBindingEvidence#ordinaryAndHostStructurePassed"
private const val JUNIT_JUPITER_TEST = "Lorg/junit/jupiter/api/Test;"

private fun javaBindingTest(method: String): String = JAVA_BINDING_TEST_CLASS + method

internal val javaBindingTestIds = listOf(
    javaBindingTest("canonicalHostAgentConversationLifecycleIsJavaFriendly"),
    javaBindingTest("controllerFuturesProjectAuthenticationInteractionsAndCancellation"),
    javaBindingTest("catalogAndResourceFuturesProjectValuesOptionalsAndOwnership"),
    javaBindingTest("structuredFailuresAndFutureCancellationPreserveCanonicalSemantics"),
    javaBindingTest("cancellingCloseFutureDoesNotCancelCanonicalCleanup"),
    javaBindingTest("observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken"),
).sorted()

private val javaLifecycleTest = javaBindingTest("canonicalHostAgentConversationLifecycleIsJavaFriendly")
private val javaControllerTest = javaBindingTest("controllerFuturesProjectAuthenticationInteractionsAndCancellation")
private val javaCatalogTest = javaBindingTest("catalogAndResourceFuturesProjectValuesOptionalsAndOwnership")
private val javaFailureTest = javaBindingTest("structuredFailuresAndFutureCancellationPreserveCanonicalSemantics")
private val javaCloseTest = javaBindingTest("cancellingCloseFutureDoesNotCancelCanonicalCleanup")
private val javaObservationTest = javaBindingTest("observationCloseWaitsForAnInFlightCallbackAndFailureClosesTheToken")

internal val javaBindingScenarioMappings = listOf(
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_SUCCESS,
        listOf(javaLifecycleTest, javaControllerTest, javaCatalogTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_FAILURE,
        listOf(javaFailureTest, javaObservationTest, javaControllerTest, javaCatalogTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.CANCELLATION,
        listOf(javaFailureTest, javaCloseTest, javaControllerTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
        listOf(javaLifecycleTest, javaControllerTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
        listOf(javaLifecycleTest, javaControllerTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
        listOf(javaLifecycleTest, javaObservationTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.TERMINAL_DELIVERY,
        listOf(javaLifecycleTest, javaCloseTest, javaObservationTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.STRUCTURED_FAILURE,
        listOf(javaFailureTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.IDENTITY,
        listOf(javaLifecycleTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
        listOf(javaLifecycleTest, javaCloseTest, javaControllerTest, javaCatalogTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE,
        listOf(javaLifecycleTest, javaCloseTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.NULLABILITY,
        listOf(javaLifecycleTest, javaControllerTest, javaCatalogTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING,
        listOf(javaLifecycleTest, javaControllerTest, javaCatalogTest),
    ),
    JavaBindingScenarioMapping(
        CrossLanguageBindingScenario.VALUE_CONVERSION,
        listOf(javaLifecycleTest, javaFailureTest, javaControllerTest, javaCatalogTest),
    ),
)

internal fun deriveCrossLanguageJavaBindingParityEvidence(
    canonicalCapabilityKeys: List<String>,
    canonicalCoverageKeys: List<String>,
    structuralEvidence: CrossLanguageJavaBindingStructuralEvidence,
    compiledJavaTests: File,
    testResultsDirectory: File,
    scenarioMappings: List<JavaBindingScenarioMapping> = javaBindingScenarioMappings,
): CrossLanguageJavaBindingParityEvidence {
    val structuralClaims = structuralEvidence.capabilityClaims
    check(structuralClaims.map(JavaBindingCapabilityClaim::capabilityKey).sorted() == canonicalCapabilityKeys.sorted()) {
        "Java structural capability inventory does not match the canonical API"
    }

    val compiledTests = readCompiledJavaBindingTests(compiledJavaTests)
    val testResults = readCanonicalTestResults(testResultsDirectory).associateBy { it.testId }
    javaBindingTestIds.forEach { testId ->
        when (testResults[testId]?.status) {
            null -> error("Java binding test was not executed: $testId")
            CanonicalTestStatus.SKIPPED -> error("Java binding test was skipped: $testId")
            CanonicalTestStatus.FAILED -> error("Java binding test failed: $testId")
            CanonicalTestStatus.PASSED -> Unit
        }
    }
    val bindingTests = (javaBindingTestIds.map { testId ->
        CrossLanguageBindingTestEvidence(
            CrossLanguageBinding.JAVA,
            testId,
            CrossLanguageBindingTestStatus.PASSED,
        )
    } + CrossLanguageBindingTestEvidence(
        CrossLanguageBinding.JAVA,
        JAVA_STRUCTURAL_VERIFIER_TEST_ID,
        CrossLanguageBindingTestStatus.PASSED,
    )).sortedBy(CrossLanguageBindingTestEvidence::testId)

    val mappingsByScenario = scenarioMappings.groupBy(JavaBindingScenarioMapping::scenario)
    check(mappingsByScenario.keys == CrossLanguageBindingScenario.entries.toSet() &&
        mappingsByScenario.values.all { it.size == 1 }) {
        "Java binding scenario mapping is not an exact one-per-scenario inventory"
    }
    val scenarioEvidence = CrossLanguageBindingScenario.entries.map { scenario ->
        val testIds = mappingsByScenario.getValue(scenario).single().testIds
        check(testIds.isNotEmpty() && testIds.distinct().size == testIds.size &&
            testIds.all { it in javaBindingTestIds }) {
            "Java binding scenario ${scenario.id} has missing, duplicate, or stale tests"
        }
        CrossLanguageScenarioEvidence(CrossLanguageBinding.JAVA, scenario, testIds.sorted())
    }
    check(scenarioEvidence.flatMap(CrossLanguageScenarioEvidence::testIds).toSet() == javaBindingTestIds.toSet()) {
        "Java binding scenario matrix does not use the exact binding-test inventory"
    }

    val projectionClaims = structuralClaims.map { claim ->
        val executedTests = when (claim.proofKind) {
            JavaBindingProofKind.STRUCTURAL, JavaBindingProofKind.HOST_FACTORY -> {
                check(claim.testReferenceTargets.isEmpty()) {
                    "Structural Java capability unexpectedly declares test-reference targets: ${claim.capabilityKey}"
                }
                listOf(JAVA_STRUCTURAL_VERIFIER_TEST_ID)
            }
            JavaBindingProofKind.TEST_REFERENCED -> {
                check(claim.testReferenceTargets.isNotEmpty()) {
                    "Java exceptional capability has no test-reference target: ${claim.capabilityKey}"
                }
                claim.testReferenceTargets.flatMap { target ->
                    compiledTests.filter { test ->
                        test.methodReferences.any { reference -> target.matches(reference) }
                    }.map(CompiledJavaBindingTest::testId)
                        .also { references ->
                            check(references.isNotEmpty()) {
                                "Java exceptional projection is not referenced by a compiled binding test: " +
                                    "${claim.capabilityKey}: ${target.owner}#${target.name}"
                            }
                        }
                }.distinct().sorted()
            }
        }
        val sharedScenarios = when (claim.proofKind) {
            JavaBindingProofKind.STRUCTURAL -> listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
            JavaBindingProofKind.HOST_FACTORY -> listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
            JavaBindingProofKind.TEST_REFERENCED -> scenarioEvidence.filter { evidence ->
                evidence.testIds.any(executedTests::contains)
            }.map(CrossLanguageScenarioEvidence::scenario)
        }
        check(sharedScenarios.isNotEmpty()) { "Java projection has no matching shared scenario: ${claim.capabilityKey}" }
        CrossLanguageProjectionClaim(
            capabilityKey = claim.capabilityKey,
            language = CrossLanguageBinding.JAVA,
            publicSymbols = claim.publicSymbols,
            executedTests = executedTests,
            sharedScenarios = sharedScenarios,
        )
    }
    val parityReport = evaluateCrossLanguageBindingParity(
        CrossLanguageBindingParityInput(
            phase = CrossLanguageBindingPhase.M7_5,
            capabilityKeys = canonicalCapabilityKeys,
            canonicalCoverageKeys = canonicalCoverageKeys,
            projectionClaims = projectionClaims,
            publicSymbols = mapOf(CrossLanguageBinding.JAVA to structuralEvidence.publicSymbols),
            bindingTests = bindingTests,
            scenarioEvidence = scenarioEvidence,
        ),
    )
    check(parityReport.obligations.isNotEmpty()) { parityReport.errors.joinToString("\n") }
    val javaObligations = parityReport.obligations.filter { it.language == CrossLanguageBinding.JAVA }
    check(javaObligations.size == canonicalCapabilityKeys.size && javaObligations.all {
        it.applicable && it.status == CrossLanguageObligationStatus.SATISFIED
    }) {
        parityReport.errors.sorted().joinToString("\n")
    }

    return CrossLanguageJavaBindingParityEvidence(
        digests = JavaBindingParityDigests(
            artifactDigests = structuralEvidence.digests,
            compiledTestsSha256 = compiledJavaTests.crossLanguageTreeDigest(),
            testResultsSha256 = testResultsDirectory.crossLanguageTreeDigest(),
        ),
        projectionClaims = projectionClaims,
        publicSymbols = structuralEvidence.publicSymbols,
        bindingTests = bindingTests,
        scenarioEvidence = scenarioEvidence,
        parityReport = parityReport,
    )
}

private data class CompiledJavaBindingTest(
    val testId: String,
    val methodReferences: Set<JavaBindingMethodReference>,
)

private data class JavaBindingMethodReference(val owner: String, val name: String, val descriptor: String)

private fun JavaBindingMethodTarget.matches(reference: JavaBindingMethodReference): Boolean =
    owner == reference.owner && name == reference.name && reference.descriptor in descriptors

private data class JavaTestMethodKey(val name: String, val descriptor: String)

private data class JavaTestMethodBody(
    val access: Int,
    val junitAnnotations: Int,
    val references: Set<JavaBindingMethodReference>,
)

private fun readCompiledJavaBindingTests(classesDirectory: File): List<CompiledJavaBindingTest> {
    check(classesDirectory.isDirectory && !Files.isSymbolicLink(classesDirectory.toPath())) {
        "Compiled Java binding-test directory is missing or symbolic"
    }
    val classFile = classesDirectory.resolve("$JAVA_BINDING_TEST_INTERNAL_NAME.class")
    check(classFile.isFile && !Files.isSymbolicLink(classFile.toPath())) {
        "Compiled CodexJavaApiTest class is missing"
    }
    val expectedMethods = javaBindingTestIds.map { it.substringAfter('#') }.toSet()
    val methods = linkedMapOf<JavaTestMethodKey, JavaTestMethodBody>()
    ClassReader(classFile.readBytes()).accept(object : ClassVisitor(Opcodes.ASM9) {
        override fun visit(
            version: Int,
            access: Int,
            name: String,
            signature: String?,
            superName: String?,
            interfaces: Array<out String>?,
        ) {
            check(name == JAVA_BINDING_TEST_INTERNAL_NAME) {
                "Compiled Java binding-test class identity mismatch: $name"
            }
        }

        override fun visitMethod(
            access: Int,
            name: String,
            descriptor: String,
            signature: String?,
            exceptions: Array<out String>?,
        ): MethodVisitor? {
            var junitAnnotations = 0
            val references = linkedSetOf<JavaBindingMethodReference>()
            val key = JavaTestMethodKey(name, descriptor)
            check(key !in methods) { "Duplicate compiled Java binding test method: $name$descriptor" }
            return object : MethodVisitor(Opcodes.ASM9) {
                override fun visitAnnotation(descriptor: String, visible: Boolean): AnnotationVisitor? {
                    if (descriptor == JUNIT_JUPITER_TEST) junitAnnotations++
                    return null
                }

                override fun visitMethodInsn(
                    opcode: Int,
                    owner: String,
                    methodName: String,
                    methodDescriptor: String,
                    isInterface: Boolean,
                ) {
                    references += JavaBindingMethodReference(owner, methodName, methodDescriptor)
                }

                override fun visitInvokeDynamicInsn(
                    name: String,
                    descriptor: String,
                    bootstrapMethodHandle: Handle,
                    vararg bootstrapMethodArguments: Any,
                ) {
                    bootstrapMethodArguments.filterIsInstance<Handle>().filter { handle ->
                        handle.tag in setOf(
                            Opcodes.H_INVOKEVIRTUAL,
                            Opcodes.H_INVOKESTATIC,
                            Opcodes.H_INVOKESPECIAL,
                            Opcodes.H_NEWINVOKESPECIAL,
                            Opcodes.H_INVOKEINTERFACE,
                        )
                    }.forEach { handle ->
                        references += JavaBindingMethodReference(handle.owner, handle.name, handle.desc)
                    }
                }

                override fun visitEnd() {
                    methods[key] = JavaTestMethodBody(access, junitAnnotations, references)
                }
            }
        }
    }, ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES)

    val compiledTests = expectedMethods.associateWith { name ->
        val key = JavaTestMethodKey(name, "()V")
        val body = methods[key] ?: error("Compiled Java binding-test inventory is not exact: missing=[$name]")
        check(body.access and (Opcodes.ACC_ABSTRACT or Opcodes.ACC_SYNTHETIC) == 0) {
            "Compiled Java binding test has an invalid method shape: $name()V"
        }
        check(body.junitAnnotations == 1) { "Compiled Java binding test is missing one @Test annotation: $name" }
        val references = linkedSetOf<JavaBindingMethodReference>()
        fun collect(method: JavaTestMethodKey, seen: MutableSet<JavaTestMethodKey>) {
            if (!seen.add(method)) return
            methods[method]?.references.orEmpty().forEach { reference ->
                references += reference
                if (reference.owner == JAVA_BINDING_TEST_INTERNAL_NAME) {
                    collect(JavaTestMethodKey(reference.name, reference.descriptor), seen)
                }
            }
        }
        collect(key, linkedSetOf())
        CompiledJavaBindingTest(JAVA_BINDING_TEST_CLASS + name, references)
    }
    return javaBindingTestIds.map { testId -> compiledTests.getValue(testId.substringAfter('#')) }
}
