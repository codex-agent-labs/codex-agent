import java.io.File
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.testfixtures.ProjectBuilder

class CrossLanguageJavaScriptEnumDeclarationsTest {
    @Test
    fun `task declares cacheable path-insensitive report and output fragment`() {
        val type = GenerateJavaScriptEnumDeclarationsTask::class.java
        assertNotNull(type.getAnnotation(CacheableTask::class.java))
        val input = type.getMethod("getApiReport")
        assertNotNull(input.getAnnotation(InputFile::class.java))
        assertEquals(PathSensitivity.NONE, input.getAnnotation(PathSensitive::class.java).value)
        assertNotNull(type.getMethod("getDeclarationsFile").getAnnotation(OutputFile::class.java))
    }

    @Test
    fun `generates exact sorted UTF-8 LF declarations including enum owners with properties`() = withRoot { root ->
        val report = root.resolve("canonical-api.json")
        val output = root.resolve("canonical-enums.d.ts")
        val approval = "sample/AgentApprovalPreset"
        val authentication = "sample/AgentAuthenticationStatus"
        val role = "sample/AgentMessageRole"
        val mode = "sample/ZMode"
        writeReport(
            report,
            listOf(
                Owner(mode, listOf(enumEntry(mode, "Second"), enumEntry(mode, "FIRST_VALUE"))),
                Owner(role, listOf(enumEntry(role, "USER"), property(role, "displayName"), enumEntry(role, "ASSISTANT"))),
                Owner(authentication, listOf(enumEntry(authentication, "SIGNED_OUT"), enumEntry(authentication, "AUTHENTICATED"))),
                Owner(approval, listOf(enumEntry(approval, "STRICT"), enumEntry(approval, "AUTO_REVIEW"))),
            ),
        )
        val expected = """
            export type CodexApprovalPreset = "auto_review" | "strict";
            export type CodexAuthenticationStatus = "authenticated" | "signed_out";
            export type CodexMessageRole = "assistant" | "user";
            export type ZMode = "first_value" | "second";
        """.trimIndent() + "\n"
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "generateJavaScriptEnumDeclarations",
            GenerateJavaScriptEnumDeclarationsTask::class.java,
        ).apply {
            apiReport.set(report)
            declarationsFile.set(output)
        }

        task.generate()
        assertEquals(expected, output.readText(UTF_8))
        assertTrue(output.readBytes().contentEquals(expected.toByteArray(UTF_8)))
        assertFalse('\r'.code.toByte() in output.readBytes())

        writeReport(
            report,
            listOf(
                Owner(approval, listOf(enumEntry(approval, "AUTO_REVIEW"), enumEntry(approval, "STRICT"))),
                Owner(mode, listOf(enumEntry(mode, "FIRST_VALUE"), enumEntry(mode, "Second"))),
                Owner(authentication, listOf(enumEntry(authentication, "AUTHENTICATED"), enumEntry(authentication, "SIGNED_OUT"))),
                Owner(role, listOf(enumEntry(role, "ASSISTANT"), property(role, "displayName"), enumEntry(role, "USER"))),
            ),
        )
        task.generate()
        assertEquals(expected, output.readText(UTF_8))
    }

    @Test
    fun `rejects wrong schema fields noncanonical bytes symlinks and nonfiles`() = withRoot { root ->
        val owner = Owner("sample/Mode", listOf(enumEntry("sample/Mode", "READY")))
        val wrongSchema = root.resolve("wrong-schema.json").also { writeReport(it, listOf(owner), schema = 1) }
        val wrongFields = root.resolve("wrong-fields.json").also {
            writeReport(it, listOf(owner), unexpectedField = true)
        }
        val noncanonical = root.resolve("noncanonical.json").also {
            writeReport(it, listOf(owner))
            it.writeText(it.readText().replace("    ", "  "))
        }
        val target = root.resolve("target.json").also { writeReport(it, listOf(owner)) }
        val symlink = root.resolve("symlink.json")
        Files.createSymbolicLink(symlink.toPath(), target.toPath())
        val directory = root.resolve("directory.json").apply { mkdirs() }

        listOf(wrongSchema, wrongFields, noncanonical, symlink, directory).forEach { invalid ->
            assertFailsWith<IllegalStateException>(invalid.name) { renderJavaScriptEnumDeclarations(invalid) }
        }
    }

    @Test
    fun `rejects no enums malformed or mixed identity kinds and ABI owner mismatches`() = withRoot { root ->
        val owner = "sample/Mode"
        val reports = listOf(
            listOf(Owner(owner, listOf(property(owner, "label")))),
            listOf(Owner(owner, listOf(enumEntry(owner, "READY").replace("kind=enum-entry", "kind=unknown")))),
            listOf(Owner(owner, listOf(enumEntry(owner, "READY").replace("|abi=", "|kind=property|abi=")))),
            listOf(Owner(owner, listOf(enumEntry(owner, "READY").replace("abi=$owner.READY", "abi=sample/Other.READY")))),
            listOf(Owner(owner, listOf(enumEntry(owner, "READY").replace("abi=$owner.READY", "abi=$owner.READY.EXTRA")))),
            listOf(
                Owner(
                    owner,
                    listOf(
                        enumEntry(owner, "READY"),
                        property(owner, "label").replace("abi=$owner.label", "abi=$owner.label.extra"),
                    ),
                ),
            ),
            listOf(Owner(owner, listOf(enumEntry(owner, "READY").replace("|null[0]", "|return=kotlin/String!!")))),
        )
        reports.forEachIndexed { index, owners ->
            val report = root.resolve("invalid-$index.json").also { writeReport(it, owners) }
            assertFailsWith<IllegalStateException>(report.name) { renderJavaScriptEnumDeclarations(report) }
        }
    }

    @Test
    fun `rejects unsafe and colliding names literals and exports`() = withRoot { root ->
        val cases = listOf(
            listOf(Owner("sample/Bad-Mode", listOf(enumEntry("sample/Bad-Mode", "READY")))),
            listOf(Owner("sample/Mode", listOf(enumEntry("sample/Mode", "BAD-VALUE")))),
            listOf(Owner("sample/Mode", listOf(enumEntry("sample/Mode", "VALUE"), enumEntry("sample/Mode", "Value")))),
            listOf(
                Owner("one/AgentApprovalPreset", listOf(enumEntry("one/AgentApprovalPreset", "ONE"))),
                Owner("two/CodexApprovalPreset", listOf(enumEntry("two/CodexApprovalPreset", "TWO"))),
            ),
            listOf(
                Owner("one/Mode", listOf(enumEntry("one/Mode", "ONE"))),
                Owner("two/Mode", listOf(enumEntry("two/Mode", "TWO"))),
            ),
        )
        cases.forEachIndexed { index, owners ->
            val report = root.resolve("collision-$index.json").also { writeReport(it, owners) }
            assertFailsWith<IllegalStateException>(report.name) { renderJavaScriptEnumDeclarations(report) }
        }
    }

    @Test
    fun `rejects duplicate owners and entries and deletes stale task output`() = withRoot { root ->
        val owner = "sample/Mode"
        val duplicateOwners = root.resolve("duplicate-owners.json").also {
            writeReport(
                it,
                listOf(
                    Owner(owner, listOf(enumEntry(owner, "ONE"))),
                    Owner(owner, listOf(enumEntry(owner, "TWO"))),
                ),
            )
        }
        val entry = enumEntry(owner, "ONE")
        val duplicateEntries = root.resolve("duplicate-entries.json").also {
            writeReport(it, listOf(Owner(owner, listOf(entry, entry))))
        }
        assertFailsWith<IllegalStateException> { renderJavaScriptEnumDeclarations(duplicateOwners) }
        assertFailsWith<IllegalStateException> { renderJavaScriptEnumDeclarations(duplicateEntries) }

        val output = root.resolve("canonical-enums.d.ts").apply { writeText("stale\n") }
        val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
            "generateInvalidJavaScriptEnumDeclarations",
            GenerateJavaScriptEnumDeclarationsTask::class.java,
        ).apply {
            apiReport.set(duplicateEntries)
            declarationsFile.set(output)
        }
        assertFailsWith<IllegalStateException> { task.generate() }
        assertFalse(output.exists())
    }

    private fun writeReport(
        file: File,
        owners: List<Owner>,
        schema: Int = 2,
        unexpectedField: Boolean = false,
    ) {
        val report = buildJsonObject {
            put("schema", JsonPrimitive(schema))
            put("libraryUniqueName", JsonPrimitive("sample:library"))
            put("markerAnnotation", JsonPrimitive("sample.Marker"))
            put("signatureVersion", JsonPrimitive(2))
            put("boundaryTypes", buildJsonArray { add(JsonPrimitive("sample/Boundary")) })
            put("memberExclusionAnnotation", JsonPrimitive("sample.Excluded"))
            put("excludedReachableTypes", buildJsonArray { add(JsonPrimitive("sample/ExcludedType")) })
            put("excludedMemberKeys", buildJsonArray {})
            put("dataClassMetadataAvailable", JsonPrimitive(true))
            put("dataClassNames", buildJsonArray {})
            put("owners", buildJsonArray {
                owners.forEach { owner ->
                    add(buildJsonObject {
                        put("name", JsonPrimitive(owner.name))
                        put("capabilities", buildJsonArray {
                            owner.capabilities.forEach { add(JsonPrimitive(it)) }
                        })
                    })
                }
            })
            put("targets", buildJsonArray {
                listOf("native", "wasm", "jvm-classes").forEachIndexed { index, kind ->
                    add(buildJsonObject {
                        put("kind", JsonPrimitive(kind))
                        put("sha256", JsonPrimitive(index.toString().repeat(64)))
                    })
                }
            })
            if (unexpectedField) put("unexpected", JsonPrimitive(true))
        }
        file.writeText(releaseJson.encodeToString(JsonElement.serializer(), report) + "\n", UTF_8)
    }

    private fun enumEntry(owner: String, name: String): String =
        "common|owner=$owner|kind=enum-entry|abi=$owner.$name|null[0]"

    private fun property(owner: String, name: String): String =
        "common|owner=$owner|kind=property|abi=$owner.$name|{}$name[0]|propertyKind=VAL|type=kotlin/String!!"

    private fun withRoot(block: (File) -> Unit) {
        val root = createTempDirectory("javascript-enum-declarations").toFile()
        try {
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }

    private data class Owner(val name: String, val capabilities: List<String>)
}
