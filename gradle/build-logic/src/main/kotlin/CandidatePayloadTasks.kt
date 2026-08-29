import java.io.File
import java.nio.file.Files
import java.util.zip.ZipFile
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

internal fun verifyCandidatePayload(
    manifestFile: File,
    payload: File,
    expectedVersion: String,
    expectedTag: String,
    expectedCommit: String,
    policyFiles: Map<String, File>,
): JsonObject {
    check(manifestFile.name == "candidate-manifest.json") { "Candidate manifest file name is invalid" }
    val manifest = manifestFile.readReleaseObject()
    verifyCandidateManifestStructure(manifest)
    check(manifest.releaseString("version") == expectedVersion) { "Candidate version mismatch" }
    check(manifest.releaseString("releaseTag") == expectedTag) { "Candidate release tag mismatch" }
    check(manifest.releaseString("candidateCommit") == expectedCommit) { "Candidate commit mismatch" }
    val evidence = manifest.releaseObject("evidence")
    val policies = manifest.releaseObject("policies")
    val artifacts = manifest.releaseObject("artifacts")
    val records = candidatePayloadRecords(manifest)
    val transportedManifest = manifestFile.canonicalFile.parentFile == payload.canonicalFile
    val expectedFiles = records.map { it.releaseString("fileName") } +
        if (transportedManifest) listOf(manifestFile.name) else emptyList()
    check(expectedFiles.toSet().size == expectedFiles.size) { "Candidate payload file names are not unique" }
    check(payload.isDirectory) { "Candidate payload directory is missing" }
    val actualFiles = Files.walk(payload.toPath()).use { paths ->
        paths.filter(Files::isRegularFile).map { payload.toPath().relativize(it).toString().replace(File.separatorChar, '/') }
            .toList().toSet()
    }
    check(actualFiles == expectedFiles.toSet()) {
        "Candidate payload file set mismatch: expected=${expectedFiles.toSet().sorted()} actual=${actualFiles.sorted()}"
    }
    records.forEach { verifyPayloadRecord(payload, it) }
    verifyPromotedCandidatePayload(manifest, payload, expectedVersion, expectedCommit)
    check(policyFiles.keys == policies.keys) { "Candidate policy verifier is incomplete" }
    policyFiles.forEach { (name, file) ->
        val record = policies.releaseObject(name)
        check(record.releaseString("fileName") == file.name) { "Candidate policy file name mismatch: $name" }
        verifyReleaseRecord(file, record)
    }
    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("result", JsonPrimitive("passed"))
        put("releaseTag", JsonPrimitive(expectedTag))
        put("swiftAsset", JsonPrimitive(artifacts.releaseObject("swiftPackage").releaseString("fileName")))
        put("centralBundles", buildJsonArray {
            promotedCentralBundleRecords(manifest).forEach { record ->
                add(JsonPrimitive(record.releaseString("fileName")))
            }
        })
    }
}

internal fun candidatePayloadRecords(manifest: JsonObject): List<JsonObject> = buildList {
    val artifacts = manifest.releaseObject("artifacts")
    add(artifacts.releaseObject("swiftPackage"))
    promotedCentralBundleRecords(manifest).forEach(::add)
    val evidence = manifest.releaseObject("evidence")
    evidence.filterKeys { it !in candidateEvidenceArrayNames }.values.forEach { add(it as JsonObject) }
    candidateEvidenceArrayNames.forEach { name ->
        if (name in evidence) {
            evidence.releaseArray(name).forEach { add(it as JsonObject) }
        }
    }
    manifest.releaseObject("policies").values.forEach { add(it as JsonObject) }
}

private fun verifyPromotedCandidatePayload(
    manifest: JsonObject,
    payload: File,
    expectedVersion: String,
    expectedCommit: String,
) {
    val expectedTree = manifest.releaseString("candidateTree")
    val evidence = manifest.releaseObject("evidence")
    val artifacts = manifest.releaseObject("artifacts")
    val crossLanguageM8Files = evidence.releaseArray("crossLanguageM8").associate { value ->
        val record = value.jsonObject
        val name = record.releaseString("fileName")
        name to safePayloadFile(payload, name)
    }
    verifyCompleteCrossLanguageM8Evidence(crossLanguageM8Files)
    val promotion = safePayloadFile(payload, evidence.releaseObject("promotionReceipt").releaseString("fileName"))
        .readReleaseObject()
    check(promotion.releaseInt("schemaVersion") == 1 &&
        promotion.releaseString("repository") == CodexAgentBuild.REPOSITORY &&
        promotion.releaseString("workflowPath") == ".github/workflows/promote.yml" &&
        promotion.releaseString("result") == "passed" &&
        promotion.releaseString("finalCommit") == expectedCommit &&
        promotion.releaseString("finalTree") == expectedTree &&
        promotion.releaseString("validatedTree") == expectedTree) {
        "Transported promotion receipt identity mismatch"
    }
    val plan = safePayloadFile(payload, evidence.releaseObject("impactPlan").releaseString("fileName"))
        .readReleaseObject()
    val validation = safePayloadFile(payload, evidence.releaseObject("validationReceipt").releaseString("fileName"))
        .readReleaseObject()
    val plannedLanes = plan.releaseObject("lanes")
    check(plannedLanes.keys == promotedCandidateLaneNames) { "Transported impact plan lane set is incomplete" }
    val activeLanes = plannedLanes.filterValues { value ->
        val state = value.jsonObject
        state.releaseBoolean("build") || state.releaseBoolean("test") || state.releaseBoolean("metadata")
    }.keys
    val promotionLanes = promotion.releaseObject("lanes")
    val validationLanes = validation.releaseObject("lanes")
    check(plan.releaseInt("schemaVersion") == 1 && plan.releaseString("repository") == CodexAgentBuild.REPOSITORY &&
        plan.releaseString("event") == "merge_group" && plan.releaseBoolean("mergeReady") &&
        plan.releaseString("validationTree") == expectedTree &&
        validation.releaseInt("schemaVersion") == 1 &&
        validation.releaseString("repository") == CodexAgentBuild.REPOSITORY &&
        validation.releaseString("validationCommit") == promotion.releaseString("validatedCommit") &&
        validation.releaseString("validationTree") == expectedTree && validation.releaseString("result") == "passed" &&
        promotionLanes.keys == promotedCandidateLaneNames && validationLanes.keys == activeLanes) {
        "Transported validation identity mismatch"
    }
    promotionLanes.forEach { (lane, value) ->
        val identity = value.jsonObject
        check(identity.releaseLong("sourceRunId") > 0 && identity.releaseInt("sourceRunAttempt") > 0 &&
            identity.releaseString("promotedArtifactName") == "codex-agent-promoted-$lane-$expectedCommit" &&
            if (lane in activeLanes) {
                val summary = validationLanes.getValue(lane).jsonObject
                identity.releaseString("sourceKind") == "validation" &&
                    identity["sourcePromotionRunId"] == JsonNull && identity["sourcePromotionCommit"] == JsonNull
                    && identity.releaseLong("sourceRunId") == summary.releaseLong("runId")
                    && identity.releaseInt("sourceRunAttempt") == summary.releaseInt("runAttempt")
                    && identity.releaseString("sourceArtifactName") == summary.releaseString("artifactName")
            } else {
                val sourceCommit = identity.releaseString("sourcePromotionCommit")
                identity.releaseString("sourceKind") == "promotion" &&
                    sourceCommit.matches(Regex("[0-9a-f]{40}")) && sourceCommit != expectedCommit &&
                    identity.releaseLong("sourcePromotionRunId") == identity.releaseLong("sourceRunId") &&
                    identity.releaseString("sourceArtifactName") == "codex-agent-promoted-$lane-$sourceCommit"
            }) {
            "Transported promotion provenance is invalid for $lane"
        }
    }
    validationLanes.forEach { (lane, value) ->
        val summary = value.jsonObject
        check(summary.releaseString("result") == "passed" &&
            summary.releaseString("validationCommit").matches(Regex("[0-9a-f]{40}")) &&
            summary.releaseString("validationTree") == expectedTree) {
            "Transported active validation did not pass for $lane"
        }
    }
    val promotedInventory = safePayloadFile(
        payload, evidence.releaseObject("promotedArtifactInventory").releaseString("fileName"),
    ).readReleaseObject()
    val promotedInventoryLanes = promotedInventory.releaseArray("lanes").map { value ->
        val record = value.jsonObject
        val lane = record.releaseString("lane")
        check(record.releaseString("artifactName") == "codex-agent-promoted-$lane-$expectedCommit" &&
            record.releaseArray("files").isNotEmpty()) {
            "Transported promoted-artifact inventory is invalid for $lane"
        }
        lane
    }
    check(promotedInventory.releaseInt("schemaVersion") == 1 &&
        promotedInventory.releaseString("repository") == CodexAgentBuild.REPOSITORY &&
        promotedInventory.releaseString("finalCommit") == expectedCommit &&
        promotedInventory.releaseString("finalTree") == expectedTree &&
        promotedInventoryLanes.toSet() == promotedCandidateLaneNames &&
        promotedInventoryLanes.size == promotedCandidateLaneNames.size) {
        "Transported promoted-artifact inventory identity mismatch"
    }

    val mavenFile = safePayloadFile(payload, evidence.releaseObject("mavenInventory").releaseString("fileName"))
    val maven = mavenFile.readReleaseObject()
    val expectedArtifactIds = expectedMavenPrimaryPaths(expectedVersion).map { it.substringBefore('/') }.toSet()
    val artifactIds = maven.releaseArray("artifactIds").map { it.jsonPrimitive.content }
    check(maven.keys == setOf(
        "schemaVersion", "groupId", "version", "artifactIds", "signaturesRequired", "primaryArtifactCount", "files",
    ) && maven.releaseInt("schemaVersion") == 3 &&
        maven.releaseString("groupId") == CodexAgentBuild.MAVEN_GROUP &&
        maven.releaseString("version") == expectedVersion && maven.releaseBoolean("signaturesRequired") &&
        artifactIds.size == expectedArtifactIds.size && artifactIds.toSet() == expectedArtifactIds &&
        maven.releaseInt("primaryArtifactCount") == expectedMavenPrimaryPaths(expectedVersion).size) {
        "Transported Maven inventory is not the signed promoted repository"
    }
    val centralFile = safePayloadFile(
        payload, evidence.releaseObject("centralBundleInventory").releaseString("fileName"),
    )
    val central = centralFile.readReleaseObject()
    val centralBundles = promotedCentralBundleRecords(manifest).associate { record ->
        val file = safePayloadFile(payload, record.releaseString("fileName"))
        verifyReleaseRecord(file, record)
        file.name to file
    }
    val bundleInventory = central.releaseArray("bundles").map { it.jsonObject }
    check(central.releaseInt("schemaVersion") == 3 &&
        central.releaseBoolean("allBundlesBelowCentralPortalUploadLimit") &&
        central.releaseLong("centralPortalUploadLimitBytes") == CENTRAL_PORTAL_UPLOAD_LIMIT_BYTES &&
        central.releaseString("mavenInventorySha256") == mavenFile.releaseDigest() &&
        bundleInventory.size == centralBundleShardNames.size &&
        bundleInventory.map { it.releaseString("shard") }.toSet() == centralBundleShardNames.toSet() &&
        bundleInventory.sumOf { it.releaseInt("entryCount") } == central.releaseInt("includedArtifactCount")) {
        "Transported Central inventory does not bind the signed Maven inventory"
    }
    bundleInventory.forEach { record ->
        val shard = record.releaseString("shard")
        check(record.releaseString("fileName") == centralBundleFileName(expectedVersion, shard)) {
            "Transported Central bundle inventory file name is invalid"
        }
        val bundle = centralBundles.getValue(centralBundleFileName(expectedVersion, shard))
        check(bundle.length() < CENTRAL_PORTAL_UPLOAD_LIMIT_BYTES) { "Transported Central bundle exceeds limit" }
        verifyReleaseRecord(bundle, record)
    }
    val centralBundle = centralBundles.getValue(centralBundleFileName(expectedVersion, CENTRAL_MAIN_SHARD))

    val swift = safePayloadFile(payload, artifacts.releaseObject("swiftPackage").releaseString("fileName"))
    val swiftChecksum = safePayloadFile(
        payload, evidence.releaseObject("swiftPackageChecksum").releaseString("fileName"),
    )
    check(swiftChecksum.readText().trim() == swift.releaseDigest() &&
        artifacts.releaseObject("swiftPackage").releaseString("swiftPmChecksum") == swift.releaseDigest()) {
        "Transported Swift checksum does not bind the promoted ZIP"
    }
    check(evidence.releaseObject("privacyAudit").releaseString("fileName") == "privacy-audit.json") {
        "Transported promoted privacy audit is missing"
    }
    verifyPromotedIosEvidence(manifest, payload, expectedVersion, expectedCommit, expectedTree, swift, swiftChecksum)
    verifyPromotedRuntimeEvidence(manifest, payload, expectedVersion, mavenFile, centralBundle)
}

private fun verifyPromotedIosEvidence(
    manifest: JsonObject,
    payload: File,
    version: String,
    commit: String,
    tree: String,
    swiftArchive: File,
    swiftChecksum: File,
) {
    val evidence = manifest.releaseObject("evidence")
    val policies = manifest.releaseObject("policies")
    val packageSwift = safePayloadFile(payload, policies.releaseObject("packageSwift").releaseString("fileName"))
    val resourcePolicy = safePayloadFile(
        payload,
        policies.releaseObject("iosResourcePolicy").releaseString("fileName"),
    )
    val swiftProof = safePayloadFile(
        payload,
        evidence.releaseObject("swiftPackageProof").releaseString("fileName"),
    ).readReleaseObject()
    check(swiftProof.keys == setOf(
        "schemaVersion", "protocol", "result", "version", "releaseTag", "candidateCommit", "candidateTree",
        "producerCommit", "producerTree", "packageSwiftUrl", "swiftPmChecksum", "archive", "checksumFile",
        "packageSwift",
    ) && swiftProof.releaseInt("schemaVersion") == 1 &&
        swiftProof.releaseString("protocol") == "promoted-swift-package-v1" &&
        swiftProof.releaseString("result") == "passed" && swiftProof.releaseString("version") == version &&
        swiftProof.releaseString("releaseTag") == "v$version" &&
        swiftProof.releaseString("candidateCommit") == commit && swiftProof.releaseString("candidateTree") == tree &&
        swiftProof.releaseString("producerCommit").matches(Regex("[0-9a-f]{40}")) &&
        swiftProof.releaseString("producerTree").matches(Regex("[0-9a-f]{40}")) &&
        swiftProof.releaseString("packageSwiftUrl") ==
        "https://github.com/${CodexAgentBuild.REPOSITORY}/releases/download/v$version/${swiftArchive.name}" &&
        swiftProof.releaseString("swiftPmChecksum") == swiftArchive.releaseDigest()) {
        "Promoted Swift package proof identity is invalid"
    }
    verifyReleaseRecord(swiftArchive, swiftProof.releaseObject("archive"))
    verifyReleaseRecord(swiftChecksum, swiftProof.releaseObject("checksumFile"))
    verifyReleaseRecord(packageSwift, swiftProof.releaseObject("packageSwift"))
    val packageContents = packageSwift.readText()
    check(Regex("""url\s*:\s*"([^"]+)"""").findAll(packageContents).map { it.groupValues[1] }.toList() ==
        listOf(swiftProof.releaseString("packageSwiftUrl")) &&
        Regex("""checksum\s*:\s*"([0-9a-f]{64})"""").findAll(packageContents)
            .map { it.groupValues[1] }.toList() == listOf(swiftArchive.releaseDigest())) {
        "Promoted Package.swift does not contain the exact release URL and checksum"
    }

    fun producer(record: JsonObject) = TransportProducerIdentity(
        record.releaseString("producerCommit"),
        record.releaseString("producerTree"),
    )
    fun producedFile(name: String): Pair<File, TransportProducerIdentity> {
        val record = evidence.releaseObject(name)
        return safePayloadFile(payload, record.releaseString("fileName")) to producer(record)
    }
    fun verifyRustProof(name: String, spec: AppleRustSliceSpec): JsonObject {
        val record = evidence.releaseObject(name)
        val proof = safePayloadFile(payload, record.releaseString("fileName")).readReleaseObject()
        check(proof.keys == setOf(
            "schemaVersion", "protocol", "result", "candidateCommit", "candidateTree", "cleanCheckout", "target",
            "archive", "nativeInputsSha256", "nativeProvenanceSha256", "compilerSettingsSha256", "rustToolchain",
            "rustSrcComponent", "rustCompilerIdentitySha256", "appleToolchainIdentitySha256", "xcodeVersionSha256",
            "swiftVersionSha256",
        ) && proof.releaseInt("schemaVersion") == 2 &&
            proof.releaseString("protocol") == "codex-agent-ios-rust-slice-v2" &&
            proof.releaseString("result") == "passed" && proof.releaseBoolean("cleanCheckout") &&
            proof.releaseString("candidateCommit") == record.releaseString("producerCommit") &&
            proof.releaseString("candidateTree") == record.releaseString("producerTree") &&
            proof.releaseString("target") == spec.target && proof.releaseString("rustToolchain").isNotBlank() &&
            proof.releaseString("rustSrcComponent") == "required") {
            "Promoted ${spec.target} Rust proof identity is invalid"
        }
        listOf(
            "nativeInputsSha256", "nativeProvenanceSha256", "compilerSettingsSha256",
            "rustCompilerIdentitySha256", "appleToolchainIdentitySha256", "xcodeVersionSha256", "swiftVersionSha256",
        ).forEach { field ->
            check(proof.releaseString(field).matches(Regex("[0-9a-f]{64}"))) {
                "Promoted ${spec.target} Rust proof has an invalid $field"
            }
        }
        val archive = proof.releaseObject("archive")
        check(archive.keys == setOf("fileName", "bytes", "sha256") &&
            archive.releaseString("fileName") == spec.archiveName &&
            archive.releaseString("fileName") == record.releaseString("archiveFileName") &&
            archive.releaseLong("bytes") == record.releaseLong("archiveBytes") &&
            archive.releaseString("sha256") == record.releaseString("archiveSha256")) {
            "Promoted ${spec.target} Rust proof archive binding is invalid"
        }
        return proof
    }
    val deviceProof = verifyRustProof("iosDeviceRustProof", appleRustSliceSpecs[0])
    val simulatorProof = verifyRustProof("iosSimulatorRustProof", appleRustSliceSpecs[1])
    listOf(
        "nativeInputsSha256", "nativeProvenanceSha256", "compilerSettingsSha256", "rustToolchain",
        "rustSrcComponent", "rustCompilerIdentitySha256", "xcodeVersionSha256", "swiftVersionSha256",
    ).forEach { field ->
        check(deviceProof.releaseString(field) == simulatorProof.releaseString(field)) {
            "Promoted Rust slice proofs disagree on $field"
        }
    }

    val (nativeTestsFile, nativeTestsProducer) = producedFile("iosNativeTests")
    val nativeTests = nativeTestsFile.readReleaseObject()
    check(nativeTests.keys == setOf(
        "schemaVersion", "protocol", "result", "candidateCommit", "candidateTree", "cleanCheckout",
        "commandCount", "passedCommandCount", "commands", "nativeInputsSha256", "nativeProvenanceSha256",
        "rustToolchain", "rustSrcComponent",
    ) && nativeTests.releaseInt("schemaVersion") == 2 &&
        nativeTests.releaseString("protocol") == "codex-agent-ios-native-tests-v2" &&
        nativeTests.releaseString("result") == "passed" && nativeTests.releaseBoolean("cleanCheckout") &&
        nativeTests.releaseString("candidateCommit") == nativeTestsProducer.commit &&
        nativeTests.releaseString("candidateTree") == nativeTestsProducer.tree &&
        nativeTests.releaseString("nativeInputsSha256") == deviceProof.releaseString("nativeInputsSha256") &&
        nativeTests.releaseString("nativeProvenanceSha256") == deviceProof.releaseString("nativeProvenanceSha256") &&
        nativeTests.releaseString("rustToolchain") == deviceProof.releaseString("rustToolchain") &&
        nativeTests.releaseString("rustSrcComponent") == "not-required") {
        "Promoted Apple native-test proof identity is invalid"
    }
    val expectedCommands = listOf(
        AppleNativeTestCommand(
            ":codex-agent-runtime-ios:testCodexIosBridge",
            listOf("test", "--locked", "-p", "codex-agent-ios-bridge", "--lib"),
        ),
        AppleNativeTestCommand(
            ":codex-agent-runtime-ios:testCodexIosDirectToolMode",
            listOf(
                "test", "--locked", "-p", "codex-core", "--lib",
                "ios_runtime_forces_direct_tools_for_code_mode_only_models",
            ),
        ),
    )
    val actualCommands = nativeTests.releaseArray("commands").map { value ->
        val command = value.jsonObject
        check(command.keys == setOf("taskPath", "cargoArguments", "result") &&
            command.releaseString("result") == "passed") {
            "Promoted Apple native-test command is invalid"
        }
        AppleNativeTestCommand(
            command.releaseString("taskPath"),
            command.releaseArray("cargoArguments").map { it.toString().trim('"') },
        )
    }
    check(nativeTests.releaseInt("commandCount") == expectedCommands.size &&
        nativeTests.releaseInt("passedCommandCount") == expectedCommands.size && actualCommands == expectedCommands) {
        "Promoted Apple native-test command set is incomplete"
    }

    val (artifactMetricsFile, artifactMetricsProducer) = producedFile("artifactMetrics")
    check(artifactMetricsProducer.commit == swiftProof.releaseString("producerCommit") &&
        artifactMetricsProducer.tree == swiftProof.releaseString("producerTree")) {
        "Promoted iOS artifact metrics and Swift package have different producers"
    }
    val artifactMetrics = artifactMetricsFile.readReleaseObject()
    check(artifactMetrics.keys == setOf(
        "compressedXcframeworkBytes", "deviceFrameworkBytes", "sampleAppInstallBytes",
    ) && artifactMetrics.releaseLong("compressedXcframeworkBytes") == swiftArchive.length() &&
        artifactMetrics.releaseLong("deviceFrameworkBytes") > 0 &&
        artifactMetrics.releaseLong("sampleAppInstallBytes") > 0) {
        "Promoted iOS artifact metrics do not bind the Swift archive"
    }
    verifyAppleArtifactBudgets(
        AppleArtifactMetrics(
            artifactMetrics.releaseLong("compressedXcframeworkBytes"),
            artifactMetrics.releaseLong("deviceFrameworkBytes"),
            artifactMetrics.releaseLong("sampleAppInstallBytes"),
        ),
        resourcePolicy,
    )
    val (runtimeMetrics, _) = producedFile("iosRuntimeMetrics")
    validateIosRuntimeMetrics(runtimeMetrics.readReleaseObject())
}

private data class TransportedRuntimeEvidence(
    val file: File,
    val producerCommit: String,
)

private fun verifyPromotedRuntimeEvidence(
    manifest: JsonObject,
    payload: File,
    version: String,
    mavenInventory: File,
    centralBundle: File,
) {
    val evidence = manifest.releaseObject("evidence")
    fun records(name: String) = evidence.releaseArray(name).map { value ->
        val record = value as? JsonObject ?: error("Invalid promoted $name record")
        TransportedRuntimeEvidence(
            safePayloadFile(payload, record.releaseString("fileName")),
            record.releaseString("producerCommit"),
        )
    }
    fun record(name: String): File {
        val value = evidence.releaseObject(name)
        value.releaseString("producerCommit")
        return safePayloadFile(payload, value.releaseString("fileName"))
    }
    fun commits(
        values: List<TransportedRuntimeEvidence>,
        fileName: (String) -> String,
    ) = desktopRuntimeEvidenceTargets.keys.associateWith { target ->
        values.single { it.file.name == fileName(target) }.producerCommit
    }

    val desktop = records("desktopRuntime")
    val jvm = records("jvmRuntime")
    val node = records("nodeRuntime")
    val nodeWasm = records("nodeWasmRuntime")
    val android = records("androidRuntime")
    val distributionManifest = safePayloadFile(
        payload,
        manifest.releaseObject("policies").releaseObject("desktopDistributionManifest").releaseString("fileName"),
    )
    val temporary = Files.createTempDirectory("codex-agent-promoted-runtime-").toFile()
    try {
        val classifiers = extractCandidateDesktopClassifiers(centralBundle, version, temporary)
        val desktopCommits = commits(desktop, ::desktopRuntimeEvidenceFileName)
        val jvmCommits = commits(jvm, ::jvmRuntimeEvidenceFileName)
        val nodeCommits = commits(node) { target -> nodeRuntimeEvidenceFileName(target, NODE_RUNTIME_JS_BACKEND) }
        val nodeWasmCommits = commits(nodeWasm) { target ->
            nodeRuntimeEvidenceFileName(target, NODE_RUNTIME_WASM_BACKEND)
        }
        check(listOf(jvmCommits, nodeCommits, nodeWasmCommits).all { it == desktopCommits }) {
            "Promoted runtime evidence for one desktop lane has inconsistent producer commits"
        }
        val desktopErrors = validateDesktopRuntimeEvidence(
            desktop.map(TransportedRuntimeEvidence::file),
            desktopCommits,
            version,
            mavenInventory,
            distributionManifest,
            classifiers,
        )
        check(desktopErrors.isEmpty()) {
            "Promoted desktop runtime evidence is invalid: ${desktopErrors.joinToString()}"
        }
        val jvmErrors = validateJvmRuntimeEvidence(
            jvm.map(TransportedRuntimeEvidence::file),
            jvmCommits,
            distributionManifest,
            classifiers,
            record("jvmRuntimeRunner"),
        )
        check(jvmErrors.isEmpty()) { "Promoted JVM runtime evidence is invalid: ${jvmErrors.joinToString()}" }
        listOf(
            Triple(NODE_RUNTIME_JS_BACKEND, node, "nodeRuntimeRunner"),
            Triple(NODE_RUNTIME_WASM_BACKEND, nodeWasm, "nodeWasmRuntimeRunner"),
        ).forEach { (backend, runtimeEvidence, runnerName) ->
            val errors = validateNodeRuntimeEvidence(
                runtimeEvidence.map(TransportedRuntimeEvidence::file),
                if (backend == NODE_RUNTIME_JS_BACKEND) nodeCommits else nodeWasmCommits,
                backend,
                distributionManifest,
                classifiers,
                record(runnerName),
            )
            check(errors.isEmpty()) {
                "Promoted Node $backend runtime evidence is invalid: ${errors.joinToString()}"
            }
        }
    } finally {
        temporary.deleteRecursively()
    }
    val androidCommits = android.map(TransportedRuntimeEvidence::producerCommit).toSet()
    check(androidCommits.size == 1) { "Promoted Firebase Android evidence has multiple validation commits" }
    val androidFiles = android.map(TransportedRuntimeEvidence::file)
    verifyCandidateFirebaseAndroidEvidence(androidFiles, androidCommits.single())
    verifyCandidateCentralAndroidRuntimeBinding(androidFiles, centralBundle, version)
}

private fun extractCandidateDesktopClassifiers(
    centralBundle: File,
    version: String,
    output: File,
): List<File> = ZipFile(centralBundle).use { central ->
    desktopRuntimeEvidenceTargets.values.map { target ->
        val name = "codex-agent-runtime-desktop-$version-${target.classifier}.zip"
        val path = "${CodexAgentBuild.MAVEN_GROUP.replace('.', '/')}/codex-agent-runtime-desktop/$version/$name"
        val entries = central.entries().asSequence().filter { !it.isDirectory && it.name == path }.toList()
        check(entries.size == 1) { "Central bundle must contain exactly one $name" }
        output.resolve(name).also { classifier ->
            central.getInputStream(entries.single()).use { input ->
                classifier.outputStream().use(input::copyTo)
            }
        }
    }
}

internal fun candidateGithubOutputs(result: JsonObject): String = buildString {
    append("releaseTag=").append(result.releaseString("releaseTag")).append('\n')
    append("swiftAsset=").append(result.releaseString("swiftAsset")).append('\n')
    append("centralBundles=").append(result.releaseArray("centralBundles")).append('\n')
}

internal fun resolveCandidatePrivacyReview(
    manifest: JsonObject,
    payload: File,
    explicitReview: File?,
    decisionTemplate: File?,
): File {
    val payloadReview = manifest.releaseObject("policies").releaseObject("privacyRequiredReasonReviews")
        .releaseString("fileName").let { safePayloadFile(payload, it) }
    val exactReview = explicitReview ?: payloadReview
    decisionTemplate?.let { template ->
        val auditName = manifest.releaseObject("evidence").releaseObject("privacyAudit").releaseString("fileName")
        verifyBoundIosPrivacyReview(template, exactReview, safePayloadFile(payload, auditName))
    }
    return exactReview
}

private fun verifyPayloadRecord(payload: File, record: JsonObject) {
    verifyReleaseRecord(safePayloadFile(payload, record.releaseString("fileName")), record)
}

internal fun validateIosRuntimeMetrics(metrics: JsonObject) {
    fun durations(name: String) = metrics.releaseArray(name).map { value ->
        (value as? JsonPrimitive)?.longOrNull ?: error("Invalid $name value")
    }
    val startup = durations("startupMilliseconds")
    val shutdown = durations("shutdownMilliseconds")
    check(metrics.releaseInt("warmupCycles") == 1 && metrics.releaseInt("measuredCycles") == 5) {
        "iOS runtime metrics use the wrong cycle counts"
    }
    check(startup.size == 5 && startup.all { it in 0L until 30_000L }) { "iOS runtime startup gate failed" }
    check(shutdown.size == 5 && shutdown.all { it in 0L until 5_000L }) { "iOS runtime shutdown gate failed" }
    check(metrics.releaseLong("coldStartupMilliseconds") in 0L until 30_000L) { "iOS cold startup gate failed" }
    check(metrics.releaseLong("startupMaximumMilliseconds") == startup.max()) { "iOS startup maximum mismatch" }
    check(metrics.releaseLong("shutdownMaximumMilliseconds") == shutdown.max()) { "iOS shutdown maximum mismatch" }
    check(metrics.releaseLong("idleCurrentResidentBytes") >= 0L) { "iOS idle memory is invalid" }
    check(metrics.releaseLong("recursiveSearchCurrentResidentBytes") >= 0L) { "iOS search memory is invalid" }
}
