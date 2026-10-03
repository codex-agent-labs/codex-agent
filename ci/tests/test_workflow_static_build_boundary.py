"""Structural workflow-lint build-boundary checks; not compiler execution evidence."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkflowStaticBuildBoundaryTest(unittest.TestCase):
    def test_focused_diagnostics_are_exact_source_and_unprivileged(self):
        caller = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        match = re.search(r"^  build-logic-diagnostics:\n(.*?)(?=^  [a-z0-9-]+:\n)",
                          caller, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        job = match.group(1)
        self.assertIn("inputs.purpose == 'build-logic-diagnostics'", job)
        for binding in ('test "$VALIDATION_COMMIT" = "$GITHUB_SHA"',
                        "git rev-parse 'HEAD^{tree}'", 'persist-credentials: false'):
            self.assertIn(binding, job)
        for forbidden in ("secrets:", "environment:", "id-token:", "ciProductPhase", "verifyRuntime"):
            self.assertNotIn(forbidden, job)
        self.assertIn("--info --stacktrace", job)
        self.assertIn("if: always()", job)
        self.assertIn("build/test-results/test/*.xml", job)
        self.assertEqual(6, job.count("--tests '"))
        self.assertIn("run: ./gradlew help -Pkotlin.daemon.jvmargs=-Xmx2g", job)
        self.assertLess(job.index("run: ./gradlew help"), job.index("--tests '"))
        self.assertIn("inputs.purpose == 'build-logic-diagnostics' && 'Build logic diagnostics / complete'", caller)

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
            "./gradlew -p gradle/build-logic test -Pkotlin.daemon.jvmargs=-Xmx2g --configuration-cache "
            "--configuration-cache-problems=fail --no-build-cache"
        )
        normalized = " ".join(self.job.split())
        self.assertEqual(2, self.job.count("./gradlew"))
        self.assertIn("run: ./gradlew help -Pkotlin.daemon.jvmargs=-Xmx2g", self.job)
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
        provisioning = self.job.index("run: ./gradlew help")
        execution = self.job.index("./gradlew -p gradle/build-logic test")
        event_guards = [match.start() for match in re.finditer(re.escape(event), self.job)]
        remote_guards = [match.start() for match in re.finditer(re.escape(remote), self.job)]
        self.assertEqual(3, len(event_guards))
        self.assertEqual(3, len(remote_guards))
        self.assertLess(event_guards[0], setup)
        self.assertLess(remote_guards[0], setup)
        self.assertLess(setup, event_guards[1])
        self.assertLess(setup, remote_guards[1])
        self.assertLess(event_guards[1], provisioning)
        self.assertLess(remote_guards[1], provisioning)
        self.assertLess(provisioning, event_guards[2])
        self.assertLess(event_guards[2], execution)
        self.assertLess(remote_guards[2], execution)

    def test_android_firebase_and_apple_are_guarded_before_job_creation(self):
        for name, selector in (("android", "lane_android"),
                               ("android-runtime-evidence", "android_evidence_required"),
                               ("apple", "any_apple")):
            with self.subTest(job=name):
                match = re.search(
                    rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
                    self.workflow, re.MULTILINE | re.DOTALL,
                )
                self.assertIsNotNone(match)
                job = match.group("body")
                condition = job.split("    needs:", 1)[0]
                for guard in ("needs.plan.outputs.event_authorized == 'true'",
                              "needs.plan.outputs.remote_build_authorized == 'true'",
                              "needs.plan.outputs.validation_reused != 'true'",
                              f"needs.plan.outputs.{selector} == 'true'"):
                    self.assertIn(guard, condition)
                self.assertLess(job.index("    if:"), job.index("    needs:"))
                if name != "android":
                    self.assertIn("    uses:", job)
                    self.assertLess(job.index("    if:"), job.index("    uses:"))
                else:
                    self.assertLess(job.index("    if:"), job.index("setup-android@"))


if __name__ == "__main__":
    unittest.main()
