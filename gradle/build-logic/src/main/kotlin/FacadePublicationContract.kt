import java.io.File
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault
import org.w3c.dom.Element
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

internal data class FacadePublicationSpec(
    val publication: String,
    val artifact: String,
    val coreArtifact: String,
    val scope: String,
    val variantNames: Set<String>,
    val standardModules: Set<String>,
)

internal val facadePublicationSpecs = listOf(
    FacadePublicationSpec("kotlinMultiplatform", "codex-agent", "codex-agent-core", "runtime",
        setOf("metadataApiElements", "metadataSourcesElements"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("android", "codex-agent-android", "codex-agent-core-android", "compile",
        setOf("androidApiElements-published", "androidRuntimeElements-published", "androidSourcesElements-published"),
        setOf("kotlin-stdlib")),
    FacadePublicationSpec("jvm", "codex-agent-jvm", "codex-agent-core-jvm", "compile",
        setOf("jvmApiElements-published", "jvmRuntimeElements-published", "jvmSourcesElements-published"),
        setOf("kotlin-stdlib")),
    FacadePublicationSpec("iosArm64", "codex-agent-iosarm64", "codex-agent-core-iosarm64", "compile",
        setOf("iosArm64ApiElements-published", "iosArm64MetadataElements-published", "iosArm64SourcesElements-published"),
        setOf("kotlin-stdlib")),
    FacadePublicationSpec("iosSimulatorArm64", "codex-agent-iossimulatorarm64",
        "codex-agent-core-iossimulatorarm64", "compile",
        setOf("iosSimulatorArm64ApiElements-published", "iosSimulatorArm64MetadataElements-published",
            "iosSimulatorArm64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("macosArm64", "codex-agent-macosarm64", "codex-agent-core-macosarm64", "compile",
        setOf("macosArm64ApiElements-published", "macosArm64MetadataElements-published",
            "macosArm64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("macosX64", "codex-agent-macosx64", "codex-agent-core-macosx64", "compile",
        setOf("macosX64ApiElements-published", "macosX64MetadataElements-published",
            "macosX64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("linuxArm64", "codex-agent-linuxarm64", "codex-agent-core-linuxarm64", "compile",
        setOf("linuxArm64ApiElements-published", "linuxArm64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("linuxX64", "codex-agent-linuxx64", "codex-agent-core-linuxx64", "compile",
        setOf("linuxX64ApiElements-published", "linuxX64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("mingwX64", "codex-agent-mingwx64", "codex-agent-core-mingwx64", "compile",
        setOf("mingwX64ApiElements-published", "mingwX64SourcesElements-published"), setOf("kotlin-stdlib")),
    FacadePublicationSpec("js", "codex-agent-js", "codex-agent-core-js", "compile",
        setOf("jsApiElements-published", "jsRuntimeElements-published", "jsSourcesElements-published"),
        setOf("kotlin-dom-api-compat", "kotlin-stdlib-js")),
    FacadePublicationSpec("wasmJs", "codex-agent-wasm-js", "codex-agent-core-wasm-js", "compile",
        setOf("wasmJsApiElements-published", "wasmJsRuntimeElements-published", "wasmJsSourcesElements-published"),
        setOf("kotlin-stdlib-wasm-js")),
)

private data class PublicationDependency(
    val group: String,
    val module: String,
    val version: String,
    val scope: String?,
)

private fun <T, K> List<T>.rejectDuplicates(label: String, identity: (T) -> K): List<T> = apply {
    check(size == map(identity).toSet().size) { "$label contains duplicate entries" }
}

private fun Element.children(name: String): List<Element> = (0 until childNodes.length).mapNotNull { index ->
    (childNodes.item(index) as? Element)?.takeIf { it.localName == name || it.tagName == name }
}

private fun Element.one(name: String): Element = children(name).singleOrNull()
    ?: error("Expected exactly one <$name>")

private fun Element.optionalOne(name: String): Element? = children(name).also {
    check(it.size <= 1) { "Expected at most one <$name>" }
}.singleOrNull()

private fun Element.text(name: String): String = one(name).textContent.trim().also {
    check(it.isNotEmpty()) { "<$name> must not be empty" }
}

private fun pomDependencies(root: Element, managed: Boolean = false): List<PublicationDependency> {
    val parent = if (managed) root.optionalOne("dependencyManagement")?.one("dependencies")
        else root.optionalOne("dependencies")
    return parent?.children("dependency").orEmpty().map { dependency ->
        val elementNames = (0 until dependency.childNodes.length).mapNotNull { index ->
            (dependency.childNodes.item(index) as? Element)?.let { it.localName ?: it.tagName }
        }
        check(elementNames.all { it in setOf("groupId", "artifactId", "version", "scope") }) {
            "POM dependency contains unsupported resolution semantics"
        }
        val scope = dependency.children("scope").also {
            check(it.size <= 1) { "Expected at most one <scope>" }
        }.singleOrNull()?.textContent?.trim()?.also {
            check(it.isNotEmpty()) { "<scope> must not be empty" }
        }
        PublicationDependency(
            dependency.text("groupId"),
            dependency.text("artifactId"),
            dependency.text("version"),
            scope,
        )
    }
}

private fun verifyPomResolutionStructure(root: Element, allowDependencyManagement: Boolean) {
    listOf("parent", "profiles", "repositories", "pluginRepositories", "distributionManagement", "relocation")
        .forEach { name -> check(root.children(name).isEmpty()) { "POM contains unsupported <$name>" } }
    if (!allowDependencyManagement) {
        check(root.children("dependencyManagement").isEmpty()) { "Facade POM contains dependencyManagement" }
    }
}

private fun verifyNoPathLeak(file: File, forbiddenPath: String) {
    val contents = file.readText()
    check(forbiddenPath.isEmpty() || !contents.contains(forbiddenPath)) { "Publication leaks the project path: $file" }
    check(!contents.contains("file:/") &&
        !Regex("""(?m)(?:^|[\s\"'=>(])[A-Za-z]:[/\\]""").containsMatchIn(contents)) {
        "Publication contains an absolute file path: $file"
    }
}

private fun JsonObject.exactKeys(expected: Set<String>, label: String): JsonObject = apply {
    check(keys == expected) { "$label keys mismatch: expected=$expected actual=$keys" }
}

private fun JsonObject.exactStringAttributes(expected: Map<String, String>, label: String) {
    exactKeys(expected.keys, label)
    expected.forEach { (name, value) ->
        check(releaseString(name) == value) { "$label mismatch for $name" }
    }
}

internal fun facadeVariantAttributes(spec: FacadePublicationSpec, name: String): Map<String, String> {
    check(name in spec.variantNames)
    val sources = "SourcesElements" in name
    val metadata = "MetadataElements" in name || name == "metadataApiElements"
    val runtime = "RuntimeElements" in name
    val attributes = linkedMapOf(
        "org.gradle.category" to if (sources) "documentation" else "library",
    )
    if (sources) {
        attributes["org.gradle.dependency.bundling"] = "external"
        attributes["org.gradle.docstype"] = "sources"
    }
    attributes["org.gradle.jvm.environment"] = when (spec.publication) {
        "android" -> "android"
        "jvm" -> "standard-jvm"
        else -> "non-jvm"
    }
    if (spec.publication in setOf("android", "jvm")) {
        attributes["org.gradle.libraryelements"] = when {
            spec.publication == "android" && !sources -> "aar"
            else -> "jar"
        }
    }
    attributes["org.gradle.usage"] = when {
        sources && spec.publication in setOf("android", "jvm") -> "java-runtime"
        sources -> "kotlin-runtime"
        metadata -> "kotlin-metadata"
        spec.publication in setOf("android", "jvm") -> if (runtime) "java-runtime" else "java-api"
        runtime -> "kotlin-runtime"
        else -> "kotlin-api"
    }
    when (spec.publication) {
        "kotlinMultiplatform" -> attributes["org.jetbrains.kotlin.platform.type"] = "common"
        "android" -> attributes["org.jetbrains.kotlin.platform.type"] = "androidJvm"
        "jvm" -> attributes["org.jetbrains.kotlin.platform.type"] = "jvm"
        "js" -> {
            attributes["org.jetbrains.kotlin.js.compiler"] = "ir"
            attributes["org.jetbrains.kotlin.platform.type"] = "js"
        }
        "wasmJs" -> {
            attributes["org.jetbrains.kotlin.platform.type"] = "wasm"
            attributes["org.jetbrains.kotlin.wasm.target"] = "js"
        }
        else -> {
            attributes["org.jetbrains.kotlin.native.target"] = when (spec.publication) {
                "iosArm64" -> "ios_arm64"
                "iosSimulatorArm64" -> "ios_simulator_arm64"
                "macosArm64" -> "macos_arm64"
                "macosX64" -> "macos_x64"
                "linuxArm64" -> "linux_arm64"
                "linuxX64" -> "linux_x64"
                "mingwX64" -> "mingw_x64"
                else -> error("Unsupported facade publication: ${spec.publication}")
            }
            attributes["org.jetbrains.kotlin.platform.type"] = "native"
        }
    }
    return attributes
}

private fun moduleDependency(value: JsonObject): PublicationDependency {
    value.exactKeys(setOf("group", "module", "version"), "Gradle module dependency")
    val version = value.releaseObject("version").exactKeys(setOf("requires"), "Gradle module dependency version")
    return PublicationDependency(
        value.releaseString("group"), value.releaseString("module"), version.releaseString("requires"), null,
    )
}

private fun moduleDependencies(variant: JsonObject): List<PublicationDependency> =
    (variant["dependencies"] as? JsonArray).orEmpty().map { moduleDependency(it.jsonObject) }

internal fun facadeVariantFileIdentity(
    spec: FacadePublicationSpec,
    name: String,
    sdkVersion: String,
): Pair<String, String> {
    val suffix = spec.artifact.removePrefix("codex-agent-")
    val sources = "SourcesElements" in name
    val metadata = "MetadataElements" in name
    val url = when {
        sources -> "${spec.artifact}-$sdkVersion-sources.jar"
        metadata -> "${spec.artifact}-$sdkVersion-metadata.jar"
        spec.publication == "android" -> "${spec.artifact}-$sdkVersion.aar"
        spec.publication in setOf("kotlinMultiplatform", "jvm") -> "${spec.artifact}-$sdkVersion.jar"
        else -> "${spec.artifact}-$sdkVersion.klib"
    }
    val publishedName = when {
        spec.publication == "kotlinMultiplatform" && sources ->
            "codex-agent-sdk-kotlin-$sdkVersion-sources.jar"
        spec.publication == "kotlinMultiplatform" -> "codex-agent-sdk-metadata-$sdkVersion.jar"
        sources -> "codex-agent-sdk-$suffix-$sdkVersion-sources.jar"
        metadata -> "codex-agent-sdk-$suffix-$sdkVersion-metadata.jar"
        spec.publication == "android" -> "codex-agent-sdk.aar"
        spec.publication == "jvm" -> "codex-agent-sdk-jvm-$sdkVersion.jar"
        spec.publication in setOf("js", "wasmJs") -> "codex-agent-sdk-$suffix-$sdkVersion.klib"
        else -> "codex-agent-sdk-${spec.publication}Main-$sdkVersion.klib"
    }
    return publishedName to url
}

private fun verifyModuleFiles(
    variant: JsonObject,
    spec: FacadePublicationSpec,
    name: String,
    sdkVersion: String,
) {
    val files = variant.releaseArray("files")
    check(files.size == 1) { "Facade variant must contain exactly one file: ${spec.artifact}/$name" }
    val file = files.single().jsonObject.exactKeys(
        setOf("name", "url", "size", "sha512", "sha256", "sha1", "md5"), "Gradle module file",
    )
    val expected = facadeVariantFileIdentity(spec, name, sdkVersion)
    check(file.releaseString("name") == expected.first && file.releaseString("url") == expected.second) {
        "Facade variant file identity mismatch: ${spec.artifact}/$name"
    }
    check(file.releaseLong("size") > 0) { "Facade variant file size must be positive" }
    mapOf("sha512" to 128, "sha256" to 64, "sha1" to 40, "md5" to 32).forEach { (field, size) ->
        check(Regex("[0-9a-f]{$size}").matches(file.releaseString(field))) {
            "Facade variant file $field is invalid"
        }
    }
}

private fun verifyPom(
    file: File,
    group: String,
    artifact: String,
    version: String,
    expected: Set<PublicationDependency>,
): Set<PublicationDependency> {
    check(file.isFile) { "Facade POM is missing: $file" }
    val root = secureDocumentBuilderFactory(namespaceAware = true).newDocumentBuilder().parse(file).documentElement
    check(root.text("modelVersion") == "4.0.0" && root.text("groupId") == group &&
        root.text("artifactId") == artifact && root.text("version") == version) {
        "Facade POM coordinate mismatch: $file"
    }
    verifyPomResolutionStructure(root, allowDependencyManagement = false)
    val actual = pomDependencies(root).rejectDuplicates("Facade POM dependencies for $artifact") {
        it.group to it.module
    }
    check(actual.toSet() == expected) {
        "Facade POM dependencies mismatch for $artifact: expected=$expected actual=$actual"
    }
    return actual.toSet()
}

private fun expectedPomDependencies(
    group: String,
    spec: FacadePublicationSpec,
    contractVersion: String,
    kotlinVersion: String,
): Set<PublicationDependency> = buildSet {
    add(PublicationDependency(group, spec.coreArtifact, contractVersion, spec.scope))
    spec.standardModules.forEach { add(PublicationDependency("org.jetbrains.kotlin", it, kotlinVersion, spec.scope)) }
}

internal fun verifyFacadePublicationContract(
    facadePublications: File,
    bomPublications: File,
    group: String,
    contractVersion: String,
    runtimeVersion: String,
    sdkVersion: String,
    kotlinVersion: String,
    forbiddenPath: String = "",
): JsonObject {
    check(facadePublications.isDirectory && bomPublications.isDirectory) { "Facade/BOM publications are missing" }
    val specByArtifact = facadePublicationSpecs.associateBy(FacadePublicationSpec::artifact)
    facadePublicationSpecs.forEach { spec ->
        val directory = facadePublications.resolve(spec.publication)
        val expected = expectedPomDependencies(group, spec, contractVersion, kotlinVersion)
        val pom = directory.resolve("pom-default.xml")
        verifyPom(pom, group, spec.artifact, sdkVersion, expected)
        val pomRoot = secureDocumentBuilderFactory(namespaceAware = true).newDocumentBuilder().parse(pom).documentElement
        val expectedPackaging = when (spec.publication) {
            "android" -> "aar"
            "kotlinMultiplatform", "jvm" -> "jar"
            else -> "klib"
        }
        check(pomRoot.optionalOne("packaging")?.textContent?.trim().orEmpty().ifEmpty { "jar" } == expectedPackaging) {
            "Facade POM packaging mismatch for ${spec.artifact}"
        }
        val moduleFile = directory.resolve("module.json")
        check(moduleFile.isFile) { "Facade Gradle module metadata is missing: $moduleFile" }
        verifyNoPathLeak(directory.resolve("pom-default.xml"), forbiddenPath)
        verifyNoPathLeak(moduleFile, forbiddenPath)
        val module = moduleFile.readReleaseObject().exactKeys(
            setOf("formatVersion", "component", "createdBy", "variants"), "Facade Gradle module metadata",
        )
        check(module.releaseString("formatVersion") == "1.1") { "Unsupported facade module metadata format" }
        val component = module.releaseObject("component")
        val expectedComponentKeys = if (spec.publication == "kotlinMultiplatform") {
            setOf("group", "module", "version", "attributes")
        } else {
            setOf("url", "group", "module", "version", "attributes")
        }
        component.exactKeys(expectedComponentKeys, "Facade module component")
        check(component.releaseString("group") == group && component.releaseString("module") == "codex-agent" &&
            component.releaseString("version") == sdkVersion) { "Facade module component identity mismatch" }
        component.releaseObject("attributes").exactStringAttributes(
            mapOf("org.gradle.status" to "release"),
            "Facade module component attributes",
        )
        if (spec.publication != "kotlinMultiplatform") {
            check(component.releaseString("url") ==
                "../../codex-agent/$sdkVersion/codex-agent-$sdkVersion.module") {
                "Facade target module does not reference the SDK root"
            }
        }
        val variants = module.releaseArray("variants").map { it.jsonObject }
        val names = variants.map { it.releaseString("name") }
            .rejectDuplicates("Facade module variant names for ${spec.artifact}") { it }
        val expectedNames = if (spec.publication == "kotlinMultiplatform") {
            facadePublicationSpecs.flatMap { it.variantNames }.toSet()
        } else spec.variantNames
        check(names.toSet() == expectedNames && names.size == expectedNames.size) {
            "Facade module variants mismatch for ${spec.artifact}"
        }
        variants.forEach { variant ->
            val name = variant.releaseString("name")
            val targetSpec = if (spec.publication == "kotlinMultiplatform") {
                facadePublicationSpecs.single { name in it.variantNames }
            } else spec
            variant.releaseObject("attributes").exactStringAttributes(
                facadeVariantAttributes(targetSpec, name),
                "Facade variant attributes for ${spec.artifact}/$name",
            )
            if (spec.publication == "kotlinMultiplatform" && name !in spec.variantNames) {
                variant.exactKeys(setOf("name", "attributes", "available-at"), "Facade available-at variant")
                val available = variant.releaseObject("available-at").exactKeys(
                    setOf("url", "group", "module", "version"), "Facade available-at identity",
                )
                check(available.releaseString("group") == group &&
                    available.releaseString("module") == targetSpec.artifact &&
                    available.releaseString("version") == sdkVersion &&
                    available.releaseString("url") ==
                    "../../${targetSpec.artifact}/$sdkVersion/${targetSpec.artifact}-$sdkVersion.module") {
                    "Facade available-at identity mismatch: $name"
                }
            } else {
                val sources = name.contains("Sources")
                variant.exactKeys(
                    if (sources) setOf("name", "attributes", "files")
                    else setOf("name", "attributes", "dependencies", "files"),
                    "Facade local variant",
                )
                verifyModuleFiles(variant, spec, name, sdkVersion)
                val expectedModuleDependencies = if (sources) emptySet() else expected.map {
                    it.copy(
                        module = when {
                            it.group == group && it.module == spec.coreArtifact -> "codex-agent-core"
                            it.group == "org.jetbrains.kotlin" && it.module.startsWith("kotlin-stdlib") ->
                                "kotlin-stdlib"
                            else -> it.module
                        },
                        scope = null,
                    )
                }.toSet()
                val actualModuleDependencies = moduleDependencies(variant)
                    .rejectDuplicates("Facade module dependencies for ${spec.artifact}/$name") {
                        it.group to it.module
                    }
                check(actualModuleDependencies.toSet() == expectedModuleDependencies) {
                    "Facade module dependencies mismatch: ${spec.artifact}/$name"
                }
            }
        }
    }

    val bomPom = bomPublications.resolve("pom-default.xml")
    val bomModule = bomPublications.resolve("module.json")
    verifyNoPathLeak(bomPom, forbiddenPath)
    verifyNoPathLeak(bomModule, forbiddenPath)
    val expectedConstraints = mapOf(
        "codex-agent" to sdkVersion,
        "codex-agent-core" to contractVersion,
        "codex-agent-runtime-desktop" to runtimeVersion,
        "codex-agent-runtime-android" to sdkVersion,
        "codex-agent-runtime-ios" to sdkVersion,
    )
    val bomRoot = secureDocumentBuilderFactory(namespaceAware = true).newDocumentBuilder().parse(bomPom).documentElement
    verifyPomResolutionStructure(bomRoot, allowDependencyManagement = true)
    check(bomRoot.text("modelVersion") == "4.0.0" && bomRoot.text("groupId") == group &&
        bomRoot.text("artifactId") == "codex-agent-bom" &&
        bomRoot.text("version") == sdkVersion && bomRoot.text("packaging") == "pom" &&
        pomDependencies(bomRoot).isEmpty()) { "SDK BOM POM identity mismatch" }
    val expectedBomDependencies = expectedConstraints.mapTo(linkedSetOf()) { (module, version) ->
        PublicationDependency(group, module, version, null)
    }
    val pomConstraints = pomDependencies(bomRoot, managed = true)
        .rejectDuplicates("SDK BOM POM constraints") { it.group to it.module }
    check(pomConstraints.toSet() == expectedBomDependencies) {
        "SDK BOM POM constraints mismatch"
    }
    val module = bomModule.readReleaseObject().exactKeys(
        setOf("formatVersion", "component", "createdBy", "variants"), "SDK BOM module",
    )
    check(module.releaseString("formatVersion") == "1.1") { "Unsupported SDK BOM module metadata format" }
    val component = module.releaseObject("component").exactKeys(
        setOf("group", "module", "version", "attributes"), "SDK BOM module component",
    )
    check(component.releaseString("group") == group && component.releaseString("module") == "codex-agent-bom" &&
        component.releaseString("version") == sdkVersion) { "SDK BOM module identity mismatch" }
    val componentAttributes = component.releaseObject("attributes").exactKeys(
        setOf("org.gradle.status"), "SDK BOM module component attributes",
    )
    check(componentAttributes.releaseString("org.gradle.status") == "release") {
        "SDK BOM module component status mismatch"
    }
    val bomVariants = module.releaseArray("variants").map { it.jsonObject }
    val expectedBomVariants = mapOf("apiElements" to "java-api", "runtimeElements" to "java-runtime")
    val bomVariantNames = bomVariants.map { it.releaseString("name") }
        .rejectDuplicates("SDK BOM module variant names") { it }
    check(bomVariantNames.size == expectedBomVariants.size && bomVariantNames.toSet() == expectedBomVariants.keys) {
        "SDK BOM variants mismatch"
    }
    bomVariants.forEach { variant ->
        variant.exactKeys(setOf("name", "attributes", "dependencyConstraints"), "SDK BOM variant")
        val name = variant.releaseString("name")
        val attributes = variant.releaseObject("attributes").exactKeys(
            setOf("org.gradle.category", "org.gradle.usage"), "SDK BOM variant attributes",
        )
        check(attributes.releaseString("org.gradle.category") == "platform" &&
            attributes.releaseString("org.gradle.usage") == expectedBomVariants.getValue(name)) {
            "SDK BOM variant attributes mismatch: $name"
        }
        val constraints = variant.releaseArray("dependencyConstraints").map { value ->
            val constraint = value.jsonObject.exactKeys(
                setOf("group", "module", "version"), "SDK BOM constraint",
            )
            val required = constraint.releaseObject("version").exactKeys(setOf("requires"), "SDK BOM version")
            PublicationDependency(
                constraint.releaseString("group"), constraint.releaseString("module"),
                required.releaseString("requires"), null,
            )
        }.rejectDuplicates("SDK BOM module constraints for $name") { it.group to it.module }
        check(constraints.toSet() == expectedBomDependencies) { "SDK BOM module constraints mismatch" }
    }
    check(specByArtifact.size == 12) { "Facade publication specification is not complete" }
    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("result", JsonPrimitive("passed"))
        put("contractVersion", JsonPrimitive(contractVersion))
        put("runtimeVersion", JsonPrimitive(runtimeVersion))
        put("sdkVersion", JsonPrimitive(sdkVersion))
        put("publicationCount", JsonPrimitive(facadePublicationSpecs.size))
        put("rootVariantCount", JsonPrimitive(32))
        put("bomConstraintCount", JsonPrimitive(expectedConstraints.size))
    }
}

@DisableCachingByDefault(because = "This task verifies generated publication metadata")
abstract class VerifySdkFacadePublicationMetadataTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val facadePublications: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val bomPublications: DirectoryProperty
    @get:Input abstract val groupId: Property<String>
    @get:Input abstract val contractVersion: Property<String>
    @get:Input abstract val runtimeVersion: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val kotlinVersion: Property<String>
    @get:Input abstract val forbiddenPath: Property<String>
    @get:OutputFile abstract val resultFile: RegularFileProperty

    @TaskAction
    fun verify() {
        resultFile.get().asFile.atomicWriteJson(verifyFacadePublicationContract(
            facadePublications.get().asFile,
            bomPublications.get().asFile,
            groupId.get(),
            contractVersion.get(),
            runtimeVersion.get(),
            sdkVersion.get(),
            kotlinVersion.get(),
            forbiddenPath.get(),
        ))
    }
}
