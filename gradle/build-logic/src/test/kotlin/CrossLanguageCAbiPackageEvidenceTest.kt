import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put
import org.gradle.api.tasks.CacheableTask

class CrossLanguageCAbiPackageEvidenceTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-bindings").isDirectory }

    @Test
    fun `SDK plugin wires imported native wrapper packages`() {
        val sdkWiring = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts",
        ).readText()
        listOf(
            "tasks.register<StageCrossLanguageNativeWrapperSdksTask>",
            "tasks.register<MaterializeCrossLanguageNativeWrapperPackageAssetsTask>",
            "codexAgent.nativeWrapperRuntimeStageRoot",
            "native-wrapper-c-abi-sdks",
            "native-wrapper-package-assets",
            "prepareNativeWrapperPackageSources",
            "native-wrapper-package-sources/",
            "\"dart\" to (\"Dart\" to listOf(\"build/**\"",
        ).forEach { contract -> assertTrue(contract in sdkWiring, "Missing SDK wrapper wiring: $contract") }
        val cppCmake = repository.resolve("codex-agent-bindings/cpp/CMakeLists.txt").readText()
        assertTrue("\"${'$'}{CodexAgent_C_SDK_ROOT}/LICENSE.txt\"" in cppCmake)
        assertFalse("../../../LICENSE" in cppCmake)
    }

    @Test
    fun `C ABI client Runtime production and SDK staging have disjoint ownership`() {
        val clientSource = repository.resolve(
            "gradle/build-logic/src/main/kotlin/CrossLanguageCAbiClient.kt",
        ).readText()
        val runtimeSource = listOf(
            "runtime/build-logic/src/main/kotlin/RuntimeCAbiClient.kt",
            "runtime/build-logic/src/main/kotlin/CrossLanguageCAbiRuntimeProduction.kt",
        ).joinToString("\n") { repository.resolve(it).readText() }
        val stagingSource = repository.resolve(
            "gradle/build-logic/src/main/kotlin/CrossLanguageNativeWrapperSdkStaging.kt",
        ).readText()
        val sdkSource = repository.resolve(
            "gradle/build-logic/src/main/kotlin/CrossLanguageNativeWrapperGradleTasks.kt",
        ).readText()
        listOf(
            "data class CrossLanguageNativeWrapperSdkInput",
            "data class CrossLanguageNativeWrapperSdkIndex",
            "fun stageCrossLanguageNativeWrapperSdks",
            "fun materializeCrossLanguageNativeWrapperPackageAssets",
            "fun readCrossLanguageNativeWrapperSdkIndex",
        ).forEach { declaration ->
            assertFalse(declaration in clientSource, "Root C ABI client owns SDK staging: $declaration")
            assertFalse(declaration in runtimeSource, "Runtime C ABI source owns SDK staging: $declaration")
            assertTrue(declaration in stagingSource, "SDK staging source does not own $declaration")
        }
        listOf(
            "StageCrossLanguageNativeWrapperSdksTask",
            "MaterializeCrossLanguageNativeWrapperPackageAssetsTask",
        ).forEach { taskType ->
            val declaration = "abstract class $taskType"
            assertFalse(declaration in clientSource, "Root C ABI client owns $taskType")
            assertFalse(declaration in runtimeSource, "Runtime C ABI source owns $taskType")
            assertTrue(declaration in sdkSource, "SDK Gradle source does not own $taskType")
        }
        assertTrue("runProductPythonModule(\"c_abi\", arguments)" in clientSource)
        assertTrue("add(\"portable-verify\")" in clientSource)
    }

    @Test
    fun `target host classifier and proof catalog is exact`() {
        assertEquals(
            mapOf(
                "macosArm64" to "c-abi-macos-arm64",
                "macosX64" to "c-abi-macos-x64",
                "linuxArm64" to "c-abi-linux-arm64",
                "linuxX64" to "c-abi-linux-x64",
                "mingwX64" to "c-abi-windows-x64",
            ),
            crossLanguageCAbiTargetSpecs.mapValues { it.value.classifier },
        )
        assertEquals(setOf("mach-o", "elf", "pe"), crossLanguageCAbiTargetSpecs.values.map { it.format }.toSet())
        assertEquals("macosArm64", crossLanguageCAbiHostTarget("Mac OS X", "aarch64"))
        assertEquals("macosArm64", crossLanguageCAbiHostTarget("macOS", "arm64"))
        assertEquals("macosX64", crossLanguageCAbiHostTarget("Mac OS X", "x86_64"))
        assertEquals("linuxArm64", crossLanguageCAbiHostTarget("Linux", "aarch64"))
        assertEquals("linuxX64", crossLanguageCAbiHostTarget("Linux", "amd64"))
        assertEquals("mingwX64", crossLanguageCAbiHostTarget("Windows 11", "x86_64"))
        assertEquals(null, crossLanguageCAbiHostTarget("FreeBSD", "x86_64"))
        assertEquals(null, crossLanguageCAbiHostTarget("Mac OS X", "riscv64"))
        assertEquals(setOf("codex_agent_lifecycle_compile.cpp"), crossLanguageCAbiCompileOnlyConsumers)
        assertEquals(30, crossLanguageCAbiStrictConsumers.size)
        assertEquals(
            setOf(
                "c-abi-package-macos-arm64",
                "c-abi-package-macos-x64",
                "c-abi-package-linux-arm64",
                "c-abi-package-linux-x64",
                "c-abi-package-windows-x64",
            ),
            crossLanguageCAbiPackageProofIds.values.toSet(),
        )
        assertEquals(
            "codex-agent-runtime-desktop-0.2.0-c-abi-windows-x64.zip",
            crossLanguageCAbiArchiveFileName("0.2.0", "mingwX64"),
        )
        assertEquals("c-abi-package-linux-arm64.json", crossLanguageCAbiPackageEvidenceFileName("linuxArm64"))
        assertEquals(
            setOf("c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport"),
            crossLanguageCAbiRequiredToolIds("mingwX64"),
        )
        assertEquals(777, CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT)
        assertEquals("1.12", CROSS_LANGUAGE_C_ABI_CURRENT)
        assertEquals("1.0", CROSS_LANGUAGE_C_ABI_MINIMUM)
        assertEquals("0x010c0000", CROSS_LANGUAGE_C_ABI_ENCODED)
    }

    @Test
    fun `packaged Python products stage and materialize all five SDK targets`() = withFixture { fixture ->
        val archives = linkedMapOf<String, File>()
        val evidence = linkedMapOf<String, File>()
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val archive = fixture.root.resolve(crossLanguageCAbiArchiveFileName(Fixture.VERSION, spec.target))
            val snapshot = fixture.packageArchive(spec, archive)
            val proof = fixture.root.resolve(crossLanguageCAbiPackageEvidenceFileName(spec.target))
            fixture.writeEvidence(spec, archive, snapshot, proof)
            archives[spec.target] = archive
            evidence[spec.target] = proof
        }

        val input = CrossLanguageNativeWrapperSdkInput(
            Fixture.VERSION,
            Fixture.COMMIT,
            Fixture.TREE,
            archives,
            evidence,
            crossLanguageCAbiTargetSpecs.mapValues { (_, spec) -> fixture.reference(spec) },
        )
        val staged = fixture.root.resolve("wrapper-sdks")
        stageCrossLanguageNativeWrapperSdks(input, staged)
        val index = readCrossLanguageNativeWrapperSdkIndex(staged)
        assertEquals(crossLanguageCAbiTargetSpecs.keys, index.records.keys)
        assertEquals(Fixture.COMMIT, index.producerCommit)
        assertEquals(Fixture.TREE, index.producerTree)

        val packageAssets = fixture.root.resolve("wrapper-package-assets")
        materializeCrossLanguageNativeWrapperPackageAssets(staged, packageAssets)
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val classifier = spec.classifier.removePrefix("c-abi-")
            val packageClassifier = when (classifier) {
                "macos-arm64" -> "osx-arm64"
                "macos-x64" -> "osx-x64"
                "windows-x64" -> "win-x64"
                else -> classifier
            }
            val expectedLibrary = fixture.library(spec).releaseDigest()
            val libraryName = File(spec.libraryPath).name
            listOf(
                packageAssets.resolve("python/src/codex_agent/native/$classifier"),
                packageAssets.resolve("csharp/native/$packageClassifier"),
                packageAssets.resolve("rust/native/$packageClassifier"),
                packageAssets.resolve("dart/lib/src/native/$classifier"),
            ).forEach { destination ->
                assertTrue(fixture.library(spec).readBytes().contentEquals(destination.resolve(libraryName).readBytes()))
                assertEquals(
                    evidence.getValue(spec.target).readBytes().toList(),
                    destination.resolve("codex-agent-c-abi-evidence.json").readBytes().toList(),
                )
            }
            val cppSdk = packageAssets.resolve("cpp/native/$classifier")
            assertEquals(expectedLibrary, cppSdk.resolve(spec.libraryPath).releaseDigest())
            assertTrue(cppSdk.resolve(C_ABI_HEADER_PATH).isFile)
            assertTrue(cppSdk.resolve(C_ABI_PACKAGE_MANIFEST).isFile)
        }
        assertEquals(
            staged.resolve("codex-agent-native-wrapper-sdks.json").readBytes().toList(),
            packageAssets.resolve("codex-agent-native-wrapper-sdks.json").readBytes().toList(),
        )
    }

    @Test
    fun `SDK Gradle tasks remain cacheable`() {
        assertNotNull(StageCrossLanguageNativeWrapperSdksTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(
            MaterializeCrossLanguageNativeWrapperPackageAssetsTask::class.java.getAnnotation(CacheableTask::class.java),
        )
    }

    class Fixture {
        val root = createTempDirectory("c-abi-sdk-staging-").toFile()
        private val symbols = (0 until CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT)
            .map { "codex_agent_symbol_${it.toString().padStart(3, '0')}" }
        private val header = root.resolve("codex_agent.h").apply {
            writeText(symbols.joinToString("\n", postfix = "\n") { "int $it(void);" })
        }
        private val license = root.resolve("LICENSE").apply { writeText("license\n") }
        private val notice = root.resolve("THIRD_PARTY_NOTICES.md").apply { writeText("notice\n") }
        private val gnuImport = root.resolve("libcodex_agent.dll.a").apply { writeText("gnu import\n") }
        private val msvcImport = root.resolve("codex_agent.lib").apply { writeText("msvc import\n") }
        private val consumers = crossLanguageCAbiStrictConsumers.associateWith { name ->
            root.resolve("consumers/$name").apply {
                parentFile.mkdirs()
                writeText("/* $name */\n")
            }
        }

        fun library(spec: CrossLanguageCAbiTargetSpec): File = root.resolve("${spec.target}-library").apply {
            if (!isFile) writeText("${spec.format}:${spec.architecture}:${spec.loaderIdentity}\n")
        }

        fun reference(spec: CrossLanguageCAbiTargetSpec) = CrossLanguageNativeWrapperSdkReferenceInput(
            header,
            license,
            notice,
            exportPolicy(spec),
            consumers.values.toList(),
        )

        fun packageArchive(spec: CrossLanguageCAbiTargetSpec, archive: File): JsonObject {
            val output = runProductPythonModule(
                "c_abi",
                listOf("package") + packageArguments(spec) + listOf("--output", archive.absolutePath),
            )
            return Json.parseToJsonElement(output).jsonObject
        }

        fun writeEvidence(spec: CrossLanguageCAbiTargetSpec, archive: File, snapshot: JsonObject, output: File) {
            val policy = Json.parseToJsonElement(runProductPythonModule(
                "c_abi",
                listOf(
                    "describe-export-policy",
                    "--export-policy", exportPolicy(spec).absolutePath,
                    "--format", spec.format,
                ),
            )).jsonObject
            val members = snapshot.strictArray("members").associate { value ->
                val record = value.jsonObject
                record.strictString("path") to record.strictSha256("sha256")
            }
            val tools = crossLanguageCAbiRequiredToolIds(spec.target).associateWith { digest("tool:$it") }
            val values = buildJsonObject {
                put("architecture", spec.architecture)
                put("archiveSha256", snapshot.strictSha256("archiveSha256"))
                put("classifier", spec.classifier)
                put("consumers", consumerProofs(tools, gnu = false))
                put("format", spec.format)
                put(
                    "gnuConsumers",
                    if (spec.format == "pe") consumerProofs(tools, gnu = true) else JsonArray(emptyList()),
                )
                put("headerSha256", snapshot.strictSha256("headerSha256"))
                put("importLibraries", buildJsonArray {
                    spec.importLibraryPaths.sorted().forEach { path -> add(buildJsonObject {
                        put("path", path)
                        put("sha256", members.getValue(path))
                    }) }
                })
                put("librarySha256", snapshot.strictSha256("librarySha256"))
                put("libraryVersion", VERSION)
                put("loaderIdentity", spec.loaderIdentity)
                put("producerCommit", COMMIT)
                put("producerTree", TREE)
                put("publicSymbolVersions", policy.strictArray("publicSymbolVersions"))
                put("publicSymbols", policy.strictArray("publicSymbols"))
                put("runnerArch", spec.runnerArch)
                put("runnerOs", spec.runnerOs)
                put("schemaVersion", 1)
                put("target", spec.target)
                put("toolProofs", buildJsonArray {
                    tools.toSortedMap().forEach { (id, sha256) -> add(buildJsonObject {
                        put("id", id)
                        put("outputSha256", sha256)
                    }) }
                })
                put("versionIdentity", spec.expectedVersionIdentity())
            }
            val valuesFile = root.resolve("${spec.target}-values.json")
            valuesFile.writeText(canonicalJson(values))
            val verificationArguments = packageArguments(spec) + listOf(
                "--archive", archive.absolutePath,
                "--expected-runner-os", spec.runnerOs,
                "--expected-runner-arch", spec.runnerArch,
            ) + consumers.values.sortedBy(File::getName).flatMap {
                listOf("--consumer-source", it.absolutePath)
            }
            val canonicalEvidence = runProductPythonModule(
                "c_abi",
                listOf("evidence-write") + verificationArguments +
                    listOf("--values", valuesFile.absolutePath, "--output", output.absolutePath),
            )
            assertTrue(output.isFile)
            assertEquals(
                canonicalEvidence,
                runProductPythonModule(
                    "c_abi",
                    listOf("evidence-verify") + verificationArguments +
                        listOf("--evidence", output.absolutePath),
                ),
            )
        }

        private fun consumerProofs(tools: Map<String, String>, gnu: Boolean): JsonArray = buildJsonArray {
            val sources = if (gnu) C_ABI_GNU_CONSUMERS else crossLanguageCAbiStrictConsumers
            sources.sorted().forEach { source ->
                val cpp = source.endsWith(".cpp")
                val compileOnly = !gnu && source in crossLanguageCAbiCompileOnlyConsumers
                add(buildJsonObject {
                    put("artifactSha256", digest("artifact:$source:$gnu"))
                    put("compileOutputSha256", digest("compile:$source:$gnu"))
                    put("compilerIdentitySha256", tools.getValue(when {
                        gnu && cpp -> "gnuCpp"
                        gnu -> "gnuC"
                        cpp -> "cpp"
                        else -> "c"
                    }))
                    put("executed", !compileOnly)
                    put("exitCode", 0)
                    put("language", if (cpp) "c++17" else "c11")
                    put("linked", !compileOnly)
                    put("source", source)
                    put("sourceSha256", consumers.getValue(source).releaseDigest())
                })
            }
        }

        private fun packageArguments(spec: CrossLanguageCAbiTargetSpec): List<String> = buildList {
            addAll(listOf(
                "--target", spec.target,
                "--classifier", spec.classifier,
                "--library-version", VERSION,
                "--producer-commit", COMMIT,
                "--producer-tree", TREE,
                "--reviewed-header", header.absolutePath,
                "--license", license.absolutePath,
                "--notice", notice.absolutePath,
                "--library", library(spec).absolutePath,
                "--export-policy", exportPolicy(spec).absolutePath,
            ))
            if (spec.format == "pe") addAll(listOf(
                "--gnu-import-library", gnuImport.absolutePath,
                "--msvc-import-library", msvcImport.absolutePath,
            ))
        }

        private fun exportPolicy(spec: CrossLanguageCAbiTargetSpec): File = root.resolve("${spec.target}.exports").apply {
            if (isFile) return@apply
            if (spec.format == "elf") {
                writeText((0..12).joinToString("\n", postfix = "\n") { minor ->
                    buildString {
                        appendLine("CODEX_AGENT_1.$minor {")
                        appendLine("    global:")
                        symbols.filterIndexed { index, _ -> index % 13 == minor }.forEach {
                            appendLine("        $it;")
                        }
                        append("};")
                    }
                })
            } else {
                val prefix = if (spec.format == "mach-o") "_" else ""
                writeText(symbols.joinToString("\n", postfix = "\n") { "$prefix$it" })
            }
        }

        companion object {
            const val VERSION = "0.2.0"
            const val COMMIT = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            const val TREE = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
    }
}

private inline fun <T> withFixture(block: (CrossLanguageCAbiPackageEvidenceTest.Fixture) -> T): T {
    val fixture = CrossLanguageCAbiPackageEvidenceTest.Fixture()
    return try {
        block(fixture)
    } finally {
        fixture.root.deleteRecursively()
    }
}

private fun digest(value: String): String = value.byteInputStream().releaseDigest()

private fun canonicalJson(value: JsonElement): String = Json.encodeToString(
    JsonElement.serializer(),
    value.sortedObjectKeys(),
) + "\n"

private fun JsonElement.sortedObjectKeys(): JsonElement = when (this) {
    is JsonObject -> JsonObject(entries.sortedBy { it.key }.associate { (key, value) ->
        key to value.sortedObjectKeys()
    })
    is JsonArray -> JsonArray(map(JsonElement::sortedObjectKeys))
    is JsonPrimitive -> this
}
