import java.io.ByteArrayInputStream
import java.io.File
import java.util.zip.ZipInputStream
import kotlin.metadata.ClassKind
import kotlin.metadata.KmClass
import kotlin.metadata.KmClassifier
import kotlin.metadata.KmFunction
import kotlin.metadata.KmType
import kotlin.metadata.KmTypeParameter
import kotlin.metadata.KmValueParameter
import kotlin.metadata.Visibility
import kotlin.metadata.declaresDefaultValue
import kotlin.metadata.isDefinitelyNonNull
import kotlin.metadata.isNullable
import kotlin.metadata.isSuspend
import kotlin.metadata.isVar
import kotlin.metadata.kind
import kotlin.metadata.jvm.KotlinClassMetadata
import kotlin.metadata.jvm.fieldSignature
import kotlin.metadata.jvm.getterSignature
import kotlin.metadata.jvm.signature
import kotlin.metadata.jvm.toJvmInternalName
import kotlin.metadata.visibility
import org.jetbrains.org.objectweb.asm.AnnotationVisitor
import org.jetbrains.org.objectweb.asm.ClassReader
import org.jetbrains.org.objectweb.asm.ClassVisitor
import org.jetbrains.org.objectweb.asm.FieldVisitor
import org.jetbrains.org.objectweb.asm.MethodVisitor
import org.jetbrains.org.objectweb.asm.Opcodes
import org.jetbrains.org.objectweb.asm.Type

internal enum class JavaJvmSymbolKind(val id: String) { METHOD("method"), FIELD("field") }

internal data class JavaJvmSymbol(
    val kind: JavaJvmSymbolKind,
    val owner: String,
    val name: String,
    val descriptor: String,
    val genericSignature: String? = null,
) {
    init {
        check(owner.isNotBlank() && name.isNotBlank() && descriptor.isNotBlank() && '*' !in owner + name + descriptor) {
            "Java JVM symbol is blank or wildcard"
        }
        when (kind) {
            JavaJvmSymbolKind.METHOD -> Type.getMethodType(descriptor)
            JavaJvmSymbolKind.FIELD -> Type.getType(descriptor)
        }
    }

    val id: String
        get() = (when (kind) {
            JavaJvmSymbolKind.METHOD -> "method:$owner#$name$descriptor"
            JavaJvmSymbolKind.FIELD -> "field:$owner#$name:$descriptor"
        }) + "|genericSha256=${genericSignature?.byteInputStream()?.releaseDigest() ?: "none"}"
}

internal sealed interface JavaBindingExceptionalAlias {
    val capabilityKey: String
}

internal data class JavaSuspendBindingAlias(
    override val capabilityKey: String,
    val futureMethod: JavaJvmSymbol,
) : JavaBindingExceptionalAlias

internal data class JavaStateFlowBindingAlias(
    override val capabilityKey: String,
    val currentMethod: JavaJvmSymbol,
    val observeMethod: JavaJvmSymbol,
) : JavaBindingExceptionalAlias

internal data class JavaHostFactoryBindingAlias(
    override val capabilityKey: String,
    val desktopFactory: JavaJvmSymbol,
    val androidFactory: JavaJvmSymbol,
) : JavaBindingExceptionalAlias

internal data class JavaStaticBindingAlias(
    override val capabilityKey: String,
    val staticMethod: JavaJvmSymbol,
) : JavaBindingExceptionalAlias

internal data class JavaBindingArtifactDigests(
    val coreJvmJarSha256: String,
    val coreAndroidAarSha256: String,
    val desktopRuntimeJarSha256: String,
    val androidRuntimeAarSha256: String,
)

internal data class JavaBindingCapabilityClaim(
    val capabilityKey: String,
    val publicSymbols: List<String>,
    val proofKind: JavaBindingProofKind = JavaBindingProofKind.STRUCTURAL,
    val testReferenceTargets: List<JavaBindingMethodTarget> = emptyList(),
)

internal enum class JavaBindingProofKind { STRUCTURAL, TEST_REFERENCED, HOST_FACTORY }

internal data class JavaBindingMethodTarget(
    val owner: String,
    val name: String,
    val descriptors: List<String>,
) {
    init {
        check(owner.isNotBlank() && name.isNotBlank() && '*' !in owner + name && descriptors.isNotEmpty()) {
            "Java binding test-reference target is blank or wildcard"
        }
        requireUniqueExactJavaValues(descriptors, "Java binding test-reference descriptor")
        descriptors.forEach(Type::getMethodType)
    }
}

internal data class CrossLanguageJavaBindingStructuralEvidence(
    val digests: JavaBindingArtifactDigests,
    val capabilityClaims: List<JavaBindingCapabilityClaim>,
) {
    val publicSymbols: List<String> = capabilityClaims.flatMap(JavaBindingCapabilityClaim::publicSymbols).distinct().sorted()
}

internal fun deriveCrossLanguageJavaBindingStructuralEvidence(
    canonicalMemberKeys: List<String>,
    coreJvmJar: File,
    coreAndroidAar: File,
    desktopRuntimeJar: File,
    androidRuntimeAar: File,
    exceptionalAliases: List<JavaBindingExceptionalAlias>,
): CrossLanguageJavaBindingStructuralEvidence {
    requireUniqueExactJavaValues(canonicalMemberKeys, "Canonical Java capability")
    val members = canonicalMemberKeys.map(::parseJavaCanonicalMember)
    val exceptions = members.filter { it.exceptionKind != null }
    val ordinary = members - exceptions.toSet()

    val aliasesByKey = exceptionalAliases.groupBy(JavaBindingExceptionalAlias::capabilityKey)
    check(aliasesByKey.values.none { it.size != 1 }) {
        "Duplicate Java exceptional aliases: ${aliasesByKey.filterValues { it.size != 1 }.keys.sorted()}"
    }
    val expectedExceptionKeys = exceptions.map(JavaCanonicalMember::key).toSet()
    val aliasKeys = aliasesByKey.keys
    check(expectedExceptionKeys == aliasKeys) {
        "Java exceptional aliases are not exact: missing=${(expectedExceptionKeys - aliasKeys).sorted()}, " +
            "stale=${(aliasKeys - expectedExceptionKeys).sorted()}"
    }
    exceptions.forEach { member ->
        val alias = aliasesByKey.getValue(member.key).single()
        check(checkNotNull(member.exceptionKind).accepts(alias)) {
            "Wrong Java exceptional alias kind for ${member.key}: ${alias::class.simpleName}"
        }
    }

    val coreJvm = readJavaJar(coreJvmJar, "core JVM JAR")
    val coreAndroid = readJavaAar(coreAndroidAar, "core Android AAR")
    val desktopRuntime = readJavaJar(desktopRuntimeJar, "Desktop runtime JAR")
    val androidRuntime = readJavaAar(androidRuntimeAar, "Android runtime AAR")
    members.forEach { member ->
        coreJvm.index.requireCanonicalDeclaration(member)
        coreAndroid.index.requireCanonicalDeclaration(member)
    }

    val claims = buildList {
        ordinary.forEach { member ->
            val jvm = coreJvm.index.resolveOrdinary(member)
            val android = coreAndroid.index.resolveOrdinary(member)
            check(jvm == android) {
                "Java ordinary member differs between core JVM JAR and Android AAR: ${member.key}: " +
                    "${jvm.map(JavaJvmSymbol::id)} != ${android.map(JavaJvmSymbol::id)}"
            }
            add(JavaBindingCapabilityClaim(member.key, jvm.map(JavaJvmSymbol::id)))
        }
        exceptions.forEach { member ->
            val alias = aliasesByKey.getValue(member.key).single()
            val symbols = when (alias) {
                is JavaSuspendBindingAlias -> {
                    val jvm = coreJvm.index.requireFuture(alias.futureMethod, member)
                    val android = coreAndroid.index.requireFuture(alias.futureMethod, member)
                    requireCoreCounterpart(member.key, jvm, android)
                }
                is JavaStateFlowBindingAlias -> {
                    val jvm = coreJvm.index.requireStateProjection(alias, member)
                    val android = coreAndroid.index.requireStateProjection(alias, member)
                    requireCoreCounterpart(member.key, jvm, android)
                }
                is JavaHostFactoryBindingAlias -> {
                    listOf(
                        desktopRuntime.index.requireHostFactory(alias.desktopFactory, member.owner, "Desktop"),
                        androidRuntime.index.requireHostFactory(alias.androidFactory, member.owner, "Android"),
                    )
                }
                is JavaStaticBindingAlias -> {
                    val jvm = coreJvm.index.requireStaticProjection(alias.staticMethod, member)
                    val android = coreAndroid.index.requireStaticProjection(alias.staticMethod, member)
                    requireCoreCounterpart(member.key, jvm, android)
                }
            }
            val proofKind = when (alias) {
                is JavaHostFactoryBindingAlias -> JavaBindingProofKind.HOST_FACTORY
                else -> JavaBindingProofKind.TEST_REFERENCED
            }
            val targets = when (alias) {
                is JavaSuspendBindingAlias -> {
                    val jvm = coreJvm.index.requireFutureTestTarget(alias.futureMethod, member)
                    val android = coreAndroid.index.requireFutureTestTarget(alias.futureMethod, member)
                    check(jvm == android) { "Java Future default-overload family differs between core artifacts: ${member.key}" }
                    listOf(jvm)
                }
                is JavaStateFlowBindingAlias -> listOf(alias.currentMethod, alias.observeMethod).map { symbol ->
                    JavaBindingMethodTarget(symbol.owner, symbol.name, listOf(symbol.descriptor))
                }
                is JavaStaticBindingAlias -> {
                    val jvm = coreJvm.index.requireStaticTestTarget(alias.staticMethod, member)
                    val android = coreAndroid.index.requireStaticTestTarget(alias.staticMethod, member)
                    check(jvm == android) { "Java static default-overload family differs between core artifacts: ${member.key}" }
                    listOf(jvm)
                }
                is JavaHostFactoryBindingAlias -> emptyList()
            }.distinct().sortedWith(
                compareBy(JavaBindingMethodTarget::owner, JavaBindingMethodTarget::name),
            )
            add(JavaBindingCapabilityClaim(member.key, symbols.map(JavaJvmSymbol::id).sorted(), proofKind, targets))
        }
    }.sortedBy(JavaBindingCapabilityClaim::capabilityKey)

    val reusedSymbols = claims.flatMap { claim -> claim.publicSymbols.map { it to claim.capabilityKey } }
        .groupBy { it.first }.filterValues { records -> records.size != 1 }.keys.sorted()
    check(reusedSymbols.isEmpty()) {
        "Java public symbols are reused across capability claims: $reusedSymbols"
    }

    return CrossLanguageJavaBindingStructuralEvidence(
        JavaBindingArtifactDigests(
            coreJvm.sha256,
            coreAndroid.sha256,
            desktopRuntime.sha256,
            androidRuntime.sha256,
        ),
        claims,
    )
}

private fun requireCoreCounterpart(
    capability: String,
    jvm: List<JavaJvmSymbol>,
    android: List<JavaJvmSymbol>,
): List<JavaJvmSymbol> {
    check(jvm == android) {
        "Java projection differs between core JVM JAR and Android AAR: $capability: " +
            "${jvm.map(JavaJvmSymbol::id)} != ${android.map(JavaJvmSymbol::id)}"
    }
    return jvm
}

private enum class JavaExceptionKind {
    SUSPEND,
    STATE_FLOW,
    HOST_FACTORY,
    COMPANION_STATIC,
    ;

    fun accepts(alias: JavaBindingExceptionalAlias): Boolean = when (this) {
        SUSPEND -> alias is JavaSuspendBindingAlias
        STATE_FLOW -> alias is JavaStateFlowBindingAlias
        HOST_FACTORY -> alias is JavaHostFactoryBindingAlias
        COMPANION_STATIC -> alias is JavaStaticBindingAlias
    }
}

private data class JavaCanonicalParameter(
    val kind: String,
    val type: String,
    val hasDefault: Boolean,
    val isVararg: Boolean,
)

private data class JavaCanonicalMember(
    val key: String,
    val owner: String,
    val kind: String,
    val name: String,
    val returnType: String?,
    val parameters: List<JavaCanonicalParameter>,
    val propertyKind: String?,
    val propertyType: String?,
    val isSuspend: Boolean,
    val typeParameterBoundsIdentity: String,
    val exceptionKind: JavaExceptionKind?,
)

private fun parseJavaCanonicalMember(key: String): JavaCanonicalMember {
    val parts = key.split('|')
    check(parts.firstOrNull() == "common") { "Invalid canonical Java capability target: $key" }
    fun single(prefix: String): String = parts.filter { it.startsWith(prefix) }.singleOrNull()?.removePrefix(prefix)
        ?: error("Invalid canonical Java capability $prefix field: $key")
    val owner = single("owner=")
    val kind = single("kind=")
    check(kind in setOf("constructor", "function", "property", "enum-entry", "object")) {
        "Unsupported canonical Java capability kind $kind: $key"
    }
    val abiIdentity = single("abi=")
    val name = if (kind == "object") "INSTANCE" else abiIdentity.substringAfterLast('.', missingDelimiterValue = "")
    check(if (kind == "object") abiIdentity == owner else name.isNotBlank() && abiIdentity.removeSuffix(".$name") == owner) {
        "Canonical Java capability ABI identity mismatch: $key"
    }
    if (kind == "object") {
        check(parts.size == 5 && parts.last() == "null[0]") {
            "Canonical Java object ABI signature mismatch: $key"
        }
    }
    val abiSignatureStart = key.indexOf('|', key.indexOf("|abi=") + 5) + 1
    check(abiSignatureStart > 0) { "Invalid canonical Java ABI signature: $key" }
    val abiSignatureEnd = listOf("|return=", "|propertyKind=", "|type=", "|suspend=", "|parameters=")
        .map { key.indexOf(it, abiSignatureStart) }
        .filter { it >= 0 }
        .minOrNull() ?: key.length
    val typeParameterBoundsIdentity = key.substring(abiSignatureStart, abiSignatureEnd)
        .parseJavaCanonicalTypeParameterBounds()
    val suspend = parts.singleOrNull { it.startsWith("suspend=") } == "suspend=true"
    val returnType = parts.singleOrNull { it.startsWith("return=") }?.removePrefix("return=")
    val propertyKind = parts.singleOrNull { it.startsWith("propertyKind=") }?.removePrefix("propertyKind=")
    val propertyType = parts.singleOrNull { it.startsWith("type=") }?.removePrefix("type=")
    val parameters = parts.singleOrNull { it.startsWith("parameters=") }?.removePrefix("parameters=")
        ?.parseJavaCanonicalParameters().orEmpty()
    val stateFlow = parts.singleOrNull { it.startsWith("type=") }
        ?.startsWith("type=kotlinx.coroutines.flow/StateFlow<") == true
    check(!suspend || kind == "function") { "Only functions may be suspend Java exceptions: $key" }
    check(!stateFlow || kind == "property") { "Only properties may be StateFlow Java exceptions: $key" }
    check(kind == "function" || typeParameterBoundsIdentity.isEmpty()) {
        "Only functions may declare canonical Java type-parameter bounds: $key"
    }
    when (kind) {
        "constructor", "function" -> check(returnType != null && propertyKind == null && propertyType == null) {
            "Invalid canonical Java function semantics: $key"
        }
        "property" -> check(returnType == null && propertyKind != null && propertyType != null && parameters.isEmpty()) {
            "Invalid canonical Java property semantics: $key"
        }
        "enum-entry" -> check(returnType == null && propertyKind == null && propertyType == null && parameters.isEmpty()) {
            "Invalid canonical Java enum-entry semantics: $key"
        }
        "object" -> check(returnType == null && propertyKind == null && propertyType == null && parameters.isEmpty()) {
            "Invalid canonical Java object semantics: $key"
        }
    }
    val hostFactory = owner.substringAfterLast('/') == "CodexHost" && kind == "constructor"
    val companionStatic = owner.endsWith(".Companion") && kind == "function"
    val exceptionKinds = listOfNotNull(
        JavaExceptionKind.SUSPEND.takeIf { suspend },
        JavaExceptionKind.STATE_FLOW.takeIf { stateFlow },
        JavaExceptionKind.HOST_FACTORY.takeIf { hostFactory },
        JavaExceptionKind.COMPANION_STATIC.takeIf { companionStatic },
    )
    check(exceptionKinds.size <= 1) { "Overlapping Java exception categories: $key" }
    return JavaCanonicalMember(
        key,
        owner,
        kind,
        name,
        returnType,
        parameters,
        propertyKind,
        propertyType,
        suspend,
        typeParameterBoundsIdentity,
        exceptionKinds.singleOrNull(),
    )
}

private fun String.parseJavaCanonicalTypeParameterBounds(): String {
    val open = indexOf('{')
    if (open < 0) {
        check('}' !in this) { "Invalid canonical Java ABI type-parameter bounds: $this" }
        return ""
    }
    val close = indexOf('}', open + 1)
    check(close > open && indexOf('{', open + 1) < 0 && indexOf('}', close + 1) < 0) {
        "Invalid canonical Java ABI type-parameter bounds: $this"
    }
    return substring(open + 1, close)
}

private fun String.parseJavaCanonicalParameters(): List<JavaCanonicalParameter> {
    check(startsWith('[') && endsWith(']')) { "Invalid canonical Java parameter inventory: $this" }
    val body = substring(1, length - 1)
    if (body.isEmpty()) return emptyList()
    return body.splitJavaCanonicalTopLevel().map { parameter ->
        val kindEnd = parameter.indexOf(':')
        val defaultStart = parameter.lastIndexOf(":default=")
        val varargStart = parameter.lastIndexOf(":vararg=")
        check(kindEnd > 0 && defaultStart > kindEnd && varargStart > defaultStart) {
            "Invalid canonical Java parameter: $parameter"
        }
        JavaCanonicalParameter(
            kind = parameter.substring(0, kindEnd),
            type = parameter.substring(kindEnd + 1, defaultStart),
            hasDefault = parameter.substring(defaultStart + 9, varargStart).toStrictBoolean("default", parameter),
            isVararg = parameter.substring(varargStart + 8).toStrictBoolean("vararg", parameter),
        )
    }
}

private fun String.splitJavaCanonicalTopLevel(): List<String> {
    var depth = 0
    var start = 0
    return buildList {
        this@splitJavaCanonicalTopLevel.forEachIndexed { index, character ->
            when (character) {
                '<' -> depth++
                '>' -> depth--
                ',' -> if (depth == 0) {
                    add(this@splitJavaCanonicalTopLevel.substring(start, index))
                    start = index + 1
                }
            }
            check(depth >= 0) { "Unbalanced canonical Java type: ${this@splitJavaCanonicalTopLevel}" }
        }
        check(depth == 0) { "Unbalanced canonical Java type: ${this@splitJavaCanonicalTopLevel}" }
        add(this@splitJavaCanonicalTopLevel.substring(start))
    }
}

private fun String.toStrictBoolean(label: String, parameter: String): Boolean = when (this) {
    "true" -> true
    "false" -> false
    else -> error("Invalid canonical Java $label flag: $parameter")
}

private fun JavaCanonicalMember.matchesConstructor(valueParameters: List<KmValueParameter>): Boolean =
    kind == "constructor" && returnType == owner && matchesParameters(valueParameters)

private fun JavaCanonicalMember.matchesFunction(
    actualReturnType: KmType,
    valueParameters: List<KmValueParameter>,
    actualSuspend: Boolean,
    actualTypeParameters: List<KmTypeParameter>,
): Boolean = kind == "function" && isSuspend == actualSuspend &&
    returnType == actualReturnType.renderCanonicalKmType(normalizeUnitReturn = true) &&
    typeParameterBoundsIdentity == actualTypeParameters.renderCompilerAbiTypeParameterBounds() &&
    matchesParameters(valueParameters)

private fun JavaCanonicalMember.matchesProperty(actualType: KmType, actualVar: Boolean): Boolean =
    kind == "property" && propertyKind == (if (actualVar) "VAR" else "VAL") &&
        propertyType == actualType.renderCanonicalKmType()

private fun JavaCanonicalMember.matchesParameters(actual: List<KmValueParameter>): Boolean =
    parameters.size == actual.size && parameters.zip(actual).all { (expected, value) ->
        expected.kind == "REGULAR" &&
            expected.type == value.type.renderCanonicalKmType() &&
            expected.hasDefault == value.declaresDefaultValue &&
            expected.isVararg == (value.varargElementType != null)
    }

private fun KmType.renderCanonicalKmType(
    normalizeUnitReturn: Boolean = false,
    typeParameterBounds: Map<Int, KmType> = emptyMap(),
    resolvingTypeParameters: Set<Int> = emptySet(),
    resolveTypeParameters: Boolean = false,
): String {
    check(abbreviatedType == null && outerType == null && flexibleTypeUpperBound == null) {
        "Unsupported flexible, abbreviated, or outer Kotlin metadata type"
    }
    val classifierValue = classifier
    if (classifierValue is KmClassifier.TypeParameter && resolveTypeParameters) {
        check(classifierValue.id !in resolvingTypeParameters && arguments.isEmpty()) {
            "Unsupported recursive or parameterized Kotlin metadata type parameter"
        }
        val bound = typeParameterBounds[classifierValue.id]?.renderCanonicalKmType(
            typeParameterBounds = typeParameterBounds,
            resolvingTypeParameters = resolvingTypeParameters + classifierValue.id,
            resolveTypeParameters = true,
        ) ?: "kotlin/Any?"
        val classifierAndArguments = bound.removeSuffix("?").removeSuffix("!!")
        val nullability = when {
            isNullable -> "?"
            isDefinitelyNonNull -> "!!"
            else -> bound.removePrefix(classifierAndArguments)
        }
        return classifierAndArguments + nullability
    }
    val classifierName = when (val value = classifierValue) {
        is KmClassifier.Class -> value.name.toCanonicalClassifierName()
        is KmClassifier.TypeAlias -> value.name.toCanonicalClassifierName()
        is KmClassifier.TypeParameter -> "^A${value.id + 1}"
    }
    val renderedArguments = arguments.joinToString(separator = ",", prefix = "<", postfix = ">") { argument ->
        val type = argument.type
        if (type == null) {
            "*"
        } else {
            val variance = checkNotNull(argument.variance)
            "${variance.name}:${type.renderCanonicalKmType(
                typeParameterBounds = typeParameterBounds,
                resolvingTypeParameters = resolvingTypeParameters,
                resolveTypeParameters = resolveTypeParameters,
            )}"
        }
    }.takeIf { arguments.isNotEmpty() }.orEmpty()
    val nullability = when {
        isNullable -> "?"
        isDefinitelyNonNull -> "!!"
        normalizeUnitReturn && classifierName == "kotlin/Unit" && arguments.isEmpty() -> ""
        classifierValue is KmClassifier.TypeParameter -> ""
        else -> "!!"
    }
    return classifierName + renderedArguments + nullability
}

private fun List<KmTypeParameter>.renderCompilerAbiTypeParameterBounds(): String {
    val tags = mapIndexed { index, parameter -> parameter.id to "0:$index" }.toMap()
    check(tags.size == size) { "Duplicate Kotlin metadata type-parameter id" }
    return mapIndexed { index, parameter ->
        val bounds = parameter.upperBounds.joinToString("&") { it.renderCompilerAbiType(tags) }.ifEmpty { "kotlin.Any?" }
        "$index§<$bounds>"
    }.joinToString(";")
}

private fun KmType.renderCompilerAbiType(typeParameterTags: Map<Int, String>): String {
    check(abbreviatedType == null && outerType == null && flexibleTypeUpperBound == null) {
        "Unsupported flexible, abbreviated, or outer Kotlin metadata type bound"
    }
    val classifierName = when (val value = classifier) {
        is KmClassifier.Class -> value.name.replace('/', '.')
        is KmClassifier.TypeAlias -> value.name.replace('/', '.')
        is KmClassifier.TypeParameter -> checkNotNull(typeParameterTags[value.id]) {
            "Kotlin metadata type bound references an out-of-scope type parameter ${value.id}"
        }
    }
    val renderedArguments = arguments.joinToString(separator = ",", prefix = "<", postfix = ">") { argument ->
        val type = argument.type
        if (type == null) {
            "*"
        } else {
            val variance = checkNotNull(argument.variance)
            val prefix = when (variance.name) {
                "INVARIANT" -> ""
                "IN" -> "in|"
                "OUT" -> "out|"
                else -> error("Unsupported Kotlin metadata type-bound variance: $variance")
            }
            prefix + type.renderCompilerAbiType(typeParameterTags)
        }
    }.takeIf { arguments.isNotEmpty() }.orEmpty()
    val nullability = when {
        isNullable -> "?"
        isDefinitelyNonNull -> "!!"
        else -> ""
    }
    return classifierName + renderedArguments + nullability
}

internal fun String.toCanonicalClassifierName(): String {
    val classSeparator = lastIndexOf('/')
    if (classSeparator < 0) return this
    return substring(0, classSeparator).replace('/', '.') + substring(classSeparator)
}

private enum class JavaVisibleVariance { INVARIANT, IN, OUT, STAR }

private data class JavaVisibleTypeArgument(
    val variance: JavaVisibleVariance,
    val type: JavaVisibleType? = null,
    val acceptsCompilerParameterOut: Boolean = false,
)

private data class JavaVisibleType(
    val classifier: String,
    val arguments: List<JavaVisibleTypeArgument> = emptyList(),
)

private data class JavaVisibleMethod(
    val parameters: List<JavaVisibleType>,
    val returnType: JavaVisibleType,
)

private data class CanonicalJavaType(
    val classifier: String,
    val arguments: List<Pair<JavaVisibleVariance, CanonicalJavaType?>>,
    val nullable: Boolean,
) {
    fun stateFlowElement(capability: String): CanonicalJavaType {
        check(classifier == "kotlinx.coroutines.flow/StateFlow" && arguments.size == 1 &&
            arguments.single().first == JavaVisibleVariance.INVARIANT && arguments.single().second != null) {
            "Canonical StateFlow capability has an invalid element type: $capability"
        }
        return checkNotNull(arguments.single().second)
    }

    fun toJavaVisibleType(topLevelProjection: Boolean, genericContext: Boolean): JavaVisibleType {
        if (nullable && topLevelProjection) {
            return JavaVisibleType(
                "java/util/Optional",
                listOf(JavaVisibleTypeArgument(
                    JavaVisibleVariance.INVARIANT,
                    copy(nullable = false).toJavaVisibleType(topLevelProjection = false, genericContext = true),
                )),
            )
        }
        val primitives = mapOf(
            "kotlin/Boolean" to ("Z" to "java/lang/Boolean"),
            "kotlin/Byte" to ("B" to "java/lang/Byte"),
            "kotlin/Char" to ("C" to "java/lang/Character"),
            "kotlin/Short" to ("S" to "java/lang/Short"),
            "kotlin/Int" to ("I" to "java/lang/Integer"),
            "kotlin/Long" to ("J" to "java/lang/Long"),
            "kotlin/Float" to ("F" to "java/lang/Float"),
            "kotlin/Double" to ("D" to "java/lang/Double"),
        )
        primitives[classifier]?.let { (descriptor, boxed) ->
            check(arguments.isEmpty()) { "Canonical primitive type has arguments: $classifier" }
            return JavaVisibleType(if (genericContext) boxed else descriptor)
        }
        val javaClassifier = when (classifier) {
            "kotlin/Unit" -> if (genericContext) "java/lang/Void" else "V"
            "kotlin/Any" -> "java/lang/Object"
            "kotlin/String" -> "java/lang/String"
            "kotlin.collections/List" -> "java/util/List"
            "kotlin.collections/MutableList" -> "java/util/List"
            "kotlin.collections/Set" -> "java/util/Set"
            "kotlin.collections/MutableSet" -> "java/util/Set"
            "kotlin.collections/Map" -> "java/util/Map"
            "kotlin.collections/MutableMap" -> "java/util/Map"
            else -> canonicalOwnerToJvmInternalName(classifier)
        }
        return JavaVisibleType(javaClassifier, arguments.map { (variance, type) ->
            JavaVisibleTypeArgument(
                variance,
                type?.toJavaVisibleType(topLevelProjection = false, genericContext = true),
            )
        })
    }

    fun toOrdinaryJavaVisibleType(
        position: JavaOrdinaryTypePosition,
        parameterProjection: Boolean = position == JavaOrdinaryTypePosition.VALUE_PARAMETER,
    ): JavaVisibleType {
        val genericContext = position == JavaOrdinaryTypePosition.GENERIC
        val primitives = mapOf(
            "kotlin/Boolean" to ("Z" to "java/lang/Boolean"),
            "kotlin/Byte" to ("B" to "java/lang/Byte"),
            "kotlin/Char" to ("C" to "java/lang/Character"),
            "kotlin/Short" to ("S" to "java/lang/Short"),
            "kotlin/Int" to ("I" to "java/lang/Integer"),
            "kotlin/Long" to ("J" to "java/lang/Long"),
            "kotlin/Float" to ("F" to "java/lang/Float"),
            "kotlin/Double" to ("D" to "java/lang/Double"),
        )
        primitives[classifier]?.let { (descriptor, boxed) ->
            check(arguments.isEmpty()) { "Canonical primitive type has arguments: $classifier" }
            return JavaVisibleType(if (genericContext || nullable) boxed else descriptor)
        }
        if (classifier == "kotlin/Array") {
            check(arguments.size == 1 && arguments.single().second != null) {
                "Canonical Array type has an invalid element: $this"
            }
            return JavaVisibleType(
                "[",
                listOf(JavaVisibleTypeArgument(
                    JavaVisibleVariance.INVARIANT,
                    checkNotNull(arguments.single().second).toOrdinaryJavaVisibleType(
                        JavaOrdinaryTypePosition.GENERIC,
                        parameterProjection,
                    ),
                )),
            )
        }
        val primitiveArrays = mapOf(
            "kotlin/BooleanArray" to "Z",
            "kotlin/ByteArray" to "B",
            "kotlin/CharArray" to "C",
            "kotlin/ShortArray" to "S",
            "kotlin/IntArray" to "I",
            "kotlin/LongArray" to "J",
            "kotlin/FloatArray" to "F",
            "kotlin/DoubleArray" to "D",
        )
        primitiveArrays[classifier]?.let { element ->
            check(arguments.isEmpty()) { "Canonical primitive-array type has arguments: $classifier" }
            return JavaVisibleType(
                "[",
                listOf(JavaVisibleTypeArgument(JavaVisibleVariance.INVARIANT, JavaVisibleType(element))),
            )
        }
        val javaClassifier = when (classifier) {
            "kotlin/Unit" -> if (position == JavaOrdinaryTypePosition.RETURN && !nullable) "V" else "kotlin/Unit"
            "kotlin/Nothing" -> "java/lang/Void"
            "kotlin/Any" -> "java/lang/Object"
            "kotlin/String" -> "java/lang/String"
            "kotlin.collections/Iterable" -> "java/lang/Iterable"
            "kotlin.collections/Collection", "kotlin.collections/MutableCollection" -> "java/util/Collection"
            "kotlin.collections/List", "kotlin.collections/MutableList" -> "java/util/List"
            "kotlin.collections/Set", "kotlin.collections/MutableSet" -> "java/util/Set"
            "kotlin.collections/Map", "kotlin.collections/MutableMap" -> "java/util/Map"
            "kotlin.collections/Map.Entry", "kotlin.collections/MutableMap.MutableEntry" -> "java/util/Map\$Entry"
            else -> if (classifier.startsWith("^A")) classifier else canonicalOwnerToJvmInternalName(classifier)
        }
        return JavaVisibleType(javaClassifier, arguments.mapIndexed { index, (variance, type) ->
            JavaVisibleTypeArgument(
                variance,
                type?.toOrdinaryJavaVisibleType(JavaOrdinaryTypePosition.GENERIC, parameterProjection),
                parameterProjection && variance == JavaVisibleVariance.INVARIANT &&
                    classifier.acceptsCompilerParameterOutAt(index),
            )
        })
    }
}

private enum class JavaOrdinaryTypePosition { RETURN, PROPERTY, VALUE_PARAMETER, GENERIC }

private fun String.acceptsCompilerParameterOutAt(index: Int): Boolean = when (this) {
    "kotlin.collections/List",
    "kotlin.collections/Set",
    -> index == 0
    "kotlin.collections/Map" -> index == 1
    else -> false
}

private fun JavaVisibleType.matchesCanonicalJavaType(
    expected: JavaVisibleType,
    typeVariables: MutableMap<String, String> = linkedMapOf(),
): Boolean {
    if (expected.classifier.startsWith("^A")) {
        if (!classifier.startsWith("T:") || arguments.isNotEmpty()) return false
        return typeVariables.getOrPut(expected.classifier) { classifier } == classifier
    }
    return classifier == expected.classifier && arguments.size == expected.arguments.size &&
        arguments.zip(expected.arguments).all { (actual, canonical) ->
            (actual.variance == canonical.variance ||
                canonical.acceptsCompilerParameterOut && actual.variance == JavaVisibleVariance.OUT) && when {
                actual.type == null || canonical.type == null -> actual.type == canonical.type
                else -> actual.type.matchesCanonicalJavaType(canonical.type, typeVariables)
            }
        }
}

private fun String.parseCanonicalJavaType(): CanonicalJavaType = CanonicalJavaTypeParser(this).parse()

private class CanonicalJavaTypeParser(private val source: String) {
    private var index = 0

    fun parse(): CanonicalJavaType = parseType().also {
        check(index == source.length) { "Trailing canonical Java type content: $source" }
    }

    private fun parseType(): CanonicalJavaType {
        val start = index
        while (index < source.length && source[index] !in setOf('<', '>', ',', '?', '!')) index++
        check(index > start) { "Invalid canonical Java type: $source" }
        val classifier = source.substring(start, index)
        val arguments = if (source.getOrNull(index) == '<') {
            index++
            buildList {
                while (source.getOrNull(index) != '>') {
                    if (source.getOrNull(index) == '*') {
                        index++
                        add(JavaVisibleVariance.STAR to null)
                    } else {
                        val variance = JavaVisibleVariance.entries.firstOrNull { candidate ->
                            source.startsWith(candidate.name + ":", index) && candidate != JavaVisibleVariance.STAR
                        } ?: error("Invalid canonical Java type variance: $source")
                        index += variance.name.length + 1
                        add(variance to parseType())
                    }
                    if (source.getOrNull(index) == ',') index++ else check(source.getOrNull(index) == '>') {
                        "Invalid canonical Java type arguments: $source"
                    }
                }
                index++
            }
        } else emptyList()
        val nullable = when {
            source.getOrNull(index) == '?' -> true.also { index++ }
            source.startsWith("!!", index) -> false.also { index += 2 }
            else -> false
        }
        return CanonicalJavaType(classifier, arguments, nullable)
    }
}

private fun JavaMemberRecord.javaMethodSemantic(): JavaVisibleMethod =
    signature?.let { JavaGenericSignatureParser(it).parseMethod() } ?: JavaVisibleMethod(
        Type.getArgumentTypes(symbol.descriptor).map(Type::toJavaVisibleType),
        Type.getReturnType(symbol.descriptor).toJavaVisibleType(),
    )

private fun JavaMemberRecord.javaFieldSemantic(): JavaVisibleType =
    signature?.let { JavaGenericSignatureParser(it).parseField() } ?: Type.getType(symbol.descriptor).toJavaVisibleType()

private fun JavaCanonicalMember.matchesOrdinaryJavaAbi(member: JavaMemberRecord): Boolean {
    val typeVariables = linkedMapOf<String, String>()
    return when (kind) {
        "constructor" -> {
            val method = member.javaMethodSemantic()
            method.returnType == JavaVisibleType("V") &&
                method.parameters.matchesCanonicalParameters(parameters, typeVariables)
        }
        "function" -> {
            val method = member.javaMethodSemantic()
            method.parameters.matchesCanonicalParameters(parameters, typeVariables) &&
                method.returnType.matchesCanonicalJavaType(
                    checkNotNull(returnType).parseCanonicalJavaType()
                        .toOrdinaryJavaVisibleType(JavaOrdinaryTypePosition.RETURN),
                    typeVariables,
                )
        }
        "property" -> {
            val expected = checkNotNull(propertyType).parseCanonicalJavaType()
                .toOrdinaryJavaVisibleType(JavaOrdinaryTypePosition.PROPERTY)
            val actual = when (member.symbol.kind) {
                JavaJvmSymbolKind.METHOD -> member.javaMethodSemantic().returnType
                JavaJvmSymbolKind.FIELD -> member.javaFieldSemantic()
            }
            actual.matchesCanonicalJavaType(expected, typeVariables)
        }
        "enum-entry" -> true
        "object" -> true
        else -> false
    }
}

private fun List<JavaVisibleType>.matchesCanonicalParameters(
    canonical: List<JavaCanonicalParameter>,
    typeVariables: MutableMap<String, String>,
): Boolean = size == canonical.size && zip(canonical).all { (actual, expected) ->
    actual.matchesCanonicalJavaType(
        expected.type.parseCanonicalJavaType().toOrdinaryJavaVisibleType(JavaOrdinaryTypePosition.VALUE_PARAMETER),
        typeVariables,
    )
}

private fun List<JavaVisibleType>.matchesCanonicalJavaTypes(expected: List<JavaVisibleType>): Boolean {
    val typeVariables = linkedMapOf<String, String>()
    return size == expected.size && zip(expected).all { (actual, canonical) ->
        actual.matchesCanonicalJavaType(canonical, typeVariables)
    }
}

private fun List<JavaVisibleType>.defaultVariants(
    parameters: List<JavaCanonicalParameter>,
    allowOmissions: Boolean,
): List<List<JavaVisibleType>> {
    check(size == parameters.size) { "Canonical Java projection parameter inventory mismatch" }
    if (!allowOmissions) return listOf(this)
    return buildList {
        fun addVariants(index: Int, selected: MutableList<JavaVisibleType>) {
            if (index == parameters.size) {
                add(selected.toList())
                return
            }
            selected += this@defaultVariants[index]
            addVariants(index + 1, selected)
            selected.removeAt(selected.lastIndex)
            if (parameters[index].hasDefault) addVariants(index + 1, selected)
        }
        addVariants(0, mutableListOf())
    }
}

private fun Type.toJavaVisibleType(): JavaVisibleType = when (sort) {
    Type.VOID -> JavaVisibleType("V")
    Type.BOOLEAN -> JavaVisibleType("Z")
    Type.CHAR -> JavaVisibleType("C")
    Type.BYTE -> JavaVisibleType("B")
    Type.SHORT -> JavaVisibleType("S")
    Type.INT -> JavaVisibleType("I")
    Type.FLOAT -> JavaVisibleType("F")
    Type.LONG -> JavaVisibleType("J")
    Type.DOUBLE -> JavaVisibleType("D")
    Type.ARRAY -> JavaVisibleType("[", listOf(JavaVisibleTypeArgument(JavaVisibleVariance.INVARIANT, elementType.toJavaVisibleType())))
    Type.OBJECT -> JavaVisibleType(internalName)
    else -> error("Unsupported JVM descriptor type: $descriptor")
}

private class JavaGenericSignatureParser(private val source: String) {
    private var index = 0

    fun parseMethod(): JavaVisibleMethod {
        check(source.getOrNull(index) == '(') { "Generic Java method type parameters are unsupported: $source" }
        index++
        val parameters = buildList {
            while (source.getOrNull(index) != ')') add(parseType())
        }
        index++
        val result = JavaVisibleMethod(parameters, parseType())
        check(index == source.length || source[index] == '^') { "Trailing Java generic signature content: $source" }
        return result
    }

    fun parseField(): JavaVisibleType = parseType().also {
        check(index == source.length) { "Trailing Java generic field signature content: $source" }
    }

    private fun parseType(): JavaVisibleType = when (val marker = source.getOrNull(index)) {
        'V', 'Z', 'C', 'B', 'S', 'I', 'F', 'J', 'D' -> JavaVisibleType(marker.toString()).also { index++ }
        '[' -> {
            index++
            JavaVisibleType("[", listOf(JavaVisibleTypeArgument(JavaVisibleVariance.INVARIANT, parseType())))
        }
        'T' -> {
            index++
            val end = source.indexOf(';', index)
            check(end > index) { "Invalid Java generic type variable: $source" }
            JavaVisibleType("T:" + source.substring(index, end)).also { index = end + 1 }
        }
        'L' -> parseClassType()
        else -> error("Invalid Java generic signature type '$marker': $source")
    }

    private fun parseClassType(): JavaVisibleType {
        index++
        val name = StringBuilder()
        val arguments = mutableListOf<JavaVisibleTypeArgument>()
        while (true) {
            when (val character = source.getOrNull(index)) {
                ';' -> {
                    index++
                    return JavaVisibleType(name.toString(), arguments)
                }
                '<' -> {
                    index++
                    while (source.getOrNull(index) != '>') arguments += parseTypeArgument()
                    index++
                }
                '.' -> {
                    name.append('$')
                    index++
                }
                null -> error("Unterminated Java generic class type: $source")
                else -> {
                    name.append(character)
                    index++
                }
            }
        }
    }

    private fun parseTypeArgument(): JavaVisibleTypeArgument = when (source.getOrNull(index)) {
        '*' -> JavaVisibleTypeArgument(JavaVisibleVariance.STAR).also { index++ }
        '+' -> {
            index++
            JavaVisibleTypeArgument(JavaVisibleVariance.OUT, parseType())
        }
        '-' -> {
            index++
            JavaVisibleTypeArgument(JavaVisibleVariance.IN, parseType())
        }
        else -> JavaVisibleTypeArgument(JavaVisibleVariance.INVARIANT, parseType())
    }
}

internal fun canonicalOwnerToJvmInternalName(owner: String): String {
    val packageSeparator = owner.lastIndexOf('/')
    if (packageSeparator < 0) return owner.replace('.', '$')
    return owner.substring(0, packageSeparator).replace('.', '/') + "/" +
        owner.substring(packageSeparator + 1).replace('.', '$')
}

private data class JavaMemberRecord(
    val symbol: JavaJvmSymbol,
    val access: Int,
    val signature: String?,
)

private data class JavaClassRecord(
    val internalName: String,
    val access: Int,
    val superName: String?,
    val interfaces: List<String>,
    val fields: Map<Pair<String, String>, JavaMemberRecord>,
    val methods: Map<Pair<String, String>, JavaMemberRecord>,
    val metadata: KmClass?,
)

private class JavaArtifactIndex(
    private val label: String,
    private val classes: Map<String, JavaClassRecord>,
) {
    fun requireCanonicalDeclaration(member: JavaCanonicalMember) {
        val owner = canonicalOwner(member)
        val metadata = checkNotNull(owner.metadata)
        val matches = when (member.kind) {
            "constructor" -> metadata.constructors.filter { constructor ->
                constructor.visibility == Visibility.PUBLIC && member.matchesConstructor(constructor.valueParameters)
            }.size
            "function" -> metadata.functions.filter { function ->
                function.name == member.name && function.visibility == Visibility.PUBLIC &&
                    member.matchesFunction(
                        function.returnType,
                        function.valueParameters,
                        function.isSuspend,
                        function.typeParameters,
                    )
            }.size
            "property" -> metadata.properties.filter { property ->
                property.name == member.name && property.visibility == Visibility.PUBLIC &&
                    member.matchesProperty(property.returnType, property.isVar)
            }.size
            "enum-entry" -> metadata.enumEntries.count { it == member.name }
            "object" -> if (metadata.kind == ClassKind.OBJECT) 1 else 0
            else -> error("Unsupported canonical Java member kind ${member.kind}")
        }
        check(matches == 1) {
            "$label does not contain exactly one Kotlin declaration matching canonical semantics: ${member.key}"
        }
        check(canonicalJvmCandidates(member).isNotEmpty()) {
            "$label canonical Kotlin declaration has no public JVM member: ${member.key}"
        }
    }

    fun resolveOrdinary(member: JavaCanonicalMember): List<JavaJvmSymbol> {
        val candidates = canonicalJvmCandidates(member)
        check(candidates.size == 1) {
            "$label does not resolve ${member.key} to exactly one public non-synthetic Java member: " +
                candidates.map { it.symbol.id }
        }
        check(member.matchesOrdinaryJavaAbi(candidates.single())) {
            "$label ordinary Java ABI does not match canonical types: ${member.key}: ${candidates.single().symbol.id}"
        }
        return listOf(candidates.single().symbol)
    }

    private fun canonicalJvmCandidates(member: JavaCanonicalMember): List<JavaMemberRecord> {
        val owner = canonicalOwner(member)
        val metadata = checkNotNull(owner.metadata)
        return when (member.kind) {
            "constructor" -> metadata.constructors.filter {
                it.visibility == Visibility.PUBLIC && member.matchesConstructor(it.valueParameters)
            }
                .mapNotNull { it.signature }.map { method(owner, it.name, it.descriptor, member.key) }
            "function" -> metadata.functions.filter {
                it.name == member.name && it.visibility == Visibility.PUBLIC &&
                    member.matchesFunction(it.returnType, it.valueParameters, it.isSuspend, it.typeParameters)
            }
                .mapNotNull { it.signature }.map { method(owner, it.name, it.descriptor, member.key) }
            "property" -> metadata.properties.filter {
                it.name == member.name && it.visibility == Visibility.PUBLIC &&
                    member.matchesProperty(it.returnType, it.isVar)
            }
                .flatMap { property ->
                    listOfNotNull(
                        property.getterSignature?.let { publicMethodOrNull(owner, it.name, it.descriptor) },
                        property.fieldSignature?.let { publicFieldOrNull(owner, it.name, it.descriptor) },
                    )
                }
            "enum-entry" -> listOf(field(owner, member.name, "L${owner.internalName};", member.key).also { field ->
                check(field.access and Opcodes.ACC_STATIC != 0 && field.access and Opcodes.ACC_FINAL != 0) {
                    "$label enum entry is not static final: ${field.symbol.id}"
                }
            })
            "object" -> listOf(field(owner, "INSTANCE", "L${owner.internalName};", member.key).also { field ->
                check(field.access and Opcodes.ACC_STATIC != 0 && field.access and Opcodes.ACC_FINAL != 0) {
                    "$label Kotlin object INSTANCE is not static final: ${field.symbol.id}"
                }
            })
            else -> error("Unsupported ordinary Java member kind ${member.kind}")
        }.distinctBy(JavaMemberRecord::symbol)
    }

    private fun canonicalOwner(member: JavaCanonicalMember): JavaClassRecord {
        val expectedOwner = canonicalOwnerToJvmInternalName(member.owner)
        return classes.values.singleOrNull { it.internalName == expectedOwner && it.metadata != null }
            ?.also { requirePublicClass(it, member.key) }
            ?: error("$label does not contain exactly one Kotlin class for ${member.owner}")
    }

    fun requireFuture(symbol: JavaJvmSymbol, member: JavaCanonicalMember): List<JavaJvmSymbol> {
        val method = publicMethod(symbol, member.key)
        requireFutureMethod(method, member)
        return listOf(method.symbol)
    }

    fun requireFutureTestTarget(symbol: JavaJvmSymbol, member: JavaCanonicalMember): JavaBindingMethodTarget =
        JavaBindingMethodTarget(
            symbol.owner,
            symbol.name,
            validatedDefaultOverloads(symbol, member) { candidate ->
                requireFutureMethod(candidate, member, allowDefaultOmissions = true)
            },
        )

    private fun requireFutureMethod(
        method: JavaMemberRecord,
        member: JavaCanonicalMember,
        allowDefaultOmissions: Boolean = false,
    ) {
        val symbol = method.symbol
        val returnType = Type.getReturnType(symbol.descriptor)
        val allowed = setOf("java/util/concurrent/CompletableFuture", "java/util/concurrent/CompletionStage")
        check(returnType.sort == Type.OBJECT && returnType.internalName in allowed) {
            "$label Java async projection must return CompletableFuture or CompletionStage: ${symbol.id}"
        }
        check(Type.getArgumentTypes(symbol.descriptor).none { it.internalNameOrNull() == "kotlin/coroutines/Continuation" }) {
            "$label Java async projection exposes a Kotlin Continuation: ${symbol.id}"
        }
        val genericMarker = "L${returnType.internalName}<"
        val returnSignature = method.signature?.substringAfterLast(')')
        check(returnSignature?.startsWith(genericMarker) == true && returnSignature?.getOrNull(genericMarker.length) != '*') {
            "$label Java async projection exposes a raw Future: ${symbol.id}"
        }
        val semantic = method.javaMethodSemantic()
        val semanticReturn = semantic.returnType
        val expectedValue = checkNotNull(member.returnType).parseCanonicalJavaType().toJavaVisibleType(
            topLevelProjection = true,
            genericContext = true,
        )
        check(semanticReturn.classifier in allowed &&
            semanticReturn.arguments == listOf(JavaVisibleTypeArgument(JavaVisibleVariance.INVARIANT, expectedValue))) {
            "$label Java async projection type does not match canonical return ${member.returnType}: ${method.symbol.id}"
        }
        val canonicalParameters = canonicalProjectionParameterTypes(member)
        val expectedParameters = canonicalParameters.defaultVariants(member.parameters, allowDefaultOmissions)
            .map { listOf(canonicalProjectionReceiver(member)) + it }
        check(expectedParameters.any { expected ->
            semantic.parameters.matchesCanonicalJavaTypes(expected)
        }) {
            "$label Java async projection receiver/parameters do not match the canonical member: ${method.symbol.id}"
        }
    }

    fun requireStateProjection(alias: JavaStateFlowBindingAlias, member: JavaCanonicalMember): List<JavaJvmSymbol> {
        check(alias.currentMethod != alias.observeMethod) { "Java StateFlow projection reuses one method: ${member.key}" }
        val current = publicMethod(alias.currentMethod, member.key)
        val observe = publicMethod(alias.observeMethod, member.key)
        listOf(current, observe).forEach { method ->
            check("kotlinx/coroutines/flow/StateFlow" !in method.symbol.descriptor &&
                "kotlinx/coroutines/flow/StateFlow" !in method.signature.orEmpty()) {
                "$label Java StateFlow projection exposes StateFlow directly: ${method.symbol.id}"
            }
        }
        check(Type.getReturnType(current.symbol.descriptor).sort != Type.VOID) {
            "$label Java StateFlow current-value projection returns void: ${current.symbol.id}"
        }
        val stateElement = checkNotNull(member.propertyType).parseCanonicalJavaType().stateFlowElement(member.key)
        val expectedCurrent = stateElement.toJavaVisibleType(topLevelProjection = true, genericContext = false)
        val expectedReceiver = canonicalProjectionReceiver(member)
        val currentSemantic = current.javaMethodSemantic()
        check(currentSemantic.returnType == expectedCurrent) {
            "$label Java StateFlow current-value type does not match canonical element: ${current.symbol.id}"
        }
        check(currentSemantic.parameters.matchesCanonicalJavaTypes(listOf(expectedReceiver))) {
            "$label Java StateFlow current-value receiver does not match canonical owner: ${current.symbol.id}"
        }
        val observationType = Type.getReturnType(observe.symbol.descriptor)
        val observeParameters = Type.getArgumentTypes(observe.symbol.descriptor).mapNotNull(Type::internalNameOrNull)
        check("java/util/function/Consumer" in observeParameters) {
            "$label Java StateFlow observation does not accept java.util.function.Consumer: ${observe.symbol.id}"
        }
        val leakage = listOf("kotlinx/coroutines/flow/", "kotlin/jvm/functions/", "kotlin/coroutines/")
        check(leakage.none { it in observe.symbol.descriptor || it in observe.signature.orEmpty() }) {
            "$label Java StateFlow observation exposes Kotlin flow/function types: ${observe.symbol.id}"
        }
        check(observationType.sort == Type.OBJECT && isPublicAutoCloseable(observationType.internalName, member.key)) {
            "$label Java StateFlow observation is not AutoCloseable: ${observe.symbol.id}"
        }
        val expectedConsumer = JavaVisibleType(
            "java/util/function/Consumer",
            listOf(JavaVisibleTypeArgument(
                JavaVisibleVariance.IN,
                stateElement.toJavaVisibleType(topLevelProjection = true, genericContext = true),
            )),
        )
        val observeSemantic = observe.javaMethodSemantic()
        check(observeSemantic.parameters.matchesCanonicalJavaTypes(listOf(
            expectedReceiver,
            JavaVisibleType("java/util/concurrent/Executor"),
            expectedConsumer,
        ))) {
            "$label Java StateFlow observation parameters do not match canonical receiver/executor/element: " +
                observe.symbol.id
        }
        return listOf(current.symbol, observe.symbol)
    }

    private fun canonicalProjectionReceiver(member: JavaCanonicalMember): JavaVisibleType {
        val owner = canonicalOwner(member)
        val packageName = member.owner.substringBeforeLast('/', missingDelimiterValue = "")
        val agentName = canonicalOwnerToJvmInternalName(
            if (packageName.isEmpty()) "CodexAgent" else "$packageName/CodexAgent",
        )
        val agent = classes[agentName]
        val projectedFromAgent = agent?.metadata?.properties?.any { property ->
            property.visibility == Visibility.PUBLIC &&
                (property.returnType.classifier as? KmClassifier.Class)?.name?.toJvmInternalName() == owner.internalName &&
                property.getterSignature?.let { signature ->
                    publicMethodOrNull(agent, signature.name, signature.descriptor) != null
                } == true
        } == true
        return JavaVisibleType(if (projectedFromAgent) agentName else owner.internalName)
    }

    private fun canonicalProjectionParameterTypes(member: JavaCanonicalMember): List<JavaVisibleType> {
        val function = canonicalFunction(member)
        val typeParameterBounds = function.typeParameters.mapNotNull { parameter ->
            check(parameter.upperBounds.size <= 1) {
                "$label Java projection cannot erase a canonical type parameter with multiple bounds: ${member.key}"
            }
            parameter.upperBounds.singleOrNull()?.let { parameter.id to it }
        }.toMap()
        return function.valueParameters.map { parameter ->
            parameter.type.renderCanonicalKmType(
                typeParameterBounds = typeParameterBounds,
                resolveTypeParameters = true,
            )
                .parseCanonicalJavaType()
                .toOrdinaryJavaVisibleType(JavaOrdinaryTypePosition.VALUE_PARAMETER)
        }
    }

    private fun canonicalFunction(member: JavaCanonicalMember): KmFunction {
        val metadata = checkNotNull(canonicalOwner(member).metadata)
        return metadata.functions.single { function ->
            function.name == member.name && function.visibility == Visibility.PUBLIC &&
                member.matchesFunction(
                    function.returnType,
                    function.valueParameters,
                    function.isSuspend,
                    function.typeParameters,
                )
        }
    }

    fun requireHostFactory(symbol: JavaJvmSymbol, canonicalOwner: String, platform: String): JavaJvmSymbol {
        val method = publicMethod(symbol, "$platform host factory")
        check(method.access and Opcodes.ACC_STATIC != 0) { "$label $platform host factory is not static: ${symbol.id}" }
        val expectedHost = canonicalOwnerToJvmInternalName(canonicalOwner)
        check(Type.getReturnType(symbol.descriptor).internalNameOrNull() == expectedHost) {
            "$label $platform host factory does not return $expectedHost: ${symbol.id}"
        }
        val expectedBootstrapType = when (platform) {
            "Desktop" -> "java/nio/file/Path"
            "Android" -> "android/content/Context"
            else -> error("Unsupported Java Host-factory platform $platform")
        }
        val parameters = Type.getArgumentTypes(symbol.descriptor).mapNotNull(Type::internalNameOrNull)
        check(expectedBootstrapType in parameters) {
            "$label $platform host factory does not accept $expectedBootstrapType: ${symbol.id}"
        }
        val forbiddenNames = setOf("CodexPlatform", "PreparedCodexRuntime", "CoroutineScope", "Continuation")
        val forbiddenFragments = listOf("/internal/", "kotlinx/coroutines/CoroutineScope", "kotlin/coroutines/Continuation")
        val forbidden = parameters.filter { type ->
            val simpleName = type.substringAfterLast('/')
            simpleName in forbiddenNames || forbiddenFragments.any(type::contains) ||
                ("/runtime/" in type && (simpleName.endsWith("Runtime") || simpleName.endsWith("Platform")))
        }
        val signature = method.signature.orEmpty()
        val forbiddenSignature = forbiddenFragments.any(signature::contains) ||
            forbiddenNames.any { name -> "/$name;" in signature || "L$name;" in signature } ||
            Regex("L[^;<]*(?:/internal/|/runtime/)[^;<]*(?:Runtime|Platform);").containsMatchIn(signature)
        check(forbidden.isEmpty() && !forbiddenSignature) {
            "$label $platform host factory exposes platform/runtime SPI: ${symbol.id}: $forbidden"
        }
        return method.symbol
    }

    fun requireStaticProjection(symbol: JavaJvmSymbol, member: JavaCanonicalMember): List<JavaJvmSymbol> {
        val method = publicMethod(symbol, member.key)
        requireStaticMethod(method, member)
        return listOf(method.symbol)
    }

    fun requireStaticTestTarget(symbol: JavaJvmSymbol, member: JavaCanonicalMember): JavaBindingMethodTarget =
        JavaBindingMethodTarget(
            symbol.owner,
            symbol.name,
            validatedDefaultOverloads(symbol, member) { candidate -> requireStaticMethod(candidate, member) },
        )

    private fun requireStaticMethod(method: JavaMemberRecord, member: JavaCanonicalMember) {
        val symbol = method.symbol
        check(method.access and Opcodes.ACC_STATIC != 0 && !symbol.owner.endsWith("\$Companion")) {
            "$label Java companion projection is not a true static method: ${symbol.id}"
        }
        check(member.matchesOrdinaryJavaAbi(method)) {
            "$label Java companion projection types do not match canonical member: ${member.key}: ${symbol.id}"
        }
    }

    private fun validatedDefaultOverloads(
        symbol: JavaJvmSymbol,
        member: JavaCanonicalMember,
        validate: (JavaMemberRecord) -> Unit,
    ): List<String> {
        val owner = classes[symbol.owner] ?: error("$label is missing Java alias owner ${symbol.owner}: ${member.key}")
        val argumentTypes = Type.getArgumentTypes(symbol.descriptor).toList()
        val prefixCount = argumentTypes.size - member.parameters.size
        check(prefixCount >= 0) { "$label Java alias has fewer parameters than its canonical member: ${symbol.id}" }
        val prefix = argumentTypes.take(prefixCount)
        val canonicalArguments = argumentTypes.drop(prefixCount)
        val candidateDescriptors = buildList {
            fun addCombinations(index: Int, selected: MutableList<Type>) {
                if (index == member.parameters.size) {
                    add(Type.getMethodDescriptor(Type.getReturnType(symbol.descriptor), *(prefix + selected).toTypedArray()))
                    return
                }
                selected += canonicalArguments[index]
                addCombinations(index + 1, selected)
                selected.removeAt(selected.lastIndex)
                if (member.parameters[index].hasDefault) addCombinations(index + 1, selected)
            }
            addCombinations(0, mutableListOf())
        }.distinct().sorted()
        val validated = candidateDescriptors.mapNotNull { descriptor ->
            owner.methods[symbol.name to descriptor]?.takeIf { it.access.isPublicJavaApi() }?.also(validate)?.symbol?.descriptor
        }
        check(symbol.descriptor in validated) { "$label Java alias exact overload was not validated: ${symbol.id}" }
        return validated
    }

    private fun method(
        owner: JavaClassRecord,
        name: String,
        descriptor: String,
        capability: String,
    ): JavaMemberRecord = publicMember(owner.methods[name to descriptor], capability, "method $name$descriptor")

    private fun field(
        owner: JavaClassRecord,
        name: String,
        descriptor: String,
        capability: String,
    ): JavaMemberRecord = publicMember(owner.fields[name to descriptor], capability, "field $name:$descriptor")

    private fun publicMethodOrNull(owner: JavaClassRecord, name: String, descriptor: String): JavaMemberRecord? =
        owner.methods[name to descriptor]?.takeIf { member ->
            member.access.isPublicJavaApi()
        }

    private fun publicFieldOrNull(owner: JavaClassRecord, name: String, descriptor: String): JavaMemberRecord? =
        owner.fields[name to descriptor]?.takeIf { member ->
            member.access and Opcodes.ACC_PUBLIC != 0 && member.access and Opcodes.ACC_SYNTHETIC == 0
        }

    private fun publicMethod(symbol: JavaJvmSymbol, capability: String): JavaMemberRecord {
        check(symbol.kind == JavaJvmSymbolKind.METHOD) { "$label Java alias is not a method: ${symbol.id}" }
        val owner = classes[symbol.owner] ?: error("$label is missing Java alias owner ${symbol.owner}: $capability")
        requirePublicClass(owner, capability)
        return publicMember(owner.methods[symbol.name to symbol.descriptor], capability, symbol.id)
    }

    private fun publicMember(member: JavaMemberRecord?, capability: String, identity: String): JavaMemberRecord {
        check(member != null) { "$label is missing Java member $identity for $capability" }
        check(member.access and Opcodes.ACC_PUBLIC != 0) { "$label Java member is not public: $identity" }
        check(member.access and Opcodes.ACC_SYNTHETIC == 0) { "$label Java member is synthetic: $identity" }
        if (member.symbol.kind == JavaJvmSymbolKind.METHOD) {
            check(member.access and Opcodes.ACC_BRIDGE == 0) { "$label Java member is a bridge: $identity" }
        }
        return member
    }

    private fun requirePublicClass(owner: JavaClassRecord, capability: String) {
        check(owner.access and Opcodes.ACC_PUBLIC != 0) { "$label Java owner is not public: ${owner.internalName}: $capability" }
        check(owner.access and Opcodes.ACC_SYNTHETIC == 0) { "$label Java owner is synthetic: ${owner.internalName}: $capability" }
    }

    private fun implementsInterface(type: String, target: String, seen: MutableSet<String> = mutableSetOf()): Boolean {
        if (type == target) return true
        if (!seen.add(type)) return false
        val record = classes[type] ?: return false
        return record.interfaces.any { implementsInterface(it, target, seen) } ||
            record.superName?.let { implementsInterface(it, target, seen) } == true
    }

    private fun isPublicAutoCloseable(type: String, capability: String): Boolean {
        if (type == "java/lang/AutoCloseable") return true
        val record = classes[type] ?: return false
        requirePublicClass(record, capability)
        return implementsInterface(type, "java/lang/AutoCloseable")
    }
}

private fun Int.isPublicJavaApi(): Boolean =
    this and Opcodes.ACC_PUBLIC != 0 && this and (Opcodes.ACC_SYNTHETIC or Opcodes.ACC_BRIDGE) == 0

private fun Type.internalNameOrNull(): String? = if (sort == Type.OBJECT) internalName else null

private data class JavaArtifactSnapshot(val index: JavaArtifactIndex, val sha256: String)

private fun readJavaJar(file: File, label: String): JavaArtifactSnapshot {
    check(file.isFile && file.extension == "jar" && file.length() > 0L) { "$label is missing or not an exact JAR: $file" }
    val bytes = file.readBytes()
    return JavaArtifactSnapshot(readJavaZip(bytes, label), bytes.inputStream().releaseDigest())
}

private fun readJavaAar(file: File, label: String): JavaArtifactSnapshot {
    check(file.isFile && file.extension == "aar" && file.length() > 0L) { "$label is missing or not an exact AAR: $file" }
    val bytes = file.readBytes()
    val classesJars = buildList {
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (!entry.isDirectory && entry.name == "classes.jar") add(zip.readBytes())
            }
        }
    }
    check(classesJars.size == 1) { "$label must contain exactly one classes.jar" }
    return JavaArtifactSnapshot(
        readJavaZip(classesJars.single(), "$label/classes.jar"),
        bytes.inputStream().releaseDigest(),
    )
}

private fun readJavaZip(bytes: ByteArray, label: String): JavaArtifactIndex {
    val classes = linkedMapOf<String, JavaClassRecord>()
    ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
        while (true) {
            val entry = zip.nextEntry ?: break
            if (!entry.isDirectory && entry.name.endsWith(".class")) {
                val record = readJavaClass(zip.readBytes())
                check(entry.name.removeSuffix(".class") == record.internalName) {
                    "$label class entry path does not match bytecode name: ${entry.name} != ${record.internalName}.class"
                }
                check(classes.put(record.internalName, record) == null) {
                    "$label contains duplicate Java class ${record.internalName}"
                }
            }
        }
    }
    check(classes.isNotEmpty()) { "$label contains no Java classes" }
    return JavaArtifactIndex(label, classes)
}

private fun readJavaClass(bytes: ByteArray): JavaClassRecord {
    val reader = ClassReader(bytes)
    var access = 0
    var superName: String? = null
    var interfaces = emptyList<String>()
    var metadataHeader: JavaKotlinMetadataHeader? = null
    val fields = linkedMapOf<Pair<String, String>, JavaMemberRecord>()
    val methods = linkedMapOf<Pair<String, String>, JavaMemberRecord>()
    reader.accept(object : ClassVisitor(Opcodes.ASM9) {
        override fun visit(
            version: Int,
            classAccess: Int,
            name: String,
            signature: String?,
            parent: String?,
            implemented: Array<out String>,
        ) {
            access = classAccess
            superName = parent
            interfaces = implemented.toList()
        }

        override fun visitAnnotation(descriptor: String, visible: Boolean): AnnotationVisitor? =
            if (descriptor == "Lkotlin/Metadata;") {
                check(metadataHeader == null) { "Duplicate kotlin.Metadata annotation: ${reader.className}" }
                JavaKotlinMetadataHeader().also { metadataHeader = it }
            } else null

        override fun visitField(
            fieldAccess: Int,
            name: String,
            descriptor: String,
            signature: String?,
            value: Any?,
        ): FieldVisitor? {
            val symbol = JavaJvmSymbol(JavaJvmSymbolKind.FIELD, reader.className, name, descriptor, signature)
            check(fields.put(name to descriptor, JavaMemberRecord(symbol, fieldAccess, signature)) == null) {
                "Duplicate Java field ${symbol.id}"
            }
            return null
        }

        override fun visitMethod(
            methodAccess: Int,
            name: String,
            descriptor: String,
            signature: String?,
            exceptions: Array<out String>?,
        ): MethodVisitor? {
            val symbol = JavaJvmSymbol(JavaJvmSymbolKind.METHOD, reader.className, name, descriptor, signature)
            check(methods.put(name to descriptor, JavaMemberRecord(symbol, methodAccess, signature)) == null) {
                "Duplicate Java method ${symbol.id}"
            }
            return null
        }
    }, ClassReader.SKIP_CODE or ClassReader.SKIP_DEBUG or ClassReader.SKIP_FRAMES)
    val metadata = metadataHeader?.build()?.let(KotlinClassMetadata::readStrict) as? KotlinClassMetadata.Class
    metadata?.kmClass?.let { kmClass ->
        check(kmClass.name.toJvmInternalName() == reader.className) {
            "Kotlin metadata/JVM class-name mismatch: ${kmClass.name} != ${reader.className}"
        }
    }
    return JavaClassRecord(
        reader.className,
        access,
        superName,
        interfaces,
        fields,
        methods,
        metadata?.kmClass,
    )
}

private class JavaKotlinMetadataHeader : AnnotationVisitor(Opcodes.ASM9) {
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

    fun build(): kotlin.Metadata = kotlin.Metadata(
        kind = kind ?: 1,
        metadataVersion = metadataVersion ?: intArrayOf(),
        data1 = data1.toTypedArray(),
        data2 = data2.toTypedArray(),
        extraString = extraString.orEmpty(),
        packageName = packageName.orEmpty(),
        extraInt = extraInt ?: 0,
    )
}

private fun requireUniqueExactJavaValues(values: List<String>, label: String) {
    check(values.isNotEmpty()) { "$label list is empty" }
    check(values.none { it.isBlank() || '*' in it }) { "$label is blank or wildcard" }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label identities are duplicated: $duplicates" }
}
