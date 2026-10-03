import java.io.ByteArrayOutputStream
import java.nio.file.Files

private object PackagedProductPythonMarker

internal fun runPackagedProductPython(
    module: String,
    selected: List<String>,
    arguments: List<String>,
    script: String? = null,
): String {
    val root = Files.createTempDirectory("codex-agent-product-python-").toRealPath().toFile()
    try {
        val resources = listOf("ci/products/__init__.py", "ci/products/inventory.py",
            "ci/products/zip_central_directory.py") + selected
        resources.distinct().forEach { relative ->
            val resource = "python/$relative"
            val output = root.resolve(relative)
            output.parentFile.mkdirs()
            val input = PackagedProductPythonMarker::class.java.classLoader.getResourceAsStream(resource)
                ?: error("Packaged product Python resource is missing: $resource")
            input.use { source -> output.outputStream().use(source::copyTo) }
        }
        // A regular private package cannot fall through to another namespace portion.
        root.resolve("ci/__init__.py").writeText("")
        val captured = verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }
        val entry = if (script == null)
            "runpy.run_module('ci.products.$module', run_name='__main__', alter_sys=True)" else
            "runpy.run_path(sys.argv.pop(1), run_name='__main__')"
        val bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); $entry"
        val scriptPath = if (script == null) emptyList() else listOf(root.resolve(script).absolutePath)
        val output = ByteArrayOutputStream()
        // -I/-S exclude environment, cwd and site hooks; fresh extraction plus -B excludes stale bytecode.
        val process = ProcessBuilder(listOf("python3", "-I", "-S", "-B", "-c", bootstrap, root.absolutePath) + scriptPath + arguments)
            .directory(root)
            .redirectInput(ProcessBuilder.Redirect.PIPE)
            .redirectErrorStream(true)
            .apply {
                environment()["LC_ALL"] = "C"
                environment()["LANG"] = "C"
            }
            .start()
        process.inputStream.use { it.copyTo(output) }
        val exit = process.waitFor()
        val stdout = output.toString(Charsets.UTF_8.name())
        check(captured == verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }) {
            "Packaged product Python resources changed during execution"
        }
        check(exit == 0) { "ci.products.$module failed ($exit): ${stdout.trim()}" }
        return stdout
    } finally {
        // This is only the fresh private extraction owned by this invocation.
        Files.walk(root.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
