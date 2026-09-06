import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.Project
import org.gradle.api.attributes.Attribute
import org.gradle.api.attributes.Usage
import org.gradle.api.component.SoftwareComponentFactory
import org.gradle.api.file.Directory
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.FileCollection
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.publish.PublishingExtension
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.publish.maven.internal.publication.DefaultMavenPublication
import org.gradle.api.publish.maven.internal.publication.MavenPublicationInternal
import org.gradle.api.publish.maven.tasks.GenerateMavenPom
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.TaskProvider

private val runtimeMavenChecksums = linkedMapOf(".md5" to "MD5", ".sha1" to "SHA-1", ".sha256" to "SHA-256", ".sha512" to "SHA-512")

internal fun runtimeAdapterPrimaryName(component: String, classifier: String?, extension: String): String {
    val primaryExtension = when (component) {
        "jvm" -> "jar"
        "node-js", "node-wasm" -> "klib"
        else -> error("Unsupported Runtime Maven adapter: $component")
    }
    return when {
        classifier.isNullOrEmpty() && extension == primaryExtension -> "main.$extension"
        classifier in setOf("sources", "javadoc") && extension == "jar" -> "$classifier.jar"
        else -> error("Unexpected Runtime publication artifact: $classifier.$extension")
    }
}

/** Capture the existing publication, not a reconstruction from linked JS or checkout sources. */
fun Project.retainRuntimeAdapterPublication(component: String, title: String, publicationName: String) {
    val publication = extensions.getByType(PublishingExtension::class.java).publications
        .getByName(publicationName) as MavenPublication
    val artifacts = publication.artifacts.toList()
    val names = artifacts.map { runtimeAdapterPrimaryName(component, it.classifier, it.extension) }
    check(names.size == 3 && names.toSet().size == 3) {
        "Runtime publication must contain exactly main, sources and javadoc: " +
            "component=$component publication=$publicationName artifacts=" +
            artifacts.map { "${it.classifier.orEmpty()}:${it.extension}:${it.file.name}" } + " mapped=$names"
    }
    tasks.named("stage${title}RuntimeBinaryOutputs", Sync::class.java).configure {
        artifacts.zip(names).forEach { (artifact, name) ->
            dependsOn(artifact.buildDependencies)
            from(artifact.file) { into("publication"); rename { name } }
        }
    }
}

abstract class RuntimeAdapterComponentFactory @Inject constructor(val components: SoftwareComponentFactory)

abstract class PrepareRuntimeAdapterMavenTask : DefaultTask() {
    @get:Input abstract val component: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val originalPackage: DirectoryProperty
    @get:Internal abstract val ownedBuild: DirectoryProperty
    @get:Internal abstract val workspace: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun prepare() {
        val input = originalPackage.get().asFile.toPath()
        val owned = ownedBuild.get().asFile.toPath()
        val output = workspace.get().asFile.toPath()
        check(component.get() in setOf("jvm", "node-js", "node-wasm"))
        check(output == owned.resolve("runtime-adapter-maven/${component.get()}")) { "Runtime Maven workspace must be task-owned" }
        listOf(input, owned, output).forEach { path ->
            check(path.isAbsolute && path.normalize() == path) { "Runtime Maven paths must be absolute and normalized" }
            generateSequence(path) { it.parent }.forEach { parent ->
                check(!Files.isSymbolicLink(parent) && (!Files.exists(parent, LinkOption.NOFOLLOW_LINKS) ||
                    Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS))) { "Unsafe Runtime Maven directory: $parent" }
            }
        }
        requireRegularRuntimeProductTree(input, "Original Runtime adapter package")
        val realInput = input.toRealPath()
        // Use the existing metadata-stage safety algorithm: an already-existing
        // case alias must be resolved itself, not reconstructed from the build root.
        var existingOutput = output
        val missingNames = mutableListOf<java.nio.file.Path>()
        while (!Files.exists(existingOutput, LinkOption.NOFOLLOW_LINKS)) {
            missingNames.add(existingOutput.fileName)
            existingOutput = checkNotNull(existingOutput.parent)
        }
        val realOutput = missingNames.asReversed().fold(existingOutput.toRealPath()) { parent, name -> parent.resolve(name) }
        fun containsSameFile(descendant: java.nio.file.Path, ancestor: java.nio.file.Path): Boolean =
            Files.exists(ancestor, LinkOption.NOFOLLOW_LINKS) &&
                generateSequence(descendant) { it.parent }.any { path ->
                    Files.exists(path, LinkOption.NOFOLLOW_LINKS) && Files.isSameFile(path, ancestor)
                }
        check(!realInput.startsWith(realOutput) && !realOutput.startsWith(realInput) &&
            !containsSameFile(realInput, realOutput) && !containsSameFile(realOutput, realInput)) {
            "Runtime Maven workspace overlaps original package"
        }
        if (Files.exists(output, LinkOption.NOFOLLOW_LINKS)) {
            Files.walk(output).use { entries -> entries.forEach { path ->
                check(!Files.isSymbolicLink(path) && (Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) ||
                    Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS))) { "Unsafe previous Runtime Maven workspace: $path" }
            } }
            Files.walk(output).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        }
        Files.createDirectories(output)
    }
}

abstract class FinalizeRuntimeAdapterMavenTask : DefaultTask() {
    @get:Input abstract val component: Property<String>
    @get:Input abstract val groupId: Property<String>
    @get:Input abstract val artifactId: Property<String>
    @get:Input abstract val productVersion: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val originalPrimaries: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val freshRepository: DirectoryProperty
    @get:OutputDirectory abstract val repository: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun finalizeRepository() = finalizeRuntimeAdapterMaven(
        component.get(), groupId.get(), artifactId.get(), productVersion.get(),
        originalPrimaries.get().asFile, freshRepository.get().asFile, repository.get().asFile,
    )
}

/** Only frames/checksums fresh Gradle output; Gradle remains the POM/GMM producer. */
internal fun finalizeRuntimeAdapterMaven(
    component: String, group: String, artifact: String, version: String,
    original: File, fresh: File, destination: File,
) {
    check(group == "io.github.codex-agent-labs") { "Unexpected Runtime Maven group" }
    val suffix = mapOf("jvm" to "jvm", "node-js" to "js", "node-wasm" to "wasm-js").getValue(component)
    check(artifact == "codex-agent-runtime-desktop-$suffix") { "Unexpected Runtime Maven coordinate" }
    check(PRODUCT_SEMVER.matches(version)) { "Runtime Maven version must be canonical" }
    val workspace = fresh.parentFile
    check(fresh.name == "fresh" && destination == workspace.resolve("repository") &&
        original == workspace.resolve("original-package/outputs/publication")) { "Runtime Maven finalization paths must be owned siblings" }
    requireRegularRuntimeProductTree(fresh.toPath(), "Fresh Runtime Maven publication")
    requireRegularRuntimeProductTree(original.toPath(), "Original Runtime Maven primaries")
    check(!Files.exists(destination.toPath(), LinkOption.NOFOLLOW_LINKS) ||
        (!Files.isSymbolicLink(destination.toPath()) && Files.isDirectory(destination.toPath(), LinkOption.NOFOLLOW_LINKS) &&
            destination.listFiles()!!.isEmpty())) { "Runtime Maven handoff already exists or is unsafe" }
    val extension = if (component == "jvm") "jar" else "klib"
    val prefix = "${group.replace('.', '/')}/$artifact/$version/$artifact-$version"
    val originalNames = mapOf(".$extension" to "main.$extension", "-sources.jar" to "sources.jar", "-javadoc.jar" to "javadoc.jar")
    check(original.listFiles()!!.map { it.name }.toSet() == originalNames.values.toSet()) { "Runtime Maven original primary inventory mismatch" }
    val primaries = (originalNames.keys + setOf(".pom", ".module")).map { prefix + it }.toSet()
    val metadata = "${group.replace('.', '/')}/$artifact/maven-metadata.xml"
    val expected = (primaries + metadata).flatMap { primary -> listOf(primary) + runtimeMavenChecksums.keys.map { primary + it } }.toSet()
    fun inventory(root: File) = root.walkTopDown().filter(File::isFile).associate {
        it.relativeTo(root).invariantSeparatorsPath to (it.length() to it.releaseDigest())
    }
    val before = inventory(fresh)
    val originalBefore = inventory(original)
    check(before.keys == expected) { "Fresh Runtime Maven publication inventory mismatch" }
    (primaries + metadata).forEach { primary -> runtimeMavenChecksums.forEach { (suffix, algorithm) ->
        val digest = fresh.resolve(primary).releaseDigest(algorithm)
        check(fresh.resolve(primary + suffix).readText() in setOf(digest, "$digest\n")) { "Fresh Runtime Maven checksum mismatch: $primary$suffix" }
    } }
    originalNames.forEach { (suffix, name) ->
        check(before.getValue(prefix + suffix) == originalBefore.getValue(name)) { "Published Runtime artifact differs from original primary: $name" }
    }
    try {
        primaries.sorted().forEach { primary ->
            val output = destination.resolve("$component/$primary")
            Files.createDirectories(output.parentFile.toPath())
            Files.copy(fresh.resolve(primary).toPath(), output.toPath())
            runtimeMavenChecksums.forEach { (suffix, algorithm) ->
                Files.writeString(output.resolveSibling(output.name + suffix).toPath(), output.releaseDigest(algorithm) + "\n")
            }
        }
        requireRegularRuntimeProductTree(fresh.toPath(), "Fresh Runtime Maven publication")
        requireRegularRuntimeProductTree(original.toPath(), "Original Runtime Maven primaries")
        check(inventory(fresh) == before && inventory(original) == originalBefore) { "Original Runtime Maven inputs changed during framing" }
    } catch (failure: Exception) {
        if (destination.exists()) Files.walk(destination.toPath()).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        throw failure
    }
}

/** Called after KGP has created its real target publication and dependency rewriting. */
fun Project.registerRuntimeAdapterMavenHandoff(
    component: String, title: String, publicationName: String, originalStage: Provider<Directory>,
    originalVersion: Provider<String>, tooling: FileCollection, repositoryRoot: File,
): TaskProvider<FinalizeRuntimeAdapterMavenTask> {
    val publishing = extensions.getByType(PublishingExtension::class.java)
    val original = publishing.publications.getByName(publicationName) as DefaultMavenPublication
    check(!providers.gradleProperty("signingInMemoryKey").isPresent &&
        !providers.gradleProperty("signing.secretKeyRingFile").isPresent) { "Reusable Runtime Maven handoffs must not be signed" }
    val workspace = layout.buildDirectory.dir("runtime-adapter-maven/$component")
    val snapshotRoot = workspace.map { it.dir("original-package") }
    val prepare = tasks.register("prepare${title}RuntimeMavenHandoff", PrepareRuntimeAdapterMavenTask::class.java) {
        this.component.set(component); originalPackage.set(originalStage)
        ownedBuild.set(layout.buildDirectory); this.workspace.set(workspace)
    }
    val snapshot = registerRuntimeStageSnapshot("snapshot${title}RuntimeMavenPackage", originalStage, snapshotRoot, tooling, repositoryRoot)
    snapshot.configure { dependsOn(prepare) }
    val verify = registerRuntimeOutputVerification(
        "verify${title}RuntimeMavenPackage", snapshot, providers.provider { component }, "package",
        providers.provider { component }, originalVersion, snapshotRoot, tooling, repositoryRoot,
    )
    val imported = snapshotRoot.map { it.dir("outputs/publication") }
    val importedComponent = objects.newInstance(RuntimeAdapterComponentFactory::class.java).components.adhoc("imported${title}Runtime")
    components.add(importedComponent)
    // Register publications while plugin afterEvaluate callbacks are still legal.
    // KGP usages are attached only after its nested evaluation lifecycle finishes.
    val publication = publishing.publications.create("imported${title}Runtime", MavenPublication::class.java) {
        groupId = original.groupId; artifactId = original.artifactId; version = original.version
        from(importedComponent)
    }
    // Pinned Gradle 9.4.1 seam: retain the ORIGINAL KGP POM generator and its target dependency rewrite.
    (publication as MavenPublicationInternal).setPomGenerator(tasks.named("generatePomFileFor${publicationName.replaceFirstChar(Char::uppercaseChar)}Publication", GenerateMavenPom::class.java))
    (publication as DefaultMavenPublication).withoutBuildIdentifier()
    val repositoryName = "imported${title}Runtime"
    publishing.repositories.maven { name = repositoryName; url = uri(workspace.get().dir("fresh")) }
    val publish = tasks.named("publishImported${title}RuntimePublicationToImported${title}RuntimeRepository")
    publish.configure { dependsOn(verify) }
    val finalize = tasks.register("finalize${title}RuntimeMavenHandoff", FinalizeRuntimeAdapterMavenTask::class.java) {
        dependsOn(publish); this.component.set(component)
        originalPrimaries.set(imported); freshRepository.set(workspace.map { it.dir("fresh") })
        repository.set(workspace.map { it.dir("repository") })
    }
    gradle.projectsEvaluated {
        // Preserve actual KGP published attributes/dependencies, never artifact build dependencies.
        original.component.get().usages.forEachIndexed { index, usage ->
            val configuration = configurations.create("imported${title}RuntimeVariant$index") {
                isCanBeResolved = false; isCanBeConsumed = true
                usage.attributes.keySet().forEach { key ->
                    @Suppress("UNCHECKED_CAST") val attribute = key as Attribute<Any>
                    attributes.attribute(attribute, checkNotNull(usage.attributes.getAttribute(attribute)))
                }
                usage.dependencies.forEach { dependencies.add(it.copy()) }
                usage.dependencyConstraints.forEach { dependencyConstraints.add(it) }
                usage.globalExcludes.forEach { rule -> exclude(buildMap {
                    rule.group?.let { put("group", it) }
                    rule.module?.let { put("module", it) }
                }) }
                usage.capabilities.forEach { outgoing.capability("${it.group}:${it.name}:${it.version}") }
                usage.artifacts.forEach { artifact ->
                    val name = runtimeAdapterPrimaryName(component, artifact.classifier, artifact.extension)
                    outgoing.artifact(imported.map { it.file(name) }) {
                        classifier = artifact.classifier; extension = artifact.extension; builtBy(verify)
                    }
                }
            }
            importedComponent.addVariantsFromConfiguration(configuration) {
                val usageName = usage.attributes.getAttribute(Usage.USAGE_ATTRIBUTE)?.name.orEmpty()
                mapToMavenScope(if (usageName.endsWith("-api")) "compile" else "runtime")
                if (usage.artifacts.all { !it.classifier.isNullOrEmpty() }) mapToOptional()
            }
        }
        // The plugin's delayed artifactId callback has now run. Preserve the
        // original target's final coordinates, not the imported publication name.
        publication.groupId = original.groupId
        publication.artifactId = original.artifactId
        publication.version = original.version
        // Replace Vanniktech's generated javadoc only after usages are attached;
        // reading artifacts earlier would prematurely materialize an empty component.
        publication.artifacts.removeAll { it.classifier == "javadoc" }
        publication.artifact(imported.map { it.file("javadoc.jar") }) {
            classifier = "javadoc"; extension = "jar"; builtBy(verify)
        }
        finalize.configure {
            groupId.set(publication.groupId); artifactId.set(publication.artifactId); productVersion.set(publication.version)
        }
    }
    return finalize
}
