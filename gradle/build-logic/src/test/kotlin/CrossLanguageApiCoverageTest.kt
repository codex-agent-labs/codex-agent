import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import org.jetbrains.org.objectweb.asm.ClassWriter
import org.jetbrains.org.objectweb.asm.Opcodes

class CrossLanguageApiCoverageTest {
    @Test
    fun `compiled CoversApi claims are read without reflection`() = withDirectory { root ->
        val classes = root.resolve("classes").apply { mkdir() }
        writeCoverageClass(
            classes.resolve("fixture/BinaryCoverageFixture.class"),
            FIXTURE_TOKENS,
            "fixture/BinaryCoverageFixture",
        )

        val claims = readCoveredApiClaims(classes, fixtureAnnotationDescriptor)

        assertEquals(
            listOf(CoveredApiClaim("fixture.BinaryCoverageFixture#covered", FIXTURE_TOKENS)),
            claims,
        )
    }

    @Test
    fun `compiled CoversApi claim reader handles the current API scale`() = withDirectory { root ->
        val classes = root.resolve("classes").apply { mkdir() }
        val tokens = List(556) { index ->
            "api-v1:Scale#function:m$index#sha256:${index.toString(16).padStart(64, '0')}"
        }
        writeCoverageClass(classes.resolve("fixture/ScaleCoverageTest.class"), tokens, "fixture/ScaleCoverageTest")

        assertEquals(
            listOf(CoveredApiClaim("fixture.ScaleCoverageTest#covered", tokens)),
            readCoveredApiClaims(classes, fixtureAnnotationDescriptor),
        )
    }

    @Test
    fun `compiled CoversApi claim must be attached to a test method`() = withDirectory { root ->
        val classes = root.resolve("classes").apply { mkdir() }
        copyClass(NonTestCoverageFixture::class.java, classes)

        val failure = assertFailsWith<IllegalStateException> {
            readCoveredApiClaims(classes, fixtureAnnotationDescriptor)
        }
        assertTrue(failure.message.orEmpty().contains("non-test method"))
    }

    @Test
    fun `JUnit reports distinguish passed skipped and failed tests`() = withDirectory { root ->
        val results = root.resolve("results").apply { mkdir() }
        writeReport(
            results.resolve("TEST-fixture.xml"),
            "passed" to "",
            "skipped" to "<skipped/>",
            "failed" to "<failure message=\"no\"/>",
        )

        assertEquals(
            listOf(
                CanonicalTestResult("fixture.CoverageTest#failed", CanonicalTestStatus.FAILED),
                CanonicalTestResult("fixture.CoverageTest#passed", CanonicalTestStatus.PASSED),
                CanonicalTestResult("fixture.CoverageTest#skipped", CanonicalTestStatus.SKIPPED),
            ),
            readCanonicalTestResults(results),
        )
    }

    @Test
    fun `coverage is exact unique and bound to successful execution`() {
        val testId = "fixture.CoverageTest#covered"
        val claims = listOf(CoveredApiClaim(testId, API_TOKENS))
        val passed = listOf(CanonicalTestResult(testId, CanonicalTestStatus.PASSED))

        val coverage = verifyCrossLanguageApiCoverage(API_KEYS, claims, passed)
        assertEquals(API_KEYS, coverage.memberKeys)
        assertEquals(listOf(ResolvedCoveredApiClaim(testId, API_KEYS)), coverage.claims)
        assertFailure(crossLanguageApiCoverageToken(API_KEY_THREE)) {
            verifyCrossLanguageApiCoverage(API_KEYS + API_KEY_THREE, claims, passed)
        }
        assertFailure("${crossLanguageApiCoverageToken(API_KEY_TWO)} <- [$testId]") {
            verifyCrossLanguageApiCoverage(listOf(API_KEY_ONE), claims, passed)
        }
        assertFailure("keys are duplicated") {
            verifyCrossLanguageApiCoverage(
                API_KEYS,
                listOf(CoveredApiClaim(testId, listOf(API_TOKENS.first(), API_TOKENS.first()))),
                passed,
            )
        }
        assertFailure("was not executed") {
            verifyCrossLanguageApiCoverage(API_KEYS, claims, emptyList())
        }
        assertFailure("skipped or disabled") {
            verifyCrossLanguageApiCoverage(
                API_KEYS,
                claims,
                listOf(CanonicalTestResult(testId, CanonicalTestStatus.SKIPPED)),
            )
        }
        assertFailure("test failed") {
            verifyCrossLanguageApiCoverage(
                API_KEYS,
                claims,
                listOf(CanonicalTestResult(testId, CanonicalTestStatus.FAILED)),
            )
        }
    }

    @Test
    fun `distinct successful tests may cover the same member`() {
        val first = "fixture.FirstTest#covered"
        val second = "fixture.SecondTest#covered"
        val coverage = verifyCrossLanguageApiCoverage(
            API_KEYS,
            listOf(
                CoveredApiClaim(first, listOf(API_TOKENS.first())),
                CoveredApiClaim(second, API_TOKENS),
            ),
            listOf(
                CanonicalTestResult(first, CanonicalTestStatus.PASSED),
                CanonicalTestResult(second, CanonicalTestStatus.PASSED),
            ),
        )

        assertEquals(API_KEYS, coverage.memberKeys)
    }

    @Test
    fun `coverage tokens bind to the entire compiler member key`() {
        val changedKey = API_KEY_ONE.replace("kotlin/Boolean!!", "kotlin/String!!")
        val originalToken = crossLanguageApiCoverageToken(API_KEY_ONE)
        val changedToken = crossLanguageApiCoverageToken(changedKey)
        val testId = "fixture.CoverageTest#covered"

        assertNotEquals(originalToken, changedToken)
        val failure = assertFailsWith<IllegalStateException> {
            verifyCrossLanguageApiCoverage(
                listOf(changedKey),
                listOf(CoveredApiClaim(testId, listOf(originalToken))),
                listOf(CanonicalTestResult(testId, CanonicalTestStatus.PASSED)),
            )
        }
        assertTrue(failure.message.orEmpty().contains("$changedToken -> $changedKey"), failure.message)
        assertTrue(failure.message.orEmpty().contains("$originalToken <- [$testId]"), failure.message)
    }

    @Test
    fun `object capability tokens are exact and participate in coverage`() {
        val token = crossLanguageApiCoverageToken(OBJECT_KEY)
        val testId = "fixture.CoverageTest#objectVariant"

        assertTrue(token.startsWith("api-v1:State.Ready#object:Ready#sha256:"), token)
        val coverage = verifyCrossLanguageApiCoverage(
            listOf(OBJECT_KEY),
            listOf(CoveredApiClaim(testId, listOf(token))),
            listOf(CanonicalTestResult(testId, CanonicalTestStatus.PASSED)),
        )
        assertEquals(listOf(OBJECT_KEY), coverage.memberKeys)
        assertFailure("invalid ABI identity") {
            crossLanguageApiCoverageToken(OBJECT_KEY.replace("abi=fixture/State.Ready", "abi=fixture/State.Other"))
        }
    }

    @Test
    fun `coverage tokens reject malformed groups and unknown exact members`() {
        val testId = "fixture.CoverageTest#covered"
        val passed = listOf(CanonicalTestResult(testId, CanonicalTestStatus.PASSED))
        fun verify(token: String) = verifyCrossLanguageApiCoverage(
            API_KEYS,
            listOf(CoveredApiClaim(testId, listOf(token))),
            passed,
        )

        assertFailure("token is malformed") { verify("api#one") }
        assertFailure("must name one exact member") {
            verify("api-v1:Host#function:*#sha256:${"0".repeat(64)}")
        }
        val unknown = "api-v1:Host#function:unknown#sha256:${"0".repeat(64)}"
        assertFailure("$unknown <- [$testId]") { verify(unknown) }
        assertFailure("Compiler-derived member keys are duplicated") {
            verifyCrossLanguageApiCoverage(
                listOf(API_KEY_ONE, API_KEY_ONE),
                listOf(CoveredApiClaim(testId, listOf(API_TOKENS.first()))),
                passed,
            )
        }
    }

    private fun assertFailure(message: String, block: () -> Unit) {
        val failure = assertFailsWith<IllegalStateException> { block() }
        assertTrue(failure.message.orEmpty().contains(message), failure.message)
    }

    private fun copyClass(type: Class<*>, destination: File) {
        val relativePath = type.name.replace('.', '/') + ".class"
        val output = destination.resolve(relativePath).apply { parentFile.mkdirs() }
        type.getResourceAsStream("/$relativePath").use { input ->
            output.outputStream().use { outputStream ->
                checkNotNull(input) { "Missing fixture class: $relativePath" }.copyTo(outputStream)
            }
        }
    }

    private fun writeCoverageClass(file: File, tokens: List<String>, className: String) {
        val writer = ClassWriter(0)
        writer.visit(Opcodes.V1_8, Opcodes.ACC_PUBLIC, className, null, "java/lang/Object", null)
        val method = writer.visitMethod(Opcodes.ACC_PUBLIC, "covered", "()V", null, null)
        method.visitAnnotation("Lorg/junit/Test;", true).visitEnd()
        val coverage = method.visitAnnotation(fixtureAnnotationDescriptor, false)
        val members = coverage.visitArray("members")
        tokens.forEach { token -> members.visit(null, token) }
        members.visitEnd()
        coverage.visitEnd()
        method.visitCode()
        method.visitInsn(Opcodes.RETURN)
        method.visitMaxs(0, 1)
        method.visitEnd()
        writer.visitEnd()
        file.apply { parentFile.mkdirs() }.writeBytes(writer.toByteArray())
    }

    private fun writeReport(file: File, vararg tests: Pair<String, String>) {
        file.writeText(buildString {
            append("<testsuite tests=\"").append(tests.size)
                .append("\" skipped=\"0\" failures=\"0\" errors=\"0\">")
            tests.forEach { (name, result) ->
                append("<testcase classname=\"fixture.CoverageTest\" name=\"")
                    .append(name).append("()[jvm]\">").append(result).append("</testcase>")
            }
            append("</testsuite>")
        })
    }

    private fun withDirectory(block: (File) -> Unit) {
        val root = createTempDirectory("cross-language-api-coverage").toFile()
        try {
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }

    @Retention(AnnotationRetention.BINARY)
    private annotation class FixtureCoversApi(vararg val members: String)

    private class NonTestCoverageFixture {
        @FixtureCoversApi("api#one")
        fun notATest() = Unit
    }

    private companion object {
        const val API_KEY_ONE =
            "common|owner=fixture/Host|kind=property|abi=fixture/Host.ready|{}ready[0]|propertyKind=VAL|type=kotlin/Boolean!!"
        const val API_KEY_TWO =
            "common|owner=fixture/Host|kind=function|abi=fixture/Host.refresh|refresh(){}[0]|return=kotlin/Unit|suspend=true|parameters=[]"
        const val API_KEY_THREE =
            "common|owner=fixture/Host|kind=property|abi=fixture/Host.count|{}count[0]|propertyKind=VAL|type=kotlin/Int!!"
        const val OBJECT_KEY =
            "common|owner=fixture/State.Ready|kind=object|abi=fixture/State.Ready|null[0]"
        const val FIXTURE_TOKEN_ONE =
            "api-v1:Fixture#function:one#sha256:0000000000000000000000000000000000000000000000000000000000000001"
        const val FIXTURE_TOKEN_TWO =
            "api-v1:Fixture#function:two#sha256:0000000000000000000000000000000000000000000000000000000000000002"
        val API_KEYS = listOf(API_KEY_ONE, API_KEY_TWO).sorted()
        val API_TOKENS = API_KEYS.map(::crossLanguageApiCoverageToken)
        val FIXTURE_TOKENS = listOf(FIXTURE_TOKEN_ONE, FIXTURE_TOKEN_TWO)
        val fixtureAnnotationDescriptor =
            "L${FixtureCoversApi::class.java.name.replace('.', '/')};"
    }
}
