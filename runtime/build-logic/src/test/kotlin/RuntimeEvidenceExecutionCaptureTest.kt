import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertFailsWith

class RuntimeEvidenceExecutionCaptureTest {
    @Test
    fun `shared capture rejects unsafe outputs and malformed records without touching originals`() {
        val root = createTempDirectory("runtime-capture").toFile().canonicalFile
        try {
            val original = root.resolve("original").apply { writeText("keep") }
            val output = root.resolve("capture.json")
            val link = root.resolve("link")
            Files.createSymbolicLink(link.toPath(), original.toPath())
            val hardlink = root.resolve("hardlink")
            Files.createLink(hardlink.toPath(), original.toPath())
            for (outputs in listOf(listOf(original), listOf(link), listOf(output, output),
                listOf(hardlink), listOf(root.resolve("missing/../capture.json")))) {
                assertFailsWith<IllegalStateException> {
                    validateRuntimeEvidenceOutputs(outputs, listOf(original))
                }
            }
            assertContentEquals("keep".toByteArray(), original.readBytes())
            for ((component, target, captures) in listOf(
                Triple("unknown", "linuxX64", emptyList()),
                Triple("jvm", "unknown", emptyList()),
                Triple("jvm", "linuxX64", listOf(RuntimeEvidenceProcessCapture("discovery", 0, byteArrayOf()),
                    RuntimeEvidenceProcessCapture("discovery", 0, byteArrayOf()))),
            )) {
                assertFailsWith<IllegalStateException> {
                    writeRuntimeEvidenceExecution(output, component, target, "ExactClass", captures)
                }
            }
        } finally { root.deleteRecursively() }
    }

    @Test
    fun `shared JUnit reader rejects skipped duplicate wrong-class and failed cases`() {
        val root = createTempDirectory("runtime-report").toFile().canonicalFile
        try {
            val report = root.resolve("report.xml")
            val methods = linkedSetOf("first", "second")
            writeRuntimeEvidenceTestReport(report, "ExactClass", methods)
            verifyRuntimeEvidenceTestReport(report, "ExactClass", methods)
            val original = report.readText()
            for (mutation in listOf(
                original.replace("skipped=\"0\"", "skipped=\"1\""),
                original.replace("name=\"second\"", "name=\"first\""),
                original.replace("ExactClass", "OtherClass"),
                original.replace("</testsuite>", "<failure/></testsuite>"),
            )) {
                report.writeText(mutation)
                assertFailsWith<IllegalStateException> {
                    verifyRuntimeEvidenceTestReport(report, "ExactClass", methods)
                }
            }
            assertFailsWith<IllegalStateException> {
                writeRuntimeEvidenceTestReport(report, "Class\"", methods)
            }
        } finally { root.deleteRecursively() }
    }
}
