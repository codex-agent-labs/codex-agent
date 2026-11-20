import java.io.File
import java.nio.file.Files
import kotlin.metadata.ClassKind
import kotlin.metadata.isData
import kotlin.metadata.kind
import kotlin.metadata.jvm.KotlinClassMetadata
import kotlin.metadata.jvm.Metadata as metadataAnnotation
import kotlin.metadata.jvm.toJvmInternalName
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Classpath
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.jetbrains.org.objectweb.asm.AnnotationVisitor
import org.jetbrains.org.objectweb.asm.ClassReader
import org.jetbrains.org.objectweb.asm.ClassVisitor
import org.jetbrains.org.objectweb.asm.Opcodes
import javax.inject.Inject

private const val KOTLIN_METADATA_ANNOTATION_DESCRIPTOR = "Lkotlin/Metadata;"

@CacheableTask
abstract class DiscoverCrossLanguageApiTask @Inject constructor(
    private val execOperations: ExecOperations,
) : DefaultTask() {
    @get:Classpath
    abstract val toolClasspath: ConfigurableFileCollection

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeKlib: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val wasmKlib: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val jvmClasses: DirectoryProperty

    @get:Input
    abstract val markerAnnotation: Property<String>

    @get:Input
    abstract val allowedBoundaryTypes: org.gradle.api.provider.ListProperty<String>

    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun discover() {
        val output = reportFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val boundaryList = allowedBoundaryTypes.get()
        requireCrossLanguageUnique(
            boundaryList.map { it.trim().replace('/', '.') },
            "Allowed cross-language boundary type",
        )
        val boundaries = boundaryList.toSet()
        val marker = markerAnnotation.get()
        val nativeDirectory = nativeKlib.get().asFile
        val wasmDirectory = wasmKlib.get().asFile
        val jvmDirectory = jvmClasses.get().asFile
        val inputs = temporaryDir.resolve("inputs").apply { mkdirs() }
        val boundariesFile = inputs.resolve("boundaries.bin").apply {
            writeCrossLanguageStrings(boundaries)
        }
        val excludedTypesFile = inputs.resolve("excluded-types.bin").apply {
            writeCrossLanguageStrings(setOf("kotlinx.coroutines.CoroutineScope"))
        }
        val compilerFacts = readCompilerJvmClassFacts(jvmDirectory)
        val dataClassesFile = inputs.resolve("data-classes.bin").apply {
            writeCrossLanguageStrings(compilerFacts.dataClassNames)
        }
        val singletonObjectsFile = inputs.resolve("singleton-objects.bin").apply {
            writeCrossLanguageStrings(compilerFacts.singletonObjectNames)
        }
        val companionObjectsFile = inputs.resolve("companion-objects.bin").apply {
            writeCrossLanguageStrings(compilerFacts.companionObjectNames)
        }
        val compilerReport = temporaryDir.resolve("compiler-report.bin")
        Files.deleteIfExists(compilerReport.toPath())
        execOperations.javaexec {
            classpath(toolClasspath)
            mainClass.set("CrossLanguageApiDiscoveryCliKt")
            args(
                nativeDirectory.absolutePath,
                wasmDirectory.absolutePath,
                marker,
                boundariesFile.absolutePath,
                "io.github.codex_agent_labs.codexagent.agent.CodexBindingApiKotlinOnly",
                excludedTypesFile.absolutePath,
                dataClassesFile.absolutePath,
                singletonObjectsFile.absolutePath,
                companionObjectsFile.absolutePath,
                compilerReport.absolutePath,
            )
        }.rethrowFailure().assertNormalExitValue()
        check(compilerReport.isFile) { "Cross-language compiler report was not produced" }
        val report = compilerReport.readCrossLanguageApiReport()
        output.atomicWriteJson(report.toJson(nativeDirectory, wasmDirectory, jvmDirectory))
    }
}

@CacheableTask
abstract class VerifyCrossLanguageApiCoverageTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compiledTests: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val testResults: DirectoryProperty

    @get:Input
    abstract val kotlinCompilerVersion: Property<String>

    @get:Input
    abstract val canonicalTestTask: Property<String>

    @get:OutputFile
    abstract val receiptFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = receiptFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val report = apiReport.get().asFile
        val classes = compiledTests.get().asFile
        val results = testResults.get().asFile
        val capabilityKeys = readCrossLanguageApiMemberKeys(report)
        val claims = readCoveredApiClaims(classes)
        val testResults = readCanonicalTestResults(results)
        val coverage = verifyCrossLanguageApiCoverage(capabilityKeys, claims, testResults)
        output.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2))
            put("result", JsonPrimitive("passed"))
            put("kotlinCompilerVersion", JsonPrimitive(kotlinCompilerVersion.get()))
            put("canonicalTestTask", JsonPrimitive(canonicalTestTask.get()))
            put("apiReportSha256", JsonPrimitive(report.releaseDigest()))
            put("compiledTestsSha256", JsonPrimitive(classes.crossLanguageTreeDigest()))
            put("testResultsSha256", JsonPrimitive(results.crossLanguageTreeDigest()))
            put("capabilities", coverage.memberKeys.toJsonArray())
            put("claims", buildJsonArray {
                coverage.claims.forEach { claim ->
                    add(buildJsonObject {
                        put("testId", JsonPrimitive(claim.testId))
                        put("capabilities", claim.memberKeys.sorted().toJsonArray())
                    })
                }
            })
        })
    }
}

private fun CrossLanguageApiReport.toJson(
    nativeKlib: File,
    wasmKlib: File,
    jvmClasses: File,
): JsonObject = buildJsonObject {
    put("schema", JsonPrimitive(2))
    put("libraryUniqueName", JsonPrimitive(libraryUniqueName))
    put("markerAnnotation", JsonPrimitive(markerAnnotation))
    put("signatureVersion", JsonPrimitive(signatureVersion))
    put("boundaryTypes", boundaryTypes.toJsonArray())
    put("memberExclusionAnnotation", JsonPrimitive(checkNotNull(memberExclusionAnnotation)))
    put("excludedReachableTypes", excludedReachableTypes.toJsonArray())
    put("excludedMemberKeys", excludedMemberKeys.toJsonArray())
    put("dataClassMetadataAvailable", JsonPrimitive(dataClassMetadataAvailable))
    put("dataClassNames", dataClassNames.toJsonArray())
    put("owners", buildJsonArray {
        owners.forEach { owner ->
            add(buildJsonObject {
                put("name", JsonPrimitive(owner.name))
                put("capabilities", owner.capabilityKeys.toJsonArray())
            })
        }
    })
    put("targets", buildJsonArray {
        add(targetRecord("native", nativeKlib))
        add(targetRecord("wasm", wasmKlib))
        add(targetRecord("jvm-classes", jvmClasses))
    })
}

private fun targetRecord(kind: String, directory: File): JsonObject = buildJsonObject {
    put("kind", JsonPrimitive(kind))
    put("sha256", JsonPrimitive(directory.crossLanguageTreeDigest()))
}

private fun Iterable<String>.toJsonArray(): JsonArray = buildJsonArray {
    this@toJsonArray.forEach { add(JsonPrimitive(it)) }
}

private fun requireCrossLanguageUnique(values: List<String>, label: String) {
    check(values.none(String::isBlank)) { "$label is blank" }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label identities are duplicated: $duplicates" }
}

internal data class CompilerJvmClassFacts(
    val dataClassNames: Set<String>,
    val singletonObjectNames: Set<String>,
    val companionObjectNames: Set<String>,
)

internal fun readCompilerDataClassNames(classesDirectory: File): Set<String> =
    readCompilerJvmClassFacts(classesDirectory).dataClassNames

internal fun readCompilerJvmClassFacts(classesDirectory: File): CompilerJvmClassFacts {
    check(classesDirectory.isDirectory) { "JVM compiler classes directory is missing: $classesDirectory" }
    val facts = classesDirectory.walkTopDown()
        .onEnter { directory ->
            check(!Files.isSymbolicLink(directory.toPath())) { "JVM compiler classes contain a symlink: $directory" }
            true
        }
        .filter { file ->
            check(!Files.isSymbolicLink(file.toPath())) { "JVM compiler classes contain a symlink: $file" }
            file.isFile && file.extension == "class"
        }
        .sortedBy { it.relativeTo(classesDirectory).invariantSeparatorsPath }
        .mapNotNull { readCompilerJvmClassFact(it) }
        .toList()
    requireCrossLanguageUnique(facts.map(CompilerJvmClassFact::name), "Compiler-derived JVM class")
    val dataClasses = facts.filter(CompilerJvmClassFact::isData).map(CompilerJvmClassFact::name)
    val singletonObjects = facts.filter { it.kind == ClassKind.OBJECT }.map(CompilerJvmClassFact::name)
    val companionObjects = facts.filter { it.kind == ClassKind.COMPANION_OBJECT }.map(CompilerJvmClassFact::name)
    listOf(
        "data class" to dataClasses,
        "singleton object" to singletonObjects,
        "companion object" to companionObjects,
    ).forEach { (label, names) -> requireCrossLanguageUnique(names, "Compiler-derived $label") }
    check(singletonObjects.intersect(companionObjects.toSet()).isEmpty()) {
        "Compiler-derived singleton and companion object identities overlap"
    }
    return CompilerJvmClassFacts(dataClasses.toSet(), singletonObjects.toSet(), companionObjects.toSet())
}

private data class CompilerJvmClassFact(
    val name: String,
    val kind: ClassKind,
    val isData: Boolean,
)

private fun readCompilerJvmClassFact(classFile: File): CompilerJvmClassFact? {
    val reader = ClassReader(classFile.readBytes())
    var header: KotlinMetadataHeader? = null
    reader.accept(object : ClassVisitor(Opcodes.ASM9) {
        override fun visitAnnotation(descriptor: String, visible: Boolean): AnnotationVisitor? =
            if (descriptor == KOTLIN_METADATA_ANNOTATION_DESCRIPTOR) {
                check(header == null) { "Duplicate kotlin.Metadata annotation: ${reader.className}" }
                KotlinMetadataHeader().also { header = it }
            } else {
                null
            }
    }, ClassReader.SKIP_CODE or ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES)
    val metadata = header?.build() ?: return null
    val parsed = KotlinClassMetadata.readStrict(metadata) as? KotlinClassMetadata.Class ?: return null
    val kmClass = parsed.kmClass
    val internalName = kmClass.name.toJvmInternalName()
    check(internalName == reader.className) {
        "Kotlin metadata/JVM class-name mismatch: $internalName != ${reader.className}"
    }
    return CompilerJvmClassFact(kmClass.name, kmClass.kind, kmClass.isData)
}

private class KotlinMetadataHeader : AnnotationVisitor(Opcodes.ASM9) {
    private var kind: Int? = null
    private var metadataVersion: IntArray? = null
    private val data1 = mutableListOf<String>()
    private val data2 = mutableListOf<String>()
    private var extraString: String? = null
    private var packageName: String? = null
    private var extraInt: Int? = null

    override fun visit(name: String?, value: Any?) {
        when (name) {
            "k" -> kind = value as Int
            "mv" -> metadataVersion = value as IntArray
            "xs" -> extraString = value as String
            "pn" -> packageName = value as String
            "xi" -> extraInt = value as Int
        }
    }

    override fun visitArray(name: String?): AnnotationVisitor? {
        val destination = when (name) {
            "d1" -> data1
            "d2" -> data2
            else -> return null
        }
        return object : AnnotationVisitor(Opcodes.ASM9) {
            override fun visit(name: String?, value: Any?) {
                destination += value as String
            }
        }
    }

    fun build(): kotlin.Metadata = metadataAnnotation(
        kind = kind,
        metadataVersion = metadataVersion,
        data1 = data1.toTypedArray(),
        data2 = data2.toTypedArray(),
        extraString = extraString,
        packageName = packageName,
        extraInt = extraInt,
    )
}
