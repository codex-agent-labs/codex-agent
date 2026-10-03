import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals

class CrossLanguageApiTasksTest {
    @Test
    fun `JVM compiler metadata identifies data classes singletons and named companions without reflection`() {
        withDirectory { classes ->
            copyClass(DataFixture::class.java, classes)
            copyClass(OrdinaryFixture::class.java, classes)
            copyClass(SingletonFixture::class.java, classes)
            copyClass(CompanionFixture.Factory::class.java, classes)

            val facts = readCompilerJvmClassFacts(classes)
            assertEquals(setOf("CrossLanguageApiTasksTest.DataFixture"), facts.dataClassNames)
            assertEquals(setOf("CrossLanguageApiTasksTest.SingletonFixture"), facts.singletonObjectNames)
            assertEquals(
                setOf("CrossLanguageApiTasksTest.CompanionFixture.Factory"),
                facts.companionObjectNames,
            )
            assertEquals(facts.dataClassNames, readCompilerDataClassNames(classes))
        }
    }

    private fun copyClass(type: Class<*>, destination: File) {
        val relativePath = type.name.replace('.', '/') + ".class"
        val output = destination.resolve(relativePath).apply { parentFile.mkdirs() }
        type.getResourceAsStream("/$relativePath").use { input ->
            output.outputStream().use { outputStream ->
                checkNotNull(input) { "Missing fixture class: $relativePath" }.copyTo(outputStream)
            }
        }
    }

    private fun withDirectory(block: (File) -> Unit) {
        val root = createTempDirectory("cross-language-api-tasks").toFile()
        try {
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }

    private data class DataFixture(val value: String)

    private class OrdinaryFixture

    private object SingletonFixture

    private class CompanionFixture {
        companion object Factory
    }
}
