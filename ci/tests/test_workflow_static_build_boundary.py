"""Structural workflow-lint build-boundary checks; not compiler execution evidence."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkflowStaticBuildBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        match = re.search(
            r"^  workflow-lint:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
            cls.workflow,
            re.MULTILINE | re.DOTALL,
        )
        if match is None:
            raise AssertionError("workflow-lint job is missing")
        cls.job = match.group("body")

    def test_settings_boundaries_explain_the_standalone_build(self):
        root = (ROOT / "settings.gradle.kts").read_text(encoding="utf-8")
        runtime = (ROOT / "runtime/settings.gradle.kts").read_text(encoding="utf-8")
        build_logic = (ROOT / "gradle/build-logic/settings.gradle.kts").read_text(encoding="utf-8")
        self.assertNotIn('include(":codex-agent-runtime-desktop")', root)
        self.assertIn('include(":codex-agent-runtime-desktop")', runtime)
        self.assertNotIn('include(":codex-agent-runtime-desktop")', build_logic)
        self.assertIn('rootProject.name = "build-logic"', build_logic)

    def test_workflow_lint_runs_only_the_guarded_standalone_build_logic_tests(self):
        command = (
            "./gradlew -p gradle/build-logic test --configuration-cache "
            "--configuration-cache-problems=fail --no-build-cache"
        )
        normalized = " ".join(self.job.split())
        self.assertEqual(1, self.job.count("./gradlew"))
        self.assertEqual(1, normalized.count(command))
        self.assertNotIn("--dry-run", self.job)
        for forbidden in (
            ":build-logic:test",
            ":codex-agent-sdk:",
            ":codex-agent-runtime-desktop:",
        ):
            self.assertNotIn(forbidden, self.job)

        event = "needs.plan.outputs.event_authorized == 'true'"
        remote = "needs.plan.outputs.remote_build_authorized == 'true'"
        setup = self.job.index("uses: ./.github/actions/setup-kmp")
        execution = self.job.index("./gradlew")
        event_guards = [match.start() for match in re.finditer(re.escape(event), self.job)]
        remote_guards = [match.start() for match in re.finditer(re.escape(remote), self.job)]
        self.assertEqual(2, len(event_guards))
        self.assertEqual(2, len(remote_guards))
        self.assertLess(event_guards[0], setup)
        self.assertLess(remote_guards[0], setup)
        self.assertLess(setup, event_guards[1])
        self.assertLess(setup, remote_guards[1])
        self.assertLess(event_guards[1], execution)
        self.assertLess(remote_guards[1], execution)


if __name__ == "__main__":
    unittest.main()
