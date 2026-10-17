import java.lang.reflect.Proxy
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.provider.ProviderFactory
import org.gradle.testfixtures.ProjectBuilder

/** Mode routing only: provider lookup is controlled; the production validator runs unchanged. */
class IosSdkValidationModeTest {
    @Test
    fun `unrelated phases do not activate validation but both exact validation targets do`() = withMode { mode ->
        assertFalse(mode(emptyMap(), emptyMap()))
        listOf("codexAgent.product" to "runtime", "codexAgent.component" to "sdk-core",
            "codexAgent.phase" to "package").forEach { changed ->
            assertFalse(mode((properties() - "codexAgent.iosValidationPackageStage") + changed, emptyMap()))
        }
        // Shared Contract/compatibility inputs alone must not switch unrelated callers into validation.
        assertFalse(mode(mapOf("codexAgent.contractBinaryStage" to "/original/contract",
            "codexAgent.sdkCompatibilityFile" to "/original/sdk-compatibility.json"), emptyMap()))
        listOf("ios-arm64", "ios-simulator-arm64").forEach { target ->
            assertTrue(mode(properties() + ("codexAgent.target" to target), emptyMap()))
        }
    }

    @Test
    fun `package locator activation requires exact SDK validation identity`() = withMode { mode ->
        assertFailsWith<IllegalStateException> {
            mode(mapOf("codexAgent.iosValidationPackageStage" to "/original/package"), emptyMap())
        }
        listOf("codexAgent.product" to "runtime", "codexAgent.component" to "sdk-core",
            "codexAgent.phase" to "package", "codexAgent.target" to "ios",
            "codexAgent.target" to "desktop").forEach { (key, value) ->
            assertFailsWith<IllegalStateException>("$key=$value") {
                mode(properties() + (key to value), emptyMap())
            }
        }
        listOf("codexAgent.product", "codexAgent.component", "codexAgent.phase", "codexAgent.target").forEach { key ->
            assertFailsWith<IllegalStateException>(key) { mode(properties() - key, emptyMap()) }
        }
    }

    @Test
    fun `selected validation rejects missing empty and whitespace original inputs`() = withMode { mode ->
        listOf("ios-arm64", "ios-simulator-arm64").forEach { target ->
            val selected = properties() + ("codexAgent.target" to target)
            listOf("codexAgent.iosValidationPackageStage", "codexAgent.contractBinaryStage",
                "codexAgent.sdkCompatibilityFile", "codexAgent.iosValidationTestApplicationDirectory",
                "codexAgent.iosValidationCompilerConsumersDirectory").forEach { key ->
                assertFailsWith<IllegalStateException>("missing $key for $target") { mode(selected - key, emptyMap()) }
                listOf("", " \t\n").forEach { blank ->
                    assertFailsWith<IllegalStateException>("blank $key for $target") {
                        mode(selected + (key to blank), emptyMap())
                    }
                }
            }
        }
    }

    @Test
    fun `selected validation rejects every legacy fresh package and compiler override`() = withMode { mode ->
        assertEquals("codexAgent.iosVerifiedDistributionDirectory", IOS_VERIFIED_DISTRIBUTION_PROPERTY)
        listOf("codexAgent.iosPackageFromBinary", IOS_VERIFIED_DISTRIBUTION_PROPERTY,
            "codexAgent.iosExpectedDistributionProof", "codexAgent.iosExpectedSdkCompatibility",
            "codexAgent.iosNativeEvidenceDirectory", "codexAgent.iosDeviceFrameworkDirectory",
            "codexAgent.iosSimulatorFrameworkDirectory", "codexAgent.iosContractBinaryStage",
            "codexAgent.sdkCompatibilityRequest").forEach { key ->
            listOf("", "/untrusted/override").forEach { value ->
                assertFailsWith<IllegalStateException>("$key=$value") {
                    mode(properties() + (key to value), emptyMap())
                }
            }
        }
        listOf("CODEX_AGENT_IMPORTED_SWIFT_ZIP", "CODEX_AGENT_SWIFT_COMPILATION_DIRECTORY").forEach { key ->
            listOf("", "/untrusted/override").forEach { value ->
                assertFailsWith<IllegalStateException>("$key=$value") {
                    mode(properties(), mapOf(key to value))
                }
            }
        }
    }

    private fun properties() = mapOf(
        "codexAgent.product" to "sdk", "codexAgent.component" to "sdk-ios",
        "codexAgent.phase" to "validation", "codexAgent.target" to "ios-arm64",
        "codexAgent.iosValidationPackageStage" to "/original/package",
        "codexAgent.contractBinaryStage" to "/original/contract",
        "codexAgent.sdkCompatibilityFile" to "/original/sdk-compatibility.json",
        "codexAgent.iosValidationTestApplicationDirectory" to "/original/TestApp",
        "codexAgent.iosValidationCompilerConsumersDirectory" to "/original/CompilerEvidence",
    )

    private fun withMode(block: ((Map<String, String>, Map<String, String>) -> Boolean) -> Unit) {
        val root = createTempDirectory("ios-sdk-validation-mode-").toFile()
        try {
            val factory = ProjectBuilder.builder().withProjectDir(root).build().providers
            block { properties, environment ->
                val providers = Proxy.newProxyInstance(ProviderFactory::class.java.classLoader,
                    arrayOf(ProviderFactory::class.java)) { _, method, arguments ->
                    val values = when (method.name) {
                        "gradleProperty" -> properties
                        "environmentVariable" -> environment
                        else -> error("Unexpected provider call: ${method.name}")
                    }
                    factory.provider { values[arguments!![0] as String] }
                } as ProviderFactory
                val project = Proxy.newProxyInstance(Project::class.java.classLoader,
                    arrayOf(Project::class.java)) { _, method, _ ->
                    check(method.name == "getProviders") { "Unexpected project call: ${method.name}" }
                    providers
                } as Project
                project.usesAppleSdkValidationInputs()
            }
        } finally {
            root.deleteRecursively()
        }
    }
}
