import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import kotlinx.serialization.json.jsonObject

/** Joins exact installed-package identity to full capability proof; no phase/host trust is minted. */
internal fun verifyCrossLanguageNativeWrapperValidationEvidence(
    language: CrossLanguageBinding, classifier: String, capabilityInputs: File,
    installedEvidence: File, capabilityEvidence: File, claims: File,
): CrossLanguageNativeWrapperCapabilityEvidence {
    val host = requireExactNativeWrapperInstalledConsumerEvidence(installedEvidence, language.id, classifier)
    val receipt = capabilityInputs.resolve("receipts/sdk-package.json").readReleaseObject()
    check(receipt.releaseString("product") == "sdk" && receipt.releaseString("component") == language.id &&
        receipt.releaseString("phase") == "package" && receipt.releaseString("target") == "desktop") {
        "Installed capability input receipt is not the original language package"
    }
    val packagePath = "outputs/${language.id}/" + host[1].removePrefix("${language.id}-package/")
    val packages = receipt.releaseArray("outputs").map { it.jsonObject }
        .filter { it.releaseString("relativePath") == packagePath }
    check(packages.size == 1 && packages.single().releaseString("kind") == "package" &&
        packages.single().releaseString("sha256") == "sha256:${host[2]}") {
        "Installed host proof differs from the authenticated SDK package artifact"
    }
    val library = crossLanguageCAbiTargetSpecs.values.singleOrNull { it.classifier == "c-abi-$classifier" }
        ?.libraryPath ?: error("Unsupported native capability target: $classifier")
    val native = verifiedRegularFiles(capabilityInputs.resolve("sdks/$classifier"))[library]
        ?: error("Authenticated native capability library is missing")
    check(native.releaseDigest() == host[3]) {
        "Installed host proof differs from the authenticated target library"
    }
    check(verifiedRegularFiles(capabilityEvidence).isNotEmpty()) { "Capability evidence is empty" }
    return verifyCrossLanguageNativeWrapperCapabilityEvidence(
        language, capabilityInputs.resolve("contract/canonical-api.json"),
        capabilityInputs.resolve("contract/canonical-coverage.json"),
        capabilityInputs.resolve("bootstrap/bootstrap-evidence.json"), claims,
        capabilityEvidence.resolve("compiler-evidence.tsv"), capabilityEvidence.resolve("test-program"),
        capabilityEvidence.resolve("executed-tests.tsv"),
    )
}

/** Local content/semantic verification only; trusted tooling is supplied by the invoking build.
 * Original hosted provenance and protected release admission remain separate mandatory gates.
 * There is deliberately no caller-selected matcher executable, acceptance token or output receipt.
 */
internal fun verifyImportedNativeWrapperValidation(
    repository: File, language: CrossLanguageBinding, classifier: String,
    packageStage: File, packageReceipt: File, compatibilityRequest: File,
    runtimeStages: File, stagedSdks: File, validationStage: File, validationReceipt: File,
) {
    check(language in nativeWrapperBindings && crossLanguageCAbiTargetSpecs.values.any {
        it.classifier == "c-abi-$classifier"
    }) { "Unsupported imported native validation language/host" }
    val sources = listOf(packageStage, packageReceipt, compatibilityRequest, runtimeStages, stagedSdks,
        validationStage, validationReceipt, repository.resolve("ci")) +
        if (language.id == "cpp") listOf(repository.resolve(
            "codex-agent-bindings/cpp/tools/verify_imported_package.py")) else emptyList()
    fun inventory(): Map<String, String> = buildMap {
        sources.forEach { source ->
            generateSequence(source.toPath().toAbsolutePath()) { it.parent }.forEach { path ->
                check(!Files.isSymbolicLink(path)) { "Imported validation input has a symbolic link: $path" }
            }
            if (Files.isDirectory(source.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                verifiedRegularFiles(source).values.forEach { file -> put(file.absolutePath, file.releaseDigest()) }
            } else {
                check(Files.isRegularFile(source.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                    "Missing imported validation input: $source"
                }
                put(source.absolutePath, source.releaseDigest())
            }
        }
    }
    val before = inventory()
    val work = Files.createTempDirectory("native-validation-import-").toFile()
    try {
        val handoff = work.resolve("inputs")
        fun runPython(vararg arguments: String) {
            val process = ProcessBuilder(listOf("python3", "-E", "-s", "-B") + arguments)
                .directory(repository).inheritIO().start()
            check(process.waitFor() == 0) { "Imported native validation input/evidence verification failed" }
        }
        runPython("-m", "ci.products.sdk_package", "verify-native",
            "--repository", repository.absolutePath, "--component", language.id,
            "--stage", packageStage.absolutePath, "--receipt", packageReceipt.absolutePath,
            "--compatibility-request", compatibilityRequest.absolutePath,
            "--runtime-stages", runtimeStages.absolutePath, "--staged-sdks", stagedSdks.absolutePath,
            "--validation-stage", validationStage.absolutePath,
            "--validation-receipt", validationReceipt.absolutePath, "--validation-target", classifier,
            "--validation-inputs-output", handoff.absolutePath)
        check(handoff.resolve("receipts/sdk-validation.json").releaseDigest() ==
            before.getValue(validationReceipt.absolutePath)) { "Imported validation receipt changed" }
        val captured = verifiedRegularFiles(handoff).mapValues { it.value.releaseDigest() }
        val raw = handoff.resolve("validation/outputs")
        if (language.id == "cpp") runPython(
            repository.resolve("codex-agent-bindings/cpp/tools/verify_imported_package.py").absolutePath,
            "verify-evidence", "--evidence", raw.resolve("package-negatives").absolutePath,
            "--expected-test-program", handoff.resolve("validation-source/test_installed_package_tamper.py").absolutePath)
        verifyCrossLanguageNativeWrapperValidationEvidence(language, classifier, handoff,
            raw.resolve("installed"), raw.resolve("capability"),
            handoff.resolve("validation-source/capability-claims.tsv"))
        check(captured == verifiedRegularFiles(handoff).mapValues { it.value.releaseDigest() } && before == inventory()) {
            "Imported validation inputs changed during full semantic verification"
        }
    } finally {
        // The only removed tree is this invocation's newly allocated private work.
        Files.walk(work.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
