import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CrossLanguageBindingParityTest {
    @Test
    fun `defines exactly eleven stable language ids`() {
        assertEquals(
            listOf(
                "kotlin", "java", "swift", "objective-c", "javascript-typescript", "c-abi",
                "python", "csharp", "rust", "cpp", "dart",
            ),
            CrossLanguageBinding.entries.map(CrossLanguageBinding::id),
        )
    }

    @Test
    fun `owns the closed R757 scenario vocabulary`() {
        assertEquals(
            listOf(
                "async-success",
                "async-failure",
                "cancellation",
                "state-current-value",
                "state-subsequent-value",
                "subscription-cancellation",
                "terminal-delivery",
                "structured-failure",
                "identity",
                "parent-child-ownership",
                "repeated-close-dispose",
                "nullability",
                "collection-immutability-ordering",
                "value-conversion",
            ),
            CrossLanguageBindingScenario.entries.map(CrossLanguageBindingScenario::id),
        )
    }

    @Test
    fun `future additions fail canonical coverage before creating binding obligations`() {
        val input = passingInput().copy(
            capabilityKeys = listOf(CAPABILITY, FUTURE_CAPABILITY),
            projectionClaims = emptyList(),
            bindingTests = emptyList(),
            scenarioEvidence = emptyList(),
        )
        val report = evaluateCrossLanguageBindingParity(input)

        assertTrue(report.obligations.isEmpty())
        assertEquals(listOf("Missing canonical coverage for $FUTURE_CAPABILITY"), report.errors)
    }

    @Test
    fun `one future addition advances through coverage and every language independently`() {
        val capabilities = listOf(CAPABILITY, FUTURE_CAPABILITY).sorted()
        val uncovered = passingInput().copy(
            capabilityKeys = capabilities,
            canonicalCoverageKeys = listOf(CAPABILITY),
        )
        val blocked = evaluateCrossLanguageBindingParity(uncovered)

        assertTrue(blocked.obligations.isEmpty())
        assertEquals(listOf("Missing canonical coverage for $FUTURE_CAPABILITY"), blocked.errors)

        val activeForeignLanguages = activeLanguages(CrossLanguageBindingPhase.M7_5)
            .filterNot { it == CrossLanguageBinding.KOTLIN }
        val phasedLanguages = listOf(
            CrossLanguageBindingPhase.M8 to CrossLanguageBinding.C_ABI,
            CrossLanguageBindingPhase.M9_PYTHON to CrossLanguageBinding.PYTHON,
            CrossLanguageBindingPhase.M9_CSHARP to CrossLanguageBinding.CSHARP,
            CrossLanguageBindingPhase.M9_RUST to CrossLanguageBinding.RUST,
            CrossLanguageBindingPhase.M9_CPP to CrossLanguageBinding.CPP,
            CrossLanguageBindingPhase.M9_DART to CrossLanguageBinding.DART,
        )
        val futureLanguages = phasedLanguages.mapTo(mutableSetOf()) { it.second }
        var projectedLanguages = setOf(CrossLanguageBinding.KOTLIN)
        activeForeignLanguages.forEachIndexed { index, language ->
            val before = evaluateCrossLanguageBindingParity(
                futureProjectionInput(passingInput(), capabilities, projectedLanguages),
            )
            assertEquals(
                projectedLanguages,
                before.futureObligations(CrossLanguageObligationStatus.SATISFIED),
            )
            assertEquals(
                activeForeignLanguages.drop(index).toSet(),
                before.futureObligations(CrossLanguageObligationStatus.MISSING),
            )
            assertEquals(
                futureLanguages,
                before.futureObligations(CrossLanguageObligationStatus.PENDING),
            )

            projectedLanguages += language
        }

        val m7_5 = verifyCrossLanguageBindingParity(
            futureProjectionInput(passingInput(), capabilities, projectedLanguages),
        )
        assertEquals(
            activeLanguages(CrossLanguageBindingPhase.M7_5).toSet(),
            m7_5.futureObligations(CrossLanguageObligationStatus.SATISFIED),
        )
        assertEquals(futureLanguages, m7_5.futureObligations(CrossLanguageObligationStatus.PENDING))

        phasedLanguages.forEachIndexed { index, (phase, language) ->
            val before = evaluateCrossLanguageBindingParity(
                futureProjectionInput(passingInput(phase), capabilities, projectedLanguages),
            )
            val laterLanguages = phasedLanguages.drop(index + 1).mapTo(mutableSetOf()) { it.second }
            assertEquals(projectedLanguages, before.futureObligations(CrossLanguageObligationStatus.SATISFIED))
            assertEquals(setOf(language), before.futureObligations(CrossLanguageObligationStatus.MISSING))
            assertEquals(laterLanguages, before.futureObligations(CrossLanguageObligationStatus.PENDING))
            assertEquals(
                listOf("Missing active binding projection ${language.id}:$FUTURE_CAPABILITY"),
                before.errors,
            )

            projectedLanguages += language
            val after = verifyCrossLanguageBindingParity(
                futureProjectionInput(passingInput(phase), capabilities, projectedLanguages),
            )
            assertEquals(projectedLanguages, after.futureObligations(CrossLanguageObligationStatus.SATISFIED))
            assertTrue(after.futureObligations(CrossLanguageObligationStatus.MISSING).isEmpty())
            assertEquals(laterLanguages, after.futureObligations(CrossLanguageObligationStatus.PENDING))
        }

        val m11 = verifyCrossLanguageBindingParity(
            futureProjectionInput(passingInput(CrossLanguageBindingPhase.M11), capabilities, projectedLanguages),
        )
        assertEquals(
            CrossLanguageBinding.entries.toSet(),
            m11.futureObligations(CrossLanguageObligationStatus.SATISFIED),
        )
        assertTrue(m11.futureObligations(CrossLanguageObligationStatus.MISSING).isEmpty())
        assertTrue(m11.futureObligations(CrossLanguageObligationStatus.PENDING).isEmpty())
    }

    @Test
    fun `invalid or stale coverage also returns no obligations`() {
        val inputs = listOf(
            passingInput().copy(canonicalCoverageKeys = listOf(CAPABILITY, "removed#member")),
            passingInput().copy(canonicalCoverageKeys = listOf(CAPABILITY, CAPABILITY)),
            passingInput().copy(canonicalCoverageKeys = listOf(CAPABILITY, "")),
        )

        inputs.forEach { input ->
            val report = evaluateCrossLanguageBindingParity(input)
            assertTrue(report.obligations.isEmpty(), report.errors.joinToString())
            assertTrue(report.errors.isNotEmpty())
            assertFalse(report.errors.any { "binding projection" in it })
        }
    }

    @Test
    fun `every phase materializes all pairs with exact active and pending counts`() {
        val activeCounts = mapOf(
            CrossLanguageBindingPhase.M7_5 to 5,
            CrossLanguageBindingPhase.M8 to 6,
            CrossLanguageBindingPhase.M9_PYTHON to 7,
            CrossLanguageBindingPhase.M9_CSHARP to 8,
            CrossLanguageBindingPhase.M9_RUST to 9,
            CrossLanguageBindingPhase.M9_CPP to 10,
            CrossLanguageBindingPhase.M9_DART to 11,
            CrossLanguageBindingPhase.M11 to 11,
        )

        activeCounts.forEach { (phase, active) ->
            val report = verifyCrossLanguageBindingParity(passingInput(phase))
            assertEquals(11, report.obligations.size, phase.name)
            assertEquals(active, report.obligations.count { it.status == CrossLanguageObligationStatus.SATISFIED }, phase.name)
            assertEquals(11 - active, report.obligations.count { it.status == CrossLanguageObligationStatus.PENDING }, phase.name)
            assertTrue(report.obligations.all { it.applicable }, phase.name)
        }
    }

    @Test
    fun `accepts an idiomatic projection name instead of signature equality`() {
        val report = verifyCrossLanguageBindingParity(passingInput())
        val java = report.obligations.single { it.language == CrossLanguageBinding.JAVA }

        assertEquals(CrossLanguageObligationStatus.SATISFIED, java.status)
        assertFalse("isAuthenticated" in JAVA_SYMBOL)
    }

    @Test
    fun `Kotlin identity projection requires the compiler derived public member`() {
        val input = passingInput().copy(
            publicSymbols = passingInput().publicSymbols - CrossLanguageBinding.KOTLIN,
        )
        val report = evaluateCrossLanguageBindingParity(input)

        assertTrue(report.errors.any { "Missing active binding projection kotlin:$CAPABILITY" in it })
        assertEquals(
            CrossLanguageObligationStatus.MISSING,
            report.obligations.single { it.language == CrossLanguageBinding.KOTLIN }.status,
        )
    }

    @Test
    fun `skipped and failed binding tests satisfy neither claims nor scenarios`() {
        listOf(CrossLanguageBindingTestStatus.SKIPPED, CrossLanguageBindingTestStatus.FAILED).forEach { status ->
            val input = passingInput().copy(
                bindingTests = passingBindingTests().map {
                    if (it.language == CrossLanguageBinding.JAVA) it.copy(status = status) else it
                },
            )
            val report = evaluateCrossLanguageBindingParity(input)

            assertTrue(report.errors.any { "Unknown or non-passed java binding test" in it }, status.name)
            assertTrue(report.errors.any { "Unknown or non-passed java scenario test" in it }, status.name)
            assertTrue(report.errors.any { "Missing java shared scenario evidence" in it }, status.name)
            assertTrue(report.errors.any { "Missing active binding projection java:$CAPABILITY" in it }, status.name)
        }
    }

    @Test
    fun `requires the complete scenario matrix for every active language including Kotlin`() {
        val input = passingInput()
        val active = CrossLanguageBinding.entries.filter { it.isActive(input.phase) }
        assertEquals(active.size * CrossLanguageBindingScenario.entries.size, input.scenarioEvidence.size)
        assertTrue(
            active.all { language ->
                CrossLanguageBindingScenario.entries.all { scenario ->
                    input.scenarioEvidence.any { it.language == language && it.scenario == scenario }
                }
            },
        )

        CrossLanguageBindingScenario.entries.forEach { scenario ->
            val missingJava = input.copy(
                scenarioEvidence = input.scenarioEvidence.filterNot {
                    it.language == CrossLanguageBinding.JAVA && it.scenario == scenario
                },
            )
            assertHasError("Missing java shared scenario evidence ${scenario.id}", missingJava)
        }
        val missingKotlin = input.copy(
            scenarioEvidence = input.scenarioEvidence.filterNot {
                it.language == CrossLanguageBinding.KOTLIN &&
                    it.scenario == CrossLanguageBindingScenario.ASYNC_SUCCESS
            },
        )
        assertHasError("Missing kotlin shared scenario evidence async-success", missingKotlin)
    }

    @Test
    fun `each active non Kotlin language requires its own claim`() {
        val input = passingInput()
        activeLanguages(input.phase).filterNot { it == CrossLanguageBinding.KOTLIN }.forEach { language ->
            assertHasError(
                "Missing active binding projection ${language.id}:$CAPABILITY",
                input.copy(projectionClaims = input.projectionClaims.filterNot { it.language == language }),
            )
        }
    }

    @Test
    fun `accepts a narrow exclusion without a minimum reason length`() {
        val input = passingInput().copy(
            projectionClaims = passingClaims().filterNot { it.language == CrossLanguageBinding.SWIFT },
            applicabilityExclusions = listOf(
                CrossLanguageApplicabilityExclusion(CAPABILITY, CrossLanguageBinding.SWIFT, "Swift host factory."),
            ),
        )
        val report = verifyCrossLanguageBindingParity(input)
        val swift = report.obligations.single { it.language == CrossLanguageBinding.SWIFT }

        assertEquals(CrossLanguageObligationStatus.EXCLUDED, swift.status)
        assertFalse(swift.applicable)
    }

    @Test
    fun `rejects blank wildcard broad stale duplicate conflicting and inactive exclusions`() {
        val valid = CrossLanguageApplicabilityExclusion(
            CAPABILITY,
            CrossLanguageBinding.SWIFT,
            "Swift host factory.",
        )
        val noSwiftClaim = passingInput().copy(
            projectionClaims = passingClaims().filterNot { it.language == CrossLanguageBinding.SWIFT },
        )

        assertHasError("Blank applicability exclusion reason", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid.copy(reason = "")),
        ))
        assertHasError("Wildcard applicability exclusion reason", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid.copy(reason = "Swift *")),
        ))
        assertHasError("Broad applicability exclusion reason", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid.copy(reason = "not applicable")),
        ))
        assertHasError("Wildcard applicability exclusion capability key", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid.copy(capabilityKey = "*")),
        ))
        assertHasError("Stale applicability exclusion", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid.copy(capabilityKey = "removed#member")),
        ))
        assertHasError("Duplicate applicability exclusion", noSwiftClaim.copy(
            applicabilityExclusions = listOf(valid, valid),
        ))
        assertHasError("conflicts with applicability exclusion", passingInput().copy(
            applicabilityExclusions = listOf(valid),
        ))
        assertHasError("targets an inactive language", passingInput().copy(
            applicabilityExclusions = listOf(
                valid.copy(language = CrossLanguageBinding.C_ABI, reason = "C host bootstrap only."),
            ),
        ))
    }

    @Test
    fun `rejects stale duplicate unknown and non-passed projection records`() {
        assertHasError("Stale projection claim", passingInput().copy(
            projectionClaims = passingClaims() + claim(CrossLanguageBinding.C_ABI).copy(
                capabilityKey = "removed#member",
            ),
        ))
        assertHasError("Duplicate projection claim", passingInput().copy(
            projectionClaims = passingClaims() + passingClaims().first(),
        ))
        assertHasError("Unknown java public symbol", replaceClaim(CrossLanguageBinding.JAVA) {
            it.copy(publicSymbols = listOf("missing-symbol"))
        })
        assertHasError("Duplicate java binding test evidence", passingInput().copy(
            bindingTests = passingBindingTests() + passingBindingTests().first { it.language == CrossLanguageBinding.JAVA }
                .copy(status = CrossLanguageBindingTestStatus.FAILED),
        ))
        assertHasError("Duplicate swift scenario evidence", passingInput().copy(
            scenarioEvidence = passingScenarioEvidence() + passingScenarioEvidence().first {
                it.language == CrossLanguageBinding.SWIFT
            },
        ))
        assertHasError("has no shared scenario", replaceClaim(CrossLanguageBinding.OBJECTIVE_C) {
            it.copy(sharedScenarios = emptyList())
        })
    }

    @Test
    fun `a C ABI projection does not satisfy any wrapper`() {
        val input = passingInput(CrossLanguageBindingPhase.M11)
        val wrappers = listOf(
            CrossLanguageBinding.PYTHON,
            CrossLanguageBinding.CSHARP,
            CrossLanguageBinding.RUST,
            CrossLanguageBinding.CPP,
            CrossLanguageBinding.DART,
        )

        wrappers.forEach { wrapper ->
            val report = evaluateCrossLanguageBindingParity(input.copy(
                projectionClaims = input.projectionClaims.filterNot { it.language == wrapper },
            ))
            assertTrue(
                report.errors.any { "Missing active binding projection ${wrapper.id}:$CAPABILITY" in it },
                wrapper.id,
            )
            assertFalse(
                report.errors.any { "Missing active binding projection c-abi:$CAPABILITY" in it },
                wrapper.id,
            )
        }
    }

    @Test
    fun `verify throws the complete parity report`() {
        val input = passingInput().copy(projectionClaims = emptyList())
        val failure = assertFailsWith<IllegalStateException> { verifyCrossLanguageBindingParity(input) }

        assertTrue("Missing active binding projection java:$CAPABILITY" in failure.message.orEmpty())
        assertTrue("Missing active binding projection swift:$CAPABILITY" in failure.message.orEmpty())
    }

    private fun replaceClaim(
        language: CrossLanguageBinding,
        transform: (CrossLanguageProjectionClaim) -> CrossLanguageProjectionClaim,
    ): CrossLanguageBindingParityInput = passingInput().copy(
        projectionClaims = passingClaims().map { if (it.language == language) transform(it) else it },
    )

    private fun assertHasError(expected: String, input: CrossLanguageBindingParityInput) {
        val report = evaluateCrossLanguageBindingParity(input)
        assertTrue(report.errors.any { expected in it }, report.errors.joinToString("\n"))
    }

    private fun futureProjectionInput(
        input: CrossLanguageBindingParityInput,
        capabilities: List<String>,
        projectedLanguages: Set<CrossLanguageBinding>,
    ): CrossLanguageBindingParityInput = input.copy(
        capabilityKeys = capabilities,
        canonicalCoverageKeys = capabilities,
        projectionClaims = input.projectionClaims + projectedLanguages
            .filterNot { it == CrossLanguageBinding.KOTLIN }
            .map { language ->
                claim(language).copy(
                    capabilityKey = FUTURE_CAPABILITY,
                    publicSymbols = listOf(futureSymbol(language)),
                )
            },
        publicSymbols = input.publicSymbols.mapValues { (language, symbols) ->
            if (language !in projectedLanguages) {
                symbols
            } else {
                (symbols + if (language == CrossLanguageBinding.KOTLIN) FUTURE_CAPABILITY else futureSymbol(language))
                    .sorted()
            }
        },
    )

    private fun CrossLanguageBindingParityReport.futureObligations(
        status: CrossLanguageObligationStatus,
    ): Set<CrossLanguageBinding> = obligations
        .filter { it.capabilityKey == FUTURE_CAPABILITY && it.status == status }
        .mapTo(mutableSetOf(), CrossLanguageBindingObligation::language)

    private companion object {
        const val CAPABILITY =
            "io.github.codex_agent_labs.codexagent.agent.CodexAuthentication|property|isAuthenticated|" +
                "():kotlinx.coroutines.flow.StateFlow<kotlin.Boolean>"
        const val FUTURE_CAPABILITY =
            "io.github.codex_agent_labs.codexagent.agent.CodexAuthentication|function|refresh|():kotlin.Unit"
        const val JAVA_SYMBOL = "CodexJava#observeAuthenticationStatus(CodexAuthentication,Executor,Consumer)"

        fun passingInput(
            phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        ): CrossLanguageBindingParityInput = CrossLanguageBindingParityInput(
            phase = phase,
            capabilityKeys = listOf(CAPABILITY),
            canonicalCoverageKeys = listOf(CAPABILITY),
            projectionClaims = passingClaims(phase),
            publicSymbols = passingPublicSymbols(phase),
            bindingTests = passingBindingTests(phase),
            scenarioEvidence = passingScenarioEvidence(phase),
        )

        fun passingClaims(
            phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        ): List<CrossLanguageProjectionClaim> = activeLanguages(phase)
            .filterNot { it == CrossLanguageBinding.KOTLIN }
            .map(::claim)

        fun claim(language: CrossLanguageBinding): CrossLanguageProjectionClaim =
            CrossLanguageProjectionClaim(
                capabilityKey = CAPABILITY,
                language = language,
                publicSymbols = listOf(symbol(language)),
                executedTests = listOf(testId(language)),
                sharedScenarios = listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            )

        fun passingPublicSymbols(
            phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        ): Map<CrossLanguageBinding, List<String>> = activeLanguages(phase).associateWith { language ->
            if (language == CrossLanguageBinding.KOTLIN) listOf(CAPABILITY) else listOf(symbol(language))
        }

        fun passingBindingTests(
            phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        ): List<CrossLanguageBindingTestEvidence> = activeLanguages(phase).map { language ->
            CrossLanguageBindingTestEvidence(language, testId(language), CrossLanguageBindingTestStatus.PASSED)
        }

        fun passingScenarioEvidence(
            phase: CrossLanguageBindingPhase = CrossLanguageBindingPhase.M7_5,
        ): List<CrossLanguageScenarioEvidence> = activeLanguages(phase).flatMap { language ->
            CrossLanguageBindingScenario.entries.map { scenario ->
                CrossLanguageScenarioEvidence(language, scenario, listOf(testId(language)))
            }
        }

        fun activeLanguages(phase: CrossLanguageBindingPhase): List<CrossLanguageBinding> =
            CrossLanguageBinding.entries.filter { it.isActive(phase) }

        fun symbol(language: CrossLanguageBinding): String = when (language) {
            CrossLanguageBinding.JAVA -> JAVA_SYMBOL
            CrossLanguageBinding.SWIFT -> "CodexAuthentication.authenticationStates"
            CrossLanguageBinding.OBJECTIVE_C -> "-[CDXAuthentication observeStateWithHandler:]"
            CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT -> "CodexAuthentication.observeState"
            CrossLanguageBinding.C_ABI -> "codex_authentication_subscribe"
            CrossLanguageBinding.PYTHON -> "CodexAuthentication.states"
            CrossLanguageBinding.CSHARP -> "CodexAuthentication.States"
            CrossLanguageBinding.RUST -> "CodexAuthentication::states"
            CrossLanguageBinding.CPP -> "CodexAuthentication::states"
            CrossLanguageBinding.DART -> "CodexAuthentication.states"
            CrossLanguageBinding.KOTLIN -> error("Kotlin is satisfied by canonical coverage")
        }

        fun testId(language: CrossLanguageBinding): String = "${language.id}-binding-test"

        fun futureSymbol(language: CrossLanguageBinding): String = "${symbol(language)}#future"
    }
}
