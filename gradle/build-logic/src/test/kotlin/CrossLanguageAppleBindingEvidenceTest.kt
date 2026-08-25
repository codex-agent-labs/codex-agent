import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.tasks.CacheableTask
import org.gradle.testfixtures.ProjectBuilder

class CrossLanguageAppleBindingEvidenceTest {
    @Test
    fun `observes six independent claims and 550 explicit gaps per Apple language`() {
        val fixture = fixture()
        val report = fixture.derive()

        assertEquals(1, report.releaseInt("schemaVersion"))
        assertEquals(APPLE_BINDING_EVIDENCE_PROTOCOL, report.releaseString("protocol"))
        assertEquals("observed", report.releaseString("result"))
        assertFalse("receipt" in report)
        assertFalse("parity" in report)
        val languages = report.releaseArray("languages").map { it as JsonObject }
        assertEquals(listOf("objective-c", "swift"), languages.map { it.releaseString("language") })
        languages.forEach { language ->
            assertEquals(8, language.releaseArray("publicSymbols").size)
            assertEquals(6, language.releaseArray("referencedSymbols").size)
            assertEquals(6, language.releaseArray("claims").size)
            assertTrue(language.releaseArray("exclusions").isEmpty())
            assertEquals(550, language.releaseArray("missingCapabilityKeys").size)
            assertEquals(
                fixture.capabilities,
                language.releaseArray("claims").map { (it as JsonObject).releaseString("canonicalKey") },
            )
            val behaviorTest = if (language.releaseString("language") == "swift") {
                SWIFT_FAILURE_TEST
            } else {
                OBJECTIVE_C_FAILURE_TEST
            }
            assertTrue(language.releaseArray("claims").all {
                val claim = it as JsonObject
                claim.releaseString("behaviorTest") == behaviorTest &&
                    claim.releaseString("publicSymbol") == claim.releaseString("compilerReference")
            })
        }
    }

    @Test
    fun `fails closed on canonical surface reference claim artifact target and XCTest drift`() {
        val fixture = fixture()
        val compiler = fixture.compiler
        val surface = compiler.releaseObject("surface")
        val swift = surface.releaseArray("swift")
        val changedSwift = JsonArray(swift.mapIndexed { index, value ->
            if (index == 2) JsonObject((value as JsonObject) + ("accessLevel" to JsonPrimitive("public"))) else value
        })
        val surfaceDrift = compiler.withObject("surface", JsonObject(surface + mapOf(
            "swift" to changedSwift,
            "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changedSwift)),
        )))
        val signatureDrift = compiler.surfaceDrift(
            "swift", 1, "declaration", JsonPrimitive("init(code: String, message: String)"),
        )
        val typeDrift = compiler.surfaceDrift(
            "swift", 2, "typeIdentifiers", strings(listOf("s:Si")),
        )
        val readonlyDrift = compiler.surfaceDrift(
            "objectiveC", 2, "declaration", JsonPrimitive("@property (readwrite) NSString * code;"),
        )
        val selectorDrift = compiler.surfaceDrift(
            "objectiveC", 1, "title", JsonPrimitive("initWithMessage:code:isRecoverable:"),
        )
        val missingSurface = compiler.withObject("surface", run {
            val reduced = JsonArray(swift.dropLast(1))
            JsonObject(surface + mapOf(
                "swift" to reduced,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(reduced)),
            ))
        })
        val duplicateSurface = compiler.withObject("surface", run {
            val duplicated = JsonArray(swift + swift.last())
            JsonObject(surface + mapOf(
                "swift" to duplicated,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(duplicated)),
            ))
        })
        val references = compiler.releaseObject("references")
        val missingReference = JsonArray(references.releaseArray("objectiveC").dropLast(1))
        val referenceDrift = compiler.withObject("references", JsonObject(references + mapOf(
            "objectiveC" to missingReference,
            "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(missingReference)),
        )))
        val swiftReferenceTypeDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("swift").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == ACCEPT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("\$sSo31CodexAgentAgentApprovalDecisionCD")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "swift" to changed,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val qualifierDrift = compiler.withObject("references", run {
            val changed = JsonArray(references.releaseArray("objectiveC").map { value ->
                val reference = value as JsonObject
                if (reference.releaseString("precise") == ACCEPT_USR) {
                    JsonObject(reference + ("valueType" to JsonPrimitive("CodexAgentAgentApprovalDecision *")))
                } else {
                    reference
                }
            })
            JsonObject(references + mapOf(
                "objectiveC" to changed,
                "objectiveCSha256" to JsonPrimitive(appleCompilerJsonDigest(changed)),
            ))
        })
        val claims = compiler.releaseArray("claims")
        val first = claims.first() as JsonObject
        val swappedClaim = compiler.withArray("claims", JsonArray(listOf(
            JsonObject(first + ("swiftUsr" to JsonPrimitive(CODE_USR))),
        ) + claims.drop(1)))
        val missingClaim = compiler.withArray("claims", JsonArray(claims.dropLast(1)))
        val duplicateClaim = compiler.withArray("claims", JsonArray(claims + claims.first()))
        val wrongOwnerClaim = compiler.withArray("claims", JsonArray(listOf(
            JsonObject(first + ("canonicalKey" to JsonPrimitive(
                first.releaseString("canonicalKey").replace(APPROVAL_CANONICAL_OWNER, "sample/Foreign"),
            ))),
        ) + claims.drop(1)))
        val cdx = compiler.withObject("surface", run {
            val extra = JsonArray(swift + symbol(
                "c:objc(cs)CDXFailure", "swift", "swift.class", listOf("CDXFailure"), "CDXFailure", "public",
                "class CDXFailure",
            ))
            JsonObject(surface + mapOf(
                "swift" to extra,
                "swiftSha256" to JsonPrimitive(appleCompilerJsonDigest(extra)),
            ))
        })
        val wrongArtifact = compiler.withObject(
            "artifacts",
            JsonObject(compiler.releaseObject("artifacts") + ("swiftConsumerSha256" to JsonPrimitive(SHA_F))),
        )
        val duplicateTarget = compiler.withArray(
            "targets",
            JsonArray(compiler.releaseArray("targets") + compiler.releaseArray("targets").first()),
        )
        val failedTests = fixture.xctest.withArray("tests", JsonArray(
            fixture.xctest.releaseArray("tests").mapIndexed { index, value ->
                if (index == 1) JsonObject((value as JsonObject) + ("status" to JsonPrimitive("Failed"))) else value
            },
        ))
        val renamedTests = fixture.xctest.withArray("tests", JsonArray(
            fixture.xctest.releaseArray("tests").mapIndexed { index, value ->
                if (index == 1) JsonObject(
                    (value as JsonObject) + ("identifier" to JsonPrimitive("Other/testChanged()")),
                ) else value
            },
        ))
        val futureCanonical = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) +
                canonicalProperty("future", "kotlin/String!!")).sorted(),
        )
        val overloadedCanonical = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) +
                canonicalConstructor().replace("{}[0]", "{}[1]")).sorted(),
        )
        val futureDecision = fixture.canonical.copy(
            memberKeys = (fixture.canonical.memberKeys.dropLast(1) + canonicalApprovalDecision("FUTURE")).sorted(),
        )

        listOf(
            surfaceDrift, signatureDrift, typeDrift, readonlyDrift, selectorDrift, missingSurface,
            duplicateSurface, referenceDrift, swiftReferenceTypeDrift, qualifierDrift, swappedClaim,
            missingClaim, duplicateClaim, wrongOwnerClaim,
            cdx, wrongArtifact, duplicateTarget,
        ).forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(compiler = drift) }
        }
        listOf(failedTests, renamedTests).forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(xctest = drift) }
        }
        listOf(futureCanonical, overloadedCanonical, futureDecision).forEach { drift ->
            assertFailsWith<IllegalStateException> { fixture.derive(canonical = drift) }
        }
        assertFailsWith<IllegalStateException> {
            fixture.derive(digests = fixture.digests.copy(xcresultSha256 = SHA_B))
        }
    }

    @Test
    fun `task is cacheable and deletes stale output before malformed inputs`() = withRoot { root ->
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "appleBindingEvidence",
            GenerateAppleBindingEvidenceTask::class.java,
        )
        val missing = root.resolve("missing")
        task.canonicalApiReport.set(missing.resolve("canonical-api.json"))
        task.canonicalCoverageReceipt.set(missing.resolve("canonical-coverage.json"))
        task.compilerEvidence.set(missing.resolve("compiler-evidence.json"))
        task.xcframeworkDirectory.set(missing.resolve("CodexAgent.xcframework"))
        task.swiftConsumer.set(missing.resolve("consumer.swift"))
        task.objectiveCConsumer.set(missing.resolve("consumer.m"))
        task.xctestEvidence.set(missing.resolve("xctest.json"))
        task.xcresultDirectory.set(missing.resolve("tests.xcresult"))
        val output = root.resolve("binding-evidence.json").apply { writeText("stale observed evidence") }
        task.evidenceFile.set(output)

        assertTrue(GenerateAppleBindingEvidenceTask::class.java.isAnnotationPresent(CacheableTask::class.java))
        assertFailsWith<IllegalStateException> { task.generate() }
        assertFalse(output.exists())
    }

    @Test
    fun `iOS plugin registers only observed Apple evidence with stale invalidation`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("build.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val registration = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts",
        ).readText()

        listOf(
            "invalidateCodexAgentAppleBindingEvidence",
            "generateCodexAgentAppleBindingEvidence",
            "GenerateAppleBindingEvidenceTask",
            "reports/cross-language-api/apple/binding-evidence.json",
            "appleCompilerEvidence.flatMap(AppleCompilerEvidenceTask::evidenceFile)",
            "VerifySwiftAuthenticationTestsTask::summaryFile",
            "VerifySwiftAuthenticationTestsTask::resultBundleDirectory",
        ).forEach { expected -> assertTrue(expected in registration) }
        assertFalse("swift-parity.json" in registration)
        assertFalse("objective-c-parity.json" in registration)
    }

    private data class Fixture(
        val canonical: CrossLanguageCanonicalApiEvidence,
        val compiler: JsonObject,
        val xctest: JsonObject,
        val digests: AppleBindingInputDigests,
    ) {
        val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)

        fun derive(
            canonical: CrossLanguageCanonicalApiEvidence = this.canonical,
            compiler: JsonObject = this.compiler,
            xctest: JsonObject = this.xctest,
            digests: AppleBindingInputDigests = this.digests,
        ) = deriveCrossLanguageAppleBindingEvidence(canonical, compiler, xctest, digests)
    }

    private fun fixture(): Fixture {
        val members = (listOf(
            canonicalConstructor(),
            canonicalProperty("code", "kotlin/String!!"),
            canonicalProperty("isRecoverable", "kotlin/Boolean!!"),
            canonicalProperty("message", "kotlin/String!!"),
            canonicalApprovalDecision("ACCEPT"),
            canonicalApprovalDecision("DECLINE"),
        ) + (0 until 550).map { index ->
            "common|owner=sample/Owner${index.toString().padStart(3, '0')}|kind=property|" +
                "abi=sample/Owner$index.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!"
        }).sorted()
        val canonical = CrossLanguageCanonicalApiEvidence(
            members,
            CrossLanguageBindingCanonicalIdentity(SHA_A, SHA_B),
            mapOf("native" to SHA_C, "wasm" to SHA_D, "jvm-classes" to SHA_E),
            SHA_D,
            SHA_E,
            setOf("canonical/test"),
        )
        val capabilities = appleBindingCapabilityKeys(members)
        val targetDigests = linkedMapOf(
            "ios-arm64" to AppleBindingTargetDigests(SHA_A, SHA_B, SHA_C, SHA_D),
            "ios-arm64-simulator" to AppleBindingTargetDigests(SHA_E, SHA_F, SHA_C, SHA_D),
        )
        val swift = swiftSurface()
        val objectiveC = objectiveCSurface()
        val swiftReferences = swiftReferences()
        val objectiveCReferences = objectiveCReferences()
        val compiler = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive(APPLE_COMPILER_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed"))
            put("moduleName", JsonPrimitive("CodexAgent"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(SHA_A))
                put("coverageReceiptSha256", JsonPrimitive(SHA_B))
                put("nativeTargetSha256", JsonPrimitive(SHA_C))
                put("capabilities", strings(capabilities))
            })
            put("toolchain", buildJsonObject {
                put("xcodeVersion", JsonPrimitive("26.6"))
                put("xcodeBuild", JsonPrimitive("17F113"))
                put("swiftVersion", JsonPrimitive("6.3.3"))
                put("clangVersion", JsonPrimitive("Apple clang version 21.0.0"))
            })
            put("artifacts", buildJsonObject {
                put("xcframeworkSha256", JsonPrimitive(SHA_A))
                put("swiftConsumerSha256", JsonPrimitive(SHA_B))
                put("objectiveCConsumerSha256", JsonPrimitive(SHA_C))
            })
            put("targets", buildJsonArray {
                add(target("ios-arm64", "iphoneos", "arm64-apple-ios15.0", targetDigests.getValue("ios-arm64")))
                add(target(
                    "ios-arm64-simulator", "iphonesimulator", "arm64-apple-ios15.0-simulator",
                    targetDigests.getValue("ios-arm64-simulator"),
                ))
            })
            put("surface", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swift)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveC)))
                put("swift", swift)
                put("objectiveC", objectiveC)
            })
            put("references", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftReferences)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCReferences)))
                put("swift", swiftReferences)
                put("objectiveC", objectiveCReferences)
            })
            put("claims", buildJsonArray {
                capabilities.forEach { capability ->
                    val usr = usr(capability)
                    add(buildJsonObject {
                        put("canonicalKey", JsonPrimitive(capability))
                        put("swiftUsr", JsonPrimitive(usr))
                        put("objectiveCUsr", JsonPrimitive(usr))
                    })
                }
            })
        }
        val tests = listOf(
            "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
            SWIFT_FAILURE_TEST,
            OBJECTIVE_C_FAILURE_TEST,
            "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
        ).sorted()
        val xctest = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive("codex-agent-apple-xctest-v1"))
            put("result", JsonPrimitive("passed"))
            put("totalTestCount", JsonPrimitive(4))
            put("failedTests", JsonPrimitive(0))
            put("xcresultSha256", JsonPrimitive(SHA_D))
            put("tests", buildJsonArray { tests.forEach { test -> add(buildJsonObject {
                put("identifier", JsonPrimitive(test)); put("status", JsonPrimitive("Passed"))
            }) } })
        }
        return Fixture(
            canonical,
            compiler,
            xctest,
            AppleBindingInputDigests(SHA_E, SHA_A, SHA_B, SHA_C, SHA_F, SHA_D, targetDigests),
        )
    }

    private fun swiftSurface() = JsonArray(listOf(
        symbol(OWNER, "swift", "swift.class", listOf("CodexFailure"), "CodexFailure", "public", "class CodexFailure"),
        symbol(
            CONSTRUCTOR, "swift", "swift.init", listOf("CodexFailure", "init(code:message:isRecoverable:)"),
            "init(code:message:isRecoverable:)", "public",
            "init(code: String, message: String, isRecoverable: Bool)",
            listOf("s:SS", "s:SS", "s:Sb"),
            listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
        ),
        symbol(CODE_USR, "swift", "swift.property", listOf("CodexFailure", "code"), "code", "open",
            "var code: String { get }", listOf("s:SS")),
        symbol(RECOVERABLE_USR, "swift", "swift.property", listOf("CodexFailure", "isRecoverable"),
            "isRecoverable", "open", "var isRecoverable: Bool { get }", listOf("s:Sb")),
        symbol(MESSAGE_USR, "swift", "swift.property", listOf("CodexFailure", "message"), "message", "open",
            "var message: String { get }", listOf("s:SS")),
        symbol(APPROVAL_OWNER, "swift", "swift.class", listOf("AgentApprovalDecision"),
            "AgentApprovalDecision", "public", "class AgentApprovalDecision"),
        symbol(ACCEPT_USR, "swift", "swift.type.property", listOf("AgentApprovalDecision", "accept"),
            "accept", "open", "class var accept: AgentApprovalDecision { get }", listOf(APPROVAL_OWNER)),
        symbol(DECLINE_USR, "swift", "swift.type.property", listOf("AgentApprovalDecision", "decline"),
            "decline", "open", "class var decline: AgentApprovalDecision { get }", listOf(APPROVAL_OWNER)),
    ).sortedBy { it.releaseString("precise") })

    private fun objectiveCSurface() = JsonArray(listOf(
        symbol(OWNER, "objective-c", "objective-c.class", listOf("CodexAgentCodexFailure"),
            "CodexAgentCodexFailure", "public", "@interface CodexAgentCodexFailure : CodexAgentBase",
            listOf("c:objc(cs)CodexAgentBase")),
        symbol(
            CONSTRUCTOR, "objective-c", "objective-c.method",
            listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
            "initWithCode:message:isRecoverable:", "public",
            "- (instancetype) initWithCode:(NSString *) code message:(NSString *) message " +
                "isRecoverable:(BOOL) isRecoverable;",
            listOf("c:objc(cs)NSString", "c:objc(cs)NSString", "c:@T@BOOL"),
            listOf("code" to "(NSString *) code", "message" to "(NSString *) message",
                "isRecoverable" to "(BOOL) isRecoverable"),
            "instancetype",
        ),
        symbol(CODE_USR, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "code"),
            "code", "public", "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString")),
        symbol(RECOVERABLE_USR, "objective-c", "objective-c.property",
            listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
            "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL")),
        symbol(MESSAGE_USR, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "message"),
            "message", "public", "@property (readonly) NSString * message;", listOf("c:objc(cs)NSString")),
        symbol(APPROVAL_OWNER, "objective-c", "objective-c.class", listOf("CodexAgentAgentApprovalDecision"),
            "CodexAgentAgentApprovalDecision", "public",
            "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum")),
        symbol(ACCEPT_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
            "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;", listOf(APPROVAL_OWNER)),
        symbol(DECLINE_USR, "objective-c", "objective-c.type.property",
            listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
            "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;", listOf(APPROVAL_OWNER)),
    ).sortedBy { it.releaseString("precise") })

    private fun swiftReferences() = JsonArray(listOf(
        reference(CONSTRUCTOR, "declref_expr", "init", null, "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD"),
        reference(CODE_USR, "member_ref_expr", "code", null, "\$sSSD"),
        reference(RECOVERABLE_USR, "member_ref_expr", "isRecoverable", null, "\$sSbD"),
        reference(MESSAGE_USR, "member_ref_expr", "message", null, "\$sSSD"),
        reference(ACCEPT_USR, "member_ref_expr", "accept", null, APPROVAL_SWIFT_TYPE),
        reference(DECLINE_USR, "member_ref_expr", "decline", null, APPROVAL_SWIFT_TYPE),
    ).sortedBy { it.releaseString("precise") })

    private fun objectiveCReferences() = JsonArray(listOf(
        reference(CONSTRUCTOR, "ObjCMessageExpr", "initWithCode:message:isRecoverable:",
            "CodexAgentCodexFailure", "CodexAgentCodexFailure *", listOf("NSString *", "NSString *", "BOOL")),
        reference(CODE_USR, "ObjCPropertyRefExpr", "code", "CodexAgentCodexFailure *", "<pseudo-object type>"),
        reference(RECOVERABLE_USR, "ObjCPropertyRefExpr", "isRecoverable", "CodexAgentCodexFailure *",
            "<pseudo-object type>"),
        reference(MESSAGE_USR, "ObjCPropertyRefExpr", "message", "CodexAgentCodexFailure *", "<pseudo-object type>"),
        reference(ACCEPT_USR, "ObjCMessageExpr", "accept", "CodexAgentAgentApprovalDecision",
            "CodexAgentAgentApprovalDecision * _Nonnull"),
        reference(DECLINE_USR, "ObjCMessageExpr", "decline", "CodexAgentAgentApprovalDecision",
            "CodexAgentAgentApprovalDecision * _Nonnull"),
    ).sortedBy { it.releaseString("precise") })

    private fun symbol(
        precise: String,
        language: String,
        kind: String,
        path: List<String>,
        title: String,
        access: String,
        declaration: String,
        types: List<String> = emptyList(),
        parameters: List<Pair<String, String>> = emptyList(),
        returns: String? = null,
    ) = buildJsonObject {
        put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(language))
        put("kind", JsonPrimitive(kind)); put("path", strings(path)); put("title", JsonPrimitive(title))
        put("accessLevel", JsonPrimitive(access)); put("declaration", JsonPrimitive(declaration))
        put("typeIdentifiers", strings(types)); put("parameters", buildJsonArray {
            parameters.forEach { (name, value) -> add(buildJsonObject {
                put("name", JsonPrimitive(name)); put("declaration", JsonPrimitive(value))
            }) }
        })
        put("returns", returns?.let(::JsonPrimitive) ?: JsonNull)
    }

    private fun reference(
        precise: String,
        kind: String,
        name: String,
        receiverType: String?,
        valueType: String,
        argumentTypes: List<String> = emptyList(),
    ) = buildJsonObject {
        put("precise", JsonPrimitive(precise)); put("kind", JsonPrimitive(kind)); put("name", JsonPrimitive(name))
        put("receiverType", receiverType?.let(::JsonPrimitive) ?: JsonNull)
        put("valueType", JsonPrimitive(valueType)); put("argumentTypes", strings(argumentTypes))
    }

    private fun target(name: String, sdk: String, triple: String, digests: AppleBindingTargetDigests) =
        buildJsonObject {
            put("name", JsonPrimitive(name)); put("sdk", JsonPrimitive(sdk)); put("sdkVersion", JsonPrimitive("26.5"))
            put("targetTriple", JsonPrimitive(triple)); put("frameworkSha256", JsonPrimitive(digests.frameworkSha256))
            put("binarySha256", JsonPrimitive(digests.binarySha256)); put("headerSha256", JsonPrimitive(digests.headerSha256))
            put("moduleMapSha256", JsonPrimitive(digests.moduleMapSha256))
        }

    private fun usr(capability: String) = when {
        "|kind=constructor|" in capability -> CONSTRUCTOR
        "|{}code[0]|" in capability -> CODE_USR
        "|{}isRecoverable[0]|" in capability -> RECOVERABLE_USR
        "|{}message[0]|" in capability -> MESSAGE_USR
        ".ACCEPT|null[0]" in capability -> ACCEPT_USR
        else -> DECLINE_USR
    }

    private fun canonicalConstructor(): String =
        "common|owner=$CANONICAL_OWNER|kind=constructor|abi=$CANONICAL_OWNER.<init>|" +
            "<init>(kotlin.String;kotlin.String;kotlin.Boolean){}[0]|return=$CANONICAL_OWNER|suspend=false|" +
            "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/String!!:default=false:vararg=false," +
            "REGULAR:kotlin/Boolean!!:default=false:vararg=false]"

    private fun canonicalProperty(name: String, type: String): String =
        "common|owner=$CANONICAL_OWNER|kind=property|abi=$CANONICAL_OWNER.$name|{}$name[0]|" +
            "propertyKind=VAL|type=$type"

    private fun canonicalApprovalDecision(name: String): String =
        "common|owner=$APPROVAL_CANONICAL_OWNER|kind=enum-entry|" +
            "abi=$APPROVAL_CANONICAL_OWNER.$name|null[0]"

    private fun strings(values: Iterable<String>) = buildJsonArray { values.forEach { add(JsonPrimitive(it)) } }
    private fun JsonObject.withObject(name: String, value: JsonObject) = JsonObject(this + (name to value))
    private fun JsonObject.withArray(name: String, value: JsonArray) = JsonObject(this + (name to value))
    private fun JsonObject.surfaceDrift(
        language: String,
        index: Int,
        field: String,
        value: JsonElement,
    ): JsonObject {
        val surface = releaseObject("surface")
        val changed = JsonArray(surface.releaseArray(language).mapIndexed { itemIndex, item ->
            if (itemIndex == index) JsonObject((item as JsonObject) + (field to value)) else item
        })
        val digestField = if (language == "swift") "swiftSha256" else "objectiveCSha256"
        return withObject("surface", JsonObject(surface + mapOf(
            language to changed,
            digestField to JsonPrimitive(appleCompilerJsonDigest(changed)),
        )))
    }

    private fun withRoot(block: (File) -> Unit) {
        val root = createTempDirectory("apple-binding-evidence").toFile()
        try {
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }

    private companion object {
        const val CANONICAL_OWNER = "io.github.codex_agent_labs.codexmobile.agent/CodexFailure"
        const val OWNER = "c:objc(cs)CodexAgentCodexFailure"
        const val CONSTRUCTOR = "$OWNER(im)initWithCode:message:isRecoverable:"
        const val CODE_USR = "$OWNER(py)code"
        const val RECOVERABLE_USR = "$OWNER(py)isRecoverable"
        const val MESSAGE_USR = "$OWNER(py)message"
        const val APPROVAL_CANONICAL_OWNER =
            "io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision"
        const val APPROVAL_OWNER = "c:objc(cs)CodexAgentAgentApprovalDecision"
        const val ACCEPT_USR = "$APPROVAL_OWNER(cpy)accept"
        const val DECLINE_USR = "$APPROVAL_OWNER(cpy)decline"
        const val APPROVAL_SWIFT_TYPE = "\$sSo010CodexAgentB16ApprovalDecisionCD"
        const val SWIFT_FAILURE_TEST =
            "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()"
        const val OBJECTIVE_C_FAILURE_TEST =
            "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()"
        val SHA_A = "a".repeat(64)
        val SHA_B = "b".repeat(64)
        val SHA_C = "c".repeat(64)
        val SHA_D = "d".repeat(64)
        val SHA_E = "e".repeat(64)
        val SHA_F = "f".repeat(64)
    }
}
