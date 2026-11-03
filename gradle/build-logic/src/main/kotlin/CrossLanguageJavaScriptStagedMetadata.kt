import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.file.StandardOpenOption.CREATE_NEW
import java.nio.file.StandardOpenOption.WRITE
import kotlinx.serialization.json.JsonElement

/** Full content replay over captured original stages, not source admission.
 * The authenticated caller supplies the exact original consumer directory and
 * versions, and separately binds these stages to original phase receipts and
 * authenticated K/R/package evidence. No command can declare that authority.
 */
internal fun writeImportedJavaScriptMetadataContent(
    contractStage: File,
    packageStage: File,
    validationStage: File,
    runtimeValidationStage: File,
    originalConsumerDirectory: File,
    contractVersion: String,
    sdkVersion: String,
    runtimeVersion: String,
    contentOutput: File,
) {
    val originals = linkedMapOf("contract" to contractStage, "package" to packageStage,
        "validation" to validationStage, "runtime" to runtimeValidationStage)
    fun inventory(root: File): Map<String, String> {
        check(root.isAbsolute && root.toPath() == root.toPath().normalize()) {
            "JavaScript metadata stage must have an absolute normalized path"
        }
        generateSequence(root.toPath()) { it.parent }.forEach {
            check(!Files.isSymbolicLink(it)) { "JavaScript metadata stage has symbolic ancestry" }
        }
        return verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }
    }
    val before = originals.mapValues { inventory(it.value) }
    val output = contentOutput.toPath()
    fun outputParent(): java.nio.file.Path {
        check(output.isAbsolute && output == output.normalize() &&
            !Files.exists(output, NOFOLLOW_LINKS) && Files.isDirectory(output.parent, NOFOLLOW_LINKS)) {
            "JavaScript metadata output must be a fresh absolute file with an existing parent"
        }
        generateSequence(output) { it.parent }.forEach {
            check(!Files.isSymbolicLink(it)) { "JavaScript metadata output has symbolic ancestry" }
        }
        val parent = output.parent.toRealPath()
        val resolved = parent.resolve(output.fileName)
        originals.values.forEach { source ->
            val input = source.toPath().toRealPath()
            check(!resolved.startsWith(input) && !input.startsWith(resolved)) {
                "JavaScript metadata output overlaps its original stages"
            }
        }
        return parent
    }
    val parent = outputParent()
    check(originalConsumerDirectory.isAbsolute &&
        originalConsumerDirectory.path == originalConsumerDirectory.toPath().normalize().toString()) {
        "JavaScript metadata requires its authenticated original consumer directory"
    }
    val work = Files.createTempDirectory("javascript-metadata-stages-").toRealPath().toFile()
    val content: ByteArray
    try {
        originals.values.forEach { source ->
            val input = source.toPath().toRealPath()
            check(!work.toPath().startsWith(input) && !input.startsWith(work.toPath())) {
                "JavaScript metadata capture overlaps its original stages"
            }
        }
        originals.forEach { (name, source) ->
            val captured = work.resolve(name)
            runProductPythonModule("receipt", listOf("snapshot-tree", "--source", source.absolutePath,
                "--destination", captured.absolutePath))
            check(inventory(captured) == before.getValue(name)) {
                "JavaScript metadata original stage changed during capture"
            }
        }
        fun verify(name: String, product: String, component: String, phase: String, target: String, version: String) {
            runProductPythonModule("receipt", listOf("verify-output-manifest", "--root", work.resolve(name).absolutePath,
                "--product", product, "--component", component, "--phase", phase, "--target", target,
                "--product-version", version))
        }
        verify("contract", "contract", "contract", "binary", "common", contractVersion)
        verify("package", "sdk", "javascript", "package", "node", sdkVersion)
        verify("validation", "sdk", "javascript", "validation", "node", sdkVersion)
        verify("runtime", "runtime", "node-js", "validation", "node-js-binding", runtimeVersion)
        val contract = work.resolve("contract/outputs/evidence")
        val validation = work.resolve("validation/outputs")
        val runtime = work.resolve("runtime/outputs")
        val archive = work.resolve("package/outputs/package/codex-agent-$sdkVersion.tgz")
        val installed = work.resolve("installed-package")
        restoreJavaScriptMetadataPackage(archive, installed)
        val capturedBefore = inventory(work)
        val result = replayJavaScriptMetadata(
            CrossLanguageJavaScriptBindingFiles(
                apiReport = contract.resolve("canonical-api.json"),
                canonicalCoverageReceipt = contract.resolve("canonical-coverage.json"),
                packedPublicApiReport = validation.resolve("compiler-evidence/public-api.json"),
                npmTarball = archive,
                installedPackageDirectory = installed,
                consumerSourceDirectory = validation.resolve("test-program"),
                compiledJsNodeTestProgramDirectory = runtime.resolve("test-program"),
                packedJUnitReport = validation.resolve("test-report/packed-tests.xml"),
                jsNodeJUnitReport = runtime.resolve("test-report/TEST-jsNodeTest.CodexNodeApiTest.xml"),
            ),
            validation.resolve("execution"), originalConsumerDirectory,
            validation.resolve("binding-evidence/javascript-typescript-parity.json"),
        )
        content = (releaseJson.encodeToString(JsonElement.serializer(), result.toJson()) + "\n")
            .toByteArray(Charsets.UTF_8)
        check(capturedBefore == inventory(work) && originals.keys.all { name ->
            inventory(work.resolve(name)) == before.getValue(name)
        }) { "JavaScript metadata private inputs changed during replay" }
    } finally {
        // Only this invocation's fresh private capture is removed.
        Files.walk(work.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
    check(before == originals.mapValues { inventory(it.value) }) {
        "JavaScript metadata original stages changed during replay"
    }
    check(outputParent() == parent) { "JavaScript metadata output parent changed during replay" }
    val stream = Files.newOutputStream(output, CREATE_NEW, WRITE)
    try {
        stream.use { it.write(content) }
    } catch (failure: Exception) {
        Files.deleteIfExists(output) // Only the file created by this invocation.
        throw failure
    }
}
