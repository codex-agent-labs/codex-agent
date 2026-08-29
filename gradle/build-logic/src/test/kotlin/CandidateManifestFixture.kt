import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

internal fun schema15CandidateManifest(
    version: String,
    commit: String,
    centralBundles: Map<String, File> = emptyMap(),
): JsonObject {
    fun record(name: String) = buildJsonObject {
        put("fileName", JsonPrimitive(name))
        put("bytes", JsonPrimitive(1))
        put("sha256", JsonPrimitive("a".repeat(64)))
    }
    fun runtimeRecord(name: String) = buildJsonObject {
        record(name).forEach { (key, value) -> put(key, value) }
        put("producerCommit", JsonPrimitive(commit))
    }
    fun producedRecord(name: String) = buildJsonObject {
        record(name).forEach { (key, value) -> put(key, value) }
        put("producerCommit", JsonPrimitive(commit))
        put("producerTree", JsonPrimitive("b".repeat(40)))
    }
    fun rustProofRecord(name: String, spec: AppleRustSliceSpec) = buildJsonObject {
        producedRecord(name).forEach { (key, value) -> put(key, value) }
        put("target", JsonPrimitive(spec.target))
        put("archiveFileName", JsonPrimitive(spec.archiveName))
        put("archiveBytes", JsonPrimitive(9))
        put("archiveSha256", JsonPrimitive("c".repeat(64)))
    }
    fun centralRecord(shard: String): JsonObject = centralBundles[shard]?.releaseRecord()
        ?: record(centralBundleFileName(version, shard))

    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(PROMOTED_CANDIDATE_SCHEMA))
        put("version", JsonPrimitive(version))
        put("releaseTag", JsonPrimitive("v$version"))
        put("candidateCommit", JsonPrimitive(commit))
        put("candidateTree", JsonPrimitive("d".repeat(40)))
        put("protectedCandidate", JsonPrimitive(true))
        put("artifacts", buildJsonObject {
            put("swiftPackage", buildJsonObject {
                record("CodexAgent-$version.xcframework.zip").forEach { (key, value) -> put(key, value) }
                put("swiftPmChecksum", JsonPrimitive("a".repeat(64)))
                put("members", buildJsonArray {})
            })
            put("centralBundles", buildJsonArray {
                centralBundleShardNames.forEach { add(centralRecord(it)) }
            })
            put("sbom", record(aggregateReleaseSbomFileName(version)))
        })
        put("evidence", buildJsonObject {
            mapOf(
                "swiftPackageChecksum" to "CodexAgent-$version.xcframework.zip.sha256",
                "centralBundleInventory" to "central-bundle.json",
                "mavenInventory" to "maven-inventory.json",
                "promotionReceipt" to "promotion-receipt.json",
                "impactPlan" to "impact-plan.json",
                "validationReceipt" to "validation-receipt.json",
                "promotedArtifactInventory" to "promoted-artifact-inventory.json",
                "privacyAudit" to "privacy-audit.json",
                "swiftPackageProof" to "swift-package-proof.json",
                "releaseTooling" to RELEASE_TOOLING_FILE_NAME,
            ).forEach { (name, fileName) -> put(name, record(fileName)) }
            put("jvmRuntimeRunner", runtimeRecord(JVM_RUNTIME_RUNNER_ARCHIVE))
            put("nodeRuntimeRunner", runtimeRecord(NODE_RUNTIME_RUNNER_ARCHIVE))
            put("nodeWasmRuntimeRunner", runtimeRecord(NODE_WASM_RUNTIME_RUNNER_ARCHIVE))
            put("iosNativeTests", producedRecord(IOS_NATIVE_TESTS_PROOF))
            put("artifactMetrics", producedRecord("artifact-metrics.json"))
            put("iosRuntimeMetrics", producedRecord("runtime-metrics.json"))
            put("iosDeviceRustProof", rustProofRecord(appleRustSliceSpecs[0].proofName, appleRustSliceSpecs[0]))
            put("iosSimulatorRustProof", rustProofRecord(appleRustSliceSpecs[1].proofName, appleRustSliceSpecs[1]))
            mapOf(
                "desktopRuntime" to desktopRuntimeEvidenceTargets.keys.map(::desktopRuntimeEvidenceFileName),
                "jvmRuntime" to desktopRuntimeEvidenceTargets.keys.map(::jvmRuntimeEvidenceFileName),
                "nodeRuntime" to desktopRuntimeEvidenceTargets.keys.map {
                    nodeRuntimeEvidenceFileName(it, NODE_RUNTIME_JS_BACKEND)
                },
                "nodeWasmRuntime" to desktopRuntimeEvidenceTargets.keys.map {
                    nodeRuntimeEvidenceFileName(it, NODE_RUNTIME_WASM_BACKEND)
                },
                "androidRuntime" to candidateFirebaseAndroidEvidenceFileNames,
                "crossLanguageM8" to crossLanguageM8EvidenceFileNames,
            ).forEach { (name, fileNames) ->
                put(name, buildJsonArray { fileNames.forEach { add(runtimeRecord(it)) } })
            }
        })
        put("policies", buildJsonObject {
            mapOf(
                "approvals" to "publication-approvals.json",
                "privacyManifest" to "PrivacyInfo.xcprivacy",
                "privacyDataFlowReview" to "privacy-data-flow-review.json",
                "privacyRequiredReasonReviews" to "privacy-required-reason-reviews.json",
                "iosResourcePolicy" to "ios-resource-policy.json",
                "packageSwift" to "Package.swift",
                "desktopDistributionManifest" to "codex-app-server-distributions.json",
                "desktopBundledLicense" to "openai-codex-LICENSE.txt",
                "desktopBundledNotice" to "openai-codex-NOTICE.txt",
            ).forEach { (name, fileName) -> put(name, record(fileName)) }
        })
    }
}

internal fun writeTestIosRuntimeMetrics(file: File, startup: Long = 10): File = file.apply {
    atomicWriteJson(buildJsonObject {
        put("warmupCycles", JsonPrimitive(1))
        put("measuredCycles", JsonPrimitive(5))
        put("coldStartupMilliseconds", JsonPrimitive(10))
        put("startupMilliseconds", buildJsonArray { repeat(5) { add(JsonPrimitive(startup)) } })
        put("startupMaximumMilliseconds", JsonPrimitive(startup))
        put("shutdownMilliseconds", buildJsonArray { repeat(5) { add(JsonPrimitive(10)) } })
        put("shutdownMaximumMilliseconds", JsonPrimitive(10))
        put("idleCurrentResidentBytes", JsonPrimitive(1))
        put("recursiveSearchCurrentResidentBytes", JsonPrimitive(2))
    })
}
