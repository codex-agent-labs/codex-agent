import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals

class CrossLanguageApiTasksTest {
    @Test
    fun `JVM compiler metadata identifies data classes without reflection`() {
        withDirectory { classes ->
            copyClass(DataFixture::class.java, classes)
            copyClass(OrdinaryFixture::class.java, classes)

            assertEquals(
                setOf("CrossLanguageApiTasksTest.DataFixture"),
                readCompilerDataClassNames(classes),
            )
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
}
