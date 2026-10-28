"""The Android Firebase test app must not compile the SDK adapter in imported mode."""

from pathlib import Path
import unittest


SCRIPT = (Path(__file__).resolve().parents[2] /
          "tooling/android-runtime-evidence/build.gradle.kts")


class AndroidEvidenceDependencyBoundaryTest(unittest.TestCase):
    def test_authenticated_mode_uses_the_exact_published_adapter(self):
        source = SCRIPT.read_text(encoding="utf-8")
        boundary = source.split("val authenticatedVersion = ", 1)[1].split(
            "androidTestImplementation(libs.androidx.test.ext.junit)", 1)[0]
        self.assertIn('rootProject.extra.properties["codexAgent.authenticatedAndroidEvidenceSdkVersion"]',
                      boundary)
        self.assertIn('if (authenticatedVersion == null) {\n        implementation(project(":codex-agent-runtime-android"))',
                      boundary)
        imported = boundary.split("} else {", 1)[1]
        self.assertIn("require(authenticatedVersion == sdkVersion)", imported)
        self.assertIn('implementation("io.github.codex-agent-labs:codex-agent-runtime-android:$sdkVersion")',
                      imported)
        self.assertNotIn('project(":codex-agent-runtime-android")', imported)


if __name__ == "__main__":
    unittest.main()
