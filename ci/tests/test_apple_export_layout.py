"""Static guards for the fresh Apple export layout; this does not execute Gradle."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AppleExportLayoutSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "settings.gradle.kts").read_text(encoding="utf-8")
        start = source.index('val appleExportBuildRootProperty = "codexAgent.appleExportBuildRoot"')
        end = source.index("val sdkBinaryRequest =", start)
        cls.block = source[start:end]

    def test_isolation_is_reserved_for_one_exact_fresh_export(self):
        self.assertIn(
            'System.getProperty("org.gradle.project.$appleExportBuildRootProperty") == null',
            self.block,
        )
        self.assertIn(
            'System.getenv("ORG_GRADLE_PROJECT_$appleExportBuildRootProperty") == null',
            self.block,
        )
        self.assertIn(
            "gradle.startParameter.taskNames == listOf(\n"
            '        ":codex-agent-runtime-ios:exportCodexAgentIosVerifiedDistribution",\n'
            "    ) && gradle.startParameter.includedBuilds.isEmpty()",
            self.block,
        )
        self.assertEqual(1, self.block.count("exportCodexAgentIosVerifiedDistribution"))

    def test_tree_and_repository_owned_root_are_exact_and_fresh(self):
        for required in (
            'rootProjectProperties["codexAgent.candidateTree"]',
            'Regex("[0-9a-f]{40}").matches(tree)',
            'val repository = settingsDir.toPath().toRealPath()',
            'val expected = repository.resolve("build/apple-export/$tree")',
            "supplied.isAbsolute && supplied.normalize() == supplied && supplied == expected",
            "!java.nio.file.Files.isSymbolicLink(ancestor)",
            "java.nio.file.Files.isDirectory(ancestor, java.nio.file.LinkOption.NOFOLLOW_LINKS)",
            "!java.nio.file.Files.exists(supplied, java.nio.file.LinkOption.NOFOLLOW_LINKS)",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.block)
        self.assertLess(self.block.index("while (ancestor != null"), self.block.index("gradle.beforeProject"))
        self.assertLess(
            self.block.index("!java.nio.file.Files.exists(supplied"),
            self.block.index("gradle.beforeProject"),
        )

    def test_only_sdk_and_ios_receive_disjoint_project_named_build_roots(self):
        self.assertIn("gradle.beforeProject(org.gradle.api.Action<org.gradle.api.Project>", self.block)
        self.assertIn(
            'if (path in setOf(":codex-agent-sdk", ":codex-agent-runtime-ios"))',
            self.block,
        )
        self.assertIn("layout.buildDirectory.set(exportRoot.resolve(name))", self.block)
        self.assertEqual(1, self.block.count("layout.buildDirectory.set("))
        for unrelated in (":codex-agent-core", ":codex-agent-runtime-android"):
            self.assertNotIn(unrelated, self.block)


if __name__ == "__main__":
    unittest.main()
