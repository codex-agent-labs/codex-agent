import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

internal const val APPLE_BINDING_EVIDENCE_PROTOCOL = "codex-agent-apple-binding-evidence-v1"
internal const val APPLE_BINDING_CANONICAL_CAPABILITY_COUNT = 556

private const val appleXCTestProtocol = "codex-agent-apple-xctest-v1"
private const val appleFailureConstructorUsr =
    "$APPLE_CODEX_FAILURE_OWNER_USR(im)initWithCode:message:isRecoverable:"
private const val appleFailureCodeUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)code"
private const val appleFailureRecoverableUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)isRecoverable"
private const val appleFailureMessageUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)message"
private const val appleApprovalAcceptUsr = "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)accept"
private const val appleApprovalDeclineUsr = "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)decline"
private const val swiftFailureTest =
    "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()"
private const val objectiveCFailureTest =
    "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()"

private val expectedAppleTests = listOf(
    "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
    swiftFailureTest,
    objectiveCFailureTest,
    "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
).sorted()

internal data class AppleBindingTargetDigests(
    val frameworkSha256: String,
    val binarySha256: String,
    val headerSha256: String,
    val moduleMapSha256: String,
)

internal data class AppleBindingInputDigests(
    val compilerEvidenceSha256: String,
    val xcframeworkSha256: String,
    val swiftConsumerSha256: String,
    val objectiveCConsumerSha256: String,
    val xctestEvidenceSha256: String,
    val xcresultSha256: String,
    val targets: Map<String, AppleBindingTargetDigests>,
)

private data class AppleCompilerClaim(
    val canonicalKey: String,
    val swiftUsr: String,
    val objectiveCUsr: String,
)

internal fun deriveCrossLanguageAppleBindingEvidence(
    canonical: CrossLanguageCanonicalApiEvidence,
    compilerEvidence: JsonObject,
    xctestEvidence: JsonObject,
    digests: AppleBindingInputDigests,
): JsonObject {
    listOf(
        "compiler evidence" to digests.compilerEvidenceSha256,
        "XCFramework" to digests.xcframeworkSha256,
        "Swift consumer" to digests.swiftConsumerSha256,
        "Objective-C consumer" to digests.objectiveCConsumerSha256,
        "XCTest evidence" to digests.xctestEvidenceSha256,
        "xcresult" to digests.xcresultSha256,
    ).forEach { (label, digest) -> digest.appleSha256(label) }
    digests.targets.forEach { (target, values) ->
        listOf(
            "framework" to values.frameworkSha256,
            "binary" to values.binarySha256,
            "header" to values.headerSha256,
            "module map" to values.moduleMapSha256,
        ).forEach { (label, digest) -> digest.appleSha256("$target $label") }
    }
    check(canonical.memberKeys.size == APPLE_BINDING_CANONICAL_CAPABILITY_COUNT) {
        "Apple binding evidence requires exactly $APPLE_BINDING_CANONICAL_CAPABILITY_COUNT canonical capabilities"
    }
    check(canonical.memberKeys == canonical.memberKeys.distinct().sorted()) {
        "Apple binding canonical capability inventory is duplicated or unsorted"
    }
    canonical.canonical.apiReportSha256.appleSha256("canonical API report")
    canonical.canonical.coverageReceiptSha256.appleSha256("canonical coverage receipt")
    canonical.targetSha256.getValue("native").appleSha256("canonical native target")
    val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)
    check(capabilities.size == 6) { "Apple binding capability count changed" }
    val usrByCapability = capabilities.associateWith(::appleBindingUsr)

    compilerEvidence.appleKeys(
        "Apple compiler evidence",
        "schemaVersion", "protocol", "result", "moduleName", "canonical", "toolchain", "artifacts",
        "targets", "surface", "references", "claims",
    )
    check(compilerEvidence.appleInt("schemaVersion") == 1) { "Unsupported Apple compiler evidence schema" }
    check(compilerEvidence.appleString("protocol") == APPLE_COMPILER_EVIDENCE_PROTOCOL) {
        "Unsupported Apple compiler evidence protocol"
    }
    check(compilerEvidence.appleString("result") == "observed") { "Apple compiler evidence was not observed" }
    check(compilerEvidence.appleString("moduleName") == "CodexAgent") { "Apple compiler module changed" }

    val compilerCanonical = compilerEvidence.appleObject("canonical").also {
        it.appleKeys(
            "Apple compiler canonical identity",
            "apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "capabilities",
        )
    }
    check(compilerCanonical.appleSha256("apiReportSha256") == canonical.canonical.apiReportSha256 &&
        compilerCanonical.appleSha256("coverageReceiptSha256") == canonical.canonical.coverageReceiptSha256 &&
        compilerCanonical.appleSha256("nativeTargetSha256") == canonical.targetSha256.getValue("native") &&
        compilerCanonical.appleStrings("capabilities") == capabilities
    ) { "Apple compiler evidence canonical identity changed" }

    compilerEvidence.appleObject("toolchain").also { toolchain ->
        toolchain.appleKeys(
            "Apple compiler toolchain", "xcodeVersion", "xcodeBuild", "swiftVersion", "clangVersion",
        )
        listOf("xcodeVersion", "xcodeBuild", "swiftVersion", "clangVersion").forEach { name ->
            toolchain.appleString(name).appleRecord("Apple compiler toolchain $name")
        }
    }
    val compilerArtifacts = compilerEvidence.appleObject("artifacts").also {
        it.appleKeys(
            "Apple compiler artifacts", "xcframeworkSha256", "swiftConsumerSha256", "objectiveCConsumerSha256",
        )
    }
    check(compilerArtifacts.appleSha256("xcframeworkSha256") == digests.xcframeworkSha256 &&
        compilerArtifacts.appleSha256("swiftConsumerSha256") == digests.swiftConsumerSha256 &&
        compilerArtifacts.appleSha256("objectiveCConsumerSha256") == digests.objectiveCConsumerSha256
    ) { "Apple compiler artifact identity changed" }

    validateAppleTargets(compilerEvidence.appleArray("targets"), digests.targets)
    val surfaces = compilerEvidence.appleObject("surface").also {
        it.appleKeys("Apple compiler surfaces", "swiftSha256", "objectiveCSha256", "swift", "objectiveC")
    }
    val swiftSurfaceJson = surfaces.appleArray("swift")
    val objectiveCSurfaceJson = surfaces.appleArray("objectiveC")
    check(surfaces.appleSha256("swiftSha256") == appleCompilerJsonDigest(swiftSurfaceJson) &&
        surfaces.appleSha256("objectiveCSha256") == appleCompilerJsonDigest(objectiveCSurfaceJson)
    ) { "Apple compiler surface digest changed" }
    val swiftSurface = swiftSurfaceJson.map { it.appleSymbol() }
    val objectiveCSurface = objectiveCSurfaceJson.map { it.appleSymbol() }
    check(swiftSurface == expectedSwiftAppleBindingSurface()) { "Swift Apple binding compiler surface changed" }
    check(objectiveCSurface == expectedObjectiveCAppleBindingSurface()) {
        "Objective-C Apple binding compiler surface changed"
    }

    val references = compilerEvidence.appleObject("references").also {
        it.appleKeys("Apple compiler references", "swiftSha256", "objectiveCSha256", "swift", "objectiveC")
    }
    val swiftReferencesJson = references.appleArray("swift")
    val objectiveCReferencesJson = references.appleArray("objectiveC")
    check(references.appleSha256("swiftSha256") == appleCompilerJsonDigest(swiftReferencesJson) &&
        references.appleSha256("objectiveCSha256") == appleCompilerJsonDigest(objectiveCReferencesJson)
    ) { "Apple compiler reference digest changed" }
    val swiftReferences = swiftReferencesJson.map { it.appleReference() }
    val objectiveCReferences = objectiveCReferencesJson.map { it.appleReference() }
    check(swiftReferences == expectedSwiftAppleBindingReferences()) {
        "Swift Apple binding compiler references changed"
    }
    check(objectiveCReferences == expectedObjectiveCAppleBindingReferences()) {
        "Objective-C Apple binding compiler references changed"
    }

    val compilerClaims = compilerEvidence.appleArray("claims").map { value ->
        val claim = value.appleObject("Apple compiler claim").also {
            it.appleKeys("Apple compiler claim", "canonicalKey", "swiftUsr", "objectiveCUsr")
        }
        AppleCompilerClaim(
            claim.appleString("canonicalKey"),
            claim.appleString("swiftUsr"),
            claim.appleString("objectiveCUsr"),
        )
    }
    val expectedClaims = capabilities.map { capability ->
        AppleCompilerClaim(capability, usrByCapability.getValue(capability), usrByCapability.getValue(capability))
    }
    check(compilerClaims == expectedClaims) { "Apple compiler claims changed" }

    validateAppleXCTestEvidence(xctestEvidence, digests.xcresultSha256)
    val missing = (canonical.memberKeys.toSet() - capabilities.toSet()).sorted()
    check(missing.size == 550) { "Apple partial binding gap count changed: ${missing.size}" }
    val swiftSymbols = swiftSurface.map(AppleCompilerSymbol::precise).sorted()
    val objectiveCSymbols = objectiveCSurface.map(AppleCompilerSymbol::precise).sorted()
    val swiftReferenced = swiftReferences.map(AppleCompilerReference::precise).sorted()
    val objectiveCReferenced = objectiveCReferences.map(AppleCompilerReference::precise).sorted()

    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("protocol", JsonPrimitive(APPLE_BINDING_EVIDENCE_PROTOCOL))
        put("result", JsonPrimitive("observed"))
        put("canonical", buildJsonObject {
            put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
            put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
            put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
            put("capabilityCount", JsonPrimitive(canonical.memberKeys.size))
        })
        put("artifacts", buildJsonObject {
            put("compilerEvidenceSha256", JsonPrimitive(digests.compilerEvidenceSha256))
            put("xcframeworkSha256", JsonPrimitive(digests.xcframeworkSha256))
            put("swiftConsumerSha256", JsonPrimitive(digests.swiftConsumerSha256))
            put("objectiveCConsumerSha256", JsonPrimitive(digests.objectiveCConsumerSha256))
            put("xctestEvidenceSha256", JsonPrimitive(digests.xctestEvidenceSha256))
            put("xcresultSha256", JsonPrimitive(digests.xcresultSha256))
        })
        put("languages", buildJsonArray {
            add(appleLanguageEvidence(
                "objective-c", objectiveCSymbols, objectiveCReferenced, capabilities,
                usrByCapability, objectiveCFailureTest, missing,
            ))
            add(appleLanguageEvidence(
                "swift", swiftSymbols, swiftReferenced, capabilities,
                usrByCapability, swiftFailureTest, missing,
            ))
        })
    }
}

private fun validateAppleTargets(
    values: JsonArray,
    actualDigests: Map<String, AppleBindingTargetDigests>,
) {
    val expectedTargets = linkedMapOf(
        "ios-arm64" to Pair("iphoneos", "arm64-apple-ios15.0"),
        "ios-arm64-simulator" to Pair("iphonesimulator", "arm64-apple-ios15.0-simulator"),
    )
    check(actualDigests.keys == expectedTargets.keys) { "Apple compiler target artifacts changed" }
    val targets = values.map { value ->
        val target = value.appleObject("Apple compiler target").also {
            it.appleKeys(
                "Apple compiler target", "name", "sdk", "sdkVersion", "targetTriple",
                "frameworkSha256", "binarySha256", "headerSha256", "moduleMapSha256",
            )
        }
        val name = target.appleString("name")
        val expected = expectedTargets[name] ?: error("Unexpected Apple compiler target: $name")
        check(target.appleString("sdk") == expected.first && target.appleString("targetTriple") == expected.second) {
            "Apple compiler target identity changed: $name"
        }
        check(target.appleString("sdkVersion").matches(Regex("[0-9]+(?:\\.[0-9]+)*"))) {
            "Apple compiler SDK version is invalid: $name"
        }
        val actual = actualDigests.getValue(name)
        check(target.appleSha256("frameworkSha256") == actual.frameworkSha256 &&
            target.appleSha256("binarySha256") == actual.binarySha256 &&
            target.appleSha256("headerSha256") == actual.headerSha256 &&
            target.appleSha256("moduleMapSha256") == actual.moduleMapSha256
        ) { "Apple compiler target artifact changed: $name" }
        name to actual
    }
    check(targets.map(Pair<String, AppleBindingTargetDigests>::first) == expectedTargets.keys.toList()) {
        "Apple compiler target inventory changed"
    }
    check(targets.map { it.second.headerSha256 }.distinct().size == 1 &&
        targets.map { it.second.moduleMapSha256 }.distinct().size == 1
    ) { "Apple compiler device and simulator interfaces differ" }
}

private fun validateAppleXCTestEvidence(evidence: JsonObject, xcresultSha256: String) {
    evidence.appleKeys(
        "Apple XCTest evidence",
        "schemaVersion", "protocol", "result", "totalTestCount", "failedTests", "xcresultSha256", "tests",
    )
    check(evidence.appleInt("schemaVersion") == 1 &&
        evidence.appleString("protocol") == appleXCTestProtocol &&
        evidence.appleString("result") == "passed" &&
        evidence.appleInt("totalTestCount") == expectedAppleTests.size &&
        evidence.appleInt("failedTests") == 0 &&
        evidence.appleSha256("xcresultSha256") == xcresultSha256
    ) { "Apple XCTest evidence identity or result changed" }
    val tests = evidence.appleArray("tests").map { value ->
        val test = value.appleObject("Apple XCTest result").also {
            it.appleKeys("Apple XCTest result", "identifier", "status")
        }
        test.appleString("identifier") to test.appleString("status")
    }
    check(tests == expectedAppleTests.map { it to "Passed" }) { "Apple XCTest inventory or status changed" }
}

private fun appleLanguageEvidence(
    language: String,
    publicSymbols: List<String>,
    referencedSymbols: List<String>,
    capabilities: List<String>,
    usrByCapability: Map<String, String>,
    behaviorTest: String,
    missing: List<String>,
) = buildJsonObject {
    check(publicSymbols.size == 8 && referencedSymbols.size == 6 &&
        referencedSymbols.toSet() == publicSymbols.toSet() -
            setOf(APPLE_CODEX_FAILURE_OWNER_USR, APPLE_APPROVAL_DECISION_OWNER_USR)
    ) { "$language Apple binding symbol/reference inventory changed" }
    put("language", JsonPrimitive(language))
    put("publicSymbols", publicSymbols.appleJsonStrings())
    put("referencedSymbols", referencedSymbols.appleJsonStrings())
    put("claims", buildJsonArray {
        capabilities.forEach { capability ->
            val usr = usrByCapability.getValue(capability)
            add(buildJsonObject {
                put("canonicalKey", JsonPrimitive(capability))
                put("publicSymbol", JsonPrimitive(usr))
                put("compilerReference", JsonPrimitive(usr))
                put("behaviorTest", JsonPrimitive(behaviorTest))
            })
        }
    })
    put("exclusions", buildJsonArray {})
    put("missingCapabilityKeys", missing.appleJsonStrings())
}

private fun appleBindingUsr(capability: String): String = when {
    "|kind=constructor|" in capability -> appleFailureConstructorUsr
    "|{}code[0]|" in capability -> appleFailureCodeUsr
    "|{}isRecoverable[0]|" in capability -> appleFailureRecoverableUsr
    "|{}message[0]|" in capability -> appleFailureMessageUsr
    ".ACCEPT|null[0]" in capability -> appleApprovalAcceptUsr
    ".DECLINE|null[0]" in capability -> appleApprovalDeclineUsr
    else -> error("Unexpected canonical Apple binding capability: $capability")
}

private fun expectedSwiftAppleBindingSurface(): List<AppleCompilerSymbol> = listOf(
    AppleCompilerSymbol(
        APPLE_CODEX_FAILURE_OWNER_USR, "swift", "swift.class", listOf("CodexFailure"),
        "CodexFailure", "public", "class CodexFailure", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureConstructorUsr, "swift", "swift.init",
        listOf("CodexFailure", "init(code:message:isRecoverable:)"),
        "init(code:message:isRecoverable:)", "public",
        "init(code: String, message: String, isRecoverable: Bool)", listOf("s:SS", "s:SS", "s:Sb"),
        listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
        null,
    ),
    AppleCompilerSymbol(
        appleFailureCodeUsr, "swift", "swift.property", listOf("CodexFailure", "code"),
        "code", "open", "var code: String { get }", listOf("s:SS"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureRecoverableUsr, "swift", "swift.property", listOf("CodexFailure", "isRecoverable"),
        "isRecoverable", "open", "var isRecoverable: Bool { get }", listOf("s:Sb"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureMessageUsr, "swift", "swift.property", listOf("CodexFailure", "message"),
        "message", "open", "var message: String { get }", listOf("s:SS"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_APPROVAL_DECISION_OWNER_USR, "swift", "swift.class", listOf("AgentApprovalDecision"),
        "AgentApprovalDecision", "public", "class AgentApprovalDecision", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalAcceptUsr, "swift", "swift.type.property", listOf("AgentApprovalDecision", "accept"),
        "accept", "open", "class var accept: AgentApprovalDecision { get }",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalDeclineUsr, "swift", "swift.type.property", listOf("AgentApprovalDecision", "decline"),
        "decline", "open", "class var decline: AgentApprovalDecision { get }",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
).sortedBy(AppleCompilerSymbol::precise)

private fun expectedObjectiveCAppleBindingSurface(): List<AppleCompilerSymbol> = listOf(
    AppleCompilerSymbol(
        APPLE_CODEX_FAILURE_OWNER_USR, "objective-c", "objective-c.class", listOf("CodexAgentCodexFailure"),
        "CodexAgentCodexFailure", "public", "@interface CodexAgentCodexFailure : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureConstructorUsr, "objective-c", "objective-c.method",
        listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
        "initWithCode:message:isRecoverable:", "public",
        "- (instancetype) initWithCode:(NSString *) code message:(NSString *) message " +
            "isRecoverable:(BOOL) isRecoverable;",
        listOf("c:objc(cs)NSString", "c:objc(cs)NSString", "c:@T@BOOL"),
        listOf(
            "code" to "(NSString *) code",
            "message" to "(NSString *) message",
            "isRecoverable" to "(BOOL) isRecoverable",
        ),
        "instancetype",
    ),
    AppleCompilerSymbol(
        appleFailureCodeUsr, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "code"),
        "code", "public", "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureRecoverableUsr, "objective-c", "objective-c.property",
        listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
        "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureMessageUsr, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "message"),
        "message", "public", "@property (readonly) NSString * message;",
        listOf("c:objc(cs)NSString"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_APPROVAL_DECISION_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentApprovalDecision"), "CodexAgentAgentApprovalDecision", "public",
        "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalAcceptUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalDeclineUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
).sortedBy(AppleCompilerSymbol::precise)

private fun expectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleFailureConstructorUsr, "declref_expr", "init", null,
        "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD", emptyList(),
    ),
    AppleCompilerReference(appleFailureCodeUsr, "member_ref_expr", "code", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleFailureRecoverableUsr, "member_ref_expr", "isRecoverable", null, "\$sSbD", emptyList(),
    ),
    AppleCompilerReference(appleFailureMessageUsr, "member_ref_expr", "message", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleApprovalAcceptUsr, "member_ref_expr", "accept", null,
        "\$sSo010CodexAgentB16ApprovalDecisionCD", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalDeclineUsr, "member_ref_expr", "decline", null,
        "\$sSo010CodexAgentB16ApprovalDecisionCD", emptyList(),
    ),
).sortedBy(AppleCompilerReference::precise)

private fun expectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleFailureConstructorUsr, "ObjCMessageExpr", "initWithCode:message:isRecoverable:",
        "CodexAgentCodexFailure", "CodexAgentCodexFailure *", listOf("NSString *", "NSString *", "BOOL"),
    ),
    AppleCompilerReference(
        appleFailureCodeUsr, "ObjCPropertyRefExpr", "code", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleFailureRecoverableUsr, "ObjCPropertyRefExpr", "isRecoverable", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleFailureMessageUsr, "ObjCPropertyRefExpr", "message", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalAcceptUsr, "ObjCMessageExpr", "accept", "CodexAgentAgentApprovalDecision",
        "CodexAgentAgentApprovalDecision * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalDeclineUsr, "ObjCMessageExpr", "decline", "CodexAgentAgentApprovalDecision",
        "CodexAgentAgentApprovalDecision * _Nonnull", emptyList(),
    ),
).sortedBy(AppleCompilerReference::precise)

private fun JsonElement.appleSymbol(): AppleCompilerSymbol {
    val symbol = appleObject("Apple compiler symbol").also {
        it.appleKeys(
            "Apple compiler symbol", "precise", "interfaceLanguage", "kind", "path", "title", "accessLevel",
            "declaration", "typeIdentifiers", "parameters", "returns",
        )
    }
    return AppleCompilerSymbol(
        symbol.appleString("precise"), symbol.appleString("interfaceLanguage"), symbol.appleString("kind"),
        symbol.appleStrings("path"), symbol.appleString("title"), symbol.appleString("accessLevel"),
        symbol.appleString("declaration"), symbol.appleStrings("typeIdentifiers", unique = false),
        symbol.appleArray("parameters").map { value ->
            val parameter = value.appleObject("Apple compiler parameter").also {
                it.appleKeys("Apple compiler parameter", "name", "declaration")
            }
            parameter.appleString("name") to parameter.appleString("declaration")
        },
        symbol.appleNullableString("returns"),
    )
}

private fun JsonElement.appleReference(): AppleCompilerReference {
    val reference = appleObject("Apple compiler reference").also {
        it.appleKeys(
            "Apple compiler reference", "precise", "kind", "name", "receiverType", "valueType", "argumentTypes",
        )
    }
    return AppleCompilerReference(
        reference.appleString("precise"), reference.appleString("kind"), reference.appleString("name"),
        reference.appleNullableString("receiverType"), reference.appleString("valueType"),
        reference.appleStrings("argumentTypes", unique = false, allowAsterisk = true),
    )
}

private fun JsonObject.appleKeys(label: String, vararg keys: String) {
    check(this.keys == keys.toSet()) {
        "$label keys changed: expected=${keys.sorted()} actual=${this.keys.sorted()}"
    }
}

private fun JsonElement.appleObject(label: String): JsonObject = this as? JsonObject
    ?: error("$label is not a JSON object")

private fun JsonObject.appleObject(name: String): JsonObject = this[name]?.appleObject(name)
    ?: error("Missing Apple JSON object: $name")

private fun JsonObject.appleArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing Apple JSON array: $name")

private fun JsonObject.appleString(name: String): String {
    val value = this[name] as? JsonPrimitive ?: error("Missing Apple JSON string: $name")
    check(value.isString) { "Apple JSON field $name is not a string" }
    return value.contentOrNull ?: error("Missing Apple JSON string: $name")
}

private fun JsonObject.appleNullableString(name: String): String? = when (val value = this[name]) {
    JsonNull -> null
    is JsonPrimitive -> {
        check(value.isString) { "Apple JSON field $name is not a nullable string" }
        value.content
    }
    else -> error("Apple JSON field $name is not a nullable string")
}

private fun JsonObject.appleInt(name: String): Int {
    val value = this[name] as? JsonPrimitive ?: error("Missing Apple JSON integer: $name")
    check(!value.isString) { "Apple JSON field $name is not an integer" }
    return value.intOrNull ?: error("Apple JSON field $name is not an integer")
}

private fun JsonObject.appleSha256(name: String): String = appleString(name).also { digest ->
    digest.appleSha256("Apple JSON field $name")
}

private fun String.appleSha256(label: String) {
    check(length == 64 && all { it in '0'..'9' || it in 'a'..'f' }) { "$label is not an exact SHA-256" }
}

private fun JsonObject.appleStrings(
    name: String,
    unique: Boolean = true,
    allowAsterisk: Boolean = false,
): List<String> = appleArray(name).map { value ->
    val primitive = value as? JsonPrimitive ?: error("Apple JSON array $name contains a non-string")
    check(primitive.isString) { "Apple JSON array $name contains a non-string" }
    primitive.content
}.also { values ->
    check(!unique || values.size == values.distinct().size) { "Apple JSON array $name contains duplicates" }
    values.forEach { it.appleRecord("Apple JSON array $name", allowAsterisk) }
}

private fun String.appleRecord(label: String, allowAsterisk: Boolean = false) {
    check(isNotBlank() && this == trim() && (allowAsterisk || '*' !in this) && none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $this"
    }
}

private fun Iterable<String>.appleJsonStrings(): JsonArray = buildJsonArray {
    this@appleJsonStrings.forEach { add(JsonPrimitive(it)) }
}

private fun readCanonicalAppleBindingObject(file: File, label: String): JsonObject {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "$label is missing, non-regular, or a symlink: $file"
    }
    val contents = file.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject ?: error("$label is not a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "$label is not canonically encoded"
    }
    return root
}

private fun appleBindingTargetDigests(xcframework: File): Map<String, AppleBindingTargetDigests> = listOf(
    "ios-arm64", "ios-arm64-simulator",
).associateWith { name ->
    val framework = xcframework.resolve("$name/CodexAgent.framework")
    val binary = framework.resolve("CodexAgent")
    val header = framework.resolve("Headers/CodexAgent.h")
    val moduleMap = framework.resolve("Modules/module.modulemap")
    listOf(binary, header, moduleMap).forEach { file ->
        check(file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L) {
            "Apple binding artifact is missing, empty, or unsafe: $file"
        }
    }
    AppleBindingTargetDigests(
        framework.crossLanguageTreeDigest(), binary.releaseDigest(), header.releaseDigest(), moduleMap.releaseDigest(),
    )
}

@CacheableTask
abstract class GenerateAppleBindingEvidenceTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalApiReport: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalCoverageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val compilerEvidence: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcframeworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val swiftConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val objectiveCConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val xctestEvidence: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcresultDirectory: DirectoryProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val compilerFile = compilerEvidence.get().asFile
        val xctestFile = xctestEvidence.get().asFile
        val xcframework = xcframeworkDirectory.get().asFile
        val xcresult = xcresultDirectory.get().asFile
        val report = deriveCrossLanguageAppleBindingEvidence(
            readCrossLanguageCanonicalApiEvidence(
                canonicalApiReport.get().asFile,
                canonicalCoverageReceipt.get().asFile,
            ),
            readCanonicalAppleBindingObject(compilerFile, "Apple compiler evidence"),
            readCanonicalAppleBindingObject(xctestFile, "Apple XCTest evidence"),
            AppleBindingInputDigests(
                compilerFile.releaseDigest(),
                xcframework.crossLanguageTreeDigest(),
                appleBindingFileDigest(swiftConsumer.get().asFile, "Swift compiler consumer"),
                appleBindingFileDigest(objectiveCConsumer.get().asFile, "Objective-C compiler consumer"),
                xctestFile.releaseDigest(),
                xcresult.crossLanguageTreeDigest(),
                appleBindingTargetDigests(xcframework),
            ),
        )
        output.atomicWriteJson(report)
        check(readCanonicalAppleBindingObject(output, "Apple binding evidence") == report) {
            "Apple binding evidence does not match freshly derived observations"
        }
    }
}

private fun appleBindingFileDigest(file: File, label: String): String {
    check(file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L) {
        "$label is missing, empty, or a symlink: $file"
    }
    return file.releaseDigest()
}
