import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

class CandidateManifestTasksTest {
    @Test
    fun `native wrapper package files match all five M11 receipts exactly`() {
        val root = createTempDirectory("native-wrapper-candidate-packages").toFile()
        try {
            val packageNames = linkedMapOf(
                CrossLanguageBinding.PYTHON to listOf(
                    "codex_agent-0.2.0.tar.gz", "codex_agent-0.2.0-py3-none-macosx_11_0_arm64.whl",
                    "codex_agent-0.2.0-py3-none-macosx_10_13_x86_64.whl",
                    "codex_agent-0.2.0-py3-none-linux_aarch64.whl",
                    "codex_agent-0.2.0-py3-none-linux_x86_64.whl",
                    "codex_agent-0.2.0-py3-none-win_amd64.whl",
                ),
                CrossLanguageBinding.CSHARP to listOf("CodexAgent.0.2.0.nupkg"),
                CrossLanguageBinding.RUST to listOf("codex-agent-0.2.0.crate"),
                CrossLanguageBinding.CPP to listOf(
                    "codex-agent-cpp-0.2.0-macos-arm64.zip", "codex-agent-cpp-0.2.0-macos-x64.zip",
                    "codex-agent-cpp-0.2.0-linux-arm64.zip", "codex-agent-cpp-0.2.0-linux-x64.zip",
                    "codex-agent-cpp-0.2.0-windows-x64.zip",
                ),
                CrossLanguageBinding.DART to listOf("codex-agent-dart-0.2.0.tar.gz"),
            ).mapValues { (language, packages) ->
                packages + "codex-agent-${language.id}-package-toolchain.tsv"
            }
            val receipts = nativeWrapperBindings.associateWith { language ->
                val directory = root.resolve(language.id).apply { mkdirs() }
                val artifacts = packageNames.getValue(language).map { name ->
                    val file = directory.resolve(name).apply { writeText("${language.id}:$name") }
                    CrossLanguageBindingArtifactIdentity("${language.id}-package/$name", file.releaseDigest())
                }
                CrossLanguageBindingReceipt(
                    phase = CrossLanguageBindingPhase.M11,
                    language = language,
                    canonical = CrossLanguageBindingCanonicalIdentity("a".repeat(64), "b".repeat(64)),
                    artifacts = artifacts,
                    testProgramSha256 = "c".repeat(64),
                    testResultsSha256 = "d".repeat(64),
                    publicSymbols = emptyList(),
                    bindingTests = emptyList(),
                    scenarioEvidence = emptyList(),
                    projectionClaims = emptyList(),
                    applicabilityExclusions = emptyList(),
                )
            }
            val expected = nativeWrapperM11PackageArtifacts(receipts)
            assertEquals(19, verifyNativeWrapperPackageFiles(root, expected).values.sumOf { it.size })

            val python = root.resolve("python/${packageNames.getValue(CrossLanguageBinding.PYTHON).first()}")
            val original = python.readText()
            python.writeText("tampered")
            assertTrue(assertFailsWith<IllegalStateException> {
                verifyNativeWrapperPackageFiles(root, expected)
            }.message.orEmpty().contains("hash mismatch"))
            python.writeText(original)

            val extra = root.resolve("csharp/unexpected.bin").apply { writeText("extra") }
            assertTrue(assertFailsWith<IllegalStateException> {
                verifyNativeWrapperPackageFiles(root, expected)
            }.message.orEmpty().contains("inventory mismatch"))
            extra.delete()
            python.delete()
            assertFailsWith<IllegalStateException> { verifyNativeWrapperPackageFiles(root, expected) }
            python.writeText(original)

            val wrongPhase = receipts + (CrossLanguageBinding.DART to
                receipts.getValue(CrossLanguageBinding.DART).copy(phase = CrossLanguageBindingPhase.M9_DART))
            assertFailsWith<IllegalStateException> { nativeWrapperM11PackageArtifacts(wrongPhase) }
            val wrongLanguage = receipts + (CrossLanguageBinding.PYTHON to
                receipts.getValue(CrossLanguageBinding.PYTHON).copy(language = CrossLanguageBinding.CSHARP))
            assertFailsWith<IllegalStateException> { nativeWrapperM11PackageArtifacts(wrongLanguage) }
            val nested = receipts + (CrossLanguageBinding.PYTHON to receipts.getValue(CrossLanguageBinding.PYTHON).copy(
                artifacts = listOf(CrossLanguageBindingArtifactIdentity(
                    "python-package/nested/package.whl", "e".repeat(64),
                )),
            ))
            assertFailsWith<IllegalStateException> { nativeWrapperM11PackageArtifacts(nested) }
            val duplicateName = packageNames.getValue(CrossLanguageBinding.PYTHON).first()
            val ambiguous = receipts + (CrossLanguageBinding.CSHARP to receipts.getValue(CrossLanguageBinding.CSHARP).copy(
                artifacts = listOf(CrossLanguageBindingArtifactIdentity(
                    "csharp-package/$duplicateName", "f".repeat(64),
                )),
            ))
            assertFailsWith<IllegalStateException> { nativeWrapperM11PackageArtifacts(ambiguous) }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `schema 16 structure is exact and schema 15 is rejected`() {
        val manifest = schema16CandidateManifest(VERSION, COMMIT)

        verifyCandidateManifestStructure(manifest)
        assertEquals(16, PROMOTED_CANDIDATE_SCHEMA)
        assertEquals(
            setOf(
                "canonical-api.json", "canonical-coverage.json", "kotlin-parity.json",
                "java-parity.json", "javascript-typescript-parity.json", "swift-parity.json",
                "objective-c-parity.json", "c-abi-parity.json", "python-parity.json",
                "csharp-parity.json", "rust-parity.json", "cpp-parity.json", "dart-parity.json",
                "binding-obligations-m11.json",
            ),
            manifest.releaseObject("evidence").releaseArray("crossLanguageM11")
                .map { it.jsonObject.releaseString("fileName") }.toSet(),
        )
        val legacy = JsonObject(manifest + ("schemaVersion" to JsonPrimitive(15)))
        assertFailsWith<IllegalStateException> { verifyCandidateManifestStructure(legacy) }
        val missingPolicy = JsonObject(manifest + ("policies" to JsonObject(
            manifest.releaseObject("policies") - "iosResourcePolicy",
        )))
        assertFailsWith<IllegalStateException> { verifyCandidateManifestStructure(missingPolicy) }
    }

    @Test
    fun `payload records traverse every Central bundle and evidence array`() {
        val manifest = schema16CandidateManifest(VERSION, COMMIT)
        val records = candidatePayloadRecords(manifest).map { it.releaseString("fileName") }
        val expectedBundles = centralBundleShardNames.map { centralBundleFileName(VERSION, it) }
        val evidence = manifest.releaseObject("evidence")
        val arrayEvidence = candidateEvidenceArrayNames.flatMap { name ->
            evidence.releaseArray(name).map { it.jsonObject.releaseString("fileName") }
        }

        assertTrue(records.containsAll(expectedBundles))
        assertTrue(records.containsAll(promotedNativeWrapperPackageRecords(manifest).map {
            it.releaseString("fileName")
        }))
        assertTrue(records.containsAll(arrayEvidence))
        assertEquals(records.size, records.toSet().size)
    }

    @Test
    fun `extra missing and tampered payload files are rejected`() {
        val root = createTempDirectory("candidate-payload-files").toFile()
        try {
            val payload = root.resolve("payload").apply { mkdirs() }
            val swift = payload.resolve("CodexAgent-$VERSION.xcframework.zip").apply { writeText("swift") }
            val base = schema16CandidateManifest(VERSION, COMMIT)
            val artifacts = base.releaseObject("artifacts")
            val swiftRecord = buildJsonObject {
                swift.releaseRecord().forEach { (key, value) -> put(key, value) }
                put("swiftPmChecksum", JsonPrimitive(swift.releaseDigest()))
                put("members", buildJsonArray {})
            }
            val manifest = JsonObject(base + ("artifacts" to JsonObject(
                artifacts + ("swiftPackage" to swiftRecord),
            )))
            val manifestFile = root.resolve("candidate-manifest.json").apply { atomicWriteJson(manifest) }
            candidatePayloadRecords(manifest).drop(1).forEach { record ->
                payload.resolve(record.releaseString("fileName")).writeText("x")
            }

            val extra = payload.resolve("unexpected.bin").apply { writeText("x") }
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
            extra.delete()

            val missing = payload.resolve(candidatePayloadRecords(manifest).last().releaseString("fileName"))
            missing.delete()
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
            missing.writeText("x")

            swift.appendText("tampered")
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `GitHub output contains plural Central bundles and the SBOM`() {
        val bundles = centralBundleShardNames.map { centralBundleFileName(VERSION, it) }
        val sbom = aggregateReleaseSbomFileName(VERSION)
        val result = buildJsonObject {
            put("releaseTag", JsonPrimitive("v$VERSION"))
            put("swiftAsset", JsonPrimitive("swift.zip"))
            put("centralBundles", buildJsonArray { bundles.forEach { add(JsonPrimitive(it)) } })
            put("nativeWrapperAssets", buildJsonArray { add(JsonPrimitive("python.whl")) })
            put("sbomAsset", JsonPrimitive(sbom))
        }

        assertEquals(
            "releaseTag=v$VERSION\nswiftAsset=swift.zip\n" +
                "centralBundles=${result.releaseArray("centralBundles")}\n" +
                "nativeWrapperAssets=${result.releaseArray("nativeWrapperAssets")}\nsbomAsset=$sbom\n",
            candidateGithubOutputs(result),
        )
    }

    @Test
    fun `aggregate SBOM is deterministic exact and reconstructed from schema 3 inventory`() {
        val root = createTempDirectory("aggregate-sbom").toFile()
        try {
            val groupPath = CodexAgentBuild.MAVEN_GROUP.replace('.', '/')
            val primaryPaths = expectedMavenPrimaryPaths(VERSION).mapTo(sortedSetOf()) { "$groupPath/$it" }
            val inventoryPaths = primaryPaths.flatMapTo(sortedSetOf()) { path ->
                listOf(path, "$path.asc", "$path.md5", "$path.sha1", "$path.sha256", "$path.sha512")
            }
            val inventory = root.resolve("maven-inventory.json").apply { atomicWriteJson(buildJsonObject {
                put("schemaVersion", JsonPrimitive(3)); put("groupId", JsonPrimitive(CodexAgentBuild.MAVEN_GROUP))
                put("version", JsonPrimitive(VERSION))
                put("artifactIds", buildJsonArray {
                    expectedMavenPrimaryPaths(VERSION).mapTo(sortedSetOf()) { it.substringBefore('/') }
                        .forEach { add(JsonPrimitive(it)) }
                })
                put("primaryArtifactCount", JsonPrimitive(primaryPaths.size))
                put("signaturesRequired", JsonPrimitive(true))
                put("files", buildJsonArray { inventoryPaths.forEach { path -> add(buildJsonObject {
                    put("path", JsonPrimitive(path)); put("bytes", JsonPrimitive(path.length.toLong()))
                    put("sha256", JsonPrimitive(path.encodeToByteArray().inputStream().releaseDigest()))
                }) } })
            }) }
            val swift = root.resolve("CodexAgent-$VERSION.xcframework.zip").apply { writeText("swift") }
            val desktopManifest = writeTestDesktopDistributionManifest(
                root.resolve("codex-app-server-distributions.json"),
                "f".repeat(64),
            )
            val license = root.resolve("openai-codex-LICENSE.txt").apply { writeText("license") }
            val notice = root.resolve("openai-codex-NOTICE.txt").apply { writeText("notice") }
            val nativePackage = root.resolve("codex-agent-python.whl").apply { writeText("python") }
            fun build() = buildAggregateReleaseSbom(
                VERSION, "v$VERSION", COMMIT, "f".repeat(40), inventory, swift,
                listOf(nativePackage), desktopManifest, license, notice,
            )

            val first = build()
            assertEquals(first, build())
            assertEquals(
                setOf(
                    "${'$'}schema", "bomFormat", "specVersion", "version", "metadata",
                    "components", "dependencies", "compositions",
                ),
                first.keys,
            )
            assertEquals("CycloneDX", first.releaseString("bomFormat"))
            assertEquals("1.7", first.releaseString("specVersion"))
            assertEquals("post-build", first.releaseObject("metadata").releaseArray("lifecycles")
                .single().let { (it as JsonObject).releaseString("phase") })
            val components = first.releaseArray("components").map { it as JsonObject }
            val mavenComponents = components.filter { it.releaseString("bom-ref").startsWith("pkg:maven/") }
            assertEquals(28, components.size)
            assertEquals(25, mavenComponents.size)
            assertEquals(primaryPaths.size, mavenComponents.sumOf { it.releaseArray("externalReferences").size })

            val sbom = root.resolve(aggregateReleaseSbomFileName(VERSION)).apply { atomicWriteJson(first) }
            verifyAggregateReleaseSbom(
                sbom, VERSION, "v$VERSION", COMMIT, "f".repeat(40), inventory, swift,
                listOf(nativePackage), desktopManifest, license, notice,
            )
            sbom.atomicWriteJson(JsonObject(first + ("unexpected" to JsonPrimitive(true))))
            val failure = assertFailsWith<IllegalStateException> {
                verifyAggregateReleaseSbom(
                    sbom, VERSION, "v$VERSION", COMMIT, "f".repeat(40), inventory, swift,
                    listOf(nativePackage), desktopManifest, license, notice,
                )
            }
            assertTrue(failure.message.orEmpty().contains("exact release inputs"))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `privacy review must be declared even with an explicit override`() {
        val root = createTempDirectory("candidate-privacy-review").toFile()
        try {
            val payload = root.resolve("payload").apply { mkdirs() }
            val declared = payload.resolve("privacy-required-reason-reviews.json").apply { writeText("{}") }
            val explicit = root.resolve(declared.name).apply { writeText("{}") }
            val manifest = buildJsonObject {
                put("policies", buildJsonObject {
                    put("privacyRequiredReasonReviews", declared.releaseRecord())
                })
            }
            assertSame(explicit, resolveCandidatePrivacyReview(manifest, payload, explicit, null))
            val absent = buildJsonObject { put("policies", buildJsonObject {}) }
            assertFailsWith<IllegalStateException> {
                resolveCandidatePrivacyReview(absent, payload, explicit, null)
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `iOS runtime metrics keep their release gates`() {
        val root = createTempDirectory("candidate-ios-metrics").toFile()
        try {
            val metrics = writeTestIosRuntimeMetrics(root.resolve("runtime-metrics.json"))
            validateIosRuntimeMetrics(metrics.readReleaseObject())
            writeTestIosRuntimeMetrics(metrics, startup = 30_000)
            assertFailsWith<IllegalStateException> {
                validateIosRuntimeMetrics(metrics.readReleaseObject())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    companion object {
        private const val VERSION = "0.2.0"
        private const val COMMIT = "0123456789abcdef0123456789abcdef01234567"
    }
}
