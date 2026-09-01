import java.io.File
import java.nio.file.Files
import org.jetbrains.org.objectweb.asm.AnnotationVisitor
import org.jetbrains.org.objectweb.asm.ClassReader
import org.jetbrains.org.objectweb.asm.ClassVisitor
import org.jetbrains.org.objectweb.asm.MethodVisitor
import org.jetbrains.org.objectweb.asm.Opcodes

internal const val COVERS_API_ANNOTATION_DESCRIPTOR =
    "Lio/github/codex_agent_labs/codexagent/agent/CoversApi;"
private val JUNIT_TEST_ANNOTATION_DESCRIPTORS = setOf(
    "Lorg/junit/Test;",
    "Lorg/junit/jupiter/api/Test;",
)

internal data class CoveredApiClaim(
    val testId: String,
    val memberTokens: List<String>,
)

internal data class ResolvedCoveredApiClaim(
    val testId: String,
    val memberKeys: List<String>,
)

internal data class CanonicalApiCoverage(
    val memberKeys: List<String>,
    val claims: List<ResolvedCoveredApiClaim>,
)

internal fun readCoveredApiClaims(
    classesDirectory: File,
    annotationDescriptor: String = COVERS_API_ANNOTATION_DESCRIPTOR,
): List<CoveredApiClaim> {
    check(classesDirectory.isDirectory) { "Canonical test classes directory is missing" }
    check(annotationDescriptor.startsWith('L') && annotationDescriptor.endsWith(';')) {
        "CoversApi annotation descriptor is invalid"
    }
    val classFiles = classesDirectory.walkTopDown()
        .onEnter { !Files.isSymbolicLink(it.toPath()) }
        .filter { it.isFile && !Files.isSymbolicLink(it.toPath()) && it.extension == "class" }
        .sortedBy { it.relativeTo(classesDirectory).invariantSeparatorsPath }
        .toList()
    check(classFiles.isNotEmpty()) { "Canonical test classes are missing" }

    return buildList {
        classFiles.forEach { classFile ->
            var className = ""
            ClassReader(classFile.readBytes()).accept(object : ClassVisitor(Opcodes.ASM9) {
                override fun visit(
                    version: Int,
                    access: Int,
                    name: String,
                    signature: String?,
                    superName: String?,
                    interfaces: Array<out String>?,
                ) {
                    className = name.replace('/', '.')
                }

                override fun visitMethod(
                    access: Int,
                    name: String,
                    descriptor: String,
                    signature: String?,
                    exceptions: Array<out String>?,
                ): MethodVisitor = object : MethodVisitor(Opcodes.ASM9) {
                    private var isTest = false
                    private var coverageAnnotations = 0
                    private val memberTokens = mutableListOf<String>()

                    override fun visitAnnotation(descriptor: String, visible: Boolean): AnnotationVisitor? {
                        if (descriptor in JUNIT_TEST_ANNOTATION_DESCRIPTORS) isTest = true
                        if (descriptor != annotationDescriptor) return null
                        coverageAnnotations += 1
                        return object : AnnotationVisitor(Opcodes.ASM9) {
                            override fun visitArray(name: String?): AnnotationVisitor {
                                check(name == "members") { "CoversApi has an unexpected argument: $name" }
                                return object : AnnotationVisitor(Opcodes.ASM9) {
                                    override fun visit(name: String?, value: Any?) {
                                        check(value is String) { "CoversApi members must be strings" }
                                        memberTokens += value
                                    }
                                }
                            }
                        }
                    }

                    override fun visitEnd() {
                        if (coverageAnnotations == 0) return
                        val testId = "$className#$name"
                        check(coverageAnnotations == 1) { "Duplicate CoversApi annotation: $testId" }
                        check(isTest) { "CoversApi is attached to a non-test method: $testId" }
                        check(memberTokens.isNotEmpty()) { "CoversApi has no member tokens: $testId" }
                        add(CoveredApiClaim(testId, memberTokens.toList()))
                    }
                }
            }, ClassReader.SKIP_CODE or ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES)
        }
    }
}

internal fun verifyCrossLanguageApiCoverage(
    discoveredMemberKeys: Iterable<String>,
    claims: Iterable<CoveredApiClaim>,
    testResults: Iterable<CanonicalTestResult>,
): CanonicalApiCoverage {
    val discovered = discoveredMemberKeys.toList()
    check(discovered.isNotEmpty()) { "Compiler-derived cross-language API is empty" }
    requireUniqueNonBlank(discovered, "Compiler-derived member")
    val expectedByToken = discovered.map { memberKey ->
        crossLanguageApiCoverageToken(memberKey) to memberKey
    }.also { indexedMembers ->
        requireUniqueNonBlank(indexedMembers.map(Pair<String, String>::first), "Compiler-derived coverage token")
    }.toMap()

    val claimList = claims.toList()
    val duplicateClaimTests = claimList.groupingBy(CoveredApiClaim::testId).eachCount()
        .filterValues { it != 1 }.keys.sorted()
    check(duplicateClaimTests.isEmpty()) { "Duplicate CoversApi test claims: $duplicateClaimTests" }
    claimList.forEach { claim ->
        check(claim.testId.isNotBlank()) { "CoversApi test identity is blank" }
        check(claim.memberTokens.isNotEmpty()) { "CoversApi has no member tokens: ${claim.testId}" }
        claim.memberTokens.forEach { token -> requireExactCoverageToken(token, claim.testId) }
        requireUniqueNonBlank(claim.memberTokens, "CoversApi member token for ${claim.testId}")
    }
    val claimedTokens = claimList.flatMap { claim -> claim.memberTokens.map { it to claim.testId } }

    val resultList = testResults.toList()
    val duplicateResults = resultList.groupingBy(CanonicalTestResult::testId).eachCount()
        .filterValues { it != 1 }.keys.sorted()
    check(duplicateResults.isEmpty()) { "Duplicate canonical test results: $duplicateResults" }
    val resultsById = resultList.associateBy(CanonicalTestResult::testId)
    claimList.forEach { claim ->
        when (resultsById[claim.testId]?.status) {
            null -> error("CoversApi test was not executed: ${claim.testId}")
            CanonicalTestStatus.SKIPPED -> error("CoversApi test was skipped or disabled: ${claim.testId}")
            CanonicalTestStatus.FAILED -> error("CoversApi test failed: ${claim.testId}")
            CanonicalTestStatus.PASSED -> Unit
        }
    }

    val covered = claimedTokens.map(Pair<String, String>::first).toSet()
    val missing = (expectedByToken.keys - covered).sorted().map { token ->
        "$token -> ${expectedByToken.getValue(token)}"
    }
    val claimTestsByToken = claimedTokens.groupBy(
        keySelector = Pair<String, String>::first,
        valueTransform = Pair<String, String>::second,
    ).mapValues { (_, tests) -> tests.distinct().sorted() }
    val stale = (covered - expectedByToken.keys).sorted().map { token ->
        "$token <- ${claimTestsByToken.getValue(token)}"
    }
    check(missing.isEmpty() && stale.isEmpty()) {
        "Cross-language API coverage mismatch: missing=$missing stale=$stale"
    }
    return CanonicalApiCoverage(
        memberKeys = discovered.sorted(),
        claims = claimList.map { claim ->
            ResolvedCoveredApiClaim(
                testId = claim.testId,
                memberKeys = claim.memberTokens.map { token -> expectedByToken.getValue(token) }.sorted(),
            )
        }.sortedBy(ResolvedCoveredApiClaim::testId),
    )
}

internal fun crossLanguageApiCoverageToken(memberKey: String): String {
    val ownerPrefix = "common|owner="
    val kindPrefix = "|kind="
    val abiPrefix = "|abi="
    check(memberKey.startsWith(ownerPrefix)) { "Compiler-derived member key has an invalid owner: $memberKey" }
    val kindStart = memberKey.indexOf(kindPrefix, ownerPrefix.length)
    val abiStart = memberKey.indexOf(abiPrefix, kindStart + kindPrefix.length)
    val abiEnd = memberKey.indexOf('|', abiStart + abiPrefix.length)
    check(kindStart > ownerPrefix.length && abiStart > kindStart && abiEnd > abiStart) {
        "Compiler-derived member key has an invalid shape: $memberKey"
    }
    val owner = memberKey.substring(ownerPrefix.length, kindStart)
    val kind = memberKey.substring(kindStart + kindPrefix.length, abiStart)
    check(kind in setOf("constructor", "function", "property", "enum-entry", "object")) {
        "Compiler-derived member key has an unsupported kind: $kind"
    }
    val abiName = memberKey.substring(abiStart + abiPrefix.length, abiEnd)
    val memberName = if (kind == "object") {
        check(abiName == owner && memberKey.substring(abiEnd + 1).isNotBlank()) {
            "Compiler-derived object key has an invalid ABI identity: $memberKey"
        }
        owner.substringAfterLast('/').substringAfterLast('.')
    } else {
        abiName.removePrefix("$owner.").also { name ->
            check(name != abiName && name.isNotBlank()) {
                "Compiler-derived member key has an invalid ABI name: $memberKey"
            }
        }
    }
    val ownerName = owner.substringAfterLast('/')
    check(ownerName.isNotBlank()) { "Compiler-derived member key has an invalid owner: $memberKey" }
    return "api-v1:$ownerName#$kind:$memberName#sha256:${memberKey.byteInputStream().releaseDigest()}"
}

private fun requireExactCoverageToken(token: String, testId: String) {
    val digestMarker = "#sha256:"
    val digestStart = token.lastIndexOf(digestMarker)
    val digest = token.substring((digestStart + digestMarker.length).coerceAtMost(token.length))
    check(
        token == token.trim() && token.startsWith("api-v1:") && digestStart > "api-v1:".length &&
            digest.length == 64 && digest.all { it in '0'..'9' || it in 'a'..'f' },
    ) { "CoversApi token is malformed for $testId: $token" }
    check('*' !in token && ".." !in token) {
        "CoversApi token must name one exact member for $testId: $token"
    }
}

private fun requireUniqueNonBlank(values: List<String>, label: String) {
    check(values.none(String::isBlank)) { "$label key is blank" }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label keys are duplicated: $duplicates" }
}
