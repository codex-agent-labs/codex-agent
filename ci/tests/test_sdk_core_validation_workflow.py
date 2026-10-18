"""Saved Core validation child wiring; real eleven-host evidence remains pending."""

from pathlib import Path
import json
import os
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests.test_sdk_native_continuation import locator, needs_for


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"
CHILD = WORKFLOW.with_name("sdk-core-validation.yml")


class CoreValidationWorkflowTest(unittest.TestCase):
    def test_native_diagnostics_are_narrow_and_collect_before_failure(self):
        source = WORKFLOW.with_name("portable-reuse-proof.yml").read_text()
        block = source.split("  native-validation-diagnostics:\n", 1)[1].split("  windows-control-diagnostics:\n", 1)[0]
        for required in ("ci:native-validation-diagnostics", "pull_request.number == 31",
                         "head.repo.fork == false", "persist-credentials: false",
                         "runs-on: windows-2025", "uses: ./.github/actions/setup-msvc",
                         "uses: ./.github/actions/provision-sdk-dart-cache",
                         "dart pub get --enforce-lockfile --offline", "overwrite: false"):
            self.assertIn(required, block)
        self.assertEqual(4, block.count("continue-on-error: true"))
        self.assertLess(block.index("uses: actions/upload-artifact@"), block.index("Fail after collecting"))
        for forbidden in ("secrets.", "id-token: write", "attestations: write", "gradlew",
                          "capture-sdk-tooling", "product-attestation", "download-artifact"):
            self.assertNotIn(forbidden, block)
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        passed = {name: {"outcome": "success"} for name in ("cpp", "csharp", "dart-identity", "dart-lifecycle")}
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed),
                                     "DIAGNOSTIC_LABEL": "ci:native-validation-diagnostics"}):
            exec(compile(script, "native-host-diagnostic-result", "exec"), {})
        passed["cpp"]["outcome"] = "failure"
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed),
                                     "DIAGNOSTIC_LABEL": "ci:native-validation-diagnostics"}), self.assertRaises(AssertionError):
            exec(compile(script, "native-host-diagnostic-result", "exec"), {})
        for step in ("cpp", "csharp"):
            passed[step]["outcome"] = "skipped"
        self.assertEqual(2, block.count("if: github.event.label.name == 'ci:native-validation-diagnostics'"))
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed),
                                     "DIAGNOSTIC_LABEL": "ci:dart-validation-diagnostics"}):
            exec(compile(script, "native-host-diagnostic-result", "exec"), {})
            passed['dart-identity']['outcome'] = 'failure'
            with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed)}), self.assertRaises(AssertionError):
                exec(compile(script, "native-host-diagnostic-result", "exec"), {})
        self.assertIn("if: github.event.label.name != 'ci:dart-lifecycle-diagnostics'", block)
        passed['dart-identity']['outcome'] = 'skipped'
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed),
                                     "DIAGNOSTIC_LABEL": "ci:dart-lifecycle-diagnostics"}):
            exec(compile(script, "native-host-diagnostic-result", "exec"), {})
            passed['dart-lifecycle']['outcome'] = 'failure'
            with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(passed)}), self.assertRaises(AssertionError):
                exec(compile(script, "native-host-diagnostic-result", "exec"), {})

    def test_native_diagnostic_commands_preserve_exact_compiler_policy(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"VCToolsVersion": "14.51.36231"}):
            scratch = Path(temporary)
            _, commands = diagnostic.commands("cpp", scratch)
            for flag in ("/c", "/O2", "/Ob2", "/MD", "/EHsc", "/W4", "/WX", "/DNDEBUG"):
                self.assertIn(flag, commands[0])
            self.assertNotIn("/Zs", commands[0])
            self.assertIn("/Fo" + str(scratch / "host_smoke.obj"), commands[0])
            self.assertIn("/std:c++20", commands[0])
            self.assertTrue(commands[0][-1].endswith("consumer/host_smoke.cpp"))
            with patch("sys.platform", "win32"):
                _, commands = diagnostic.commands("csharp", scratch)
            self.assertEqual(["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-DCODEX_AGENT_BUILD"], commands[1][:6])
            fixture = scratch / "source/tests/CodexAgent.Tests/native/fake_codex_agent.c"
            self.assertTrue(fixture.read_bytes().startswith(b"#define _CRT_SECURE_NO_WARNINGS 1\n"))
        with patch.dict(os.environ, {"VCToolsVersion": "different"}), self.assertRaises(ValueError):
            diagnostic.commands("cpp", Path("unused"))

    def test_windows_controls_use_only_existing_inputs_and_collect_all_outcomes(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        source = WORKFLOW.with_name("portable-reuse-proof.yml").read_text()
        block = source.split("  windows-control-diagnostics:\n", 1)[1].split("  core-validation-diagnostics:\n", 1)[0]
        for required in ("ci:windows-control-diagnostics", "pull_request.number == 31",
                         "head.repo.fork == false", "persist-credentials: false",
                         "runs-on: windows-2025", "GIT_CONFIG_VALUE_0: 'false'", "overwrite: false"):
            self.assertIn(required, block)
        for forbidden in ("secrets.", "id-token: write", "gradlew", "setup-msvc", "dart-cache",
                          "download-artifact", "capture-sdk-tooling", "product-attestation"):
            self.assertNotIn(forbidden, block)
        self.assertEqual(4, block.count("continue-on-error: true"))
        self.assertLess(block.index("uses: actions/upload-artifact@"), block.index("Require complete diagnostic"))
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        results = {name: {"outcome": "success"} for name in diagnostic.CONTROL_CHECKS}
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(results)}):
            exec(compile(script, "windows-controls-result", "exec"), {})
        results["runtime-exit"]["outcome"] = "failure"
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(results)}), self.assertRaises(AssertionError):
            exec(compile(script, "windows-controls-result", "exec"), {})
        for check in diagnostic.CONTROL_CHECKS:
            cwd, commands = diagnostic.commands(check, Path("private"))
            self.assertEqual(diagnostic.ROOT, cwd)
            self.assertEqual([check, str(Path("private/probe")), "--probe"], commands[0][-3:])
        compile(diagnostic.RUNTIME_EXIT_PROBE, "runtime-exit-child", "exec")

    def test_windows_library_projection_rejects_duplicates_links_and_wrong_digest(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        from products.inventory import sha256_bytes
        import io
        import tarfile
        library = b"already-authenticated-package-fixture"
        compatibility = {"runtime": {"embeddedVariants": [dict(target="windows-x64",
            runtimeLibrarySha256=sha256_bytes(library))]}}
        def crate(*, duplicate=False, symlink=False):
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w:gz") as archive:
                for _ in range(2 if duplicate else 1):
                    member = tarfile.TarInfo("codex-agent-0.8.0/native/win-x64/codex_agent.dll")
                    member.size = len(library)
                    if symlink:
                        member.type = tarfile.SYMTYPE
                        member.linkname = "elsewhere"
                    archive.addfile(member, io.BytesIO(library))
            return raw.getvalue()
        self.assertEqual(library, diagnostic.windows_library_bytes(crate(), compatibility))
        for options in ({"duplicate": True}, {"symlink": True}):
            with self.assertRaises(ValueError):
                diagnostic.windows_library_bytes(crate(**options), compatibility)
        compatibility["runtime"]["embeddedVariants"][0]["runtimeLibrarySha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from authenticated"):
            diagnostic.windows_library_bytes(crate(), compatibility)

    def test_windows_original_mismatch_fails_before_body_download(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        import product_reuse
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-only"}), \
                patch.object(product_reuse, "_observe_ci_producer_jobs", return_value=[{"jobs": []}]), \
                patch.object(product_reuse, "_matching_ci_jobs", return_value=[{"id": 99}]), \
                patch.object(product_reuse, "_reuse_contract_ci_upload") as download:
            with self.assertRaisesRegex(ValueError, "original job differs"):
                diagnostic.pinned_windows_library(Path("unused"))
            download.assert_not_called()

    def test_failed_native_diagnostic_preserves_observations_not_success(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        import subprocess
        with tempfile.TemporaryDirectory() as temporary, patch("sys.platform", "win32"), \
                patch.object(diagnostic.subprocess, "check_output", return_value="observed\n"), \
                patch.object(diagnostic.subprocess, "run", return_value=subprocess.CompletedProcess(["cl"], 1)), \
                patch.dict(os.environ, {"VCToolsVersion": "14.51.36231"}), patch("builtins.print"):
            output = Path(temporary) / "diagnostics"
            self.assertEqual(1, diagnostic.diagnose("cpp", output))
            report = json.loads((output / "result.json").read_text())
            self.assertTrue(report["diagnosticOnly"])
            self.assertFalse(report["productExecuted"])
            self.assertFalse(report["passed"])
            self.assertEqual(1, report["commands"][0]["returnCode"])
            self.assertGreater(report["commands"][0]["elapsedNs"], 0)
            self.assertTrue((output / "0.log").is_file())

    def test_narrow_diagnostics_are_read_only_and_separate_from_product_proofs(self):
        source = WORKFLOW.with_name("portable-reuse-proof.yml").read_text()
        block = source.split("  core-validation-diagnostics:\n", 1)[1].split("  recovery-diagnostics:\n", 1)[0]
        for required in ("ci:core-validation-diagnostics", "pull_request.number == 31",
                         "head.repo.fork == false", "persist-credentials: false", "'archiveBodyBytesRead': 0",
                         "GIT_CONFIG_KEY_0: core.autocrlf", "GIT_CONFIG_VALUE_0: 'false'"):
            self.assertIn(required, block)
        for forbidden in ("secrets.", "id-token: write", "attestations: write", "gradlew", "response.read("):
            self.assertNotIn(forbidden, block)
        for script in block.split("        run: |\n")[1:]:
            compile(textwrap.dedent(script.split("\n      - ", 1)[0]),
                    "core-validation-host-diagnostic", "exec")
        for required in ("ci.tests.test_sdk_android_archive_provision",
                         "ci.tests.test_product_sdk_maven.SdkMavenPackagingTest.test_every_component_packages_its_exact_carrier_set",
                         "ci.tests.test_sdk_core_native_archive_provision", "packages: platform-tools",
                         "capture_facade_validation_sources", "_stage_fingerprint(captured)",
                         "GITHUB_TOKEN: ${{ github.token }}", "x-ratelimit-remaining", "report_api_error"):
            self.assertIn(required, block)
    def test_wave_thirteen_uses_original_inputs_and_fails_after_collection(self):
        source = CHILD.read_text()
        self.assertIn("GIT_CONFIG_KEY_0: core.autocrlf", source)
        self.assertIn("GIT_CONFIG_VALUE_0: 'false'", source)

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        parent = WORKFLOW.read_text()
        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13",
            "sdk-core-validation-result"))
        self.assertIn("uses: ./.github/workflows/sdk-core-validation.yml", parent)
        self.assertIn("sdk-core-validation-wave", parent.split("  sdk-completion:\n", 1)[1].split("\n", 1)[0])
        for block in (plan, worker, collect, result):
            self.assertIn("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'", block)
            self.assertIn("fromJSON(inputs.packageWave).result == 'success'", block)
        self.assertIn("family: core-validation", plan)
        self.assertIn("sdk-family: core-validation", collect)
        self.assertIn("wave: '13'", collect)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-core-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-core-validation-wave / sdk-core-validation-{target}", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("fromJSON(inputs.sdkInputs).result == 'success'", worker)
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", worker)
        self.assertIn("ci.sdk_core_native_archive_provision", worker)
        self.assertIn("name: Provision only Git-pinned native compiler archives\n        shell: bash", worker)
        self.assertIn("name: Select installed caller Java\n        shell: bash", worker)
        self.assertIn("uses: ./.github/actions/sdk-core-validation-worker", worker)
        self.assertLess(worker.index("ci.sdk_core_native_archive_provision"),
                        worker.index("uses: ./.github/actions/sdk-core-validation-worker"))
        for field in ("sdk-inputs-id", "sdk-inputs-sha256", "sdk-validation-tooling",
                      "sdk-apple-validation-policy", "native-compiler-archive", "build-key", "tree"):
            self.assertIn(field + ":", worker)
        self.assertIn("needs['sdk-core-package-wave'] = json.loads(os.environ['PACKAGE_RESULT'])", result)
        self.assertIn("select_native_state(needs, stage='core-validation')", result)

    def test_child_result_rejoins_package_parent_before_selection(self):
        block = CHILD.read_text().split("  sdk-core-validation-result:\n", 1)[1]
        script = textwrap.dedent(block.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        for required in (False, True):
            needs = needs_for("core-validation", required=required, state=locator("12", "0"))
            package = needs.pop("sdk-core-package-wave")
            with self.subTest(required=required), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "PACKAGE_RESULT": json.dumps(package),
                                          "GITHUB_OUTPUT": str(output)}, clear=True):
                    exec(compile(script, "sdk-core-validation-result", "exec"), {})
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual("13" if required else "12", values["sdk_state_wave"])
                package["result"] = "failure"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "PACKAGE_RESULT": json.dumps(package),
                                          "GITHUB_OUTPUT": str(output)}, clear=True), self.assertRaises(ValueError):
                    exec(compile(script, "sdk-core-validation-result", "exec"), {})


if __name__ == "__main__":
    unittest.main()
