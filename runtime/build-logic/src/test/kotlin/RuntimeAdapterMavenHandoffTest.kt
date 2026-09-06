import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.Json
import kotlinx.serialization.KSerializer
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testfixtures.ProjectBuilder

/** Real Gradle publication/manifest tests with synthetic primaries, not compiler or hosted evidence. */
class RuntimeAdapterMavenHandoffTest {
    private val rootRepository = File("../..").canonicalFile
    private val adapters = listOf(Triple("jvm", "Jvm", "jvm"), Triple("node-js", "NodeJs", "js"), Triple("node-wasm", "NodeWasm", "wasmJs"))
    private val groupPath = "io/github/codex-agent-labs"

    private fun original(root: File, component: String): File {
        val stage = root.resolve("original/$component").apply { mkdirs() }
        val extension = if (component == "jvm") "jar" else "klib"
        listOf("main.$extension", "sources.jar", "javadoc.jar").forEach { name ->
            stage.resolve("outputs/publication/$name").apply { parentFile.mkdirs(); writeText("synthetic original $component $name\n") }
        }
        val process = ProcessBuilder(
            "python3", "-B", "-m", "ci.products", "receipt", "write-output-manifest",
            "--root", stage.absolutePath, "--product", "runtime", "--component", component,
            "--phase", "package", "--target", component, "--product-version", "0.2.0",
            "--output-root", "publication=outputs/publication",
        ).directory(rootRepository).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().readText()
        assertEquals(0, process.waitFor(), output)
        return stage
    }

    private fun fixture(root: File) {
        adapters.forEach { original(root, it.first) }
        val classpath = listOf(PrepareRuntimeAdapterMavenTask::class.java, Json::class.java, KSerializer::class.java)
            .map { File(it.protectionDomain.codeSource.location.toURI()).invariantSeparatorsPath }.distinct()
        root.resolve("settings.gradle.kts").writeText("rootProject.name = \"imported-runtime-maven\"\n")
        root.resolve("compiler-owned").mkdir()
        listOf("main.jar", "main.klib", "sources.jar", "javadoc.jar").forEach {
            root.resolve("compiler-owned/$it").writeText("must never be published: $it\n")
        }
        root.resolve("build.gradle.kts").writeText(
            """
            import java.io.File
            import org.gradle.api.attributes.Category
            import org.gradle.api.attributes.DocsType
            import org.gradle.api.attributes.Usage
            import org.gradle.api.publish.maven.MavenPublication
            import org.gradle.api.tasks.Sync
            buildscript { dependencies { classpath(files(${classpath.joinToString(",") { "\"$it\"" }})) } }
            plugins { `maven-publish` }
            group = "io.github.codex-agent-labs"
            version = "0.2.9"
            tasks.register("compileForbidden") { doLast { error("Compiler edge must never run") } }
            tasks.register("sourceArchiveForbidden") { doLast { error("Source archive must be imported") } }
            // Vanniktech's callback also affects publications created by the handoff.
            publishing.publications.withType(MavenPublication::class.java).configureEach {
                val currentPublication = this
                // Actual Vanniktech coordinates register an afterEvaluate callback
                // at publication creation, so late publication creation must fail.
                afterEvaluate {
                    if (currentPublication.name.startsWith("imported")) currentPublication.artifactId = "must-rebind-after-plugin-callback"
                }
                artifact(layout.projectDirectory.file("compiler-owned/javadoc.jar")) { classifier = "javadoc"; builtBy("sourceArchiveForbidden") }
            }
            listOf(Triple("jvm", "Jvm", "jvm"), Triple("node-js", "NodeJs", "js"), Triple("node-wasm", "NodeWasm", "wasmJs")).forEach { (component, title, target) ->
                val extension = if (component == "jvm") "jar" else "klib"
                val originalComponent = objects.newInstance(RuntimeAdapterComponentFactory::class.java).components.adhoc("original" + title)
                components.add(originalComponent)
                listOf("api", "runtime", "sources").forEach { kind ->
                    val configuration = configurations.create(target + kind) {
                        isCanBeConsumed = true
                        isCanBeResolved = false
                        attributes.attribute(Usage.USAGE_ATTRIBUTE, objects.named(if (kind == "api") "java-api" else "java-runtime"))
                        attributes.attribute(Category.CATEGORY_ATTRIBUTE, objects.named(if (kind == "sources") "documentation" else "library"))
                        if (kind == "sources") attributes.attribute(DocsType.DOCS_TYPE_ATTRIBUTE, objects.named("sources"))
                        if (kind != "sources") dependencies.add(project.dependencies.create("io.github.codex-agent-labs:codex-agent-core:0.2.0"))
                        outgoing.artifact(layout.projectDirectory.file("compiler-owned/" + if (kind == "sources") "sources.jar" else "main." + extension)) {
                            if (kind == "sources") classifier = "sources"
                            builtBy(if (kind == "sources") "sourceArchiveForbidden" else "compileForbidden")
                        }
                    }
                    originalComponent.addVariantsFromConfiguration(configuration) {
                        mapToMavenScope(if (kind == "api") "compile" else "runtime")
                        if (kind == "sources") mapToOptional()
                    }
                }
                val originalPublication = publishing.publications.create(target, MavenPublication::class.java) {
                    artifactId = "codex-agent-runtime-desktop-" + when (component) { "node-js" -> "js"; "node-wasm" -> "wasm-js"; else -> "jvm" }
                    pom { name.set("Original target POM")
                        licenses { license { name.set("GNU General Public License v3.0 or later"); url.set("https://www.gnu.org/licenses/gpl-3.0.txt") } }
                    }
                }
                // Reproduce the observed KGP ordering: javadoc is already attached,
                // while main/sources arrive in a later nested afterEvaluate callback.
                afterEvaluate { afterEvaluate { originalPublication.from(originalComponent) } }
                tasks.register<Sync>("stage" + title + "RuntimeBinaryOutputs") { into(layout.buildDirectory.dir("unused-binary/" + component)) }
                gradle.projectsEvaluated {
                    retainRuntimeAdapterPublication(component, title, target)
                }
                registerRuntimeAdapterMavenHandoff(
                    component, title, target, providers.provider { layout.projectDirectory.dir("original/" + component) },
                    providers.provider { "0.2.0" }, files(), File("${rootRepository.invariantSeparatorsPath}"),
                )
            }
            """.trimIndent(),
        )
    }

    private fun runner(root: File, vararg tasks: String) = GradleRunner.create().withProjectDir(root)
        .withArguments(tasks.toList() + listOf("--offline", "--configuration-cache", "--configuration-cache-problems=fail", "--stacktrace"))

    @Test fun `all three metadata publications forward imported bytes with original POM and no compiler edges`() {
        val root = createTempDirectory("runtime-adapter-maven-").toFile().canonicalFile
        try {
            fixture(root)
            val originals = root.resolve("original").walkTopDown().filter(File::isFile).associate { it to it.readBytes() }
            val result = runner(root, *adapters.map { "finalize${it.second}RuntimeMavenHandoff" }.toTypedArray()).build()
            assertTrue(result.tasks.none { "Forbidden" in it.path || "BinaryOutputs" in it.path || "compile" in it.path.lowercase() })
            adapters.forEach { (component, title, target) ->
                val artifact = "codex-agent-runtime-desktop-" + if (target == "wasmJs") "wasm-js" else target
                val repository = root.resolve("build/runtime-adapter-maven/$component/repository/$component")
                val coordinate = repository.resolve("$groupPath/$artifact/0.2.9")
                val prefix = "$artifact-0.2.9"
                val extension = if (component == "jvm") "jar" else "klib"
                mapOf(".$extension" to "main.$extension", "-sources.jar" to "sources.jar", "-javadoc.jar" to "javadoc.jar").forEach { (suffix, name) ->
                    assertContentEquals(root.resolve("original/$component/outputs/publication/$name").readBytes(), coordinate.resolve(prefix + suffix).readBytes())
                }
                assertEquals(25, repository.walkTopDown().count(File::isFile))
                val pom = coordinate.resolve("$prefix.pom").readText()
                assertTrue("Original target POM" in pom && "GNU General Public License" in pom && "codex-agent-core" in pom)
                assertTrue(result.tasks.any { it.path == ":generatePomFileFor${target.replaceFirstChar(Char::uppercaseChar)}Publication" })
                assertFalse(result.tasks.any { it.path == ":generatePomFileForImported${title}RuntimePublication" })
                val module = coordinate.resolve("$prefix.module").readText()
                assertTrue("codex-agent-core" in module)
                assertFalse("buildId" in module || "compiler-owned" in module)
                coordinate.listFiles()!!.filter { it.name.endsWith(".sha256") }.forEach { sidecar ->
                    assertEquals(sidecar.resolveSibling(sidecar.name.removeSuffix(".sha256")).releaseDigest() + "\n", sidecar.readText())
                }
            }
            fun publishedInventory() = adapters.flatMap { (component, _, _) ->
                val repository = root.resolve("build/runtime-adapter-maven/$component/repository")
                repository.walkTopDown().filter(File::isFile).map { file ->
                    "$component/${file.relativeTo(repository).invariantSeparatorsPath}" to (file.length() to file.releaseDigest())
                }.toList()
            }.toMap()
            val publishedBefore = publishedInventory()
            val repeat = runner(root, *adapters.map { "finalize${it.second}RuntimeMavenHandoff" }.toTypedArray()).build()
            assertTrue("Reusing configuration cache" in repeat.output)
            assertTrue(repeat.tasks.none { "Forbidden" in it.path || "BinaryOutputs" in it.path || "compile" in it.path.lowercase() })
            assertEquals(publishedBefore, publishedInventory())
            originals.forEach { (file, bytes) -> assertContentEquals(bytes, file.readBytes()) }
        } finally { root.deleteRecursively() }
    }

    @Test fun `missing original primary fails before Maven publication without source fallback`() {
        val root = createTempDirectory("runtime-adapter-maven-missing-").toFile().canonicalFile
        try {
            fixture(root)
            root.resolve("original/node-js/outputs/publication/main.klib").delete()
            val result = runner(root, "finalizeNodeJsRuntimeMavenHandoff").buildAndFail()
            assertTrue(result.tasks.none { "PublicationTo" in it.path || "Forbidden" in it.path })
            assertFalse(root.resolve("build/runtime-adapter-maven/node-js/repository").exists())
        } finally { root.deleteRecursively() }
    }

    @Test fun `primary mapping is exact and binary and package inventories include original publications`() {
        assertEquals("main.jar", runtimeAdapterPrimaryName("jvm", null, "jar"))
        assertEquals("main.klib", runtimeAdapterPrimaryName("node-js", "", "klib"))
        assertEquals("main.klib", runtimeAdapterPrimaryName("node-wasm", null, "klib"))
        for (component in adapters.map { it.first }) {
            assertEquals("sources.jar", runtimeAdapterPrimaryName(component, "sources", "jar"))
            assertEquals("javadoc.jar", runtimeAdapterPrimaryName(component, "javadoc", "jar"))
            assertFailsWith<IllegalStateException> { runtimeAdapterPrimaryName(component, "signature", "asc") }
        }
        val module = rootRepository.resolve("codex-agent-runtime-desktop/build.gradle.kts").readText()
        val plugin = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        assertEquals(4, Regex("\"publication\" to \"outputs/publication\"").findAll(module).count())
        assertEquals(2, Regex("\"publication\" to \"outputs/publication\"").findAll(plugin).count())
        assertTrue("retainRuntimeAdapterPublication(component, title, publicationName)" in module)
        assertTrue("gradle.projectsEvaluated {" in module.substringBefore("retainRuntimeAdapterPublication(component, title, publicationName)").takeLast(500))
        assertFalse("importedRuntimeMavenRepository" in module)
        assertTrue("dependsOn(\"finalize\u0024{title}RuntimeMavenHandoff\")" in module)
        assertTrue("from(jvmRuntimeBinaryStageRoot.map { it.dir(\"outputs/publication\") })" in plugin)
        assertTrue("from(nodeJsPackageInput.map { it.dir(\"outputs/publication\") })" in module)
        assertTrue("from(nodeWasmPackageInput.map { it.dir(\"outputs/publication\") })" in module)
    }

    @Test fun `fresh framing rejects crosspaired primary checksum signature and immutable destination`() {
        val root = createTempDirectory("runtime-maven-framing-").toFile().canonicalFile
        try {
            val original = root.resolve("original-package/outputs/publication").apply { mkdirs() }
            val fresh = root.resolve("fresh").apply { mkdir() }
            val destination = root.resolve("repository")
            val artifact = "codex-agent-runtime-desktop-jvm"
            val prefix = "$groupPath/$artifact/0.2.9/$artifact-0.2.9"
            mapOf(".jar" to "main.jar", "-sources.jar" to "sources.jar", "-javadoc.jar" to "javadoc.jar").forEach { (suffix, name) ->
                original.resolve(name).writeText("original $name\n")
                fresh.resolve(prefix + suffix).apply { parentFile.mkdirs(); writeBytes(original.resolve(name).readBytes()) }
            }
            // This fixture exercises framing only. The other test uses real Gradle POM/GMM generators.
            fresh.resolve("$prefix.pom").writeText("synthetic POM framing input\n")
            fresh.resolve("$prefix.module").writeText("synthetic GMM framing input\n")
            fresh.resolve("$groupPath/$artifact/maven-metadata.xml").writeText("fresh discovery framing input\n")
            val checksums = mapOf(".md5" to "MD5", ".sha1" to "SHA-1", ".sha256" to "SHA-256", ".sha512" to "SHA-512")
            fun refresh(file: File) = checksums.forEach { (suffix, algorithm) -> file.resolveSibling(file.name + suffix).writeText(file.releaseDigest(algorithm)) }
            fresh.walkTopDown().filter(File::isFile).toList().forEach(::refresh)
            fun verify() = finalizeRuntimeAdapterMaven("jvm", "io.github.codex-agent-labs", artifact, "0.2.9", original, fresh, destination)
            val originals = original.listFiles()!!.associate { it to it.readBytes() }
            val primary = fresh.resolve("$prefix.jar")
            val primaryBytes = primary.readBytes()
            primary.writeText("different actual primary\n"); refresh(primary)
            assertFailsWith<IllegalStateException> { verify() }
            assertFalse(destination.exists())
            primary.writeBytes(primaryBytes); refresh(primary)
            val checksum = fresh.resolve("$prefix.jar.sha256")
            val checksumBytes = checksum.readBytes()
            checksum.writeText("0".repeat(64))
            assertFailsWith<IllegalStateException> { verify() }
            assertFalse(destination.exists())
            checksum.writeBytes(checksumBytes)
            val signature = fresh.resolve("$prefix.jar.asc").apply { writeText("signature must remain external\n") }
            assertFailsWith<IllegalStateException> { verify() }
            signature.delete()
            destination.mkdir()
            val sentinel = destination.resolve("sentinel").apply { writeText("preserve\n") }
            assertFailsWith<IllegalStateException> { verify() }
            assertEquals("preserve\n", sentinel.readText())
            sentinel.delete()
            verify()
            assertEquals(25, destination.walkTopDown().count(File::isFile))
            assertFalse(destination.walkTopDown().any { it.name == "maven-metadata.xml" })
            originals.forEach { (file, bytes) -> assertContentEquals(bytes, file.readBytes()) }
        } finally { root.deleteRecursively() }
    }

    private fun prepareTask(root: File, original: File): PrepareRuntimeAdapterMavenTask {
        val project = ProjectBuilder.builder().withProjectDir(root).build()
        return project.tasks.create("prepareImportedMaven", PrepareRuntimeAdapterMavenTask::class.java).apply {
            component.set("jvm")
            originalPackage.set(original)
            ownedBuild.set(root.resolve("build"))
            workspace.set(root.resolve("build/runtime-adapter-maven/jvm"))
        }
    }

    @Test fun `workspace cleanup rejects equal ancestor and descendant original inputs before mutation`() {
        for (shape in listOf("equal", "ancestor", "descendant")) {
            val root = createTempDirectory("runtime-maven-overlap-").toFile().canonicalFile
            try {
                val workspace = root.resolve("build/runtime-adapter-maven/jvm").apply { mkdirs() }
                val original = when (shape) {
                    "equal" -> workspace
                    "ancestor" -> root.resolve("build")
                    else -> workspace.resolve("original").apply { mkdir() }
                }
                val sourceSentinel = original.resolve("original.bin").apply { writeText("original source\n") }
                val outputSentinel = workspace.resolve("previous.bin").apply { writeText("previous output\n") }
                val failure = assertFailsWith<IllegalStateException> { prepareTask(root, original).prepare() }
                assertTrue("overlaps original package" in failure.message.orEmpty())
                assertEquals("original source\n", sourceSentinel.readText())
                assertEquals("previous output\n", outputSentinel.readText())
            } finally { root.deleteRecursively() }
        }
    }

    @Test fun `actual case aliases preserve sources inside existing or absent workspace`() {
        for (shape in listOf("existing", "absent")) {
            val root = createTempDirectory("runtime-maven-case-alias-").toFile().canonicalFile
            try {
                val actualParent = root.resolve("build/RUNTIME-ADAPTER-MAVEN").apply { mkdirs() }
                val actualWorkspace = actualParent.resolve("JVM")
                val original = if (shape == "existing") {
                    actualWorkspace.resolve("original").apply { mkdirs() }
                } else {
                    actualParent
                }
                val sourceSentinel = original.resolve("original.bin").apply { writeText("preserve original\n") }
                val aliasParent = root.resolve("build/runtime-adapter-maven")
                if (!aliasParent.exists()) {
                    // No case alias exists on this filesystem. This conditional
                    // is not evidence of a case-insensitive host execution.
                    assertTrue(actualParent.isDirectory)
                    assertEquals("preserve original\n", sourceSentinel.readText())
                    continue
                }
                assertTrue(Files.isSameFile(actualParent.toPath(), aliasParent.toPath()))
                val outputSentinel = if (shape == "existing") actualWorkspace.resolve("previous.bin").apply {
                    writeText("preserve previous output\n")
                } else null
                val failure = assertFailsWith<IllegalStateException> { prepareTask(root, original).prepare() }
                assertTrue("overlaps original package" in failure.message.orEmpty())
                assertEquals("preserve original\n", sourceSentinel.readText())
                if (outputSentinel != null) assertEquals("preserve previous output\n", outputSentinel.readText())
                else assertFalse(actualWorkspace.exists())
            } finally { root.deleteRecursively() }
        }
    }

    @Test fun `symbolic original or workspace aliases preserve original and previous bytes`() {
        for (shape in listOf("input", "output")) {
            val root = createTempDirectory("runtime-maven-symbolic-alias-").toFile().canonicalFile
            try {
                val original = root.resolve("original").apply { mkdir() }
                val sourceSentinel = original.resolve("original.bin").apply { writeText("original source\n") }
                val actualWorkspace = if (shape == "output") original.resolve("jvm").apply { mkdir() }
                    else root.resolve("build/runtime-adapter-maven/jvm").apply { mkdirs() }
                val outputSentinel = actualWorkspace.resolve("previous.bin").apply { writeText("previous output\n") }
                val input = if (shape == "input") {
                    root.resolve("original-alias").also { Files.createSymbolicLink(it.toPath(), original.toPath()) }
                } else {
                    root.resolve("build").mkdirs()
                    Files.createSymbolicLink(root.resolve("build/runtime-adapter-maven").toPath(), original.toPath())
                    original
                }
                assertFailsWith<IllegalStateException> { prepareTask(root, input).prepare() }
                assertEquals("original source\n", sourceSentinel.readText())
                assertEquals("previous output\n", outputSentinel.readText())
            } finally { root.deleteRecursively() }
        }
    }
}
