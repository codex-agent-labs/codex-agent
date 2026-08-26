import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal const val APPLE_COMPILER_EVIDENCE_PROTOCOL = "codex-agent-apple-compiler-evidence-v1"
internal const val APPLE_CODEX_FAILURE_OWNER_USR = "c:objc(cs)CodexAgentCodexFailure"
internal const val APPLE_APPROVAL_DECISION_OWNER_USR = "c:objc(cs)CodexAgentAgentApprovalDecision"
internal const val APPLE_COLLABORATION_MODE_OWNER_USR = "c:objc(cs)CodexAgentAgentCollaborationMode"
internal const val APPLE_MESSAGE_ROLE_OWNER_USR = "c:objc(cs)CodexAgentAgentMessageRole"
private const val APPLE_CODEX_FAILURE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/CodexFailure"
private const val APPLE_APPROVAL_DECISION_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision"
private const val APPLE_COLLABORATION_MODE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode"
private const val APPLE_MESSAGE_ROLE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole"

private val appleCodexFailureMembers = linkedMapOf(
    "constructor:<init>" to "$APPLE_CODEX_FAILURE_OWNER_USR(im)initWithCode:message:isRecoverable:",
    "property:code" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)code",
    "property:isRecoverable" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)isRecoverable",
    "property:message" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)message",
)

private val appleCodexFailureCoverageTokens = mapOf(
    "constructor:<init>" to
        "api-v1:CodexFailure#constructor:<init>#sha256:db9872249097654acec4959fcef85fbac47c20419b28bbceee4a2ed40f619dce",
    "property:code" to
        "api-v1:CodexFailure#property:code#sha256:3a601436ff450cdd3e651dfc2e9faf56278431319e63c16c5fc2bff9417f10f9",
    "property:isRecoverable" to
        "api-v1:CodexFailure#property:isRecoverable#sha256:8973cb954621824ea55abdabe7aa39d7b8db93b56057971121255b2e7bd0cfa6",
    "property:message" to
        "api-v1:CodexFailure#property:message#sha256:8bc0e280b734d05df8b06e7f8f5544ba9323faa14cd59b35531b05ea3023ddad",
)

private val appleApprovalDecisionMembers = linkedMapOf(
    "enum-entry:ACCEPT" to "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)accept",
    "enum-entry:DECLINE" to "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)decline",
)

private val appleApprovalDecisionCoverageTokens = mapOf(
    "enum-entry:ACCEPT" to
        "api-v1:AgentApprovalDecision#enum-entry:ACCEPT#sha256:c6613f75901ffd0146f3c8f945f73fabdc67efb237d52809c8a1e062835dc868",
    "enum-entry:DECLINE" to
        "api-v1:AgentApprovalDecision#enum-entry:DECLINE#sha256:db4d1df5ec20f42363a10d2b7a416c5e114a21663f8f70e0b32f4608dade7d56",
)

private val appleCollaborationModeMembers = linkedMapOf(
    "enum-entry:DEFAULT" to "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)default_",
    "enum-entry:PLAN" to "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)plan",
)

private val appleCollaborationModeCoverageTokens = mapOf(
    "enum-entry:DEFAULT" to
        "api-v1:AgentCollaborationMode#enum-entry:DEFAULT#sha256:e7a82ccb52ea70efb42bb512dfc2ef7616813fd6e0668c6d661f6b3b01c8a3d3",
    "enum-entry:PLAN" to
        "api-v1:AgentCollaborationMode#enum-entry:PLAN#sha256:ec0e7395b27d5e890c396ea4e39af43f49b093b933ee9062c83fc9c07a754e4d",
)

private val appleMessageRoleMembers = linkedMapOf(
    "enum-entry:USER" to "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)user",
    "enum-entry:ASSISTANT" to "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)assistant",
)

private val appleMessageRoleCoverageTokens = mapOf(
    "enum-entry:USER" to
        "api-v1:AgentMessageRole#enum-entry:USER#sha256:5572c10ccfb5180d31c30ba322e62f73ce28013434d77ee9e6fe416e076fe895",
    "enum-entry:ASSISTANT" to
        "api-v1:AgentMessageRole#enum-entry:ASSISTANT#sha256:f369c4f0e47685b440320333006c0c058783ee2a55f2b9c554839a8d9a0df128",
)

private val appleBindingMembers =
    appleCodexFailureMembers + appleApprovalDecisionMembers + appleCollaborationModeMembers + appleMessageRoleMembers
private val appleBindingCoverageTokens =
    appleCodexFailureCoverageTokens + appleApprovalDecisionCoverageTokens + appleCollaborationModeCoverageTokens +
        appleMessageRoleCoverageTokens

private fun appleBindingShape(capability: String): String {
    val token = crossLanguageApiCoverageToken(capability)
    return appleBindingCoverageTokens.entries.singleOrNull { it.value == token }?.key
        ?: error("Unexpected canonical Apple binding capability: $capability")
}

internal data class AppleCompilerSymbol(
    val precise: String,
    val interfaceLanguage: String,
    val kind: String,
    val path: List<String>,
    val title: String,
    val accessLevel: String,
    val declaration: String,
    val typeIdentifiers: List<String>,
    val parameters: List<Pair<String, String>>,
    val returns: String?,
)

internal data class AppleCompilerReference(
    val precise: String,
    val kind: String,
    val name: String,
    val receiverType: String?,
    val valueType: String,
    val argumentTypes: List<String>,
)

private data class ExpectedAppleCompilerSymbol(
    val kind: String,
    val path: List<String>,
    val title: String,
    val access: String,
    val declaration: String,
    val typeIdentifiers: List<String>,
    val parameters: List<Pair<String, String>> = emptyList(),
    val returns: String? = null,
)

private data class AppleCompilerSlice(
    val name: String,
    val sdkName: String,
    val targetTriple: String,
)

private data class InspectedAppleCompilerSlice(
    val specification: AppleCompilerSlice,
    val sdkVersion: String,
    val framework: File,
    val swiftSurface: List<AppleCompilerSymbol>,
    val objectiveCSurface: List<AppleCompilerSymbol>,
    val swiftReferences: List<AppleCompilerReference>,
    val objectiveCReferences: List<AppleCompilerReference>,
)

private val appleCompilerSlices = listOf(
    AppleCompilerSlice("ios-arm64", "iphoneos", "arm64-apple-ios15.0"),
    AppleCompilerSlice("ios-arm64-simulator", "iphonesimulator", "arm64-apple-ios15.0-simulator"),
)

private val expectedSwiftAppleBindingSymbols = linkedMapOf(
    APPLE_CODEX_FAILURE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("CodexFailure"), "CodexFailure", "public", "class CodexFailure", emptyList(),
    ),
    appleCodexFailureMembers.getValue("constructor:<init>") to ExpectedAppleCompilerSymbol(
        "swift.init", listOf("CodexFailure", "init(code:message:isRecoverable:)"),
        "init(code:message:isRecoverable:)", "public",
        "init(code: String, message: String, isRecoverable: Bool)", listOf("s:SS", "s:SS", "s:Sb"),
        listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
    ),
    appleCodexFailureMembers.getValue("property:code") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "code"), "code", "open",
        "var code: String { get }", listOf("s:SS"),
    ),
    appleCodexFailureMembers.getValue("property:isRecoverable") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "isRecoverable"), "isRecoverable", "open",
        "var isRecoverable: Bool { get }", listOf("s:Sb"),
    ),
    appleCodexFailureMembers.getValue("property:message") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "message"), "message", "open",
        "var message: String { get }", listOf("s:SS"),
    ),
    APPLE_APPROVAL_DECISION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentApprovalDecision"), "AgentApprovalDecision", "public",
        "class AgentApprovalDecision", emptyList(),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:ACCEPT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentApprovalDecision", "accept"), "accept", "open",
        "class var accept: AgentApprovalDecision { get }", listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:DECLINE") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentApprovalDecision", "decline"), "decline", "open",
        "class var decline: AgentApprovalDecision { get }", listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    APPLE_COLLABORATION_MODE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentCollaborationMode"), "AgentCollaborationMode", "public",
        "class AgentCollaborationMode", emptyList(),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:DEFAULT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentCollaborationMode", "default_"), "default_", "open",
        "class var default_: AgentCollaborationMode { get }", listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:PLAN") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentCollaborationMode", "plan"), "plan", "open",
        "class var plan: AgentCollaborationMode { get }", listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    APPLE_MESSAGE_ROLE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentMessageRole"), "AgentMessageRole", "public",
        "class AgentMessageRole", emptyList(),
    ),
    appleMessageRoleMembers.getValue("enum-entry:USER") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMessageRole", "user"), "user", "open",
        "class var user: AgentMessageRole { get }", listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    appleMessageRoleMembers.getValue("enum-entry:ASSISTANT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMessageRole", "assistant"), "assistant", "open",
        "class var assistant: AgentMessageRole { get }", listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
)

private val expectedObjectiveCAppleBindingSymbols = linkedMapOf(
    APPLE_CODEX_FAILURE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentCodexFailure"), "CodexAgentCodexFailure", "public",
        "@interface CodexAgentCodexFailure : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
    ),
    appleCodexFailureMembers.getValue("constructor:<init>") to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
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
    appleCodexFailureMembers.getValue("property:code") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "code"), "code", "public",
        "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString"),
    ),
    appleCodexFailureMembers.getValue("property:isRecoverable") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
        "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL"),
    ),
    appleCodexFailureMembers.getValue("property:message") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "message"), "message", "public",
        "@property (readonly) NSString * message;", listOf("c:objc(cs)NSString"),
    ),
    APPLE_APPROVAL_DECISION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentApprovalDecision"), "CodexAgentAgentApprovalDecision", "public",
        "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:ACCEPT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:DECLINE") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    APPLE_COLLABORATION_MODE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentCollaborationMode"),
        "CodexAgentAgentCollaborationMode", "public",
        "@interface CodexAgentAgentCollaborationMode : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:DEFAULT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentCollaborationMode", "default_"), "default_", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * default_;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:PLAN") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentCollaborationMode", "plan"), "plan", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * plan;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    APPLE_MESSAGE_ROLE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentMessageRole"),
        "CodexAgentAgentMessageRole", "public",
        "@interface CodexAgentAgentMessageRole : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleMessageRoleMembers.getValue("enum-entry:USER") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMessageRole", "user"), "user", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * user;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    appleMessageRoleMembers.getValue("enum-entry:ASSISTANT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMessageRole", "assistant"), "assistant", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * assistant;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
)

internal fun appleBindingCapabilityKeys(memberKeys: List<String>): List<String> {
    val ownerPrefixes = setOf(
        "common|owner=$APPLE_CODEX_FAILURE_CANONICAL_OWNER|",
        "common|owner=$APPLE_APPROVAL_DECISION_CANONICAL_OWNER|",
        "common|owner=$APPLE_COLLABORATION_MODE_CANONICAL_OWNER|",
        "common|owner=$APPLE_MESSAGE_ROLE_CANONICAL_OWNER|",
    )
    val byShape = memberKeys.filter { key -> ownerPrefixes.any { prefix -> key.startsWith(prefix) } }.groupBy { key ->
        appleBindingShape(key)
    }
    check(byShape.keys == appleBindingMembers.keys) {
        "Canonical Apple binding capability set changed: ${byShape.keys.sorted()}"
    }
    check(byShape.values.all { it.size == 1 }) { "Canonical Apple binding capabilities are overloaded" }
    return byShape.values.map { it.single() }.sorted()
}

internal fun swiftSymbolGraphCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    output: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "swift-symbolgraph-extract", "-module-name", "CodexAgent", "-target", target,
    "-sdk", sdk.absolutePath, "-F", frameworkSearchPath.absolutePath,
    "-module-cache-path", moduleCache.absolutePath, "-minimum-access-level", "public",
    "-skip-synthesized-members", "-output-dir", output.absolutePath,
)

internal fun objectiveCExtractApiCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    header: File,
    output: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "clang", "-extract-api", "-x", "objective-c-header", "-target", target,
    "-isysroot", sdk.absolutePath, "-fmodules", "-fmodules-cache-path=${moduleCache.absolutePath}",
    "-F", frameworkSearchPath.absolutePath, header.absolutePath, "-o", output.absolutePath,
)

internal fun swiftConsumerAstCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    consumer: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "swiftc", "-typecheck", "-dump-ast", "-dump-ast-format", "json",
    "-target", target, "-sdk", sdk.absolutePath, "-F", frameworkSearchPath.absolutePath,
    "-module-cache-path", moduleCache.absolutePath, consumer.absolutePath,
)

internal fun objectiveCConsumerAstCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    consumer: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "clang", "-fsyntax-only", "-x", "objective-c", "-target", target,
    "-isysroot", sdk.absolutePath, "-fmodules", "-fmodules-cache-path=${moduleCache.absolutePath}",
    "-F", frameworkSearchPath.absolutePath, "-Xclang", "-ast-dump=json", consumer.absolutePath,
)

internal fun parseSwiftAppleBindingSurface(json: String): List<AppleCompilerSymbol> =
    parseAppleBindingSurface(json, "swift", expectedSwiftAppleBindingSymbols)

internal fun parseObjectiveCAppleBindingSurface(json: String): List<AppleCompilerSymbol> =
    parseAppleBindingSurface(json, "objective-c", expectedObjectiveCAppleBindingSymbols)

private fun parseAppleBindingSurface(
    json: String,
    language: String,
    expected: Map<String, ExpectedAppleCompilerSymbol>,
): List<AppleCompilerSymbol> {
    val root = appleJsonObject(json, "$language API")
    val symbols = root.appleArray("symbols").map { element -> element.appleObject("$language symbol") }
        .filter { symbol -> symbol.appleObject("identifier").appleString("precise") in expected }
        .map(::normalizeAppleCompilerSymbol)
    check(symbols.map(AppleCompilerSymbol::precise).toSet() == expected.keys && symbols.size == expected.size) {
        "$language Apple binding symbol set changed"
    }
    symbols.forEach { actual ->
        val contract = expected.getValue(actual.precise)
        check(actual.interfaceLanguage == language && actual.kind == contract.kind && actual.path == contract.path &&
            actual.title == contract.title && actual.accessLevel == contract.access &&
            actual.declaration == contract.declaration && actual.typeIdentifiers == contract.typeIdentifiers &&
            actual.parameters == contract.parameters && actual.returns == contract.returns) {
            "$language Apple binding symbol changed: ${actual.precise}"
        }
    }
    val memberOwners = appleCodexFailureMembers.values.associateWith { APPLE_CODEX_FAILURE_OWNER_USR } +
        appleApprovalDecisionMembers.values.associateWith { APPLE_APPROVAL_DECISION_OWNER_USR } +
        appleCollaborationModeMembers.values.associateWith { APPLE_COLLABORATION_MODE_OWNER_USR } +
        appleMessageRoleMembers.values.associateWith { APPLE_MESSAGE_ROLE_OWNER_USR }
    val relationships = root.appleArray("relationships").map { it.appleObject("$language relationship") }
        .filter { relationship ->
            relationship.appleString("kind") == "memberOf" &&
                relationship.appleString("source") in memberOwners
        }.map { relationship ->
            relationship.appleString("source") to relationship.appleString("target")
        }
    check(relationships.size == memberOwners.size &&
        relationships.map(Pair<String, String>::first).toSet() == memberOwners.keys &&
        relationships.all { (source, target) -> target == memberOwners.getValue(source) }) {
        "$language Apple binding ownership relationships changed"
    }
    return symbols.sortedBy(AppleCompilerSymbol::precise)
}

private fun normalizeAppleCompilerSymbol(symbol: JsonObject): AppleCompilerSymbol {
    val identifier = symbol.appleObject("identifier")
    val fragments = symbol.appleArray("declarationFragments").map { it.appleObject("declaration fragment") }
    val signature = symbol["functionSignature"] as? JsonObject
    val parameters = signature?.appleArray("parameters")?.map { parameterElement ->
        val parameter = parameterElement.appleObject("function parameter")
        parameter.appleString("name") to fragmentsText(parameter.appleArray("declarationFragments"))
    }.orEmpty()
    val returns = signature?.get("returns")?.let { value -> fragmentsText(value.appleArray("function returns")) }
    return AppleCompilerSymbol(
        precise = identifier.appleString("precise"),
        interfaceLanguage = identifier.appleString("interfaceLanguage"),
        kind = symbol.appleObject("kind").appleString("identifier"),
        path = symbol.appleArray("pathComponents").map { it.appleString("path component") },
        title = symbol.appleObject("names").appleString("title"),
        accessLevel = symbol.appleString("accessLevel"),
        declaration = fragmentsText(JsonArray(fragments)),
        typeIdentifiers = fragments.filter { it.appleString("kind") == "typeIdentifier" }
            .map { it.appleString("preciseIdentifier") },
        parameters = parameters,
        returns = returns,
    )
}

internal fun parseSwiftAppleBindingReferences(json: String): List<AppleCompilerReference> {
    val references = appleJsonObject(json, "Swift consumer AST").walkAppleObjects().mapNotNull { node ->
        val declaration = node["decl"] as? JsonObject ?: return@mapNotNull null
        val precise = declaration.appleStringOrNull("decl_usr") ?: return@mapNotNull null
        if (precise !in appleBindingMembers.values) return@mapNotNull null
        AppleCompilerReference(
            precise, node.appleString("_kind"), declaration.appleString("base_name"), null,
            node.appleString("type"), emptyList(),
        )
    }.toList().groupBy(AppleCompilerReference::precise).map { (precise, values) ->
        check(values.distinct().size == 1) { "Swift reference is ambiguous: $precise" }
        values.first()
    }.sortedBy(AppleCompilerReference::precise)
    check(references.map(AppleCompilerReference::precise).toSet() == appleBindingMembers.values.toSet()) {
        "Swift Apple binding reference set changed"
    }
    val expectedKinds = mapOf(
        appleCodexFailureMembers.getValue("constructor:<init>") to ("declref_expr" to "init"),
        appleCodexFailureMembers.getValue("property:code") to ("member_ref_expr" to "code"),
        appleCodexFailureMembers.getValue("property:isRecoverable") to ("member_ref_expr" to "isRecoverable"),
        appleCodexFailureMembers.getValue("property:message") to ("member_ref_expr" to "message"),
        appleApprovalDecisionMembers.getValue("enum-entry:ACCEPT") to ("member_ref_expr" to "accept"),
        appleApprovalDecisionMembers.getValue("enum-entry:DECLINE") to ("member_ref_expr" to "decline"),
        appleCollaborationModeMembers.getValue("enum-entry:DEFAULT") to ("member_ref_expr" to "default_"),
        appleCollaborationModeMembers.getValue("enum-entry:PLAN") to ("member_ref_expr" to "plan"),
        appleMessageRoleMembers.getValue("enum-entry:USER") to ("member_ref_expr" to "user"),
        appleMessageRoleMembers.getValue("enum-entry:ASSISTANT") to ("member_ref_expr" to "assistant"),
    )
    references.forEach { reference ->
        check(reference.kind to reference.name == expectedKinds.getValue(reference.precise) &&
            reference.valueType.isNotBlank()) { "Swift reference changed: ${reference.precise}" }
    }
    return references
}

internal fun parseObjectiveCAppleBindingReferences(json: String): List<AppleCompilerReference> {
    val nodes = appleJsonObject(json, "Objective-C consumer AST").walkAppleObjects().toList()
    val constructor = nodes.filter { node ->
        node.appleStringOrNull("kind") == "ObjCMessageExpr" &&
            node.appleStringOrNull("selector") == "initWithCode:message:isRecoverable:"
    }.map { node ->
        val inner = node.appleArray("inner")
        val receiver = inner.first().appleObject("Objective-C constructor receiver")
        AppleCompilerReference(
            appleCodexFailureMembers.getValue("constructor:<init>"), "ObjCMessageExpr",
            node.appleString("selector"), receiver.appleObject("classType").appleString("qualType"),
            node.appleObject("type").appleString("qualType"),
            inner.drop(1).map { it.appleObject("Objective-C constructor argument")
                .appleObject("type").appleString("qualType") },
        )
    }.distinct()
    check(constructor == listOf(AppleCompilerReference(
        appleCodexFailureMembers.getValue("constructor:<init>"), "ObjCMessageExpr",
        "initWithCode:message:isRecoverable:", "CodexAgentCodexFailure", "CodexAgentCodexFailure *",
        listOf("NSString *", "NSString *", "BOOL"),
    ))) { "Objective-C CodexFailure constructor reference changed" }

    val propertyUsrs = appleCodexFailureMembers.filterKeys { it.startsWith("property:") }
        .mapKeys { it.key.substringAfter(':') }
    val properties = nodes.filter { node ->
        node.appleStringOrNull("kind") == "ObjCPropertyRefExpr" &&
            (node["property"] as? JsonObject)?.appleStringOrNull("name")
                ?.let(propertyUsrs::containsKey) == true
    }.map { node ->
        val name = node.appleObject("property").appleString("name")
        val inner = node.appleArray("inner").first().appleObject("Objective-C property receiver")
        AppleCompilerReference(
            propertyUsrs.getValue(name), "ObjCPropertyRefExpr", name,
            inner.appleObject("type").appleString("qualType"), node.appleObject("type").appleString("qualType"),
            emptyList(),
        ).also {
            check(node.appleBoolean("isMessagingGetter")) { "Objective-C property is not a getter: $name" }
        }
    }.distinct().sortedBy(AppleCompilerReference::precise)
    val expectedProperties = propertyUsrs.map { (name, precise) ->
        AppleCompilerReference(
            precise, "ObjCPropertyRefExpr", name, "CodexAgentCodexFailure *", "<pseudo-object type>", emptyList(),
        )
    }.sortedBy(AppleCompilerReference::precise)
    check(properties == expectedProperties) { "Objective-C CodexFailure property references changed" }
    val decisions = listOf("accept", "decline").map { name ->
        val node = nodes.singleOrNull { candidate ->
            candidate.appleStringOrNull("kind") == "ObjCMessageExpr" &&
                candidate.appleStringOrNull("selector") == name
        } ?: error("Objective-C AgentApprovalDecision reference changed: $name")
        check(node.appleString("receiverKind") == "class") {
            "Objective-C AgentApprovalDecision receiver changed: $name"
        }
        AppleCompilerReference(
            appleApprovalDecisionMembers.getValue("enum-entry:${name.uppercase()}"),
            "ObjCMessageExpr", name, node.appleObject("classType").appleString("qualType"),
            node.appleObject("type").appleString("qualType"), emptyList(),
        )
    }
    val expectedDecisions = listOf("accept", "decline").map { name ->
        AppleCompilerReference(
            appleApprovalDecisionMembers.getValue("enum-entry:${name.uppercase()}"),
            "ObjCMessageExpr", name, "CodexAgentAgentApprovalDecision",
            "CodexAgentAgentApprovalDecision * _Nonnull", emptyList(),
        )
    }
    check(decisions == expectedDecisions) { "Objective-C AgentApprovalDecision references changed" }
    val collaborationModes = listOf("default_", "plan").map { name ->
        val node = nodes.singleOrNull { candidate ->
            candidate.appleStringOrNull("kind") == "ObjCMessageExpr" &&
                candidate.appleStringOrNull("selector") == name
        } ?: error("Objective-C AgentCollaborationMode reference changed: $name")
        check(node.appleString("receiverKind") == "class") {
            "Objective-C AgentCollaborationMode receiver changed: $name"
        }
        val shape = if (name == "default_") "enum-entry:DEFAULT" else "enum-entry:PLAN"
        AppleCompilerReference(
            appleCollaborationModeMembers.getValue(shape), "ObjCMessageExpr", name,
            node.appleObject("classType").appleString("qualType"),
            node.appleObject("type").appleString("qualType"), emptyList(),
        )
    }
    val expectedCollaborationModes = listOf("default_", "plan").map { name ->
        val shape = if (name == "default_") "enum-entry:DEFAULT" else "enum-entry:PLAN"
        AppleCompilerReference(
            appleCollaborationModeMembers.getValue(shape), "ObjCMessageExpr", name,
            "CodexAgentAgentCollaborationMode", "CodexAgentAgentCollaborationMode * _Nonnull", emptyList(),
        )
    }
    check(collaborationModes == expectedCollaborationModes) {
        "Objective-C AgentCollaborationMode references changed"
    }
    val messageRoles = listOf("user", "assistant").map { name ->
        val node = nodes.singleOrNull { candidate ->
            candidate.appleStringOrNull("kind") == "ObjCMessageExpr" &&
                candidate.appleStringOrNull("selector") == name
        } ?: error("Objective-C AgentMessageRole reference changed: $name")
        check(node.appleString("receiverKind") == "class") {
            "Objective-C AgentMessageRole receiver changed: $name"
        }
        val shape = if (name == "user") "enum-entry:USER" else "enum-entry:ASSISTANT"
        AppleCompilerReference(
            appleMessageRoleMembers.getValue(shape), "ObjCMessageExpr", name,
            node.appleObject("classType").appleString("qualType"),
            node.appleObject("type").appleString("qualType"), emptyList(),
        )
    }
    val expectedMessageRoles = listOf("user", "assistant").map { name ->
        val shape = if (name == "user") "enum-entry:USER" else "enum-entry:ASSISTANT"
        AppleCompilerReference(
            appleMessageRoleMembers.getValue(shape), "ObjCMessageExpr", name,
            "CodexAgentAgentMessageRole", "CodexAgentAgentMessageRole * _Nonnull", emptyList(),
        )
    }
    check(messageRoles == expectedMessageRoles) { "Objective-C AgentMessageRole references changed" }
    return (constructor + properties + decisions + collaborationModes + messageRoles)
        .sortedBy(AppleCompilerReference::precise)
}

private fun JsonObject.walkAppleObjects(): Sequence<JsonObject> = sequence {
    yield(this@walkAppleObjects)
    for (value in values) yieldAll(value.walkAppleObjects())
}

private fun JsonElement.walkAppleObjects(): Sequence<JsonObject> = when (this) {
    is JsonObject -> walkAppleObjects()
    is JsonArray -> asSequence().flatMap { it.walkAppleObjects() }
    else -> emptySequence()
}

private fun fragmentsText(fragments: JsonArray): String = fragments.joinToString("") { fragment ->
    fragment.appleObject("declaration fragment").appleString("spelling")
}

private fun appleJsonObject(json: String, label: String): JsonObject =
    releaseJson.parseToJsonElement(json) as? JsonObject ?: error("$label is not a JSON object")

private fun JsonElement.appleObject(label: String): JsonObject = this as? JsonObject
    ?: error("$label is not a JSON object")

private fun JsonElement.appleArray(label: String): JsonArray = this as? JsonArray
    ?: error("$label is not a JSON array")

private fun JsonElement.appleString(label: String): String {
    val primitive = this as? JsonPrimitive ?: error("$label is not a string")
    check(primitive.isString) { "$label is not a string" }
    return primitive.content
}

private fun JsonObject.appleObject(name: String): JsonObject = this[name]?.appleObject(name)
    ?: error("Missing JSON object: $name")
private fun JsonObject.appleArray(name: String): JsonArray = this[name]?.appleArray(name)
    ?: error("Missing JSON array: $name")
private fun JsonObject.appleString(name: String): String = this[name]?.appleString(name)
    ?: error("Missing JSON string: $name")
private fun JsonObject.appleStringOrNull(name: String): String? = (this[name] as? JsonPrimitive)
    ?.takeIf { it.isString }?.contentOrNull
private fun JsonObject.appleBoolean(name: String): Boolean {
    val primitive = this[name] as? JsonPrimitive ?: error("$name is not a boolean")
    check(!primitive.isString && primitive.content in setOf("true", "false")) { "$name is not a boolean" }
    return primitive.content == "true"
}

private fun AppleCompilerSymbol.toJson(): JsonObject = buildJsonObject {
    put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(interfaceLanguage))
    put("kind", JsonPrimitive(kind)); put("path", buildJsonArray { path.forEach { add(JsonPrimitive(it)) } })
    put("title", JsonPrimitive(title)); put("accessLevel", JsonPrimitive(accessLevel))
    put("declaration", JsonPrimitive(declaration))
    put("typeIdentifiers", buildJsonArray { typeIdentifiers.forEach { add(JsonPrimitive(it)) } })
    put("parameters", buildJsonArray { parameters.forEach { (name, declaration) -> add(buildJsonObject {
        put("name", JsonPrimitive(name)); put("declaration", JsonPrimitive(declaration))
    }) } })
    put("returns", returns?.let(::JsonPrimitive) ?: kotlinx.serialization.json.JsonNull)
}

private fun AppleCompilerReference.toJson(): JsonObject = buildJsonObject {
    put("precise", JsonPrimitive(precise)); put("kind", JsonPrimitive(kind)); put("name", JsonPrimitive(name))
    put("receiverType", receiverType?.let(::JsonPrimitive) ?: kotlinx.serialization.json.JsonNull)
    put("valueType", JsonPrimitive(valueType))
    put("argumentTypes", buildJsonArray { argumentTypes.forEach { add(JsonPrimitive(it)) } })
}

internal fun appleCompilerJsonDigest(value: JsonElement): String {
    val bytes = (releaseJson.encodeToString(JsonElement.serializer(), value) + "\n").encodeToByteArray()
    return MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

private fun symbolsJson(symbols: List<AppleCompilerSymbol>) = buildJsonArray { symbols.forEach { add(it.toJson()) } }
private fun referencesJson(references: List<AppleCompilerReference>) =
    buildJsonArray { references.forEach { add(it.toJson()) } }

@DisableCachingByDefault(because = "Invokes the installed, pinned Apple compiler toolchain")
abstract class AppleCompilerEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcframeworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalApiReport: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalCoverageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val swiftConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val objectiveCConsumer: RegularFileProperty
    @get:Input abstract val minimumIosVersion: Property<String>
    @get:Input abstract val expectedXcodeVersion: Property<String>
    @get:Input abstract val expectedXcodeBuild: Property<String>
    @get:Input abstract val expectedSwiftVersion: Property<String>
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        check(minimumIosVersion.get() == "15.0") { "Apple compiler evidence target contract changed" }
        val canonical = readCrossLanguageCanonicalApiEvidence(
            canonicalApiReport.get().asFile, canonicalCoverageReceipt.get().asFile,
        )
        val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)
        val xcodeOutput = processes.captureReleaseProcess(listOf("/usr/bin/xcodebuild", "-version"))
        val swiftOutput = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "swift", "--version"))
        verifyAppleToolchainOutput(
            xcodeOutput, swiftOutput, expectedXcodeVersion.get(), expectedXcodeBuild.get(), expectedSwiftVersion.get(),
        )
        val clangVersion = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "clang", "--version"))
            .lineSequence().firstOrNull()?.also { check(it.startsWith("Apple clang version ")) }
            ?: error("Apple Clang version is missing")
        val xcframework = xcframeworkDirectory.get().asFile
        val work = temporaryDir.resolve("compiler-evidence").also { deleteReleaseTree(it); Files.createDirectories(it.toPath()) }
        val slices = appleCompilerSlices.map { specification -> inspectSlice(specification, xcframework, work) }
        check(slices.map(InspectedAppleCompilerSlice::swiftSurface).distinct().size == 1) {
            "Swift Apple binding device and simulator surfaces differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::objectiveCSurface).distinct().size == 1) {
            "Objective-C Apple binding device and simulator surfaces differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::swiftReferences).distinct().size == 1) {
            "Swift Apple binding device and simulator references differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::objectiveCReferences).distinct().size == 1) {
            "Objective-C Apple binding device and simulator references differ"
        }
        val swiftSurface = slices.first().swiftSurface
        val objectiveCSurface = slices.first().objectiveCSurface
        val swiftReferences = slices.first().swiftReferences
        val objectiveCReferences = slices.first().objectiveCReferences
        val swiftSurfaceJson = symbolsJson(swiftSurface)
        val objectiveCSurfaceJson = symbolsJson(objectiveCSurface)
        val swiftReferencesJson = referencesJson(swiftReferences)
        val objectiveCReferencesJson = referencesJson(objectiveCReferences)
        output.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1)); put("protocol", JsonPrimitive(APPLE_COMPILER_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed")); put("moduleName", JsonPrimitive("CodexAgent"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
                put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
                put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
                put("capabilities", buildJsonArray { capabilities.forEach { add(JsonPrimitive(it)) } })
            })
            put("toolchain", buildJsonObject {
                put("xcodeVersion", JsonPrimitive(expectedXcodeVersion.get()))
                put("xcodeBuild", JsonPrimitive(expectedXcodeBuild.get()))
                put("swiftVersion", JsonPrimitive(expectedSwiftVersion.get()))
                put("clangVersion", JsonPrimitive(clangVersion))
            })
            put("artifacts", buildJsonObject {
                put("xcframeworkSha256", JsonPrimitive(xcframework.crossLanguageTreeDigest()))
                put("swiftConsumerSha256", JsonPrimitive(swiftConsumer.get().asFile.releaseDigest()))
                put("objectiveCConsumerSha256", JsonPrimitive(objectiveCConsumer.get().asFile.releaseDigest()))
            })
            put("targets", buildJsonArray { slices.forEach { slice -> add(slice.toJson()) } })
            put("surface", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftSurfaceJson)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCSurfaceJson)))
                put("swift", swiftSurfaceJson); put("objectiveC", objectiveCSurfaceJson)
            })
            put("references", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftReferencesJson)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCReferencesJson)))
                put("swift", swiftReferencesJson); put("objectiveC", objectiveCReferencesJson)
            })
            put("claims", buildJsonArray { capabilities.forEach { capability ->
                val shape = appleBindingShape(capability)
                val precise = appleBindingMembers.getValue(shape)
                add(buildJsonObject {
                    put("canonicalKey", JsonPrimitive(capability))
                    put("swiftUsr", JsonPrimitive(precise)); put("objectiveCUsr", JsonPrimitive(precise))
                })
            } })
        })
    }

    private fun inspectSlice(specification: AppleCompilerSlice, xcframework: File, work: File): InspectedAppleCompilerSlice {
        val frameworkSearchPath = xcframework.resolve(specification.name)
        val framework = frameworkSearchPath.resolve("CodexAgent.framework")
        val header = framework.resolve("Headers/CodexAgent.h")
        val moduleMap = framework.resolve("Modules/module.modulemap")
        val binary = framework.resolve("CodexAgent")
        listOf(header, moduleMap, binary).forEach { file ->
            check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
                "Apple compiler evidence framework member is missing or unsafe: $file"
            }
        }
        val sdkPath = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", specification.sdkName, "--show-sdk-path"),
        ).trim().let(::File).also { check(it.isDirectory) { "Apple SDK is missing: $it" } }
        val sdkVersion = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", specification.sdkName, "--show-sdk-version"),
        ).trim().also { check(it.matches(Regex("[0-9]+(?:\\.[0-9]+)*"))) { "Apple SDK version is invalid" } }
        val sliceWork = work.resolve(specification.name).also { Files.createDirectories(it.toPath()) }
        val swiftOutput = sliceWork.resolve("swift-symbols").also { Files.createDirectories(it.toPath()) }
        val swiftCache = sliceWork.resolve("swift-module-cache").also { Files.createDirectories(it.toPath()) }
        processes.captureReleaseProcess(swiftSymbolGraphCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, swiftCache, swiftOutput,
        ))
        val swiftSymbolGraph = swiftOutput.resolve("CodexAgent.symbols.json")
        check(swiftSymbolGraph.isFile && swiftSymbolGraph.length() > 0L) { "Swift symbol graph was not produced" }
        val objectiveCExtractApi = sliceWork.resolve("CodexAgent.objc.symbols.json")
        val clangCache = sliceWork.resolve("clang-module-cache").also { Files.createDirectories(it.toPath()) }
        processes.captureReleaseProcess(objectiveCExtractApiCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, clangCache, header, objectiveCExtractApi,
        ))
        check(objectiveCExtractApi.isFile && objectiveCExtractApi.length() > 0L) {
            "Objective-C extract-api output was not produced"
        }
        val swiftConsumerCache = sliceWork.resolve("swift-consumer-cache")
            .also { Files.createDirectories(it.toPath()) }
        val objectiveCConsumerCache = sliceWork.resolve("objective-c-consumer-cache")
            .also { Files.createDirectories(it.toPath()) }
        val swiftAst = processes.captureReleaseProcess(swiftConsumerAstCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, swiftConsumerCache,
            swiftConsumer.get().asFile,
        ))
        val objectiveCAst = processes.captureReleaseProcess(objectiveCConsumerAstCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, objectiveCConsumerCache,
            objectiveCConsumer.get().asFile,
        ))
        return InspectedAppleCompilerSlice(
            specification, sdkVersion, framework,
            parseSwiftAppleBindingSurface(swiftSymbolGraph.readText()),
            parseObjectiveCAppleBindingSurface(objectiveCExtractApi.readText()),
            parseSwiftAppleBindingReferences(swiftAst),
            parseObjectiveCAppleBindingReferences(objectiveCAst),
        )
    }
}

private fun InspectedAppleCompilerSlice.toJson(): JsonObject = buildJsonObject {
    put("name", JsonPrimitive(specification.name)); put("sdk", JsonPrimitive(specification.sdkName))
    put("sdkVersion", JsonPrimitive(sdkVersion)); put("targetTriple", JsonPrimitive(specification.targetTriple))
    put("frameworkSha256", JsonPrimitive(framework.crossLanguageTreeDigest()))
    put("binarySha256", JsonPrimitive(framework.resolve("CodexAgent").releaseDigest()))
    put("headerSha256", JsonPrimitive(framework.resolve("Headers/CodexAgent.h").releaseDigest()))
    put("moduleMapSha256", JsonPrimitive(framework.resolve("Modules/module.modulemap").releaseDigest()))
}
