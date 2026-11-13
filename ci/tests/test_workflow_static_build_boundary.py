"""Structural workflow-lint build-boundary checks; not compiler execution evidence."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WorkflowStaticBuildBoundaryTest(unittest.TestCase):
    def test_all_pinned_android_callers_select_supported_packages_explicitly(self):
        callers = []
        for path in (ROOT / ".github").rglob("*.yml"):
            text = path.read_text()
            for match in re.finditer(r"(?m)^([ \t]*)(- )?uses: android-actions/setup-android@[^\n]+\n", text):
                callers.append(path)
                indent = match[1] + ("  " if match[2] else "")
                remaining = text[match.end():]
                if remaining.startswith(indent + "if: "):
                    remaining = remaining.split("\n", 1)[1]
                self.assertTrue(remaining.startswith(
                    indent + "with:\n" + indent + "  packages: platform-tools\n"), path)
        self.assertGreaterEqual(len(callers), 7)

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
        cls.jobs = {}
        for name in ("workflow-lint", "workflow-source-checks", "workflow-build-logic"):
            match = re.search(
                rf"^  {name}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
                cls.workflow, re.MULTILINE | re.DOTALL,
            )
            if match is None:
                raise AssertionError(name + " job is missing")
            cls.jobs[name] = match.group("body")
        cls.job = cls.jobs["workflow-build-logic"]

    def test_settings_boundaries_explain_the_standalone_build(self):
        root = (ROOT / "settings.gradle.kts").read_text(encoding="utf-8")
        runtime = (ROOT / "runtime/settings.gradle.kts").read_text(encoding="utf-8")
        build_logic = (ROOT / "gradle/build-logic/settings.gradle.kts").read_text(encoding="utf-8")
        self.assertNotIn('include(":codex-agent-runtime-desktop")', root)
        self.assertIn('include(":codex-agent-runtime-desktop")', runtime)
        self.assertNotIn('include(":codex-agent-runtime-desktop")', build_logic)
        self.assertIn('rootProject.name = "build-logic"', build_logic)

    def test_workflow_build_logic_runs_only_the_guarded_standalone_build_logic_tests(self):
        normalized = " ".join(self.job.split())
        self.assertEqual(1, self.job.count("./gradlew"))
        self.assertIn("run: ./gradlew help -Pkotlin.daemon.jvmargs=-Xmx2g", self.job)
        helper = ".github/actions/run-ci-lane/build-logic-tests.py"
        command = (f'python3 -B {helper} --repository-root "$GITHUB_WORKSPACE" '
                   '--tooling-policy "$TEST_TOOLING_POLICY" --policy-revision "$TEST_POLICY_REVISION"')
        self.assertEqual(1, normalized.count(command))
        self.assertIn('TEST_TOOLING_POLICY: ${{ steps.test-tooling.outputs.tooling-policy }}', self.job)
        self.assertIn('TEST_POLICY_REVISION: ${{ needs.plan.outputs.validation_commit }}', self.job)
        self.assertNotIn("--dry-run", self.job)
        for forbidden in (
            ":build-logic:test", ":codex-agent-sdk:", ":codex-agent-runtime-desktop:",
            "ciProductPhase", "releaseToolingJar", "--tests", "python3 -m unittest",
        ):
            self.assertNotIn(forbidden, self.job)
        helper_source = (ROOT / helper).read_text()
        self.assertIn('"-p", "gradle/build-logic", "test"', helper_source)
        self.assertIn('"-x", "releaseToolingJar", "--init-script"', helper_source)
        self.assertIn('with verified_tooling_capture(', helper_source)
        self.assertIn('required_trust_domain="release"', helper_source)

        event = "needs.plan.outputs.event_authorized == 'true'"
        remote = "needs.plan.outputs.remote_build_authorized == 'true'"
        # YAML single-quoted conditions escape a literal quote by doubling it.
        guarded = self.job.replace("''", "'")
        condition = guarded.split("    needs:", 1)[0]
        for guard in ("always()", "!cancelled()", "!inputs.toolingOnly", "!inputs.runtimeRecoveryOnly",
                      "!inputs.sdkRecoveryOnly", "needs.plan.result == 'success'", event, remote):
            self.assertIn(guard, condition)
        self.assertIn("needs: [plan, contract-validation]", self.job)
        steps = guarded.split("      - ")[1:]
        for marker in ("uses: ./.github/actions/setup-kmp", "id: test-tooling",
                       "run: ./gradlew help", "id: build-logic"):
            step, = [step for step in steps if marker in step]
            for guard in ("!inputs.runtimeRecoveryOnly", "!inputs.sdkRecoveryOnly", event, remote):
                self.assertIn(guard, step.split("\n        run:", 1)[0])
        self.assertNotIn("restore-reuse-qualification@", self.job)
        self.assertLess(guarded.index("id: test-tooling"), guarded.index("run: ./gradlew help"))
        self.assertLess(guarded.index("run: ./gradlew help"), guarded.index("id: build-logic"))
        capture, = [step for step in steps if "id: test-tooling" in step]
        for field, output in (("artifact-id", "tooling_artifact_id"),
                              ("artifact-sha256", "tooling_artifact_sha256"),
                              ("transport-producer", "tooling_transport_producer")):
            self.assertIn(field + ": ${{ needs.contract-validation.result == 'success' && "
                          f"needs.contract-validation.outputs.{output} || needs.plan.outputs.{output}" + " }}", capture)
        for binding in ("trusted-workflow-sha: ${{ needs.plan.outputs.publisher_sha }}",
                        "policy-revision: ${{ needs.plan.outputs.validation_commit }}",
                        "trusted-workflow-path: .github/workflows/contract-validation.yml",
                        "trusted-job-name: product-validation / contract-validation / tooling-attestation"):
            self.assertIn(binding, capture)
        self.assertIn("if: always() && steps.build-logic.outcome == 'failure'", self.job)
        self.assertIn("path: gradle/build-logic/build/test-results/test/TEST-*.xml", self.job)
        self.assertIn("if-no-files-found: error", self.job)
        self.assertIn("overwrite: false", self.job)

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
