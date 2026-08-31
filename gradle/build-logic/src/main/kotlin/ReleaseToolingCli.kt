import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

private class ReleaseToolingArguments(values: Array<String>) {
    private val values = buildMap {
        check(values.size % 2 == 0) { "Release-tooling options must be --name value pairs" }
        values.asList().chunked(2).forEach { (name, value) ->
            check(name.startsWith("--") && name.length > 2 && put(name.removePrefix("--"), value) == null) {
                "Malformed or duplicate release-tooling option: $name"
            }
        }
    }

    fun required(name: String): String = values[name]?.takeIf(String::isNotBlank)
        ?: error("Missing release-tooling option: --$name")

    fun file(name: String): File = File(required(name))
    fun long(name: String): Long = required(name).toLong()
    fun int(name: String): Int = required(name).toInt()
    fun requireOnly(vararg names: String) {
        check(values.keys == names.toSet()) {
            "Unexpected release-tooling options: ${(values.keys - names.toSet()).sorted()}"
        }
    }
}

fun main(arguments: Array<String>) {
    val command = arguments.firstOrNull() ?: error("Release-tooling command is required")
    val options = ReleaseToolingArguments(arguments.drop(1).toTypedArray())
    when (command) {
        "self-check" -> {
            options.requireOnly()
            check(canonicalPromotedMavenOwners().size == expectedMavenPrimaryPaths("VERSION")
                .map { it.substringBefore('/') }.toSet().size)
            check(centralAuthorization("user", "password").startsWith("Bearer "))
            check(releaseJson.parseToJsonElement("{\"ready\":true}").jsonObject.releaseBoolean("ready"))
            check(requireIosFreeDiskSpace(2L * 1024 * 1024 * 1024, 1) > 0)
            check(desktopRuntimeEvidenceFileName("linuxX64") == "desktop-runtime-linuxX64.json")
            check(crossLanguageCAbiTargetSpecs.size == 5)
            check(productionCrossLanguageCAbiScenarioMappings().sumOf { it.testIds.size } == 231)
            println("codex-agent release tooling is ready")
        }
        "assemble-c-abi-binding-receipt" -> {
            options.requireOnly(
                "repository", "bootstrap", "scenario-proof", "packages", "proofs",
                "version", "commit", "tree", "output",
            )
            val output = options.file("output")
            Files.deleteIfExists(output.toPath())
            val repository = options.file("repository").canonicalFile
            val bootstrap = options.file("bootstrap")
            val scenarioFile = options.file("scenario-proof")
            val packages = options.file("packages")
            val proofs = options.file("proofs")
            val version = options.required("version")
            val commit = options.required("commit")
            val tree = options.required("tree")
            val archiveNames = crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
                crossLanguageCAbiArchiveFileName(version, target)
            }
            val proofNames = crossLanguageCAbiTargetSpecs.keys.associateWith(::crossLanguageCAbiPackageEvidenceFileName)
            requireExactReleaseToolingDirectory(packages, archiveNames.values.toSet(), "C ABI packages")
            requireExactReleaseToolingDirectory(proofs, proofNames.values.toSet(), "C ABI package proofs")
            val header = repository.resolve("codex-agent-runtime-desktop/native/c-api/include/codex_agent.h")
            val license = repository.resolve("LICENSE")
            val notice = repository.resolve("THIRD_PARTY_NOTICES.md")
            val consumers = repository.resolve("codex-agent-runtime-desktop/native/c-api/consumer")
                .listFiles().orEmpty().filter { it.extension in setOf("c", "cpp") }
            crossLanguageCAbiTargetSpecs.keys.sorted().forEach { target ->
                val exportPolicy = repository.resolve(
                    "codex-agent-runtime-desktop/native/c-api/exports/" + when {
                        target.startsWith("macos") -> "macos.exports"
                        target.startsWith("linux") -> "linux.map"
                        else -> "windows.def"
                    },
                )
                portableVerifyCrossLanguageCAbiPackageEvidence(
                    target, version, commit, tree,
                    packages.resolve(archiveNames.getValue(target)),
                    proofs.resolve(proofNames.getValue(target)),
                    header, license, notice, exportPolicy, consumers,
                )
            }
            val scenario = readCrossLanguageCAbiScenarioProof(scenarioFile, bootstrap)
            val artifacts = buildList {
                add(CrossLanguageBindingArtifactIdentity("c-abi-bootstrap", bootstrap.releaseDigest()))
                add(CrossLanguageBindingArtifactIdentity(C_ABI_SCENARIO_PROOF_ARTIFACT_ID, scenarioFile.releaseDigest()))
                crossLanguageCAbiTargetSpecs.keys.sorted().forEach { target ->
                    add(CrossLanguageBindingArtifactIdentity(
                        crossLanguageCAbiPackageProofIds.getValue(target),
                        proofs.resolve(proofNames.getValue(target)).releaseDigest(),
                    ))
                }
            }
            writeCrossLanguageCAbiBindingReceipt(
                output,
                CrossLanguageCAbiBindingEvidenceInput(
                    bootstrapEvidence = bootstrap,
                    scenarioMappings = scenario.mappings,
                    artifactIdentities = artifacts,
                    testProgramSha256 = scenario.testProgramSha256,
                    testResultsSha256 = scenario.testResultsSha256,
                ),
            )
        }
        "assemble-native-wrapper-binding-receipt" -> {
            options.requireOnly(
                "phase", "language", "api-report", "coverage-receipt", "c-abi-bootstrap",
                "claims", "compiler-evidence", "test-program", "test-results", "packages",
                "host-evidence", "staged-c-abi-sdks", "output",
            )
            val output = options.file("output")
            Files.deleteIfExists(output.toPath())
            val phaseName = options.required("phase")
            val phase = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phaseName }
                ?: error("Unknown native wrapper binding phase: $phaseName")
            val languageName = options.required("language")
            val language = CrossLanguageBinding.entries.singleOrNull { it.id == languageName }
                ?: error("Unknown native wrapper binding language: $languageName")
            val expected = deriveCrossLanguageNativeWrapperBindingReceipt(
                CrossLanguageNativeWrapperEvidenceInput(
                    phase = phase,
                    language = language,
                    apiReport = options.file("api-report"),
                    canonicalCoverageReceipt = options.file("coverage-receipt"),
                    cAbiBootstrapEvidence = options.file("c-abi-bootstrap"),
                    claims = options.file("claims"),
                    compilerEvidence = options.file("compiler-evidence"),
                    testProgram = options.file("test-program"),
                    testResults = options.file("test-results"),
                    packageArtifacts = nativeWrapperPackageArtifacts(language, options.file("packages")),
                    hostEvidenceDirectory = options.file("host-evidence"),
                    stagedCAbiSdks = options.file("staged-c-abi-sdks"),
                ),
            )
            writeCrossLanguageBindingReceipt(output, expected)
            check(readCrossLanguageBindingReceipt(output).toJson() == expected.toJson()) {
                "Native wrapper binding receipt does not match freshly recomputed evidence"
            }
        }
        "advance-cross-language-binding-receipt" -> {
            options.requireOnly("phase", "source", "output")
            val phaseName = options.required("phase")
            val phase = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phaseName }
                ?: error("Unknown carried binding phase: $phaseName")
            advanceCrossLanguageBindingReceiptPhase(
                options.file("source"),
                phase,
                options.file("output"),
            )
        }
        "audit-cross-language-bindings" -> {
            options.requireOnly("phase", "api-report", "coverage-receipt", "receipts", "output")
            val output = options.file("output")
            Files.deleteIfExists(output.toPath())
            val phaseName = options.required("phase")
            val phase = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phaseName }
                ?: error("Unknown cross-language binding phase: $phaseName")
            writeCompleteCrossLanguageBindingAudit(
                phase = phase,
                apiReport = options.file("api-report"),
                canonicalCoverageReceipt = options.file("coverage-receipt"),
                receiptDirectory = options.file("receipts"),
                auditFile = output,
            )
        }
        "stage-promoted-maven" -> {
            options.requireOnly("promoted", "commit", "version", "output")
            stageCanonicalPromotedMavenPrimaries(
                options.file("promoted"), options.required("commit"), options.required("version"),
                options.file("output"),
            )
        }
        "assemble-promoted-candidate" -> {
            options.requireOnly(
                "repository", "promoted", "signed-maven", "version", "tag", "commit", "tree",
                "promotion-run-id", "promotion-run-attempt", "release-tool", "payload",
            )
            val repository = options.file("repository").canonicalFile
            assemblePromotedCandidate(PromotedCandidateInputs(
                promotedArtifacts = options.file("promoted"),
                signedMavenRepository = options.file("signed-maven"),
                version = options.required("version"),
                releaseTag = options.required("tag"),
                commit = options.required("commit"),
                tree = options.required("tree"),
                promotionRunId = options.long("promotion-run-id"),
                promotionRunAttempt = options.int("promotion-run-attempt"),
                approvals = repository.resolve("gradle/release/publication-approvals.json"),
                privacyManifest = repository.resolve(
                    "codex-agent-runtime-ios/apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy",
                ),
                privacyDataFlowReview = repository.resolve("gradle/release/privacy-data-flow-review.json"),
                privacyReviewTemplate = repository.resolve("gradle/release/privacy-required-reason-review.json"),
                iosResourcePolicy = repository.resolve("gradle/release/ios-resource-policy.json"),
                packageSwift = repository.resolve("Package.swift"),
                remoteConsumerManifest = repository.resolve("codex-agent-runtime-ios/apple/RemoteConsumer/Package.swift"),
                desktopDistributionManifest = repository.resolve(
                    "codex-agent-runtime-desktop/codex-app-server-distributions.json",
                ),
                desktopBundledLicense = repository.resolve(
                    "legal/openai-codex/openai-codex-LICENSE.txt",
                ),
                desktopBundledNotice = repository.resolve(
                    "legal/openai-codex/openai-codex-NOTICE.txt",
                ),
                releaseTooling = options.file("release-tool"),
                repository = repository,
                payload = options.file("payload"),
            ))
        }
        "verify-candidate" -> {
            options.requireOnly(
                "repository", "manifest", "payload", "version", "tag", "commit",
                "verification-output", "github-output",
            )
            val repository = options.file("repository").canonicalFile
            val manifestFile = options.file("manifest")
            val payload = options.file("payload")
            val manifest = manifestFile.readReleaseObject()
            check(manifest.releaseInt("schemaVersion") == PROMOTED_CANDIDATE_SCHEMA) {
                "Publication requires the current promoted candidate schema"
            }
            verifyCandidateManifestStructure(manifest)
            val exactReview = resolveCandidatePrivacyReview(
                manifest,
                payload,
                explicitReview = null,
                decisionTemplate = repository.resolve("gradle/release/privacy-required-reason-review.json"),
            )
            val policies = linkedMapOf(
                "approvals" to repository.resolve("gradle/release/publication-approvals.json"),
                "privacyManifest" to repository.resolve(
                    "codex-agent-runtime-ios/apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy",
                ),
                "privacyDataFlowReview" to repository.resolve("gradle/release/privacy-data-flow-review.json"),
                "privacyRequiredReasonReviews" to checkNotNull(exactReview),
                "iosResourcePolicy" to repository.resolve("gradle/release/ios-resource-policy.json"),
                "packageSwift" to repository.resolve("Package.swift"),
                "desktopDistributionManifest" to repository.resolve(
                    "codex-agent-runtime-desktop/codex-app-server-distributions.json",
                ),
                "desktopBundledLicense" to repository.resolve(
                    "legal/openai-codex/openai-codex-LICENSE.txt",
                ),
                "desktopBundledNotice" to repository.resolve(
                    "legal/openai-codex/openai-codex-NOTICE.txt",
                ),
            )
            val result = verifyCandidatePayload(
                manifestFile, payload, options.required("version"), options.required("tag"),
                options.required("commit"), policies,
            )
            verifyPublicationReadiness(
                policies.getValue("approvals"), policies.getValue("privacyManifest"),
                policies.getValue("privacyDataFlowReview"), policies.getValue("desktopDistributionManifest"),
                policies.getValue("desktopBundledLicense"), policies.getValue("desktopBundledNotice"),
            )
            options.file("verification-output").atomicWriteJson(buildJsonObject {
                result.forEach { (name, value) -> put(name, value) }
                put("releaseTooling", JsonPrimitive(RELEASE_TOOLING_FILE_NAME))
            })
            options.file("github-output").apply {
                parentFile?.mkdirs()
                writeText(candidateGithubOutputs(result))
            }
        }
        "central-prepare", "central-await", "central-release" -> {
            val common = arrayOf("bundle", "candidate", "record")
            if (command == "central-prepare") options.requireOnly(*(common + "allow-new-upload"))
            else options.requireOnly(*common)
            val bundle = options.file("bundle")
            val candidate = options.file("candidate")
            val record = options.file("record")
            val api = System.getenv("CENTRAL_PORTAL_API")?.takeIf(String::isNotBlank)
                ?: DEFAULT_CENTRAL_PORTAL_API
            val username = System.getenv("MAVEN_CENTRAL_USERNAME").orEmpty()
            val password = System.getenv("MAVEN_CENTRAL_PASSWORD").orEmpty()
            when (command) {
                "central-prepare" -> prepareCentralDeployment(
                    bundle, candidate, record, api, username, password,
                    options.required("allow-new-upload").toBooleanStrict(),
                )
                "central-await" -> awaitCentralValidation(bundle, candidate, record, api, username, password)
                else -> releaseCentralDeployment(bundle, candidate, record, api, username, password)
            }
        }
        else -> error("Unknown release-tooling command: $command")
    }
}

private fun requireExactReleaseToolingDirectory(directory: File, expected: Set<String>, label: String) {
    check(directory.isDirectory && !Files.isSymbolicLink(directory.toPath())) {
        "$label directory is missing or symbolic: $directory"
    }
    val actual = directory.listFiles().orEmpty().map(File::getName).toSet()
    check(actual == expected && directory.listFiles().orEmpty().size == expected.size) {
        "$label inventory mismatch: expected=${expected.sorted()} actual=${actual.sorted()}"
    }
}
