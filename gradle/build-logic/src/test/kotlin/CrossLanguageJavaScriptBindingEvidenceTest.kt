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
    fun `current 320-symbol compiler snapshot inventories gaps without claiming canonical parity`() {
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
            packedApi = packedEvidence(d049CurrentPublicSymbols(), schema = 1),
        )

        assertEquals(4, evidence.canonical.memberKeys.size)
        assertEquals(320, evidence.packedApi.publicSymbols.size)
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
        val unsupportedFirst = canonicalObject("UnsupportedSingleton.First")
        val unsupportedSecond = canonicalObject("UnsupportedSingleton.Second")
        val authenticationType =
            "type:CodexAuthenticationMethod:\"chatgpt_browser\" | \"chatgpt_device_code\" | \"api_key\""
        val hostType =
            "type:CodexHostStatus:\"new\" | \"restoring\" | \"workspace_required\" | \"preparing\" | \"ready\" | \"failed\" | \"closed\""
        val symbols = listOf(
            authenticationType,
            hostType,
            "type:UnsupportedSingleton:\"first\" | \"second\"",
        ).sorted()
        val evidence = derive(
            listOf(browser, device, new, restoring, closed, unsupportedFirst, unsupportedSecond).sorted(),
            symbols,
            references = listOf(authenticationType, hostType),
        )

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertEquals(setOf(unsupportedFirst, unsupportedSecond), evidence.missingCapabilityKeys.toSet())
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
    fun `authorization URLs preserve validated values purposes and static factories`() {
        val keys = d049AuthorizationUrlKeys()
        val symbols = d049AuthorizationUrlSymbols()
        val evidence = derive(keys, symbols, references = D049_PUBLIC_SYMBOLS)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(4, claims.size)
        claims.values.forEach { claim ->
            assertEquals(listOf(CrossLanguageBindingScenario.VALUE_CONVERSION), claim.sharedScenarios)
            assertEquals(1, claim.publicSymbols.size)
        }
        assertEquals(D049_PUBLIC_SYMBOLS, evidence.packedApi.referencedSymbols)
        assertEquals(376, 372 + claims.size)
        assertEquals(168, 172 - claims.size)
        assertEquals(556, 376 + 12 + 168)
        assertEquals(27, 29 - 2)
        val currentSymbols = d049CurrentPublicSymbols()
        assertEquals(320, currentSymbols.size)
        assertEquals(78, symbolExports(currentSymbols).first.size)
        assertEquals(50, symbolExports(currentSymbols).second.size)
        assertEquals(278, 273 + D049_PUBLIC_SYMBOLS.size)

        listOf(
            D049_PURPOSE to D049_PURPOSE.replace("CodexAuthorizationPurpose", "string"),
            D049_VALUE to D049_VALUE.replace("string", "number"),
            D049_CHAT_GPT to D049_CHAT_GPT.replace("[static]", ""),
            D049_CHAT_GPT to D049_CHAT_GPT.replace("value: string", "value?: string"),
            D049_EXTERNAL to D049_EXTERNAL.replace("value: string", "value: number"),
            D049_EXTERNAL to D049_EXTERNAL.replace(": CodexAuthorizationUrl", ": string"),
        ).forEach { (exact, drifted) ->
            val drift = derive(
                keys,
                symbols.map { if (it == exact) drifted else it }.sorted(),
                references = D049_PUBLIC_SYMBOLS.map { if (it == exact) drifted else it }.sorted(),
            )
            assertTrue(drift.missingCapabilityKeys.isNotEmpty(), "Accepted authorization URL drift: $drifted")
        }

        listOf(D049_CHAT_GPT, D049_EXTERNAL).forEach { symbol ->
            val unreferenced = derive(keys, symbols, references = D049_PUBLIC_SYMBOLS - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && symbol in it })
        }

        val stateKey = canonicalProperty(
            "AgentAuthenticationState",
            "pendingSignInUrl",
            "example/CodexAuthorizationUrl?",
        )
        val typedStateSymbols = listOf(
            "class:CodexAuthenticationState",
            "class:CodexAuthorizationUrl",
            "getter:CodexAuthenticationState#pendingSignInUrl:CodexAuthorizationUrl | null | undefined",
        ).sorted()
        assertEquals(1, derive(listOf(stateKey), typedStateSymbols).projectionClaims.size)
        assertTrue(
            stateKey in derive(
                listOf(stateKey),
                typedStateSymbols.map {
                    if (it.startsWith("getter:")) {
                        "getter:CodexAuthenticationState#pendingSignInUrl:string | null | undefined"
                    } else it
                }.sorted(),
            ).missingCapabilityKeys,
        )

        val future = canonicalFunction(
            "CodexAuthorizationUrl.Companion",
            "future",
            returnType = "example/CodexAuthorizationUrl!!",
            parameters = listOf("kotlin/String!!"),
        )
        assertTrue(future in derive(listOf(future), symbols, references = D049_PUBLIC_SYMBOLS).missingCapabilityKeys)
    }

    @Test
    fun `mcp servers close exact transport configuration value and controller family`() {
        val keys = d050McpServersKeys()
        val symbols = d050McpServersSymbols()
        val evidence = derive(keys, symbols, references = D050_PUBLIC_SYMBOLS)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(43, keys.size)
        assertEquals(43, claims.size)
        assertEquals(D050_PUBLIC_SYMBOLS, evidence.packedApi.referencedSymbols)
        assertEquals(D050_PUBLIC_SYMBOLS.toSet(), claims.values.flatMap { it.publicSymbols }.toSet())
        assertEquals(419, 376 + claims.size)
        assertEquals(125, 168 - claims.size)
        assertEquals(556, 419 + 12 + 125)
        assertEquals(22, 27 - 5)

        val controllerClaims = claims.values.filter { "owner=$CANONICAL_AGENT_PACKAGE/CodexMcpServers" in it.capabilityKey }
        assertEquals(4, controllerClaims.size)
        controllerClaims.forEach { claim ->
            if ("kind=function" in claim.capabilityKey) {
                assertTrue(CrossLanguageBindingScenario.ASYNC_SUCCESS in claim.sharedScenarios)
                assertTrue(CrossLanguageBindingScenario.ASYNC_FAILURE in claim.sharedScenarios)
                assertTrue(CrossLanguageBindingScenario.CANCELLATION in claim.sharedScenarios)
            }
            assertTrue(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP in claim.sharedScenarios)
        }
        val currentSymbols = d050CurrentPublicSymbols()
        assertEquals(369, currentSymbols.size)
        assertEquals(84, symbolExports(currentSymbols).first.size)
        assertEquals(55, symbolExports(currentSymbols).second.size)
    }

    @Test
    fun `mcp servers reject canonical public declaration reference and family drift`() {
        val keys = d050McpServersKeys()
        val symbols = d050McpServersSymbols()

        keys.forEach { exact ->
            val drifted = when {
                "|kind=constructor|" in exact -> exact.replace("suspend=false", "suspend=true")
                "|kind=property|" in exact -> exact.replace("propertyKind=VAL", "propertyKind=VAR")
                else -> exact.replace("suspend=true", "suspend=false")
            }
            val drift = derive(keys - exact + drifted, symbols, references = D050_PUBLIC_SYMBOLS)
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys }, "Accepted canonical drift: $drifted")
        }

        D050_PUBLIC_SYMBOLS.forEach { exact ->
            val drifted = when {
                exact.startsWith("class:") -> "${exact}Drift"
                exact.startsWith("type:") ->
                    exact.replace("AgentMcpStdioTransport | AgentMcpHttpTransport", "AgentMcpHttpTransport | AgentMcpStdioTransport")
                exact.startsWith("constructor:") -> exact.replaceFirst("string", "number")
                exact.startsWith("getter:") -> "$exact | false"
                else -> exact.replaceFirst("#", "#drift")
            }
            val renameClass = exact.removePrefix("class:").takeIf { exact.startsWith("class:") }
            val driftSymbols = if (renameClass != null) {
                val pattern = Regex("\\b${Regex.escape(renameClass)}\\b")
                symbols.map { it.replace(pattern, "${renameClass}Drift") }.sorted()
            } else {
                symbols.map { if (it == exact) drifted else it }.sorted()
            }
            val references = if (renameClass != null) {
                val pattern = Regex("\\b${Regex.escape(renameClass)}\\b")
                D050_PUBLIC_SYMBOLS.map { it.replace(pattern, "${renameClass}Drift") }.sorted()
            } else {
                D050_PUBLIC_SYMBOLS.map { if (it == exact) drifted else it }.sorted()
            }
            val drift = derive(keys, driftSymbols, references = references)
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys }, "Accepted public drift: $drifted")
        }

        keys.forEach { omitted ->
            val partial = derive(keys - omitted, symbols, references = D050_PUBLIC_SYMBOLS)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys }, "Accepted without $omitted")
        }
        D050_PUBLIC_SYMBOLS.forEach { omitted ->
            val unreferenced = derive(keys, symbols, references = D050_PUBLIC_SYMBOLS - omitted)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && omitted in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey in keys })
        }

        val future = canonicalProperty("CodexMcpServers", "future", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive(keys + future, symbols, references = D050_PUBLIC_SYMBOLS)
        assertTrue(future in futureEvidence.missingCapabilityKeys)
        assertTrue(futureEvidence.projectionClaims.none { it.capabilityKey in keys })

        val foreign = keys.first().replace(CANONICAL_AGENT_PACKAGE, "foreign")
        val crossPackage = derive(keys + foreign, symbols, references = D050_PUBLIC_SYMBOLS)
        assertTrue(foreign in crossPackage.missingCapabilityKeys)
        assertTrue(crossPackage.projectionClaims.none { it.capabilityKey in keys })

        val exactGetter = D050_PUBLIC_SYMBOLS.single { it == "getter:AgentMcpServer#name:string" }
        val ambiguousGetter = exactGetter.replace(":string", ":number")
        val ambiguous = derive(
            keys,
            (symbols + ambiguousGetter).sorted(),
            references = (D050_PUBLIC_SYMBOLS + ambiguousGetter).sorted(),
        )
        assertTrue(ambiguous.projectionClaims.none { it.capabilityKey in keys })
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
    fun `connector family projects eleven generic capabilities and rejects drift`() {
        val constructor = canonicalConstructor(
            "AgentConnector",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String?",
                "kotlin/Boolean!!",
                "kotlin/Boolean!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
            ),
            defaultParameterIndices = setOf(2, 3, 4, 5, 6),
        )
        val description = canonicalProperty("AgentConnector", "description", "kotlin/String!!")
        val id = canonicalProperty("AgentConnector", "id", "kotlin/String!!")
        val installUrl = canonicalProperty("AgentConnector", "installUrl", "kotlin/String?")
        val isAccessible = canonicalProperty("AgentConnector", "isAccessible", "kotlin/Boolean!!")
        val isEnabled = canonicalProperty("AgentConnector", "isEnabled", "kotlin/Boolean!!")
        val name = canonicalProperty("AgentConnector", "name", "kotlin/String!!")
        val pluginNames = canonicalProperty(
            "AgentConnector",
            "pluginNames",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val agentConnectors = canonicalProperty("CodexAgent", "connectors", "example/CodexConnectors!!")
        val isAvailable = canonicalProperty("CodexConnectors", "isAvailable", "kotlin/Boolean!!")
        val list = canonicalFunction(
            "CodexConnectors",
            "list",
            returnType = "kotlin.collections/List<INVARIANT:example/AgentConnector!!>!!",
            suspendFunction = true,
            parameters = listOf("kotlin/Boolean!!"),
            defaultParameterIndices = setOf(0),
        )
        val keys = listOf(
            constructor,
            description,
            id,
            installUrl,
            isAccessible,
            isEnabled,
            name,
            pluginNames,
            agentConnectors,
            isAvailable,
            list,
        ).sorted()
        val constructorSymbol =
            "constructor:AgentConnector#(id: string, name: string, description?: string, " +
                "installUrl?: string | null | undefined, isAccessible?: boolean, isEnabled?: boolean, " +
                "pluginNames?: ReadonlyArray<string>)"
        val installUrlSymbol = "getter:AgentConnector#installUrl:string | null | undefined"
        val pluginNamesSymbol = "getter:AgentConnector#pluginNames:ReadonlyArray<string>"
        val listSymbol =
            "method:CodexConnectors#list:(forceReload?: boolean, " +
                "signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConnector>>"
        val symbols = listOf(
            "class:AgentConnector",
            "class:CodexAgent",
            "class:CodexConnectors",
            constructorSymbol,
            "getter:AgentConnector#description:string",
            "getter:AgentConnector#id:string",
            installUrlSymbol,
            "getter:AgentConnector#isAccessible:boolean",
            "getter:AgentConnector#isEnabled:boolean",
            "getter:AgentConnector#name:string",
            pluginNamesSymbol,
            "getter:CodexAgent#connectors:CodexConnectors",
            "getter:CodexConnectors#isAvailable:boolean",
            listSymbol,
        ).sorted()
        val references = symbols - "class:CodexAgent"
        val evidence = derive(keys, symbols, references = references)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(11, evidence.projectionClaims.size)
        assertEquals(14, symbols.size) // Thirteen new symbols plus the existing CodexAgent owner class.
        assertEquals(13, references.size)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        assertEquals(
            mapOf(
                constructor to listOf(constructorSymbol),
                description to listOf("getter:AgentConnector#description:string"),
                id to listOf("getter:AgentConnector#id:string"),
                installUrl to listOf(installUrlSymbol),
                isAccessible to listOf("getter:AgentConnector#isAccessible:boolean"),
                isEnabled to listOf("getter:AgentConnector#isEnabled:boolean"),
                name to listOf("getter:AgentConnector#name:string"),
                pluginNames to listOf(pluginNamesSymbol),
                agentConnectors to listOf("getter:CodexAgent#connectors:CodexConnectors"),
                isAvailable to listOf("getter:CodexConnectors#isAvailable:boolean"),
                list to listOf(listSymbol),
            ),
            evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols },
        )
        assertEquals(
            setOf(CrossLanguageBindingScenario.ASYNC_SUCCESS, CrossLanguageBindingScenario.ASYNC_FAILURE),
            evidence.projectionClaims.single { it.capabilityKey == list }.sharedScenarios.toSet(),
        )
        assertTrue(evidence.projectionClaims.filterNot { it.capabilityKey == list }.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })

        listOf(
            constructorSymbol.replace("description?: string", "description: string"),
            constructorSymbol.replace(
                "installUrl?: string | null | undefined",
                "installUrl?: string",
            ),
            constructorSymbol.replace("ReadonlyArray<string>", "Array<string>"),
        ).forEach { drifted ->
            val driftedSymbols = symbols.map { if (it == constructorSymbol) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == constructorSymbol) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(constructor in drift.missingCapabilityKeys, "Accepted constructor drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == constructor })
        }
        listOf(
            installUrl to installUrlSymbol.replace("string | null | undefined", "string"),
            pluginNames to pluginNamesSymbol.replace("ReadonlyArray<string>", "Array<string>"),
        ).forEach { (key, drifted) ->
            val exact = if (key == installUrl) installUrlSymbol else pluginNamesSymbol
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "Accepted property drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }
        listOf(
            listSymbol.replace("forceReload?: boolean", "forceReload: boolean"),
            listSymbol.replace("AbortSignal | null | undefined", "string"),
            listSymbol.replace(
                "Promise<ReadonlyArray<AgentConnector>>",
                "Promise<Array<AgentConnector>>",
            ),
        ).forEach { drifted ->
            val driftedSymbols = symbols.map { if (it == listSymbol) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == listSymbol) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(list in drift.missingCapabilityKeys, "Accepted list drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == list })
        }

        listOf(constructorSymbol to constructor, listSymbol to list).forEach { (symbol, key) ->
            val unreferenced = derive(keys, symbols, references = references - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey == key })
        }

        val listOverload = listSymbol.replace("forceReload?: boolean", "reload?: boolean")
        val ambiguous = derive(
            keys,
            (symbols + listOverload).sorted(),
            references = (references + listOverload).sorted(),
        )
        assertTrue(ambiguous.errors.any { "Ambiguous" in it && list in it })
        assertTrue(ambiguous.projectionClaims.none { it.capabilityKey == list })

        val future = canonicalProperty("CodexConnectors", "future", "kotlin/String!!")
        val futureEvidence = derive(keys + future, symbols, references = references)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertTrue(futureEvidence.projectionClaims.none { it.capabilityKey == future })
    }

    @Test
    fun `models family projects eighteen generic capabilities and rejects drift`() {
        val serviceTierConstructor = canonicalConstructor(
            "AgentServiceTier",
            listOf("kotlin/String!!", "kotlin/String!!", "kotlin/String!!"),
        )
        val serviceTierDescription = canonicalProperty("AgentServiceTier", "description", "kotlin/String!!")
        val serviceTierId = canonicalProperty("AgentServiceTier", "id", "kotlin/String!!")
        val serviceTierName = canonicalProperty("AgentServiceTier", "name", "kotlin/String!!")
        val modelConstructor = canonicalConstructor(
            "AgentModel",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                "kotlin/String!!",
                "kotlin/Boolean!!",
                "kotlin.collections/List<INVARIANT:example/AgentServiceTier!!>!!",
                "kotlin/String?",
            ),
            defaultParameterIndices = setOf(6, 7),
        )
        val modelDefaultEffort = canonicalProperty("AgentModel", "defaultEffort", "kotlin/String!!")
        val modelDefaultServiceTier = canonicalProperty("AgentModel", "defaultServiceTier", "kotlin/String?")
        val modelDescription = canonicalProperty("AgentModel", "description", "kotlin/String!!")
        val modelDisplayName = canonicalProperty("AgentModel", "displayName", "kotlin/String!!")
        val modelId = canonicalProperty("AgentModel", "id", "kotlin/String!!")
        val modelIsDefault = canonicalProperty("AgentModel", "isDefault", "kotlin/Boolean!!")
        val modelServiceTiers = canonicalProperty(
            "AgentModel",
            "serviceTiers",
            "kotlin.collections/List<INVARIANT:example/AgentServiceTier!!>!!",
        )
        val modelSupportedEfforts = canonicalProperty(
            "AgentModel",
            "supportedEfforts",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val agentModels = canonicalProperty("CodexAgent", "models", "example/CodexModels!!")
        val list = canonicalFunction(
            "CodexModels",
            "list",
            returnType = "kotlin.collections/List<INVARIANT:example/AgentModel!!>!!",
            suspendFunction = true,
        )
        val resolve = canonicalFunction(
            "CodexModels",
            "resolve",
            returnType = "example/AgentModel!!",
            suspendFunction = true,
            parameters = listOf("example/AgentResolution!!"),
            defaultParameterIndices = setOf(0),
        )
        val resolveEffort = canonicalFunction(
            "CodexModels",
            "resolveEffort",
            returnType = "kotlin/String!!",
            suspendFunction = true,
            parameters = listOf("example/AgentModel!!", "example/AgentResolution!!"),
            defaultParameterIndices = setOf(1),
        )
        val resolveServiceTier = canonicalFunction(
            "CodexModels",
            "resolveServiceTier",
            returnType = "example/AgentServiceTier?",
            suspendFunction = true,
            parameters = listOf("example/AgentModel!!", "example/AgentResolution!!"),
            defaultParameterIndices = setOf(1),
        )
        val keys = listOf(
            serviceTierConstructor,
            serviceTierDescription,
            serviceTierId,
            serviceTierName,
            modelConstructor,
            modelDefaultEffort,
            modelDefaultServiceTier,
            modelDescription,
            modelDisplayName,
            modelId,
            modelIsDefault,
            modelServiceTiers,
            modelSupportedEfforts,
            agentModels,
            list,
            resolve,
            resolveEffort,
            resolveServiceTier,
        ).sorted()
        val modelSymbols = modelPublicSymbols()
        val modelConstructorSymbol = modelSymbols.single { it.startsWith("constructor:AgentModel#") }
        val serviceTierConstructorSymbol =
            modelSymbols.single { it.startsWith("constructor:AgentServiceTier#") }
        val listSymbol = modelSymbols.single { it.startsWith("method:CodexModels#list:") }
        val resolveSymbol = modelSymbols.single { it.startsWith("method:CodexModels#resolve:") }
        val resolveEffortSymbol = modelSymbols.single { it.startsWith("method:CodexModels#resolveEffort:") }
        val resolveServiceTierSymbol =
            modelSymbols.single { it.startsWith("method:CodexModels#resolveServiceTier:") }
        val symbols = (modelSymbols + "class:CodexAgent").sorted()
        val references = modelSymbols
        val evidence = derive(keys, symbols, references = references)
        val claims = evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(18, keys.size)
        assertEquals(18, evidence.projectionClaims.size)
        assertEquals(21, references.size)
        assertEquals(229, 208 + modelSymbols.size)
        assertEquals(182, 161 + references.size)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        assertEquals(
            mapOf(
                serviceTierConstructor to listOf(serviceTierConstructorSymbol),
                serviceTierDescription to listOf("getter:AgentServiceTier#description:string"),
                serviceTierId to listOf("getter:AgentServiceTier#id:string"),
                serviceTierName to listOf("getter:AgentServiceTier#name:string"),
                modelConstructor to listOf(modelConstructorSymbol),
                modelDefaultEffort to listOf("getter:AgentModel#defaultEffort:string"),
                modelDefaultServiceTier to
                    listOf("getter:AgentModel#defaultServiceTier:string | null | undefined"),
                modelDescription to listOf("getter:AgentModel#description:string"),
                modelDisplayName to listOf("getter:AgentModel#displayName:string"),
                modelId to listOf("getter:AgentModel#id:string"),
                modelIsDefault to listOf("getter:AgentModel#isDefault:boolean"),
                modelServiceTiers to listOf("getter:AgentModel#serviceTiers:ReadonlyArray<AgentServiceTier>"),
                modelSupportedEfforts to listOf("getter:AgentModel#supportedEfforts:ReadonlyArray<string>"),
                agentModels to listOf("getter:CodexAgent#models:CodexModels"),
                list to listOf(listSymbol),
                resolve to listOf(resolveSymbol),
                resolveEffort to listOf(resolveEffortSymbol),
                resolveServiceTier to listOf(resolveServiceTierSymbol),
            ),
            claims,
        )
        assertTrue(claims.values.all { it.size == 1 })
        assertEquals(265, 247 + claims.size)
        assertEquals(279, 297 - claims.size)
        assertEquals(556, 265 + 12 + 279)
        val completedGapOwners = setOf("AgentModel", "AgentServiceTier", "CodexModels")
        assertEquals(58, 61 - completedGapOwners.size)
        assertTrue(evidence.projectionClaims.filter { "|owner=example/CodexModels|" in it.capabilityKey }.all {
            it.sharedScenarios.toSet() ==
                setOf(CrossLanguageBindingScenario.ASYNC_SUCCESS, CrossLanguageBindingScenario.ASYNC_FAILURE)
        })
        assertTrue(evidence.projectionClaims.filterNot { "|owner=example/CodexModels|" in it.capabilityKey }.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })

        listOf(
            serviceTierConstructor to serviceTierConstructorSymbol.replace("description: string", "description: number"),
            serviceTierDescription to "getter:AgentServiceTier#description:number",
            serviceTierId to "getter:AgentServiceTier#id:number",
            serviceTierName to "getter:AgentServiceTier#name:number",
            modelConstructor to modelConstructorSymbol.replace("ReadonlyArray<string>", "Array<string>"),
            modelDefaultEffort to "getter:AgentModel#defaultEffort:number",
            modelDefaultServiceTier to "getter:AgentModel#defaultServiceTier:string",
            modelDescription to "getter:AgentModel#description:number",
            modelDisplayName to "getter:AgentModel#displayName:number",
            modelId to "getter:AgentModel#id:number",
            modelIsDefault to "getter:AgentModel#isDefault:string",
            modelServiceTiers to "getter:AgentModel#serviceTiers:Array<AgentServiceTier>",
            modelSupportedEfforts to "getter:AgentModel#supportedEfforts:Array<string>",
            agentModels to "getter:CodexAgent#models:string",
            list to listSymbol.replace("ReadonlyArray<AgentModel>", "Array<AgentModel>"),
            resolve to resolveSymbol.replace("resolution?: AgentResolution", "resolution: AgentResolution"),
            resolveEffort to resolveEffortSymbol.replace("Promise<string>", "Promise<number>"),
            resolveServiceTier to resolveServiceTierSymbol.replace(
                "AgentServiceTier | null | undefined",
                "AgentServiceTier",
            ),
        ).forEach { (key, drifted) ->
            val exact = claims.getValue(key).single()
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "Accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(
            Triple(
                modelConstructor,
                modelConstructorSymbol,
                modelConstructorSymbol.replace("serviceTiers?:", "serviceTiers:"),
            ),
            Triple(
                modelConstructor,
                modelConstructorSymbol,
                modelConstructorSymbol.replace(
                    "defaultServiceTier?: string | null | undefined",
                    "defaultServiceTier?: string",
                ),
            ),
            Triple(
                modelConstructor,
                modelConstructorSymbol,
                modelConstructorSymbol.replace("defaultServiceTier?:", "defaultServiceTier:"),
            ),
            Triple(
                modelId,
                "getter:AgentModel#id:string",
                "property:AgentModel#id:string",
            ),
            Triple(
                resolveEffort,
                resolveEffortSymbol,
                resolveEffortSymbol.replace("resolution?: AgentResolution", "resolution: AgentResolution"),
            ),
            Triple(
                resolveEffort,
                resolveEffortSymbol,
                resolveEffortSymbol.replace("model: AgentModel", "model: string"),
            ),
            Triple(
                resolveServiceTier,
                resolveServiceTierSymbol,
                resolveServiceTierSymbol.replace("resolution?: AgentResolution", "resolution: AgentResolution"),
            ),
            Triple(
                resolveServiceTier,
                resolveServiceTierSymbol,
                resolveServiceTierSymbol.replace("AbortSignal | null | undefined", "string"),
            ),
        ).forEach { (key, exact, drifted) ->
            val drift = derive(
                keys,
                symbols.map { if (it == exact) drifted else it }.sorted(),
                references = references.map { if (it == exact) drifted else it }.sorted(),
            )
            assertTrue(key in drift.missingCapabilityKeys, "Accepted shape drift: $drifted")
        }

        val futureOwnerSymbol = resolveServiceTierSymbol.replace("CodexModels#", "FutureModels#")
        val futureOwner = derive(
            keys,
            (symbols.map { if (it == resolveServiceTierSymbol) futureOwnerSymbol else it } +
                "class:FutureModels").sorted(),
            references = references.map {
                if (it == resolveServiceTierSymbol) futureOwnerSymbol else it
            }.sorted(),
        )
        assertTrue(resolveServiceTier in futureOwner.missingCapabilityKeys)

        listOf(
            serviceTierConstructorSymbol to serviceTierConstructor,
            modelConstructorSymbol to modelConstructor,
            listSymbol to list,
            resolveSymbol to resolve,
            resolveEffortSymbol to resolveEffort,
            resolveServiceTierSymbol to resolveServiceTier,
        ).forEach { (symbol, key) ->
            val unreferenced = derive(keys, symbols, references = references - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(
            list to listSymbol.replace("(signal?: AbortSignal | null | undefined)", "()"),
            resolve to resolveSymbol.replace(", signal?: AbortSignal | null | undefined", ""),
            resolveEffort to resolveEffortSymbol.replace(", signal?: AbortSignal | null | undefined", ""),
            resolveServiceTier to
                resolveServiceTierSymbol.replace(", signal?: AbortSignal | null | undefined", ""),
        ).forEach { (key, overload) ->
            val ambiguous = derive(
                keys,
                (symbols + overload).sorted(),
                references = (references + overload).sorted(),
            )
            assertTrue(ambiguous.errors.any { "Ambiguous" in it && key in it })
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey == key })
        }
    }

    @Test
    fun `skills family projects twenty four generic capabilities and rejects drift`() {
        val skillConstructor = canonicalConstructor(
            "AgentSkill",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "example/AgentSkillScope!!",
                "kotlin/Boolean!!",
                "kotlin/String?",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                "kotlin/Boolean!!",
                "example/AgentResourceOrigin!!",
            ),
            defaultParameterIndices = setOf(6, 7, 8, 9),
        )
        val skillBrandColor = canonicalProperty("AgentSkill", "brandColor", "kotlin/String?")
        val skillCanUninstall = canonicalProperty("AgentSkill", "canUninstall", "kotlin/Boolean!!")
        val skillDependencies = canonicalProperty(
            "AgentSkill",
            "dependencies",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val skillDescription = canonicalProperty("AgentSkill", "description", "kotlin/String!!")
        val skillDisplayName = canonicalProperty("AgentSkill", "displayName", "kotlin/String!!")
        val skillIsEnabled = canonicalProperty("AgentSkill", "isEnabled", "kotlin/Boolean!!")
        val skillName = canonicalProperty("AgentSkill", "name", "kotlin/String!!")
        val skillOrigin = canonicalProperty("AgentSkill", "origin", "example/AgentResourceOrigin!!")
        val skillPath = canonicalProperty("AgentSkill", "path", "kotlin/String!!")
        val skillScope = canonicalProperty("AgentSkill", "scope", "example/AgentSkillScope!!")
        val catalogConstructor = canonicalConstructor(
            "AgentSkillCatalog",
            listOf(
                "kotlin.collections/List<INVARIANT:example/AgentSkill!!>!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
            ),
            defaultParameterIndices = setOf(1),
        )
        val catalogErrors = canonicalProperty(
            "AgentSkillCatalog",
            "errors",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        )
        val catalogSkills = canonicalProperty(
            "AgentSkillCatalog",
            "skills",
            "kotlin.collections/List<INVARIANT:example/AgentSkill!!>!!",
        )
        val chunkConstructor = canonicalConstructor(
            "AgentSkillChunk",
            listOf("kotlin/String!!", "kotlin/Long?", "kotlin/Long!!"),
        )
        val chunkContent = canonicalProperty("AgentSkillChunk", "content", "kotlin/String!!")
        val chunkNextOffset = canonicalProperty("AgentSkillChunk", "nextOffset", "kotlin/Long?")
        val chunkTotalBytes = canonicalProperty("AgentSkillChunk", "totalBytes", "kotlin/Long!!")
        val agentSkills = canonicalProperty("CodexAgent", "skills", "example/CodexSkills!!")
        val isAvailable = canonicalProperty("CodexSkills", "isAvailable", "kotlin/Boolean!!")
        val install = canonicalFunction(
            "CodexSkills",
            "install",
            returnType = "example/AgentSkill!!",
            suspendFunction = true,
            parameters = listOf("kotlin/String!!", "example/AgentInstallationScope!!"),
        )
        val list = canonicalFunction(
            "CodexSkills",
            "list",
            returnType = "example/AgentSkillCatalog!!",
            suspendFunction = true,
            parameters = listOf("kotlin/Boolean!!"),
            defaultParameterIndices = setOf(0),
        )
        val read = canonicalFunction(
            "CodexSkills",
            "read",
            returnType = "example/AgentSkillChunk!!",
            suspendFunction = true,
            parameters = listOf("kotlin/String!!", "kotlin/Long!!"),
            defaultParameterIndices = setOf(1),
        )
        val uninstall = canonicalFunction(
            "CodexSkills",
            "uninstall",
            suspendFunction = true,
            parameters = listOf("example/AgentSkill!!"),
        )
        val keys = listOf(
            skillConstructor,
            skillBrandColor,
            skillCanUninstall,
            skillDependencies,
            skillDescription,
            skillDisplayName,
            skillIsEnabled,
            skillName,
            skillOrigin,
            skillPath,
            skillScope,
            catalogConstructor,
            catalogErrors,
            catalogSkills,
            chunkConstructor,
            chunkContent,
            chunkNextOffset,
            chunkTotalBytes,
            agentSkills,
            isAvailable,
            install,
            list,
            read,
            uninstall,
        ).sorted()
        val skillSymbols = skillsPublicSymbols()
        val symbols = (skillSymbols + "class:CodexAgent").sorted()
        val references = skillSymbols
        val evidence = derive(keys, symbols, references = references)
        val claims = evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols }
        val skillConstructorSymbol = skillSymbols.single { it.startsWith("constructor:AgentSkill#") }
        val catalogConstructorSymbol = skillSymbols.single { it.startsWith("constructor:AgentSkillCatalog#") }
        val chunkConstructorSymbol = skillSymbols.single { it.startsWith("constructor:AgentSkillChunk#") }
        val installSymbol = skillSymbols.single { it.startsWith("method:CodexSkills#install:") }
        val listSymbol = skillSymbols.single { it.startsWith("method:CodexSkills#list:") }
        val readSymbol = skillSymbols.single { it.startsWith("method:CodexSkills#read:") }
        val uninstallSymbol = skillSymbols.single { it.startsWith("method:CodexSkills#uninstall:") }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(24, keys.size)
        assertEquals(24, claims.size)
        assertEquals(28, references.size)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        assertEquals(
            mapOf(
                skillConstructor to listOf(skillConstructorSymbol),
                skillBrandColor to listOf("getter:AgentSkill#brandColor:string | null | undefined"),
                skillCanUninstall to listOf("getter:AgentSkill#canUninstall:boolean"),
                skillDependencies to listOf("getter:AgentSkill#dependencies:ReadonlyArray<string>"),
                skillDescription to listOf("getter:AgentSkill#description:string"),
                skillDisplayName to listOf("getter:AgentSkill#displayName:string"),
                skillIsEnabled to listOf("getter:AgentSkill#isEnabled:boolean"),
                skillName to listOf("getter:AgentSkill#name:string"),
                skillOrigin to listOf("getter:AgentSkill#origin:AgentResourceOrigin"),
                skillPath to listOf("getter:AgentSkill#path:string"),
                skillScope to listOf("getter:AgentSkill#scope:AgentSkillScope"),
                catalogConstructor to listOf(catalogConstructorSymbol),
                catalogErrors to listOf("getter:AgentSkillCatalog#errors:ReadonlyArray<string>"),
                catalogSkills to listOf("getter:AgentSkillCatalog#skills:ReadonlyArray<AgentSkill>"),
                chunkConstructor to listOf(chunkConstructorSymbol),
                chunkContent to listOf("getter:AgentSkillChunk#content:string"),
                chunkNextOffset to listOf("getter:AgentSkillChunk#nextOffset:bigint | null | undefined"),
                chunkTotalBytes to listOf("getter:AgentSkillChunk#totalBytes:bigint"),
                agentSkills to listOf("getter:CodexAgent#skills:CodexSkills"),
                isAvailable to listOf("getter:CodexSkills#isAvailable:boolean"),
                install to listOf(installSymbol),
                list to listOf(listSymbol),
                read to listOf(readSymbol),
                uninstall to listOf(uninstallSymbol),
            ),
            claims,
        )
        assertTrue(claims.values.all { it.size == 1 })
        assertEquals(294, 270 + claims.size)
        assertEquals(250, 274 - claims.size)
        assertEquals(556, 294 + 12 + 250)
        assertEquals(52, 56 - setOf("AgentSkill", "AgentSkillCatalog", "AgentSkillChunk", "CodexSkills").size)
        assertEquals(284, currentPublicSymbols().size)
        assertTrue(skillSymbols.all { it in currentPublicSymbols() })
        assertTrue(evidence.projectionClaims.filter { "|owner=example/CodexSkills|" in it.capabilityKey && "|kind=function|" in it.capabilityKey }.all {
            it.sharedScenarios.toSet() ==
                setOf(CrossLanguageBindingScenario.ASYNC_SUCCESS, CrossLanguageBindingScenario.ASYNC_FAILURE)
        })
        assertTrue(evidence.projectionClaims.filterNot { "|owner=example/CodexSkills|" in it.capabilityKey && "|kind=function|" in it.capabilityKey }.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })

        mapOf(
            skillConstructor to skillConstructorSymbol.replace("scope: AgentSkillScope", "scope: string"),
            skillBrandColor to "getter:AgentSkill#brandColor:string",
            skillCanUninstall to "getter:AgentSkill#canUninstall:string",
            skillDependencies to "getter:AgentSkill#dependencies:Array<string>",
            skillDescription to "getter:AgentSkill#description:number",
            skillDisplayName to "getter:AgentSkill#displayName:number",
            skillIsEnabled to "getter:AgentSkill#isEnabled:string",
            skillName to "getter:AgentSkill#name:number",
            skillOrigin to "getter:AgentSkill#origin:string",
            skillPath to "getter:AgentSkill#path:number",
            skillScope to "getter:AgentSkill#scope:string",
            catalogConstructor to catalogConstructorSymbol.replace("ReadonlyArray<AgentSkill>", "Array<AgentSkill>"),
            catalogErrors to "getter:AgentSkillCatalog#errors:Array<string>",
            catalogSkills to "getter:AgentSkillCatalog#skills:Array<AgentSkill>",
            chunkConstructor to chunkConstructorSymbol.replace("nextOffset: bigint | null | undefined", "nextOffset: bigint"),
            chunkContent to "getter:AgentSkillChunk#content:number",
            chunkNextOffset to "getter:AgentSkillChunk#nextOffset:number | null | undefined",
            chunkTotalBytes to "getter:AgentSkillChunk#totalBytes:number",
            agentSkills to "getter:CodexAgent#skills:string",
            isAvailable to "getter:CodexSkills#isAvailable:string",
            install to installSymbol.replace("scope: AgentInstallationScope", "scope: string"),
            list to listSymbol.replace("forceReload?: boolean", "forceReload: boolean"),
            read to readSymbol.replace("offset?: bigint", "offset?: number"),
            uninstall to uninstallSymbol.replace("Promise<void>", "Promise<string>"),
        ).forEach { (key, drifted) ->
            val exact = claims.getValue(key).single()
            val drift = derive(
                keys,
                symbols.map { if (it == exact) drifted else it }.sorted(),
                references = references.map { if (it == exact) drifted else it }.sorted(),
            )
            assertTrue(key in drift.missingCapabilityKeys, "Accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(
            Triple(skillConstructor, skillConstructorSymbol, skillConstructorSymbol.replace("origin?:", "origin:")),
            Triple(skillConstructor, skillConstructorSymbol, skillConstructorSymbol.replace("dependencies?: ReadonlyArray<string>", "dependencies?: Array<string>")),
            Triple(catalogConstructor, catalogConstructorSymbol, catalogConstructorSymbol.replace("errors?:", "errors:")),
            Triple(chunkConstructor, chunkConstructorSymbol, chunkConstructorSymbol.replace("totalBytes: bigint", "totalBytes?: bigint")),
            Triple(install, installSymbol, installSymbol.replace("signal?: AbortSignal | null | undefined", "signal?: string")),
            Triple(list, listSymbol, listSymbol.replace("Promise<AgentSkillCatalog>", "Promise<ReadonlyArray<AgentSkill>>")),
            Triple(read, readSymbol, readSymbol.replace("offset?: bigint", "offset: bigint")),
            Triple(uninstall, uninstallSymbol, uninstallSymbol.replace("skill: AgentSkill", "skill: string")),
        ).forEach { (key, exact, drifted) ->
            val drift = derive(
                keys,
                symbols.map { if (it == exact) drifted else it }.sorted(),
                references = references.map { if (it == exact) drifted else it }.sorted(),
            )
            assertTrue(key in drift.missingCapabilityKeys, "Accepted shape drift: $drifted")
        }

        listOf(
            skillConstructorSymbol to skillConstructor,
            catalogConstructorSymbol to catalogConstructor,
            chunkConstructorSymbol to chunkConstructor,
            installSymbol to install,
            listSymbol to list,
            readSymbol to read,
            uninstallSymbol to uninstall,
        ).forEach { (symbol, key) ->
            val unreferenced = derive(keys, symbols, references = references - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(
            list to listSymbol.replace("forceReload?: boolean", "reload?: boolean"),
            read to readSymbol.replace("offset?: bigint", "start?: bigint"),
            install to installSymbol.replace(", signal?: AbortSignal | null | undefined", ""),
            uninstall to uninstallSymbol.replace(", signal?: AbortSignal | null | undefined", ""),
        ).forEach { (key, overload) ->
            val ambiguous = derive(
                keys,
                (symbols + overload).sorted(),
                references = (references + overload).sorted(),
            )
            assertTrue(ambiguous.errors.any { "Ambiguous" in it && key in it })
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey == key })
        }

        val future = canonicalProperty("CodexSkills", "future", "kotlin/String!!")
        val futureEvidence = derive(keys + future, symbols, references = references)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertTrue(futureEvidence.projectionClaims.none { it.capabilityKey == future })
    }

    @Test
    fun `capability invocation and message metadata project seventeen exact capabilities and reject drift`() {
        fun agentProperty(
            owner: String,
            name: String,
            type: String,
            propertyKind: String = "VAL",
        ): String = canonicalProperty(owner, name, type, propertyKind)
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")

        fun agentConstructor(
            owner: String,
            parameters: List<String>,
            defaultParameterIndices: Set<Int> = emptySet(),
        ): String = canonicalConstructor(owner, parameters, defaultParameterIndices)
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")

        val capabilityDisplayLabel = agentProperty("AgentCapability", "displayLabel", "kotlin/String!!")
        val capabilityIcon = agentProperty("AgentCapability", "icon", "kotlin/String?")
        val capabilityId = agentProperty("AgentCapability", "id", "kotlin/String!!")
        val capabilityPromptLabel = agentProperty("AgentCapability", "promptLabel", "kotlin/String!!")
        val invocationKey = agentProperty("AgentInvocation", "key", "kotlin/String!!")
        val invocationName = agentProperty("AgentInvocation", "name", "kotlin/String!!")
        val pluginConstructor = agentConstructor(
            "AgentInvocation.Plugin",
            listOf("kotlin/String!!", "kotlin/String!!"),
        )
        val pluginKey = agentProperty("AgentInvocation.Plugin", "key", "kotlin/String!!")
        val pluginName = agentProperty("AgentInvocation.Plugin", "name", "kotlin/String!!")
        val pluginUri = agentProperty("AgentInvocation.Plugin", "uri", "kotlin/String!!")
        val skillConstructor = agentConstructor(
            "AgentInvocation.Skill",
            listOf("kotlin/String!!", "kotlin/String!!"),
        )
        val skillKey = agentProperty("AgentInvocation.Skill", "key", "kotlin/String!!")
        val skillName = agentProperty("AgentInvocation.Skill", "name", "kotlin/String!!")
        val skillPath = agentProperty("AgentInvocation.Skill", "path", "kotlin/String!!")
        val messageCapabilities = agentProperty(
            "AgentMessage",
            "capabilities",
            "kotlin.collections/Set<INVARIANT:$CANONICAL_AGENT_PACKAGE/AgentCapability!!>!!",
        )
        val messageCollaborationMode = agentProperty(
            "AgentMessage",
            "collaborationMode",
            "$CANONICAL_AGENT_PACKAGE/AgentCollaborationMode!!",
        )
        val messageInvocations = agentProperty(
            "AgentMessage",
            "invocations",
            "kotlin.collections/List<INVARIANT:$CANONICAL_AGENT_PACKAGE/AgentInvocation!!>!!",
        )
        val keys = listOf(
            capabilityDisplayLabel,
            capabilityIcon,
            capabilityId,
            capabilityPromptLabel,
            invocationKey,
            invocationName,
            pluginConstructor,
            pluginKey,
            pluginName,
            pluginUri,
            skillConstructor,
            skillKey,
            skillName,
            skillPath,
            messageCapabilities,
            messageCollaborationMode,
            messageInvocations,
        ).sorted()
        val familySymbols = d043PublicSymbols()
        val symbols = (familySymbols + "class:CodexMessage").sorted()
        val evidence = derive(keys, symbols, references = familySymbols)
        val claims = evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols }
        val pluginConstructorSymbol = familySymbols.single { it.startsWith("constructor:AgentPluginInvocation#") }
        val skillConstructorSymbol = familySymbols.single { it.startsWith("constructor:AgentSkillInvocation#") }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(17, keys.size)
        assertEquals(17, claims.size)
        assertEquals(18, familySymbols.size)
        assertEquals(familySymbols, evidence.packedApi.referencedSymbols)
        assertEquals(
            mapOf(
                capabilityDisplayLabel to listOf(AGENT_CAPABILITY_DISPLAY_LABEL),
                capabilityIcon to listOf(AGENT_CAPABILITY_ICON),
                capabilityId to listOf(AGENT_CAPABILITY_ID),
                capabilityPromptLabel to listOf(AGENT_CAPABILITY_PROMPT_LABEL),
                invocationKey to listOf(
                    "getter:AgentPluginInvocation#key:string",
                    "getter:AgentSkillInvocation#key:string",
                    AGENT_INVOCATION_TYPE,
                ).sorted(),
                invocationName to listOf(
                    "getter:AgentPluginInvocation#name:string",
                    "getter:AgentSkillInvocation#name:string",
                    AGENT_INVOCATION_TYPE,
                ).sorted(),
                pluginConstructor to listOf(pluginConstructorSymbol),
                pluginKey to listOf("getter:AgentPluginInvocation#key:string"),
                pluginName to listOf("getter:AgentPluginInvocation#name:string"),
                pluginUri to listOf("getter:AgentPluginInvocation#uri:string"),
                skillConstructor to listOf(skillConstructorSymbol),
                skillKey to listOf("getter:AgentSkillInvocation#key:string"),
                skillName to listOf("getter:AgentSkillInvocation#name:string"),
                skillPath to listOf("getter:AgentSkillInvocation#path:string"),
                messageCapabilities to listOf("getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>"),
                messageCollaborationMode to listOf("getter:CodexMessage#collaborationMode:AgentCollaborationMode"),
                messageInvocations to listOf("getter:CodexMessage#invocations:ReadonlyArray<AgentInvocation>"),
            ),
            claims,
        )
        assertEquals(
            listOf(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING),
            evidence.projectionClaims.single { it.capabilityKey == messageCapabilities }.sharedScenarios,
        )
        assertTrue(evidence.projectionClaims.filterNot { it.capabilityKey == messageCapabilities }.all {
            it.sharedScenarios == listOf(CrossLanguageBindingScenario.VALUE_CONVERSION)
        })
        assertEquals(311, 294 + claims.size)
        assertEquals(233, 250 - claims.size)
        assertEquals(556, 311 + 12 + 233)
        assertEquals(47, 52 - 5)
        val currentSymbols = currentPublicSymbols()
        assertEquals(284, currentSymbols.size)
        assertTrue(familySymbols.all { it in currentSymbols })
        assertEquals(73, symbolExports(currentSymbols).first.size)
        assertEquals(46, symbolExports(currentSymbols).second.size)

        val canonicalDrift = listOf(
            capabilityId.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            agentProperty("OtherCapability", "id", "kotlin/String!!"),
            capabilityId.replace("AgentCapability.id", "AgentCapability.otherId"),
            agentProperty("AgentCapability", "id", "kotlin/String!!", propertyKind = "VAR"),
            agentProperty("AgentCapability", "id", "kotlin/Int!!"),
            agentProperty("AgentCapability", "id", "kotlin/String?"),
            agentProperty("AgentCapability", "icon", "kotlin/String!!"),
            "$capabilityId|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$capabilityId|suspend=true",
            canonicalFunction("AgentCapability", "id", returnType = "kotlin/String!!")
                .replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            invocationName.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            agentProperty("OtherInvocation", "name", "kotlin/String!!"),
            agentProperty("AgentInvocation", "name", "kotlin/String?"),
            pluginConstructor.replace("default=false", "default=true"),
            pluginConstructor.replace(
                "return=$CANONICAL_AGENT_PACKAGE/AgentInvocation.Plugin",
                "return=$CANONICAL_AGENT_PACKAGE/AgentInvocation.Skill",
            ),
            pluginConstructor.replace("kotlin/String!!:default=false", "kotlin/Int!!:default=false"),
            skillConstructor.replace("suspend=false", "suspend=true"),
            pluginUri.replace("AgentInvocation.Plugin.uri", "AgentInvocation.Plugin.otherUri"),
            skillPath.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            messageCapabilities.replace("kotlin.collections/Set", "kotlin.collections/List"),
            messageCollaborationMode.replace("AgentCollaborationMode!!", "AgentCollaborationMode?"),
            messageInvocations.replace("AgentInvocation!!", "AgentInvocation?"),
        )
        canonicalDrift.forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = familySymbols)
            assertEquals(listOf(drifted), drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        val publicDrift = listOf(
            capabilityId to AGENT_CAPABILITY_ID.replace("agentCapabilityId", "futureCapabilityId"),
            capabilityId to AGENT_CAPABILITY_ID.replace("capability:", "value:"),
            capabilityId to AGENT_CAPABILITY_ID.replace("AgentCapability", "string"),
            capabilityId to AGENT_CAPABILITY_ID.replace("capability:", "capability?:"),
            capabilityId to AGENT_CAPABILITY_ID.replace("capability:", "...capability:"),
            capabilityId to AGENT_CAPABILITY_ID.replace("): string", "): number"),
            capabilityIcon to AGENT_CAPABILITY_ICON.replace(" | null | undefined", ""),
            invocationKey to AGENT_INVOCATION_TYPE.replace("AgentSkillInvocation", "FutureSkillInvocation"),
            pluginConstructor to pluginConstructorSymbol.replace("uri: string", "uri?: string"),
            pluginConstructor to "$pluginConstructorSymbol: AgentPluginInvocation",
            skillConstructor to skillConstructorSymbol.replace("path: string", "path: number"),
            pluginUri to "getter:AgentPluginInvocation#uri:number",
            skillPath to "property:AgentSkillInvocation#path:string",
            messageCapabilities to "getter:CodexMessage#capabilities:ReadonlySet<AgentCapability>",
            messageCapabilities to "getter:CodexMessage#capabilities:Array<AgentCapability>",
            messageCollaborationMode to "getter:CodexMessage#collaborationMode:string",
            messageInvocations to "getter:CodexMessage#invocations:Array<AgentInvocation>",
            messageInvocations to "getter:CodexMessage#invocations:ReadonlyArray<AgentSkillInvocation>",
        )
        publicDrift.forEach { (key, drifted) ->
            val exact = when (key) {
                capabilityId -> AGENT_CAPABILITY_ID
                capabilityIcon -> AGENT_CAPABILITY_ICON
                invocationKey -> AGENT_INVOCATION_TYPE
                pluginConstructor -> pluginConstructorSymbol
                skillConstructor -> skillConstructorSymbol
                pluginUri -> "getter:AgentPluginInvocation#uri:string"
                skillPath -> "getter:AgentSkillInvocation#path:string"
                messageCapabilities -> "getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>"
                messageCollaborationMode -> "getter:CodexMessage#collaborationMode:AgentCollaborationMode"
                messageInvocations -> "getter:CodexMessage#invocations:ReadonlyArray<AgentInvocation>"
                else -> error("Unknown drift key: $key")
            }
            val driftSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftSymbols, references = driftSymbols)
            assertTrue(key in drift.missingCapabilityKeys, "Accepted public drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(
            AGENT_CAPABILITY_ID,
            AGENT_INVOCATION_TYPE,
            pluginConstructorSymbol,
            skillConstructorSymbol,
            "getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>",
            "getter:CodexMessage#collaborationMode:AgentCollaborationMode",
            "getter:CodexMessage#invocations:ReadonlyArray<AgentInvocation>",
        ).forEach { removed ->
            val partial = derive(
                keys,
                symbols - removed,
                references = familySymbols - removed,
            )
            assertTrue(partial.missingCapabilityKeys.isNotEmpty(), "Accepted partial inventory without $removed")
        }

        listOf(
            AGENT_CAPABILITY_ID to capabilityId,
            AGENT_INVOCATION_TYPE to invocationKey,
            "getter:AgentPluginInvocation#name:string" to invocationName,
            pluginConstructorSymbol to pluginConstructor,
            skillConstructorSymbol to skillConstructor,
            "getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>" to messageCapabilities,
        ).forEach { (symbol, key) ->
            val unreferenced = derive(keys, symbols, references = familySymbols - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey == key })
        }

        val future = agentProperty("AgentInvocation.Skill", "future", "kotlin/String!!")
        val futureEvidence = derive(keys + future, symbols, references = familySymbols)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(17, futureEvidence.projectionClaims.size)

        val aliasOnly = derive(
            keys,
            listOf(AGENT_CAPABILITY_ALIAS, AGENT_INVOCATION_TYPE),
            references = listOf(AGENT_CAPABILITY_ALIAS, AGENT_INVOCATION_TYPE),
        )
        assertEquals(keys, aliasOnly.missingCapabilityKeys)
        assertTrue(aliasOnly.projectionClaims.isEmpty())

        val unauthorized = agentProperty("AgentPluginInvocation", "name", "kotlin/String!!")
        val unauthorizedEvidence = derive(keys + unauthorized, symbols, references = familySymbols)
        assertTrue(unauthorizedEvidence.errors.any {
            "Reused JavaScript/TypeScript public symbol getter:AgentPluginInvocation#name:string" in it
        })
        assertTrue(unauthorizedEvidence.projectionClaims.none { it.capabilityKey == unauthorized })
    }

    @Test
    fun `host state variants flatten eight exact discriminated values onto the existing lifecycle surface`() {
        val lifecycle = d044HostLifecycleKey()
        val keys = d044HostStateKeys()
        val references = d044HostStateReferences()
        val symbols = (references + listOf("class:CodexHost", "class:CodexHostState")).sorted()
        val evidence = derive((keys + lifecycle).sorted(), symbols, references = references)
        val claims = evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols }
        val hostStateClaims = claims.filterKeys(keys::contains)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(9, claims.size)
        assertEquals(8, hostStateClaims.size)
        assertEquals(10, symbols.size)
        assertEquals(8, references.size)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        assertEquals(listOf(HOST_STATE_GETTER, HOST_STATE_OBSERVER).sorted(), claims.getValue(lifecycle))

        keys.forEach { key ->
            val leaves = when {
                "CodexHostState.Ready" in key -> setOf(HOST_STATE_AGENT)
                "CodexHostState.Failed" in key && ".failure|" in key -> setOf(HOST_STATE_FAILURE)
                "CodexHostState.WorkspaceRequired" in key ->
                    setOf(HOST_STATE_SELECTION_MESSAGE, HOST_STATE_SELECTION_REASON)
                "CodexWorkspaceResolution.SelectionRequired" in key && ".reason|" in key ->
                    setOf(HOST_STATE_SELECTION_REASON)
                "CodexWorkspaceResolution.SelectionRequired" in key && ".message|" in key ->
                    setOf(HOST_STATE_SELECTION_MESSAGE)
                else -> setOf(HOST_STATE_WORKSPACE)
            }
            assertEquals(
                (setOf(HOST_STATE_GETTER, HOST_STATE_OBSERVER, HOST_STATE_STATUS) + leaves).sorted(),
                hostStateClaims.getValue(key),
            )
        }
        assertTrue(hostStateClaims.values.all { claim ->
            HOST_STATE_GETTER in claim && HOST_STATE_OBSERVER in claim && HOST_STATE_STATUS in claim
        })
        assertTrue(evidence.projectionClaims.filter { it.capabilityKey in keys }.all {
            it.sharedScenarios.toSet() == setOf(
                CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
                CrossLanguageBindingScenario.VALUE_CONVERSION,
            )
        })
        assertEquals(
            setOf(
                CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
            ),
            evidence.projectionClaims.single { it.capabilityKey == lifecycle }.sharedScenarios.toSet(),
        )
        assertEquals(319, 311 + hostStateClaims.size)
        assertEquals(225, 233 - hostStateClaims.size)
        assertEquals(556, 319 + 12 + 225)
        assertEquals(41, 47 - 6)
        assertEquals(284, currentPublicSymbols().size)
        assertTrue(symbols.all { it in currentPublicSymbols() })
        assertEquals(5, references.count { it.startsWith("getter:CodexHostState#") && it != HOST_STATE_STATUS })
    }

    @Test
    fun `host state flattening rejects canonical public reference cardinality and reuse drift`() {
        val lifecycle = d044HostLifecycleKey()
        val keys = d044HostStateKeys()
        val references = d044HostStateReferences()
        val symbols = (references + listOf("class:CodexHost", "class:CodexHostState")).sorted()
        val preparing = keys.single { "CodexHostState.Preparing" in it }

        listOf(
            preparing.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            preparing.replace("CodexHostState.Preparing", "CodexHostState.Ready"),
            canonicalProperty(
                "CodexHostState.Preparing",
                "future",
                "$CANONICAL_AGENT_PACKAGE/CodexWorkspace!!",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            canonicalFunction(
                "CodexHostState.Preparing",
                "workspace",
                returnType = "$CANONICAL_AGENT_PACKAGE/CodexWorkspace!!",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            canonicalProperty(
                "CodexHostState.Preparing",
                "workspace",
                "$CANONICAL_AGENT_PACKAGE/CodexWorkspace!!",
                propertyKind = "VAR",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            preparing.replace("CodexWorkspace!!", "CodexWorkspace?"),
            "$preparing|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$preparing|suspend=true",
            preparing.replace(".workspace|{}workspace", ".otherWorkspace|{}workspace"),
        ).forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = references)
            assertEquals(listOf(drifted), drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        listOf(
            HOST_STATE_GETTER to HOST_STATE_GETTER.replace("CodexHostState", "string"),
            HOST_STATE_OBSERVER to HOST_STATE_OBSERVER.replace("state: CodexHostState", "state: string"),
            HOST_STATE_STATUS to HOST_STATE_STATUS.replace("CodexHostStatus", "string"),
            HOST_STATE_WORKSPACE to HOST_STATE_WORKSPACE.replace(" | null | undefined", ""),
            HOST_STATE_AGENT to HOST_STATE_AGENT.replace(" | null | undefined", ""),
            HOST_STATE_FAILURE to HOST_STATE_FAILURE.replace(" | null | undefined", ""),
            HOST_STATE_SELECTION_REASON to HOST_STATE_SELECTION_REASON.replace(" | null | undefined", ""),
            HOST_STATE_SELECTION_MESSAGE to HOST_STATE_SELECTION_MESSAGE.replace(" | null | undefined", ""),
        ).forEach { (exact, drifted) ->
            val driftSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive((keys + lifecycle).sorted(), driftSymbols, references = driftReferences)
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys }, "Accepted public drift: $drifted")
            assertTrue(drift.missingCapabilityKeys.isNotEmpty() || drift.errors.isNotEmpty())
        }

        listOf(
            "property:CodexHostState#status[readonly]:CodexHostStatus",
            "property:CodexHostState#workspace[readonly]:CodexWorkspace | null | undefined",
            "method:CodexHost#observeState:(listener: (state: CodexHostState) => string): CodexObservation",
        ).forEach { extra ->
            val ambiguous = derive(
                (keys + lifecycle).sorted(),
                (symbols + extra).sorted(),
                references = (references + extra).sorted(),
            )
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey in keys }, "Accepted extra shape: $extra")
            assertTrue(ambiguous.missingCapabilityKeys.isNotEmpty() || ambiguous.errors.isNotEmpty())
        }

        symbols.filter { it.startsWith("getter:CodexHostState#") && it != HOST_STATE_STATUS }.forEach { leaf ->
            val partial = derive(
                (keys + lifecycle).sorted(),
                symbols - leaf,
                references = references - leaf,
            )
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys }, "Accepted partial surface without $leaf")
        }

        references.forEach { symbol ->
            val unreferenced = derive(
                (keys + lifecycle).sorted(),
                symbols,
                references = references - symbol,
            )
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && symbol in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey in keys })
        }

        val partialCanonical = derive(
            (keys.dropLast(1) + lifecycle).sorted(),
            symbols,
            references = references,
        )
        assertTrue(partialCanonical.errors.any { "Reused JavaScript/TypeScript public symbol" in it })
        assertTrue(partialCanonical.projectionClaims.none { it.capabilityKey in keys })

        listOf(
            canonicalProperty(
                "CodexHostState",
                "workspace",
                "$CANONICAL_AGENT_PACKAGE/CodexWorkspace?",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            canonicalProperty(
                "CodexHostState",
                "status",
                "$CANONICAL_AGENT_PACKAGE/CodexHostStatus!!",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
        ).forEach { arbitrary ->
            val unauthorized = derive(
                (keys + lifecycle + arbitrary).sorted(),
                symbols,
                references = references,
            )
            assertTrue(unauthorized.errors.any { "Reused JavaScript/TypeScript public symbol" in it && arbitrary in it })
            assertTrue(unauthorized.projectionClaims.none { it.capabilityKey == arbitrary })
        }

        val future = canonicalProperty(
            "CodexWorkspaceResolution.SelectionRequired",
            "future",
            "kotlin/String!!",
        ).replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive((keys + lifecycle + future).sorted(), symbols, references = references)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(keys.toSet(), futureEvidence.projectionClaims.mapTo(mutableSetOf()) { it.capabilityKey }
            .intersect(keys.toSet()))
    }

    @Test
    fun `conversation history completes five exact claims through the flattened controller`() {
        val keys = d045ConversationKeys()
        val aggregateKeys = d045ConversationAggregateKeys()
        val symbols = d045ConversationSymbols()
        val evidence = derive(aggregateKeys, symbols, references = symbols)
        val claims = evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols }
        val historyClaims = claims.filterKeys(keys::contains)
        val constructor = keys.single { "AgentConversation.<init>" in it }
        val messages = keys.single { "AgentConversation.messages" in it }
        val summary = keys.single { "AgentConversation.summary" in it }
        val read = keys.single { "CodexConversations.read" in it }
        val conversations = keys.single { "CodexAgent.conversations" in it }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(15, claims.size)
        assertEquals(5, historyClaims.size)
        assertEquals(listOf(AGENT_CONVERSATION_CONSTRUCTOR), claims.getValue(constructor))
        assertEquals(listOf(AGENT_CONVERSATION_MESSAGES), claims.getValue(messages))
        assertEquals(listOf(AGENT_CONVERSATION_SUMMARY), claims.getValue(summary))
        assertEquals(listOf(READ_CONVERSATION), claims.getValue(read))
        assertEquals(d045ConversationEnvelope(), claims.getValue(conversations))
        assertEquals(
            listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            evidence.projectionClaims.single { it.capabilityKey == constructor }.sharedScenarios,
        )
        assertEquals(
            setOf(CrossLanguageBindingScenario.ASYNC_SUCCESS, CrossLanguageBindingScenario.ASYNC_FAILURE),
            evidence.projectionClaims.single { it.capabilityKey == read }.sharedScenarios.toSet(),
        )
        assertEquals(
            listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP),
            evidence.projectionClaims.single { it.capabilityKey == conversations }.sharedScenarios,
        )
        assertEquals(324, 319 + historyClaims.size)
        assertEquals(220, 225 - historyClaims.size)
        assertEquals(556, 324 + 12 + 220)
        assertEquals(39, 41 - 2)
        assertEquals(284, currentPublicSymbols().size)
        assertTrue(symbols.all { it in currentPublicSymbols() })
        assertEquals(5, d045PublicSymbols().size)
    }

    @Test
    fun `conversation history rejects canonical public reference inventory and reuse drift`() {
        val keys = d045ConversationKeys()
        val aggregateKeys = d045ConversationAggregateKeys()
        val symbols = d045ConversationSymbols()
        val parent = keys.single { "CodexAgent.conversations" in it }
        val read = keys.single { "CodexConversations.read" in it }
        val constructor = keys.single { "AgentConversation.<init>" in it }
        val messages = keys.single { "AgentConversation.messages" in it }

        listOf(
            parent.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            parent.replace("CodexAgent.conversations", "OtherAgent.conversations"),
            parent.replace(".conversations|{}conversations", ".future|{}conversations"),
            parent.replace("propertyKind=VAL", "propertyKind=VAR"),
            parent.replace("CodexConversations!!", "CodexConversations?"),
            "$parent|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$parent|suspend=true",
            read.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            read.replace("CodexConversations.read", "OtherConversations.read"),
            read.replace(".read|read(", ".future|future("),
            read.replace("AgentConversation!!", "AgentConversation?"),
            read.replaceFirst("default=false", "default=true"),
            read.replaceFirst("vararg=false", "vararg=true"),
            read.replace("suspend=true", "suspend=false"),
            constructor.replace("AgentConversationSummary!!", "AgentConversationSummary?"),
            messages.replace("propertyKind=VAL", "propertyKind=VAR"),
        ).forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = symbols)
            assertEquals(listOf(drifted), drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        listOf(
            Triple(
                READ_CONVERSATION,
                READ_CONVERSATION.replace("readConversation", "read"),
                setOf(parent, read),
            ),
            Triple(
                READ_CONVERSATION,
                READ_CONVERSATION.replace("conversationId: string", "id: string"),
                setOf(parent, read),
            ),
            Triple(
                READ_CONVERSATION,
                READ_CONVERSATION.replace("conversationId: string", "conversationId?: string"),
                setOf(parent, read),
            ),
            Triple(
                READ_CONVERSATION,
                READ_CONVERSATION.replace("Promise<AgentConversation>", "Promise<void>"),
                setOf(parent, read),
            ),
            Triple(
                AGENT_CONVERSATION_CONSTRUCTOR,
                AGENT_CONVERSATION_CONSTRUCTOR.replace(
                    "ReadonlyArray<CodexMessage>",
                    "Array<CodexMessage>",
                ),
                setOf(constructor),
            ),
            Triple(
                AGENT_CONVERSATION_MESSAGES,
                AGENT_CONVERSATION_MESSAGES.replace(
                    "ReadonlyArray<CodexMessage>",
                    "ReadonlyArray<string>",
                ),
                setOf(messages),
            ),
        ).forEach { (exact, drifted, rejectedKeys) ->
            val driftSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftReferences = symbols.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(aggregateKeys, driftSymbols, references = driftReferences)
            assertTrue(drift.missingCapabilityKeys.isNotEmpty() || drift.errors.isNotEmpty())
            assertTrue(drift.projectionClaims.none { it.capabilityKey in rejectedKeys })
        }

        listOf(
            "property:CodexAgent#activeConversation[readonly]:CodexConversation | null | undefined",
            "method:CodexAgent#readConversation:(conversationId: string): Promise<AgentConversation>",
        ).forEach { extra ->
            val ambiguous = derive(
                aggregateKeys,
                (symbols + extra).sorted(),
                references = (symbols + extra).sorted(),
            )
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey in setOf(parent, read) })
            assertTrue(ambiguous.missingCapabilityKeys.isNotEmpty() || ambiguous.errors.isNotEmpty())
        }

        d045ConversationEnvelope().forEach { omitted ->
            val partial = derive(
                aggregateKeys,
                symbols - omitted,
                references = symbols - omitted,
            )
            assertTrue(partial.projectionClaims.none { it.capabilityKey == parent }, "Accepted without $omitted")
        }

        val claimReferences = d045ConversationEnvelope() + AGENT_CONVERSATION_CONSTRUCTOR
        claimReferences.forEach { symbol ->
            val unreferenced = derive(
                aggregateKeys,
                symbols,
                references = symbols - symbol,
            )
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && symbol in it })
            assertTrue(unreferenced.projectionClaims.none { symbol in it.publicSymbols })
        }

        val controllerAggregate = aggregateKeys.filterNot {
            "AgentConversation.<init>" in it || "AgentConversation.messages" in it ||
                "AgentConversation.summary" in it
        }
        controllerAggregate.forEach { omitted ->
            val partial = derive(aggregateKeys - omitted, symbols, references = symbols)
            assertTrue(partial.errors.any {
                "Reused JavaScript/TypeScript public symbol" in it ||
                    "conversation controller flattening" in it
            })
            assertTrue(partial.projectionClaims.none { it.capabilityKey == parent })
        }

        val future = canonicalProperty("CodexConversations", "future", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive(aggregateKeys + future, symbols, references = symbols)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(keys.toSet(), futureEvidence.projectionClaims.mapTo(mutableSetOf()) { it.capabilityKey }
            .intersect(keys.toSet()))

        val foreignId = aggregateKeys.single { "ConversationId.value" in it }
            .replace(CANONICAL_AGENT_PACKAGE, "foreign")
        val unauthorized = derive(aggregateKeys + foreignId, symbols, references = symbols)
        assertTrue(unauthorized.errors.any { "Reused JavaScript/TypeScript public symbol" in it })
        assertTrue(unauthorized.projectionClaims.none {
            it.capabilityKey in setOf(parent, read, foreignId)
        })
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
    fun `api key value flattens only into the exact referenced authentication overload`() {
        val apiKeyConstructor = canonicalConstructor(
            "CodexAuthenticationMethod.ApiKey",
            listOf("kotlin/String!!"),
        )
        val apiKeyValue =
            canonicalProperty("CodexAuthenticationMethod.ApiKey", "value", "kotlin/String!!")
        val authenticate = canonicalFunction(
            "CodexAuthentication",
            "authenticate",
            suspendFunction = true,
            parameters = listOf("example/CodexAuthenticationMethod!!"),
            defaultParameterIndices = setOf(0),
        )
        val keys = listOf(apiKeyConstructor, apiKeyValue, authenticate).sorted()
        val symbols = (listOf("class:CodexAuthentication") + AUTHENTICATION_OVERLOADS).sorted()
        val apiKeyOverload = AUTHENTICATION_OVERLOADS.single { "\"api_key\"" in it }

        val evidence = derive(keys, symbols, references = AUTHENTICATION_OVERLOADS)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty())
        assertEquals(3, evidence.projectionClaims.size)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        assertEquals(listOf(apiKeyOverload), claims.getValue(apiKeyConstructor).publicSymbols)
        assertEquals(listOf(apiKeyOverload), claims.getValue(apiKeyValue).publicSymbols)
        assertEquals(AUTHENTICATION_OVERLOADS.sorted(), claims.getValue(authenticate).publicSymbols)

        listOf(
            canonicalConstructor("OtherAuthenticationMethod.ApiKey", listOf("kotlin/String!!")),
            canonicalFunction(
                "CodexAuthenticationMethod.ApiKey",
                "create",
                returnType = "example/CodexAuthenticationMethod.ApiKey",
                parameters = listOf("kotlin/String!!"),
            ),
            canonicalConstructor(
                "CodexAuthenticationMethod.ApiKey",
                listOf("kotlin/String!!"),
                defaultParameterIndices = setOf(0),
            ),
            canonicalConstructor("CodexAuthenticationMethod.ApiKey", listOf("kotlin/Int!!")),
            canonicalConstructor(
                "CodexAuthenticationMethod.ApiKey",
                listOf("kotlin/String!!", "kotlin/String!!"),
            ),
            apiKeyConstructor.replace(
                "return=example/CodexAuthenticationMethod.ApiKey",
                "return=example/Wrong",
            ),
            apiKeyConstructor.replace(
                "abi=example/CodexAuthenticationMethod.ApiKey.<init>",
                "abi=example/Wrong.<init>",
            ),
            canonicalProperty("CodexAuthenticationMethod.ApiKey", "value", "kotlin/Int!!"),
            canonicalProperty(
                "CodexAuthenticationMethod.ApiKey",
                "value",
                "kotlin/String!!",
                propertyKind = "VAR",
            ),
        ).forEach { malformed ->
            val rejected = derive(listOf(malformed), symbols, references = AUTHENTICATION_OVERLOADS)
            assertEquals(listOf(malformed), rejected.missingCapabilityKeys, "Accepted malformed key: $malformed")
            assertTrue(rejected.projectionClaims.isEmpty())
        }

        listOf(
            AUTHENTICATION_OVERLOADS.map { symbol ->
                if (symbol == apiKeyOverload) symbol.replace("apiKey: string", "apiKey?: string") else symbol
            },
            AUTHENTICATION_OVERLOADS +
                "method:CodexAuthentication#authenticate:(method: string): Promise<void>",
        ).forEach { overloads ->
            val rejected = derive(keys, (listOf("class:CodexAuthentication") + overloads).sorted())
            assertEquals(keys, rejected.missingCapabilityKeys)
            assertTrue(rejected.projectionClaims.isEmpty())
        }

        val unreferenced = derive(
            keys,
            symbols,
            references = AUTHENTICATION_OVERLOADS.filterNot { it == apiKeyOverload },
        )
        assertEquals(3, unreferenced.errors.count { "Unreferenced exceptional" in it })
        assertTrue(unreferenced.projectionClaims.isEmpty())

        val foreignConstructor = apiKeyConstructor.replace("example/", "foreign/")
        val foreignValue = apiKeyValue.replace("example/", "foreign/")
        val crossPackage = derive(
            keys + foreignConstructor + foreignValue,
            symbols,
            references = AUTHENTICATION_OVERLOADS,
        )
        assertTrue(crossPackage.errors.any { "Reused" in it })
        assertTrue(crossPackage.projectionClaims.none {
            it.capabilityKey in setOf(apiKeyConstructor, apiKeyValue, authenticate, foreignConstructor, foreignValue)
        })
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
    fun `conversation listing projects one immutable bigint summary family and rejects drift`() {
        val constructor = canonicalConstructor(
            "AgentConversationSummary",
            listOf("example/ConversationId!!", "kotlin/String!!", "kotlin/Long!!"),
        )
        val conversationId = canonicalProperty(
            "AgentConversationSummary",
            "conversationId",
            "example/ConversationId!!",
        )
        val title = canonicalProperty("AgentConversationSummary", "title", "kotlin/String!!")
        val updatedAt = canonicalProperty(
            "AgentConversationSummary",
            "updatedAtEpochSeconds",
            "kotlin/Long!!",
        )
        val list = canonicalFunction(
            "CodexConversations",
            "list",
            returnType =
                "kotlin.collections/List<INVARIANT:example/AgentConversationSummary!!>!!",
            suspendFunction = true,
        )
        val keys = listOf(constructor, conversationId, title, updatedAt, list).sorted()
        val constructorSymbol =
            "constructor:AgentConversationSummary#" +
                "(conversationId: string, title: string, updatedAtEpochSeconds: bigint)"
        val conversationIdSymbol = "getter:AgentConversationSummary#conversationId:string"
        val titleSymbol = "getter:AgentConversationSummary#title:string"
        val updatedAtSymbol = "getter:AgentConversationSummary#updatedAtEpochSeconds:bigint"
        val listSymbol =
            "method:CodexAgent#listConversations:" +
                "(signal?: AbortSignal | null | undefined): " +
                "Promise<ReadonlyArray<AgentConversationSummary>>"
        val familySymbols = listOf(
            "class:AgentConversationSummary",
            constructorSymbol,
            conversationIdSymbol,
            titleSymbol,
            updatedAtSymbol,
            listSymbol,
        ).sorted()
        val references = familySymbols
        val symbols = (familySymbols + "class:CodexAgent").sorted()
        val evidence = derive(keys, symbols, references = references)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(5, evidence.projectionClaims.size)
        assertEquals(6, familySymbols.size)
        assertEquals(6, references.size)
        assertEquals(
            mapOf(
                constructor to listOf(constructorSymbol),
                conversationId to listOf(conversationIdSymbol),
                title to listOf(titleSymbol),
                updatedAt to listOf(updatedAtSymbol),
                list to listOf(listSymbol),
            ),
            evidence.projectionClaims.associate { it.capabilityKey to it.publicSymbols },
        )
        assertEquals(
            setOf(CrossLanguageBindingScenario.ASYNC_SUCCESS, CrossLanguageBindingScenario.ASYNC_FAILURE),
            evidence.projectionClaims.single { it.capabilityKey == list }.sharedScenarios.toSet(),
        )

        listOf(
            constructor to constructorSymbol.replace("bigint", "number"),
            conversationId to conversationIdSymbol.replace(":string", ":number"),
            title to titleSymbol.replace(":string", ":number"),
            updatedAt to updatedAtSymbol.replace(":bigint", ":number"),
            list to listSymbol.replace("AbortSignal | null | undefined", "string"),
            list to listSymbol.replace("ReadonlyArray", "Array"),
            list to listSymbol.replace("Promise<", "ReadonlyArray<"),
        ).forEach { (key, drifted) ->
            val exact = when (key) {
                constructor -> constructorSymbol
                conversationId -> conversationIdSymbol
                title -> titleSymbol
                updatedAt -> updatedAtSymbol
                else -> listSymbol
            }
            val driftedSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val driftedReferences = references.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(keys, driftedSymbols, references = driftedReferences)
            assertTrue(key in drift.missingCapabilityKeys, "Accepted drift: $drifted")
            assertTrue(drift.projectionClaims.none { it.capabilityKey == key })
        }

        listOf(constructorSymbol to constructor, listSymbol to list).forEach { (symbol, key) ->
            val unreferenced = derive(keys, symbols, references = references - symbol)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && key in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey == key })
        }

        val signalFreeOverload =
            "method:CodexAgent#listConversations:" +
                "(): Promise<ReadonlyArray<AgentConversationSummary>>"
        val ambiguous = derive(
            keys,
            (symbols + signalFreeOverload).sorted(),
            references = (references + signalFreeOverload).sorted(),
        )
        assertTrue(ambiguous.errors.any { "Ambiguous" in it && list in it })
        assertTrue(ambiguous.projectionClaims.none { it.capabilityKey == list })

        listOf(
            canonicalFunction(
                "CodexConversations",
                "list",
                returnType = "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                suspendFunction = true,
            ),
            canonicalFunction(
                "OtherConversations",
                "list",
                returnType =
                    "kotlin.collections/List<INVARIANT:example/AgentConversationSummary!!>!!",
                suspendFunction = true,
            ),
        ).forEach { wrongCanonical ->
            assertEquals(
                listOf(wrongCanonical),
                derive(listOf(wrongCanonical), symbols, references = references).missingCapabilityKeys,
            )
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
        ).replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val settingsApproval = canonicalProperty(
            "AgentConversationSettings",
            "approvalPreset",
            "example/AgentApprovalPreset!!",
        ).replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val settingsServiceTier =
            canonicalProperty("AgentConversationSettings", "serviceTier", "kotlin/String?")
                .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val conversationIdConstructor = canonicalConstructor("ConversationId", listOf("kotlin/String!!"))
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val conversationIdValue = canonicalProperty("ConversationId", "value", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val pathConstructor =
            canonicalConstructor("CodexPathWorkspaceSelection", listOf("kotlin/String!!"))
                .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val pathValue = canonicalProperty("CodexPathWorkspaceSelection", "path", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val flattened = listOf(
            settingsConstructor,
            settingsApproval,
            settingsServiceTier,
            conversationIdConstructor,
            conversationIdValue,
            pathConstructor,
            pathValue,
        ).sorted()
        val controller = d045ConversationAggregateKeys().filterNot {
            it in flattened || "AgentConversation." in it
        }
        val ordinary = controller + listOf(
            canonicalProperty("AgentConversationState", "conversationId", "example/ConversationId?"),
            canonicalFunction(
                "CodexHost",
                "selectWorkspace",
                suspendFunction = true,
                parameters = listOf("example/CodexWorkspaceSelection!!"),
            ),
        ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }
        val symbols = (d045ConversationSymbols() + listOf(
            "class:CodexConversationState",
            "class:CodexHost",
            CONVERSATION_ID_GETTER,
            SELECT_WORKSPACE,
        )).distinct().sorted()
        val evidence = derive(flattened + ordinary, symbols, references = symbols)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(16, evidence.projectionClaims.size)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        listOf(settingsConstructor, settingsApproval, settingsServiceTier).forEach { key ->
            assertEquals(listOf(OPEN_CONVERSATION), claims.getValue(key).publicSymbols)
        }
        listOf(conversationIdConstructor, conversationIdValue).forEach { key ->
            assertEquals(
                listOf(
                    DELETE_CONVERSATION,
                    OPEN_CONVERSATION,
                    READ_CONVERSATION,
                    RENAME_CONVERSATION,
                ).sorted(),
                claims.getValue(key).publicSymbols,
            )
        }
        listOf(pathConstructor, pathValue).forEach { key ->
            assertEquals(listOf(SELECT_WORKSPACE), claims.getValue(key).publicSymbols)
        }

        listOf(
            settingsConstructor.replace("default=true", "default=false"),
            settingsApproval.replace(
                "$CANONICAL_AGENT_PACKAGE/AgentApprovalPreset!!",
                "kotlin/String!!",
            ),
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
                READ_CONVERSATION,
                RENAME_CONVERSATION,
            ).sorted(),
            pathValue to listOf("class:CodexHost", SELECT_WORKSPACE).sorted(),
        ).forEach { (key, projectedSymbols) ->
            val foreign = key.replace(CANONICAL_AGENT_PACKAGE, "foreign")
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
    fun `client info flattens only into the exact referenced host factory`() {
        val hostConstructor = canonicalConstructor(
            "CodexHost",
            listOf("example/CodexPlatform!!", "example/CodexClientInfo!!"),
        )
        val clientConstructor = canonicalConstructor(
            "CodexClientInfo",
            listOf("kotlin/String!!", "kotlin/String!!", "kotlin/String!!"),
        )
        val clientName = canonicalProperty("CodexClientInfo", "name", "kotlin/String!!")
        val clientTitle = canonicalProperty("CodexClientInfo", "title", "kotlin/String!!")
        val clientVersion = canonicalProperty("CodexClientInfo", "version", "kotlin/String!!")
        val clientKeys = listOf(clientConstructor, clientName, clientTitle, clientVersion).sorted()
        val keys = (clientKeys + hostConstructor).sorted()
        val symbols = listOf("class:CodexHost", CREATE_CODEX_HOST).sorted()
        val references = listOf(CREATE_CODEX_HOST)
        val evidence = derive(keys, symbols, references = references)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(5, claims.size)
        assertEquals(
            listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP),
            claims.getValue(hostConstructor).sharedScenarios,
        )
        clientKeys.forEach { key ->
            assertEquals(listOf(CREATE_CODEX_HOST), claims.getValue(key).publicSymbols)
            assertEquals(
                listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
                claims.getValue(key).sharedScenarios,
            )
        }
        val clientProjectionSymbols = clientKeys.flatMap { claims.getValue(it).publicSymbols }.toSet()
        assertEquals(setOf(CREATE_CODEX_HOST), clientProjectionSymbols)
        assertEquals(269, 265 + clientKeys.size)
        assertEquals(275, 279 - clientKeys.size)
        assertEquals(556, 269 + 12 + 275)
        assertEquals(57, 58 - 1)
        assertEquals(
            284,
            currentPublicSymbols().size + (clientProjectionSymbols - currentPublicSymbols().toSet()).size,
        )
        assertEquals(references, evidence.packedApi.referencedSymbols)

        val canonicalDrift = listOf(
            clientConstructor to canonicalConstructor(
                "OtherClientInfo",
                listOf("kotlin/String!!", "kotlin/String!!", "kotlin/String!!"),
            ),
            clientConstructor to canonicalConstructor(
                "CodexClientInfo",
                listOf("kotlin/String?", "kotlin/String!!", "kotlin/String!!"),
            ),
            clientConstructor to canonicalConstructor(
                "CodexClientInfo",
                listOf("kotlin/String!!", "kotlin/String!!"),
            ),
            clientConstructor to canonicalConstructor(
                "CodexClientInfo",
                listOf("kotlin/String!!", "kotlin/String!!", "kotlin/String!!", "kotlin/String!!"),
            ),
            clientConstructor to clientConstructor.replaceFirst("default=false", "default=true"),
            clientConstructor to clientConstructor.replaceFirst("vararg=false", "vararg=true"),
            clientConstructor to clientConstructor.replace("suspend=false", "suspend=true"),
            clientConstructor to clientConstructor.replace(
                "return=example/CodexClientInfo",
                "return=example/OtherClientInfo",
            ),
            clientName to canonicalProperty("OtherClientInfo", "name", "kotlin/String!!"),
            clientName to canonicalFunction("CodexClientInfo", "name", returnType = "kotlin/String!!"),
            clientName to canonicalProperty("CodexClientInfo", "futureName", "kotlin/String!!"),
            clientName to canonicalProperty("CodexClientInfo", "name", "kotlin/Int!!"),
            clientName to canonicalProperty("CodexClientInfo", "name", "kotlin/String!!", propertyKind = "VAR"),
            clientName to "$clientName|suspend=true",
            clientName to "$clientName|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            clientTitle to canonicalProperty("CodexClientInfo", "title", "kotlin/String?"),
            clientVersion to canonicalProperty("CodexClientInfo", "version", "kotlin/Int!!"),
        )
        canonicalDrift.forEach { (exact, drifted) ->
            val driftedKeys = keys.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(driftedKeys, symbols, references = references)
            assertTrue(drift.projectionClaims.isEmpty(), "Accepted canonical drift: $drifted")
            assertTrue(
                drifted in drift.missingCapabilityKeys || drift.errors.any { "Reused" in it },
                "Did not reject canonical drift: $drifted",
            )
        }
        listOf(clientConstructor, clientName).forEach { exact ->
            val malformedAbi = exact.replace(
                "abi=example/CodexClientInfo.",
                "abi=example/OtherClientInfo.",
            )
            val malformed = derive(
                keys.map { if (it == exact) malformedAbi else it }.sorted(),
                symbols,
                references = references,
            )
            assertTrue(malformed.projectionClaims.isEmpty())
            assertTrue(malformedAbi in malformed.missingCapabilityKeys || malformed.errors.any { "Reused" in it })
        }

        listOf(
            CREATE_CODEX_HOST.replace("bundleDirectory", "bundle"),
            CREATE_CODEX_HOST.replace(
                "clientName: string, clientTitle: string",
                "clientTitle: string, clientName: string",
            ),
            CREATE_CODEX_HOST.replace("clientName: string", "clientName?: string"),
            CREATE_CODEX_HOST.replace("clientTitle: string", "...clientTitle: string"),
            CREATE_CODEX_HOST.replace("clientVersion: string", "clientVersion: number"),
            CREATE_CODEX_HOST.replace(", clientVersion: string", ""),
            CREATE_CODEX_HOST.replace("): CodexHost", ", future: string): CodexHost"),
            CREATE_CODEX_HOST.replace(": CodexHost", ": OtherHost"),
            CREATE_CODEX_HOST.replace("createCodexHost", "createFutureHost"),
        ).forEach { driftedFactory ->
            val drift = derive(
                keys,
                listOf("class:CodexHost", driftedFactory).sorted(),
                references = listOf(driftedFactory),
            )
            assertEquals(keys, drift.missingCapabilityKeys, "Accepted factory drift: $driftedFactory")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        keys.indices.forEach { omittedIndex ->
            val partial = derive(
                keys.filterIndexed { index, _ -> index != omittedIndex },
                symbols,
                references = references,
            )
            assertTrue(partial.errors.any { "Reused" in it }, "Accepted partial reuse without ${keys[omittedIndex]}")
            assertTrue(partial.projectionClaims.isEmpty())
        }

        val future = canonicalProperty("CodexClientInfo", "future", "kotlin/String!!")
        val futureEvidence = derive((keys + future).sorted(), symbols, references = references)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(keys, futureEvidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))

        val arbitrary = canonicalProperty("OtherValue", "name", "kotlin/String!!")
        val arbitraryEvidence = derive((keys + arbitrary).sorted(), symbols, references = references)
        assertEquals(listOf(arbitrary), arbitraryEvidence.missingCapabilityKeys)
        assertEquals(keys, arbitraryEvidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))

        val crossPackage = derive(
            (keys + clientKeys.map { it.replace("example/", "foreign/") }).sorted(),
            symbols,
            references = references,
        )
        assertTrue(crossPackage.errors.any { "Reused" in it })
        assertTrue(crossPackage.projectionClaims.isEmpty())

        val unreferenced = derive(keys, symbols, references = emptyList())
        assertEquals(5, unreferenced.errors.count { "Unreferenced exceptional" in it })
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
    fun `skill scope display name requires one exact referenced public function`() {
        fun agentProperty(
            owner: String,
            name: String,
            type: String,
            propertyKind: String = "VAL",
        ): String = canonicalProperty(owner, name, type, propertyKind)
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")

        val key = agentProperty("AgentSkillScope", "displayName", "kotlin/String!!")
        val evidence = derive(
            listOf(key),
            listOf(SKILL_SCOPE_DISPLAY_NAME),
            references = listOf(SKILL_SCOPE_DISPLAY_NAME),
        )

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty())
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(listOf(key), evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(listOf(SKILL_SCOPE_DISPLAY_NAME), evidence.projectionClaims.single().publicSymbols)
        assertEquals(
            listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            evidence.projectionClaims.single().sharedScenarios,
        )
        assertEquals(listOf(SKILL_SCOPE_DISPLAY_NAME), evidence.packedApi.referencedSymbols)

        assertEquals(270, 269 + evidence.projectionClaims.size)
        assertEquals(274, 275 - evidence.projectionClaims.size)
        assertEquals(556, 270 + 12 + 274)
        assertEquals(56, 57 - 1)
        val currentSymbols = currentPublicSymbols()
        assertEquals(
            listOf(SKILL_SCOPE_DISPLAY_NAME),
            currentSymbols.filter { it == SKILL_SCOPE_DISPLAY_NAME },
        )
        assertEquals(284, currentSymbols.size)

        val canonicalDrift = listOf(
            agentProperty("OtherSkillScope", "displayName", "kotlin/String!!"),
            key.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            agentProperty("AgentSkillScope", "futureDisplayName", "kotlin/String!!"),
            canonicalFunction(
                "AgentSkillScope",
                "displayName",
                returnType = "kotlin/String!!",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            agentProperty("AgentSkillScope", "displayName", "kotlin/String!!", propertyKind = "VAR"),
            agentProperty("AgentSkillScope", "displayName", "kotlin/Int!!"),
            agentProperty("AgentSkillScope", "displayName", "kotlin/String?"),
            "$key|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$key|suspend=true",
            key.replace(
                "abi=$CANONICAL_AGENT_PACKAGE/AgentSkillScope.displayName",
                "abi=$CANONICAL_AGENT_PACKAGE/AgentSkillScope.otherDisplayName",
            ),
        )
        canonicalDrift.forEach { drifted ->
            val drift = derive(
                listOf(drifted),
                listOf(SKILL_SCOPE_DISPLAY_NAME),
                references = listOf(SKILL_SCOPE_DISPLAY_NAME),
            )
            assertEquals(listOf(drifted), drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        listOf(
            SKILL_SCOPE_DISPLAY_NAME.replace("agentSkillScopeDisplayName", "futureSkillScopeDisplayName"),
            SKILL_SCOPE_DISPLAY_NAME.replace("scope:", "value:"),
            SKILL_SCOPE_DISPLAY_NAME.replace("AgentSkillScope", "string"),
            SKILL_SCOPE_DISPLAY_NAME.replace("scope:", "scope?:"),
            SKILL_SCOPE_DISPLAY_NAME.replace("scope:", "...scope:"),
            SKILL_SCOPE_DISPLAY_NAME.replace("): string", "): number"),
            SKILL_SCOPE_DISPLAY_NAME.replace("(scope: AgentSkillScope)", "()"),
        ).forEach { drifted ->
            val drift = derive(listOf(key), listOf(drifted), references = listOf(drifted))
            assertEquals(listOf(key), drift.missingCapabilityKeys, "Accepted public drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        val future = agentProperty("AgentSkillScope", "future", "kotlin/String!!")
        val futureEvidence = derive(
            listOf(key, future),
            listOf(SKILL_SCOPE_DISPLAY_NAME),
            references = listOf(SKILL_SCOPE_DISPLAY_NAME),
        )
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(listOf(key), futureEvidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))

        val aliasOnly = derive(
            listOf(key),
            listOf(SKILL_SCOPE_ALIAS),
            references = listOf(SKILL_SCOPE_ALIAS),
        )
        assertEquals(listOf(key), aliasOnly.missingCapabilityKeys)
        assertTrue(aliasOnly.projectionClaims.isEmpty())

        val unreferenced = derive(listOf(key), listOf(SKILL_SCOPE_DISPLAY_NAME), references = emptyList())
        assertTrue(unreferenced.errors.single().contains("Unreferenced exceptional"))
        assertTrue(unreferenced.projectionClaims.isEmpty())
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
    fun `conversation state snapshot compacts only the exact default and shares the supplied state envelope`() {
        val keys = d046ConversationStateKeys()
        val aggregateKeys = d046ConversationStateAggregateKeys()
        val symbols = d046ConversationStateSymbols()
        val evidence = derive(aggregateKeys, symbols, references = symbols)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        val conversation = keys.single { "AgentConversationState.conversation" in it }
        val turnProgress = keys.single { "AgentConversationState.turnProgress" in it }
        val state = aggregateKeys.single { "CodexConversation.state" in it }
        val activeTurnProgress = aggregateKeys.single { "CodexConversation.activeTurnProgress" in it }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(4, claims.size)
        assertEquals(
            (setOf(CONVERSATION_STATE_GETTER, CONVERSATION_STATE_OBSERVER) + D046_CONVERSATION).sorted(),
            claims.getValue(conversation).publicSymbols,
        )
        assertEquals(
            (setOf(CONVERSATION_STATE_GETTER, CONVERSATION_STATE_OBSERVER) + D046_TURN_PROGRESS).sorted(),
            claims.getValue(turnProgress).publicSymbols,
        )
        keys.forEach { key ->
            assertEquals(
                setOf(
                    CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                    CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                    CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
                    CrossLanguageBindingScenario.VALUE_CONVERSION,
                ),
                claims.getValue(key).sharedScenarios.toSet(),
            )
        }
        assertEquals(4, claims.values.count { CONVERSATION_STATE_GETTER in it.publicSymbols })
        assertEquals(4, claims.values.count { CONVERSATION_STATE_OBSERVER in it.publicSymbols })
        assertEquals(1, claims.values.count { D046_CONVERSATION in it.publicSymbols })
        assertEquals(2, claims.values.count { D046_TURN_PROGRESS in it.publicSymbols })
        assertTrue(D046_TURN_PROGRESS in claims.getValue(activeTurnProgress).publicSymbols)
        assertEquals(
            listOf(CONVERSATION_STATE_GETTER, CONVERSATION_STATE_OBSERVER).sorted(),
            claims.getValue(state).publicSymbols,
        )
        assertEquals(326, 324 + keys.size)
        assertEquals(218, 220 - keys.size)
        assertEquals(556, 326 + 12 + 218)
        assertEquals(38, 39 - 1)
        val currentSymbols = currentPublicSymbols()
        assertEquals(284, currentSymbols.size)
        assertEquals(listOf(D046_CONVERSATION), currentSymbols.filter { it == D046_CONVERSATION })
        assertEquals(73, symbolExports(currentSymbols).first.size)
        assertEquals(46, symbolExports(currentSymbols).second.size)
    }

    @Test
    fun `conversation state snapshot rejects canonical public reference envelope and reuse drift`() {
        val keys = d046ConversationStateKeys()
        val aggregateKeys = d046ConversationStateAggregateKeys()
        val symbols = d046ConversationStateSymbols()
        val conversation = keys.single { "AgentConversationState.conversation" in it }
        val turnProgress = keys.single { "AgentConversationState.turnProgress" in it }

        listOf(
            conversation.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            conversation.replace("AgentConversationState", "OtherConversationState"),
            canonicalFunction(
                "AgentConversationState",
                "conversation",
                returnType = "$CANONICAL_AGENT_PACKAGE/AgentConversation?",
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            conversation.replace("propertyKind=VAL", "propertyKind=VAR"),
            conversation.replace("AgentConversation?", "AgentConversation!!"),
            "$conversation|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$conversation|suspend=true",
            conversation.replace("AgentConversationState.conversation", "AgentConversationState.future"),
            turnProgress.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            turnProgress.replace("propertyKind=VAL", "propertyKind=VAR"),
            turnProgress.replace("AgentTurnProgress!!", "AgentTurnProgress?"),
            turnProgress.replace("AgentTurnProgress!!", "kotlin/String!!"),
        ).forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = symbols)
            assertEquals(listOf(drifted), drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        aggregateKeys.forEach { omitted ->
            val partial = derive(aggregateKeys - omitted, symbols, references = symbols)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys }, "Accepted without $omitted")
        }

        listOf(
            CONVERSATION_STATE_GETTER,
            CONVERSATION_STATE_OBSERVER,
            D046_CONVERSATION,
            D046_TURN_PROGRESS,
        ).forEach { omitted ->
            val partialSymbols = symbols - omitted
            val partial = derive(aggregateKeys, partialSymbols, references = partialSymbols)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys }, "Accepted without $omitted")
        }

        listOf(
            D046_CONVERSATION to D046_CONVERSATION.replace("AgentConversation", "string"),
            D046_TURN_PROGRESS to D046_TURN_PROGRESS.replace("CodexTurnProgress", "string"),
            CONVERSATION_STATE_GETTER to CONVERSATION_STATE_GETTER.replace("CodexConversationState", "string"),
            CONVERSATION_STATE_OBSERVER to
                CONVERSATION_STATE_OBSERVER.replace("state: CodexConversationState", "state: string"),
        ).forEach { (exact, drifted) ->
            val driftSymbols = symbols.map { if (it == exact) drifted else it }.sorted()
            val drift = derive(aggregateKeys, driftSymbols, references = driftSymbols)
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys })
        }

        listOf(
            "property:CodexConversationState#conversation[readonly]:AgentConversation | null | undefined",
            "property:CodexConversationState#turnProgress[readonly]:CodexTurnProgress | null | undefined",
        ).forEach { extra ->
            val ambiguousSymbols = (symbols + extra).sorted()
            val ambiguous = derive(aggregateKeys, ambiguousSymbols, references = ambiguousSymbols)
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey in keys })
        }

        listOf(
            CONVERSATION_STATE_GETTER,
            CONVERSATION_STATE_OBSERVER,
            D046_CONVERSATION,
            D046_TURN_PROGRESS,
        ).forEach { unreferenced ->
            val evidence = derive(aggregateKeys, symbols, references = symbols - unreferenced)
            assertTrue(evidence.errors.any { "Unreferenced exceptional" in it && unreferenced in it })
            assertTrue(evidence.projectionClaims.none { it.capabilityKey in keys })
        }

        val future = canonicalProperty("AgentConversationState", "future", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive(aggregateKeys + future, symbols, references = symbols)
        assertEquals(listOf(future), futureEvidence.missingCapabilityKeys)
        assertEquals(keys.toSet(), futureEvidence.projectionClaims.mapTo(mutableSetOf()) { it.capabilityKey }
            .intersect(keys.toSet()))

        val extraAggregate = canonicalProperty(
            "CodexConversation",
            "turnProgress",
            "kotlinx.coroutines.flow/StateFlow<INVARIANT:$CANONICAL_AGENT_PACKAGE/AgentTurnProgress?>!!",
        ).replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val reused = derive(aggregateKeys + extraAggregate, symbols, references = symbols)
        assertTrue(reused.errors.any {
            "Reused JavaScript/TypeScript public symbol" in it && turnProgress in it && extraAggregate in it
        })
        assertTrue(reused.projectionClaims.none { it.capabilityKey in setOf(turnProgress, extraAggregate) })

        val foreign = turnProgress.replace(CANONICAL_AGENT_PACKAGE, "foreign")
        val crossPackage = derive(aggregateKeys + foreign, symbols, references = symbols)
        assertEquals(listOf(foreign), crossPackage.missingCapabilityKeys)
        assertTrue(crossPackage.projectionClaims.none { it.capabilityKey == foreign })
    }

    @Test
    fun `typed turn request closes ten exact values and canonical send through two symbols`() {
        val keys = d047AgentTurnRequestKeys()
        val symbols = d047AgentTurnRequestSymbols()
        val references = listOf(D047_AGENT_TURN_REQUEST, D047_SEND_REQUEST).sorted()
        val evidence = derive(keys, symbols, references = references)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        val requestKeys = keys.filter { "owner=$CANONICAL_AGENT_PACKAGE/AgentTurnRequest|" in it }
        val constructor = requestKeys.single { "|kind=constructor|" in it }
        val capabilities = requestKeys.single { "AgentTurnRequest.capabilities" in it }
        val invocations = requestKeys.single { "AgentTurnRequest.invocations" in it }
        val nullable = requestKeys.filter {
            listOf("clientMessageId", "model", "effort", "serviceTier").any { name ->
                "AgentTurnRequest.$name" in it
            }
        }
        val send = keys.single { "CodexConversation.send" in it }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(11, keys.size)
        assertEquals(10, requestKeys.size)
        assertEquals(11, claims.size)
        requestKeys.forEach { key ->
            assertEquals(listOf(D047_AGENT_TURN_REQUEST), claims.getValue(key).publicSymbols)
            assertTrue(CrossLanguageBindingScenario.VALUE_CONVERSION in claims.getValue(key).sharedScenarios)
        }
        assertEquals(
            setOf(
                CrossLanguageBindingScenario.VALUE_CONVERSION,
                CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING,
                CrossLanguageBindingScenario.NULLABILITY,
            ),
            claims.getValue(constructor).sharedScenarios.toSet(),
        )
        listOf(capabilities, invocations).forEach { key ->
            assertTrue(
                CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING in
                    claims.getValue(key).sharedScenarios,
            )
        }
        nullable.forEach { key ->
            assertTrue(CrossLanguageBindingScenario.NULLABILITY in claims.getValue(key).sharedScenarios)
        }
        assertEquals(
            listOf(D047_AGENT_TURN_REQUEST, D047_SEND_REQUEST).sorted(),
            claims.getValue(send).publicSymbols,
        )
        assertEquals(
            setOf(
                CrossLanguageBindingScenario.ASYNC_SUCCESS,
                CrossLanguageBindingScenario.ASYNC_FAILURE,
                CrossLanguageBindingScenario.CANCELLATION,
                CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
            ),
            claims.getValue(send).sharedScenarios.toSet(),
        )
        assertEquals(337, 326 + claims.size)
        assertEquals(207, 218 - claims.size)
        assertEquals(556, 337 + 12 + 207)
        assertEquals(36, 38 - 2)
        assertEquals(references, evidence.packedApi.referencedSymbols)
        val currentSymbols = currentPublicSymbols()
        assertEquals(284, currentSymbols.size)
        assertTrue(references.all { it in currentSymbols })
        assertEquals(73, symbolExports(currentSymbols).first.size)
        assertEquals(46, symbolExports(currentSymbols).second.size)
        assertEquals(242, 240 + references.size)
    }

    @Test
    fun `typed turn request rejects family canonical symbol reference and reuse drift`() {
        val keys = d047AgentTurnRequestKeys()
        val symbols = d047AgentTurnRequestSymbols()
        val references = listOf(D047_AGENT_TURN_REQUEST, D047_SEND_REQUEST).sorted()
        val constructor = keys.single { "AgentTurnRequest.<init>" in it }
        val prompt = keys.single { "AgentTurnRequest.prompt" in it }
        val clientMessageId = keys.single { "AgentTurnRequest.clientMessageId" in it }
        val model = keys.single { "AgentTurnRequest.model" in it }
        val effort = keys.single { "AgentTurnRequest.effort" in it }
        val serviceTier = keys.single { "AgentTurnRequest.serviceTier" in it }
        val approvalPreset = keys.single { "AgentTurnRequest.approvalPreset" in it }
        val capabilities = keys.single { "AgentTurnRequest.capabilities" in it }
        val invocations = keys.single { "AgentTurnRequest.invocations" in it }
        val collaborationMode = keys.single { "AgentTurnRequest.collaborationMode" in it }
        val send = keys.single { "CodexConversation.send" in it }

        val canonicalDrift = listOf(
            constructor.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            constructor.replace("kind=constructor", "kind=function"),
            constructor.replaceFirst("kotlin/String!!", "kotlin/Int!!"),
            constructor.replaceFirst("default=false", "default=true"),
            constructor.replaceFirst("default=true", "default=false"),
            constructor.replaceFirst("vararg=false", "vararg=true"),
            constructor.replace("return=$CANONICAL_AGENT_PACKAGE/AgentTurnRequest", "return=kotlin/String"),
            constructor.replace("suspend=false", "suspend=true"),
            canonicalConstructor(
                "AgentTurnRequest",
                listOf(
                    "kotlin/String?",
                    "kotlin/String!!",
                    "kotlin/String?",
                    "kotlin/String?",
                    "kotlin/String?",
                    "example/AgentApprovalPreset!!",
                    "kotlin.collections/Set<INVARIANT:example/AgentCapability!!>!!",
                    "kotlin.collections/List<INVARIANT:example/AgentInvocation!!>!!",
                    "example/AgentCollaborationMode!!",
                ),
                defaultParameterIndices = (1..8).toSet(),
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            canonicalConstructor(
                "AgentTurnRequest",
                listOf("kotlin/String!!"),
            ).replace("example/", "$CANONICAL_AGENT_PACKAGE/"),
            prompt.replace("kotlin/String!!", "kotlin/String?"),
            clientMessageId.replace("kotlin/String?", "kotlin/String!!"),
            model.replace("kotlin/String?", "kotlin/Int?"),
            effort.replace("kotlin/String?", "kotlin/Boolean?"),
            serviceTier.replace("kotlin/String?", "kotlin/Long?"),
            approvalPreset.replace("AgentApprovalPreset!!", "AgentCollaborationMode!!"),
            capabilities.replace("kotlin.collections/Set", "kotlin.collections/List"),
            invocations.replace("kotlin.collections/List", "kotlin.collections/Set"),
            collaborationMode.replace("AgentCollaborationMode!!", "AgentCollaborationMode?"),
            prompt.replace("propertyKind=VAL", "propertyKind=VAR"),
            "$prompt|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
            "$prompt|suspend=true",
            prompt.replace("AgentTurnRequest.prompt", "AgentTurnRequest.future"),
            send.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            send.replace("return=kotlin/Unit", "return=kotlin/String!!"),
            send.replace("suspend=true", "suspend=false"),
            send.replace("AgentTurnRequest!!:default=false", "AgentTurnRequest?:default=false"),
            send.replace("default=false", "default=true"),
            send.replace("vararg=false", "vararg=true"),
            send.replace(".send|send()", ".future|future()"),
        )
        canonicalDrift.forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = references)
            assertTrue(drifted in drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        val aliasDrift = listOf(
            D047_AGENT_TURN_REQUEST.replace("readonly prompt: string; ", ""),
            D047_AGENT_TURN_REQUEST.replace("readonly model?: string | null | undefined; ", ""),
            D047_AGENT_TURN_REQUEST.replace(
                "readonly model?: string | null | undefined; readonly effort?: string | null | undefined; ",
                "readonly effort?: string | null | undefined; readonly model?: string | null | undefined; ",
            ),
            D047_AGENT_TURN_REQUEST.replace("readonly prompt", "prompt"),
            D047_AGENT_TURN_REQUEST.replace("prompt: string", "prompt?: string"),
            D047_AGENT_TURN_REQUEST.replace("clientMessageId?:", "clientMessageId:"),
            D047_AGENT_TURN_REQUEST.replace("model?: string", "model?: number"),
            D047_AGENT_TURN_REQUEST.replace("approvalPreset?: CodexApprovalPreset", "approvalPreset?: string"),
            D047_AGENT_TURN_REQUEST.replace("ReadonlyArray<AgentCapability>", "Array<AgentCapability>"),
            D047_AGENT_TURN_REQUEST.replace("ReadonlyArray<AgentInvocation>", "ReadonlyArray<string>"),
            D047_AGENT_TURN_REQUEST.replace("AgentCollaborationMode; }", "string; }"),
            D047_AGENT_TURN_REQUEST.replace("; }", "; readonly future?: string; }"),
        )
        aliasDrift.forEach { drifted ->
            val driftSymbols = symbols.map { if (it == D047_AGENT_TURN_REQUEST) drifted else it }.sorted()
            val drift = derive(keys, driftSymbols, references = listOf(drifted, D047_SEND_REQUEST).sorted())
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys }, "Accepted alias drift: $drifted")
        }

        listOf(
            D047_SEND_REQUEST.replace("sendRequest", "sendStructured"),
            D047_SEND_REQUEST.replace("request: AgentTurnRequest", "request?: AgentTurnRequest"),
            D047_SEND_REQUEST.replace("request: AgentTurnRequest", "request: string"),
            D047_SEND_REQUEST.replace("signal?:", "signal:"),
            D047_SEND_REQUEST.replace("AbortSignal | null | undefined", "AbortSignal"),
            D047_SEND_REQUEST.replace("Promise<void>", "Promise<string>"),
        ).forEach { drifted ->
            val driftSymbols = symbols.map { if (it == D047_SEND_REQUEST) drifted else it }.sorted()
            val drift = derive(keys, driftSymbols, references = listOf(D047_AGENT_TURN_REQUEST, drifted).sorted())
            assertTrue(drift.projectionClaims.none { it.capabilityKey in keys }, "Accepted method drift: $drifted")
        }

        keys.forEach { omitted ->
            val partial = derive(keys - omitted, symbols, references = references)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys }, "Accepted without $omitted")
        }
        references.forEach { omitted ->
            val unreferenced = derive(keys, symbols, references = references - omitted)
            assertTrue(unreferenced.errors.any { "Unreferenced exceptional" in it && omitted in it })
            assertTrue(unreferenced.projectionClaims.none { it.capabilityKey in keys })
        }
        listOf(D047_AGENT_TURN_REQUEST, D047_SEND_REQUEST).forEach { omitted ->
            val partialSymbols = symbols - omitted
            val partial = derive(keys, partialSymbols, references = references - omitted)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in keys })
        }

        listOf(
            D047_SEND_REQUEST.replace("signal?: AbortSignal | null | undefined", "signal?: AbortSignal"),
        ).forEach { extra ->
            val ambiguousSymbols = (symbols + extra).sorted()
            val ambiguous = derive(keys, ambiguousSymbols, references = (references + extra).sorted())
            assertTrue(ambiguous.projectionClaims.none { it.capabilityKey in keys })
        }

        val future = canonicalProperty("AgentTurnRequest", "future", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive(keys + future, symbols, references = references)
        assertTrue(future in futureEvidence.missingCapabilityKeys)
        assertTrue(futureEvidence.projectionClaims.none { it.capabilityKey in keys })

        val foreign = prompt.replace(CANONICAL_AGENT_PACKAGE, "foreign")
        val crossPackage = derive(keys + foreign, symbols, references = references)
        assertTrue(foreign in crossPackage.missingCapabilityKeys)
        assertTrue(crossPackage.projectionClaims.none { it.capabilityKey in keys })

        val unrelated = canonicalProperty("OtherRequest", "prompt", "kotlin/String!!")
        val arbitrary = derive(keys + unrelated, symbols, references = references)
        assertTrue(unrelated in arbitrary.missingCapabilityKeys)
        assertTrue(arbitrary.projectionClaims.none { it.capabilityKey == unrelated })
    }

    @Test
    fun `hooks close exact canonical values handler union and controller through thirty one symbols`() {
        val keys = d048HookKeys()
        val symbols = d048HookSymbols()
        val evidence = derive(keys, symbols, references = D048_PUBLIC_SYMBOLS)
        val claims = evidence.projectionClaims.associateBy(CrossLanguageProjectionClaim::capabilityKey)
        val handlerKeys = keys.filter { "AgentHookHandler." in it }

        assertTrue(evidence.errors.isEmpty(), evidence.errors.joinToString("\n"))
        assertTrue(evidence.missingCapabilityKeys.isEmpty(), evidence.missingCapabilityKeys.joinToString("\n"))
        assertTrue(evidence.applicabilityExclusions.isEmpty())
        assertEquals(35, keys.size)
        assertEquals(8, handlerKeys.size)
        assertEquals(35, claims.size)
        handlerKeys.forEach { key ->
            assertEquals(listOf(D048_AGENT_HOOK_HANDLER), claims.getValue(key).publicSymbols)
            assertEquals(
                setOf(
                    CrossLanguageBindingScenario.VALUE_CONVERSION,
                    CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING,
                ),
                claims.getValue(key).sharedScenarios.toSet(),
            )
        }
        assertEquals(372, 337 + claims.size)
        assertEquals(172, 207 - claims.size)
        assertEquals(556, 372 + 12 + 172)
        assertEquals(29, 36 - 7)
        assertEquals(D048_PUBLIC_SYMBOLS, evidence.packedApi.referencedSymbols)
        val currentSymbols = d048CurrentPublicSymbols()
        assertEquals(315, currentSymbols.size)
        assertTrue(D048_PUBLIC_SYMBOLS.all { it in currentSymbols })
        assertEquals(77, symbolExports(currentSymbols).first.size)
        assertEquals(49, symbolExports(currentSymbols).second.size)
        assertEquals(273, 242 + D048_PUBLIC_SYMBOLS.size)
    }

    @Test
    fun `hook handler union rejects canonical declaration reference and reuse drift`() {
        val keys = d048HookKeys()
        val symbols = d048HookSymbols()
        val handlerKeys = keys.filter { "AgentHookHandler." in it }
        val commandConstructor = handlerKeys.single { "AgentHookHandler.Command.<init>" in it }
        val command = handlerKeys.single { "AgentHookHandler.Command.command" in it }

        listOf(
            commandConstructor.replace(CANONICAL_AGENT_PACKAGE, "foreign"),
            commandConstructor.replace("kind=constructor", "kind=function"),
            commandConstructor.replaceFirst("kotlin/String!!", "kotlin/Int!!"),
            commandConstructor.replaceFirst("default=false", "default=true"),
            commandConstructor.replaceFirst("vararg=false", "vararg=true"),
            commandConstructor.replace("suspend=false", "suspend=true"),
            command.replace("kotlin/String!!", "kotlin/String?"),
            command.replace("propertyKind=VAL", "propertyKind=VAR"),
            command.replace("AgentHookHandler.Command.command", "AgentHookHandler.Command.future"),
        ).forEach { drifted ->
            val drift = derive(listOf(drifted), symbols, references = D048_PUBLIC_SYMBOLS)
            assertTrue(drifted in drift.missingCapabilityKeys, "Accepted canonical drift: $drifted")
            assertTrue(drift.projectionClaims.isEmpty())
        }

        listOf(
            D048_AGENT_HOOK_HANDLER.replace("readonly type", "type"),
            D048_AGENT_HOOK_HANDLER.replace("readonly command: string; ", ""),
            D048_AGENT_HOOK_HANDLER.replace("readonly isAsync: boolean", "readonly isAsync?: boolean"),
            D048_AGENT_HOOK_HANDLER.replace("readonly server: string", "readonly server: number"),
            D048_AGENT_HOOK_HANDLER.replace("readonly server: string; readonly tool: string", "readonly tool: string; readonly server: string"),
            D048_AGENT_HOOK_HANDLER.replace(" | { readonly type: \"prompt\"; }", ""),
            "$D048_AGENT_HOOK_HANDLER | { readonly type: \"future\"; }",
        ).forEach { drifted ->
            val driftSymbols = symbols.map { if (it == D048_AGENT_HOOK_HANDLER) drifted else it }.sorted()
            val drift = derive(keys, driftSymbols, references = D048_PUBLIC_SYMBOLS.map {
                if (it == D048_AGENT_HOOK_HANDLER) drifted else it
            }.sorted())
            assertTrue(drift.projectionClaims.none { it.capabilityKey in handlerKeys }, "Accepted alias drift: $drifted")
        }

        handlerKeys.forEach { omitted ->
            val partial = derive(keys - omitted, symbols, references = D048_PUBLIC_SYMBOLS)
            assertTrue(partial.projectionClaims.none { it.capabilityKey in handlerKeys }, "Accepted without $omitted")
        }
        val unreferenced = derive(keys, symbols, references = D048_PUBLIC_SYMBOLS - D048_AGENT_HOOK_HANDLER)
        assertTrue(unreferenced.errors.any {
            "Unreferenced exceptional" in it && D048_AGENT_HOOK_HANDLER in it
        })
        assertTrue(unreferenced.projectionClaims.none { it.capabilityKey in handlerKeys })

        val future = canonicalProperty("AgentHookHandler.Command", "future", "kotlin/String!!")
            .replace("example/", "$CANONICAL_AGENT_PACKAGE/")
        val futureEvidence = derive(keys + future, symbols, references = D048_PUBLIC_SYMBOLS)
        assertTrue(future in futureEvidence.missingCapabilityKeys)
        assertTrue(futureEvidence.projectionClaims.none { it.capabilityKey in handlerKeys })

        val foreignReuse = canonicalProperty("ForeignHookHandler", "command", "kotlin/String!!")
        val reused = derive(keys + foreignReuse, symbols, references = D048_PUBLIC_SYMBOLS)
        assertEquals(listOf(foreignReuse), reused.missingCapabilityKeys)
        assertTrue(reused.projectionClaims.none { it.capabilityKey == foreignReuse })
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

    private fun d046ConversationStateKeys(): List<String> = listOf(
        canonicalProperty(
            "AgentConversationState",
            "conversation",
            "$CANONICAL_AGENT_PACKAGE/AgentConversation?",
        ),
        canonicalProperty(
            "AgentConversationState",
            "turnProgress",
            "$CANONICAL_AGENT_PACKAGE/AgentTurnProgress!!",
        ),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d046ConversationStateAggregateKeys(): List<String> = (
        d046ConversationStateKeys() + listOf(
            canonicalProperty(
                "CodexConversation",
                "state",
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:$CANONICAL_AGENT_PACKAGE/" +
                    "AgentConversationState!!>!!",
            ),
            canonicalProperty(
                "CodexConversation",
                "activeTurnProgress",
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:$CANONICAL_AGENT_PACKAGE/" +
                    "AgentTurnProgress?>!!",
            ),
        ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }
        ).sorted()

    private fun d046ConversationStateSymbols(): List<String> = listOf(
        "class:AgentConversation",
        "class:CodexConversation",
        "class:CodexConversationState",
        CONVERSATION_STATE_GETTER,
        CONVERSATION_STATE_OBSERVER,
        D046_CONVERSATION,
        D046_TURN_PROGRESS,
    ).sorted()

    private fun d047AgentTurnRequestKeys(): List<String> = listOf(
        canonicalConstructor(
            "AgentTurnRequest",
            listOf(
                "kotlin/String!!",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/String?",
                "example/AgentApprovalPreset!!",
                "kotlin.collections/Set<INVARIANT:example/AgentCapability!!>!!",
                "kotlin.collections/List<INVARIANT:example/AgentInvocation!!>!!",
                "example/AgentCollaborationMode!!",
            ),
            defaultParameterIndices = (1..8).toSet(),
        ),
        canonicalProperty("AgentTurnRequest", "prompt", "kotlin/String!!"),
        canonicalProperty("AgentTurnRequest", "clientMessageId", "kotlin/String?"),
        canonicalProperty("AgentTurnRequest", "model", "kotlin/String?"),
        canonicalProperty("AgentTurnRequest", "effort", "kotlin/String?"),
        canonicalProperty("AgentTurnRequest", "serviceTier", "kotlin/String?"),
        canonicalProperty("AgentTurnRequest", "approvalPreset", "example/AgentApprovalPreset!!"),
        canonicalProperty(
            "AgentTurnRequest",
            "capabilities",
            "kotlin.collections/Set<INVARIANT:example/AgentCapability!!>!!",
        ),
        canonicalProperty(
            "AgentTurnRequest",
            "invocations",
            "kotlin.collections/List<INVARIANT:example/AgentInvocation!!>!!",
        ),
        canonicalProperty(
            "AgentTurnRequest",
            "collaborationMode",
            "example/AgentCollaborationMode!!",
        ),
        canonicalFunction(
            "CodexConversation",
            "send",
            suspendFunction = true,
            parameters = listOf("example/AgentTurnRequest!!"),
        ),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d047AgentTurnRequestSymbols(): List<String> = listOf(
        "class:CodexConversation",
        D047_AGENT_TURN_REQUEST,
        D047_SEND_REQUEST,
    ).sorted()

    private fun d048HookKeys(): List<String> = listOf(
        canonicalObject("AgentHookHandler.Agent"),
        canonicalConstructor(
            "AgentHookHandler.Command",
            listOf("kotlin/String!!", "kotlin/Boolean!!"),
        ),
        canonicalProperty("AgentHookHandler.Command", "command", "kotlin/String!!"),
        canonicalProperty("AgentHookHandler.Command", "isAsync", "kotlin/Boolean!!"),
        canonicalConstructor(
            "AgentHookHandler.McpTool",
            listOf("kotlin/String!!", "kotlin/String!!"),
        ),
        canonicalProperty("AgentHookHandler.McpTool", "server", "kotlin/String!!"),
        canonicalProperty("AgentHookHandler.McpTool", "tool", "kotlin/String!!"),
        canonicalObject("AgentHookHandler.Prompt"),
        canonicalConstructor(
            "AgentHook",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/Boolean!!",
                "kotlin/String!!",
                "example/AgentHookHandler!!",
                "kotlin/Boolean!!",
                "kotlin/String!!",
                "kotlin/String!!",
                "kotlin/Long!!",
                "example/AgentHookTrustStatus!!",
                "kotlin/String?",
                "kotlin/String?",
                "kotlin/String?",
                "example/AgentResourceOrigin!!",
                "kotlin/Boolean!!",
            ),
            defaultParameterIndices = (10..14).toSet(),
        ),
        canonicalProperty("AgentHook", "key", "kotlin/String!!"),
        canonicalProperty("AgentHook", "currentHash", "kotlin/String!!"),
        canonicalProperty("AgentHook", "isEnabled", "kotlin/Boolean!!"),
        canonicalProperty("AgentHook", "eventName", "kotlin/String!!"),
        canonicalProperty("AgentHook", "handler", "example/AgentHookHandler!!"),
        canonicalProperty("AgentHook", "isManaged", "kotlin/Boolean!!"),
        canonicalProperty("AgentHook", "source", "kotlin/String!!"),
        canonicalProperty("AgentHook", "sourcePath", "kotlin/String!!"),
        canonicalProperty("AgentHook", "timeoutSeconds", "kotlin/Long!!"),
        canonicalProperty("AgentHook", "trustStatus", "example/AgentHookTrustStatus!!"),
        canonicalProperty("AgentHook", "matcher", "kotlin/String?"),
        canonicalProperty("AgentHook", "pluginId", "kotlin/String?"),
        canonicalProperty("AgentHook", "statusMessage", "kotlin/String?"),
        canonicalProperty("AgentHook", "origin", "example/AgentResourceOrigin!!"),
        canonicalProperty("AgentHook", "canUninstall", "kotlin/Boolean!!"),
        canonicalProperty("AgentHook", "canTrust", "kotlin/Boolean!!"),
        canonicalConstructor(
            "AgentHookCatalog",
            listOf(
                "kotlin.collections/List<INVARIANT:example/AgentHook!!>!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
            ),
            defaultParameterIndices = setOf(1, 2),
        ),
        canonicalProperty(
            "AgentHookCatalog",
            "hooks",
            "kotlin.collections/List<INVARIANT:example/AgentHook!!>!!",
        ),
        canonicalProperty(
            "AgentHookCatalog",
            "warnings",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        ),
        canonicalProperty(
            "AgentHookCatalog",
            "errors",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        ),
        canonicalProperty("CodexHooks", "isAvailable", "kotlin/Boolean!!"),
        canonicalFunction(
            "CodexHooks",
            "list",
            returnType = "example/AgentHookCatalog!!",
            suspendFunction = true,
        ),
        canonicalFunction(
            "CodexHooks",
            "install",
            returnType = "example/AgentHook!!",
            suspendFunction = true,
            parameters = listOf("kotlin/String!!", "example/AgentInstallationScope!!"),
        ),
        canonicalFunction(
            "CodexHooks",
            "uninstall",
            suspendFunction = true,
            parameters = listOf("example/AgentHook!!"),
        ),
        canonicalFunction(
            "CodexHooks",
            "trust",
            suspendFunction = true,
            parameters = listOf("example/AgentHook!!"),
        ),
        canonicalProperty("CodexAgent", "hooks", "example/CodexHooks!!"),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d048HookSymbols(): List<String> = (
        D048_PUBLIC_SYMBOLS + listOf("class:CodexAgent")
    ).distinct().sorted()

    private fun d049AuthorizationUrlKeys(): List<String> = listOf(
        canonicalProperty(
            "CodexAuthorizationUrl",
            "purpose",
            "example/CodexAuthorizationPurpose!!",
        ),
        canonicalProperty("CodexAuthorizationUrl", "value", "kotlin/String!!"),
        canonicalFunction(
            "CodexAuthorizationUrl.Companion",
            "chatGpt",
            returnType = "example/CodexAuthorizationUrl!!",
            parameters = listOf("kotlin/String!!"),
        ),
        canonicalFunction(
            "CodexAuthorizationUrl.Companion",
            "external",
            returnType = "example/CodexAuthorizationUrl!!",
            parameters = listOf("kotlin/String!!"),
        ),
    ).sorted()

    private fun d049AuthorizationUrlSymbols(): List<String> = (
        D049_PUBLIC_SYMBOLS +
            "type:CodexAuthorizationPurpose:\"chat_gpt\" | \"external\""
    ).sorted()

    private fun d050McpServersKeys(): List<String> = listOf(
        canonicalConstructor(
            "AgentMcpTransport.Stdio",
            listOf(
                "kotlin/String!!",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
                "kotlin/String?",
                "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
                "kotlin.collections/List<INVARIANT:example/AgentMcpEnvironmentVariable!!>!!",
            ),
            defaultParameterIndices = setOf(1, 2, 3, 4),
        ),
        canonicalProperty("AgentMcpTransport.Stdio", "command", "kotlin/String!!"),
        canonicalProperty(
            "AgentMcpTransport.Stdio",
            "arguments",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>!!",
        ),
        canonicalProperty("AgentMcpTransport.Stdio", "workingDirectory", "kotlin/String?"),
        canonicalProperty(
            "AgentMcpTransport.Stdio",
            "environment",
            "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty(
            "AgentMcpTransport.Stdio",
            "forwardedEnvironment",
            "kotlin.collections/List<INVARIANT:example/AgentMcpEnvironmentVariable!!>!!",
        ),
        canonicalConstructor(
            "AgentMcpTransport.Http",
            listOf(
                "kotlin/String!!",
                "kotlin/String?",
                "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
                "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
                "kotlin/String?",
            ),
            defaultParameterIndices = setOf(1, 2, 3, 4),
        ),
        canonicalProperty("AgentMcpTransport.Http", "url", "kotlin/String!!"),
        canonicalProperty("AgentMcpTransport.Http", "bearerTokenEnvironmentVariable", "kotlin/String?"),
        canonicalProperty(
            "AgentMcpTransport.Http",
            "headers",
            "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty(
            "AgentMcpTransport.Http",
            "environmentHeaders",
            "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty("AgentMcpTransport.Http", "headersHelper", "kotlin/String?"),
        canonicalConstructor(
            "AgentMcpServerConfiguration",
            listOf(
                "kotlin/String!!",
                "example/AgentMcpTransport!!",
                "example/AgentMcpAuthentication?",
                "kotlin/String!!",
                "kotlin/Boolean!!",
                "kotlin/Boolean!!",
                "kotlin/Boolean!!",
                "kotlin.collections/List<INVARIANT:example/AgentMcpToolExposureSurface!!>?",
                "kotlin/Double?",
                "kotlin/Double?",
                "example/AgentMcpToolApproval?",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
                "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
                "example/AgentMcpOauthConfiguration?",
                "kotlin/String?",
                "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:example/AgentMcpToolConfiguration!!>!!",
            ),
            defaultParameterIndices = (2..16).toSet(),
        ),
        canonicalProperty("AgentMcpServerConfiguration", "name", "kotlin/String!!"),
        canonicalProperty("AgentMcpServerConfiguration", "transport", "example/AgentMcpTransport!!"),
        canonicalProperty("AgentMcpServerConfiguration", "authentication", "example/AgentMcpAuthentication?"),
        canonicalProperty("AgentMcpServerConfiguration", "environmentId", "kotlin/String!!"),
        canonicalProperty("AgentMcpServerConfiguration", "isEnabled", "kotlin/Boolean!!"),
        canonicalProperty("AgentMcpServerConfiguration", "isRequired", "kotlin/Boolean!!"),
        canonicalProperty("AgentMcpServerConfiguration", "supportsParallelToolCalls", "kotlin/Boolean!!"),
        canonicalProperty(
            "AgentMcpServerConfiguration",
            "omitToolsFrom",
            "kotlin.collections/List<INVARIANT:example/AgentMcpToolExposureSurface!!>?",
        ),
        canonicalProperty("AgentMcpServerConfiguration", "startupTimeoutSeconds", "kotlin/Double?"),
        canonicalProperty("AgentMcpServerConfiguration", "toolTimeoutSeconds", "kotlin/Double?"),
        canonicalProperty("AgentMcpServerConfiguration", "defaultToolApproval", "example/AgentMcpToolApproval?"),
        canonicalProperty(
            "AgentMcpServerConfiguration",
            "enabledTools",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty(
            "AgentMcpServerConfiguration",
            "disabledTools",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty(
            "AgentMcpServerConfiguration",
            "scopes",
            "kotlin.collections/List<INVARIANT:kotlin/String!!>?",
        ),
        canonicalProperty("AgentMcpServerConfiguration", "oauth", "example/AgentMcpOauthConfiguration?"),
        canonicalProperty("AgentMcpServerConfiguration", "oauthResource", "kotlin/String?"),
        canonicalProperty(
            "AgentMcpServerConfiguration",
            "tools",
            "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:example/AgentMcpToolConfiguration!!>!!",
        ),
        canonicalConstructor(
            "AgentMcpServer",
            listOf(
                "kotlin/String!!",
                "kotlin/String!!",
                "example/AgentMcpAuthStatus!!",
                "example/AgentMcpServerConfiguration?",
                "example/AgentResourceOrigin!!",
                "kotlin/Boolean!!",
            ),
            defaultParameterIndices = setOf(3, 4, 5),
        ),
        canonicalProperty("AgentMcpServer", "name", "kotlin/String!!"),
        canonicalProperty("AgentMcpServer", "displayName", "kotlin/String!!"),
        canonicalProperty("AgentMcpServer", "authStatus", "example/AgentMcpAuthStatus!!"),
        canonicalProperty("AgentMcpServer", "configuration", "example/AgentMcpServerConfiguration?"),
        canonicalProperty("AgentMcpServer", "origin", "example/AgentResourceOrigin!!"),
        canonicalProperty("AgentMcpServer", "canRemove", "kotlin/Boolean!!"),
        canonicalProperty("AgentMcpServer", "isAuthorized", "kotlin/Boolean!!"),
        canonicalProperty("CodexMcpServers", "isAvailable", "kotlin/Boolean!!"),
        canonicalFunction(
            "CodexMcpServers",
            "list",
            returnType = "kotlin.collections/List<INVARIANT:example/AgentMcpServer!!>!!",
            suspendFunction = true,
        ),
        canonicalFunction(
            "CodexMcpServers",
            "add",
            returnType = "example/AgentMcpServer!!",
            suspendFunction = true,
            parameters = listOf("example/AgentMcpServerConfiguration!!"),
        ),
        canonicalFunction(
            "CodexMcpServers",
            "remove",
            suspendFunction = true,
            parameters = listOf("example/AgentMcpServer!!"),
        ),
        canonicalProperty("CodexAgent", "mcpServers", "example/CodexMcpServers!!"),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d050McpServersSymbols(): List<String> =
        (D050_PUBLIC_SYMBOLS + "class:CodexAgent").distinct().sorted()

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

    private fun d044HostLifecycleKey(): String = canonicalProperty(
        "CodexHost",
        "lifecycleState",
        "kotlinx.coroutines.flow/StateFlow<INVARIANT:$CANONICAL_AGENT_PACKAGE/CodexHostState!!>!!",
    ).replace("example/", "$CANONICAL_AGENT_PACKAGE/")

    private fun d044HostStateKeys(): List<String> = listOf(
        canonicalProperty(
            "CodexHostState.Failed",
            "failure",
            "$CANONICAL_AGENT_PACKAGE/CodexFailure!!",
        ),
        canonicalProperty(
            "CodexHostState.Failed",
            "workspace",
            "$CANONICAL_AGENT_PACKAGE/CodexWorkspace?",
        ),
        canonicalProperty(
            "CodexHostState.Preparing",
            "workspace",
            "$CANONICAL_AGENT_PACKAGE/CodexWorkspace!!",
        ),
        canonicalProperty(
            "CodexHostState.Ready",
            "agent",
            "$CANONICAL_AGENT_PACKAGE/CodexAgent!!",
        ),
        canonicalProperty(
            "CodexHostState.WorkspaceRequired",
            "requirement",
            "$CANONICAL_AGENT_PACKAGE/CodexWorkspaceResolution.SelectionRequired!!",
        ),
        canonicalProperty(
            "CodexWorkspaceResolution.Available",
            "workspace",
            "$CANONICAL_AGENT_PACKAGE/CodexWorkspace!!",
        ),
        canonicalProperty(
            "CodexWorkspaceResolution.SelectionRequired",
            "message",
            "kotlin/String!!",
        ),
        canonicalProperty(
            "CodexWorkspaceResolution.SelectionRequired",
            "reason",
            "$CANONICAL_AGENT_PACKAGE/CodexWorkspaceSelectionReason!!",
        ),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d044HostStateReferences(): List<String> = listOf(
        HOST_STATE_AGENT,
        HOST_STATE_FAILURE,
        HOST_STATE_GETTER,
        HOST_STATE_OBSERVER,
        HOST_STATE_SELECTION_MESSAGE,
        HOST_STATE_SELECTION_REASON,
        HOST_STATE_STATUS,
        HOST_STATE_WORKSPACE,
    ).sorted()

    private fun d045ConversationKeys(): List<String> = listOf(
        canonicalConstructor(
            "AgentConversation",
            listOf(
                "example/AgentConversationSummary!!",
                "kotlin.collections/List<INVARIANT:example/AgentMessage!!>!!",
            ),
        ),
        canonicalProperty(
            "AgentConversation",
            "messages",
            "kotlin.collections/List<INVARIANT:example/AgentMessage!!>!!",
        ),
        canonicalProperty("AgentConversation", "summary", "example/AgentConversationSummary!!"),
        canonicalFunction(
            "CodexConversations",
            "read",
            returnType = "example/AgentConversation!!",
            suspendFunction = true,
            parameters = listOf("example/ConversationId!!"),
        ),
        canonicalProperty("CodexAgent", "conversations", "example/CodexConversations!!"),
    ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }.sorted()

    private fun d045ConversationAggregateKeys(): List<String> = (
        d045ConversationKeys() + listOf(
            canonicalProperty(
                "CodexConversations",
                "active",
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:example/CodexConversation?>!!",
            ),
            canonicalFunction(
                "CodexConversations",
                "list",
                returnType =
                    "kotlin.collections/List<INVARIANT:example/AgentConversationSummary!!>!!",
                suspendFunction = true,
            ),
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
            canonicalConstructor(
                "AgentConversationSettings",
                listOf("example/AgentApprovalPreset!!", "kotlin/String?"),
                defaultParameterIndices = setOf(0, 1),
            ),
            canonicalProperty(
                "AgentConversationSettings",
                "approvalPreset",
                "example/AgentApprovalPreset!!",
            ),
            canonicalProperty("AgentConversationSettings", "serviceTier", "kotlin/String?"),
            canonicalConstructor("ConversationId", listOf("kotlin/String!!")),
            canonicalProperty("ConversationId", "value", "kotlin/String!!"),
        ).map { it.replace("example/", "$CANONICAL_AGENT_PACKAGE/") }
    ).sorted()

    private fun d045ConversationEnvelope(): List<String> = listOf(
        ACTIVE_CONVERSATION,
        DELETE_CONVERSATION,
        LIST_CONVERSATIONS,
        OBSERVE_ACTIVE_CONVERSATION,
        OPEN_CONVERSATION,
        READ_CONVERSATION,
        RENAME_CONVERSATION,
    ).sorted()

    private fun d045ConversationSymbols(): List<String> = (
        d045PublicSymbols() + d045ConversationEnvelope() + "class:CodexAgent"
    ).distinct().sorted().also { assertEquals(12, it.size) }

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

    private fun currentPublicSymbols(): List<String> {
        val baseline = CURRENT_PUBLIC_SYMBOLS.lineSequence()
            .filter(String::isNotBlank)
            .toList()
            .also { assertEquals(208, it.size) }
        return (
            baseline + modelPublicSymbols() + SKILL_SCOPE_DISPLAY_NAME + skillsPublicSymbols() +
                d043PublicSymbols() + d045PublicSymbols() + D046_CONVERSATION +
                D047_AGENT_TURN_REQUEST + D047_SEND_REQUEST
            )
            .sorted()
            .also { assertEquals(284, it.size) }
    }

    private fun d048CurrentPublicSymbols(): List<String> =
        (currentPublicSymbols() + D048_PUBLIC_SYMBOLS).distinct().sorted()
            .also { assertEquals(315, it.size) }

    private fun d049CurrentPublicSymbols(): List<String> = (
        d048CurrentPublicSymbols().map { symbol ->
            when (symbol) {
                "getter:CodexAuthenticationState#deviceVerificationUrl:string | null | undefined" ->
                    "getter:CodexAuthenticationState#deviceVerificationUrl:" +
                        "CodexAuthorizationUrl | null | undefined"
                "getter:CodexAuthenticationState#pendingSignInUrl:string | null | undefined" ->
                    "getter:CodexAuthenticationState#pendingSignInUrl:" +
                        "CodexAuthorizationUrl | null | undefined"
                else -> symbol
            }
        } + D049_PUBLIC_SYMBOLS
    ).distinct().sorted().also { assertEquals(320, it.size) }

    private fun d050CurrentPublicSymbols(): List<String> =
        (d049CurrentPublicSymbols() + D050_PUBLIC_SYMBOLS).distinct().sorted()
            .also { assertEquals(369, it.size) }

    private fun modelPublicSymbols(): List<String> = MODELS_PUBLIC_SYMBOLS.lineSequence()
        .filter(String::isNotBlank)
        .toList()
        .also {
            assertEquals(21, it.size)
            assertEquals(it.sorted(), it)
        }

    private fun skillsPublicSymbols(): List<String> = SKILLS_PUBLIC_SYMBOLS.lineSequence()
        .filter(String::isNotBlank)
        .toList()
        .also {
            assertEquals(28, it.size)
            assertEquals(it.sorted(), it)
        }

    private fun d043PublicSymbols(): List<String> = D043_PUBLIC_SYMBOLS.lineSequence()
        .filter(String::isNotBlank)
        .toList()
        .also {
            assertEquals(18, it.size)
            assertEquals(it.sorted(), it)
        }

    private fun d045PublicSymbols(): List<String> = listOf(
        "class:AgentConversation",
        AGENT_CONVERSATION_CONSTRUCTOR,
        AGENT_CONVERSATION_MESSAGES,
        AGENT_CONVERSATION_SUMMARY,
        READ_CONVERSATION,
    ).sorted().also { assertEquals(5, it.size) }

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
        private const val READ_CONVERSATION =
            "method:CodexAgent#readConversation:" +
                "(conversationId: string, " +
                "signal?: AbortSignal | null | undefined): Promise<AgentConversation>"
        private const val LIST_CONVERSATIONS =
            "method:CodexAgent#listConversations:" +
                "(signal?: AbortSignal | null | undefined): " +
                "Promise<ReadonlyArray<AgentConversationSummary>>"
        private const val ACTIVE_CONVERSATION =
            "getter:CodexAgent#activeConversation:CodexConversation | null | undefined"
        private const val OBSERVE_ACTIVE_CONVERSATION =
            "method:CodexAgent#observeActiveConversation:" +
                "(listener: (conversation: CodexConversation | null | undefined) => void): CodexObservation"
        private const val AGENT_CONVERSATION_CONSTRUCTOR =
            "constructor:AgentConversation#" +
                "(summary: AgentConversationSummary, messages: ReadonlyArray<CodexMessage>)"
        private const val AGENT_CONVERSATION_MESSAGES =
            "getter:AgentConversation#messages:ReadonlyArray<CodexMessage>"
        private const val AGENT_CONVERSATION_SUMMARY =
            "getter:AgentConversation#summary:AgentConversationSummary"
        private const val APPROVAL_PRESET_DISPLAY_NAME =
            "function:codexApprovalPresetDisplayName:(preset: CodexApprovalPreset): string"
        private const val AGENT_CAPABILITY_ALIAS = "type:AgentCapability:\"web_search\""
        private const val AGENT_CAPABILITY_DISPLAY_LABEL =
            "function:agentCapabilityDisplayLabel:(capability: AgentCapability): string"
        private const val AGENT_CAPABILITY_ICON =
            "function:agentCapabilityIcon:(capability: AgentCapability): string | null | undefined"
        private const val AGENT_CAPABILITY_ID =
            "function:agentCapabilityId:(capability: AgentCapability): string"
        private const val AGENT_CAPABILITY_PROMPT_LABEL =
            "function:agentCapabilityPromptLabel:(capability: AgentCapability): string"
        private const val AGENT_INVOCATION_TYPE =
            "type:AgentInvocation:AgentPluginInvocation | AgentSkillInvocation"
        private const val CANONICAL_AGENT_PACKAGE = "io.github.codex_agent_labs.codexmobile.agent"
        private const val HOST_STATE_GETTER = "getter:CodexHost#state:CodexHostState"
        private const val HOST_STATE_OBSERVER =
            "method:CodexHost#observeState:" +
                "(listener: (state: CodexHostState) => void): CodexObservation"
        private const val HOST_STATE_STATUS = "getter:CodexHostState#status:CodexHostStatus"
        private const val HOST_STATE_WORKSPACE =
            "getter:CodexHostState#workspace:CodexWorkspace | null | undefined"
        private const val HOST_STATE_AGENT =
            "getter:CodexHostState#agent:CodexAgent | null | undefined"
        private const val HOST_STATE_FAILURE =
            "getter:CodexHostState#failure:CodexFailure | null | undefined"
        private const val HOST_STATE_SELECTION_REASON =
            "getter:CodexHostState#selectionReason:CodexWorkspaceSelectionReason | null | undefined"
        private const val HOST_STATE_SELECTION_MESSAGE =
            "getter:CodexHostState#selectionMessage:string | null | undefined"
        private const val CREATE_CODEX_HOST =
            "function:createCodexHost:" +
                "(bundleDirectory: string, dataDirectory: string, clientName: string, " +
                "clientTitle: string, clientVersion: string): CodexHost"
        private const val SKILL_SCOPE_DISPLAY_NAME =
            "function:agentSkillScopeDisplayName:(scope: AgentSkillScope): string"
        private const val SKILL_SCOPE_ALIAS =
            "type:AgentSkillScope:\"admin\" | \"plugin\" | \"repo\" | \"system\" | \"user\""
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
        private const val D046_CONVERSATION =
            "getter:CodexConversationState#conversation:AgentConversation | null | undefined"
        private const val D046_TURN_PROGRESS =
            "getter:CodexConversationState#turnProgress:CodexTurnProgress | null | undefined"
        private const val D047_AGENT_TURN_REQUEST =
            "type:AgentTurnRequest:{ readonly prompt: string; " +
                "readonly clientMessageId?: string | null | undefined; " +
                "readonly model?: string | null | undefined; " +
                "readonly effort?: string | null | undefined; " +
                "readonly serviceTier?: string | null | undefined; " +
                "readonly approvalPreset?: CodexApprovalPreset; " +
                "readonly capabilities?: ReadonlyArray<AgentCapability>; " +
                "readonly invocations?: ReadonlyArray<AgentInvocation>; " +
                "readonly collaborationMode?: AgentCollaborationMode; }"
        private const val D047_SEND_REQUEST =
            "method:CodexConversation#sendRequest:" +
                "(request: AgentTurnRequest, " +
                "signal?: AbortSignal | null | undefined): Promise<void>"
        private const val D048_AGENT_HOOK_HANDLER =
            "type:AgentHookHandler:{ readonly type: \"agent\"; } | " +
                "{ readonly type: \"command\"; readonly command: string; readonly isAsync: boolean; } | " +
                "{ readonly type: \"mcp_tool\"; readonly server: string; readonly tool: string; } | " +
                "{ readonly type: \"prompt\"; }"
        private val D048_PUBLIC_SYMBOLS = listOf(
            "class:AgentHook",
            "class:AgentHookCatalog",
            "class:CodexHooks",
            "constructor:AgentHook#(key: string, currentHash: string, isEnabled: boolean, " +
                "eventName: string, handler: AgentHookHandler, isManaged: boolean, source: string, " +
                "sourcePath: string, timeoutSeconds: bigint, trustStatus: AgentHookTrustStatus, " +
                "matcher?: string | null | undefined, pluginId?: string | null | undefined, " +
                "statusMessage?: string | null | undefined, origin?: AgentResourceOrigin, " +
                "canUninstall?: boolean)",
            "constructor:AgentHookCatalog#(hooks: ReadonlyArray<AgentHook>, " +
                "warnings?: ReadonlyArray<string>, errors?: ReadonlyArray<string>)",
            "getter:AgentHook#canTrust:boolean",
            "getter:AgentHook#canUninstall:boolean",
            "getter:AgentHook#currentHash:string",
            "getter:AgentHook#eventName:string",
            "getter:AgentHook#handler:AgentHookHandler",
            "getter:AgentHook#isEnabled:boolean",
            "getter:AgentHook#isManaged:boolean",
            "getter:AgentHook#key:string",
            "getter:AgentHook#matcher:string | null | undefined",
            "getter:AgentHook#origin:AgentResourceOrigin",
            "getter:AgentHook#pluginId:string | null | undefined",
            "getter:AgentHook#source:string",
            "getter:AgentHook#sourcePath:string",
            "getter:AgentHook#statusMessage:string | null | undefined",
            "getter:AgentHook#timeoutSeconds:bigint",
            "getter:AgentHook#trustStatus:AgentHookTrustStatus",
            "getter:AgentHookCatalog#errors:ReadonlyArray<string>",
            "getter:AgentHookCatalog#hooks:ReadonlyArray<AgentHook>",
            "getter:AgentHookCatalog#warnings:ReadonlyArray<string>",
            "getter:CodexAgent#hooks:CodexHooks",
            "getter:CodexHooks#isAvailable:boolean",
            "method:CodexHooks#install:(directory: string, scope: AgentInstallationScope, " +
                "signal?: AbortSignal | null | undefined): Promise<AgentHook>",
            "method:CodexHooks#list:(signal?: AbortSignal | null | undefined): Promise<AgentHookCatalog>",
            "method:CodexHooks#trust:(hook: AgentHook, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
            "method:CodexHooks#uninstall:(hook: AgentHook, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
            D048_AGENT_HOOK_HANDLER,
        ).sorted()
        private const val D049_PURPOSE =
            "getter:CodexAuthorizationUrl#purpose:CodexAuthorizationPurpose"
        private const val D049_VALUE = "getter:CodexAuthorizationUrl#value:string"
        private const val D049_CHAT_GPT =
            "method:CodexAuthorizationUrl#chatGpt[static]:(value: string): CodexAuthorizationUrl"
        private const val D049_EXTERNAL =
            "method:CodexAuthorizationUrl#external[static]:(value: string): CodexAuthorizationUrl"
        private val D049_PUBLIC_SYMBOLS = listOf(
            "class:CodexAuthorizationUrl",
            D049_PURPOSE,
            D049_VALUE,
            D049_CHAT_GPT,
            D049_EXTERNAL,
        ).sorted()
        private val D050_PUBLIC_SYMBOLS = listOf(
            "class:AgentMcpHttpTransport",
            "class:AgentMcpServer",
            "class:AgentMcpServerConfiguration",
            "class:AgentMcpStdioTransport",
            "class:CodexMcpServers",
            "constructor:AgentMcpHttpTransport#(url: string, " +
                "bearerTokenEnvironmentVariable?: string | null | undefined, " +
                "headers?: Readonly<Record<string, string>> | null | undefined, " +
                "environmentHeaders?: Readonly<Record<string, string>> | null | undefined, " +
                "headersHelper?: string | null | undefined)",
            "constructor:AgentMcpServer#(name: string, displayName: string, " +
                "authStatus: AgentMcpAuthStatus, " +
                "configuration?: AgentMcpServerConfiguration | null | undefined, " +
                "origin?: AgentResourceOrigin, canRemove?: boolean)",
            "constructor:AgentMcpServerConfiguration#(name: string, transport: AgentMcpTransport, " +
                "authentication?: AgentMcpAuthentication | null | undefined, environmentId?: string, " +
                "isEnabled?: boolean, isRequired?: boolean, supportsParallelToolCalls?: boolean, " +
                "omitToolsFrom?: ReadonlyArray<AgentMcpToolExposureSurface> | null | undefined, " +
                "startupTimeoutSeconds?: number | null | undefined, " +
                "toolTimeoutSeconds?: number | null | undefined, " +
                "defaultToolApproval?: AgentMcpToolApproval | null | undefined, " +
                "enabledTools?: ReadonlyArray<string> | null | undefined, " +
                "disabledTools?: ReadonlyArray<string> | null | undefined, " +
                "scopes?: ReadonlyArray<string> | null | undefined, " +
                "oauth?: AgentMcpOauthConfiguration | null | undefined, " +
                "oauthResource?: string | null | undefined, " +
                "tools?: Readonly<Record<string, AgentMcpToolConfiguration>>)",
            "constructor:AgentMcpStdioTransport#(command: string, arguments?: ReadonlyArray<string>, " +
                "workingDirectory?: string | null | undefined, " +
                "environment?: Readonly<Record<string, string>> | null | undefined, " +
                "forwardedEnvironment?: ReadonlyArray<AgentMcpEnvironmentVariable>)",
            "getter:AgentMcpHttpTransport#bearerTokenEnvironmentVariable:string | null | undefined",
            "getter:AgentMcpHttpTransport#environmentHeaders:" +
                "Readonly<Record<string, string>> | null | undefined",
            "getter:AgentMcpHttpTransport#headers:Readonly<Record<string, string>> | null | undefined",
            "getter:AgentMcpHttpTransport#headersHelper:string | null | undefined",
            "getter:AgentMcpHttpTransport#url:string",
            "getter:AgentMcpServer#authStatus:AgentMcpAuthStatus",
            "getter:AgentMcpServer#canRemove:boolean",
            "getter:AgentMcpServer#configuration:AgentMcpServerConfiguration | null | undefined",
            "getter:AgentMcpServer#displayName:string",
            "getter:AgentMcpServer#isAuthorized:boolean",
            "getter:AgentMcpServer#name:string",
            "getter:AgentMcpServer#origin:AgentResourceOrigin",
            "getter:AgentMcpServerConfiguration#authentication:" +
                "AgentMcpAuthentication | null | undefined",
            "getter:AgentMcpServerConfiguration#defaultToolApproval:" +
                "AgentMcpToolApproval | null | undefined",
            "getter:AgentMcpServerConfiguration#disabledTools:ReadonlyArray<string> | null | undefined",
            "getter:AgentMcpServerConfiguration#enabledTools:ReadonlyArray<string> | null | undefined",
            "getter:AgentMcpServerConfiguration#environmentId:string",
            "getter:AgentMcpServerConfiguration#isEnabled:boolean",
            "getter:AgentMcpServerConfiguration#isRequired:boolean",
            "getter:AgentMcpServerConfiguration#name:string",
            "getter:AgentMcpServerConfiguration#oauth:AgentMcpOauthConfiguration | null | undefined",
            "getter:AgentMcpServerConfiguration#oauthResource:string | null | undefined",
            "getter:AgentMcpServerConfiguration#omitToolsFrom:" +
                "ReadonlyArray<AgentMcpToolExposureSurface> | null | undefined",
            "getter:AgentMcpServerConfiguration#scopes:ReadonlyArray<string> | null | undefined",
            "getter:AgentMcpServerConfiguration#startupTimeoutSeconds:number | null | undefined",
            "getter:AgentMcpServerConfiguration#supportsParallelToolCalls:boolean",
            "getter:AgentMcpServerConfiguration#toolTimeoutSeconds:number | null | undefined",
            "getter:AgentMcpServerConfiguration#tools:" +
                "Readonly<Record<string, AgentMcpToolConfiguration>>",
            "getter:AgentMcpServerConfiguration#transport:AgentMcpTransport",
            "getter:AgentMcpStdioTransport#arguments:ReadonlyArray<string>",
            "getter:AgentMcpStdioTransport#command:string",
            "getter:AgentMcpStdioTransport#environment:" +
                "Readonly<Record<string, string>> | null | undefined",
            "getter:AgentMcpStdioTransport#forwardedEnvironment:" +
                "ReadonlyArray<AgentMcpEnvironmentVariable>",
            "getter:AgentMcpStdioTransport#workingDirectory:string | null | undefined",
            "getter:CodexAgent#mcpServers:CodexMcpServers",
            "getter:CodexMcpServers#isAvailable:boolean",
            "method:CodexMcpServers#add:(configuration: AgentMcpServerConfiguration, " +
                "signal?: AbortSignal | null | undefined): Promise<AgentMcpServer>",
            "method:CodexMcpServers#list:(signal?: AbortSignal | null | undefined): " +
                "Promise<ReadonlyArray<AgentMcpServer>>",
            "method:CodexMcpServers#remove:(server: AgentMcpServer, " +
                "signal?: AbortSignal | null | undefined): Promise<void>",
            "type:AgentMcpTransport:AgentMcpStdioTransport | AgentMcpHttpTransport",
        ).sorted().also { assertEquals(49, it.size) }

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
class:AgentConnector
class:AgentConversationSummary
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
class:CodexConnectors
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
constructor:AgentConnector#(id: string, name: string, description?: string, installUrl?: string | null | undefined, isAccessible?: boolean, isEnabled?: boolean, pluginNames?: ReadonlyArray<string>)
constructor:AgentConversationSummary#(conversationId: string, title: string, updatedAtEpochSeconds: bigint)
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
getter:AgentConnector#description:string
getter:AgentConnector#id:string
getter:AgentConnector#installUrl:string | null | undefined
getter:AgentConnector#isAccessible:boolean
getter:AgentConnector#isEnabled:boolean
getter:AgentConnector#name:string
getter:AgentConnector#pluginNames:ReadonlyArray<string>
getter:AgentConversationSummary#conversationId:string
getter:AgentConversationSummary#title:string
getter:AgentConversationSummary#updatedAtEpochSeconds:bigint
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
getter:CodexAgent#connectors:CodexConnectors
getter:CodexAgent#workspace:CodexWorkspace
getter:CodexAuthentication#isAuthenticated:boolean
getter:CodexAuthentication#isAuthenticating:boolean
getter:CodexAuthentication#state:CodexAuthenticationState
getter:CodexAuthenticationState#deviceUserCode:string | null | undefined
getter:CodexAuthenticationState#deviceVerificationUrl:string | null | undefined
getter:CodexAuthenticationState#failure:CodexFailure | null | undefined
getter:CodexAuthenticationState#pendingSignInUrl:string | null | undefined
getter:CodexAuthenticationState#status:CodexAuthenticationStatus
getter:CodexConnectors#isAvailable:boolean
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
method:CodexAgent#listConversations:(signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConversationSummary>>
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
method:CodexConnectors#list:(forceReload?: boolean, signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConnector>>
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

        private val MODELS_PUBLIC_SYMBOLS = """
class:AgentModel
class:AgentServiceTier
class:CodexModels
constructor:AgentModel#(id: string, displayName: string, description: string, supportedEfforts: ReadonlyArray<string>, defaultEffort: string, isDefault: boolean, serviceTiers?: ReadonlyArray<AgentServiceTier>, defaultServiceTier?: string | null | undefined)
constructor:AgentServiceTier#(id: string, name: string, description: string)
getter:AgentModel#defaultEffort:string
getter:AgentModel#defaultServiceTier:string | null | undefined
getter:AgentModel#description:string
getter:AgentModel#displayName:string
getter:AgentModel#id:string
getter:AgentModel#isDefault:boolean
getter:AgentModel#serviceTiers:ReadonlyArray<AgentServiceTier>
getter:AgentModel#supportedEfforts:ReadonlyArray<string>
getter:AgentServiceTier#description:string
getter:AgentServiceTier#id:string
getter:AgentServiceTier#name:string
getter:CodexAgent#models:CodexModels
method:CodexModels#list:(signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentModel>>
method:CodexModels#resolve:(resolution?: AgentResolution, signal?: AbortSignal | null | undefined): Promise<AgentModel>
method:CodexModels#resolveEffort:(model: AgentModel, resolution?: AgentResolution, signal?: AbortSignal | null | undefined): Promise<string>
method:CodexModels#resolveServiceTier:(model: AgentModel, resolution?: AgentResolution, signal?: AbortSignal | null | undefined): Promise<AgentServiceTier | null | undefined>
""".trimIndent()

        private val SKILLS_PUBLIC_SYMBOLS = """
class:AgentSkill
class:AgentSkillCatalog
class:AgentSkillChunk
class:CodexSkills
constructor:AgentSkill#(name: string, displayName: string, description: string, path: string, scope: AgentSkillScope, isEnabled: boolean, brandColor?: string | null | undefined, dependencies?: ReadonlyArray<string>, canUninstall?: boolean, origin?: AgentResourceOrigin)
constructor:AgentSkillCatalog#(skills: ReadonlyArray<AgentSkill>, errors?: ReadonlyArray<string>)
constructor:AgentSkillChunk#(content: string, nextOffset: bigint | null | undefined, totalBytes: bigint)
getter:AgentSkill#brandColor:string | null | undefined
getter:AgentSkill#canUninstall:boolean
getter:AgentSkill#dependencies:ReadonlyArray<string>
getter:AgentSkill#description:string
getter:AgentSkill#displayName:string
getter:AgentSkill#isEnabled:boolean
getter:AgentSkill#name:string
getter:AgentSkill#origin:AgentResourceOrigin
getter:AgentSkill#path:string
getter:AgentSkill#scope:AgentSkillScope
getter:AgentSkillCatalog#errors:ReadonlyArray<string>
getter:AgentSkillCatalog#skills:ReadonlyArray<AgentSkill>
getter:AgentSkillChunk#content:string
getter:AgentSkillChunk#nextOffset:bigint | null | undefined
getter:AgentSkillChunk#totalBytes:bigint
getter:CodexAgent#skills:CodexSkills
getter:CodexSkills#isAvailable:boolean
method:CodexSkills#install:(directory: string, scope: AgentInstallationScope, signal?: AbortSignal | null | undefined): Promise<AgentSkill>
method:CodexSkills#list:(forceReload?: boolean, signal?: AbortSignal | null | undefined): Promise<AgentSkillCatalog>
method:CodexSkills#read:(path: string, offset?: bigint, signal?: AbortSignal | null | undefined): Promise<AgentSkillChunk>
method:CodexSkills#uninstall:(skill: AgentSkill, signal?: AbortSignal | null | undefined): Promise<void>
""".trimIndent()

        private val D043_PUBLIC_SYMBOLS = """
class:AgentPluginInvocation
class:AgentSkillInvocation
constructor:AgentPluginInvocation#(name: string, uri: string)
constructor:AgentSkillInvocation#(name: string, path: string)
function:agentCapabilityDisplayLabel:(capability: AgentCapability): string
function:agentCapabilityIcon:(capability: AgentCapability): string | null | undefined
function:agentCapabilityId:(capability: AgentCapability): string
function:agentCapabilityPromptLabel:(capability: AgentCapability): string
getter:AgentPluginInvocation#key:string
getter:AgentPluginInvocation#name:string
getter:AgentPluginInvocation#uri:string
getter:AgentSkillInvocation#key:string
getter:AgentSkillInvocation#name:string
getter:AgentSkillInvocation#path:string
getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>
getter:CodexMessage#collaborationMode:AgentCollaborationMode
getter:CodexMessage#invocations:ReadonlyArray<AgentInvocation>
type:AgentInvocation:AgentPluginInvocation | AgentSkillInvocation
""".trimIndent()
    }
}
