import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.file.Files
import java.util.concurrent.CompletableFuture
import java.util.concurrent.Executor
import java.util.function.Consumer
import java.util.jar.JarEntry
import java.util.jar.JarOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.jetbrains.org.objectweb.asm.ClassReader
import org.jetbrains.org.objectweb.asm.ClassVisitor
import org.jetbrains.org.objectweb.asm.ClassWriter
import org.jetbrains.org.objectweb.asm.FieldVisitor
import org.jetbrains.org.objectweb.asm.MethodVisitor
import org.jetbrains.org.objectweb.asm.Opcodes

class CrossLanguageJavaBindingEvidenceTest {
    @Test
    fun `canonical owner names map dotted packages and nested classes to JVM names`() {
        assertEquals("io/github/example/CodexHost", canonicalOwnerToJvmInternalName("io.github.example/CodexHost"))
        assertEquals("io/github/example/Response\$Companion", canonicalOwnerToJvmInternalName("io.github.example/Response.Companion"))
        assertEquals("io.github.example/Response.Companion", "io/github/example/Response.Companion".toCanonicalClassifierName())
        assertEquals("kotlin/String", "kotlin/String".toCanonicalClassifierName())
    }

    @Test
    fun `compiler metadata and exact artifacts deterministically cover ordinary and exceptional members`() =
        withArtifacts { artifacts ->
            val first = evidence(artifacts)
            val second = evidence(artifacts)

            assertEquals(first, second)
            assertEquals(CAPABILITIES.sorted(), first.capabilityClaims.map(JavaBindingCapabilityClaim::capabilityKey))
            assertEquals(9, first.capabilityClaims.size)
            assertEquals(11, first.publicSymbols.size)
            assertEquals(artifacts.coreJvm.readBytes().inputStream().releaseDigest(), first.digests.coreJvmJarSha256)
            assertTrue(first.publicSymbols.all { "|genericSha256=" in it })
            assertTrue(first.capabilityClaims.single { it.capabilityKey == SUSPEND }.publicSymbols.single()
                .contains("#loadAsync"))
            assertEquals(2, first.capabilityClaims.single { it.capabilityKey == STATE_FLOW }.publicSymbols.size)
            assertEquals(2, first.capabilityClaims.single { it.capabilityKey == HOST }.publicSymbols.size)
            assertTrue(first.capabilityClaims.single { it.capabilityKey == OBJECT }.publicSymbols.single()
                .contains("#INSTANCE:"))
        }

    @Test
    fun `canonical object requires Kotlin object metadata and its exact INSTANCE field`() = withArtifacts { artifacts ->
        assertFailure("Canonical Java capability ABI identity mismatch") {
            evidence(
                artifacts,
                capabilities = CAPABILITIES - OBJECT + OBJECT.replace(
                    "abi=JavaFixtureSingleton|null[0]",
                    "abi=JavaFixtureSingleton.INSTANCE|null[0]",
                ),
            )
        }
        assertFailure("Canonical Java object ABI signature mismatch") {
            evidence(artifacts, capabilities = CAPABILITIES - OBJECT + OBJECT.replace("|null[0]", "|wrong[0]"))
        }
        assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
            evidence(artifacts, capabilities = CAPABILITIES - OBJECT + OBJECT.replace(
                "owner=JavaFixtureSingleton|kind=object|abi=JavaFixtureSingleton",
                "owner=JavaFixture|kind=object|abi=JavaFixture",
            ))
        }

        listOf(
            FieldMutation.remove(JavaFixtureSingleton::class.java, "INSTANCE", SINGLETON_DESCRIPTOR) to
                "missing Java member",
            FieldMutation.makePrivate(JavaFixtureSingleton::class.java, "INSTANCE", SINGLETON_DESCRIPTOR) to
                "not public",
            FieldMutation.makeSynthetic(JavaFixtureSingleton::class.java, "INSTANCE", SINGLETON_DESCRIPTOR) to
                "synthetic",
            FieldMutation.removeStatic(JavaFixtureSingleton::class.java, "INSTANCE", SINGLETON_DESCRIPTOR) to
                "not static final",
            FieldMutation.removeFinal(JavaFixtureSingleton::class.java, "INSTANCE", SINGLETON_DESCRIPTOR) to
                "not static final",
            FieldMutation.replaceDescriptor(
                JavaFixtureSingleton::class.java,
                "INSTANCE",
                SINGLETON_DESCRIPTOR,
                "Ljava/lang/Object;",
            ) to "missing Java member",
        ).forEach { (mutation, expected) ->
            withArtifacts(coreJvmMutations = listOf(mutation)) { changed ->
                assertFailure(expected) { evidence(changed) }
            }
            withArtifacts(coreAndroidMutations = listOf(mutation)) { changed ->
                assertFailure(expected) { evidence(changed) }
            }
        }
    }

    @Test
    fun `ordinary member must have an exact Android counterpart`() = withArtifacts(
        coreAndroidMutations = listOf(MethodMutation.remove(JavaFixture::class.java, "echo", ECHO_DESCRIPTOR)),
    ) { artifacts ->
        assertFailure("core Android AAR/classes.jar is missing Java member") { evidence(artifacts) }
    }

    @Test
    fun `ordinary canonical parameter return property default and vararg semantics are exact`() =
        withArtifacts { artifacts ->
            listOf(
                FUNCTION.replace("echo(kotlin.String)", "echo(kotlin.Int)")
                    .replace("REGULAR:kotlin/String!!", "REGULAR:kotlin/Int!!"),
                FUNCTION.replace("return=kotlin/String!!", "return=kotlin/Int!!"),
                PROPERTY.replace("type=kotlin/String!!", "type=kotlin/Int!!"),
                CONSTRUCTOR.replace("default=false", "default=true"),
                CONSTRUCTOR.replace("vararg=false", "vararg=true"),
            ).forEach { replacement ->
                assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
                    evidence(artifacts, capabilities = CAPABILITIES - CAPABILITIES.first { capability ->
                        capability.substringBefore("|abi=") == replacement.substringBefore("|abi=") &&
                            capability.substringAfter("|abi=").substringBefore('|').substringAfterLast('.') ==
                            replacement.substringAfter("|abi=").substringBefore('|').substringAfterLast('.')
                    } + replacement)
                }
            }
        }

    @Test
    fun `ordinary Android descriptor drift fails counterpart proof`() = withArtifacts(
        coreAndroidMutations = listOf(
            MethodMutation.replaceDescriptor(
                JavaFixture::class.java,
                "echo",
                ECHO_DESCRIPTOR,
                "(I)Ljava/lang/String;",
            ),
        ),
    ) { artifacts ->
        assertFailure("core Android AAR/classes.jar is missing Java member") { evidence(artifacts) }
    }

    @Test
    fun `ordinary generic Java ABI must match canonical metadata in both artifacts`() = withArtifacts { artifacts ->
        assertEquals(10, evidence(artifacts, capabilities = CAPABILITIES + GENERIC_FUNCTION).capabilityClaims.size)
        val wrongGeneric = MethodMutation.replaceSignature(
            JavaFixture::class.java,
            "genericEcho",
            GENERIC_ECHO_DESCRIPTOR,
            "(Ljava/util/List<Ljava/lang/Integer;>;)Ljava/util/List<Ljava/lang/Integer;>;",
        )
        withArtifacts(coreJvmMutations = listOf(wrongGeneric), coreAndroidMutations = listOf(wrongGeneric)) { wrong ->
            assertFailure("ordinary Java ABI does not match canonical types") {
                evidence(wrong, capabilities = CAPABILITIES + GENERIC_FUNCTION)
            }
        }
    }

    @Test
    fun `ordinary read-only collection parameters accept compiler OUT and elided projections`() =
        withArtifacts { artifacts ->
            val result = evidence(
                artifacts,
                capabilities = CAPABILITIES + GENERIC_FUNCTION + READ_ONLY_COLLECTION_PARAMETERS,
            )

            assertTrue(result.capabilityClaims.any { it.capabilityKey == GENERIC_FUNCTION })
            assertTrue(result.capabilityClaims.any { it.capabilityKey == READ_ONLY_COLLECTION_PARAMETERS })
        }

    @Test
    fun `ordinary mutable collection and Map key parameters reject OUT projections`() {
        listOf(
            Triple(
                MUTABLE_COLLECTION_PARAMETER,
                MUTABLE_COLLECTION_DESCRIPTOR,
                "(Ljava/util/List<+LJavaFixtureValue;>;)V",
            ),
            Triple(
                MAP_KEY_PARAMETER,
                MAP_KEY_DESCRIPTOR,
                "(Ljava/util/Map<+LJavaFixtureValue;Ljava/lang/String;>;)V",
            ),
        ).forEach { (capability, descriptor, wrongSignature) ->
            val mutation = MethodMutation.replaceSignature(
                JavaFixture::class.java,
                if (capability == MUTABLE_COLLECTION_PARAMETER) "mutableCollectionParameter" else "mapKeyParameter",
                descriptor,
                wrongSignature,
            )
            withArtifacts(coreJvmMutations = listOf(mutation), coreAndroidMutations = listOf(mutation)) { artifacts ->
                assertFailure("ordinary Java ABI does not match canonical types") {
                    evidence(artifacts, capabilities = CAPABILITIES + capability)
                }
            }
        }
    }

    @Test
    fun `ordinary read-only parameter compatibility rejects IN classifier and element drift`() {
        listOf(
            "(Ljava/util/Map<Ljava/lang/String;+LJavaFixtureValue;>;" +
                "Ljava/util/List<-LJavaFixtureValue;>;Ljava/util/Set<+LJavaFixtureValue;>;)V",
            "(Ljava/util/Map<Ljava/lang/String;+LJavaFixtureValue;>;" +
                "Ljava/util/Set<+LJavaFixtureValue;>;Ljava/util/Set<+LJavaFixtureValue;>;)V",
            "(Ljava/util/Map<Ljava/lang/String;+Ljava/lang/Integer;>;" +
                "Ljava/util/List<+LJavaFixtureValue;>;Ljava/util/Set<+LJavaFixtureValue;>;)V",
        ).forEach { wrongSignature ->
            val mutation = MethodMutation.replaceSignature(
                JavaFixture::class.java,
                "readOnlyCollectionParameters",
                READ_ONLY_COLLECTIONS_DESCRIPTOR,
                wrongSignature,
            )
            withArtifacts(coreJvmMutations = listOf(mutation), coreAndroidMutations = listOf(mutation)) { artifacts ->
                assertFailure("ordinary Java ABI does not match canonical types") {
                    evidence(artifacts, capabilities = CAPABILITIES + READ_ONLY_COLLECTION_PARAMETERS)
                }
            }
        }
    }

    @Test
    fun `ordinary property and return types reject compiler OUT projections`() {
        listOf(
            Triple(READ_ONLY_COLLECTION_RETURN, "readOnlyCollectionReturn", "()Ljava/util/List<+LJavaFixtureValue;>;"),
            Triple(READ_ONLY_COLLECTION_PROPERTY, "getReadOnlyCollectionProperty", "()Ljava/util/List<+LJavaFixtureValue;>;"),
        ).forEach { (capability, methodName, wrongSignature) ->
            val mutation = MethodMutation.replaceSignature(
                JavaFixture::class.java,
                methodName,
                READ_ONLY_COLLECTION_RESULT_DESCRIPTOR,
                wrongSignature,
            )
            withArtifacts(coreJvmMutations = listOf(mutation), coreAndroidMutations = listOf(mutation)) { artifacts ->
                assertFailure("ordinary Java ABI does not match canonical types") {
                    evidence(artifacts, capabilities = CAPABILITIES + capability)
                }
            }
        }
    }

    @Test
    fun `ordinary member must remain public and non-synthetic`() {
        listOf(
            MethodMutation.makePrivate(JavaFixture::class.java, "echo", ECHO_DESCRIPTOR) to "not public",
            MethodMutation.makeSynthetic(JavaFixture::class.java, "echo", ECHO_DESCRIPTOR) to "synthetic",
            MethodMutation.makeBridge(JavaFixture::class.java, "echo", ECHO_DESCRIPTOR) to "bridge",
        ).forEach { (mutation, expected) ->
            withArtifacts(coreJvmMutations = listOf(mutation)) { artifacts ->
                assertFailure(expected) { evidence(artifacts) }
            }
        }
    }

    @Test
    fun `class entry path and bytecode name must agree`() = withArtifacts(
        coreJvmEntryNames = mapOf(JavaFixture::class.java to "wrong/JavaFixture.class"),
    ) { artifacts ->
        assertFailure("class entry path does not match bytecode name") { evidence(artifacts) }
    }

    @Test
    fun `generic signature is counterpart evidence not decoration`() = withArtifacts(
        coreAndroidMutations = listOf(
            MethodMutation.replaceSignature(
                JavaProjectionFixture::class.java,
                "loadAsync",
                FUTURE_DESCRIPTOR,
                "(LJavaFixture;)Ljava/util/concurrent/CompletableFuture<Ljava/lang/String;>;" +
                    "^Ljava/lang/Exception;",
            ),
        ),
    ) { artifacts ->
        assertFailure("projection differs between core JVM JAR and Android AAR") { evidence(artifacts) }
    }

    @Test
    fun `both Future artifacts with the same wrong value type fail canonical semantics`() {
        val wrongFuture = MethodMutation.replaceSignature(
            JavaProjectionFixture::class.java,
            "loadAsync",
            FUTURE_DESCRIPTOR,
            "(LJavaFixture;)Ljava/util/concurrent/CompletableFuture<Ljava/lang/Integer;>;",
        )
        withArtifacts(coreJvmMutations = listOf(wrongFuture), coreAndroidMutations = listOf(wrongFuture)) { artifacts ->
            assertFailure("async projection type does not match canonical return") { evidence(artifacts) }
        }
    }

    @Test
    fun `suspend projection parameters must match canonical metadata`() = withArtifacts { artifacts ->
        val capabilities = CAPABILITIES + SUSPEND_PARAMETER
        val correctAliases = aliases() + JavaSuspendBindingAlias(SUSPEND_PARAMETER, PARAMETER_FUTURE_METHOD)
        assertTrue(evidence(artifacts, capabilities, correctAliases).capabilityClaims.any {
            it.capabilityKey == SUSPEND_PARAMETER
        })

        val wrongAliases = aliases() + JavaSuspendBindingAlias(SUSPEND_PARAMETER, WRONG_PARAMETER_FUTURE_METHOD)
        assertFailure("receiver/parameters do not match the canonical member") {
            evidence(artifacts, capabilities, wrongAliases)
        }
    }

    @Test
    fun `generic suspend type parameters use the compiler ABI nullability grammar`() = withArtifacts { artifacts ->
        val result = evidence(
            artifacts,
            capabilities = CAPABILITIES + GENERIC_SUSPEND,
            aliases = aliases() + JavaSuspendBindingAlias(GENERIC_SUSPEND, GENERIC_FUTURE_METHOD),
        )

        assertTrue(result.capabilityClaims.any { it.capabilityKey == GENERIC_SUSPEND })

        val wrongBound = GENERIC_SUSPEND.replace("§<kotlin.Any>", "§<kotlin.String>")
        assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
            evidence(
                artifacts,
                capabilities = CAPABILITIES + wrongBound,
                aliases = aliases() + JavaSuspendBindingAlias(wrongBound, GENERIC_FUTURE_METHOD),
            )
        }
    }

    @Test
    fun `definitely non-null type parameter use sites retain the compiler ABI marker`() =
        withArtifacts { artifacts ->
            val result = evidence(
                artifacts,
                capabilities = CAPABILITIES + DEFINITELY_NON_NULL_GENERIC_SUSPEND,
                aliases = aliases() + JavaSuspendBindingAlias(
                    DEFINITELY_NON_NULL_GENERIC_SUSPEND,
                    DEFINITELY_NON_NULL_GENERIC_FUTURE_METHOD,
                ),
            )

            assertTrue(result.capabilityClaims.any { it.capabilityKey == DEFINITELY_NON_NULL_GENERIC_SUSPEND })

            val missingMarker = DEFINITELY_NON_NULL_GENERIC_SUSPEND.replace("^A1!!", "^A1")
            assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
                evidence(
                    artifacts,
                    capabilities = CAPABILITIES + missingMarker,
                    aliases = aliases() + JavaSuspendBindingAlias(
                        missingMarker,
                        DEFINITELY_NON_NULL_GENERIC_FUTURE_METHOD,
                    ),
                )
            }
        }

    @Test
    fun `suspend alias must expose a typed Future without Continuation`() = withArtifacts { artifacts ->
        val wrongReturn = aliases().map { alias ->
            if (alias is JavaSuspendBindingAlias) alias.copy(futureMethod = WRONG_FUTURE_METHOD) else alias
        }
        assertFailure("must return CompletableFuture or CompletionStage") {
            evidence(artifacts, aliases = wrongReturn)
        }

        val continuation = aliases().map { alias ->
            if (alias is JavaSuspendBindingAlias) alias.copy(futureMethod = CONTINUATION_FUTURE_METHOD) else alias
        }
        assertFailure("exposes a Kotlin Continuation") {
            evidence(artifacts, aliases = continuation)
        }

        val raw = aliases().map { alias ->
            if (alias is JavaSuspendBindingAlias) alias.copy(futureMethod = RAW_FUTURE_METHOD) else alias
        }
        assertFailure("exposes a raw Future") { evidence(artifacts, aliases = raw) }
    }

    @Test
    fun `StateFlow alias must expose current value and AutoCloseable observation`() = withArtifacts { artifacts ->
        val raw = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) alias.copy(currentMethod = RAW_STATE_METHOD) else alias
        }
        assertFailure("exposes StateFlow directly") { evidence(artifacts, aliases = raw) }

        val notCloseable = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) alias.copy(observeMethod = NOT_CLOSEABLE_OBSERVE_METHOD) else alias
        }
        assertFailure("is not AutoCloseable") { evidence(artifacts, aliases = notCloseable) }

        val noConsumer = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) alias.copy(observeMethod = NO_CONSUMER_OBSERVE_METHOD) else alias
        }
        assertFailure("does not accept java.util.function.Consumer") { evidence(artifacts, aliases = noConsumer) }

        val kotlinFunction = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) alias.copy(observeMethod = KOTLIN_FUNCTION_OBSERVE_METHOD) else alias
        }
        assertFailure("exposes Kotlin flow/function types") { evidence(artifacts, aliases = kotlinFunction) }
    }

    @Test
    fun `both StateFlow artifacts with the same wrong current and Consumer types fail canonical semantics`() {
        val wrongCurrent = MethodMutation.replaceSignature(
            JavaProjectionFixture::class.java,
            "currentState",
            CURRENT_METHOD.descriptor,
            "(LJavaFixture;)Ljava/lang/Integer;",
        )
        withArtifacts(coreJvmMutations = listOf(wrongCurrent), coreAndroidMutations = listOf(wrongCurrent)) { artifacts ->
            assertFailure("current-value type does not match canonical element") { evidence(artifacts) }
        }

        val wrongConsumer = MethodMutation.replaceSignature(
            JavaProjectionFixture::class.java,
            "observeState",
            OBSERVE_METHOD.descriptor,
            "(LJavaFixture;Ljava/util/concurrent/Executor;" +
                "Ljava/util/function/Consumer<-Ljava/lang/Integer;>;)LJavaObservationFixture;",
        )
        withArtifacts(coreJvmMutations = listOf(wrongConsumer), coreAndroidMutations = listOf(wrongConsumer)) { artifacts ->
            assertFailure("observation parameters do not match canonical receiver/executor/element") { evidence(artifacts) }
        }
    }

    @Test
    fun `StateFlow observation return owner must be public`() = withArtifacts(
        coreJvmMutations = listOf(MethodMutation.makeClassPrivate(JavaObservationFixture::class.java)),
    ) { artifacts ->
        assertFailure("Java owner is not public") { evidence(artifacts) }
    }

    @Test
    fun `StateFlow projection receiver must match the canonical owner`() = withArtifacts { artifacts ->
        val wrongReceiverAliases = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) {
                alias.copy(currentMethod = WRONG_RECEIVER_CURRENT_METHOD, observeMethod = WRONG_RECEIVER_OBSERVE_METHOD)
            } else alias
        }
        assertFailure("current-value receiver does not match canonical owner") {
            evidence(artifacts, aliases = wrongReceiverAliases)
        }

        val wrongExecutorAliases = aliases().map { alias ->
            if (alias is JavaStateFlowBindingAlias) alias.copy(observeMethod = WRONG_EXECUTOR_OBSERVE_METHOD) else alias
        }
        assertFailure("observation parameters do not match canonical receiver/executor/element") {
            evidence(artifacts, aliases = wrongExecutorAliases)
        }
    }

    @Test
    fun `Companion capability requires a true static projection`() = withArtifacts { artifacts ->
        val companionInstance = aliases().map { alias ->
            if (alias is JavaStaticBindingAlias) alias.copy(staticMethod = COMPANION_INSTANCE_METHOD) else alias
        }
        assertFailure("is not a true static method") { evidence(artifacts, aliases = companionInstance) }
    }

    @Test
    fun `exception aliases are finite exact and a new exception fails closed`() = withArtifacts { artifacts ->
        assertFailure("missing=[$SUSPEND]") {
            evidence(artifacts, aliases = aliases().filterNot { it.capabilityKey == SUSPEND })
        }

        val newSuspend = SUSPEND.replace(".load|", ".refresh|").replace("load()", "refresh()")
        assertFailure("missing=[$newSuspend]") {
            evidence(artifacts, capabilities = CAPABILITIES + newSuspend)
        }
    }

    @Test
    fun `exceptional canonical declarations must exist and match both core artifacts`() {
        withArtifacts(
            coreJvmMutations = listOf(
                MethodMutation.remove(JavaFixture::class.java, "load", SUSPEND_DESCRIPTOR),
            ),
        ) { artifacts ->
            assertFailure("is missing Java member method load") { evidence(artifacts) }
        }
        withArtifacts(rewriteCanonicalStateFlow = false) { artifacts ->
            assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
                evidence(artifacts)
            }
        }
    }

    @Test
    fun `ordinary overload and global symbol reuse fail closed`() = withArtifacts { artifacts ->
        val overload = FUNCTION.replace("echo(kotlin.String)", "echo(kotlin.Int)")
            .replace("REGULAR:kotlin/String!!", "REGULAR:kotlin/Int!!")
        assertFailure("does not contain exactly one Kotlin declaration matching canonical semantics") {
            evidence(artifacts, capabilities = CAPABILITIES + overload)
        }

        val secondSuspend = SUSPEND.replace("load(){}[0]", "load(){}[1]")
        assertFailure("public symbols are reused") {
            evidence(
                artifacts,
                capabilities = CAPABILITIES + secondSuspend,
                aliases = aliases() + JavaSuspendBindingAlias(secondSuspend, FUTURE_METHOD),
            )
        }
    }

    @Test
    fun `both platform Host factories are required`() = withArtifacts(
        androidRuntimeMutations = listOf(
            MethodMutation.remove(AndroidFactoryFixture::class.java, "createHost", ANDROID_FACTORY_DESCRIPTOR),
        ),
    ) { artifacts ->
        assertFailure("Android runtime AAR/classes.jar is missing Java member") { evidence(artifacts) }
    }

    @Test
    fun `Host factories reject platform runtime and coroutine SPI`() {
        listOf(
            "LCodexPlatform;",
            "LPreparedCodexRuntime;",
            "Lkotlinx/coroutines/CoroutineScope;",
            "Lkotlin/coroutines/Continuation;",
            "Lexample/internal/runtime/InternalRuntime;",
        ).forEach { forbidden ->
            val descriptor = "(Ljava/nio/file/Path;$forbidden)LCodexHost;"
            withArtifacts(
                desktopRuntimeMutations = listOf(
                    MethodMutation.replaceDescriptor(
                        DesktopFactoryFixture::class.java,
                        "createHost",
                        DESKTOP_FACTORY_DESCRIPTOR,
                        descriptor,
                    ),
                ),
            ) { artifacts ->
                val forbiddenAlias = aliases().map { alias ->
                    if (alias is JavaHostFactoryBindingAlias) {
                        alias.copy(desktopFactory = method(DesktopFactoryFixture::class.java, "createHost", descriptor))
                    } else alias
                }
                assertFailure("exposes platform/runtime SPI") { evidence(artifacts, aliases = forbiddenAlias) }
            }
        }
    }

    private fun evidence(
        artifacts: JavaFixtureArtifacts,
        capabilities: List<String> = CAPABILITIES,
        aliases: List<JavaBindingExceptionalAlias> = aliases(),
    ): CrossLanguageJavaBindingStructuralEvidence = deriveCrossLanguageJavaBindingStructuralEvidence(
        capabilities,
        artifacts.coreJvm,
        artifacts.coreAndroid,
        artifacts.desktopRuntime,
        artifacts.androidRuntime,
        aliases,
    )

    private fun aliases(): List<JavaBindingExceptionalAlias> = listOf(
        JavaSuspendBindingAlias(SUSPEND, FUTURE_METHOD),
        JavaStateFlowBindingAlias(STATE_FLOW, CURRENT_METHOD, OBSERVE_METHOD),
        JavaHostFactoryBindingAlias(HOST, DESKTOP_FACTORY, ANDROID_FACTORY),
        JavaStaticBindingAlias(COMPANION, STATIC_COMPANION_METHOD),
    )

    private fun assertFailure(message: String, action: () -> Unit) {
        val failure = assertFailsWith<IllegalStateException>(block = action)
        assertTrue(failure.message.orEmpty().contains(message), "Expected '$message' in '${failure.message}'")
    }

    private fun withArtifacts(
        coreJvmMutations: List<ClassMutation> = emptyList(),
        coreAndroidMutations: List<ClassMutation> = emptyList(),
        desktopRuntimeMutations: List<ClassMutation> = emptyList(),
        androidRuntimeMutations: List<ClassMutation> = emptyList(),
        coreJvmEntryNames: Map<Class<*>, String> = emptyMap(),
        rewriteCanonicalStateFlow: Boolean = true,
        block: (JavaFixtureArtifacts) -> Unit,
    ) {
        val root = Files.createTempDirectory("java-binding-evidence").toFile()
        try {
            val coreClasses = listOf(
                JavaFixture::class.java,
                JavaFixture.Companion::class.java,
                JavaFixtureValue::class.java,
                JavaFixtureEnum::class.java,
                JavaFixtureSingleton::class.java,
                CodexHost::class.java,
                JavaProjectionFixture::class.java,
                JavaObservationFixture::class.java,
            )
            val rawStateDescriptor = MethodMutation.replaceDescriptor(
                JavaProjectionFixture::class.java,
                "rawState",
                "(LJavaFixture;)Ljava/lang/Object;",
                "(LJavaFixture;)Lkotlinx/coroutines/flow/StateFlow;",
            )
            val coreJvm = root.resolve("core.jar").also {
                writeJar(
                    it,
                    coreClasses,
                    listOf(rawStateDescriptor) + coreJvmMutations,
                    coreJvmEntryNames,
                    rewriteCanonicalStateFlow,
                )
            }
            val coreAndroid = root.resolve("core.aar").also {
                writeAar(it, coreClasses, listOf(rawStateDescriptor) + coreAndroidMutations, rewriteCanonicalStateFlow)
            }
            val desktop = root.resolve("desktop.jar").also {
                writeJar(
                    it,
                    listOf(DesktopFactoryFixture::class.java),
                    listOf(
                        MethodMutation.replaceDescriptor(
                            DesktopFactoryFixture::class.java,
                            "createHost",
                            FACTORY_DESCRIPTOR,
                            DESKTOP_FACTORY_DESCRIPTOR,
                        ),
                    ) + desktopRuntimeMutations,
                )
            }
            val android = root.resolve("android.aar").also {
                writeAar(
                    it,
                    listOf(AndroidFactoryFixture::class.java),
                    listOf(
                        MethodMutation.replaceDescriptor(
                            AndroidFactoryFixture::class.java,
                            "createHost",
                            FACTORY_DESCRIPTOR,
                            ANDROID_FACTORY_DESCRIPTOR,
                        ),
                    ) + androidRuntimeMutations,
                )
            }
            block(JavaFixtureArtifacts(coreJvm, coreAndroid, desktop, android))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun writeJar(
        file: File,
        classes: List<Class<*>>,
        mutations: List<ClassMutation>,
        entryNames: Map<Class<*>, String> = emptyMap(),
        rewriteCanonicalStateFlow: Boolean = false,
    ) {
        file.outputStream().use { output ->
            JarOutputStream(output).use { jar ->
                classes.sortedBy(Class<*>::getName).forEach { type ->
                    val source = classBytes(type).let { bytes ->
                        if (rewriteCanonicalStateFlow && type == JavaFixture::class.java) {
                            rewriteFixtureStateFlow(bytes)
                        } else bytes
                    }
                    val bytes = mutations.fold(source) { current, mutation ->
                        if (mutation.owner == type.name.replace('.', '/')) mutation.apply(current) else current
                    }
                    val entryName = entryNames[type] ?: type.name.replace('.', '/') + ".class"
                    jar.putNextEntry(JarEntry(entryName).apply { time = 0L })
                    jar.write(bytes)
                    jar.closeEntry()
                }
            }
        }
    }

    private fun writeAar(
        file: File,
        classes: List<Class<*>>,
        mutations: List<ClassMutation>,
        rewriteCanonicalStateFlow: Boolean = false,
    ) {
        val jar = ByteArrayOutputStream().also { output ->
            JarOutputStream(output).use { archive ->
                classes.sortedBy(Class<*>::getName).forEach { type ->
                    val source = classBytes(type).let { bytes ->
                        if (rewriteCanonicalStateFlow && type == JavaFixture::class.java) {
                            rewriteFixtureStateFlow(bytes)
                        } else bytes
                    }
                    val bytes = mutations.fold(source) { current, mutation ->
                        if (mutation.owner == type.name.replace('.', '/')) mutation.apply(current) else current
                    }
                    archive.putNextEntry(JarEntry(type.name.replace('.', '/') + ".class").apply { time = 0L })
                    archive.write(bytes)
                    archive.closeEntry()
                }
            }
        }.toByteArray()
        file.outputStream().use { output ->
            ZipOutputStream(output).use { aar ->
                aar.putNextEntry(ZipEntry("classes.jar").apply { time = 0L })
                aar.write(jar)
                aar.closeEntry()
            }
        }
    }

    private fun classBytes(type: Class<*>): ByteArray {
        val resource = "/${type.name.replace('.', '/')}.class"
        return checkNotNull(type.getResourceAsStream(resource)) { "Missing test class resource $resource" }.use { it.readBytes() }
    }

    private fun rewriteFixtureStateFlow(bytes: ByteArray): ByteArray {
        val writer = ClassWriter(0)
        var getterRewrites = 0
        var metadataRewrites = 0
        ClassReader(bytes).accept(object : ClassVisitor(Opcodes.ASM9, writer) {
            override fun visitAnnotation(descriptor: String, visible: Boolean): org.jetbrains.org.objectweb.asm.AnnotationVisitor? {
                val delegate = super.visitAnnotation(descriptor, visible)
                if (descriptor != "Lkotlin/Metadata;") return delegate
                return object : org.jetbrains.org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9, delegate) {
                    override fun visitArray(name: String?): org.jetbrains.org.objectweb.asm.AnnotationVisitor? {
                        val array = super.visitArray(name) ?: return null
                        if (name != "d2") return array
                        return object : org.jetbrains.org.objectweb.asm.AnnotationVisitor(Opcodes.ASM9, array) {
                            override fun visit(name: String?, value: Any?) {
                                val rewritten = (value as? String)?.replace(
                                    "FixtureStateFlow",
                                    "kotlinx/coroutines/flow/StateFlow",
                                ) ?: value
                                if (rewritten != value) metadataRewrites++
                                super.visit(name, rewritten)
                            }
                        }
                    }
                }
            }

            override fun visitMethod(
                access: Int,
                name: String,
                descriptor: String,
                signature: String?,
                exceptions: Array<out String>?,
            ): MethodVisitor? {
                if (name != "getState" || "FixtureStateFlow" !in descriptor) {
                    return super.visitMethod(access, name, descriptor, signature, exceptions)
                }
                getterRewrites++
                return super.visitMethod(
                    access,
                    name,
                    descriptor.replace("FixtureStateFlow", "kotlinx/coroutines/flow/StateFlow"),
                    signature?.replace("FixtureStateFlow", "kotlinx/coroutines/flow/StateFlow"),
                    exceptions,
                )
            }
        }, 0)
        check(getterRewrites == 1 && metadataRewrites > 0) {
            "Fixture StateFlow rewrite did not update one getter and Kotlin metadata"
        }
        return writer.toByteArray()
    }

    private companion object {
        const val CONSTRUCTOR =
            "common|owner=JavaFixture|kind=constructor|abi=JavaFixture.<init>|<init>(kotlin.String){}[0]|" +
                "return=JavaFixture|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"
        const val PROPERTY =
            "common|owner=JavaFixture|kind=property|abi=JavaFixture.value|{}value[0]|propertyKind=VAL|type=kotlin/String!!"
        const val FUNCTION =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.echo|echo(kotlin.String){}[0]|" +
                "return=kotlin/String!!|suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"
        const val GENERIC_FUNCTION =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.genericEcho|" +
                "genericEcho(kotlin.collections.List){}[0]|" +
                "return=kotlin.collections/List<INVARIANT:kotlin/String!!>!!|suspend=false|" +
                "parameters=[REGULAR:kotlin.collections/List<INVARIANT:kotlin/String!!>!!:" +
                "default=false:vararg=false]"
        const val READ_ONLY_COLLECTION_PARAMETERS =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.readOnlyCollectionParameters|" +
                "readOnlyCollectionParameters(kotlin.collections.Map;kotlin.collections.List;" +
                "kotlin.collections.Set){}[0]|return=kotlin/Unit|suspend=false|parameters=[" +
                "REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:JavaFixtureValue!!>!!:" +
                "default=false:vararg=false," +
                "REGULAR:kotlin.collections/List<INVARIANT:JavaFixtureValue!!>!!:default=false:vararg=false," +
                "REGULAR:kotlin.collections/Set<INVARIANT:JavaFixtureValue!!>!!:default=false:vararg=false]"
        const val MUTABLE_COLLECTION_PARAMETER =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.mutableCollectionParameter|" +
                "mutableCollectionParameter(kotlin.collections.MutableList){}[0]|return=kotlin/Unit|suspend=false|" +
                "parameters=[REGULAR:kotlin.collections/MutableList<INVARIANT:JavaFixtureValue!!>!!:" +
                "default=false:vararg=false]"
        const val MAP_KEY_PARAMETER =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.mapKeyParameter|" +
                "mapKeyParameter(kotlin.collections.Map){}[0]|return=kotlin/Unit|suspend=false|" +
                "parameters=[REGULAR:kotlin.collections/Map<INVARIANT:JavaFixtureValue!!," +
                "INVARIANT:kotlin/String!!>!!:default=false:vararg=false]"
        const val READ_ONLY_COLLECTION_RETURN =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.readOnlyCollectionReturn|" +
                "readOnlyCollectionReturn(){}[0]|return=kotlin.collections/List<INVARIANT:JavaFixtureValue!!>!!|" +
                "suspend=false|parameters=[]"
        const val READ_ONLY_COLLECTION_PROPERTY =
            "common|owner=JavaFixture|kind=property|abi=JavaFixture.readOnlyCollectionProperty|" +
                "{}readOnlyCollectionProperty[0]|propertyKind=VAL|" +
                "type=kotlin.collections/List<INVARIANT:JavaFixtureValue!!>!!"
        const val ENUM_ENTRY =
            "common|owner=JavaFixtureEnum|kind=enum-entry|abi=JavaFixtureEnum.ONE|null[0]"
        const val OBJECT =
            "common|owner=JavaFixtureSingleton|kind=object|abi=JavaFixtureSingleton|null[0]"
        const val SUSPEND =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.load|load(){}[0]|" +
                "return=kotlin/String!!|suspend=true|parameters=[]"
        const val SUSPEND_PARAMETER =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.loadInput|loadInput(kotlin.String){}[0]|" +
                "return=kotlin/String!!|suspend=true|" +
                "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"
        const val GENERIC_SUSPEND =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.authorize|" +
                "authorize(0:0){0§<kotlin.Any>}[0]|" +
                "return=kotlin/Unit|suspend=true|parameters=[REGULAR:^A1:default=false:vararg=false]"
        const val DEFINITELY_NON_NULL_GENERIC_SUSPEND =
            "common|owner=JavaFixture|kind=function|abi=JavaFixture.authorizeDefinitelyNonNull|" +
                "authorizeDefinitelyNonNull(0:0){0§<kotlin.Any?>}[0]|return=kotlin/Unit|suspend=true|" +
                "parameters=[REGULAR:^A1!!:default=false:vararg=false]"
        const val STATE_FLOW =
            "common|owner=JavaFixture|kind=property|abi=JavaFixture.state|{}state[0]|propertyKind=VAL|" +
                "type=kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/String!!>!!"
        const val HOST =
            "common|owner=CodexHost|kind=constructor|abi=CodexHost.<init>|<init>(){}[0]|" +
                "return=CodexHost|suspend=false|parameters=[]"
        const val COMPANION =
            "common|owner=JavaFixture.Companion|kind=function|abi=JavaFixture.Companion.from|" +
                "from(kotlin.String){}[0]|return=JavaFixture!!|suspend=false|" +
                "parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]"
        val CAPABILITIES = listOf(
            CONSTRUCTOR,
            PROPERTY,
            FUNCTION,
            ENUM_ENTRY,
            OBJECT,
            SUSPEND,
            STATE_FLOW,
            HOST,
            COMPANION,
        )

        const val ECHO_DESCRIPTOR = "(Ljava/lang/String;)Ljava/lang/String;"
        const val GENERIC_ECHO_DESCRIPTOR = "(Ljava/util/List;)Ljava/util/List;"
        const val READ_ONLY_COLLECTIONS_DESCRIPTOR = "(Ljava/util/Map;Ljava/util/List;Ljava/util/Set;)V"
        const val MUTABLE_COLLECTION_DESCRIPTOR = "(Ljava/util/List;)V"
        const val MAP_KEY_DESCRIPTOR = "(Ljava/util/Map;)V"
        const val READ_ONLY_COLLECTION_RESULT_DESCRIPTOR = "()Ljava/util/List;"
        const val SUSPEND_DESCRIPTOR = "(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;"
        const val FUTURE_DESCRIPTOR = "(LJavaFixture;)Ljava/util/concurrent/CompletableFuture;"
        const val PARAMETER_FUTURE_DESCRIPTOR =
            "(LJavaFixture;Ljava/lang/String;)Ljava/util/concurrent/CompletableFuture;"
        const val WRONG_PARAMETER_FUTURE_DESCRIPTOR =
            "(LJavaFixture;I)Ljava/util/concurrent/CompletableFuture;"
        const val GENERIC_FUTURE_DESCRIPTOR =
            "(LJavaFixture;Ljava/lang/Object;)Ljava/util/concurrent/CompletableFuture;"
        const val FACTORY_DESCRIPTOR = "(Ljava/lang/String;)LCodexHost;"
        const val SINGLETON_DESCRIPTOR = "LJavaFixtureSingleton;"
        const val DESKTOP_FACTORY_DESCRIPTOR = "(Ljava/nio/file/Path;)LCodexHost;"
        const val ANDROID_FACTORY_DESCRIPTOR = "(Landroid/content/Context;)LCodexHost;"
        val FUTURE_METHOD = method(JavaProjectionFixture::class.java, "loadAsync", FUTURE_DESCRIPTOR)
        val PARAMETER_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "loadInputAsync",
            PARAMETER_FUTURE_DESCRIPTOR,
        )
        val WRONG_PARAMETER_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "loadInputWrongParameterAsync",
            WRONG_PARAMETER_FUTURE_DESCRIPTOR,
        )
        val GENERIC_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "authorizeAsync",
            GENERIC_FUTURE_DESCRIPTOR,
        )
        val DEFINITELY_NON_NULL_GENERIC_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "authorizeDefinitelyNonNullAsync",
            GENERIC_FUTURE_DESCRIPTOR,
        )
        val WRONG_FUTURE_METHOD = method(JavaProjectionFixture::class.java, "wrongFuture", "(LJavaFixture;)Ljava/lang/String;")
        val CONTINUATION_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "continuationFuture",
            "(LJavaFixture;Lkotlin/coroutines/Continuation;)Ljava/util/concurrent/CompletableFuture;",
        )
        val RAW_FUTURE_METHOD = method(
            JavaProjectionFixture::class.java,
            "rawFuture",
            "(Ljava/util/concurrent/CompletableFuture;LJavaFixture;)Ljava/util/concurrent/CompletableFuture;",
        )
        val CURRENT_METHOD = method(JavaProjectionFixture::class.java, "currentState", "(LJavaFixture;)Ljava/lang/String;")
        val OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "observeState",
            "(LJavaFixture;Ljava/util/concurrent/Executor;" +
                "Ljava/util/function/Consumer;)LJavaObservationFixture;",
        )
        val WRONG_RECEIVER_CURRENT_METHOD = method(
            JavaProjectionFixture::class.java,
            "currentStateWrongReceiver",
            "(Ljava/lang/String;)Ljava/lang/String;",
        )
        val WRONG_RECEIVER_OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "observeStateWrongReceiver",
            "(Ljava/lang/String;Ljava/util/concurrent/Executor;" +
                "Ljava/util/function/Consumer;)LJavaObservationFixture;",
        )
        val WRONG_EXECUTOR_OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "observeStateWrongExecutor",
            "(LJavaFixture;Ljava/lang/String;Ljava/util/function/Consumer;)LJavaObservationFixture;",
        )
        val RAW_STATE_METHOD = method(
            JavaProjectionFixture::class.java,
            "rawState",
            "(LJavaFixture;)Lkotlinx/coroutines/flow/StateFlow;",
        )
        val NOT_CLOSEABLE_OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "notCloseableObserve",
            "(LJavaFixture;Ljava/util/function/Consumer;)Ljava/lang/Object;",
        )
        val NO_CONSUMER_OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "observeWithoutConsumer",
            "(LJavaFixture;)LJavaObservationFixture;",
        )
        val KOTLIN_FUNCTION_OBSERVE_METHOD = method(
            JavaProjectionFixture::class.java,
            "observeWithKotlinFunction",
            "(LJavaFixture;Ljava/util/function/Consumer;Lkotlin/jvm/functions/Function1;)LJavaObservationFixture;",
        )
        val STATIC_COMPANION_METHOD = method(
            JavaProjectionFixture::class.java,
            "fromValue",
            "(Ljava/lang/String;)LJavaFixture;",
        )
        val COMPANION_INSTANCE_METHOD = method(
            JavaFixture.Companion::class.java,
            "from",
            "(Ljava/lang/String;)LJavaFixture;",
        )
        val DESKTOP_FACTORY = method(DesktopFactoryFixture::class.java, "createHost", DESKTOP_FACTORY_DESCRIPTOR)
        val ANDROID_FACTORY = method(AndroidFactoryFixture::class.java, "createHost", ANDROID_FACTORY_DESCRIPTOR)

        fun method(owner: Class<*>, name: String, descriptor: String) = JavaJvmSymbol(
            JavaJvmSymbolKind.METHOD,
            owner.name.replace('.', '/'),
            name,
            descriptor,
        )
    }
}

private data class JavaFixtureArtifacts(
    val coreJvm: File,
    val coreAndroid: File,
    val desktopRuntime: File,
    val androidRuntime: File,
)

private sealed interface ClassMutation {
    val owner: String
    fun apply(bytes: ByteArray): ByteArray
}

private enum class MethodMutationKind {
    REMOVE,
    PRIVATE,
    SYNTHETIC,
    BRIDGE,
    REPLACE_DESCRIPTOR,
    REPLACE_SIGNATURE,
    CLASS_PRIVATE,
}

private data class MethodMutation(
    override val owner: String,
    val name: String,
    val descriptor: String,
    val kind: MethodMutationKind,
    val replacementDescriptor: String? = null,
    val replacementSignature: String? = null,
) : ClassMutation {
    override fun apply(bytes: ByteArray): ByteArray {
        val writer = ClassWriter(0)
        var matches = 0
        ClassReader(bytes).accept(object : ClassVisitor(Opcodes.ASM9, writer) {
            override fun visit(
                version: Int,
                access: Int,
                name: String,
                signature: String?,
                superName: String?,
                interfaces: Array<out String>,
            ) {
                val changedAccess = if (kind == MethodMutationKind.CLASS_PRIVATE) {
                    matches++
                    access and Opcodes.ACC_PUBLIC.inv() or Opcodes.ACC_PRIVATE
                } else access
                super.visit(version, changedAccess, name, signature, superName, interfaces)
            }

            override fun visitMethod(
                access: Int,
                methodName: String,
                methodDescriptor: String,
                signature: String?,
                exceptions: Array<out String>?,
            ): MethodVisitor? {
                if (kind == MethodMutationKind.CLASS_PRIVATE || methodName != name || methodDescriptor != descriptor) {
                    return super.visitMethod(access, methodName, methodDescriptor, signature, exceptions)
                }
                matches++
                if (kind == MethodMutationKind.REMOVE) return null
                if (kind == MethodMutationKind.REPLACE_DESCRIPTOR) {
                    return super.visitMethod(access, methodName, checkNotNull(replacementDescriptor), null, exceptions)
                }
                if (kind == MethodMutationKind.REPLACE_SIGNATURE) {
                    return super.visitMethod(access, methodName, methodDescriptor, replacementSignature, exceptions)
                }
                val changedAccess = when (kind) {
                    MethodMutationKind.PRIVATE -> access and Opcodes.ACC_PUBLIC.inv() or Opcodes.ACC_PRIVATE
                    MethodMutationKind.SYNTHETIC -> access or Opcodes.ACC_SYNTHETIC
                    MethodMutationKind.BRIDGE -> access and Opcodes.ACC_SYNTHETIC.inv() or Opcodes.ACC_BRIDGE
                    MethodMutationKind.REMOVE -> error("unreachable")
                    MethodMutationKind.REPLACE_DESCRIPTOR -> error("unreachable")
                    MethodMutationKind.REPLACE_SIGNATURE -> error("unreachable")
                    MethodMutationKind.CLASS_PRIVATE -> error("unreachable")
                }
                return super.visitMethod(changedAccess, methodName, methodDescriptor, signature, exceptions)
            }
        }, 0)
        check(matches == 1) { "Expected one mutation target $owner#$name$descriptor, found $matches" }
        return writer.toByteArray()
    }

    companion object {
        fun remove(owner: Class<*>, name: String, descriptor: String) =
            MethodMutation(owner.name.replace('.', '/'), name, descriptor, MethodMutationKind.REMOVE)

        fun makePrivate(owner: Class<*>, name: String, descriptor: String) =
            MethodMutation(owner.name.replace('.', '/'), name, descriptor, MethodMutationKind.PRIVATE)

        fun makeSynthetic(owner: Class<*>, name: String, descriptor: String) =
            MethodMutation(owner.name.replace('.', '/'), name, descriptor, MethodMutationKind.SYNTHETIC)

        fun makeBridge(owner: Class<*>, name: String, descriptor: String) =
            MethodMutation(owner.name.replace('.', '/'), name, descriptor, MethodMutationKind.BRIDGE)

        fun makeClassPrivate(owner: Class<*>) =
            MethodMutation(owner.name.replace('.', '/'), "", "", MethodMutationKind.CLASS_PRIVATE)

        fun replaceDescriptor(owner: Class<*>, name: String, descriptor: String, replacement: String) =
            MethodMutation(
                owner.name.replace('.', '/'),
                name,
                descriptor,
                MethodMutationKind.REPLACE_DESCRIPTOR,
                replacement,
            )

        fun replaceSignature(owner: Class<*>, name: String, descriptor: String, replacement: String) =
            MethodMutation(
                owner.name.replace('.', '/'),
                name,
                descriptor,
                MethodMutationKind.REPLACE_SIGNATURE,
                replacementSignature = replacement,
            )
    }
}

private enum class FieldMutationKind {
    REMOVE,
    PRIVATE,
    SYNTHETIC,
    REMOVE_STATIC,
    REMOVE_FINAL,
    REPLACE_DESCRIPTOR,
}

private data class FieldMutation(
    override val owner: String,
    val name: String,
    val descriptor: String,
    val kind: FieldMutationKind,
    val replacementDescriptor: String? = null,
) : ClassMutation {
    override fun apply(bytes: ByteArray): ByteArray {
        val writer = ClassWriter(0)
        var matches = 0
        ClassReader(bytes).accept(object : ClassVisitor(Opcodes.ASM9, writer) {
            override fun visitField(
                access: Int,
                fieldName: String,
                fieldDescriptor: String,
                signature: String?,
                value: Any?,
            ): FieldVisitor? {
                if (fieldName != name || fieldDescriptor != descriptor) {
                    return super.visitField(access, fieldName, fieldDescriptor, signature, value)
                }
                matches++
                if (kind == FieldMutationKind.REMOVE) return null
                val changedAccess = when (kind) {
                    FieldMutationKind.PRIVATE -> access and Opcodes.ACC_PUBLIC.inv() or Opcodes.ACC_PRIVATE
                    FieldMutationKind.SYNTHETIC -> access or Opcodes.ACC_SYNTHETIC
                    FieldMutationKind.REMOVE_STATIC -> access and Opcodes.ACC_STATIC.inv()
                    FieldMutationKind.REMOVE_FINAL -> access and Opcodes.ACC_FINAL.inv()
                    FieldMutationKind.REPLACE_DESCRIPTOR, FieldMutationKind.REMOVE -> access
                }
                val changedDescriptor = replacementDescriptor ?: fieldDescriptor
                return super.visitField(changedAccess, fieldName, changedDescriptor, signature, value)
            }
        }, 0)
        check(matches == 1) { "Expected one field mutation target $owner#$name:$descriptor, found $matches" }
        return writer.toByteArray()
    }

    companion object {
        fun remove(owner: Class<*>, name: String, descriptor: String) =
            create(owner, name, descriptor, FieldMutationKind.REMOVE)

        fun makePrivate(owner: Class<*>, name: String, descriptor: String) =
            create(owner, name, descriptor, FieldMutationKind.PRIVATE)

        fun makeSynthetic(owner: Class<*>, name: String, descriptor: String) =
            create(owner, name, descriptor, FieldMutationKind.SYNTHETIC)

        fun removeStatic(owner: Class<*>, name: String, descriptor: String) =
            create(owner, name, descriptor, FieldMutationKind.REMOVE_STATIC)

        fun removeFinal(owner: Class<*>, name: String, descriptor: String) =
            create(owner, name, descriptor, FieldMutationKind.REMOVE_FINAL)

        fun replaceDescriptor(owner: Class<*>, name: String, descriptor: String, replacement: String) =
            create(owner, name, descriptor, FieldMutationKind.REPLACE_DESCRIPTOR, replacement)

        private fun create(
            owner: Class<*>,
            name: String,
            descriptor: String,
            kind: FieldMutationKind,
            replacement: String? = null,
        ) = FieldMutation(owner.name.replace('.', '/'), name, descriptor, kind, replacement)
    }
}

public class JavaFixture(public val value: String) {
    public fun echo(input: String): String = input

    public fun genericEcho(input: List<String>): List<String> = input

    public fun readOnlyCollectionParameters(
        @Suppress("UNUSED_PARAMETER") map: Map<String, JavaFixtureValue>,
        @Suppress("UNUSED_PARAMETER") list: List<JavaFixtureValue>,
        @Suppress("UNUSED_PARAMETER") set: Set<JavaFixtureValue>,
    ): Unit = Unit

    public fun mutableCollectionParameter(@Suppress("UNUSED_PARAMETER") value: MutableList<JavaFixtureValue>): Unit = Unit

    public fun mapKeyParameter(@Suppress("UNUSED_PARAMETER") value: Map<JavaFixtureValue, String>): Unit = Unit

    public fun readOnlyCollectionReturn(): List<JavaFixtureValue> = emptyList()

    public val readOnlyCollectionProperty: List<JavaFixtureValue>
        get() = emptyList()

    public suspend fun load(): String = value

    public suspend fun loadInput(input: String): String = value + input

    public suspend fun <T : Any> authorize(@Suppress("UNUSED_PARAMETER") target: T): Unit = Unit

    public suspend fun <T> authorizeDefinitelyNonNull(
        @Suppress("UNUSED_PARAMETER") target: T & Any,
    ): Unit = Unit

    public val state: FixtureStateFlow<String>
        get() = error("not executed")

    public companion object {
        public fun from(value: String): JavaFixture = JavaFixture(value)
    }
}

public interface JavaFixtureValue

public interface FixtureStateFlow<T>

public enum class JavaFixtureEnum { ONE }

public object JavaFixtureSingleton

public class CodexHost

public interface JavaObservationFixture : AutoCloseable

public object JavaProjectionFixture {
    @JvmStatic
    public fun loadAsync(fixture: JavaFixture): CompletableFuture<String> =
        CompletableFuture.completedFuture(fixture.value)

    @JvmStatic
    public fun loadInputAsync(fixture: JavaFixture, input: String): CompletableFuture<String> =
        CompletableFuture.completedFuture(fixture.value + input)

    @JvmStatic
    public fun loadInputWrongParameterAsync(fixture: JavaFixture, input: Int): CompletableFuture<String> =
        CompletableFuture.completedFuture(fixture.value + input)

    @JvmStatic
    public fun authorizeAsync(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") target: Any,
    ): CompletableFuture<Void> = CompletableFuture.completedFuture(null)

    @JvmStatic
    public fun authorizeDefinitelyNonNullAsync(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") target: Any,
    ): CompletableFuture<Void> = CompletableFuture.completedFuture(null)

    @JvmStatic
    public fun wrongFuture(fixture: JavaFixture): String = fixture.value

    @JvmStatic
    public fun continuationFuture(
        fixture: JavaFixture,
        continuation: kotlin.coroutines.Continuation<String>,
    ): CompletableFuture<String> = CompletableFuture.completedFuture(fixture.value + continuation.context)

    @JvmStatic
    @Suppress("UNCHECKED_CAST")
    public fun rawFuture(
        @Suppress("UNUSED_PARAMETER") typedParameter: CompletableFuture<String>,
        fixture: JavaFixture,
    ): CompletableFuture<*> = CompletableFuture.completedFuture(fixture.value) as CompletableFuture<*>

    @JvmStatic
    public fun currentState(fixture: JavaFixture): String = fixture.value

    @JvmStatic
    public fun currentStateWrongReceiver(receiver: String): String = receiver

    @JvmStatic
    public fun observeState(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") executor: Executor,
        @Suppress("UNUSED_PARAMETER") observer: Consumer<in String>,
    ): JavaObservationFixture =
        error("not executed")

    @JvmStatic
    public fun observeStateWrongReceiver(
        @Suppress("UNUSED_PARAMETER") receiver: String,
        @Suppress("UNUSED_PARAMETER") executor: Executor,
        @Suppress("UNUSED_PARAMETER") observer: Consumer<in String>,
    ): JavaObservationFixture = error("not executed")

    @JvmStatic
    public fun observeStateWrongExecutor(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") executor: String,
        @Suppress("UNUSED_PARAMETER") observer: Consumer<in String>,
    ): JavaObservationFixture = error("not executed")

    @JvmStatic
    public fun rawState(@Suppress("UNUSED_PARAMETER") fixture: JavaFixture): Any = Any()

    @JvmStatic
    public fun notCloseableObserve(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") observer: Consumer<in String>,
    ): Any = Any()

    @JvmStatic
    public fun observeWithoutConsumer(@Suppress("UNUSED_PARAMETER") fixture: JavaFixture): JavaObservationFixture =
        error("not executed")

    @JvmStatic
    public fun observeWithKotlinFunction(
        @Suppress("UNUSED_PARAMETER") fixture: JavaFixture,
        @Suppress("UNUSED_PARAMETER") observer: Consumer<in String>,
        @Suppress("UNUSED_PARAMETER") kotlinObserver: (String) -> Unit,
    ): JavaObservationFixture = error("not executed")

    @JvmStatic
    public fun fromValue(value: String): JavaFixture = JavaFixture(value)
}

public object DesktopFactoryFixture {
    @JvmStatic
    public fun createHost(@Suppress("UNUSED_PARAMETER") directory: String): CodexHost = CodexHost()
}

public object AndroidFactoryFixture {
    @JvmStatic
    public fun createHost(@Suppress("UNUSED_PARAMETER") context: String): CodexHost = CodexHost()
}
