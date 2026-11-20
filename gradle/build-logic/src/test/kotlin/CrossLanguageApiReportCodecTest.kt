import java.io.EOFException
import kotlin.io.path.createTempFile
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CrossLanguageApiReportCodecTest {
    @Test
    fun `binary report round trips every field`() = withReportFile { file ->
        file.writeCrossLanguageApiReport(report)

        assertEquals(report, file.readCrossLanguageApiReport())
    }

    @Test
    fun `binary report rejects truncation trailing bytes and unsupported versions`() = withReportFile { file ->
        file.writeCrossLanguageApiReport(report)
        file.writeBytes(file.readBytes().dropLast(1).toByteArray())
        assertFailsWith<EOFException> { file.readCrossLanguageApiReport() }

        file.writeCrossLanguageApiReport(report)
        file.appendBytes(byteArrayOf(1))
        assertFailsWith<IllegalStateException> { file.readCrossLanguageApiReport() }

        file.writeBytes(byteArrayOf(0, 0, 0, 3))
        assertFailsWith<IllegalStateException> { file.readCrossLanguageApiReport() }
    }

    @Test
    fun `Native and Wasm reports must match`() {
        assertEquals(report, requireMatchingCrossLanguageApiReports(report, report.copy()))
        assertFailsWith<IllegalStateException> {
            requireMatchingCrossLanguageApiReports(report, report.copy(libraryUniqueName = "wasm"))
        }
        assertFailsWith<IllegalStateException> {
            requireMatchingCrossLanguageApiReports(
                report,
                report.copy(owners = report.owners.map { owner ->
                    if (owner.name.endsWith(".Ready")) owner.copy(capabilityKeys = emptyList()) else owner
                }),
            )
        }
    }

    private fun withReportFile(block: (java.io.File) -> Unit) {
        val file = createTempFile("cross-language-report", ".bin").toFile()
        try {
            block(file)
        } finally {
            file.delete()
        }
    }

    private companion object {
        val report = CrossLanguageApiReport(
            libraryUniqueName = "codex-agent-core",
            signatureVersion = 2,
            markerAnnotation = "fixture.CodexBindingApi",
            boundaryTypes = listOf("fixture/Platform"),
            memberExclusionAnnotation = "fixture.KotlinOnly",
            excludedReachableTypes = listOf("kotlinx.coroutines.CoroutineScope"),
            excludedMemberKeys = listOf("fixture/Host.scoped|kind=function"),
            dataClassMetadataAvailable = true,
            dataClassNames = listOf("fixture/State"),
            owners = listOf(
                CrossLanguageApiOwner("fixture/Host", listOf("fixture/Host.open|kind=function")),
                CrossLanguageApiOwner(
                    "fixture/State.Ready",
                    listOf("common|owner=fixture/State.Ready|kind=object|abi=fixture/State.Ready|null[0]"),
                ),
            ),
        )
    }
}
