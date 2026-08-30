import java.io.File
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RepositoryVerificationTasksTest {
    @Test
    fun `repository verification keeps portable producers and includes imported native wrapper parity`() {
        assertTrue(":codex-agent-core:verifyKotlinBindingParity" in repositoryVerificationTaskPaths)
        assertTrue(":codex-agent-core:verifyJavaBindingParity" in repositoryVerificationTaskPaths)
        assertTrue(
            ":codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity" in
                repositoryVerificationTaskPaths,
        )
        assertTrue(
            ":codex-agent-runtime-desktop:verifyNativeWrapperBindingParity" in
                repositoryVerificationTaskPaths,
        )
        assertTrue(":codex-agent-runtime-desktop:macosArm64Test" in repositoryVerificationTaskPaths)
        assertFalse(
            ":codex-agent-runtime-desktop:generateCodexAgentCAbiBootstrapEvidence" in
                repositoryVerificationTaskPaths,
        )
        assertFalse(":codex-agent-core:auditCrossLanguageBindingParity" in repositoryVerificationTaskPaths)
        val source = File("src/main/kotlin/RepositoryVerificationTasks.kt").readText()
        assertTrue("gradle.includedBuild(\"build-logic\").task(\":test\")" in source)
        assertTrue("dependsOn(\n            repositoryVerificationTaskPaths" in source)
        assertTrue(":codex-agent-runtime-ios:verifyIosRuntime" in source)
        assertFalse(":codex-agent-core:auditCrossLanguageBindingParity" in source)
        assertTrue("distributed CI owns complete M8 parity" in source)
    }

    @Test
    fun `ordinary Android verification uses the complete release variant gates`() {
        assertTrue(":codex-agent-runtime-android:testDebugUnitTest" in repositoryVerificationTaskPaths)
        assertTrue(":codex-agent-runtime-android:lintRelease" in repositoryVerificationTaskPaths)
        assertTrue(":codex-agent-runtime-android:assembleRelease" in repositoryVerificationTaskPaths)
        assertFalse(":codex-agent-runtime-android:testReleaseUnitTest" in repositoryVerificationTaskPaths)
        assertFalse(":codex-agent-runtime-android:lint" in repositoryVerificationTaskPaths)
    }
}
