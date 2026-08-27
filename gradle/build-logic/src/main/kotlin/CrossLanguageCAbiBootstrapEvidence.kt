import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.LocalState
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal const val C_ABI_BOOTSTRAP_EVIDENCE_PROTOCOL = "codex-agent-c-abi-bootstrap-evidence-v1"
internal const val C_ABI_BOOTSTRAP_CAPABILITY_COUNT = 35
internal const val C_ABI_BOOTSTRAP_CAPABILITY_SHA256 =
    "f5acb8de74c3f82daf97ddd03c2ebc19c5ab9a1de2ab2ad976bbe958d6096385"

private const val C_ABI_CANONICAL_CAPABILITY_COUNT = 556
private const val C_ABI_HEADER_SHA256 =
    "4e5cbc688e03fb78c99184a275cb04cbe797b61d3dfcfb83c6f211595d46707f"
private const val C_ABI_CINTEROP_SHA256 =
    "4a132bc83e0f69251cc9f432bb7530b4eaafe2f4d7ea1c2985ed860bedafb1c8"
private const val C_ABI_MACOS_EXPORTS_SHA256 =
    "35257663d1e947a1df02956a8d8e9f90debcbcc251ab83e3001a2e884b4cfe80"
private const val C_ABI_FOUNDATION_C_SHA256 =
    "b9da8e0b82f94299ac7ae9a3f76cb7d1b51f5b369293c2a6a7661e84c715c06a"
private const val C_ABI_FOUNDATION_CPP_SHA256 =
    "518864259613c14a86f39ef5443bcd0a94bfded4fb808fefac71a67b95ba193e"
private const val C_ABI_LIFECYCLE_C_SHA256 =
    "a2242fe55aca9f33f8a66d8c28d62ed1993c910a60c5b2fc66d83a950071f72d"
private const val C_ABI_LIFECYCLE_CPP_SHA256 =
    "482211a457fffe36f7e088b13465474713288fc1006afc1dd61519f73807ffa5"

private const val AGENT_PACKAGE = "io.github.codex_agent_labs.codexmobile.agent/"
private const val C_API_TEST_PACKAGE = "macosArm64Test.io.github.codex_agent_labs.codexmobile.capi."
private const val C_LIFECYCLE_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCLifecycleTest#projectsCanonicalLifecycleAndQuiescesEveryCallback[macosArm64]"
private const val C_PREPARE_FAILURE_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCLifecycleTest#projectsStructuredPrepareFailureAndQuiescesFailedHost[macosArm64]"
private const val C_VALUE_CONVERSATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCValueProjectionTest#projectsEveryConversationStatusAndFailureExactly[macosArm64]"
private const val C_VALUE_HOST_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCValueProjectionTest#projectsMissingHostStateVariantsAndPayloadsExactly[macosArm64]"

internal data class CAbiBootstrapClaimSpec(
    val owner: String,
    val kind: String,
    val abi: String,
    val canonicalSignatureReference: String?,
    val headerReferences: List<String>,
    val consumerReferences: List<String>,
    val publicSymbols: List<String>,
    val nativeTestIds: List<String>,
)

internal data class CAbiBootstrapClaim(
    val capabilityKey: String,
    val headerReferences: List<String>,
    val consumerReferences: List<String>,
    val publicSymbols: List<String>,
    val nativeTestIds: List<String>,
)

private fun claim(
    owner: String,
    kind: String,
    member: String,
    headerReferences: List<String>,
    canonicalSignatureReference: String? = null,
    consumerReferences: List<String> = headerReferences,
    publicSymbols: List<String>,
    nativeTestIds: List<String>,
): CAbiBootstrapClaimSpec = CAbiBootstrapClaimSpec(
    owner = AGENT_PACKAGE + owner,
    kind = kind,
    abi = AGENT_PACKAGE + member,
    canonicalSignatureReference = canonicalSignatureReference,
    headerReferences = headerReferences,
    consumerReferences = consumerReferences,
    publicSymbols = publicSymbols,
    nativeTestIds = nativeTestIds,
)

internal val cAbiBootstrapClaimSpecs: List<CAbiBootstrapClaimSpec> = buildList {
    val conversationStatus = "codex_agent_conversation_state_status"
    val conversationFailure = "codex_agent_conversation_state_failure"
    add(claim(
        "AgentConversationState", "property", "AgentConversationState.failure",
        listOf(conversationFailure), publicSymbols = listOf(conversationFailure),
        nativeTestIds = listOf(C_VALUE_CONVERSATION_TEST),
    ))
    add(claim(
        "AgentConversationState", "property", "AgentConversationState.status",
        listOf(conversationStatus), publicSymbols = listOf(conversationStatus),
        nativeTestIds = listOf(C_LIFECYCLE_TEST, C_VALUE_CONVERSATION_TEST),
    ))
    listOf(
        "CANCELLING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN",
        "CLOSED" to "CODEX_AGENT_CONVERSATION_STATUS_CLOSED",
        "FAILED" to "CODEX_AGENT_CONVERSATION_STATUS_FAILED",
        "NEW" to "CODEX_AGENT_CONVERSATION_STATUS_NEW",
        "OPENING" to "CODEX_AGENT_CONVERSATION_STATUS_OPENING",
        "READY" to "CODEX_AGENT_CONVERSATION_STATUS_READY",
        "RELOADING" to "CODEX_AGENT_CONVERSATION_STATUS_RELOADING",
        "RUNNING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN",
        "STARTING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN",
    ).forEach { (entry, macro) ->
        add(claim(
            "AgentConversationStatus", "enum-entry", "AgentConversationStatus.$entry",
            listOf(macro, conversationStatus), publicSymbols = listOf(conversationStatus),
            nativeTestIds = listOf(C_VALUE_CONVERSATION_TEST),
        ))
    }
    add(claim(
        "CodexAgent", "property", "CodexAgent.conversations",
        listOf("codex_agent_agent_conversations"),
        publicSymbols = listOf("codex_agent_agent_conversations"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexConversations", "function", "CodexConversations.open",
        listOf("codex_agent_conversations_open"),
        publicSymbols = listOf("codex_agent_conversations_open"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexConversations", "property", "CodexConversations.active",
        listOf(
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            "codex_agent_active_conversation",
        ),
        publicSymbols = listOf(
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            "codex_agent_active_conversation",
        ),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    listOf(
        Triple("cancelTurn", "codex_agent_conversation_cancel_turn", "function"),
        Triple("close", "codex_agent_conversation_close", "function"),
        Triple("send", "codex_agent_conversation_send", "function"),
        Triple("state", "codex_agent_conversation_state_get", "property"),
    ).forEach { (member, symbol, kind) ->
        val symbols = if (member == "state") {
            listOf(symbol, "codex_agent_conversation_state_subscribe")
        } else {
            listOf(symbol)
        }
        add(claim(
            "CodexConversation", kind, "CodexConversation.$member",
            symbols,
            canonicalSignatureReference = if (member == "send") "send(kotlin.String){}[0]" else null,
            publicSymbols = symbols,
            nativeTestIds = listOf(C_LIFECYCLE_TEST),
        ))
    }
    listOf(
        Triple("code", "codex_agent_failure_code_copy", listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST)),
        Triple(
            "isRecoverable",
            "codex_agent_failure_is_recoverable",
            listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST, C_VALUE_HOST_TEST),
        ),
        Triple("message", "codex_agent_failure_message_copy", listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST)),
    ).forEach { (member, symbol, tests) ->
        add(claim(
            "CodexFailure", "property", "CodexFailure.$member",
            listOf(symbol), publicSymbols = listOf(symbol), nativeTestIds = tests,
        ))
    }
    fun hostState(
        owner: String,
        kind: String,
        member: String,
        macro: String,
        payloadSymbols: List<String>,
        tests: List<String>,
    ) {
        val symbols = listOf("codex_agent_host_state_kind") + payloadSymbols
        add(claim(
            owner, kind, member,
            listOf(macro) + symbols,
            publicSymbols = symbols,
            nativeTestIds = tests,
        ))
    }
    hostState(
        "CodexHostState.Closed", "object", "CodexHostState.Closed",
        "CODEX_AGENT_HOST_STATE_CLOSED", emptyList(), listOf(C_LIFECYCLE_TEST),
    )
    hostState(
        "CodexHostState.Failed", "constructor", "CodexHostState.Failed.<init>",
        "CODEX_AGENT_HOST_STATE_FAILED",
        listOf(
            "codex_agent_host_state_has_workspace",
            "codex_agent_host_state_workspace_path_copy",
            "codex_agent_host_state_workspace_display_name_copy",
            "codex_agent_host_state_failure",
        ),
        listOf(C_PREPARE_FAILURE_TEST, C_VALUE_HOST_TEST),
    )
    add(claim(
        "CodexHostState.Failed", "property", "CodexHostState.Failed.failure",
        listOf("codex_agent_host_state_failure"),
        publicSymbols = listOf("codex_agent_host_state_failure"),
        nativeTestIds = listOf(C_PREPARE_FAILURE_TEST, C_VALUE_HOST_TEST),
    ))
    hostState(
        "CodexHostState.New", "object", "CodexHostState.New",
        "CODEX_AGENT_HOST_STATE_NEW", emptyList(), listOf(C_LIFECYCLE_TEST),
    )
    hostState(
        "CodexHostState.Preparing", "constructor", "CodexHostState.Preparing.<init>",
        "CODEX_AGENT_HOST_STATE_PREPARING",
        listOf(
            "codex_agent_host_state_has_workspace",
            "codex_agent_host_state_workspace_path_copy",
            "codex_agent_host_state_workspace_display_name_copy",
        ),
        listOf(C_VALUE_HOST_TEST),
    )
    hostState(
        "CodexHostState.Ready", "constructor", "CodexHostState.Ready.<init>",
        "CODEX_AGENT_HOST_STATE_READY", listOf("codex_agent_host_state_agent"),
        listOf(C_LIFECYCLE_TEST),
    )
    add(claim(
        "CodexHostState.Ready", "property", "CodexHostState.Ready.agent",
        listOf("codex_agent_host_state_agent"),
        publicSymbols = listOf("codex_agent_host_state_agent"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    hostState(
        "CodexHostState.Restoring", "object", "CodexHostState.Restoring",
        "CODEX_AGENT_HOST_STATE_RESTORING", emptyList(), listOf(C_VALUE_HOST_TEST),
    )
    hostState(
        "CodexHostState.WorkspaceRequired", "constructor", "CodexHostState.WorkspaceRequired.<init>",
        "CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED",
        listOf(
            "codex_agent_host_state_requirement_reason",
            "codex_agent_host_state_requirement_message_copy",
        ),
        listOf(C_VALUE_HOST_TEST),
    )
    listOf(
        Triple("close", "codex_agent_host_close", "function"),
        Triple("selectWorkspace", "codex_agent_host_select_workspace", "function"),
        Triple("lifecycleState", "codex_agent_host_state_get", "property"),
    ).forEach { (member, symbol, kind) ->
        val symbols = if (member == "lifecycleState") {
            listOf(symbol, "codex_agent_host_state_subscribe")
        } else {
            listOf(symbol)
        }
        val tests = if (member == "selectWorkspace") {
            listOf(C_LIFECYCLE_TEST, C_PREPARE_FAILURE_TEST)
        } else {
            listOf(C_LIFECYCLE_TEST)
        }
        add(claim(
            "CodexHost", kind, "CodexHost.$member",
            symbols, publicSymbols = symbols, nativeTestIds = tests,
        ))
    }
    add(claim(
        "CodexPathWorkspaceSelection", "constructor", "CodexPathWorkspaceSelection.<init>",
        listOf("codex_agent_path_workspace_selection_t", "codex_agent_host_select_workspace"),
        publicSymbols = listOf("codex_agent_host_select_workspace"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexPathWorkspaceSelection", "property", "CodexPathWorkspaceSelection.path",
        listOf("codex_agent_string_view_t path;", "codex_agent_host_select_workspace"),
        consumerReferences = listOf("workspace_selection.path", "codex_agent_host_select_workspace"),
        publicSymbols = listOf("codex_agent_host_select_workspace"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
}.sortedWith(compareBy(CAbiBootstrapClaimSpec::owner, CAbiBootstrapClaimSpec::kind, CAbiBootstrapClaimSpec::abi))

internal fun deriveCAbiBootstrapClaims(
    canonicalKeys: List<String>,
    headerText: String,
    consumerText: String,
    exportedSymbols: Set<String>,
    passedNativeTestIds: Set<String>,
    claimSpecs: List<CAbiBootstrapClaimSpec> = cAbiBootstrapClaimSpecs,
): List<CAbiBootstrapClaim> {
    check(canonicalKeys.size == C_ABI_CANONICAL_CAPABILITY_COUNT &&
        canonicalKeys.size == canonicalKeys.distinct().size && canonicalKeys == canonicalKeys.sorted()) {
        "C ABI bootstrap requires the exact sorted 556-capability canonical inventory"
    }
    check(claimSpecs.size == C_ABI_BOOTSTRAP_CAPABILITY_COUNT &&
        claimSpecs.distinctBy { Triple(it.owner, it.kind, it.abi) }.size ==
        C_ABI_BOOTSTRAP_CAPABILITY_COUNT) {
        "C ABI bootstrap claim specifications are missing or duplicated"
    }
    val records = canonicalKeys.groupBy(::cAbiApiIdentity)
    val claims = claimSpecs.map { spec ->
        val identity = Triple(spec.owner, spec.kind, spec.abi)
        val candidates = records[identity].orEmpty().filter { key ->
            spec.canonicalSignatureReference?.let(key::contains) ?: true
        }
        check(candidates.size == 1) {
            "Missing or ambiguous exact canonical C ABI capability $identity " +
                "signature=${spec.canonicalSignatureReference}: $candidates"
        }
        val key = candidates.single()
        listOf(spec.headerReferences, spec.consumerReferences, spec.publicSymbols, spec.nativeTestIds).forEach {
            check(it.isNotEmpty() && it == it.distinct()) { "C ABI claim contains empty or duplicate evidence: $key" }
        }
        spec.headerReferences.forEach { reference ->
            check(headerText.containsCReference(reference)) {
                "Missing C ABI public header reference $reference for $key"
            }
        }
        spec.consumerReferences.forEach { reference ->
            check(consumerText.containsCReference(reference)) {
                "Missing compiled C consumer reference $reference for $key"
            }
        }
        spec.publicSymbols.forEach { symbol ->
            check(symbol in exportedSymbols) { "Missing exported C ABI symbol $symbol for $key" }
        }
        spec.nativeTestIds.forEach { testId ->
            check(testId in passedNativeTestIds) { "Missing passed Native C ABI test $testId for $key" }
        }
        CAbiBootstrapClaim(
            capabilityKey = key,
            headerReferences = spec.headerReferences.sorted(),
            consumerReferences = spec.consumerReferences.sorted(),
            publicSymbols = spec.publicSymbols.sorted(),
            nativeTestIds = spec.nativeTestIds.sorted(),
        )
    }.sortedBy(CAbiBootstrapClaim::capabilityKey)
    val keys = claims.map(CAbiBootstrapClaim::capabilityKey)
    check(keys.size == C_ABI_BOOTSTRAP_CAPABILITY_COUNT && keys.size == keys.distinct().size) {
        "C ABI bootstrap capability selection is not exact"
    }
    check(keys.sortedNewlineSha256() == C_ABI_BOOTSTRAP_CAPABILITY_SHA256) {
        "C ABI bootstrap capability signature drift: ${keys.sortedNewlineSha256()}"
    }
    return claims
}

private fun cAbiApiIdentity(key: String): Triple<String, String, String> {
    val ownerPrefix = "common|owner="
    val kindMarker = "|kind="
    val abiMarker = "|abi="
    check(key.startsWith(ownerPrefix)) { "Invalid canonical C ABI key owner: $key" }
    val kindIndex = key.indexOf(kindMarker, ownerPrefix.length)
    val abiIndex = key.indexOf(abiMarker, kindIndex + kindMarker.length)
    val abiEnd = key.indexOf('|', abiIndex + abiMarker.length)
    check(kindIndex > ownerPrefix.length && abiIndex > kindIndex && abiEnd > abiIndex) {
        "Invalid canonical C ABI key shape: $key"
    }
    return Triple(
        key.substring(ownerPrefix.length, kindIndex),
        key.substring(kindIndex + kindMarker.length, abiIndex),
        key.substring(abiIndex + abiMarker.length, abiEnd),
    )
}

private fun List<String>.sortedNewlineSha256(): String = MessageDigest.getInstance("SHA-256")
    .digest(sorted().joinToString(separator = "", transform = { "$it\n" }).encodeToByteArray())
    .joinToString("") { byte -> "%02x".format(byte) }

private fun exactExportPolicy(file: File): Set<String> {
    check(file.releaseDigest() == C_ABI_MACOS_EXPORTS_SHA256) { "Reviewed macOS C ABI export policy drift" }
    val rows = file.readLines().filter(String::isNotBlank)
    check(rows.size == 50 && rows == rows.sorted() && rows.size == rows.distinct().size &&
        rows.all { it.startsWith("_codex_agent_") }) {
        "macOS C ABI export policy must contain the exact sorted 50-symbol inventory"
    }
    return rows.mapTo(sortedSetOf()) { it.removePrefix("_") }
}

private fun String.containsCReference(reference: String): Boolean = Regex(
    "(?<![A-Za-z0-9_])${Regex.escape(reference)}(?![A-Za-z0-9_])",
).containsMatchIn(this)

private fun normalizedCodexSymbols(output: String): Set<String> {
    val symbols = output.lineSequence()
    .map(String::trim)
    .filter(String::isNotEmpty)
    .map { it.substringAfterLast(' ').removePrefix("_") }
    .filter { it.startsWith("codex_agent_") }
    .toList()
    check(symbols.size == symbols.distinct().size) { "Duplicated C ABI symbols in tool output: $symbols" }
    return symbols.toCollection(sortedSetOf())
}

@DisableCachingByDefault(because = "Compiles and executes consumers with the installed macOS toolchain")
abstract class GenerateCAbiBootstrapEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalApiReport: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val reviewedHeader: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val cinteropDefinition: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val exportPolicy: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val foundationCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val foundationCppConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lifecycleCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lifecycleCppConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val releaseLibrary: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val generatedHeader: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val nativeTestExecutable: RegularFileProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeTestResults: DirectoryProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeMainSources: DirectoryProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeTestSources: DirectoryProperty

    @get:LocalState abstract val consumerOutputDirectory: DirectoryProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        check(System.getProperty("os.name").lowercase().contains("mac") &&
            System.getProperty("os.arch").lowercase() in setOf("aarch64", "arm64")) {
            "C ABI bootstrap evidence requires a macOS Arm64 host"
        }

        val canonical = readCrossLanguageCanonicalApiEvidence(
            canonicalApiReport.get().asFile,
            canonicalCoverageReceipt.get().asFile,
        )
        val header = reviewedHeader.get().asFile.also {
            check(it.releaseDigest() == C_ABI_HEADER_SHA256) { "Reviewed C ABI header drift" }
        }
        val cinterop = cinteropDefinition.get().asFile.also {
            check(it.releaseDigest() == C_ABI_CINTEROP_SHA256) { "Reviewed C ABI cinterop definition drift" }
        }
        val exports = exactExportPolicy(exportPolicy.get().asFile)
        val foundationC = foundationCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_FOUNDATION_C_SHA256) { "Reviewed C foundation consumer drift" }
        }
        val foundationCpp = foundationCppConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_FOUNDATION_CPP_SHA256) { "Reviewed C++ foundation consumer drift" }
        }
        val lifecycleC = lifecycleCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_LIFECYCLE_C_SHA256) { "Reviewed C lifecycle consumer drift" }
        }
        val lifecycleCpp = lifecycleCppConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_LIFECYCLE_CPP_SHA256) { "Reviewed C++ lifecycle consumer drift" }
        }
        val library = releaseLibrary.get().asFile
        val generated = generatedHeader.get().asFile
        val nativeExecutable = nativeTestExecutable.get().asFile
        listOf(library, generated, nativeExecutable).forEach {
            check(it.isFile && !Files.isSymbolicLink(it.toPath()) && it.length() > 0L) {
                "C ABI bootstrap artifact is missing, empty, or symbolic: $it"
            }
        }

        val testReports = nativeTestResults.get().asFile.listFiles()
            .orEmpty().filter { it.isFile && it.extension == "xml" && ".capi." in it.name }.sorted()
        check(testReports.isNotEmpty()) { "C ABI Native JUnit reports are missing" }
        val nativeTests = testReports.flatMap(::readCanonicalTestReport)
        val duplicateTests = nativeTests.groupingBy(CanonicalTestResult::testId).eachCount()
            .filterValues { it != 1 }.keys.sorted()
        check(duplicateTests.isEmpty()) { "Duplicate C ABI Native test identities: $duplicateTests" }
        check(nativeTests.all { it.status == CanonicalTestStatus.PASSED }) {
            "C ABI Native test inventory contains skipped or failed tests"
        }
        val passedTests = nativeTests.mapTo(sortedSetOf(), CanonicalTestResult::testId)

        val work = consumerOutputDirectory.get().asFile
        check(work.deleteRecursively() || !work.exists()) { "Could not clear C ABI consumer work directory" }
        check(work.mkdirs()) { "Could not create C ABI consumer work directory" }
        val clang = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "--find", "clang")).trim()
        val clangCpp = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "--find", "clang++")).trim()
        val sdk = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"),
        ).trim()
        val clangVersion = processes.captureReleaseProcess(listOf(clang, "--version")).trim()
        val include = header.parentFile.absolutePath
        val rpath = library.parentFile.absolutePath
        val consumers = listOf(
            compileConsumer("c11-foundation", clang, "c11", foundationC, work, include, library, rpath, sdk, true),
            compileConsumer("c11-lifecycle", clang, "c11", lifecycleC, work, include, library, rpath, sdk, true),
            compileConsumer(
                "c++17-foundation", clangCpp, "c++17", foundationCpp,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c++17-lifecycle", clangCpp, "c++17", lifecycleCpp,
                work, include, library, rpath, sdk, false,
            ),
        )

        val defined = normalizedCodexSymbols(
            processes.captureReleaseProcess(listOf("/usr/bin/nm", "-gU", library.absolutePath)),
        )
        check(defined == exports) { "Dylib/export-policy mismatch: missing=${exports - defined} extra=${defined - exports}" }
        val lifecycleImports = normalizedCodexSymbols(
            processes.captureReleaseProcess(
                listOf("/usr/bin/nm", "-u", consumers[1].artifact.absolutePath),
            ),
        )
        check(lifecycleImports == exports) {
            "C lifecycle consumer import mismatch: missing=${exports - lifecycleImports} extra=${lifecycleImports - exports}"
        }
        val fileIdentity = processes.captureReleaseProcess(
            listOf("/usr/bin/file", "-b", library.absolutePath),
        ).trim()
        check(fileIdentity == "Mach-O 64-bit dynamically linked shared library arm64") {
            "C ABI release library is not Mach-O Arm64: $fileIdentity"
        }
        val installNames = processes.captureReleaseProcess(
            listOf("/usr/bin/otool", "-D", library.absolutePath),
        )
            .lineSequence().map(String::trim).filter(String::isNotEmpty).drop(1).toList()
        check(installNames == listOf("@rpath/libcodex_agent.dylib")) {
            "Unexpected C ABI dylib install name: $installNames"
        }
        val linkedIdentity = processes.captureReleaseProcess(
            listOf("/usr/bin/otool", "-L", library.absolutePath),
        ).lineSequence().map(String::trim).firstOrNull { it.startsWith("@rpath/libcodex_agent.dylib ") }
        check(linkedIdentity ==
            "@rpath/libcodex_agent.dylib (compatibility version 1.0.0, current version 1.1.0)") {
            "Unexpected C ABI dylib loader versions: $linkedIdentity"
        }

        val claims = deriveCAbiBootstrapClaims(
            canonical.memberKeys,
            header.readText(),
            lifecycleC.readText(),
            exports,
            passedTests,
        )
        val observedKeys = claims.map(CAbiBootstrapClaim::capabilityKey)
        val missingKeys = (canonical.memberKeys.toSet() - observedKeys.toSet()).sorted()
        check(missingKeys.size == C_ABI_CANONICAL_CAPABILITY_COUNT - C_ABI_BOOTSTRAP_CAPABILITY_COUNT &&
            observedKeys.toSet().intersect(missingKeys.toSet()).isEmpty() &&
            (observedKeys + missingKeys).sorted() == canonical.memberKeys) {
            "C ABI bootstrap observed/missing partition is not exact"
        }

        val report = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive(C_ABI_BOOTSTRAP_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed"))
            put("milestone", JsonPrimitive("D093"))
            put("language", JsonPrimitive("c-abi"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
                put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
                put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
                put("capabilityCount", JsonPrimitive(canonical.memberKeys.size))
                put("observedCapabilityCount", JsonPrimitive(observedKeys.size))
                put("observedCapabilitySha256", JsonPrimitive(observedKeys.sortedNewlineSha256()))
                put("observedCapabilityKeys", JsonArray(observedKeys.map(::JsonPrimitive)))
                put("missingCapabilityKeys", JsonArray(missingKeys.map(::JsonPrimitive)))
            })
            put("toolchain", buildJsonObject {
                put("clang", JsonPrimitive(clang))
                put("clangCpp", JsonPrimitive(clangCpp))
                put("clangVersion", JsonPrimitive(clangVersion))
                put("macosSdk", JsonPrimitive(sdk))
            })
            put("artifacts", buildJsonObject {
                put("reviewedHeaderSha256", JsonPrimitive(header.releaseDigest()))
                put("cinteropDefinitionSha256", JsonPrimitive(cinterop.releaseDigest()))
                put("exportPolicySha256", JsonPrimitive(exportPolicy.get().asFile.releaseDigest()))
                put("generatedHeaderSha256", JsonPrimitive(generated.releaseDigest()))
                put("releaseLibrarySha256", JsonPrimitive(library.releaseDigest()))
                put("nativeTestExecutableSha256", JsonPrimitive(nativeExecutable.releaseDigest()))
                put("nativeMainSourcesSha256", JsonPrimitive(nativeMainSources.get().asFile.crossLanguageTreeDigest()))
                put("nativeTestSourcesSha256", JsonPrimitive(nativeTestSources.get().asFile.crossLanguageTreeDigest()))
                put("nativeTestResultsSha256", JsonPrimitive(nativeTestResults.get().asFile.crossLanguageTreeDigest()))
                put("fileIdentity", JsonPrimitive(fileIdentity))
                put("installName", JsonPrimitive(installNames.single()))
            })
            put("compilerConsumers", buildJsonArray {
                consumers.forEach { consumer ->
                    add(buildJsonObject {
                        put("id", JsonPrimitive(consumer.id))
                        put("sourceSha256", JsonPrimitive(consumer.source.releaseDigest()))
                        put("artifactSha256", JsonPrimitive(consumer.artifact.releaseDigest()))
                        put("executed", JsonPrimitive(consumer.executed))
                    })
                }
            })
            put("linkedPublicSymbols", JsonArray(exports.sorted().map(::JsonPrimitive)))
            put("nativeTests", buildJsonArray {
                nativeTests.sortedBy(CanonicalTestResult::testId).forEach { test ->
                    add(buildJsonObject {
                        put("testId", JsonPrimitive(test.testId))
                        put("status", JsonPrimitive("passed"))
                    })
                }
            })
            put("claims", buildJsonArray {
                claims.forEach { claim ->
                    add(buildJsonObject {
                        put("capabilityKey", JsonPrimitive(claim.capabilityKey))
                        put("headerReferences", JsonArray(claim.headerReferences.map(::JsonPrimitive)))
                        put("consumerReferences", JsonArray(claim.consumerReferences.map(::JsonPrimitive)))
                        put("publicSymbols", JsonArray(claim.publicSymbols.map(::JsonPrimitive)))
                        put("nativeTestIds", JsonArray(claim.nativeTestIds.map(::JsonPrimitive)))
                    })
                }
            })
        }
        output.atomicWriteJson(report)
        check(output.readText() == releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), report) + "\n") {
            "C ABI bootstrap evidence is not canonically encoded"
        }
    }

    private fun compileConsumer(
        id: String,
        compiler: String,
        standard: String,
        source: File,
        work: File,
        include: String,
        library: File,
        rpath: String,
        sdk: String,
        execute: Boolean,
    ): CompiledCAbiConsumer {
        val artifact = work.resolve(if (execute) id else "$id.o")
        val command = mutableListOf(
            compiler,
            "-std=$standard",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-arch",
            "arm64",
            "-isysroot",
            sdk,
            "-I$include",
            source.absolutePath,
        )
        if (execute) {
            command += listOf(library.absolutePath, "-Wl,-rpath,$rpath", "-o", artifact.absolutePath)
        } else {
            command += listOf("-c", "-o", artifact.absolutePath)
        }
        processes.captureReleaseProcess(command)
        check(artifact.isFile && artifact.length() > 0L) { "C ABI consumer artifact is empty: $id" }
        if (execute) processes.captureReleaseProcess(listOf(artifact.absolutePath))
        return CompiledCAbiConsumer(id, source, artifact, execute)
    }
}

private data class CompiledCAbiConsumer(
    val id: String,
    val source: File,
    val artifact: File,
    val executed: Boolean,
)
