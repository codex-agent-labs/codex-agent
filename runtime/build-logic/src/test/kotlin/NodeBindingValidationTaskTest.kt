import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.junit.Assume.assumeTrue

/** Real pinned Mocha over small JS fixtures, not Kotlin/product acceptance evidence. */
class NodeBindingValidationTaskTest {
    private val modules = File("../build/js/node_modules").canonicalFile
    private val lock = File("../gradle/kotlin-js-store/package-lock.json").canonicalFile

    private fun program(root: File, failure: String? = null): File = root.resolve("program").also { directory ->
        directory.mkdirs()
        directory.resolve(NODE_BINDING_PROGRAM).writeText(buildString {
            appendLine("describe('CodexNodeApiTest', function () {")
            nodeBindingMethods.forEachIndexed { index, name ->
                val operation = if (failure == "skip" && index == 0) "it.skip" else "it"
                val body = if (failure == "failure" && index == 0) "throw new Error('fixture failure');" else ""
                appendLine("  $operation('$name', async function () { $body });")
            }
            if (failure == "extra") appendLine("  it('unreviewedTest', function () {});")
            appendLine("});")
        })
    }

    private fun archive(staged: File, destination: File): File {
        ZipOutputStream(destination.outputStream()).use { zip ->
            staged.walkTopDown().filter(File::isFile).sortedBy { it.relativeTo(staged).path }.forEach { file ->
                zip.putNextEntry(ZipEntry(file.relativeTo(staged).invariantSeparatorsPath).apply { time = 0 })
                file.inputStream().use { it.copyTo(zip) }
                zip.closeEntry()
            }
        }
        patchDesktopRuntimeUnixModes(destination, emptySet())
        return destination
    }

    private fun inventory(root: File) = root.walkTopDown().filter(File::isFile)
        .associate { it.relativeTo(root).invariantSeparatorsPath to it.releaseDigest() }

    @Test
    fun `pinned Mocha runs imported binding tests and preserves raw plus established report identities`() {
        assumeTrue("Enable only with the existing offline Runtime Node harness",
            System.getenv("CODEX_AGENT_TEST_NODE_BINDING_HARNESS") == "1")
        check(modules.resolve("mocha/package.json").isFile && lock.isFile) {
            "Requires the already-installed offline Runtime Node harness; do not install during this test"
        }
        val root = createTempDirectory("node-binding-test").toFile()
        try {
            val source = program(root)
            val before = inventory(source)
            val staged = root.resolve("staged")
            stageNodeBindingRunner(source, modules, lock, staged)
            val second = root.resolve("second")
            stageNodeBindingRunner(source, modules, lock, second)
            assertEquals(inventory(staged), inventory(second))
            assertEquals(before, inventory(source))
            val packed = archive(staged, root.resolve("runner.zip"))
            val packedDigest = packed.releaseDigest()
            val output = root.resolve("output")
            val raw = root.resolve("raw-mocha.xml")
            executeNodeBindingValidation(packed, "node", output, raw)
            assertTrue(raw.readText().contains("classname=\"CodexNodeApiTest\""))
            assertTrue(!output.resolve("test-report/raw-mocha.xml").exists())
            val results = readCanonicalTestReport(output.resolve("test-report/TEST-jsNodeTest.CodexNodeApiTest.xml"))
            assertEquals(nodeBindingMethods.map { "jsNodeTest.CodexNodeApiTest#$it[js, node]" }.toSet(),
                results.map { it.testId }.toSet())
            assertTrue(results.all { it.status == CanonicalTestStatus.PASSED })
            assertEquals(before, inventory(output.resolve("test-program")))
            assertEquals(packedDigest, packed.releaseDigest())
            val secondOutput = root.resolve("second-output")
            executeNodeBindingValidation(packed, "node", secondOutput, root.resolve("second-raw-mocha.xml"))
            assertEquals(inventory(output), inventory(secondOutput))
            assertTrue(!output.resolve("test-report/TEST-jsNodeTest.CodexNodeApiTest.xml").readText()
                .contains(root.absolutePath))

            for (failure in listOf("failure", "skip", "extra")) {
                stageNodeBindingRunner(program(root, failure), modules, lock, staged)
                archive(staged, root.resolve("runner.zip"))
                assertFailsWith<IllegalStateException> { executeNodeBindingValidation(packed, "node", output, raw) }
                assertTrue(!output.resolve("test-report/TEST-jsNodeTest.CodexNodeApiTest.xml").exists())
            }
            Files.createSymbolicLink(source.resolve("unsafe.js").toPath(), source.resolve(NODE_BINDING_PROGRAM).toPath())
            assertFailsWith<IllegalStateException> {
                stageNodeBindingRunner(source, modules, lock, root.resolve("symbolic-staged"))
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `unsafe imported archive fails before Node execution without a local harness`() {
        val root = createTempDirectory("node-binding-unsafe").toFile()
        try {
            val zip = root.resolve("unsafe.zip")
            ZipOutputStream(zip.outputStream()).use {
                it.putNextEntry(ZipEntry("../escape.js"))
                it.write("unsafe".toByteArray())
                it.closeEntry()
            }
            patchDesktopRuntimeUnixModes(zip, emptySet())
            assertFailsWith<IllegalStateException> {
                executeNodeBindingValidation(zip, "missing-node-must-not-start", root.resolve("output"), root.resolve("raw.xml"))
            }
            assertTrue(!root.resolve("escape.js").exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `staging rejects a symlinked installed root or package namespace`() {
        val fixture = createTempDirectory("node-binding-installed-root").toFile()
        try {
            val installed = fixture.resolve("install/node_modules").also(File::mkdirs)
            val source = program(fixture)
            val packages = listOf("mocha", "kotlin-web-helpers", "source-map-support")
            packages.forEach { name ->
                installed.resolve(name).also(File::mkdirs).resolve("package.json")
                    .writeText("{\"version\":\"1.0.0\"}")
            }
            val lock = fixture.resolve("package-lock.json")
            lock.writeText("{\"packages\":{" + packages.joinToString(",") { name ->
                "\"node_modules/$name\":{\"version\":\"1.0.0\"}"
            } + "}}")
            stageNodeBindingRunner(source, installed, lock, fixture.resolve("valid-stage"))

            val alias = fixture.resolve("alias/node_modules")
            alias.parentFile.mkdirs()
            Files.createSymbolicLink(alias.toPath(), installed.toPath())
            assertFailsWith<IllegalStateException> {
                stageNodeBindingRunner(source, alias, lock, fixture.resolve("linked-root-stage"))
            }

            val external = fixture.resolve("external/helper").also(File::mkdirs)
            external.resolve("package.json").writeText("{\"version\":\"1.0.0\"}")
            installed.resolve("mocha/package.json")
                .writeText("{\"version\":\"1.0.0\",\"dependencies\":{\"@scope/helper\":\"1.0.0\"}}")
            Files.createSymbolicLink(installed.resolve("@scope").toPath(), external.parentFile.toPath())
            lock.writeText(lock.readText().dropLast(2) + ",\"node_modules/@scope/helper\":{\"version\":\"1.0.0\"}}}")
            assertFailsWith<IllegalStateException> {
                stageNodeBindingRunner(source, installed, lock, fixture.resolve("linked-namespace-stage"))
            }
        } finally {
            fixture.deleteRecursively()
        }
    }

    @Test
    fun `Gradle directory records are accepted only with canonical safe paths modes and empty bytes`() {
        for (name in listOf("program/", "node_modules/", "node_modules/@isaacs/cliui/")) {
            requireNodeBindingArchiveMember(name, true, 0, 0x41ed)
            assertFailsWith<IllegalStateException> { requireNodeBindingArchiveMember(name, true, 1, 0x41ed) }
            assertFailsWith<IllegalStateException> { requireNodeBindingArchiveMember(name, true, 0, 0xa1ff) }
            assertFailsWith<IllegalStateException> { requireNodeBindingArchiveMember(name, true, 0, 0x81a4) }
        }
        for (name in listOf("/program/", "program/../escape/", "node_modules//x/", "node_modules/./x/",
            "node_modules/\\x/", "node_modules/C:/", "program/\u0001/", "package-lock.json/", "other/")) {
            assertFailsWith<IllegalStateException>(name) { requireNodeBindingArchiveMember(name, true, 0, 0x41ed) }
        }
        requireNodeBindingArchiveMember("program/main.js", false, 1, 0x81a4)
        assertFailsWith<IllegalStateException> { requireNodeBindingArchiveMember("program/main.js", false, 1, 0x41ed) }
    }

    @Test
    fun `binding runner staging declares the producer of its stored npm lock`() {
        val source = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
        val registration = source.substringAfter("val stageNodeBindingValidationRunner =")
            .substringBefore("val packageNodeBindingValidationRunner =")
        assertTrue("rootProject.tasks.named(\"kotlinStorePackageLock\")" in registration)
        assertTrue("gradle/kotlin-js-store/package-lock.json" in registration)
    }

    @Test
    fun `production imported binding validation has canonical identity and no jsNodeTest edge`() {
        val source = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
        val registration = source.substringAfter("val nodeJsBindingValidationRoot =")
            .substringBefore("val runtimeNativeValidationManifestTasks =")
        assertTrue("product-stage/runtime/node-js/validation/node-js-binding" in registration)
        assertTrue("dependsOn(verifyNodeBindingPackage)" in registration)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimePackageVersion\")" in registration)
        assertTrue("dependsOn(\"jsNodeTest\")" !in registration)
        assertTrue("providers.provider { \"node-js-binding\" }" in registration)
        assertTrue("runnerArchive.set(packageRoot.map" in registration)
    }
}
