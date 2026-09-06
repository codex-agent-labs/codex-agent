import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardOpenOption
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
    contentOutput: File? = null,
    enclosingContentOutput: File? = null,
) {
    check(language in nativeWrapperBindings && crossLanguageCAbiTargetSpecs.values.any {
        it.classifier == "c-abi-$classifier"
    }) { "Unsupported imported native validation language/host" }
    val sources = listOf(packageStage, packageReceipt, compatibilityRequest, runtimeStages, stagedSdks,
        validationStage, validationReceipt, repository.resolve("ci")) +
        if (language.id == "cpp") listOf(repository.resolve(
            "codex-agent-bindings/cpp/tools/verify_imported_package.py")) else emptyList()
    listOfNotNull(contentOutput, enclosingContentOutput).forEach { output ->
        requireNativeValidationContentDestination(output, sources)
    }
    val contentParent = contentOutput?.toPath()?.toAbsolutePath()?.normalize()?.parent?.toRealPath()
    val before = nativeValidationInputInventory(sources)
    val work = Files.createTempDirectory("native-validation-import-").toRealPath().toFile()
    try {
        val handoff = work.resolve("inputs")
        fun runPython(vararg arguments: String, stdout: File? = null) {
            val process = ProcessBuilder(listOf("python3", "-E", "-s", "-B") + arguments)
                .directory(repository).redirectError(ProcessBuilder.Redirect.INHERIT)
                .apply { if (stdout == null) redirectOutput(ProcessBuilder.Redirect.INHERIT) else redirectOutput(stdout) }
                .start()
            check(process.waitFor() == 0) { "Imported native validation input/evidence verification failed" }
        }
        val guardedOutput = enclosingContentOutput ?: contentOutput
        runPython("-m", "ci.products.sdk_package", "verify-native",
            "--repository", repository.absolutePath, "--component", language.id,
            "--stage", packageStage.absolutePath, "--receipt", packageReceipt.absolutePath,
            "--compatibility-request", compatibilityRequest.absolutePath,
            "--runtime-stages", runtimeStages.absolutePath, "--staged-sdks", stagedSdks.absolutePath,
            "--validation-stage", validationStage.absolutePath,
            "--validation-receipt", validationReceipt.absolutePath, "--validation-target", classifier,
            "--validation-inputs-output", handoff.absolutePath,
            *(if (guardedOutput != null) arrayOf("--validation-content-output", guardedOutput.absolutePath) else emptyArray()))
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
        val content = work.resolve("content.json")
        if (contentOutput != null) runPython("-m", "ci.products.sdk_package", "native-content",
            "--inputs", handoff.absolutePath, "--component", language.id, "--target", classifier, stdout = content)
        check(captured == verifiedRegularFiles(handoff).mapValues { it.value.releaseDigest() } &&
            before == nativeValidationInputInventory(sources)) {
            "Imported validation inputs changed during full semantic verification"
        }
        if (contentOutput != null) publishNativeValidationContent(content, contentOutput, contentParent)
    } finally {
        // The only removed tree is this invocation's newly allocated private work.
        Files.walk(work.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}

private fun requireNativeValidationContentDestination(output: File, sources: List<File>) {
    val destination = output.toPath()
    check(destination.isAbsolute && destination == destination.normalize()) {
        "Native content destination must be an absolute normalized path"
    }
    check(!Files.exists(destination, LinkOption.NOFOLLOW_LINKS) && Files.isDirectory(destination.parent)) {
        "Native content destination must be a new file with an existing parent"
    }
    generateSequence(destination) { it.parent }.forEach { path ->
        check(!Files.isSymbolicLink(path)) { "Unsafe native content destination: $path" }
    }
    val resolved = destination.parent.toRealPath().resolve(destination.fileName)
    sources.forEach { source ->
        val original = source.toPath().toRealPath()
        check(!resolved.startsWith(original) && !original.startsWith(resolved)) {
            "Native content destination overlaps an original input"
        }
    }
}

private fun nativeValidationInputInventory(sources: List<File>): Map<String, String> = buildMap {
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

private fun publishNativeValidationContent(content: File, contentOutput: File, contentParent: Path?) {
    check(content.isFile && !Files.isSymbolicLink(content.toPath()) && content.length() in 1..(16L * 1024 * 1024)) {
        "Missing or oversized native validation content"
    }
    // Only canonical Python-produced bytes are forwarded, after every input recheck.
    val destination = contentOutput.toPath().toAbsolutePath().normalize()
    generateSequence(destination) { it.parent }.forEach { path ->
        check(!Files.isSymbolicLink(path)) { "Native content destination changed to a symbolic path" }
    }
    check(destination.parent.toRealPath() == contentParent) { "Native content destination parent changed" }
    val stream = Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
    try {
        stream.use { it.write(content.readBytes()) }
    } catch (failure: Exception) {
        Files.deleteIfExists(destination) // Only the new file just created by this invocation.
        throw failure
    }
}

/** Five independent full semantic gates; raw originals and hosted trust stay external. */
internal fun writeImportedNativeWrapperMetadataContent(
    repository: File, language: CrossLanguageBinding, packageStage: File, packageReceipt: File,
    compatibilityRequest: File, runtimeStages: File, stagedSdks: File,
    validationStages: File, validationReceipts: File, contentOutput: File,
) {
    check(language in nativeWrapperBindings) { "Unsupported native metadata language" }
    val targets = crossLanguageCAbiTargetSpecs.values.map { it.classifier.removePrefix("c-abi-") }.sorted()
    val sources = listOf(packageStage, packageReceipt, compatibilityRequest, runtimeStages, stagedSdks,
        validationStages, validationReceipts, repository.resolve("ci")) + if (language.id == "cpp")
        listOf(repository.resolve("codex-agent-bindings/cpp/tools/verify_imported_package.py")) else emptyList()
    requireNativeValidationContentDestination(contentOutput, sources)
    val parent = contentOutput.toPath().parent.toRealPath()
    val before = nativeValidationInputInventory(sources)
    check(validationStages.listFiles()?.map { it.name }?.sorted() == targets &&
        targets.all { validationStages.resolve(it).isDirectory }) { "Native metadata requires exactly five host stages" }
    check(verifiedRegularFiles(validationReceipts).keys == targets.map { "$it.json" }.toSet()) {
        "Native metadata requires exactly five original validation receipts"
    }
    val work = Files.createTempDirectory("native-metadata-import-").toRealPath().toFile()
    try {
        val contents = work.resolve("hosts").apply { mkdir() }
        targets.forEach { target ->
            verifyImportedNativeWrapperValidation(repository, language, target, packageStage, packageReceipt,
                compatibilityRequest, runtimeStages, stagedSdks, validationStages.resolve(target),
                validationReceipts.resolve("$target.json"), contents.resolve("$target.json"), contentOutput)
        }
        val result = work.resolve("metadata.json")
        val process = ProcessBuilder("python3", "-E", "-s", "-B", "-m", "ci.products.sdk_package", "native-metadata",
            "--contents", contents.absolutePath, "--package-receipt", packageReceipt.absolutePath,
            "--component", language.id).directory(repository).redirectError(ProcessBuilder.Redirect.INHERIT)
            .redirectOutput(result).start()
        check(process.waitFor() == 0) { "Native metadata content join failed" }
        check(before == nativeValidationInputInventory(sources)) { "Native metadata original inputs changed" }
        publishNativeValidationContent(result, contentOutput, parent)
    } finally {
        Files.walk(work.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
