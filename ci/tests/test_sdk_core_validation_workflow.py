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
    def test_cpp_failure_diagnostics_are_scoped_and_collect_both_failures(self):
        block = WORKFLOW.with_name("portable-reuse-proof.yml").read_text().split("  cpp-failure-diagnostics:\n", 1)[1]
        for required in ("ci:cpp-failure-diagnostics", "pull_request.number == 31", "head.repo.fork == false",
                         "runs-on: windows-2025", "persist-credentials: false", "GIT_CONFIG_VALUE_0: 'false'",
                         "uses: ./.github/actions/setup-msvc", "cpp-mock-linkage", "cpp-leaf-codegen", "overwrite: false"):
            self.assertIn(required, block)
        for forbidden in ("secrets.", "id-token: write", "gradlew", "download-artifact", "capture-sdk-tooling",
                          "product-attestation", "setup-dotnet", "rust-toolchain", "reuse-qualification"):
            self.assertNotIn(forbidden, block)
        self.assertEqual(2, block.count("continue-on-error: true"))
        self.assertLess(block.index("uses: actions/upload-artifact@"), block.index("Require complete diagnostic"))
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        outcomes = {name: {"outcome": "success"} for name in ("mock-linkage", "leaf-codegen")}
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(outcomes)}):
            exec(compile(script, "cpp-diagnostic-collection", "exec"), {})
        for outcome in ("failure", "skipped"):
            outcomes["leaf-codegen"]["outcome"] = outcome
            with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(outcomes)}), self.assertRaises(AssertionError):
                exec(compile(script, "cpp-diagnostic-collection", "exec"), {})

    def test_cpp_failure_probes_preserve_baseline_and_all_comparisons(self):
        import subprocess
        from ci.tests import native_windows_diagnostic as diagnostic
        ok = subprocess.CompletedProcess([], 0, b"")
        crash = subprocess.CompletedProcess([], 2, b"fatal error C1001: Internal compiler error")
        collision = subprocess.CompletedProcess([], 1, b"error LNK2005: already defined")
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,
                {"VCToolsVersion": "14.51.36231", "GITHUB_TOKEN": "must-not-reach-compiler"}), \
                patch.object(diagnostic, "observed") as run, patch("builtins.print"):
            scratch = Path(temporary)
            run.side_effect = [crash, ok, ok]
            diagnostic.cpp_failure_probe("cpp-leaf-codegen", scratch)
            calls = run.call_args_list
            self.assertEqual(3, len(calls))
            for call, options in zip(calls, (("/O2", "/Ob2"), ("/O2", "/Ob1"), ("/Od", "/Ob0")), strict=True):
                for flag in (*options, "/W4", "/WX", "/MD", "/EHsc", "/DNDEBUG", "/c"):
                    self.assertIn(flag, call.args[0])
                self.assertTrue(call.args[0][-1].endswith("tests/leaf_real_boundary_test.cpp"))
                self.assertEqual("/Zc:preprocessor", call.kwargs["env"]["CL"])
                self.assertNotIn("GITHUB_TOKEN", call.kwargs["env"])
                self.assertFalse(call.kwargs["check"])
            run.reset_mock(); run.side_effect = [crash, crash, crash]
            with self.assertRaisesRegex(ValueError, "Both bounded optimization"):
                diagnostic.cpp_failure_probe("cpp-leaf-codegen", scratch)
            self.assertEqual(3, run.call_count)
            run.reset_mock(); run.side_effect = [ok, ok, ok]
            with self.assertRaisesRegex(ValueError, "not reproduced"):
                diagnostic.cpp_failure_probe("cpp-leaf-codegen", scratch)
            run.reset_mock(); run.side_effect = [ok] * 5 + [collision, ok, ok, ok, ok]
            diagnostic.cpp_failure_probe("cpp-mock-linkage", scratch)
            links = [c.args[0] for c in run.call_args_list if c.args[0][0] == "link" and "/dll" not in c.args[0]]
            self.assertEqual([["main.obj", "runtime.lib", "mock.lib"], ["main.obj", "mock.lib", "runtime.lib"],
                              ["main.obj", "mock.obj", "runtime.lib"]], [c[-3:] for c in links])
            self.assertIn("__declspec(dllexport)", (scratch / "mock.c").read_text())
            self.assertEqual(2, sum(c.args[0][0].endswith(".exe") for c in run.call_args_list))
            with patch.dict(os.environ, {"VCToolsVersion": "different"}), self.assertRaises(ValueError):
                diagnostic.cpp_failure_probe("cpp-leaf-codegen", scratch)

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
                         "runs-on: windows-2025", "GIT_CONFIG_VALUE_0: 'false'", "overwrite: false",
                         "windows-control-diagnostics-${{ runner.os }}-"):
            self.assertIn(required, block)
        for forbidden in ("secrets.", "id-token: write", "gradlew", "dart-cache",
                          "download-artifact", "capture-sdk-tooling", "product-attestation",
                          "signature-initialization", "install-gh.sh", "macos-26-intel"):
            self.assertNotIn(forbidden, block)
        self.assertEqual(3, block.count("continue-on-error: true"))
        self.assertEqual(2, block.count("if: runner.os == 'Windows'"))
        self.assertNotIn("rust-host-exit", block)  # Existing fifteen exit observations are sufficient.
        worker = (WORKFLOW.parents[1] / "actions/sdk-native-validation-worker/action.yml").read_text()
        self.assertIn("python-version: '3.12.10'", block)
        self.assertIn("uses: ./.github/actions/setup-msvc", block)
        rust = re.search(r"uses: dtolnay/rust-toolchain@\w+", block).group()
        self.assertIn(rust, worker)
        dotnet = re.search(r"uses: actions/setup-dotnet@\w+", block).group()
        self.assertIn(dotnet, worker)
        self.assertLess(block.index("uses: actions/upload-artifact@"), block.index("Require complete diagnostic"))
        script = textwrap.dedent(block.split("        run: |\n", 1)[1])
        results = {name: {"outcome": "success"} for name in
                   ("csharp-loader-security", "cpp-leaf-preprocessor", "rust-fixture-compiler")}
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(results)}):
            exec(compile(script, "windows-controls-result", "exec"), {})
        results["csharp-loader-security"]["outcome"] = "failure"
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(results)}), self.assertRaises(AssertionError):
            exec(compile(script, "windows-controls-result", "exec"), {})
        results["csharp-loader-security"]["outcome"] = "skipped"
        with patch.dict(os.environ, {"DIAGNOSTIC_STEPS": json.dumps(results)}), self.assertRaises(AssertionError):
            exec(compile(script, "windows-controls-result", "exec"), {})
        for check in (*diagnostic.CONTROL_CHECKS, *diagnostic.FOLLOWUP_CHECKS, *diagnostic.REMAINING_CHECKS):
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

    def test_rust_exit_diagnostic_preserves_plain_control_before_private_instrumentation(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        import native_wrappers
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(diagnostic, "pinned_windows_library") as authenticated, \
                patch.object(native_wrappers, "safe_extract_tar"), \
                patch.object(diagnostic, "observed") as run, patch("builtins.print"):
            scratch = Path(temporary).resolve()
            original = (diagnostic.ROOT / "codex-agent-bindings/rust/consumer/src/bin/host_smoke.rs").read_text()
            builds = []
            def observe(command, **kwargs):
                if command[:2] == ["cargo", "build"]:
                    builds.append((scratch / "consumer/src/bin/host_smoke.rs").read_text())
            run.side_effect = observe
            diagnostic.rust_host_probe(scratch)
            authenticated.assert_called_once_with(scratch, crate_path=scratch / "original.crate")
            calls = run.call_args_list
            self.assertEqual(19, len(calls))
            self.assertEqual(["rustc", "--version", "--verbose"], calls[0].args[0])
            self.assertEqual(["--release", "--locked", "--offline", "--bin", "codex-agent-rust-host-smoke"],
                             calls[2].args[0][-5:])
            self.assertEqual(calls[2].args, calls[8].args)
            trials = calls[3:8] + calls[9:]
            self.assertEqual(15, len(trials))
            for index, call in enumerate(trials):
                self.assertEqual(calls[3].args, call.args)
                self.assertNotIn("GITHUB_TOKEN", call.kwargs["env"])
                self.assertNotIn("GH_TOKEN", call.kwargs["env"])
                self.assertEqual("1" if index >= 10 else None, call.kwargs["env"].get("CODEX_AGENT_DIAGNOSTIC_PIN"))
                self.assertFalse(call.kwargs["check"])
            projected = (scratch / "consumer/src/bin/host_smoke.rs").read_text()
            self.assertEqual([original, projected], builds)
            self.assertEqual(original, projected.replace("\n" + diagnostic.RUST_EXIT_PIN_PROBE, ""))

    def test_private_signing_probe_also_observes_dotnet_copy_and_process_errors(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as temporary, \
                patch("ci.sdk_native_validation_workflow._private_windows_validation_parent") as private, \
                patch.object(diagnostic, "observed") as run, \
                patch.object(diagnostic, "csharp_signing_probe") as dotnet, \
                patch.dict(os.environ, {"SystemRoot": "C:/Windows", "PROGRAMDATA": "C:/ProgramData"}):
            scratch = Path(temporary) / "probe"
            diagnostic.control_probe("signing-private-parent", scratch)
            private.assert_called_once_with(scratch)
            self.assertEqual(6, run.call_count)
            self.assertTrue(run.call_args_list[1].kwargs["check"])
            verification = run.call_args_list[2:4]
            self.assertEqual(verification[0].args, verification[1].args)
            self.assertEqual(verification[0].kwargs["input"], verification[1].kwargs["input"])
            self.assertNotIn("GITHUB_TOKEN", verification[1].kwargs["env"])
            from ci.products import sdk_validation
            import inspect
            names = '{"PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"}'
            with patch.dict(os.environ, {"GITHUB_TOKEN": "not-a-child-input"}):
                environment = sdk_validation._fixed_environment()
            self.assertEqual("C:/ProgramData", environment["PROGRAMDATA"])
            self.assertNotIn("GITHUB_TOKEN", environment)
            self.assertIn(names, inspect.getsource(diagnostic.control_probe))
            repaired = run.call_args_list[4]
            self.assertEqual(verification[0].args, repaired.args)
            self.assertEqual("C:/ProgramData", repaired.kwargs["env"]["PROGRAMDATA"])
            self.assertNotIn("GITHUB_TOKEN", repaired.kwargs["env"])
            call = run.call_args_list[5]
            command = call.args[0]
            self.assertEqual(["pwsh", "-NoProfile", "-NonInteractive", "-File"], command[:4])
            self.assertFalse(call.kwargs["check"])
            self.assertEqual(diagnostic.CSHARP_SIGNING_PROBE, Path(command[4]).read_text())
            self.assertEqual(Path(command[6]) / "test-only-key", Path(command[5]))
            dotnet.assert_called_once_with(scratch)
            for required in ("[IO.File]::Copy", "[Diagnostics.ProcessStartInfo]", "ArgumentList.Add",
                             "StandardError.ReadToEnd", "exit $process.ExitCode"):
                self.assertIn(required, diagnostic.CSHARP_SIGNING_PROBE)

    def test_signature_probe_allows_macos_without_allowing_windows_consumers_there(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        for platform in ("win32", "darwin", "linux"):
            for check in diagnostic.CHECKS:
                with self.subTest(platform=platform, check=check), patch.object(diagnostic.sys, "platform", platform):
                    if platform == "win32" or (platform == "darwin" and check == "signature-initialization"):
                        diagnostic.require_diagnostic_host(check)
                    else:
                        with self.assertRaises(ValueError):
                            diagnostic.require_diagnostic_host(check)

    def test_security_diagnostic_preserves_entire_suite_and_uses_only_unit_fixtures(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as temporary, patch.object(diagnostic, "observed") as run, \
                patch("ci.sdk_native_validation_workflow._private_windows_validation_parent"):
            scratch = Path(temporary)
            diagnostic.csharp_security_probe(scratch)
            scratch, = (scratch / "validation/outputs").glob(".csharp-binding-evidence-*")
            original = diagnostic.ROOT / "codex-agent-bindings/csharp/tests/CodexAgent.Tests/RuntimeLoaderSecurity.cs"
            projected = scratch / "source/tests/CodexAgent.Tests/RuntimeLoaderSecurity.cs"
            instrumentation = '''                Console.WriteLine("fixtureKeyPath=" + privateKey + ";payloadPath=" + path);
                Console.WriteLine("fixtureKeySha256=" + Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(privateKey))));
'''
            self.assertEqual(1, projected.read_text().count(instrumentation))
            self.assertEqual(original.read_text(), projected.read_text().replace(instrumentation, "").replace(
                "Console.Error.Write(process.StandardError.ReadToEnd());", "_ = process.StandardError.ReadToEnd();"))
            self.assertEqual(3, run.call_count)
            restore, build, execute = (call.args[0] for call in run.call_args_list)
            self.assertEqual(["dotnet", "restore"], restore[:2])
            self.assertEqual(["dotnet", "build"], build[:2])
            self.assertIn("-p:UseSharedCompilation=false", build)
            self.assertFalse(any("CodexAgentRealSdkPath" in value for value in build))
            self.assertEqual("--runtime-loader-signed-fixture", execute[-1])
            entry = (scratch / "source/tests/CodexAgent.Tests/Program.cs").read_text()
            injection = '''if (args is ["--runtime-loader-signed-fixture"])
{
    RuntimeLoaderSecurity.LoadFakeNativeForTests();
    return;
}

'''
            self.assertEqual(1, entry.count(injection))
            self.assertEqual(original.with_name("Program.cs").read_text(), entry.replace(injection, ""))
            self.assertEqual(str(scratch / "dotnet-home"), run.call_args.kwargs["env"]["DOTNET_CLI_HOME"])
            self.assertNotIn("check", run.call_args.kwargs)  # Failure must fail this diagnostic.
            self.assertNotIn("GITHUB_TOKEN", run.call_args.kwargs["env"])

    def test_compiler_diagnostic_uses_exact_rust_source_and_guarded_production_adapter(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        with tempfile.TemporaryDirectory() as temporary, patch.object(diagnostic, "observed") as run, \
                patch("ci.sdk_native_validation_workflow._windows_rust_fixture_compiler", return_value={}) as adapter:
            scratch = Path(temporary).resolve()
            diagnostic.compiler_probe("rust-fixture-compiler", scratch)
            adapter.assert_called_once()
            raw = (diagnostic.ROOT / "codex-agent-bindings/rust/tests/lifecycle.rs").read_text()
            function = "fn compile_fixture_with_defines(" + raw.split("fn compile_fixture_with_defines(", 1)[1].split("\nstruct ThreadWake", 1)[0]
            self.assertIn(function, (scratch / "probe.rs").read_text())
            self.assertEqual(4, run.call_count)
            self.assertEqual("sha256:" + "a" * 64, run.call_args.kwargs["env"]["CODEX_AGENT_TEST_CONTRACT_DIGEST"])
            self.assertIn("with spaces", run.call_args.kwargs["env"]["TEMP"])
            self.assertNotIn("check", run.call_args.kwargs)
            run.reset_mock()
            with patch.dict(os.environ, {"VCToolsVersion": "14.51.36231"}):
                diagnostic.compiler_probe("cpp-leaf-preprocessor", scratch)
            self.assertEqual("/Zc:preprocessor", run.call_args.kwargs["env"]["CL"])
            self.assertTrue(run.call_args.args[0][-1].endswith("tests/leaf_behavior_test.cpp"))
            self.assertIn("/WX", run.call_args.args[0])

    def test_signature_initialization_probe_retains_all_trust_constraints(self):
        from ci.tests import native_windows_diagnostic as diagnostic
        import reuse_qualification
        import subprocess
        captured = {"qualification.json": b"frozen", "completion.json": b"sdk", "bundle.jsonl": b"bundle"}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(reuse_qualification, "_fetch_qualification_archive", return_value=({}, captured)) as fetch, \
                patch.object(diagnostic, "observed", return_value=subprocess.CompletedProcess([], 1)) as run, \
                patch.dict(os.environ, {"GITHUB_TOKEN": "test-only"}), patch("builtins.print"):
            scratch = Path(temporary) / "probe"
            diagnostic.control_probe("signature-initialization", scratch)
            self.assertEqual(2, fetch.call_count)
            calls = [call for call in run.call_args_list if call.args[0][1:3] == ["-c", diagnostic.SIGNATURE_INITIALIZATION_PROBE]]
            self.assertEqual(6, len(calls))
            self.assertEqual(3, len({call.kwargs["env"]["GH_CACHE_DIR"] for call in calls}))
            for call in calls:
                command = call.args[0]
                self.assertFalse(call.kwargs["check"])
                bundle = Path(command[4])
                self.assertEqual(".jsonl", bundle.suffix)
                self.assertEqual(captured["bundle.jsonl"], bundle.read_bytes())
                with patch.object(reuse_qualification, "_authenticate_native_subject") as verify, \
                        patch("sys.argv", ["probe", *command[3:]]):
                    exec(compile(diagnostic.SIGNATURE_INITIALIZATION_PROBE, "production-verifier-probe", "exec"))
                name = Path(command[3]).name.removesuffix(".subject")
                verify.assert_called_once_with(captured[name], captured["bundle.jsonl"], name,
                    signer_commit=command[5], source_commit=command[5])
            self.assertEqual(b"frozen", (scratch / "qualification.json.subject").read_bytes())
            self.assertEqual(b"sdk", (scratch / "completion.json.subject").read_bytes())

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
            self.assertEqual(0, report["productPhasesProduced"])
            self.assertFalse(report["existingRuntimeExecutionRequested"])
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
