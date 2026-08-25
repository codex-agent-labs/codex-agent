import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class CrossLanguageJavaScriptBindingEvidenceTest {
    @Test
    fun `current 189-symbol compiler snapshot inventories gaps without claiming canonical parity`() {
        val keys = listOf(
            canonicalProperty("CodexFailure", "message", "kotlin/String!!"),
            canonicalFunction("CodexHost", "start", suspendFunction = true),
            canonicalProperty(
                "CodexHost",
                "lifecycleState",
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/CodexHostState!!>!!",
            ),
            canonicalEnumEntry("AgentApprovalPreset", "AUTO_REVIEW"),
        ).sorted()
        val evidence = deriveCrossLanguageJavaScriptBindingEvidence(
            canonical = canonicalEvidence(keys),
            packedApi = packedEvidence(currentPublicSymbols(), schema = 1),
        )

        assertEquals(4, evidence.canonical.memberKeys.size)
        assertEquals(189, evidence.packedApi.publicSymbols.size)
        assertTrue(evidence.errors.any { "Unreferenced exceptional" in it && "CodexHost.start" in it })
        assertTrue(evidence.errors.any { "Unreferenced exceptional" in it && "lifecycleState" in it })
    }

    @Test
    fun `556 convention-derived claims and all fourteen scenarios can produce schema-3 receipt`() {
        val keys = List(556) { index ->
            canonicalProperty("ProjectedType${index.toString().padStart(3, '0')}", "value", "kotlin/String!!")
        }.sorted()
        val symbols = List(556) { index ->
            "getter:ProjectedType${index.toString().padStart(3, '0')}#value:string"
        } + List(556) { index -> "class:ProjectedType${index.toString().padStart(3, '0')}" }
        val files = receiptFiles(keys, symbols.sorted(), schema = 2, references = emptyList())

        val receipt = buildJavaScriptTypeScriptBindingReceipt(files)

        assertEquals(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA, receipt.toJson()["schema"]?.toString()?.toInt())
        assertEquals(556, receipt.projectionClaims.size)
        assertEquals(14, receipt.scenarioEvidence.size)
        assertEquals(keys, receipt.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).sorted())
        assertEquals(
            mapOf(
                "commonJs" to files.installedPackageDirectory.resolve("index.cjs").releaseDigest(),
                "declaration" to files.installedPackageDirectory.resolve("index.d.ts").releaseDigest(),
                "esm" to files.installedPackageDirectory.resolve("index.mjs").releaseDigest(),
                "packageJson" to files.installedPackageDirectory.resolve("package.json").releaseDigest(),
                "tarball" to files.npmTarball.releaseDigest(),
            ),
            receipt.artifacts.associate { it.id to it.sha256 },
        )
        assertEquals(
            labeledJavaScriptDigest(
                "compiled-js-node-test-program" to files.compiledJsNodeTestProgramDirectory.crossLanguageTreeDigest(),
                "packed-consumer-source" to files.consumerSourceDirectory.crossLanguageTreeDigest(),
            ),
            receipt.testProgramSha256,
        )
        assertEquals(
            canonicalJavaScriptBindingTestsDigest(receipt.bindingTests),
            receipt.testResultsSha256,
        )
        val rawPackedDigest = files.packedJUnitReport.releaseDigest()
        files.packedJUnitReport.writeText(files.packedJUnitReport.readText().replace("/>", " time=\"999\"/>"))
        assertTrue(rawPackedDigest != files.packedJUnitReport.releaseDigest())
        assertEquals(receipt.testResultsSha256, buildJavaScriptTypeScriptBindingReceipt(files).testResultsSha256)
    }

    @Test
    fun `schema-3 receipt exactly partitions 544 claims and twelve reviewed exclusions`() {
        val claimedKeys = List(544) { index ->
            canonicalProperty("Claimed${index.toString().padStart(3, '0')}", "value", "kotlin/String!!")
        }.sorted()
        val exclusionKeys = sdkCreatedConstructorKeys()
        val symbols = claimedKeys.flatMap { key ->
            val owner = key.substringAfter("owner=example/").substringBefore('|')
            listOf("class:$owner", "getter:$owner#value:string")
        }.sorted()
        val receipt = buildJavaScriptTypeScriptBindingReceipt(
            receiptFiles((claimedKeys + exclusionKeys).sorted(), symbols),
        )

        assertEquals(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA, receipt.toJson()["schema"]?.toString()?.toInt())
        assertEquals(544, receipt.projectionClaims.size)
        assertEquals(12, receipt.applicabilityExclusions.size)
        assertEquals(
            (claimedKeys + exclusionKeys).toSet(),
            receipt.projectionClaims.mapTo(mutableSetOf(), CrossLanguageProjectionClaim::capabilityKey) +
                receipt.applicabilityExclusions.map(CrossLanguageApplicabilityExclusion::capabilityKey),
        )
        assertTrue(
            receipt.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).toSet()
                .intersect(receipt.applicabilityExclusions.mapTo(mutableSetOf(),
                    CrossLanguageApplicabilityExclusion::capabilityKey)).isEmpty(),
        )
    }

    @Test
    fun `missing capability diagnostic is bounded and grouped by canonical owner`() {
        val keys = listOf(
            canonicalProperty("Small", "first", "kotlin/String!!"),
            canonicalProperty("Large", "first", "kotlin/String!!"),
            canonicalProperty("Large", "second", "kotlin/String!!"),
        )

        assertEquals(
            "Missing 3 JavaScript/TypeScript capabilities across 2 canonical owners; " +
                "largest owners: Large=2, Small=1",
            summarizeMissingJavaScriptCapabilities(keys),
        )
    }

    @Test
    fun `matcher rejects ambiguous reused and unreferenced projections`() {
        val ambiguous = canonicalProperty("Ambiguous", "value", "kotlin/String!!")
        val aliasOne = canonicalProperty("CodexFailure", "isRecoverable", "kotlin/Boolean!!")
        val aliasTwo = canonicalProperty("CodexFailure", "recoverable", "kotlin/Boolean!!")
        val unreferenced = canonicalFunction("CodexHost", "start", suspendFunction = true)
        val symbols = listOf(
            "class:Ambiguous",
            "class:CodexFailure",
            "class:CodexHost",
            "getter:Ambiguous#value:string",
            "getter:CodexFailure#recoverable:boolean",
            "method:CodexHost#start:(signal?: AbortSignal | null | undefined): Promise<void>",
            "property:Ambiguous#value[readonly]:string",
        ).sorted()

        val evidence = deriveCrossLanguageJavaScriptBindingEvidence(
            canonical = canonicalEvidence(listOf(ambiguous, aliasOne, aliasTwo, unreferenced).sorted()),
            packedApi = packedEvidence(symbols, schema = 2),
        )

        assertTrue(evidence.errors.any { "Ambiguous" in it && ambiguous in it })
        assertTrue(evidence.errors.any { "Reused" in it && aliasOne in it && aliasTwo in it })
        assertTrue(evidence.errors.any { "Unreferenced exceptional" in it && unreferenced in it })
        assertTrue(evidence.projectionClaims.none { it.capabilityKey in setOf(ambiguous, aliasOne, aliasTwo, unreferenced) })
    }

    @Test
    fun `finite aliases and same-owner enum literals project without per-member manifest`() {
        val lifecycle = canonicalProperty(
            "CodexHost",
            "lifecycleState",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/CodexHostState!!>!!",
        )
        val constructor = canonicalConstructor("CodexHost", listOf("example/CodexPlatform!!", "example/CodexClientInfo!!"))
        val autoReview = canonicalEnumEntry("AgentApprovalPreset", "AUTO_REVIEW")
        val askMe = canonicalEnumEntry("AgentApprovalPreset", "ASK_ME")
        val symbols = listOf(
            "class:CodexHost",
            "function:createCodexHost:(bundleDirectory: string, dataDirectory: string, clientName: string, clientTitle: string, clientVersion: string): CodexHost",
            "getter:CodexHost#state:CodexHostState",
            "method:CodexHost#observeState:(listener: (state: CodexHostState) => void): CodexObservation",
            "type:CodexApprovalPreset:\"auto_review\" | \"never\" | \"ask_me\" | \"strict\"",
        ).sorted()
        val evidence = deriveCrossLanguageJavaScriptBindingEvidence(
            canonical = canonicalEvidence(listOf(lifecycle, constructor, autoReview, askMe).sorted()),
            packedApi = packedEvidence(symbols, schema = 2, referencedSymbols = symbols),
        )

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(4, evidence.projectionClaims.size)
        assertEquals(2, evidence.projectionClaims.count {
            it.publicSymbols.singleOrNull()?.startsWith("type:CodexApprovalPreset:") == true
        })
    }

    @Test
    fun `finite singleton objects project only explicit authentication and host status literals`() {
        val browser = canonicalObject("CodexAuthenticationMethod.ChatGptBrowser")
        val device = canonicalObject("CodexAuthenticationMethod.ChatGptDeviceCode")
        val new = canonicalObject("CodexHostState.New")
        val restoring = canonicalObject("CodexHostState.Restoring")
        val closed = canonicalObject("CodexHostState.Closed")
        val hookAgent = canonicalObject("AgentHookHandler.Agent")
        val hookPrompt = canonicalObject("AgentHookHandler.Prompt")
        val authenticationType =
            "type:CodexAuthenticationMethod:\"chatgpt_browser\" | \"chatgpt_device_code\" | \"api_key\""
        val hostType =
            "type:CodexHostStatus:\"new\" | \"restoring\" | \"workspace_required\" | \"preparing\" | \"ready\" | \"failed\" | \"closed\""
        val symbols = listOf(
            authenticationType,
            hostType,
            "type:AgentHookHandler:\"agent\" | \"prompt\"",
        ).sorted()
        val evidence = derive(
            listOf(browser, device, new, restoring, closed, hookAgent, hookPrompt).sorted(),
            symbols,
            references = listOf(authenticationType, hostType),
        )

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertEquals(setOf(hookAgent, hookPrompt), evidence.missingCapabilityKeys.toSet())
        assertEquals(
            setOf(browser, device, new, restoring, closed),
            evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).toSet(),
        )
    }

    @Test
    fun `object aliases reject wrong owner literal unreferenced evidence and arbitrary reuse`() {
        val browser = canonicalObject("CodexAuthenticationMethod.ChatGptBrowser")
        val wrongOwner = canonicalObject("OtherAuthenticationMethod.ChatGptBrowser")
        val authenticationType =
            "type:CodexAuthenticationMethod:\"chatgpt_browser\" | \"chatgpt_device_code\" | \"api_key\""
        val wrongLiteral = "type:CodexAuthenticationMethod:\"chatgpt_device_code\" | \"api_key\""

        assertTrue(derive(listOf(wrongOwner), listOf(authenticationType), references = listOf(authenticationType))
            .missingCapabilityKeys.contains(wrongOwner))
        assertTrue(derive(listOf(browser), listOf(wrongLiteral), references = listOf(wrongLiteral))
            .missingCapabilityKeys.contains(browser))
        assertTrue(derive(listOf(browser), listOf(authenticationType), references = emptyList())
            .errors.any { "Unreferenced exceptional" in it && browser in it })

        val arbitrary = canonicalEnumEntry("CodexAuthenticationMethod", "CHATGPT_BROWSER")
        val reused = derive(
            listOf(browser, arbitrary).sorted(),
            listOf(authenticationType),
            references = listOf(authenticationType),
        )
        assertTrue(reused.errors.any { "Reused" in it && browser in it && arbitrary in it })
        assertTrue(reused.projectionClaims.isEmpty())

        val classCapability = canonicalClass("CodexAuthenticationMethod.ChatGptBrowser")
        assertFailsWith<IllegalStateException> {
            derive(listOf(classCapability), listOf(authenticationType), references = listOf(authenticationType))
        }
        val malformedAbi = browser.replace("abi=example/CodexAuthenticationMethod.ChatGptBrowser", "abi=example/Wrong")
        assertFailsWith<IllegalStateException> {
            derive(listOf(malformedAbi), listOf(authenticationType), references = listOf(authenticationType))
        }
    }

    @Test
    fun `companion factories require a compiler-derived static method`() {
        val key = canonicalFunction(
            "Factory.Companion",
            "create",
            returnType = "kotlin/String!!",
            parameters = listOf("kotlin/String!!"),
        )
        val instanceSymbols = listOf(
            "class:Factory",
            "method:Factory#create:(value: string): string",
        ).sorted()
        val staticSymbols = listOf(
            "class:Factory",
            "method:Factory#create[static]:(value: string): string",
        ).sorted()

        assertTrue(derive(listOf(key), instanceSymbols).missingCapabilityKeys.contains(key))
        assertEquals(listOf(key), derive(listOf(key), staticSymbols).projectionClaims.map { it.capabilityKey })
    }

    @Test
    fun `state projection requires exact current callback and observation return types`() {
        val key = canonicalProperty(
            "Stream",
            "value",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/String!!>!!",
        )
        val classSymbol = "class:Stream"
        val getter = "getter:Stream#value:string"
        val observer = "method:Stream#observeValue:(listener: (value: string) => void): CodexObservation"
        listOf(
            listOf(classSymbol, "getter:Stream#value:number", observer),
            listOf(classSymbol, getter, "method:Stream#observeValue:(listener: (value: number) => void): CodexObservation"),
            listOf(classSymbol, getter, "method:Stream#observeValue:(listener: (value: string) => void): string"),
        ).forEach { symbols ->
            assertTrue(derive(listOf(key), symbols.sorted()).missingCapabilityKeys.contains(key))
        }

        assertEquals(listOf(key), derive(listOf(key), listOf(classSymbol, getter, observer).sorted())
            .projectionClaims.map { it.capabilityKey })
    }

    @Test
    fun `type matching rejects widened nullability wrong generics and Promise substitution`() {
        val nonNull = canonicalProperty("NonNull", "value", "kotlin/String!!")
        val strings = canonicalProperty(
            "Strings",
            "values",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val synchronous = canonicalFunction("Synchronous", "read", returnType = "kotlin/String!!")
        val evidence = derive(
            listOf(nonNull, strings, synchronous).sorted(),
            listOf(
                "class:NonNull",
                "class:Strings",
                "class:Synchronous",
                "getter:NonNull#value:string | null | undefined",
                "getter:Strings#values:ReadonlyArray<number>",
                "method:Synchronous#read:(): Promise<string>",
            ).sorted(),
        )

        assertEquals(setOf(nonNull, strings, synchronous), evidence.missingCapabilityKeys.toSet())
        assertTrue(evidence.projectionClaims.isEmpty())
    }

    @Test
    fun `signatures reject arbitrary parameters and finite aliases validate exact shapes`() {
        val run = canonicalFunction(
            "Runner",
            "run",
            suspendFunction = true,
            parameters = listOf("kotlin/String!!"),
        )
        val optionalMismatch = canonicalFunction(
            "OptionalRunner",
            "run",
            parameters = listOf("kotlin/String!!"),
        )
        val host = canonicalConstructor("CodexHost", listOf("example/CodexPlatform!!", "example/CodexClientInfo!!"))
        val select = canonicalFunction(
            "CodexHost",
            "selectWorkspace",
            suspendFunction = true,
            parameters = listOf("example/CodexWorkspaceSelection!!"),
        )
        val evidence = derive(
            listOf(run, optionalMismatch, host, select).sorted(),
            listOf(
                "class:CodexHost",
                "class:OptionalRunner",
                "class:Runner",
                "function:createCodexHost:(): CodexHost",
                "method:CodexHost#selectWorkspace:(path: number, signal?: AbortSignal | null | undefined): Promise<void>",
                "method:OptionalRunner#run:(value?: string): void",
                "method:Runner#run:(value: string, required: number): Promise<void>",
            ).sorted(),
        )

        assertEquals(setOf(run, optionalMismatch, host, select), evidence.missingCapabilityKeys.toSet())
    }

    @Test
    fun `host factory and workspace alias reject canonical shape mutations`() {
        val host = canonicalConstructor("CodexHost", listOf("example/CodexPlatform!!", "example/CodexClientInfo!!"))
        val select = canonicalFunction(
            "CodexHost",
            "selectWorkspace",
            suspendFunction = true,
            parameters = listOf("example/CodexWorkspaceSelection!!"),
        )
        val symbols = listOf(
            "class:CodexHost",
            "function:createCodexHost:(bundleDirectory: string, dataDirectory: string, clientName: string, clientTitle: string, clientVersion: string): CodexHost",
            "method:CodexHost#selectWorkspace:(path: string, signal?: AbortSignal | null | undefined): Promise<void>",
        ).sorted()
        assertEquals(
            setOf(host, select),
            derive(listOf(host, select).sorted(), symbols)
                .projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).toSet(),
        )
        val hostClaim = derive(listOf(host), symbols).projectionClaims.single()
        assertEquals(listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP), hostClaim.sharedScenarios)

        val changedHost = canonicalConstructor(
            "CodexHost",
            listOf("example/CodexPlatform!!", "example/CodexClientInfo!!", "kotlin/String!!"),
        )
        val changedSelect = canonicalFunction(
            "CodexHost",
            "selectWorkspace",
            suspendFunction = true,
            parameters = listOf("example/CodexWorkspaceSelection!!", "kotlin/String!!"),
        )
        assertEquals(
            setOf(changedHost, changedSelect),
            derive(listOf(changedHost, changedSelect).sorted(), symbols).missingCapabilityKeys.toSet(),
        )
    }

    @Test
    fun `ordinary value constructors require exact signatures and claim value conversion`() {
        val key = canonicalConstructor("Value", listOf("kotlin/String!!"))
        val symbol = "constructor:Value#(value: string)"
        val evidence = derive(listOf(key), listOf("class:Value", symbol).sorted())

        assertEquals(listOf(key), evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            evidence.projectionClaims.single().sharedScenarios)
        assertTrue(derive(listOf(key), listOf("class:Value", "constructor:Value#(value: number)").sorted())
            .missingCapabilityKeys.contains(key))
    }

    @Test
    fun `current immutable validation values project ten generic capabilities`() {
        val keys = listOf(
            canonicalConstructor(
                "AgentFormOption",
                listOf("kotlin/String!!", "kotlin/String!!", "kotlin/String?"),
                defaultParameterIndices = setOf(1, 2),
            ),
            canonicalProperty("AgentFormOption", "value", "kotlin/String!!"),
            canonicalProperty("AgentFormOption", "title", "kotlin/String!!"),
            canonicalProperty("AgentFormOption", "description", "kotlin/String?"),
            canonicalConstructor(
                "AgentElicitationValidationIssue",
                listOf("kotlin/String!!", "example/AgentElicitationValidationReason!!"),
            ),
            canonicalProperty("AgentElicitationValidationIssue", "fieldName", "kotlin/String!!"),
            canonicalProperty(
                "AgentElicitationValidationIssue",
                "reason",
                "example/AgentElicitationValidationReason!!",
            ),
            canonicalConstructor(
                "AgentElicitationValidation",
                listOf(
                    "kotlin.collections/List<INVARIANT:example/AgentElicitationValidationIssue!!>!!",
                ),
            ),
            canonicalProperty("AgentElicitationValidation", "isValid", "kotlin/Boolean!!"),
            canonicalProperty(
                "AgentElicitationValidation",
                "issues",
                "kotlin.collections/List<INVARIANT:example/AgentElicitationValidationIssue!!>!!",
            ),
        ).sorted()
        val evidence = derive(keys, currentPublicSymbols())

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(10, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.filter { "|kind=constructor|" in it.capabilityKey }.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
    }

    @Test
    fun `current immutable plan values project six generic capabilities and reject signature drift`() {
        val stepConstructor = canonicalConstructor(
            "AgentPlanStep",
            listOf("kotlin/String!!", "example/AgentPlanStepStatus!!"),
        )
        val stepStatus = canonicalProperty("AgentPlanStep", "status", "example/AgentPlanStepStatus!!")
        val stepText = canonicalProperty("AgentPlanStep", "text", "kotlin/String!!")
        val progressConstructor = canonicalConstructor(
            "AgentPlanProgress",
            listOf(
                "kotlin/String?",
                "kotlin.collections/List<INVARIANT:example/AgentPlanStep!!>!!",
            ),
            defaultParameterIndices = setOf(0, 1),
        )
        val progressExplanation = canonicalProperty("AgentPlanProgress", "explanation", "kotlin/String?")
        val progressSteps = canonicalProperty(
            "AgentPlanProgress",
            "steps",
            "kotlin.collections/List<INVARIANT:example/AgentPlanStep!!>!!",
        )
        val keys = listOf(
            stepConstructor,
            stepStatus,
            stepText,
            progressConstructor,
            progressExplanation,
            progressSteps,
        ).sorted()
        val symbols = currentPublicSymbols()
        val evidence = derive(keys, symbols)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(6, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })

        val unreferenced = derive(
            keys,
            symbols,
            references = symbols.filterNot { it.startsWith("constructor:AgentPlan") },
        )
        assertEquals(2, unreferenced.errors.count {
            "Unreferenced exceptional" in it && "AgentPlan" in it
        })
        assertEquals(
            setOf(stepStatus, stepText, progressExplanation, progressSteps),
            unreferenced.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).toSet(),
        )

        val stepConstructorSymbol =
            "constructor:AgentPlanStep#(text: string, status: AgentPlanStepStatus)"
        val progressConstructorSymbol =
            "constructor:AgentPlanProgress#" +
                "(explanation?: string | null | undefined, steps?: ReadonlyArray<AgentPlanStep>)"
        listOf(
            Triple(
                progressConstructor,
                progressConstructorSymbol,
                progressConstructorSymbol.replace("explanation?:", "explanation:"),
            ),
            Triple(
                progressConstructor,
                progressConstructorSymbol,
                progressConstructorSymbol.replace("steps?:", "steps:"),
            ),
            Triple(
                progressConstructor,
                progressConstructorSymbol,
                progressConstructorSymbol.replace("ReadonlyArray<AgentPlanStep>", "Array<AgentPlanStep>"),
            ),
            Triple(
                stepConstructor,
                stepConstructorSymbol,
                stepConstructorSymbol.replace("AgentPlanStepStatus", "string"),
            ),
            Triple(
                progressExplanation,
                "getter:AgentPlanProgress#explanation:string | null | undefined",
                "getter:AgentPlanProgress#explanation:string",
            ),
            Triple(
                progressSteps,
                "getter:AgentPlanProgress#steps:ReadonlyArray<AgentPlanStep>",
                "getter:AgentPlanProgress#steps:Array<AgentPlanStep>",
            ),
        ).forEach { (key, exact, drifted) ->
            val drift = derive(keys, symbols.map { if (it == exact) drifted else it }.sorted())
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }
    }

    @Test
    fun `hook activity and nested turn progress values preserve exact immutable shapes`() {
        val hookConstructor = canonicalConstructor(
            "AgentHookActivity",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "example/AgentHookRunStatus!!",
                "kotlin/String?",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
            ),
            defaultParameterIndices = setOf(4, 5),
        )
        val hookDetails = canonicalProperty(
            "AgentHookActivity",
            "details",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val hookEventName = canonicalProperty("AgentHookActivity", "eventName", "kotlin/String!!")
        val hookHandlerType = canonicalProperty("AgentHookActivity", "handlerType", "kotlin/String!!")
        val hookId = canonicalProperty("AgentHookActivity", "id", "kotlin/String!!")
        val hookStatus = canonicalProperty("AgentHookActivity", "status", "example/AgentHookRunStatus!!")
        val hookStatusMessage = canonicalProperty("AgentHookActivity", "statusMessage", "kotlin/String?")
        val turnHookActivities = canonicalProperty(
            "AgentTurnProgress",
            "hookActivities",
            "kotlin.collections/List<INVARIANT:example/AgentHookActivity!!>!!",
        )
        val turnPlanProgress = canonicalProperty(
            "AgentTurnProgress",
            "planProgress",
            "example/AgentPlanProgress?",
        )
        val keys = listOf(
            hookConstructor,
            hookDetails,
            hookEventName,
            hookHandlerType,
            hookId,
            hookStatus,
            hookStatusMessage,
            turnHookActivities,
            turnPlanProgress,
        ).sorted()
        val hookConstructorSymbol =
            "constructor:AgentHookActivity#" +
                "(id: string, eventName: string, handlerType: string, status: AgentHookRunStatus, " +
                "statusMessage?: string | null | undefined, details?: ReadonlyArray<string>)"
        val hookDetailsSymbol = "getter:AgentHookActivity#details:ReadonlyArray<string>"
        val hookEventNameSymbol = "getter:AgentHookActivity#eventName:string"
        val hookHandlerTypeSymbol = "getter:AgentHookActivity#handlerType:string"
        val hookIdSymbol = "getter:AgentHookActivity#id:string"
        val hookStatusSymbol = "getter:AgentHookActivity#status:AgentHookRunStatus"
        val hookStatusMessageSymbol =
            "getter:AgentHookActivity#statusMessage:string | null | undefined"
        val turnHookActivitiesSymbol =
            "getter:CodexTurnProgress#hookActivities:ReadonlyArray<AgentHookActivity>"
        val turnPlanProgressSymbol =
            "getter:CodexTurnProgress#planProgress:AgentPlanProgress | null | undefined"
        val addedSymbols = listOf(
            "class:AgentHookActivity",
            hookConstructorSymbol,
            hookDetailsSymbol,
            hookEventNameSymbol,
            hookHandlerTypeSymbol,
            hookIdSymbol,
            hookStatusSymbol,
            hookStatusMessageSymbol,
            turnHookActivitiesSymbol,
            turnPlanProgressSymbol,
        ).sorted()
        val symbols = (addedSymbols + "class:CodexTurnProgress").sorted()
        val references = addedSymbols.filterNot { it.startsWith("class:") }
        val evidence = derive(keys, symbols, references = references)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(10, addedSymbols.size)
        assertEquals(9, references.size)
        assertEquals(9, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(symbols, evidence.packedApi.publicSymbols)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        assertTrue(symbols.none {
            it == "class:AgentTurnProgress" || it.startsWith("constructor:AgentTurnProgress#") ||
                it.startsWith("constructor:CodexTurnProgress#")
        })

        listOf(
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("AgentHookRunStatus", "string"),
            ),
            Triple(
                hookStatus,
                hookStatusSymbol,
                hookStatusSymbol.replace("AgentHookRunStatus", "string"),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("ReadonlyArray<string>", "Array<string>"),
            ),
            Triple(
                hookDetails,
                hookDetailsSymbol,
                hookDetailsSymbol.replace("ReadonlyArray<string>", "Array<string>"),
            ),
            Triple(
                turnHookActivities,
                turnHookActivitiesSymbol,
                turnHookActivitiesSymbol.replace(
                    "ReadonlyArray<AgentHookActivity>",
                    "Array<AgentHookActivity>",
                ),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("statusMessage?:", "statusMessage:"),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("details?:", "details:"),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("id:", "id?:"),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace("string | null | undefined", "string"),
            ),
            Triple(
                hookStatusMessage,
                hookStatusMessageSymbol,
                hookStatusMessageSymbol.replace("string | null | undefined", "string"),
            ),
            Triple(
                turnPlanProgress,
                turnPlanProgressSymbol,
                turnPlanProgressSymbol.replace(
                    "AgentPlanProgress | null | undefined",
                    "AgentPlanProgress",
                ),
            ),
            Triple(
                turnHookActivities,
                turnHookActivitiesSymbol,
                turnHookActivitiesSymbol.replace("AgentHookActivity", "AgentPlanStep"),
            ),
            Triple(
                turnPlanProgress,
                turnPlanProgressSymbol,
                turnPlanProgressSymbol.replace("AgentPlanProgress", "AgentHookActivity"),
            ),
            Triple(
                hookConstructor,
                hookConstructorSymbol,
                hookConstructorSymbol.replace(")", ", unexpected?: string)"),
            ),
        ).forEach { (key, exact, drifted) ->
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        val unreferenced = derive(
            keys,
            symbols,
            references = references.filterNot { it == hookConstructorSymbol },
        )
        assertTrue(unreferenced.errors.any {
            "Unreferenced exceptional" in it && "AgentHookActivity" in it
        })
        assertEquals(
            keys.filterNot { it == hookConstructor },
            unreferenced.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey),
        )
    }

    @Test
    fun `nested form values map four finite owners and reject signature drift`() {
        val shapes = listOf(
            Triple("AgentFormValue.BooleanValue", "AgentFormBooleanValue", "kotlin/Boolean!!" to "boolean"),
            Triple("AgentFormValue.Number", "AgentFormNumberValue", "kotlin/Double!!" to "number"),
            Triple("AgentFormValue.Text", "AgentFormTextValue", "kotlin/String!!" to "string"),
            Triple(
                "AgentFormValue.TextList",
                "AgentFormTextListValue",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!" to "ReadonlyArray<string>",
            ),
        )
        val keys = shapes.flatMap { (canonicalOwner, _, types) ->
            listOf(
                canonicalConstructor(canonicalOwner, listOf(types.first)),
                canonicalProperty(canonicalOwner, "value", types.first),
            )
        }.sorted()
        val symbols = shapes.flatMap { (_, javascriptOwner, types) ->
            listOf(
                "class:$javascriptOwner",
                "constructor:$javascriptOwner#(value: ${types.second})",
                "getter:$javascriptOwner#value:${types.second}",
            )
        }.sorted()
        val evidence = derive(keys, symbols)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(8, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(symbols, evidence.packedApi.publicSymbols)
        assertEquals(symbols, evidence.packedApi.referencedSymbols)
        assertTrue(symbols.none { it == "class:AgentFormValue" || it.startsWith("type:AgentFormValue:") })

        val wrongTypes = mapOf(
            "boolean" to "string",
            "number" to "string",
            "string" to "number",
            "ReadonlyArray<string>" to "ReadonlyArray<number>",
        )
        val driftCases = shapes.flatMap { (canonicalOwner, javascriptOwner, types) ->
            val wrongType = checkNotNull(wrongTypes[types.second])
            listOf(
                Triple(
                    canonicalConstructor(canonicalOwner, listOf(types.first)),
                    "constructor:$javascriptOwner#(value: ${types.second})",
                    "constructor:$javascriptOwner#(value: $wrongType)",
                ),
                Triple(
                    canonicalProperty(canonicalOwner, "value", types.first),
                    "getter:$javascriptOwner#value:${types.second}",
                    "getter:$javascriptOwner#value:$wrongType",
                ),
            )
        } + listOf(
            Triple(
                canonicalConstructor(
                    "AgentFormValue.TextList",
                    listOf("kotlin.collections/List<INVARIANT:kotlin/String!!>!!"),
                ),
                "constructor:AgentFormTextListValue#(value: ReadonlyArray<string>)",
                "constructor:AgentFormTextListValue#(value: Array<string>)",
            ),
            Triple(
                canonicalProperty(
                    "AgentFormValue.TextList",
                    "value",
                    "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                ),
                "getter:AgentFormTextListValue#value:ReadonlyArray<string>",
                "getter:AgentFormTextListValue#value:Array<string>",
            ),
        )
        driftCases.forEach { (key, exact, drifted) ->
            val drift = derive(keys, symbols.map { if (it == exact) drifted else it }.sorted())
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        val unreferenced = derive(
            keys,
            symbols,
            references = symbols.filterNot { it.startsWith("constructor:AgentForm") },
        )
        assertEquals(4, unreferenced.errors.count { "Unreferenced exceptional" in it })
        assertEquals(4, unreferenced.projectionClaims.size)

        listOf("AgentFormValue.Other" to "AgentFormOtherValue", "Other.Text" to "AgentFormTextValue")
            .forEach { (canonicalOwner, javascriptOwner) ->
                val key = canonicalConstructor(canonicalOwner, listOf("kotlin/String!!"))
                val unrelated = listOf(
                    "class:$javascriptOwner",
                    "constructor:$javascriptOwner#(value: string)",
                )
                assertTrue(key in derive(listOf(key), unrelated.sorted()).missingCapabilityKeys)
            }
    }

    @Test
    fun `MCP tool configuration preserves nullable approval alias and default`() {
        val constructor = canonicalConstructor(
            "AgentMcpToolConfiguration",
            listOf("example/AgentMcpToolApproval?"),
            defaultParameterIndices = setOf(0),
        )
        val approval = canonicalProperty(
            "AgentMcpToolConfiguration",
            "approval",
            "example/AgentMcpToolApproval?",
        )
        val keys = listOf(constructor, approval).sorted()
        val constructorSymbol =
            "constructor:AgentMcpToolConfiguration#" +
                "(approval?: AgentMcpToolApproval | null | undefined)"
        val getterSymbol =
            "getter:AgentMcpToolConfiguration#approval:AgentMcpToolApproval | null | undefined"
        val symbols = listOf(
            "class:AgentMcpToolConfiguration",
            constructorSymbol,
            getterSymbol,
        ).sorted()
        val references = listOf(constructorSymbol, getterSymbol).sorted()
        val evidence = derive(keys, symbols, references = references)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(2, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(symbols, evidence.packedApi.publicSymbols)
        assertEquals(references, evidence.packedApi.referencedSymbols)

        listOf(
            Triple(
                constructor,
                constructorSymbol,
                constructorSymbol.replace("AgentMcpToolApproval", "string"),
            ),
            Triple(
                approval,
                getterSymbol,
                getterSymbol.replace("AgentMcpToolApproval", "string"),
            ),
            Triple(
                constructor,
                constructorSymbol,
                constructorSymbol.replace(
                    "AgentMcpToolApproval | null | undefined",
                    "AgentMcpToolApproval",
                ),
            ),
            Triple(
                approval,
                getterSymbol,
                getterSymbol.replace(
                    "AgentMcpToolApproval | null | undefined",
                    "AgentMcpToolApproval",
                ),
            ),
            Triple(
                constructor,
                constructorSymbol,
                constructorSymbol.replace("approval?:", "approval:"),
            ),
            Triple(
                constructor,
                constructorSymbol,
                constructorSymbol.replace(
                    ")",
                    ", unexpected?: string)",
                ),
            ),
        ).forEach { (key, exact, drifted) ->
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        val unreferenced = derive(keys, symbols, references = listOf(getterSymbol))
        assertTrue(unreferenced.errors.any {
            "Unreferenced exceptional" in it && "AgentMcpToolConfiguration" in it
        })
        assertEquals(listOf(approval), unreferenced.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
    }

    @Test
    fun `MCP environment and OAuth configurations preserve nullable defaults and aliases`() {
        val environmentConstructor = canonicalConstructor(
            "AgentMcpEnvironmentVariable",
            listOf("kotlin/String!!", "example/AgentMcpEnvironmentSource?"),
            defaultParameterIndices = setOf(1),
        )
        val environmentName = canonicalProperty("AgentMcpEnvironmentVariable", "name", "kotlin/String!!")
        val environmentSource = canonicalProperty(
            "AgentMcpEnvironmentVariable",
            "source",
            "example/AgentMcpEnvironmentSource?",
        )
        val oauthConstructor = canonicalConstructor(
            "AgentMcpOauthConfiguration",
            listOf("kotlin/String?", "kotlin/Int?"),
            defaultParameterIndices = setOf(0, 1),
        )
        val oauthClientId = canonicalProperty("AgentMcpOauthConfiguration", "clientId", "kotlin/String?")
        val oauthCallbackPort = canonicalProperty("AgentMcpOauthConfiguration", "callbackPort", "kotlin/Int?")
        val keys = listOf(
            environmentConstructor,
            environmentName,
            environmentSource,
            oauthConstructor,
            oauthClientId,
            oauthCallbackPort,
        ).sorted()
        val environmentConstructorSymbol =
            "constructor:AgentMcpEnvironmentVariable#" +
                "(name: string, source?: AgentMcpEnvironmentSource | null | undefined)"
        val environmentNameSymbol = "getter:AgentMcpEnvironmentVariable#name:string"
        val environmentSourceSymbol =
            "getter:AgentMcpEnvironmentVariable#source:AgentMcpEnvironmentSource | null | undefined"
        val oauthConstructorSymbol =
            "constructor:AgentMcpOauthConfiguration#" +
                "(clientId?: string | null | undefined, callbackPort?: number | null | undefined)"
        val oauthClientIdSymbol =
            "getter:AgentMcpOauthConfiguration#clientId:string | null | undefined"
        val oauthCallbackPortSymbol =
            "getter:AgentMcpOauthConfiguration#callbackPort:number | null | undefined"
        val symbols = listOf(
            "class:AgentMcpEnvironmentVariable",
            "class:AgentMcpOauthConfiguration",
            environmentConstructorSymbol,
            environmentNameSymbol,
            environmentSourceSymbol,
            oauthConstructorSymbol,
            oauthClientIdSymbol,
            oauthCallbackPortSymbol,
        ).sorted()
        val references = symbols.filterNot { it.startsWith("class:") }
        val evidence = derive(keys, symbols, references = references)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(6, evidence.projectionClaims.size)
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(symbols, evidence.packedApi.publicSymbols)
        assertEquals(references, evidence.packedApi.referencedSymbols)

        listOf(
            Triple(
                environmentConstructor,
                environmentConstructorSymbol,
                environmentConstructorSymbol.replace("AgentMcpEnvironmentSource", "string"),
            ),
            Triple(
                environmentSource,
                environmentSourceSymbol,
                environmentSourceSymbol.replace("AgentMcpEnvironmentSource", "string"),
            ),
            Triple(
                environmentConstructor,
                environmentConstructorSymbol,
                environmentConstructorSymbol.replace(
                    "AgentMcpEnvironmentSource | null | undefined",
                    "AgentMcpEnvironmentSource",
                ),
            ),
            Triple(
                environmentSource,
                environmentSourceSymbol,
                environmentSourceSymbol.replace(
                    "AgentMcpEnvironmentSource | null | undefined",
                    "AgentMcpEnvironmentSource",
                ),
            ),
            Triple(
                environmentConstructor,
                environmentConstructorSymbol,
                environmentConstructorSymbol.replace("name:", "name?:"),
            ),
            Triple(
                environmentConstructor,
                environmentConstructorSymbol,
                environmentConstructorSymbol.replace("source?:", "source:"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace("clientId?:", "clientId:"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace(
                    "clientId?: string | null | undefined",
                    "clientId?: string",
                ),
            ),
            Triple(
                oauthClientId,
                oauthClientIdSymbol,
                oauthClientIdSymbol.replace("string | null | undefined", "string"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace("number | null | undefined", "bigint | null | undefined"),
            ),
            Triple(
                oauthCallbackPort,
                oauthCallbackPortSymbol,
                oauthCallbackPortSymbol.replace("number | null | undefined", "bigint | null | undefined"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace("number | null | undefined", "number"),
            ),
            Triple(
                oauthCallbackPort,
                oauthCallbackPortSymbol,
                oauthCallbackPortSymbol.replace("number | null | undefined", "number"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace("callbackPort?:", "callbackPort:"),
            ),
            Triple(
                environmentConstructor,
                environmentConstructorSymbol,
                environmentConstructorSymbol.replace(")", ", unexpected?: string)"),
            ),
            Triple(
                oauthConstructor,
                oauthConstructorSymbol,
                oauthConstructorSymbol.replace(")", ", unexpected?: string)"),
            ),
        ).forEach { (key, exact, drifted) ->
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        val unreferenced = derive(
            keys,
            symbols,
            references = references.filterNot { it.startsWith("constructor:AgentMcp") },
        )
        assertEquals(2, unreferenced.errors.count { "Unreferenced exceptional" in it })
        assertEquals(
            setOf(environmentName, environmentSource, oauthClientId, oauthCallbackPort),
            unreferenced.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).toSet(),
        )
    }

    @Test
    fun `authentication projection requires the exact canonical shape and all three referenced overloads`() {
        val key = canonicalFunction(
            "CodexAuthentication",
            "authenticate",
            suspendFunction = true,
            parameters = listOf("example/CodexAuthenticationMethod!!"),
            defaultParameterIndices = setOf(0),
        )
        val symbols = (listOf("class:CodexAuthentication") + AUTHENTICATION_OVERLOADS).sorted()
        val evidence = derive(listOf(key), symbols)

        assertEquals(listOf(key), evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(
            AUTHENTICATION_OVERLOADS.sorted(),
            evidence.projectionClaims.single().publicSymbols,
        )
        assertTrue(CrossLanguageBindingScenario.CANCELLATION in evidence.projectionClaims.single().sharedScenarios)

        listOf(
            AUTHENTICATION_OVERLOADS.dropLast(1),
            AUTHENTICATION_OVERLOADS.mapIndexed { index, symbol ->
                if (index == 0) symbol.replace("apiKey: string", "apiKey?: string") else symbol
            },
            AUTHENTICATION_OVERLOADS +
                "method:CodexAuthentication#authenticate:(method: string): Promise<void>",
        ).forEach { overloads ->
            assertTrue(derive(listOf(key), (listOf("class:CodexAuthentication") + overloads).sorted())
                .missingCapabilityKeys.contains(key))
        }

        val unreferenced = derive(listOf(key), symbols, references = AUTHENTICATION_OVERLOADS.dropLast(1).sorted())
        assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
        assertTrue(unreferenced.projectionClaims.isEmpty())

        listOf(
            canonicalFunction(
                "CodexAuthentication",
                "authenticate",
                suspendFunction = false,
                parameters = listOf("example/CodexAuthenticationMethod!!"),
                defaultParameterIndices = setOf(0),
            ),
            canonicalFunction(
                "CodexAuthentication",
                "authenticate",
                suspendFunction = true,
                parameters = listOf("example/CodexAuthenticationMethod!!"),
            ),
            canonicalFunction(
                "CodexAuthentication",
                "authenticate",
                suspendFunction = true,
                parameters = listOf("kotlin/String!!"),
                defaultParameterIndices = setOf(0),
            ),
        ).forEach { changedCanonical ->
            assertTrue(derive(listOf(changedCanonical), symbols).missingCapabilityKeys.contains(changedCanonical))
        }
    }

    @Test
    fun `conversation rename and delete project as referenced asynchronous agent methods`() {
        val rename = canonicalFunction(
            "CodexConversations",
            "rename",
            suspendFunction = true,
            parameters = listOf("example/ConversationId!!", "kotlin/String!!"),
        )
        val delete = canonicalFunction(
            "CodexConversations",
            "delete",
            suspendFunction = true,
            parameters = listOf("example/ConversationId!!"),
        )
        val keys = listOf(delete, rename).sorted()
        val methods = listOf(DELETE_CONVERSATION, RENAME_CONVERSATION).sorted()
        val symbols = (methods + "class:CodexAgent").sorted()
        val evidence = derive(keys, symbols, references = methods)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(methods, evidence.packedApi.referencedSymbols)
        assertEquals(
            mapOf(delete to listOf(DELETE_CONVERSATION), rename to listOf(RENAME_CONVERSATION)),
            evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols },
        )
        assertTrue(evidence.projectionClaims.all {
            it.sharedScenarios.toSet() == setOf(
                CrossLanguageBindingScenario.ASYNC_SUCCESS,
                CrossLanguageBindingScenario.ASYNC_FAILURE,
            )
        })

        listOf(
            Triple(
                rename,
                RENAME_CONVERSATION,
                RENAME_CONVERSATION.replace("conversationId: string", "conversationId: ConversationId"),
            ),
            Triple(
                delete,
                DELETE_CONVERSATION,
                DELETE_CONVERSATION.replace(
                    "signal?: AbortSignal | null | undefined",
                    "signal: AbortSignal",
                ),
            ),
            Triple(
                delete,
                DELETE_CONVERSATION,
                DELETE_CONVERSATION.replace("Promise<void>", "Promise<string>"),
            ),
        ).forEach { (key, exact, drifted) ->
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = methods.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "$key accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        methods.forEach { unreferencedMethod ->
            val unreferenced = derive(keys, symbols, references = methods - unreferencedMethod)
            assertTrue(unreferenced.errors.any {
                "Unreferenced exceptional" in it && unreferencedMethod in it
            })
            assertEquals(1, unreferenced.projectionClaims.size)
        }
    }

    @Test
    fun `open projection requires exact defaulted settings flattening and one public overload`() {
        val key = canonicalFunction(
            "CodexConversations",
            "open",
            returnType = "example/CodexConversation!!",
            suspendFunction = true,
            parameters = listOf("example/ConversationId?", "example/AgentConversationSettings!!"),
            defaultParameterIndices = setOf(0, 1),
        )
        val symbols = listOf("class:CodexAgent", OPEN_CONVERSATION).sorted()
        val evidence = derive(listOf(key), symbols)

        assertEquals(listOf(key), evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(listOf(OPEN_CONVERSATION), evidence.projectionClaims.single().publicSymbols)
        assertTrue(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP in evidence.projectionClaims.single().sharedScenarios)

        listOf(
            OPEN_CONVERSATION.replace("conversationId?:", "conversationId:"),
            OPEN_CONVERSATION.replace("serviceTier?: string", "serviceTier?: number"),
            OPEN_CONVERSATION.replace(": Promise<CodexConversation>", ": Promise<void>"),
        ).forEach { wrong ->
            assertTrue(derive(listOf(key), listOf("class:CodexAgent", wrong).sorted())
                .missingCapabilityKeys.contains(key))
        }
        assertTrue(derive(
            listOf(key),
            (symbols + "method:CodexAgent#openConversation:(): Promise<CodexConversation>").sorted(),
        ).missingCapabilityKeys.contains(key))

        val changedCanonical = canonicalFunction(
            "CodexConversations",
            "open",
            returnType = "example/CodexConversation!!",
            suspendFunction = true,
            parameters = listOf("example/ConversationId?", "example/AgentConversationSettings!!"),
            defaultParameterIndices = setOf(0),
        )
        assertTrue(derive(listOf(changedCanonical), symbols).missingCapabilityKeys.contains(changedCanonical))
        val unreferenced = derive(listOf(key), symbols, references = emptyList())
        assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
        assertTrue(unreferenced.projectionClaims.isEmpty())
    }

    @Test
    fun `seven finite flattened value members reuse only their exact reviewed SDK symbols`() {
        val settingsConstructor = canonicalConstructor(
            "AgentConversationSettings",
            listOf("example/AgentApprovalPreset!!", "kotlin/String?"),
            defaultParameterIndices = setOf(0, 1),
        )
        val settingsApproval = canonicalProperty(
            "AgentConversationSettings",
            "approvalPreset",
            "example/AgentApprovalPreset!!",
        )
        val settingsServiceTier =
            canonicalProperty("AgentConversationSettings", "serviceTier", "kotlin/String?")
        val conversationIdConstructor = canonicalConstructor("ConversationId", listOf("kotlin/String!!"))
        val conversationIdValue = canonicalProperty("ConversationId", "value", "kotlin/String!!")
        val pathConstructor =
            canonicalConstructor("CodexPathWorkspaceSelection", listOf("kotlin/String!!"))
        val pathValue = canonicalProperty("CodexPathWorkspaceSelection", "path", "kotlin/String!!")
        val flattened = listOf(
            settingsConstructor,
            settingsApproval,
            settingsServiceTier,
            conversationIdConstructor,
            conversationIdValue,
            pathConstructor,
            pathValue,
        ).sorted()
        val ordinary = listOf(
            canonicalFunction(
                "CodexConversations",
                "open",
                returnType = "example/CodexConversation!!",
                suspendFunction = true,
                parameters = listOf("example/ConversationId?", "example/AgentConversationSettings!!"),
                defaultParameterIndices = setOf(0, 1),
            ),
            canonicalFunction(
                "CodexConversations",
                "rename",
                suspendFunction = true,
                parameters = listOf("example/ConversationId!!", "kotlin/String!!"),
            ),
            canonicalFunction(
                "CodexConversations",
                "delete",
                suspendFunction = true,
                parameters = listOf("example/ConversationId!!"),
            ),
            canonicalProperty("AgentConversationState", "conversationId", "example/ConversationId?"),
            canonicalFunction(
                "CodexHost",
                "selectWorkspace",
                suspendFunction = true,
                parameters = listOf("example/CodexWorkspaceSelection!!"),
            ),
        )
        val symbols = listOf(
            "class:CodexAgent",
            "class:CodexConversationState",
            "class:CodexHost",
            OPEN_CONVERSATION,
            RENAME_CONVERSATION,
            DELETE_CONVERSATION,
            CONVERSATION_ID_GETTER,
            SELECT_WORKSPACE,
        ).sorted()
        val evidence = derive(flattened + ordinary, symbols, references = symbols)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(12, evidence.projectionClaims.size)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        listOf(settingsConstructor, settingsApproval, settingsServiceTier).forEach { key ->
            assertEquals(listOf(OPEN_CONVERSATION), claims.getValue(key).publicSymbols)
        }
        listOf(conversationIdConstructor, conversationIdValue).forEach { key ->
            assertEquals(
                listOf(DELETE_CONVERSATION, OPEN_CONVERSATION, RENAME_CONVERSATION).sorted(),
                claims.getValue(key).publicSymbols,
            )
        }
        listOf(pathConstructor, pathValue).forEach { key ->
            assertEquals(listOf(SELECT_WORKSPACE), claims.getValue(key).publicSymbols)
        }

        listOf(
            settingsConstructor.replace("default=true", "default=false"),
            settingsApproval.replace("example/AgentApprovalPreset!!", "kotlin/String!!"),
            settingsServiceTier.replace("serviceTier", "futureTier"),
            conversationIdConstructor.replace("kotlin/String!!", "kotlin/Int!!"),
            pathConstructor.replace("CodexPathWorkspaceSelection.<init>", "CodexPathWorkspaceSelection.future"),
            pathValue.replace("propertyKind=VAL", "propertyKind=VAR"),
        ).forEach { malformed ->
            val rejected = derive(listOf(malformed), symbols, references = symbols)
            assertEquals(listOf(malformed), rejected.missingCapabilityKeys, "Accepted malformed key: $malformed")
            assertTrue(rejected.projectionClaims.isEmpty())
        }
        assertFailsWith<IllegalStateException> {
            derive(
                listOf(conversationIdValue.replace("kind=property", "kind=function")),
                symbols,
                references = symbols,
            )
        }
        listOf(
            settingsApproval to listOf("class:CodexAgent", OPEN_CONVERSATION).sorted(),
            conversationIdValue to listOf(
                "class:CodexAgent",
                DELETE_CONVERSATION,
                OPEN_CONVERSATION,
                RENAME_CONVERSATION,
            ).sorted(),
            pathValue to listOf("class:CodexHost", SELECT_WORKSPACE).sorted(),
        ).forEach { (key, projectedSymbols) ->
            val foreign = key.replace("example/", "foreign/")
            val crossPackage = derive(
                listOf(key, foreign).sorted(),
                projectedSymbols,
                references = projectedSymbols,
            )
            assertTrue(crossPackage.errors.any { "Reused" in it })
            assertTrue(crossPackage.projectionClaims.isEmpty())
        }
        val future = pathValue.replace("CodexPathWorkspaceSelection", "CodexPathWorkspaceSelection.Future")
        assertEquals(listOf(future), derive(listOf(future), symbols, references = symbols).missingCapabilityKeys)

        val overloads = (symbols +
            OPEN_CONVERSATION.replace("Promise<CodexConversation>", "Promise<void>")).sorted()
        assertEquals(
            listOf(settingsConstructor),
            derive(listOf(settingsConstructor), overloads, references = overloads).missingCapabilityKeys,
        )
        val unreferenced = derive(
            listOf(conversationIdConstructor),
            symbols,
            references = symbols - DELETE_CONVERSATION,
        )
        assertTrue(unreferenced.errors.single().contains("Unreferenced exceptional"))
        assertTrue(unreferenced.projectionClaims.isEmpty())
    }

    @Test
    fun `approval preset display name requires one exact referenced public function`() {
        val key = canonicalProperty("AgentApprovalPreset", "displayName", "kotlin/String!!")
        val evidence = derive(
            listOf(key),
            listOf(APPROVAL_PRESET_DISPLAY_NAME),
            references = listOf(APPROVAL_PRESET_DISPLAY_NAME),
        )

        assertEquals(listOf(key), evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(listOf(APPROVAL_PRESET_DISPLAY_NAME), evidence.projectionClaims.single().publicSymbols)
        listOf(
            APPROVAL_PRESET_DISPLAY_NAME.replace("CodexApprovalPreset", "string"),
            APPROVAL_PRESET_DISPLAY_NAME.replace("): string", "): number"),
            APPROVAL_PRESET_DISPLAY_NAME.replace("preset:", "preset?:"),
        ).forEach { drifted ->
            assertEquals(
                listOf(key),
                derive(listOf(key), listOf(drifted), references = listOf(drifted)).missingCapabilityKeys,
            )
        }
        val overloads = listOf(
            APPROVAL_PRESET_DISPLAY_NAME,
            APPROVAL_PRESET_DISPLAY_NAME.replace("preset:", "preset?:"),
        ).sorted()
        assertFailsWith<IllegalStateException> {
            derive(listOf(key), overloads, references = overloads)
        }
        val unreferenced = derive(listOf(key), listOf(APPROVAL_PRESET_DISPLAY_NAME), references = emptyList())
        assertTrue(unreferenced.errors.single().contains("Unreferenced exceptional"))
        assertTrue(unreferenced.projectionClaims.isEmpty())
        val literalOnly = "type:CodexApprovalPreset:\"ask_me\" | \"auto_review\" | \"never\" | \"strict\""
        assertEquals(listOf(key), derive(listOf(key), listOf(literalOnly)).missingCapabilityKeys)
    }

    @Test
    fun `twelve exact SDK-created constructors alone receive narrow JavaScript exclusions`() {
        val keys = sdkCreatedConstructorKeys()
        val evidence = derive(keys, listOf("class:Unrelated"), references = emptyList())

        assertEquals(12, keys.size)
        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.projectionClaims.isEmpty())
        assertEquals(keys, evidence.applicabilityExclusions.map(CrossLanguageApplicabilityExclusion::capabilityKey))
        assertEquals(setOf(CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT),
            evidence.applicabilityExclusions.map(CrossLanguageApplicabilityExclusion::language).toSet())
        assertEquals(
            mapOf(
                "JavaScript receives this canonical immutable snapshot from the SDK; " +
                    "its constructor is intentionally private." to 6,
                "JavaScript receives this canonical state variant from the SDK; " +
                    "its constructor is intentionally private." to 6,
            ),
            evidence.applicabilityExclusions.groupingBy(CrossLanguageApplicabilityExclusion::reason).eachCount(),
        )

        sdkCreatedConstructorShapes().forEach { shape ->
            val exact = canonicalConstructor(shape.owner, shape.parameters, shape.defaultParameterIndices)
            val wrongType = canonicalConstructor(
                shape.owner,
                shape.parameters + "kotlin/String!!",
                shape.defaultParameterIndices,
            )
            val wrongDefault = canonicalConstructor(
                shape.owner,
                shape.parameters,
                if (0 in shape.defaultParameterIndices) {
                    shape.defaultParameterIndices - 0
                } else {
                    shape.defaultParameterIndices + 0
                },
            )
            val wrongOwner = exact.replace("example/${shape.owner}", "example/${shape.owner}.Future")
            val wrongAbi = exact.replace("${shape.owner}.<init>", "${shape.owner}.future")
            val wrongKind = exact.replace("kind=constructor", "kind=function")
            val property = canonicalProperty(shape.owner, "future", "kotlin/String!!")
            listOf(wrongType, wrongDefault, wrongOwner, wrongAbi, wrongKind, property).forEach { rejected ->
                val result = derive(listOf(rejected), listOf("class:Unrelated"), references = emptyList())
                assertTrue(result.applicabilityExclusions.isEmpty(), "Excluded malformed key: $rejected")
                assertEquals(listOf(rejected), result.missingCapabilityKeys)
            }
        }

        val futureVariant = canonicalConstructor(
            "CodexHostState.Future",
            listOf("example/CodexWorkspace!!"),
        )
        assertEquals(
            listOf(futureVariant),
            derive(listOf(futureVariant), listOf("class:Unrelated"), references = emptyList())
                .missingCapabilityKeys,
        )
    }

    @Test
    fun `SDK constructor exclusions conflict with every public constructor shape`() {
        val key = sdkCreatedConstructorKeys().single { "owner=example/CodexFailure|" in it }
        listOf(
            "constructor:CodexFailure#(code: string, message: string, recoverable: boolean)",
            "constructor:CodexFailure#()",
            "constructor:CodexFailure#(code: number)",
        ).forEach { constructor ->
            val evidence = derive(
                listOf(key),
                listOf("class:CodexFailure", constructor),
                references = listOf(constructor),
            )

            assertTrue(evidence.errors.single().contains("conflicts with applicability exclusion"))
            assertTrue(evidence.projectionClaims.isEmpty())
            assertTrue(evidence.applicabilityExclusions.isEmpty())
            assertTrue(evidence.missingCapabilityKeys.isEmpty())
        }
    }

    @Test
    fun `conversation StateFlows share only the exact aggregate envelope and retain unique typed leaves`() {
        val aggregateKeys = conversationStateFlowKeys()
        val keys = aggregateKeys + conversationOrdinaryStateKeys()
        val symbols = conversationStateSymbols()
        val evidence = derive(keys, symbols)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertEquals(11, evidence.projectionClaims.size)
        val aggregateClaims = evidence.projectionClaims.filter {
            "|owner=example/CodexConversation|" in it.capabilityKey
        }
        assertEquals(8, aggregateClaims.size)
        aggregateClaims.forEach { claim ->
            assertTrue(CONVERSATION_STATE_GETTER in claim.publicSymbols)
            assertTrue(CONVERSATION_STATE_OBSERVER in claim.publicSymbols)
            assertEquals(
                setOf(
                    CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                    CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                    CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
                ),
                claim.sharedScenarios.toSet(),
            )
        }
        val ordinaryClaims = evidence.projectionClaims.filter {
            "|owner=example/AgentConversationState|" in it.capabilityKey
        }
        assertEquals(3, ordinaryClaims.size)
        ordinaryClaims.forEach { claim ->
            assertEquals(1, claim.publicSymbols.size)
            assertTrue(claim.publicSymbols.single().startsWith("getter:CodexConversationState#"))
        }
        assertEquals(
            listOf("getter:CodexConversationState#turnProgress:CodexTurnProgress | null | undefined"),
            evidence.projectionClaims.single { "activeTurnProgress" in it.capabilityKey }.publicSymbols
                .filter { it !in setOf(CONVERSATION_STATE_GETTER, CONVERSATION_STATE_OBSERVER) },
        )
        assertEquals(
            listOf("getter:CodexConversationState#messages:ReadonlyArray<CodexMessage>"),
            evidence.projectionClaims.single { "currentMessages" in it.capabilityKey }.publicSymbols
                .filter { it !in setOf(CONVERSATION_STATE_GETTER, CONVERSATION_STATE_OBSERVER) },
        )
    }

    @Test
    fun `conversation aggregate mapping rejects malformed unreferenced ambiguous and reused leaves`() {
        val active = conversationStateFlowKeys().single { "activeTurnProgress" in it }
        val symbols = conversationStateSymbols()
        listOf(
            symbols.filterNot { it == CONVERSATION_STATE_GETTER },
            symbols.map { if (it == CONVERSATION_STATE_GETTER) it.replace("CodexConversationState", "string") else it },
            symbols.map { if (it == CONVERSATION_STATE_OBSERVER) it.replace("state: CodexConversationState", "state: string") else it },
            symbols + "property:CodexConversation#state[readonly]:CodexConversationState",
            symbols + "method:CodexConversation#observeState:(listener: (state: string) => void): CodexObservation",
            symbols.filterNot { "#turnProgress:" in it },
            symbols.map { if ("#turnProgress:" in it) it.replace("CodexTurnProgress", "string") else it },
        ).forEach { malformed ->
            assertTrue(derive(listOf(active), malformed.sorted()).missingCapabilityKeys.contains(active))
        }

        val unreferenced = derive(
            listOf(active),
            symbols,
            references = symbols.filterNot { "#turnProgress:" in it },
        )
        assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && active in it })

        val ambiguous = derive(
            listOf(active),
            (symbols + "property:CodexConversationState#turnProgress[readonly]:CodexTurnProgress | null | undefined")
                .sorted(),
        )
        assertTrue(ambiguous.errors.any { "Ambiguous" in it && active in it })

        val duplicateLeaf = canonicalProperty(
            "CodexConversation",
            "turnProgress",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/AgentTurnProgress?>!!",
        )
        val reused = derive(listOf(active, duplicateLeaf).sorted(), symbols)
        assertTrue(reused.errors.any { "Reused" in it && active in it && duplicateLeaf in it })
        assertTrue(reused.projectionClaims.isEmpty())

        val unrelated = canonicalProperty(
            "OtherConversation",
            "activeTurnProgress",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/AgentTurnProgress?>!!",
        )
        assertTrue(derive(listOf(unrelated), symbols).missingCapabilityKeys.contains(unrelated))

        val foreign = active.replace("owner=example/CodexConversation", "owner=foreign/CodexConversation")
            .replace("abi=example/CodexConversation", "abi=foreign/CodexConversation")
        val crossOwnerReuse = derive(listOf(active, foreign).sorted(), symbols)
        assertTrue(crossOwnerReuse.errors.any { "Reused" in it && active in it && foreign in it })
        assertTrue(crossOwnerReuse.projectionClaims.isEmpty())
    }

    @Test
    fun `conversation leaf sharing rejects aliases type changes foreign owners excess claims and absent envelope`() {
        val aggregateCanCancel = conversationStateFlowKeys().single { "canCancelTurn" in it }
        val ordinaryCanCancel = conversationOrdinaryStateKeys().single { "canCancelTurn" in it }
        val symbols = conversationStateSymbols()

        val aliasAggregate = conversationStateFlowKeys().single { "currentMessages" in it }
        val aliasOrdinary = canonicalProperty(
            "AgentConversationState",
            "messages",
            "kotlin.collections/List<INVARIANT:example/AgentMessage!!>!!",
        )
        val alias = derive(listOf(aliasAggregate, aliasOrdinary).sorted(), symbols)
        assertTrue(alias.errors.any { "Reused" in it && aliasAggregate in it && aliasOrdinary in it })

        val aggregateValue = canonicalProperty(
            "CodexConversation",
            "value",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/ConversationId?>!!",
        )
        val ordinaryValue = canonicalProperty("AgentConversationState", "value", "kotlin/String?")
        val valueSymbols = (symbols + "getter:CodexConversationState#value:string | null | undefined").sorted()
        val changedType = derive(listOf(aggregateValue, ordinaryValue).sorted(), valueSymbols)
        assertTrue(changedType.errors.any { "Reused" in it && aggregateValue in it && ordinaryValue in it })

        val foreignOrdinary = ordinaryCanCancel
            .replace("owner=example/AgentConversationState", "owner=foreign/AgentConversationState")
            .replace("abi=example/AgentConversationState", "abi=foreign/AgentConversationState")
        val foreign = derive(listOf(aggregateCanCancel, foreignOrdinary).sorted(), symbols)
        assertTrue(foreign.errors.any { "Reused" in it && aggregateCanCancel in it && foreignOrdinary in it })

        val excess = derive(listOf(aggregateCanCancel, ordinaryCanCancel, foreignOrdinary).sorted(), symbols)
        assertTrue(excess.errors.any {
            "Reused" in it && aggregateCanCancel in it && ordinaryCanCancel in it && foreignOrdinary in it
        })
        assertTrue(excess.projectionClaims.isEmpty())

        val envelopeFreeSymbols = listOf(
            "class:CodexConversationState",
            "getter:CodexConversationState#canCancelTurn:boolean",
        )
        val envelopeFree = derive(
            listOf(aggregateCanCancel, ordinaryCanCancel).sorted(),
            envelopeFreeSymbols.sorted(),
        )
        assertEquals(setOf(aggregateCanCancel), envelopeFree.missingCapabilityKeys.toSet())
        assertEquals(listOf(ordinaryCanCancel), envelopeFree.projectionClaims.map { it.capabilityKey })
    }

    @Test
    fun `mutable canonical property requires a writable TypeScript property`() {
        val key = canonicalProperty("Mutable", "value", "kotlin/String!!", propertyKind = "VAR")
        val classSymbol = "class:Mutable"
        listOf(
            "getter:Mutable#value:string",
            "property:Mutable#value[readonly]:string",
        ).forEach { readOnly ->
            assertTrue(derive(listOf(key), listOf(classSymbol, readOnly).sorted()).missingCapabilityKeys.contains(key))
        }
        assertEquals(listOf(key), derive(
            listOf(key),
            listOf(classSymbol, "property:Mutable#value:string").sorted(),
        ).projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
    }

    @Test
    fun `receipt requires exact canonical count and schema two file evidence`() {
        val shortKeys = List(555) { index ->
            canonicalProperty("Short$index", "value", "kotlin/String!!")
        }.sorted()
        val shortSymbols = shortKeys.flatMap { key ->
            val owner = key.substringAfter("owner=example/").substringBefore('|')
            listOf("class:$owner", "getter:$owner#value:string")
        }.sorted()
        assertFailsWith<IllegalStateException> {
            buildJavaScriptTypeScriptBindingReceipt(receiptFiles(shortKeys, shortSymbols))
        }

        val fullKeys = List(556) { index ->
            canonicalProperty("SchemaOne$index", "value", "kotlin/String!!")
        }.sorted()
        val fullSymbols = fullKeys.flatMap { key ->
            val owner = key.substringAfter("owner=example/").substringBefore('|')
            listOf("class:$owner", "getter:$owner#value:string")
        }.sorted()
        assertFailsWith<IllegalStateException> {
            buildJavaScriptTypeScriptBindingReceipt(receiptFiles(fullKeys, fullSymbols, schema = 1))
        }

        val receipt = buildJavaScriptTypeScriptBindingReceipt(receiptFiles(fullKeys, fullSymbols))
        assertEquals(556, receipt.projectionClaims.size)
        assertEquals(11, receipt.bindingTests.size)
        assertEquals(14, receipt.scenarioEvidence.size)
        assertEquals(
            (PACKED_TEST_IDS + JS_NODE_TEST_IDS).toSet(),
            receipt.bindingTests.map(CrossLanguageBindingTestEvidence::testId).toSet(),
        )
    }

    @Test
    fun `receipt rehashes every artifact and verifies installed package identity`() {
        val keys = fullReceiptKeys()
        val symbols = fullReceiptSymbols(keys)
        val forged = receiptFiles(keys, symbols)
        forged.npmTarball.appendText("forged")
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(forged) }

        listOf("index.cjs", "index.d.ts", "index.mjs", "package.json").forEach { name ->
            val altered = receiptFiles(keys, symbols)
            altered.installedPackageDirectory.resolve(name).appendText("forged")
            assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(altered) }
        }

        val wrongCoordinate = receiptFiles(keys, symbols, installedPackageName = "@wrong/package")
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(wrongCoordinate) }

        val wrongVersion = receiptFiles(keys, symbols, installedPackageVersion = "0.2.0")
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(wrongVersion) }
    }

    @Test
    fun `receipt validates exact files before reporting semantic gaps`() {
        val keys = fullReceiptKeys()
        val symbols = fullReceiptSymbols(keys).filterNot { it == "getter:Receipt555#value:string" }
        val forged = receiptFiles(keys, symbols)
        forged.npmTarball.appendText("forged")

        val failure = assertFailsWith<IllegalStateException> {
            buildJavaScriptTypeScriptBindingReceipt(forged)
        }

        assertTrue("artifact identities" in failure.message.orEmpty())
    }

    @Test
    fun `receipt rejects missing extra and symlinked consumer program files`() {
        val keys = fullReceiptKeys()
        val symbols = fullReceiptSymbols(keys)

        val missing = receiptFiles(keys, symbols)
        missing.consumerSourceDirectory.resolve("smoke.ts").delete()
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(missing) }

        val extra = receiptFiles(keys, symbols)
        extra.consumerSourceDirectory.resolve("unexpected.js").writeText("unexpected")
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(extra) }

        val symlinked = receiptFiles(keys, symbols)
        val source = symlinked.consumerSourceDirectory.resolve("smoke.ts")
        val target = symlinked.consumerSourceDirectory.parentFile.resolve("external-smoke.ts").apply {
            writeText("external")
        }
        source.delete()
        Files.createSymbolicLink(source.toPath(), target.toPath())
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(symlinked) }
    }

    @Test
    fun `receipt requires the exact passed packed and jsNode test inventory`() {
        val keys = fullReceiptKeys()
        val symbols = fullReceiptSymbols(keys)

        val missing = receiptFiles(keys, symbols)
        writePackedJUnit(missing.packedJUnitReport, PACKED_TEST_IDS.dropLast(1))
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(missing) }

        val extra = receiptFiles(keys, symbols)
        writePackedJUnit(extra.packedJUnitReport, PACKED_TEST_IDS + "stale packed test")
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(extra) }

        val missingJsNode = receiptFiles(keys, symbols)
        writeJsNodeResults(missingJsNode.jsNodeJUnitReport, JS_NODE_TEST_IDS.dropLast(1))
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(missingJsNode) }

        val extraJsNode = receiptFiles(keys, symbols)
        writeJsNodeResults(
            extraJsNode.jsNodeJUnitReport,
            JS_NODE_TEST_IDS + "jsNodeTest.CodexNodeApiTest#staleTest[js, node]",
        )
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(extraJsNode) }

        val failed = receiptFiles(keys, symbols)
        writePackedJUnit(
            failed.packedJUnitReport,
            PACKED_TEST_IDS,
            mapOf(PACKED_TEST_IDS.first() to CanonicalTestStatus.FAILED),
        )
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(failed) }

        val skipped = receiptFiles(keys, symbols)
        writeJsNodeResults(
            skipped.jsNodeJUnitReport,
            JS_NODE_TEST_IDS,
            mapOf(JS_NODE_TEST_IDS.first() to CanonicalTestStatus.SKIPPED),
        )
        assertFailsWith<IllegalStateException> { buildJavaScriptTypeScriptBindingReceipt(skipped) }
    }

    @Test
    fun `scenario derivation rejects stale and incomplete mappings but permits supplemental receipt tests`() {
        val receipt = buildJavaScriptTypeScriptBindingReceipt(receiptFiles(fullReceiptKeys(), fullReceiptSymbols()))
        val stale = javaScriptBindingScenarioMappings.mapIndexed { index, mapping ->
            if (index == 0) mapping.copy(testIds = mapping.testIds + "removed test") else mapping
        }
        assertFailsWith<IllegalStateException> {
            deriveJavaScriptScenarioEvidence(receipt.bindingTests, stale)
        }
        assertFailsWith<IllegalStateException> {
            deriveJavaScriptScenarioEvidence(receipt.bindingTests, javaScriptBindingScenarioMappings.dropLast(1))
        }
        val mappedTests = javaScriptBindingScenarioMappings.flatMap(JavaScriptBindingScenarioMapping::testIds).toSet()
        assertTrue(PACKED_TEST_IDS.first() in mappedTests)
        assertTrue(PACKED_TEST_IDS[3] !in mappedTests)
        assertEquals(
            CrossLanguageBindingScenario.entries.size,
            deriveJavaScriptScenarioEvidence(receipt.bindingTests, javaScriptBindingScenarioMappings).size,
        )
    }

    @Test
    fun `direct packed evidence enforces coordinate artifacts filenames and exports`() {
        val key = canonicalProperty("Projection", "value", "kotlin/String!!")
        val symbols = listOf("class:Projection", "getter:Projection#value:string")
        val packed = packedEvidence(symbols.sorted(), schema = 2)
        listOf(
            packed.copy(packageName = "@wrong/package"),
            packed.copy(artifacts = packed.artifacts.dropLast(1)),
            packed.copy(artifacts = packed.artifacts.mapIndexed { index, artifact ->
                artifact.copy(fileName = if (index < 2) "duplicate.bin" else artifact.fileName)
            }),
            packed.copy(artifacts = packed.artifacts.map { artifact ->
                if (artifact.id == "commonJs") artifact.copy(fileName = "runtime.cjs") else artifact
            }),
            packed.copy(packageVersion = "0.2.0"),
            packed.copy(typeExports = emptyList()),
        ).forEach { invalid ->
            assertFailsWith<IllegalStateException> {
                deriveCrossLanguageJavaScriptBindingEvidence(
                    canonicalEvidence(listOf(key)), invalid,
                )
            }
        }
    }

    @Test
    fun `strict packed report rejects stale references unsorted inventories and noncanonical bytes`() {
        val directory = createTempDirectory("js-api-evidence").toFile()
        val valid = File(directory, "valid.json")
        writePackedReport(
            valid,
            schema = 2,
            symbols = listOf("class:A", "getter:A#value:string"),
            references = listOf("getter:A#value:string"),
        )
        val stale = File(directory, "stale.json")
        writePackedReport(
            stale,
            schema = 2,
            symbols = listOf("getter:CodexFailure#message:string"),
            references = listOf("getter:CodexFailure#removed:string"),
        )
        val unsorted = File(directory, "unsorted.json")
        writePackedReport(
            unsorted,
            schema = 1,
            symbols = listOf("getter:Z#value:string", "getter:A#value:string"),
        )
        val noncanonical = File(directory, "noncanonical.json")
        writePackedReport(
            noncanonical,
            schema = 2,
            symbols = listOf("class:A", "getter:A#value:string"),
        )
        noncanonical.writeText(noncanonical.readText().replace("    ", "  "))

        assertEquals(JAVASCRIPT_NPM_PACKAGE, readJavaScriptPackedPublicApiEvidence(valid).packageName)
        assertFailsWith<IllegalStateException> { readJavaScriptPackedPublicApiEvidence(stale) }
        assertFailsWith<IllegalStateException> { readJavaScriptPackedPublicApiEvidence(unsorted) }
        assertFailsWith<IllegalStateException> { readJavaScriptPackedPublicApiEvidence(noncanonical) }
    }

    private fun canonicalEvidence(keys: List<String>) = CrossLanguageCanonicalApiEvidence(
        memberKeys = keys,
        canonical = CrossLanguageBindingCanonicalIdentity(digest('1'), digest('2')),
        targetSha256 = mapOf("native" to digest('6'), "wasm" to digest('7'), "jvm-classes" to digest('8')),
        compiledTestsSha256 = digest('9'),
        testResultsSha256 = digest('a'),
        coveredTestIds = setOf(COMPILER_TEST),
    )

    private fun packedEvidence(
        symbols: List<String>,
        schema: Int,
        referencedSymbols: List<String> = emptyList(),
    ): JavaScriptPackedPublicApiEvidence {
        val exports = symbolExports(symbols)
        return JavaScriptPackedPublicApiEvidence(
            schema = schema,
            packageName = JAVASCRIPT_NPM_PACKAGE,
            packageVersion = "0.1.0",
            artifacts = listOf(
                JavaScriptPackedArtifact("commonJs", "index.cjs", 1, digest('3')),
                JavaScriptPackedArtifact("declaration", "index.d.ts", 1, digest('4')),
                JavaScriptPackedArtifact("esm", "index.mjs", 1, digest('5')),
                JavaScriptPackedArtifact("packageJson", "package.json", 1, digest('6')),
                JavaScriptPackedArtifact("tarball", "codex-agent-0.1.0.tgz", 1, digest('7')),
            ),
            typeExports = exports.first,
            valueExports = exports.second,
            commonJsExports = exports.second,
            esmExports = exports.second,
            publicSymbols = symbols,
            referencedSymbols = referencedSymbols,
            compilerTestId = COMPILER_TEST,
        )
    }

    private fun derive(
        keys: List<String>,
        symbols: List<String>,
        schema: Int = 2,
        references: List<String> = if (schema == 2) symbols else emptyList(),
    ): CrossLanguageJavaScriptBindingEvidence = deriveCrossLanguageJavaScriptBindingEvidence(
        canonical = canonicalEvidence(keys.sorted()),
        packedApi = packedEvidence(symbols.sorted(), schema, references.sorted()),
    )

    private fun conversationStateFlowKeys(): List<String> = listOf(
        canonicalProperty(
            "CodexConversation",
            "state",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/AgentConversationState!!>!!",
        ),
        canonicalProperty(
            "CodexConversation",
            "activeTurnProgress",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/AgentTurnProgress?>!!",
        ),
        canonicalProperty(
            "CodexConversation",
            "currentMessages",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin.collections/List<INVARIANT:example/AgentMessage!!>!!>!!",
        ),
    ) + listOf("canCancelTurn", "canReload", "canRunShellCommand", "canStartTurn", "isTurnActive").map { name ->
        canonicalProperty(
            "CodexConversation",
            name,
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!",
        )
    }.sorted()

    private fun conversationOrdinaryStateKeys(): List<String> =
        listOf("canCancelTurn", "canReload", "canStartTurn").map { name ->
            canonicalProperty("AgentConversationState", name, "kotlin/Boolean!!")
        }.sorted()

    private fun conversationStateSymbols(): List<String> = listOf(
        "class:CodexConversation",
        "class:CodexConversationState",
        CONVERSATION_STATE_GETTER,
        CONVERSATION_STATE_OBSERVER,
        "getter:CodexConversationState#canCancelTurn:boolean",
        "getter:CodexConversationState#canReload:boolean",
        "getter:CodexConversationState#canRunShellCommand:boolean",
        "getter:CodexConversationState#canStartTurn:boolean",
        "getter:CodexConversationState#isTurnActive:boolean",
        "getter:CodexConversationState#messages:ReadonlyArray<CodexMessage>",
        "getter:CodexConversationState#turnProgress:CodexTurnProgress | null | undefined",
    ).sorted()

    private fun receiptFiles(
        keys: List<String>,
        symbols: List<String>,
        schema: Int = 2,
        references: List<String> = if (schema == 2) symbols else emptyList(),
        installedPackageName: String = JAVASCRIPT_NPM_PACKAGE,
        installedPackageVersion: String = "0.1.0",
    ): CrossLanguageJavaScriptBindingFiles {
        val directory = createTempDirectory("js-receipt-files").toFile()
        val apiReport = directory.resolve("canonical-api.json")
        val coverageReceipt = directory.resolve("canonical-coverage.json")
        val packedReport = directory.resolve("public-api.json")
        val installedPackage = directory.resolve("installed-package").apply { mkdirs() }
        val tarball = directory.resolve("codex-agent-0.1.0.tgz").apply { writeText("tarball") }
        val installedArtifacts = mapOf(
            "commonJs" to installedPackage.resolve("index.cjs").apply { writeText("module.exports = {}") },
            "declaration" to installedPackage.resolve("index.d.ts").apply { writeText("export {}") },
            "esm" to installedPackage.resolve("index.mjs").apply { writeText("export {}") },
            "packageJson" to installedPackage.resolve("package.json").apply {
                atomicWriteJson(buildJsonObject {
                    put("name", JsonPrimitive(installedPackageName))
                    put("version", JsonPrimitive(installedPackageVersion))
                })
            },
            "tarball" to tarball,
        )
        val consumerSource = directory.resolve("consumer-source").apply { mkdirs() }
        REQUIRED_CONSUMER_SOURCE_FILES.forEach { name ->
            consumerSource.resolve(name).writeText("fixture:$name")
        }
        val compiledProgram = directory.resolve("compiled-js-node-test-program").apply { mkdirs() }
        compiledProgram.resolve("test-program.mjs").writeText("fixture compiled program")
        val packedJUnit = directory.resolve("packed-junit.xml")
        writePackedJUnit(packedJUnit, PACKED_TEST_IDS)
        val jsNodeResults = directory.resolve("js-node-results").apply { mkdirs() }
        val jsNodeJUnit = jsNodeResults.resolve("TEST-jsNodeTest.CodexNodeApiTest.xml")
        writeJsNodeResults(jsNodeJUnit, JS_NODE_TEST_IDS)
        writeCanonicalApiReport(apiReport, keys.sorted())
        writeCanonicalCoverageReceipt(coverageReceipt, apiReport, keys.sorted())
        writePackedReport(
            packedReport,
            schema,
            symbols.sorted(),
            references.sorted(),
            artifactFiles = installedArtifacts,
        )
        return CrossLanguageJavaScriptBindingFiles(
            apiReport = apiReport,
            canonicalCoverageReceipt = coverageReceipt,
            packedPublicApiReport = packedReport,
            npmTarball = tarball,
            installedPackageDirectory = installedPackage,
            consumerSourceDirectory = consumerSource,
            compiledJsNodeTestProgramDirectory = compiledProgram,
            packedJUnitReport = packedJUnit,
            jsNodeJUnitReport = jsNodeJUnit,
        )
    }

    private fun fullReceiptKeys(): List<String> = List(556) { index ->
        canonicalProperty("Receipt${index.toString().padStart(3, '0')}", "value", "kotlin/String!!")
    }.sorted()

    private data class SdkCreatedConstructorShape(
        val owner: String,
        val parameters: List<String>,
        val defaultParameterIndices: Set<Int> = emptySet(),
    )

    private fun sdkCreatedConstructorShapes(): List<SdkCreatedConstructorShape> = listOf(
        SdkCreatedConstructorShape(
            "AgentAuthenticationState",
            listOf(
                "example/AgentAuthenticationStatus!!",
                "example/CodexAuthorizationUrl?",
                "example/CodexAuthorizationUrl?",
                "kotlin/String?",
                "example/CodexFailure?",
            ),
            defaultParameterIndices = (0..4).toSet(),
        ),
        SdkCreatedConstructorShape(
            "AgentConversationState",
            listOf(
                "example/AgentConversationStatus!!",
                "example/ConversationId?",
                "example/AgentConversation?",
                "example/AgentTurnProgress!!",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/String?",
                "example/CodexFailure?",
            ),
            defaultParameterIndices = (0..7).toSet(),
        ),
        SdkCreatedConstructorShape(
            "AgentMessage",
            listOf(
                "kotlin/String!!",
                "kotlin/String?",
                "example/AgentMessageRole!!",
                "kotlin/String!!",
                "example/AgentCollaborationMode!!",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/Int?",
                "kotlin.collections/Set<INVARIANT:example/AgentCapability!!>!!",
                "kotlin.collections/List<INVARIANT:example/AgentInvocation!!>!!",
            ),
            defaultParameterIndices = (4..10).toSet(),
        ),
        SdkCreatedConstructorShape(
            "AgentTurnProgress",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "example/AgentPlanProgress?",
                "kotlin/String!!",
                "kotlin/Int?",
                "example/AgentWorkActivity?",
                "kotlin.collections/List<INVARIANT:example/AgentHookActivity!!>!!",
                "kotlin/Boolean!!",
            ),
            defaultParameterIndices = (0..9).toSet(),
        ),
        SdkCreatedConstructorShape(
            "CodexFailure",
            listOf("kotlin/String!!", "kotlin/String!!", "kotlin/Boolean!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexHostState.Failed",
            listOf("example/CodexWorkspace?", "example/CodexFailure!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexHostState.Preparing",
            listOf("example/CodexWorkspace!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexHostState.Ready",
            listOf("example/CodexAgent!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexHostState.WorkspaceRequired",
            listOf("example/CodexWorkspaceResolution.SelectionRequired!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexWorkspace",
            listOf("kotlin/String!!", "kotlin/String!!"),
            defaultParameterIndices = setOf(1),
        ),
        SdkCreatedConstructorShape(
            "CodexWorkspaceResolution.Available",
            listOf("example/CodexWorkspace!!"),
        ),
        SdkCreatedConstructorShape(
            "CodexWorkspaceResolution.SelectionRequired",
            listOf("example/CodexWorkspaceSelectionReason!!", "kotlin/String!!"),
        ),
    )

    private fun sdkCreatedConstructorKeys(): List<String> = sdkCreatedConstructorShapes().map { shape ->
        canonicalConstructor(shape.owner, shape.parameters, shape.defaultParameterIndices)
    }.sorted()

    private fun fullReceiptSymbols(keys: List<String> = fullReceiptKeys()): List<String> = keys.flatMap { key ->
        val owner = key.substringAfter("owner=example/").substringBefore('|')
        listOf("class:$owner", "getter:$owner#value:string")
    }.sorted()

    private fun symbolExports(symbols: List<String>): Pair<List<String>, List<String>> {
        val classes = symbols.filter { it.startsWith("class:") }
            .map { it.substringAfter(':').substringBefore(':') }
        val types = symbols.filter { it.startsWith("type:") }
            .map { it.substringAfter(':').substringBefore(':') }
        val functions = symbols.filter { it.startsWith("function:") }
            .map { it.substringAfter(':').substringBefore(':') }
        return (classes + types).distinct().sorted() to (classes + functions).distinct().sorted()
    }

    private fun canonicalProperty(
        owner: String,
        name: String,
        type: String,
        propertyKind: String = "VAL",
    ): String =
        "common|owner=example/$owner|kind=property|abi=example/$owner.$name|{}$name[0]|" +
            "propertyKind=$propertyKind|type=$type"

    private fun canonicalEnumEntry(owner: String, name: String): String =
        "common|owner=example/$owner|kind=enum-entry|abi=example/$owner.$name|null[0]"

    private fun canonicalObject(owner: String): String =
        "common|owner=example/$owner|kind=object|abi=example/$owner|null[0]"

    private fun canonicalClass(owner: String): String =
        "common|owner=example/$owner|kind=class|abi=example/$owner|null[0]"

    private fun canonicalFunction(
        owner: String,
        name: String,
        returnType: String = "kotlin/Unit",
        suspendFunction: Boolean = false,
        parameters: List<String> = emptyList(),
        defaultParameterIndices: Set<Int> = emptySet(),
    ): String = "common|owner=example/$owner|kind=function|abi=example/$owner.$name|" +
        "$name(){}[0]|return=$returnType|suspend=$suspendFunction|parameters=" +
        canonicalParameters(parameters, defaultParameterIndices)

    private fun canonicalConstructor(
        owner: String,
        parameters: List<String>,
        defaultParameterIndices: Set<Int> = emptySet(),
    ): String =
        "common|owner=example/$owner|kind=constructor|abi=example/$owner.<init>|<init>(){}[0]|" +
            "return=example/$owner|suspend=false|parameters=" +
            canonicalParameters(parameters, defaultParameterIndices)

    private fun canonicalParameters(
        parameters: List<String>,
        defaultParameterIndices: Set<Int> = emptySet(),
    ): String = parameters.mapIndexed { index, type ->
        "REGULAR:$type:default=${index in defaultParameterIndices}:vararg=false"
    }.joinToString(
        prefix = "[",
        postfix = "]",
    )

    private fun writePackedReport(
        file: File,
        schema: Int,
        symbols: List<String>,
        references: List<String> = emptyList(),
        artifactFiles: Map<String, File>? = null,
    ) {
        val exports = symbolExports(symbols)
        file.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(schema))
            put("result", JsonPrimitive("passed"))
            put("language", JsonPrimitive("javascript-typescript"))
            put("toolchain", buildJsonObject {
                put("node", JsonPrimitive("v24.0.0"))
                put("typescript", JsonPrimitive("6.0.0"))
            })
            put("package", buildJsonObject {
                put("name", JsonPrimitive(JAVASCRIPT_NPM_PACKAGE))
                put("version", JsonPrimitive("0.1.0"))
            })
            put("artifacts", buildJsonObject {
                mapOf(
                    "tarball" to "codex-agent-0.1.0.tgz",
                    "packageJson" to "package.json",
                    "declaration" to "index.d.ts",
                    "commonJs" to "index.cjs",
                    "esm" to "index.mjs",
                ).forEach { (id, fileName) ->
                    val artifactFile = artifactFiles?.get(id)
                    put(id, buildJsonObject {
                        put("fileName", JsonPrimitive(artifactFile?.name ?: fileName))
                        put("bytes", JsonPrimitive(artifactFile?.length() ?: 1L))
                        put("sha256", JsonPrimitive(artifactFile?.releaseDigest() ?: digest('3')))
                    })
                }
            })
            put("exports", buildJsonObject {
                put("types", buildJsonArray { exports.first.forEach { add(JsonPrimitive(it)) } })
                put("values", buildJsonArray { exports.second.forEach { add(JsonPrimitive(it)) } })
                put("commonJs", buildJsonArray { exports.second.forEach { add(JsonPrimitive(it)) } })
                put("esm", buildJsonArray { exports.second.forEach { add(JsonPrimitive(it)) } })
            })
            put("publicSymbols", buildJsonArray { symbols.forEach { add(JsonPrimitive(it)) } })
            put("compilerEvidence", buildJsonObject {
                put("testId", JsonPrimitive(COMPILER_TEST))
                put("status", JsonPrimitive("passed"))
                if (schema == 2) {
                    put("referencedSymbols", buildJsonArray { references.forEach { add(JsonPrimitive(it)) } })
                }
            })
        })
    }

    private fun writePackedJUnit(
        file: File,
        testIds: List<String>,
        statuses: Map<String, CanonicalTestStatus> = emptyMap(),
    ) {
        file.writeText(buildString {
            append("<testsuites><testsuite name=\"packed-npm\">")
            testIds.forEach { testId ->
                append("<testcase name=\"").append(testId).append("\"")
                appendTestTerminal(statuses[testId] ?: CanonicalTestStatus.PASSED)
            }
            append("</testsuite></testsuites>")
        })
    }

    private fun writeJsNodeResults(
        file: File,
        testIds: List<String>,
        statuses: Map<String, CanonicalTestStatus> = emptyMap(),
    ) {
        file.parentFile.mkdirs()
        file.writeText(buildString {
            append("<testsuite name=\"compiled-js-node\">")
            testIds.forEach { testId ->
                val (className, methodName) = testId.split('#', limit = 2)
                append("<testcase classname=\"").append(className)
                    .append("\" name=\"").append(methodName).append("\"")
                appendTestTerminal(statuses[testId] ?: CanonicalTestStatus.PASSED)
            }
            append("</testsuite>")
        })
    }

    private fun StringBuilder.appendTestTerminal(status: CanonicalTestStatus) {
        when (status) {
            CanonicalTestStatus.PASSED -> append("/>")
            CanonicalTestStatus.SKIPPED -> append("><skipped/></testcase>")
            CanonicalTestStatus.FAILED -> append("><failure/></testcase>")
        }
    }

    private fun writeCanonicalApiReport(file: File, keys: List<String>) {
        val owners = keys.groupBy { key -> key.substringAfter("owner=").substringBefore('|') }.toSortedMap()
        file.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2))
            put("libraryUniqueName", JsonPrimitive("javascript-test"))
            put("markerAnnotation", JsonPrimitive("example/CodexBindingApi"))
            put("signatureVersion", JsonPrimitive(2))
            put("boundaryTypes", buildJsonArray { owners.keys.forEach { add(JsonPrimitive(it)) } })
            put("memberExclusionAnnotation", JsonPrimitive("example/CodexBindingExclude"))
            put("excludedReachableTypes", buildJsonArray {})
            put("excludedMemberKeys", buildJsonArray {})
            put("dataClassMetadataAvailable", JsonPrimitive(true))
            put("dataClassNames", buildJsonArray {})
            put("owners", buildJsonArray {
                owners.forEach { (owner, members) ->
                    add(buildJsonObject {
                        put("name", JsonPrimitive(owner))
                        put("capabilities", buildJsonArray { members.sorted().forEach { add(JsonPrimitive(it)) } })
                    })
                }
            })
            put("targets", buildJsonArray {
                listOf("jvm-classes", "native", "wasm").forEachIndexed { index, kind ->
                    add(buildJsonObject {
                        put("kind", JsonPrimitive(kind))
                        put("sha256", JsonPrimitive(digest(('6'.code + index).toChar())))
                    })
                }
            })
        })
    }

    private fun writeCanonicalCoverageReceipt(file: File, apiReport: File, keys: List<String>) {
        file.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2))
            put("result", JsonPrimitive("passed"))
            put("kotlinCompilerVersion", JsonPrimitive("test"))
            put("canonicalTestTask", JsonPrimitive("canonical-test"))
            put("apiReportSha256", JsonPrimitive(apiReport.releaseDigest()))
            put("compiledTestsSha256", JsonPrimitive(digest('9')))
            put("testResultsSha256", JsonPrimitive(digest('a')))
            put("capabilities", buildJsonArray { keys.forEach { add(JsonPrimitive(it)) } })
            put("claims", buildJsonArray {
                add(buildJsonObject {
                    put("testId", JsonPrimitive(COMPILER_TEST))
                    put("capabilities", buildJsonArray { keys.forEach { add(JsonPrimitive(it)) } })
                })
            })
        })
    }

    private fun currentPublicSymbols(): List<String> = CURRENT_PUBLIC_SYMBOLS.lineSequence()
        .filter(String::isNotBlank)
        .toList()
        .also { assertEquals(189, it.size) }

    companion object {
        private const val COMPILER_TEST = "typescript compiler discovers the exact installed public API"
        private const val OPEN_CONVERSATION =
            "method:CodexAgent#openConversation:" +
                "(conversationId?: string | null | undefined, " +
                "approvalPreset?: CodexApprovalPreset | null | undefined, " +
                "serviceTier?: string | null | undefined, " +
                "signal?: AbortSignal | null | undefined): Promise<CodexConversation>"
        private const val DELETE_CONVERSATION =
            "method:CodexAgent#delete:" +
                "(conversationId: string, signal?: AbortSignal | null | undefined): Promise<void>"
        private const val RENAME_CONVERSATION =
            "method:CodexAgent#rename:" +
                "(conversationId: string, name: string, " +
                "signal?: AbortSignal | null | undefined): Promise<void>"
        private const val APPROVAL_PRESET_DISPLAY_NAME =
            "function:codexApprovalPresetDisplayName:(preset: CodexApprovalPreset): string"
        private const val CONVERSATION_ID_GETTER =
            "getter:CodexConversationState#conversationId:string | null | undefined"
        private const val SELECT_WORKSPACE =
            "method:CodexHost#selectWorkspace:" +
                "(path: string, signal?: AbortSignal | null | undefined): Promise<void>"
        private const val CONVERSATION_STATE_GETTER =
            "getter:CodexConversation#state:CodexConversationState"
        private const val CONVERSATION_STATE_OBSERVER =
            "method:CodexConversation#observeState:" +
                "(listener: (state: CodexConversationState) => void): CodexObservation"

        private val AUTHENTICATION_OVERLOADS = listOf(
            "method:CodexAuthentication#authenticate:" +
                "(method: \"api_key\", apiKey: string, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
            "method:CodexAuthentication#authenticate:" +
                "(method: \"chatgpt_device_code\", apiKey?: null, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
            "method:CodexAuthentication#authenticate:" +
                "(method?: \"chatgpt_browser\" | null | undefined, apiKey?: null, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
        )

        private val PACKED_TEST_IDS = listOf(
            "cjs exposes the exact Node-only SDK surface",
            "cjs projects lifecycle state failure cleanup and terminal delivery",
            "cjs maps AbortSignal cancellation without starting",
            "esm exposes the same runtime values as CommonJS",
            COMPILER_TEST,
        )

        private val JS_NODE_TEST_IDS = listOf(
            "jsNodeTest.CodexNodeApiTest#projectsCanonicalLifecycleIdentityFailureAndOwnership[js, node]",
            "jsNodeTest.CodexNodeApiTest#abortsBeforeStartingAndStopsDisposedObservation[js, node]",
            "jsNodeTest.CodexNodeApiTest#mapsCanonicalCancellationAndRemovesAbortListener[js, node]",
            "jsNodeTest.CodexNodeApiTest#isolatesListenerFailureWhileOtherObserversAndCleanupContinue[js, node]",
            "jsNodeTest.CodexNodeApiTest#projectsAuthenticationStateMethodsIdentityAndDisposal[js, node]",
            "jsNodeTest.CodexNodeApiTest#mapsAuthenticationFailureAndAbortSignalCancellation[js, node]",
        )

        private val REQUIRED_CONSUMER_SOURCE_FILES = listOf(
            "package-lock.json",
            "package.json",
            "negative.ts",
            "smoke.cjs",
            "smoke.mjs",
            "smoke.ts",
            "tsconfig.json",
        )

        private fun digest(character: Char): String = character.toString().repeat(64)

        private val CURRENT_PUBLIC_SYMBOLS = """
class:AgentElicitationValidation
class:AgentElicitationValidationIssue
class:AgentFormBooleanValue
class:AgentFormNumberValue
class:AgentFormOption
class:AgentFormTextListValue
class:AgentFormTextValue
class:AgentHookActivity
class:AgentMcpEnvironmentVariable
class:AgentMcpOauthConfiguration
class:AgentMcpToolConfiguration
class:AgentPlanProgress
class:AgentPlanStep
class:CodexAgent
class:CodexAuthentication
class:CodexAuthenticationState
class:CodexConversation
class:CodexConversationState
class:CodexError:extends=Error
class:CodexFailure
class:CodexHost
class:CodexHostState
class:CodexMessage
class:CodexObservation
class:CodexTurnProgress
class:CodexWorkspace
constructor:AgentElicitationValidation#(issues: ReadonlyArray<AgentElicitationValidationIssue>)
constructor:AgentElicitationValidationIssue#(fieldName: string, reason: AgentElicitationValidationReason)
constructor:AgentFormBooleanValue#(value: boolean)
constructor:AgentFormNumberValue#(value: number)
constructor:AgentFormOption#(value: string, title?: string, description?: string | null | undefined)
constructor:AgentFormTextListValue#(value: ReadonlyArray<string>)
constructor:AgentFormTextValue#(value: string)
constructor:AgentHookActivity#(id: string, eventName: string, handlerType: string, status: AgentHookRunStatus, statusMessage?: string | null | undefined, details?: ReadonlyArray<string>)
constructor:AgentMcpEnvironmentVariable#(name: string, source?: AgentMcpEnvironmentSource | null | undefined)
constructor:AgentMcpOauthConfiguration#(clientId?: string | null | undefined, callbackPort?: number | null | undefined)
constructor:AgentMcpToolConfiguration#(approval?: AgentMcpToolApproval | null | undefined)
constructor:AgentPlanProgress#(explanation?: string | null | undefined, steps?: ReadonlyArray<AgentPlanStep>)
constructor:AgentPlanStep#(text: string, status: AgentPlanStepStatus)
function:codexApprovalPresetDisplayName:(preset: CodexApprovalPreset): string
function:createCodexHost:(bundleDirectory: string, dataDirectory: string, clientName: string, clientTitle: string, clientVersion: string): CodexHost
getter:AgentElicitationValidation#isValid:boolean
getter:AgentElicitationValidation#issues:ReadonlyArray<AgentElicitationValidationIssue>
getter:AgentElicitationValidationIssue#fieldName:string
getter:AgentElicitationValidationIssue#reason:AgentElicitationValidationReason
getter:AgentFormBooleanValue#value:boolean
getter:AgentFormNumberValue#value:number
getter:AgentFormOption#description:string | null | undefined
getter:AgentFormOption#title:string
getter:AgentFormOption#value:string
getter:AgentFormTextListValue#value:ReadonlyArray<string>
getter:AgentFormTextValue#value:string
getter:AgentHookActivity#details:ReadonlyArray<string>
getter:AgentHookActivity#eventName:string
getter:AgentHookActivity#handlerType:string
getter:AgentHookActivity#id:string
getter:AgentHookActivity#status:AgentHookRunStatus
getter:AgentHookActivity#statusMessage:string | null | undefined
getter:AgentMcpEnvironmentVariable#name:string
getter:AgentMcpEnvironmentVariable#source:AgentMcpEnvironmentSource | null | undefined
getter:AgentMcpOauthConfiguration#callbackPort:number | null | undefined
getter:AgentMcpOauthConfiguration#clientId:string | null | undefined
getter:AgentMcpToolConfiguration#approval:AgentMcpToolApproval | null | undefined
getter:AgentPlanProgress#explanation:string | null | undefined
getter:AgentPlanProgress#steps:ReadonlyArray<AgentPlanStep>
getter:AgentPlanStep#status:AgentPlanStepStatus
getter:AgentPlanStep#text:string
getter:CodexAgent#activeConversation:CodexConversation | null | undefined
getter:CodexAgent#authentication:CodexAuthentication
getter:CodexAgent#workspace:CodexWorkspace
getter:CodexAuthentication#isAuthenticated:boolean
getter:CodexAuthentication#isAuthenticating:boolean
getter:CodexAuthentication#state:CodexAuthenticationState
getter:CodexAuthenticationState#deviceUserCode:string | null | undefined
getter:CodexAuthenticationState#deviceVerificationUrl:string | null | undefined
getter:CodexAuthenticationState#failure:CodexFailure | null | undefined
getter:CodexAuthenticationState#pendingSignInUrl:string | null | undefined
getter:CodexAuthenticationState#status:CodexAuthenticationStatus
getter:CodexConversation#state:CodexConversationState
getter:CodexConversationState#canCancelTurn:boolean
getter:CodexConversationState#canReload:boolean
getter:CodexConversationState#canRunShellCommand:boolean
getter:CodexConversationState#canStartTurn:boolean
getter:CodexConversationState#conversationId:string | null | undefined
getter:CodexConversationState#effort:string | null | undefined
getter:CodexConversationState#failure:CodexFailure | null | undefined
getter:CodexConversationState#isTurnActive:boolean
getter:CodexConversationState#messages:ReadonlyArray<CodexMessage>
getter:CodexConversationState#model:string | null | undefined
getter:CodexConversationState#serviceTier:string | null | undefined
getter:CodexConversationState#status:CodexConversationStatus
getter:CodexConversationState#title:string | null | undefined
getter:CodexConversationState#turnProgress:CodexTurnProgress | null | undefined
getter:CodexError#code:string
getter:CodexError#recoverable:boolean
getter:CodexFailure#code:string
getter:CodexFailure#message:string
getter:CodexFailure#recoverable:boolean
getter:CodexHost#agent:CodexAgent | null | undefined
getter:CodexHost#state:CodexHostState
getter:CodexHostState#agent:CodexAgent | null | undefined
getter:CodexHostState#failure:CodexFailure | null | undefined
getter:CodexHostState#selectionMessage:string | null | undefined
getter:CodexHostState#selectionReason:CodexWorkspaceSelectionReason | null | undefined
getter:CodexHostState#status:CodexHostStatus
getter:CodexHostState#workspace:CodexWorkspace | null | undefined
getter:CodexMessage#clientMessageId:string | null | undefined
getter:CodexMessage#exitCode:number | null | undefined
getter:CodexMessage#id:string
getter:CodexMessage#plan:string | null | undefined
getter:CodexMessage#reasoning:string | null | undefined
getter:CodexMessage#role:CodexMessageRole
getter:CodexMessage#shellCommand:string | null | undefined
getter:CodexMessage#text:string
getter:CodexObservation#isClosed:boolean
getter:CodexTurnProgress#commentary:string
getter:CodexTurnProgress#hookActivities:ReadonlyArray<AgentHookActivity>
getter:CodexTurnProgress#plan:string
getter:CodexTurnProgress#planProgress:AgentPlanProgress | null | undefined
getter:CodexTurnProgress#reasoning:string
getter:CodexTurnProgress#shellExitCode:number | null | undefined
getter:CodexTurnProgress#shellOutput:string
getter:CodexTurnProgress#text:string
getter:CodexTurnProgress#truncated:boolean
getter:CodexTurnProgress#workActivity:CodexWorkActivity | null | undefined
getter:CodexWorkspace#displayName:string
getter:CodexWorkspace#path:string
method:CodexAgent#delete:(conversationId: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAgent#observeActiveConversation:(listener: (conversation: CodexConversation | null | undefined) => void): CodexObservation
method:CodexAgent#openConversation:(conversationId?: string | null | undefined, approvalPreset?: CodexApprovalPreset | null | undefined, serviceTier?: string | null | undefined, signal?: AbortSignal | null | undefined): Promise<CodexConversation>
method:CodexAgent#rename:(conversationId: string, name: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAuthentication#authenticate:(method: "api_key", apiKey: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAuthentication#authenticate:(method: "chatgpt_device_code", apiKey?: null, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAuthentication#authenticate:(method?: "chatgpt_browser" | null | undefined, apiKey?: null, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAuthentication#cancel:(signal?: AbortSignal | null | undefined): Promise<void>
method:CodexAuthentication#observeAuthenticated:(listener: (isAuthenticated: boolean) => void): CodexObservation
method:CodexAuthentication#observeAuthenticating:(listener: (isAuthenticating: boolean) => void): CodexObservation
method:CodexAuthentication#observeState:(listener: (state: CodexAuthenticationState) => void): CodexObservation
method:CodexAuthentication#signOut:(signal?: AbortSignal | null | undefined): Promise<void>
method:CodexConversation#[Symbol.asyncDispose]:(): Promise<void>
method:CodexConversation#cancelTurn:(): Promise<void>
method:CodexConversation#close:(): Promise<void>
method:CodexConversation#dispose:(): Promise<void>
method:CodexConversation#observeState:(listener: (state: CodexConversationState) => void): CodexObservation
method:CodexConversation#reload:(signal?: AbortSignal | null | undefined): Promise<void>
method:CodexConversation#runShellCommand:(command: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexConversation#send:(prompt: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexHost#[Symbol.asyncDispose]:(): Promise<void>
method:CodexHost#close:(): Promise<void>
method:CodexHost#dispose:(): Promise<void>
method:CodexHost#observeState:(listener: (state: CodexHostState) => void): CodexObservation
method:CodexHost#selectWorkspace:(path: string, signal?: AbortSignal | null | undefined): Promise<void>
method:CodexHost#start:(signal?: AbortSignal | null | undefined): Promise<void>
method:CodexObservation#[Symbol.dispose]:(): void
method:CodexObservation#close:(): void
method:CodexObservation#dispose:(): void
property:CodexError#cause[optional,readonly]:unknown
type:AgentApprovalDecision:"accept" | "decline"
type:AgentCapability:"web_search"
type:AgentCatalogFreshness:"fresh_cache" | "live" | "stale_cache"
type:AgentCollaborationMode:"default" | "plan"
type:AgentElicitationAction:"accept" | "cancel" | "decline"
type:AgentElicitationValidationReason:"above_maximum" | "below_minimum" | "duplicate_selection" | "invalid_format" | "invalid_selection" | "invalid_type" | "missing_required" | "non_finite_number" | "non_integer" | "unknown_field"
type:AgentFormFieldType:"boolean" | "integer" | "multi_select" | "number" | "single_select" | "string"
type:AgentFormStringFormat:"date" | "date_time" | "email" | "uri"
type:AgentHookRunStatus:"blocked" | "completed" | "failed" | "running" | "stopped"
type:AgentHookTrustStatus:"managed" | "modified" | "trusted" | "untrusted"
type:AgentInstallationScope:"user" | "workspace"
type:AgentIntegrationAuthorizationStatus:"authorized" | "awaiting_completion" | "failed" | "idle" | "starting"
type:AgentMcpAuthStatus:"bearer_token" | "not_logged_in" | "oauth" | "unknown" | "unsupported"
type:AgentMcpAuthentication:"chat_gpt" | "oauth"
type:AgentMcpEnvironmentSource:"local" | "remote"
type:AgentMcpToolApproval:"approve" | "auto" | "prompt" | "writes"
type:AgentMcpToolExposureSurface:"code_mode" | "deferred" | "direct"
type:AgentPlanStepStatus:"completed" | "in_progress" | "pending"
type:AgentPluginAuthPolicy:"on_install" | "on_use"
type:AgentPluginInstallPolicy:"available" | "installed_by_default" | "not_available"
type:AgentResolution:"default" | "first" | "preferred"
type:AgentResourceOrigin:"managed" | "plugin" | "unknown" | "user" | "workspace"
type:AgentSkillScope:"admin" | "plugin" | "repo" | "system" | "user"
type:CodexApprovalPreset:"ask_me" | "auto_review" | "never" | "strict"
type:CodexAuthenticationMethod:"chatgpt_browser" | "chatgpt_device_code" | "api_key"
type:CodexAuthenticationStatus:"authenticated" | "authenticating" | "signed_out"
type:CodexAuthorizationPurpose:"chat_gpt" | "external"
type:CodexConversationStatus:"cancelling_turn" | "closed" | "failed" | "new" | "opening" | "ready" | "reloading" | "running_turn" | "starting_turn"
type:CodexHostStatus:"new" | "restoring" | "workspace_required" | "preparing" | "ready" | "failed" | "closed"
type:CodexMessageRole:"assistant" | "user"
type:CodexWorkActivity:"running_command" | "writing_files"
type:CodexWorkspaceSelectionReason:"access_revoked" | "invalid_selection" | "not_found" | "not_selected"
""".trimIndent()
    }
}
