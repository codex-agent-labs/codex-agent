@file:OptIn(org.jetbrains.kotlin.library.abi.ExperimentalLibraryAbiReader::class)

import java.io.File
import org.jetbrains.kotlin.library.abi.AbiClass
import org.jetbrains.kotlin.library.abi.AbiClassKind
import org.jetbrains.kotlin.library.abi.AbiClassifierReference
import org.jetbrains.kotlin.library.abi.AbiDeclaration
import org.jetbrains.kotlin.library.abi.AbiDeclarationContainer
import org.jetbrains.kotlin.library.abi.AbiEnumEntry
import org.jetbrains.kotlin.library.abi.AbiFunction
import org.jetbrains.kotlin.library.abi.AbiModality
import org.jetbrains.kotlin.library.abi.AbiProperty
import org.jetbrains.kotlin.library.abi.AbiPropertyKind
import org.jetbrains.kotlin.library.abi.AbiSignatureVersion
import org.jetbrains.kotlin.library.abi.AbiType
import org.jetbrains.kotlin.library.abi.AbiTypeArgument
import org.jetbrains.kotlin.library.abi.AbiTypeNullability
import org.jetbrains.kotlin.library.abi.AbiTypeParameter
import org.jetbrains.kotlin.library.abi.AbiValueParameterKind
import org.jetbrains.kotlin.library.abi.LibraryAbiReader

internal data class CrossLanguageApiReport(
    val libraryUniqueName: String,
    val signatureVersion: Int,
    val markerAnnotation: String,
    val boundaryTypes: List<String>,
    val memberExclusionAnnotation: String?,
    val excludedReachableTypes: List<String>,
    val excludedMemberKeys: List<String>,
    val dataClassMetadataAvailable: Boolean,
    val dataClassNames: List<String>,
    val owners: List<CrossLanguageApiOwner>,
) {
    val capabilityKeys: List<String> = owners.flatMap(CrossLanguageApiOwner::capabilityKeys).sorted()
}

internal data class CrossLanguageApiOwner(
    val name: String,
    val capabilityKeys: List<String>,
)

internal fun discoverCrossLanguageApi(
    klib: File,
    markerAnnotation: String,
    allowedBoundaryTypes: Set<String>,
    memberExclusionAnnotation: String? = null,
    requiredExcludedReachableTypes: Set<String> = emptySet(),
    dataClassNames: Set<String>? = null,
    singletonObjectNames: Set<String>,
    companionObjectNames: Set<String>,
): CrossLanguageApiReport {
    check(klib.exists()) { "Cross-language API KLIB is missing: $klib" }
    val abi = LibraryAbiReader.readAbiInfo(klib)
    val signatureVersion = abi.signatureVersions.singleOrNull {
        it.versionNumber == 2 && it.isSupportedByAbiReader
    } ?: error("Cross-language API discovery requires supported KLIB signature version 2")
    return discoverCrossLanguageApi(
        library = abi.topLevelDeclarations.toCompilerLibrary(abi.uniqueName, signatureVersion),
        markerAnnotation = markerAnnotation,
        allowedBoundaryTypes = allowedBoundaryTypes,
        memberExclusionAnnotation = memberExclusionAnnotation,
        requiredExcludedReachableTypes = requiredExcludedReachableTypes,
        dataClassNames = dataClassNames,
        singletonObjectNames = singletonObjectNames,
        companionObjectNames = companionObjectNames,
    )
}

internal fun discoverCrossLanguageApi(
    library: CompilerApiLibrary,
    markerAnnotation: String,
    allowedBoundaryTypes: Set<String>,
    memberExclusionAnnotation: String? = null,
    requiredExcludedReachableTypes: Set<String> = emptySet(),
    dataClassNames: Set<String>? = null,
    singletonObjectNames: Set<String> = emptySet(),
    companionObjectNames: Set<String> = emptySet(),
): CrossLanguageApiReport {
    check(markerAnnotation.isNotBlank()) { "CodexBindingApi annotation name is blank" }
    val exclusionAnnotation = memberExclusionAnnotation?.trim()?.also { annotation ->
        check(annotation.isNotEmpty()) { "Member exclusion annotation name is blank" }
    }
    check((exclusionAnnotation == null) == requiredExcludedReachableTypes.isEmpty()) {
        "Member exclusion annotation and required reachable types must be configured together"
    }
    val normalizedBoundaries = normalizeExactDiscoveryNames(allowedBoundaryTypes, "Allowed boundary type")
    val normalizedExcludedTypes = normalizeExactDiscoveryNames(
        requiredExcludedReachableTypes,
        "Required excluded reachable type",
    )
    val normalizedSingletonObjects = normalizeExactDiscoveryNames(
        singletonObjectNames,
        "Compiler-derived singleton object",
    )
    val normalizedCompanionObjects = normalizeExactDiscoveryNames(
        companionObjectNames,
        "Compiler-derived companion object",
    )
    check(normalizedSingletonObjects.intersect(normalizedCompanionObjects).isEmpty()) {
        "Compiler-derived singleton and companion object identities overlap"
    }
    val classes = library.classes.associateByStrict(CompilerApiClass::name, "Compiler API class")
    val classesByNormalizedName = classes.values.associateByStrict(
        { normalizeQualifiedName(it.name) },
        "Normalized compiler API class",
    )
    requireUniqueNonBlankDiscovery(library.classes.map(CompilerApiClass::abiSignature), "Compiler ABI class signature")
    val markedRoots = classes.values.filter { owner ->
        owner.annotations.any { sameQualifiedName(it, markerAnnotation) }
    }
    check(markedRoots.isNotEmpty()) { "No compiler API owner is marked with $markerAnnotation" }
    val ownerNames = markedRoots.mapTo(linkedSetOf(), CompilerApiClass::name)
    do {
        val nested = classes.values.filter { it.enclosingClass in ownerNames }.map(CompilerApiClass::name)
        val changed = ownerNames.addAll(nested)
    } while (changed)
    val owners = ownerNames.map(classes::getValue).sortedBy(CompilerApiClass::name)

    val violations = sortedSetOf<String>()
    owners.forEach { owner ->
        val normalized = normalizeQualifiedName(owner.name)
        val classifications = listOf(
            normalized in normalizedSingletonObjects,
            normalized in normalizedCompanionObjects,
        ).count { it }
        when {
            owner.kind == AbiClassKind.OBJECT.name && classifications != 1 ->
                violations += "marked object owner ${owner.name} lacks one exact JVM singleton/companion classification"
            owner.kind != AbiClassKind.OBJECT.name && classifications != 0 ->
                violations += "marked non-object owner ${owner.name} has a JVM singleton/companion classification"
        }
    }
    val exactBoundaries = buildMap {
        normalizedBoundaries.forEach { normalized ->
            val boundary = classesByNormalizedName[normalized]
            if (boundary == null) {
                violations += "allowed boundary type is absent from the compiler ABI: $normalized"
            } else {
                put(normalized, boundary.name)
            }
        }
    }
    val markedBoundaries = exactBoundaries.values.filter { it in ownerNames }.sorted()
    markedBoundaries.forEach { violations += "allowed boundary type is a marked owner: $it" }

    val normalizedDataClassNames = dataClassNames?.let { names ->
        normalizeExactDiscoveryNames(names, "Compiler-derived data class")
    }
    val resolvedDataClassNames = normalizedDataClassNames.orEmpty().mapNotNullTo(linkedSetOf()) { normalized ->
        classesByNormalizedName[normalized]?.name?.takeIf(ownerNames::contains)
    }

    val relevantMembers = owners.associateWith { owner ->
        requireUniqueNonBlankDiscovery(
            owner.members.map(CompilerApiMember::abiSignature),
            "Compiler ABI member signature for ${owner.name}",
        )
        val dataFunctions = if (owner.name in resolvedDataClassNames) {
            owner.generatedDataFunctionSignatures()
        } else {
            emptySet()
        }
        owner.members.filterNot { member -> member.isCompilerGenerated(owner, dataFunctions) }
    }
    val excludedMembers = relevantMembers.mapValues { (_, members) ->
        members.filter { member ->
            exclusionAnnotation != null && member.annotations.any { sameQualifiedName(it, exclusionAnnotation) }
        }
    }
    val includedMembers = relevantMembers.mapValues { (owner, members) ->
        members - excludedMembers.getValue(owner).toSet()
    }
    val reachedBoundaries = linkedSetOf<String>()
    val reachedExcludedTypes = linkedSetOf<String>()

    fun validateReachableType(owner: CompilerApiClass, reachable: String, excludedKey: String?) {
        val normalized = normalizeQualifiedName(reachable)
        val boundary = exactBoundaries[normalized]
        val internalType = classesByNormalizedName[normalized]
        when {
            boundary != null -> reachedBoundaries += boundary
            internalType != null && internalType.name !in ownerNames ->
                violations += "marked owner ${owner.name} exposes unmarked compiler API type ${internalType.name}"
            internalType != null -> Unit
            normalized in normalizedExcludedTypes && excludedKey != null -> reachedExcludedTypes += normalized
            normalized in normalizedExcludedTypes ->
                violations += "marked owner ${owner.name} exposes member requiring exclusion annotation: $reachable"
            normalized in supportedExternalTypes -> Unit
            excludedKey != null -> violations +=
                "excluded member $excludedKey exposes unsupported external or SPI type $reachable " +
                    "as an unknown exclusion category"
            else -> violations += "marked owner ${owner.name} exposes unsupported external or SPI type $reachable"
        }
    }

    owners.forEach { owner ->
        if (owner.modality == AbiModality.SEALED.name) {
            val unmarkedChildren = classes.values.filter { child ->
                child.superTypes.classReferences.any { sameQualifiedName(it, owner.name) }
            }
                .map(CompilerApiClass::name).filterNot(ownerNames::contains).sorted()
            unmarkedChildren.forEach { child ->
                violations += "marked sealed owner ${owner.name} has unmarked public child $child"
            }
        }
        (owner.superTypes.classReferences + owner.typeBounds.classReferences).forEach { reachable ->
            validateReachableType(owner, reachable, null)
        }
        includedMembers.getValue(owner).forEach { member ->
            member.reachableTypes.forEach { reachable -> validateReachableType(owner, reachable, null) }
        }
        excludedMembers.getValue(owner).forEach { member ->
            val key = member.stableKey(owner.name)
            val categories = member.reachableTypes.mapTo(linkedSetOf(), ::normalizeQualifiedName)
                .intersect(normalizedExcludedTypes)
            if (categories.isEmpty()) {
                violations += "member exclusion annotation is unneeded on $key"
            }
            member.reachableTypes.forEach { reachable -> validateReachableType(owner, reachable, key) }
        }
    }
    val staleBoundaries = exactBoundaries.values.filterNot(reachedBoundaries::contains).sorted()
    staleBoundaries.forEach { violations += "allowed boundary type is stale or unreachable: $it" }
    (normalizedExcludedTypes - reachedExcludedTypes).forEach { excludedType ->
        violations += "required member exclusion category is stale or unreachable: $excludedType"
    }
    check(violations.isEmpty()) {
        violations.joinToString(separator = "\n- ", prefix = "Cross-language API discovery violations:\n- ")
    }

    val reports = owners.map { owner ->
        val memberKeys = includedMembers.getValue(owner).asSequence()
            .map { member -> member.stableKey(owner.name) }
            .toList()
        requireUniqueNonBlankDiscovery(memberKeys, "Compiler-derived member for ${owner.name}")
        val objectKey = owner.takeIf {
            it.kind == AbiClassKind.OBJECT.name &&
                normalizeQualifiedName(it.name) in normalizedSingletonObjects
        }?.stableObjectKey()
        val capabilityKeys = (memberKeys + listOfNotNull(objectKey)).sorted()
        requireUniqueNonBlankDiscovery(capabilityKeys, "Compiler-derived capability for ${owner.name}")
        CrossLanguageApiOwner(owner.name, capabilityKeys)
    }
    val allKeys = reports.flatMap(CrossLanguageApiOwner::capabilityKeys)
    requireUniqueNonBlankDiscovery(allKeys, "Compiler-derived capability")
    val excludedKeys = owners.flatMap { owner ->
        excludedMembers.getValue(owner).map { it.stableKey(owner.name) }
    }.sorted()
    requireUniqueNonBlankDiscovery(excludedKeys, "Excluded compiler-derived member")
    check(allKeys.intersect(excludedKeys.toSet()).isEmpty()) {
        "Compiler-derived capabilities cannot be both included and excluded"
    }
    return CrossLanguageApiReport(
        libraryUniqueName = library.uniqueName,
        signatureVersion = library.signatureVersion,
        markerAnnotation = markerAnnotation,
        boundaryTypes = exactBoundaries.values.sorted(),
        memberExclusionAnnotation = exclusionAnnotation,
        excludedReachableTypes = normalizedExcludedTypes.sorted(),
        excludedMemberKeys = excludedKeys,
        dataClassMetadataAvailable = normalizedDataClassNames != null,
        dataClassNames = resolvedDataClassNames.sorted(),
        owners = reports,
    )
}

private fun CompilerApiClass.stableObjectKey(): String =
    "common|owner=$name|kind=object|abi=$abiSignature"

internal data class CompilerApiLibrary(
    val uniqueName: String,
    val signatureVersion: Int,
    val classes: List<CompilerApiClass>,
)

internal data class CompilerApiClass(
    val name: String,
    val abiSignature: String,
    val enclosingClass: String? = null,
    val annotations: Set<String> = emptySet(),
    val kind: String = AbiClassKind.CLASS.name,
    val modality: String = AbiModality.FINAL.name,
    val superTypes: CompilerApiType = CompilerApiType(),
    val typeBounds: CompilerApiType = CompilerApiType(),
    val members: List<CompilerApiMember> = emptyList(),
)

internal data class CompilerApiType(
    val rendered: String = "",
    val classReferences: Set<String> = emptySet(),
)

internal sealed interface CompilerApiMember {
    val name: String
    val abiSignature: String
    val annotations: Set<String>
    val reachableTypes: Set<String>

    fun stableKey(owner: String): String
}

internal data class CompilerApiFunction(
    override val name: String,
    override val abiSignature: String,
    val parameters: List<CompilerApiParameter>,
    val returnType: CompilerApiType,
    override val annotations: Set<String> = emptySet(),
    val isConstructor: Boolean = false,
    val isSuspend: Boolean = false,
    val typeBounds: CompilerApiType = CompilerApiType(),
) : CompilerApiMember {
    override val reachableTypes: Set<String>
        get() = parameters.flatMapTo(linkedSetOf()) { it.type.classReferences } +
            returnType.classReferences + typeBounds.classReferences

    override fun stableKey(owner: String): String = buildString {
        append("common|owner=").append(owner)
        append("|kind=").append(if (isConstructor) "constructor" else "function")
        append("|abi=").append(abiSignature)
        append("|return=").append(returnType.rendered)
        append("|suspend=").append(isSuspend)
        append("|parameters=").append(parameters.joinToString(",", "[", "]") { it.render() })
    }
}

internal data class CompilerApiParameter(
    val type: CompilerApiType,
    val kind: String = AbiValueParameterKind.REGULAR.name,
    val hasDefault: Boolean = false,
    val isVararg: Boolean = false,
) {
    fun render(): String = "$kind:${type.rendered}:default=$hasDefault:vararg=$isVararg"
}

internal data class CompilerApiProperty(
    override val name: String,
    override val abiSignature: String,
    val propertyKind: String,
    val type: CompilerApiType,
    override val annotations: Set<String> = emptySet(),
    val setterTypes: Set<String> = emptySet(),
) : CompilerApiMember {
    override val reachableTypes: Set<String> get() = type.classReferences + setterTypes

    override fun stableKey(owner: String): String =
        "common|owner=$owner|kind=property|abi=$abiSignature|propertyKind=$propertyKind|type=${type.rendered}"
}

internal data class CompilerApiEnumEntry(
    override val name: String,
    override val abiSignature: String,
    override val annotations: Set<String> = emptySet(),
) : CompilerApiMember {
    override val reachableTypes: Set<String> = emptySet()

    override fun stableKey(owner: String): String =
        "common|owner=$owner|kind=enum-entry|abi=$abiSignature"
}

private fun CompilerApiClass.reachableTypes(relevantMembers: List<CompilerApiMember>): Set<String> = buildSet {
    addAll(superTypes.classReferences)
    addAll(typeBounds.classReferences)
    relevantMembers.forEach { addAll(it.reachableTypes) }
}

private fun CompilerApiClass.generatedDataFunctionSignatures(): Set<String> {
    val functions = members.filterIsInstance<CompilerApiFunction>()
    val constructors = functions.filter(CompilerApiFunction::isConstructor)
    val copies = functions.filter { function ->
        function.name == "copy" && !function.isSuspend && function.parameters.isNotEmpty() &&
            function.parameters.all(CompilerApiParameter::hasDefault) &&
            function.returnType.isExactlyNonNullable(name) && constructors.any { constructor ->
                constructor.parameters.map { it.type.rendered } == function.parameters.map { it.type.rendered }
            }
    }
    if (copies.size != 1) return emptySet()
    val copy = copies.single()
    val components = copy.parameters.indices.map { index ->
        functions.singleOrNull { function ->
            function.name == "component${index + 1}" && !function.isSuspend &&
                function.parameters.isEmpty() &&
                function.returnType.rendered == copy.parameters[index].type.rendered
        } ?: return emptySet()
    }
    return (components + copy).mapTo(linkedSetOf(), CompilerApiFunction::abiSignature)
}

private fun CompilerApiMember.isCompilerGenerated(
    owner: CompilerApiClass,
    generatedDataFunctions: Set<String>,
): Boolean = when (this) {
    is CompilerApiEnumEntry -> false
    is CompilerApiProperty -> owner.kind == AbiClassKind.ENUM_CLASS.name && name == "entries" &&
        propertyKind == AbiPropertyKind.VAL.name && type.isParameterizationOf("kotlin.enums/EnumEntries", owner.name)
    is CompilerApiFunction ->
        abiSignature in generatedDataFunctions || name.endsWith("\$default") || isAnyOverride() ||
            owner.kind == AbiClassKind.ENUM_CLASS.name && isGeneratedEnumFunction(owner.name)
}

private fun CompilerApiFunction.isAnyOverride(): Boolean = when (name) {
    "equals" -> parameters.size == 1 && parameters.single().type.rendered == "kotlin/Any?" &&
        returnType.isExactlyNonNullable("kotlin/Boolean")
    "hashCode" -> parameters.isEmpty() && returnType.isExactlyNonNullable("kotlin/Int")
    "toString" -> parameters.isEmpty() && returnType.isExactlyNonNullable("kotlin/String")
    else -> false
}

private fun CompilerApiFunction.isGeneratedEnumFunction(owner: String): Boolean = when (name) {
    "values" -> parameters.isEmpty() && returnType.isParameterizationOf("kotlin/Array", owner)
    "valueOf" -> parameters.singleOrNull()?.type?.isExactlyNonNullable("kotlin/String") == true &&
        returnType.isExactlyNonNullable(owner)
    else -> false
}

private fun CompilerApiType.isParameterizationOf(container: String, argument: String): Boolean =
    normalizeQualifiedName(rendered.substringBefore('<')) == normalizeQualifiedName(container) &&
        classReferences.mapTo(linkedSetOf(), ::normalizeQualifiedName) == setOf(
            normalizeQualifiedName(container),
            normalizeQualifiedName(argument),
        )

private fun CompilerApiType.isExactlyNonNullable(name: String): Boolean =
    normalizeQualifiedName(rendered.removeSuffix("!!")) == normalizeQualifiedName(name) &&
        classReferences.mapTo(linkedSetOf(), ::normalizeQualifiedName) == setOf(normalizeQualifiedName(name))

private fun AbiDeclarationContainer.toCompilerLibrary(
    uniqueName: String,
    signatureVersion: AbiSignatureVersion,
): CompilerApiLibrary {
    val classes = mutableListOf<CompilerApiClass>()
    fun collect(container: AbiDeclarationContainer, enclosingClass: String? = null) {
        container.declarations.filterIsInstance<AbiClass>().forEach { abiClass ->
            val name = abiClass.qualifiedName.toString()
            classes += CompilerApiClass(
                name = name,
                abiSignature = abiClass.requiredSignature(signatureVersion),
                enclosingClass = enclosingClass,
                annotations = abiClass.annotatedWith().mapTo(linkedSetOf()) { it.qualifiedName.toString() },
                kind = abiClass.kind.name,
                modality = abiClass.modality.name,
                superTypes = abiClass.superTypes.combineTypes(),
                typeBounds = abiClass.typeParameters.combineBounds(),
                members = abiClass.declarations.mapNotNull { declaration ->
                    declaration.toCompilerMember(name, signatureVersion)
                },
            )
            collect(abiClass, name)
        }
    }
    collect(this)
    return CompilerApiLibrary(uniqueName, signatureVersion.versionNumber, classes)
}

private fun AbiDeclaration.toCompilerMember(
    owner: String,
    signatureVersion: AbiSignatureVersion,
): CompilerApiMember? = when (this) {
    is AbiFunction -> CompilerApiFunction(
        name = qualifiedName.toString().removePrefix("$owner."),
        abiSignature = requiredSignature(signatureVersion),
        annotations = annotatedWith().mapTo(linkedSetOf()) { it.qualifiedName.toString() },
        parameters = valueParameters.map { parameter ->
            CompilerApiParameter(
                type = parameter.type.toCompilerType(),
                kind = parameter.kind.name,
                hasDefault = parameter.hasDefaultArg,
                isVararg = parameter.isVararg,
            )
        },
        returnType = normalizeCompilerFunctionReturnType(
            returnType = returnType?.toCompilerType(),
            owner = owner,
            isConstructor = isConstructor,
        ),
        isConstructor = isConstructor,
        isSuspend = isSuspend,
        typeBounds = typeParameters.combineBounds(),
    )
    is AbiProperty -> CompilerApiProperty(
        name = qualifiedName.toString().removePrefix("$owner."),
        abiSignature = requiredSignature(signatureVersion),
        annotations = annotatedWith().mapTo(linkedSetOf()) { it.qualifiedName.toString() },
        propertyKind = kind.name,
        type = normalizeCompilerFunctionReturnType(
            returnType = checkNotNull(getter) {
                "Public ABI property has no getter: $qualifiedName"
            }.returnType?.toCompilerType(),
            owner = owner,
            isConstructor = false,
        ),
        setterTypes = setter?.valueParameters.orEmpty()
            .flatMapTo(linkedSetOf()) { it.type.toCompilerType().classReferences },
    )
    is AbiEnumEntry -> CompilerApiEnumEntry(
        name = qualifiedName.toString().removePrefix("$owner."),
        abiSignature = requiredSignature(signatureVersion),
        annotations = annotatedWith().mapTo(linkedSetOf()) { it.qualifiedName.toString() },
    )
    is AbiClass -> null
}

internal fun normalizeCompilerFunctionReturnType(
    returnType: CompilerApiType?,
    owner: String,
    isConstructor: Boolean,
): CompilerApiType = returnType ?: if (isConstructor) {
    CompilerApiType(owner, setOf(owner))
} else {
    CompilerApiType("kotlin/Unit", setOf("kotlin/Unit"))
}

private fun AbiDeclaration.requiredSignature(version: AbiSignatureVersion): String =
    checkNotNull(signatures[version]) { "Compiler ABI declaration has no signature: $qualifiedName" }.also { signature ->
        check(signature.isNotBlank()) { "Compiler ABI declaration has a blank signature: $qualifiedName" }
    }

private fun List<AbiType>.combineTypes(): CompilerApiType =
    map(AbiType::toCompilerType).combineCompilerTypes()

private fun List<AbiTypeParameter>.combineBounds(): CompilerApiType =
    flatMap { it.upperBounds }.combineTypes()

private fun List<CompilerApiType>.combineCompilerTypes(): CompilerApiType = CompilerApiType(
    rendered = joinToString("&", transform = CompilerApiType::rendered),
    classReferences = flatMapTo(linkedSetOf(), CompilerApiType::classReferences),
)

private fun AbiType.toCompilerType(): CompilerApiType = when (this) {
    is AbiType.Simple -> {
        val classifier = when (val reference = classifierReference) {
            is AbiClassifierReference.ClassReference -> reference.className.toString()
            is AbiClassifierReference.TypeParameterReference -> "^${reference.tag}"
        }
        val renderedArguments = arguments.joinToString(",", "<", ">") { argument ->
            when (argument) {
                is AbiTypeArgument.StarProjection -> "*"
                is AbiTypeArgument.TypeProjection -> "${argument.variance.name}:${argument.type.toCompilerType().rendered}"
            }
        }.takeIf { arguments.isNotEmpty() }.orEmpty()
        val nullability = when (nullability) {
            AbiTypeNullability.MARKED_NULLABLE -> "?"
            AbiTypeNullability.DEFINITELY_NOT_NULL -> "!!"
            AbiTypeNullability.NOT_SPECIFIED -> ""
        }
        val nested = arguments.mapNotNull { argument ->
            (argument as? AbiTypeArgument.TypeProjection)?.type?.toCompilerType()
        }
        CompilerApiType(
            rendered = classifier + renderedArguments + nullability,
            classReferences = buildSet {
                if (classifierReference is AbiClassifierReference.ClassReference) add(classifier)
                nested.forEach { addAll(it.classReferences) }
            },
        )
    }
    is AbiType.Dynamic -> error("Dynamic types are not supported by the cross-language API")
    is AbiType.Error -> error("Compiler error types are not supported by the cross-language API")
}

private fun sameQualifiedName(left: String, right: String): Boolean =
    normalizeQualifiedName(left) == normalizeQualifiedName(right)

private fun normalizeQualifiedName(name: String): String = name.trim().replace('/', '.')

private fun normalizeExactDiscoveryNames(values: Iterable<String>, label: String): Set<String> {
    val normalized = values.map(::normalizeQualifiedName)
    requireUniqueNonBlankDiscovery(normalized, label)
    return normalized.toSortedSet()
}

private fun <T, K> Iterable<T>.associateByStrict(
    key: (T) -> K,
    label: String,
): Map<K, T> {
    val values = toList()
    val duplicates = values.groupingBy(key).eachCount().filterValues { it != 1 }.keys
    check(duplicates.isEmpty()) { "$label identities are duplicated: ${duplicates.sortedBy { it.toString() }}" }
    return values.associateBy(key)
}

private fun requireUniqueNonBlankDiscovery(values: Iterable<String>, label: String) {
    val list = values.toList()
    check(list.none(String::isBlank)) { "$label is blank" }
    val duplicates = list.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label identities are duplicated: $duplicates" }
}

private val supportedExternalTypes = setOf(
    "kotlin/Any",
    "kotlin/Array",
    "kotlin/AutoCloseable",
    "kotlin/Boolean",
    "kotlin/Byte",
    "kotlin/Char",
    "kotlin/Double",
    "kotlin/Enum",
    "kotlin/Exception",
    "kotlin/Float",
    "kotlin/Int",
    "kotlin/Long",
    "kotlin/Nothing",
    "kotlin/Pair",
    "kotlin/Short",
    "kotlin/String",
    "kotlin/Throwable",
    "kotlin/Triple",
    "kotlin/Unit",
    "kotlin.collections/Collection",
    "kotlin.collections/Iterable",
    "kotlin.collections/List",
    "kotlin.collections/Map",
    "kotlin.collections/Set",
    "kotlinx.coroutines.flow/StateFlow",
).mapTo(linkedSetOf(), ::normalizeQualifiedName)
