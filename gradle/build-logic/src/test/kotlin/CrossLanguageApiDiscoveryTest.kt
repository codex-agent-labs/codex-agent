import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class CrossLanguageApiDiscoveryTest {
    @Test
    fun `JVM metadata derives data classes without source parsing`() {
        val classes = Files.createTempDirectory("cross-language-data-classes")
        try {
            listOf("MetadataData", "MetadataRegular").forEach { nestedName ->
                val resource = "CrossLanguageApiDiscoveryTest\$$nestedName.class"
                val bytes = checkNotNull(javaClass.getResourceAsStream(resource)) { "Missing fixture $resource" }
                    .use { it.readBytes() }
                Files.write(classes.resolve("$nestedName.class"), bytes)
            }
            val names = readCompilerDataClassNames(classes.toFile())
            assertTrue(names.single().endsWith(".MetadataData"), names.toString())
        } finally {
            classes.toFile().deleteRecursively()
        }
    }

    @Test
    fun `marked owner automatically includes every current and future public member`() {
        val initial = discover(
            owner("fixture/Host", members = listOf(property("state", stringType), function("start"))),
        )
        val expanded = discover(
            owner(
                "fixture/Host",
                members = listOf(property("state", stringType), function("start"), function("refresh")),
            ),
        )

        assertEquals(2, initial.capabilityKeys.size)
        assertEquals(3, expanded.capabilityKeys.size)
        assertTrue(expanded.capabilityKeys.any { "fixture/Host.refresh|refresh()" in it })
        assertEquals(initial.capabilityKeys, initial.capabilityKeys.sorted())

        val companion = CompilerApiClass(
            name = "fixture/Host.Factory",
            abiSignature = "fixture/Host.Factory|null[0]",
            enclosingClass = "fixture/Host",
            kind = "OBJECT",
            members = listOf(function("create")),
        )
        val nested = discoverConfigured(
            listOf(owner("fixture/Host"), companion),
            companionObjectNames = setOf("fixture.Host.Factory"),
        )
        val futureNested = discoverConfigured(
            listOf(owner("fixture/Host"), companion.copy(members = companion.members + function("open"))),
            companionObjectNames = setOf("fixture.Host.Factory"),
        )
        assertEquals(listOf("fixture/Host", "fixture/Host.Factory"), nested.owners.map { it.name })
        assertEquals(nested.capabilityKeys.size + 1, futureNested.capabilityKeys.size)
        assertTrue(nested.capabilityKeys.none { "kind=object" in it })
    }

    @Test
    fun `non-companion objects add one capability and require exact JVM corroboration`() {
        val singleton = CompilerApiClass(
            name = "fixture/State.Ready",
            abiSignature = "fixture/State.Ready|null[0]",
            enclosingClass = "fixture/State",
            kind = "OBJECT",
            superTypes = type("fixture/State"),
        )
        val report = discoverConfigured(
            listOf(owner("fixture/State", modality = "SEALED"), singleton),
            singletonObjectNames = setOf("fixture.State.Ready"),
        )

        assertEquals(
            listOf("common|owner=fixture/State.Ready|kind=object|abi=fixture/State.Ready|null[0]"),
            report.owners.single { it.name == "fixture/State.Ready" }.capabilityKeys,
        )
        val futureSingleton = singleton.copy(
            name = "fixture/State.Future",
            abiSignature = "fixture/State.Future|null[0]",
        )
        val expanded = discoverConfigured(
            listOf(owner("fixture/State", modality = "SEALED"), singleton, futureSingleton),
            singletonObjectNames = setOf("fixture.State.Ready", "fixture.State.Future"),
        )
        assertEquals(report.capabilityKeys.size + 1, expanded.capabilityKeys.size)
        assertTrue(expanded.capabilityKeys.any { "owner=fixture/State.Future|kind=object" in it })
        assertFailure("lacks one exact JVM singleton/companion classification") {
            discover(owner("fixture/State", modality = "SEALED"), singleton)
        }
        assertFailure("marked non-object owner fixture/State.Ready has a JVM singleton/companion classification") {
            discoverConfigured(
                listOf(owner("fixture/State"), singleton.copy(kind = "CLASS")),
                singletonObjectNames = setOf("fixture.State.Ready"),
            )
        }
        assertFailure("identities overlap") {
            discoverConfigured(
                listOf(owner("fixture/State"), singleton),
                singletonObjectNames = setOf("fixture.State.Ready"),
                companionObjectNames = setOf("fixture/State.Ready"),
            )
        }
    }

    @Test
    fun `stable keys distinguish overload nullability suspend defaults and varargs`() {
        val report = discover(
            owner(
                "fixture/Host",
                members = listOf(
                    function("send", stringType, parameter = stringType),
                    function("send", stringType, parameter = nullableStringType),
                    function(
                        "sendMany",
                        stringType,
                        parameter = stringType,
                        isSuspend = true,
                        hasDefault = true,
                        isVararg = true,
                    ),
                ),
            ),
        )

        assertEquals(3, report.capabilityKeys.toSet().size)
        assertTrue(report.capabilityKeys.any { "kotlin/String?" in it })
        assertTrue(report.capabilityKeys.any { "suspend=true" in it && "default=true" in it && "vararg=true" in it })
    }

    @Test
    fun `ABI functions without an explicit return type normalize to Unit or their constructed owner`() {
        assertEquals(unitType, normalizeCompilerFunctionReturnType(null, "fixture/Host", isConstructor = false))
        assertEquals(
            type("fixture/Host"),
            normalizeCompilerFunctionReturnType(null, "fixture/Host", isConstructor = true),
        )
    }

    @Test
    fun `reachable compiler types and sealed children must be marked`() {
        val domain = CompilerApiClass("fixture/Domain", "fixture/Domain|null[0]")
        assertFailure("unmarked compiler API type fixture/Domain") {
            discover(owner("fixture/Host", members = listOf(property("domain", type("fixture/Domain")))), domain)
        }
        val recursive = discover(
            owner("fixture/Leaf"),
            owner("fixture/Domain", members = listOf(property("leaf", type("fixture/Leaf")))),
            owner("fixture/Host", members = listOf(property("domain", type("fixture/Domain")))),
        )
        assertEquals(listOf("fixture/Domain", "fixture/Host", "fixture/Leaf"), recursive.owners.map { it.name })

        val sealed = owner("fixture/State", modality = "SEALED")
        val child = CompilerApiClass(
            name = "fixture/State.Ready",
            abiSignature = "fixture/State.Ready|null[0]",
            superTypes = type("fixture/State"),
        )
        assertFailure("unmarked public child") {
            discover(sealed, child)
        }
        assertEquals(2, discover(sealed, child.copy(annotations = setOf(marker))).owners.size)
    }

    @Test
    fun `boundary types are exact reached and cannot be marked`() {
        val reached = discover(
            owner("fixture/Host", members = listOf(function("create", parameter = type("fixture/Platform")))),
            boundary("fixture/Platform"),
        )
        assertEquals(listOf("fixture/Platform"), reached.boundaryTypes)
        assertFailure("stale or unreachable") {
            discover(owner("fixture/Host"), boundary("fixture/Platform"))
        }
        assertFailure("is a marked owner") {
            discover(owner("fixture/Host", members = listOf(function("create", parameter = type("fixture/Platform")))),
                owner("fixture/Platform"))
        }
        assertFailure("unsupported external or SPI type fixture/OtherSpi") {
            discover(owner("fixture/Host", members = listOf(function("leak", parameter = type("fixture/OtherSpi")))),
                boundary("fixture/Platform"))
        }
    }

    @Test
    fun `strict compiler generated members are excluded without hiding ordinary names`() {
        val value = type("fixture/Value", "fixture/Value!!")
        val nonNullString = type("kotlin/String", "kotlin/String!!")
        val dataClass = owner(
            "fixture/Value",
            members = listOf(
                constructor(nonNullString),
                property("value", stringType),
                function("copy", value, nonNullString, hasDefault = true),
                function("component1", nonNullString),
                function("equals", type("kotlin/Boolean", "kotlin/Boolean!!"), nullableAnyType),
                function("hashCode", type("kotlin/Int", "kotlin/Int!!")),
                function("toString", nonNullString),
                function("component2", stringType),
            ),
        )
        val enumType = type("fixture/Mode", "fixture/Mode!!")
        val enumClass = owner(
            "fixture/Mode",
            kind = "ENUM_CLASS",
            members = listOf(
                CompilerApiEnumEntry("READY", "fixture/Mode.READY|null[0]"),
                property("entries", parameterized("kotlin.enums/EnumEntries", "fixture/Mode")),
                function("values", parameterized("kotlin/Array", "fixture/Mode")),
                function("valueOf", enumType, nonNullString),
            ),
        )
        val unavailable = discover(dataClass, enumClass)
        val report = discoverConfigured(
            listOf(dataClass, enumClass),
            dataClassNames = setOf("fixture.Value", "fixture.JvmOnlyData"),
        )

        assertEquals(6, unavailable.capabilityKeys.size)
        assertTrue(!unavailable.dataClassMetadataAvailable)
        assertEquals(4, report.capabilityKeys.size)
        assertTrue(report.dataClassMetadataAvailable)
        assertEquals(listOf("fixture/Value"), report.dataClassNames)
        assertTrue(report.capabilityKeys.any { "kind=constructor" in it })
        assertTrue(report.capabilityKeys.any { "kind=property" in it && "Value.value" in it })
        assertTrue(report.capabilityKeys.any { "kind=function" in it && "component2" in it })
        assertTrue(report.capabilityKeys.any { "kind=enum-entry" in it })
    }

    @Test
    fun `member exclusions are exact reported and mechanically checked`() {
        val excluded = function(
            "scoped",
            parameter = type("kotlinx.coroutines/CoroutineScope"),
            annotations = setOf(kotlinOnlyMarker),
        )
        val report = discoverConfigured(
            listOf(owner("fixture/Host", members = listOf(function("start"), excluded))),
            exclusionAnnotation = kotlinOnlyMarker,
            excludedTypes = setOf("kotlinx.coroutines.CoroutineScope"),
        )
        assertEquals(1, report.capabilityKeys.size)
        assertEquals(1, report.excludedMemberKeys.size)
        assertEquals(listOf("kotlinx.coroutines.CoroutineScope"), report.excludedReachableTypes)

        assertFailure("requiring exclusion annotation") {
            discoverConfigured(
                listOf(owner("fixture/Host", members = listOf(excluded.copy(annotations = emptySet())))),
                exclusionAnnotation = kotlinOnlyMarker,
                excludedTypes = setOf("kotlinx.coroutines/CoroutineScope"),
            )
        }
        assertFailure("annotation is unneeded") {
            discoverConfigured(
                listOf(owner("fixture/Host", members = listOf(function("plain", annotations = setOf(kotlinOnlyMarker))))),
                exclusionAnnotation = kotlinOnlyMarker,
                excludedTypes = setOf("kotlinx.coroutines/CoroutineScope"),
            )
        }
        val unknown = captureFailure {
            discoverConfigured(
                listOf(owner("fixture/Host", members = listOf(excluded.copy(returnType = type("fixture/OtherSpi"))))),
                exclusionAnnotation = kotlinOnlyMarker,
                excludedTypes = setOf("kotlinx.coroutines/CoroutineScope"),
            )
        }
        assertTrue("unknown exclusion category" in unknown.message.orEmpty())
        assertTrue("fixture/OtherSpi" in unknown.message.orEmpty())
        assertFailure("category is stale or unreachable") {
            discoverConfigured(
                listOf(owner("fixture/Host")),
                exclusionAnnotation = kotlinOnlyMarker,
                excludedTypes = setOf("kotlinx.coroutines/CoroutineScope"),
            )
        }
    }

    @Test
    fun `boundary violations are aggregated and sorted`() {
        val failure = captureFailure {
            discover(
                owner(
                    "fixture/Host",
                    members = listOf(
                        property("domain", type("fixture/Domain")),
                        function("leak", returnType = type("fixture/OtherSpi")),
                    ),
                ),
                owner("fixture/State", modality = "SEALED"),
                CompilerApiClass("fixture/Domain", "fixture/Domain|null[0]"),
                CompilerApiClass(
                    "fixture/State.Ready",
                    "fixture/State.Ready|null[0]",
                    superTypes = type("fixture/State"),
                ),
                boundary("fixture/Platform"),
            )
        }
        val violations = failure.message.orEmpty().lineSequence().drop(1).toList()
        assertEquals(violations.sorted(), violations)
        assertTrue(violations.any { "unmarked compiler API type fixture/Domain" in it })
        assertTrue(violations.any { "unsupported external or SPI type fixture/OtherSpi" in it })
        assertTrue(violations.any { "unmarked public child fixture/State.Ready" in it })
        assertTrue(violations.any { "stale or unreachable: fixture/Platform" in it })
    }

    @Test
    fun `duplicate compiler identities fail closed`() {
        assertFailure("class identities are duplicated") {
            discover(owner("fixture/Host"), owner("fixture/Host"))
        }
        val duplicate = function("start")
        assertFailure("identities are duplicated") {
            discover(owner("fixture/Host", members = listOf(duplicate, duplicate)))
        }
    }

    private fun discover(vararg classes: CompilerApiClass): CrossLanguageApiReport =
        discoverConfigured(classes.toList())

    private fun discoverConfigured(
        classes: List<CompilerApiClass>,
        exclusionAnnotation: String? = null,
        excludedTypes: Set<String> = emptySet(),
        dataClassNames: Set<String>? = null,
        singletonObjectNames: Set<String> = emptySet(),
        companionObjectNames: Set<String> = emptySet(),
    ): CrossLanguageApiReport =
        discoverCrossLanguageApi(
            library = CompilerApiLibrary("fixture", 2, classes),
            markerAnnotation = marker,
            allowedBoundaryTypes = if (classes.any { it.name == "fixture/Platform" }) {
                setOf("fixture.Platform")
            } else {
                emptySet()
            },
            memberExclusionAnnotation = exclusionAnnotation,
            requiredExcludedReachableTypes = excludedTypes,
            dataClassNames = dataClassNames,
            singletonObjectNames = singletonObjectNames,
            companionObjectNames = companionObjectNames,
        )

    private fun owner(
        name: String,
        members: List<CompilerApiMember> = emptyList(),
        kind: String = "CLASS",
        modality: String = "FINAL",
    ): CompilerApiClass = CompilerApiClass(
        name = name,
        abiSignature = "$name|null[0]",
        annotations = setOf(marker.replace('.', '/')),
        kind = kind,
        modality = modality,
        members = members,
    )

    private fun boundary(name: String): CompilerApiClass =
        CompilerApiClass(name, "$name|null[0]")

    private fun property(name: String, type: CompilerApiType): CompilerApiProperty =
        CompilerApiProperty(name, "fixture/Value.$name|{}$name[0]", "VAL", type)

    private fun constructor(parameter: CompilerApiType): CompilerApiFunction =
        CompilerApiFunction(
            name = "<init>",
            abiSignature = "fixture/Value.<init>|<init>(${parameter.rendered}){}[0]",
            parameters = listOf(CompilerApiParameter(parameter)),
            returnType = type("fixture/Value"),
            isConstructor = true,
        )

    private fun function(
        name: String,
        returnType: CompilerApiType = unitType,
        parameter: CompilerApiType? = null,
        isSuspend: Boolean = false,
        hasDefault: Boolean = false,
        isVararg: Boolean = false,
        annotations: Set<String> = emptySet(),
    ): CompilerApiFunction {
        val parameters = parameter?.let {
            listOf(CompilerApiParameter(it, hasDefault = hasDefault, isVararg = isVararg))
        }.orEmpty()
        return CompilerApiFunction(
            name = name,
            abiSignature = "fixture/Host.$name|$name(${parameters.joinToString { it.type.rendered }}){}[0]",
            parameters = parameters,
            returnType = returnType,
            annotations = annotations,
            isSuspend = isSuspend,
        )
    }

    private fun assertFailure(message: String, block: () -> Unit) {
        val failure = captureFailure(block)
        assertTrue(failure.message.orEmpty().contains(message), failure.message)
    }

    private fun captureFailure(block: () -> Unit): IllegalStateException =
        assertFailsWith<IllegalStateException>(block = block)

    private companion object {
        const val marker = "fixture.CodexBindingApi"
        const val kotlinOnlyMarker = "fixture.CodexBindingApiKotlinOnly"
        fun type(reference: String, rendered: String = reference): CompilerApiType =
            CompilerApiType(rendered, setOf(reference))

        fun parameterized(container: String, argument: String): CompilerApiType =
            CompilerApiType("$container<INVARIANT:$argument>", setOf(container, argument))

        val unitType = type("kotlin/Unit")
        val stringType = type("kotlin/String")
        val nullableStringType = type("kotlin/String", "kotlin/String?")
        val nullableAnyType = type("kotlin/Any", "kotlin/Any?")
        val booleanType = type("kotlin/Boolean")
        val intType = type("kotlin/Int")
    }

    private data class MetadataData(val value: String)

    private class MetadataRegular
}
