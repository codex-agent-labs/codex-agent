import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

class FacadePublicationContractTest {
    @Test
    fun `source usages match compiler target conventions`() {
        fun usage(publication: String, variant: String) = facadeVariantAttributes(
            facadePublicationSpecs.single { it.publication == publication },
            variant,
        ).getValue("org.gradle.usage")

        assertEquals("java-runtime", usage("android", "androidSourcesElements-published"))
        assertEquals("java-runtime", usage("jvm", "jvmSourcesElements-published"))
        assertEquals("kotlin-runtime", usage("kotlinMultiplatform", "metadataSourcesElements"))
        assertEquals("kotlin-runtime", usage("iosArm64", "iosArm64SourcesElements-published"))
    }

    @Test
    fun `unequal product versions pass the exact facade and BOM contract`() = withFixture { fixture ->
        val report = fixture.verify()
        assertEquals("1.2.3", report.getValue("contractVersion").jsonPrimitive.content)
        assertEquals("2.3.4", report.getValue("runtimeVersion").jsonPrimitive.content)
        assertEquals("3.4.5", report.getValue("sdkVersion").jsonPrimitive.content)
        assertEquals(12, report.getValue("publicationCount").jsonPrimitive.content.toInt())
        assertEquals(32, report.getValue("rootVariantCount").jsonPrimitive.content.toInt())
        assertEquals(5, report.getValue("bomConstraintCount").jsonPrimitive.content.toInt())
    }

    @Test
    fun `missing extra and wrong dependencies fail closed`() {
        listOf<(Fixture) -> Unit>(
            { fixture -> fixture.removeCoreDependency("jvm") },
            { fixture -> fixture.addDependency("jvm", "unexpected", "9.9.9") },
            { fixture -> fixture.replace("jvm", "codex-agent-core-jvm", "codex-agent-core-wrong") },
        ).forEach { mutation ->
            withFixture { fixture ->
                mutation(fixture)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `duplicate facade POM and module dependencies fail closed`() {
        withFixture { fixture ->
            fixture.duplicatePomDependency("jvm")
            assertDuplicateRejected(fixture)
        }
        withFixture { fixture ->
            fixture.duplicateModuleDependency("jvm")
            assertDuplicateRejected(fixture)
        }
    }

    @Test
    fun `facade POM and module file resolution semantics are exact`() {
        withFixture { fixture ->
            fixture.addPomDependencyOptional("jvm")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.replace(
                "jvm",
                "<artifactId>codex-agent-jvm</artifactId>",
                "<artifactId>codex-agent-jvm</artifactId><packaging>klib</packaging>",
            )
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.emptyModuleFiles("jvm")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.wrongTypeModuleFiles("jvm")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        listOf(
            "\"size\":1" to "\"size\":0",
            "\"sha256\":\"${"2".repeat(64)}\"" to "\"sha256\":\"invalid\"",
            "codex-agent-sdk-jvm-$sdkVersion.jar" to "wrong-$sdkVersion.jar",
        ).forEach { (old, new) ->
            withFixture { fixture ->
                fixture.replaceModule("jvm", old, new)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `duplicate facade module variant names fail closed`() = withFixture { fixture ->
        fixture.duplicateModuleVariant("jvm", "jvmApiElements-published")
        assertDuplicateRejected(fixture)
    }

    @Test
    fun `wrong local variant and available-at identity fail closed`() {
        withFixture { fixture ->
            fixture.replaceModule("jvm", "jvmApiElements-published", "wrongApiElements-published")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.replaceModule(
                "kotlinMultiplatform",
                "../../codex-agent-jvm/3.4.5/codex-agent-jvm-3.4.5.module",
                "../../codex-agent-jvm/3.4.5/wrong.module",
            )
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
    }

    @Test
    fun `facade component and every platform variant attribute are exact`() {
        listOf(
            "\"org.gradle.status\":\"release\"" to "\"org.gradle.status\":\"integration\"",
            "\"org.gradle.status\":\"release\"" to
                "\"unexpected\":\"value\",\"org.gradle.status\":\"release\"",
            "\"org.jetbrains.kotlin.platform.type\":\"jvm\"" to
                "\"org.jetbrains.kotlin.platform.type\":\"androidJvm\"",
            "\"org.jetbrains.kotlin.native.target\":\"ios_arm64\"" to
                "\"org.jetbrains.kotlin.native.target\":\"macos_arm64\"",
            "\"org.jetbrains.kotlin.js.compiler\":\"ir\"" to
                "\"org.jetbrains.kotlin.js.compiler\":\"legacy\"",
            "\"org.jetbrains.kotlin.wasm.target\":\"js\"" to
                "\"org.jetbrains.kotlin.wasm.target\":\"wasi\"",
            "\"org.gradle.usage\":\"kotlin-metadata\"" to
                "\"org.gradle.usage\":\"kotlin-runtime\"",
            "\"org.gradle.category\":\"documentation\"" to
                "\"org.gradle.category\":\"library\"",
        ).forEach { (old, new) ->
            withFixture { fixture ->
                fixture.replaceFacadeModule(old, new)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `wrong BOM constraint fails closed`() = withFixture { fixture ->
        fixture.replaceBom("<version>1.2.3</version>", "<version>9.9.9</version>")
        assertFailsWith<IllegalStateException> { fixture.verify() }
    }

    @Test
    fun `duplicate BOM constraints fail closed before identity comparison`() {
        withFixture { fixture ->
            fixture.duplicateBomPomConstraint()
            assertDuplicateRejected(fixture)
        }
        withFixture { fixture ->
            fixture.duplicateBomModuleConstraint()
            assertDuplicateRejected(fixture)
        }
    }

    @Test
    fun `BOM module format component identity and status are exact`() {
        listOf<Pair<String, String>>(
            "\"formatVersion\":\"1.1\"" to "\"formatVersion\":\"1.0\"",
            "\"group\":\"io.github.codex-agent-labs\"" to "\"group\":\"wrong.group\"",
            "\"module\":\"codex-agent-bom\"" to "\"module\":\"wrong-bom\"",
            "\"version\":\"3.4.5\"" to "\"version\":\"9.9.9\"",
            "\"org.gradle.status\":\"release\"" to "\"org.gradle.status\":\"integration\"",
            "\"org.gradle.status\":\"release\"" to
                "\"unexpected\":\"value\",\"org.gradle.status\":\"release\"",
        ).forEach { (old, new) ->
            withFixture { fixture ->
                fixture.replaceBomModule(old, new)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `BOM variants require exact count names attributes and scopes`() {
        withFixture { fixture ->
            fixture.duplicateBomVariant()
            assertDuplicateRejected(fixture)
        }
        listOf<Pair<String, String>>(
            "\"name\":\"apiElements\"" to "\"name\":\"wrongElements\"",
            "\"org.gradle.category\":\"platform\"" to "\"org.gradle.category\":\"library\"",
            "\"org.gradle.usage\":\"java-api\"" to "\"org.gradle.usage\":\"java-runtime\"",
            "\"org.gradle.usage\":\"java-api\"" to
                "\"unexpected\":\"value\",\"org.gradle.usage\":\"java-api\"",
        ).forEach { (old, new) ->
            withFixture { fixture ->
                fixture.replaceBomModule(old, new)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
        withFixture { fixture ->
            fixture.addBomPomConstraintScope()
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.addDuplicateBomPomConstraintScopes()
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.addDuplicateBomDirectDependencyContainers()
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
        withFixture { fixture ->
            fixture.replaceBom("<modelVersion>4.0.0</modelVersion>", "<modelVersion>3.0.0</modelVersion>")
            assertFailsWith<IllegalStateException> { fixture.verify() }
        }
    }

    @Test
    fun `project path leakage fails closed`() = withFixture { fixture ->
        fixture.replace(
            "jvm",
            "</project>",
            "<!-- ${fixture.root.absolutePath} --></project>",
        )
        val failure = assertFailsWith<IllegalStateException> { fixture.verify() }
        assertTrue(failure.message.orEmpty().contains("leaks the project path"))
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("facade-publication-contract").toFile()
        try {
            block(Fixture(root))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun assertDuplicateRejected(fixture: Fixture) {
        val failure = assertFailsWith<IllegalStateException> { fixture.verify() }
        assertTrue(failure.message.orEmpty().contains("duplicate"))
    }

    private class Fixture(val root: File) {
        private val facade = root.resolve("facade")
        private val bom = root.resolve("bom")

        init {
            facadePublicationSpecs.forEach { spec ->
                facade.resolve(spec.publication).apply {
                    mkdirs()
                    resolve("pom-default.xml").writeText(facadePom(spec))
                    resolve("module.json").writeText(facadeModule(spec).toString())
                }
            }
            bom.mkdirs()
            bom.resolve("pom-default.xml").writeText(bomPom())
            bom.resolve("module.json").writeText(bomModule().toString())
        }

        fun verify() = verifyFacadePublicationContract(
            facade,
            bom,
            group,
            contractVersion,
            runtimeVersion,
            sdkVersion,
            kotlinVersion,
            root.absolutePath,
        )

        fun removeCoreDependency(publication: String) {
            val spec = spec(publication)
            mutate(pom(publication), dependency(group, spec.coreArtifact, contractVersion, spec.scope), "")
        }

        fun addDependency(publication: String, module: String, version: String) {
            val spec = spec(publication)
            mutate(
                pom(publication),
                "</dependencies>",
                dependency(group, module, version, spec.scope) + "</dependencies>",
            )
        }

        fun duplicatePomDependency(publication: String) {
            val spec = spec(publication)
            addDependency(publication, spec.coreArtifact, contractVersion)
        }

        fun duplicateModuleDependency(publication: String) {
            val dependency = moduleDependency(group, "codex-agent-core", contractVersion).toString()
            mutateFirst(
                facade.resolve(publication).resolve("module.json"),
                "\"dependencies\":[$dependency",
                "\"dependencies\":[$dependency,$dependency",
            )
        }

        fun addPomDependencyOptional(publication: String) {
            mutateFirst(
                pom(publication),
                "</dependency>",
                "<optional>true</optional></dependency>",
            )
        }

        fun emptyModuleFiles(publication: String) {
            val spec = spec(publication)
            val name = spec.variantNames.sorted().first()
            mutateFirst(
                facade.resolve(publication).resolve("module.json"),
                "\"files\":[${moduleFile(spec, name)}]",
                "\"files\":[]",
            )
        }

        fun wrongTypeModuleFiles(publication: String) {
            val spec = spec(publication)
            val name = spec.variantNames.sorted().first()
            mutateFirst(
                facade.resolve(publication).resolve("module.json"),
                "\"files\":[${moduleFile(spec, name)}]",
                "\"files\":{}",
            )
        }

        fun duplicateModuleVariant(publication: String, name: String) {
            val variant = localVariant(spec(publication), name).toString()
            mutateFirst(
                facade.resolve(publication).resolve("module.json"),
                "\"variants\":[",
                "\"variants\":[$variant,",
            )
        }

        fun replace(publication: String, old: String, new: String) = mutate(pom(publication), old, new)

        fun replaceModule(publication: String, old: String, new: String) =
            mutate(facade.resolve(publication).resolve("module.json"), old, new)

        fun replaceFacadeModule(old: String, new: String) = facadePublicationSpecs.forEach { spec ->
            val file = facade.resolve(spec.publication).resolve("module.json")
            if (old in file.readText()) mutateFirst(file, old, new)
        }

        fun replaceBom(old: String, new: String) = mutate(bom.resolve("pom-default.xml"), old, new)

        fun replaceBomModule(old: String, new: String) =
            mutateFirst(bom.resolve("module.json"), old, new)

        fun duplicateBomPomConstraint() {
            mutate(
                bom.resolve("pom-default.xml"),
                "</dependencies>",
                dependency(group, "codex-agent", sdkVersion, null) + "</dependencies>",
            )
        }

        fun duplicateBomModuleConstraint() {
            val constraint = moduleDependency(group, "codex-agent", sdkVersion).toString()
            mutateFirst(
                bom.resolve("module.json"),
                "\"dependencyConstraints\":[",
                "\"dependencyConstraints\":[$constraint,",
            )
        }

        fun duplicateBomVariant() {
            val variant = bomVariant("apiElements", "java-api").toString()
            mutateFirst(bom.resolve("module.json"), "\"variants\":[", "\"variants\":[$variant,")
        }

        fun addBomPomConstraintScope() {
            mutateFirst(
                bom.resolve("pom-default.xml"),
                "<artifactId>codex-agent</artifactId><version>$sdkVersion</version>",
                "<artifactId>codex-agent</artifactId><version>$sdkVersion</version><scope>compile</scope>",
            )
        }

        fun addDuplicateBomPomConstraintScopes() {
            mutateFirst(
                bom.resolve("pom-default.xml"),
                "<artifactId>codex-agent</artifactId><version>$sdkVersion</version>",
                "<artifactId>codex-agent</artifactId><version>$sdkVersion</version>" +
                    "<scope>compile</scope><scope>runtime</scope>",
            )
        }

        fun addDuplicateBomDirectDependencyContainers() {
            mutateFirst(
                bom.resolve("pom-default.xml"),
                "<dependencyManagement>",
                "<dependencies></dependencies><dependencies></dependencies><dependencyManagement>",
            )
        }

        private fun pom(publication: String) = facade.resolve(publication).resolve("pom-default.xml")

        private fun spec(publication: String) = facadePublicationSpecs.single { it.publication == publication }

        private fun mutate(file: File, old: String, new: String) {
            val contents = file.readText()
            check(old in contents) { "Fixture mutation source is missing: $old" }
            file.writeText(contents.replace(old, new))
        }

        private fun mutateFirst(file: File, old: String, new: String) {
            val contents = file.readText()
            check(old in contents) { "Fixture mutation source is missing: $old" }
            file.writeText(contents.replaceFirst(old, new))
        }
    }

    companion object {
        private const val group = "io.github.codex-agent-labs"
        private const val contractVersion = "1.2.3"
        private const val runtimeVersion = "2.3.4"
        private const val sdkVersion = "3.4.5"
        private const val kotlinVersion = "2.2.20"

        private fun facadePom(spec: FacadePublicationSpec): String {
            val dependencies = buildList {
                add(dependency(group, spec.coreArtifact, contractVersion, spec.scope))
                spec.standardModules.forEach { add(dependency("org.jetbrains.kotlin", it, kotlinVersion, spec.scope)) }
            }.joinToString("")
            val packaging = when (spec.publication) {
                "android" -> "<packaging>aar</packaging>"
                "kotlinMultiplatform", "jvm" -> ""
                else -> "<packaging>klib</packaging>"
            }
            return "<project><modelVersion>4.0.0</modelVersion><groupId>$group</groupId>" +
                "<artifactId>${spec.artifact}</artifactId><version>$sdkVersion</version>$packaging" +
                "<dependencies>$dependencies</dependencies></project>"
        }

        private fun dependency(group: String, module: String, version: String, scope: String?) =
            "<dependency><groupId>$group</groupId><artifactId>$module</artifactId>" +
                "<version>$version</version>" +
                (scope?.let { "<scope>$it</scope>" } ?: "") + "</dependency>"

        private fun facadeModule(spec: FacadePublicationSpec): JsonObject {
            val component = linkedMapOf<String, JsonElement>(
                "group" to string(group),
                "module" to string("codex-agent"),
                "version" to string(sdkVersion),
                "attributes" to obj("org.gradle.status" to string("release")),
            )
            if (spec.publication != "kotlinMultiplatform") {
                component["url"] = string("../../codex-agent/$sdkVersion/codex-agent-$sdkVersion.module")
            }
            val variants = if (spec.publication == "kotlinMultiplatform") {
                facadePublicationSpecs.flatMap { target -> target.variantNames.map { target to it } }
                    .sortedBy { it.second }
                    .map { (target, name) ->
                        if (target == spec) localVariant(spec, name) else availableAtVariant(target, name)
                    }
            } else {
                spec.variantNames.sorted().map { localVariant(spec, it) }
            }
            return obj(
                "formatVersion" to string("1.1"),
                "component" to JsonObject(component),
                "createdBy" to obj(),
                "variants" to JsonArray(variants),
            )
        }

        private fun localVariant(spec: FacadePublicationSpec, name: String): JsonObject {
            val sources = "Sources" in name
            val values = linkedMapOf<String, JsonElement>(
                "name" to string(name),
                "attributes" to attributes(spec, name),
            )
            if (!sources) values["dependencies"] = JsonArray(buildList {
                add(moduleDependency(group, "codex-agent-core", contractVersion))
                spec.standardModules.forEach {
                    add(moduleDependency(
                        "org.jetbrains.kotlin",
                        if (it.startsWith("kotlin-stdlib")) "kotlin-stdlib" else it,
                        kotlinVersion,
                    ))
                }
            })
            values["files"] = JsonArray(listOf(moduleFile(spec, name)))
            return JsonObject(values)
        }

        private fun moduleFile(spec: FacadePublicationSpec, name: String) =
            facadeVariantFileIdentity(spec, name, sdkVersion).let { identity -> obj(
                "name" to string(identity.first),
                "url" to string(identity.second),
                "size" to JsonPrimitive(1),
                "sha512" to string("5".repeat(128)),
                "sha256" to string("2".repeat(64)),
                "sha1" to string("1".repeat(40)),
                "md5" to string("d".repeat(32)),
            ) }

        private fun availableAtVariant(spec: FacadePublicationSpec, name: String) = obj(
            "name" to string(name),
            "attributes" to attributes(spec, name),
            "available-at" to obj(
                "url" to string("../../${spec.artifact}/$sdkVersion/${spec.artifact}-$sdkVersion.module"),
                "group" to string(group),
                "module" to string(spec.artifact),
                "version" to string(sdkVersion),
            ),
        )

        private fun moduleDependency(group: String, module: String, version: String) = obj(
            "group" to string(group),
            "module" to string(module),
            "version" to obj("requires" to string(version)),
        )

        private fun bomPom(): String {
            val constraints = bomConstraints().entries.joinToString("") { (module, version) ->
                dependency(group, module, version, null)
            }
            return "<project><modelVersion>4.0.0</modelVersion><groupId>$group</groupId>" +
                "<artifactId>codex-agent-bom</artifactId><version>$sdkVersion</version><packaging>pom</packaging>" +
                "<dependencyManagement><dependencies>$constraints</dependencies></dependencyManagement></project>"
        }

        private fun bomModule(): JsonObject {
            val constraints = JsonArray(bomConstraints().map { (module, version) ->
                obj(
                    "group" to string(group),
                    "module" to string(module),
                    "version" to obj("requires" to string(version)),
                )
            })
            return obj(
                "formatVersion" to string("1.1"),
                "component" to obj(
                    "group" to string(group),
                    "module" to string("codex-agent-bom"),
                    "version" to string(sdkVersion),
                    "attributes" to obj("org.gradle.status" to string("release")),
                ),
                "createdBy" to obj(),
                "variants" to JsonArray(listOf(
                    bomVariant("apiElements", "java-api", constraints),
                    bomVariant("runtimeElements", "java-runtime", constraints),
                )),
            )
        }

        private fun bomVariant(
            name: String,
            usage: String,
            constraints: JsonArray = JsonArray(bomConstraints().map { (module, version) ->
                moduleDependency(group, module, version)
            }),
        ) = obj(
            "name" to string(name),
            "attributes" to obj(
                "org.gradle.category" to string("platform"),
                "org.gradle.usage" to string(usage),
            ),
            "dependencyConstraints" to constraints,
        )

        private fun bomConstraints() = linkedMapOf(
            "codex-agent" to sdkVersion,
            "codex-agent-core" to contractVersion,
            "codex-agent-runtime-desktop" to runtimeVersion,
            "codex-agent-runtime-android" to sdkVersion,
            "codex-agent-runtime-ios" to sdkVersion,
        )

        private fun attributes(spec: FacadePublicationSpec, name: String) = JsonObject(
            facadeVariantAttributes(spec, name).mapValues { string(it.value) },
        )

        private fun obj(vararg values: Pair<String, JsonElement>) = JsonObject(linkedMapOf(*values))

        private fun string(value: String) = JsonPrimitive(value)
    }
}
