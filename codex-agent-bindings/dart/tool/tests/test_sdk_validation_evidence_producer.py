from __future__ import annotations

import importlib.util
import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "dart_sdk_validation_evidence", Path(__file__).resolve().parents[1] / "produce_sdk_validation_evidence.py",
)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


class DartSdkValidationEvidenceProducerTest(unittest.TestCase):
    """Mocks execution: these fixtures prove orchestration, never Dart/native evidence."""

    def test_combined_subprocess_capture_preserves_invalid_utf8_nul_and_empty_output(self):
        for raw in (b"stdout\r\nstderr\x00\xff\x80\n", b""):
            with self.subTest(raw=raw), Fixture() as fixture:
                original_program = fixture.program.read_bytes()
                original_compatibility = fixture.compatibility.read_bytes()
                def run(command, *, cwd, env, check, stdout, stderr):
                    self.assertEqual(subprocess.STDOUT, stderr)
                    self.assertIn("b", stdout.mode)
                    self.assertEqual(["--reporter", "expanded", "test"], command[3:])
                    stdout.write(raw)
                    return fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)
                with patch.object(producer.subprocess, "run", side_effect=run) as called:
                    fixture.produce()
                called.assert_called_once()
                captured = (fixture.output / "dart-execution.json").read_bytes()
                execution = json.loads(captured)
                self.assertEqual({"schemaVersion", "exitCode", "outputBase64"}, set(execution))
                self.assertEqual(1, execution["schemaVersion"])
                self.assertEqual(0, execution["exitCode"])
                self.assertEqual(raw, base64.b64decode(execution["outputBase64"], validate=True))
                self.assertEqual((json.dumps(execution, sort_keys=True, separators=(",", ":")) + "\n").encode(), captured)
                self.assertTrue(captured)
                self.assertFalse((fixture.output / "dart-test.log").exists())
                self.assertTrue(all(path.stat().st_size > 0 for path in fixture.output.rglob("*") if path.is_file()))
                self.assertEqual(original_program, fixture.program.read_bytes())
                self.assertEqual(original_compatibility, fixture.compatibility.read_bytes())

    def test_failed_subprocess_raw_log_never_publishes_partial_success_output(self):
        with Fixture() as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_bytes(b"previous output")
            raw = b"partial failure\x00\xff\r\n"
            diagnostics = io.BytesIO()
            def fail(command, *, cwd, env, check, stdout, stderr):
                stdout.write(raw)
                raise subprocess.CalledProcessError(7, command)
            with patch.object(producer.subprocess, "run", side_effect=fail), \
                    patch.object(producer.sys, "stderr", SimpleNamespace(buffer=diagnostics)), \
                    self.assertRaises(subprocess.CalledProcessError) as raised:
                fixture.produce()
            self.assertEqual(7, raised.exception.returncode)
            self.assertEqual(raw, diagnostics.getvalue())
            self.assertFalse(fixture.output.exists())
            self.assertTrue(fixture.program.is_file())

    def test_existing_runner_executes_complete_suite_in_isolated_source_tree(self):
        with Fixture() as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale")
            original_config = fixture.config.read_bytes()
            original_compatibility = fixture.compatibility.read_bytes()
            source_program = fixture.program.read_bytes()
            observed = {}

            def run(command, *, cwd, env, check, stdout, stderr):
                self.assertEqual("selected-dart", command[0])
                self.assertEqual(str(fixture.runner), command[2])
                self.assertEqual(["--reporter", "expanded", "test"], command[3:])
                self.assertNotIn("pub", command)
                self.assertNotEqual(fixture.source, cwd)
                self.assertEqual(source_program, (cwd / "test/enum_parity_test.dart").read_bytes())
                self.assertEqual(fixture.marker.read_bytes(), (cwd.parents[1] / "settings.gradle.kts").read_bytes())
                private_config = Path(command[1].removeprefix("--packages="))
                config = json.loads(private_config.read_text())
                roots = {entry["name"]: entry["rootUri"] for entry in config["packages"]}
                self.assertEqual(cwd.as_uri() + "/", roots["codex_agent"])
                native = cwd / "lib/src/native"
                self.assertEqual({"sdk-compatibility.json"}, {path.name for path in native.iterdir()})
                self.assertEqual(original_compatibility, (native / "sdk-compatibility.json").read_bytes())
                self.assertEqual(fixture.test_package.as_uri() + "/", roots["test"])
                self.assertEqual(str(fixture.api), env["CODEX_AGENT_CANONICAL_API_REPORT"])
                self.assertEqual(str(fixture.bootstrap), env["CODEX_AGENT_C_ABI_BOOTSTRAP_EVIDENCE"])
                self.assertEqual(str(fixture.sdk), env["CODEX_AGENT_C_SDK_ROOT"])
                self.assertEqual(str(fixture.library), env["CODEX_AGENT_REAL_LIBRARY"])
                self.assertTrue(check)
                observed["cwd"] = cwd
                return fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)

            with patch.object(producer.subprocess, "run", side_effect=run) as runner:
                fixture.produce()
            runner.assert_called_once()
            self.assertFalse(observed["cwd"].exists())
            self.assertFalse((fixture.source / "build/parity").exists())
            self.assertEqual(original_config, fixture.config.read_bytes())
            self.assertEqual(original_compatibility, fixture.compatibility.read_bytes())
            self.assertEqual("stale source declaration", fixture.source_compatibility.read_text())
            self.assertEqual(source_program, fixture.program.read_bytes())
            self.assertEqual({"compiler-evidence.tsv", "executed-tests.tsv", "test-program", "native-evidence", "dart-execution.json"},
                             {path.name for path in fixture.output.iterdir()})
            self.assertEqual(producer.NATIVE_ENTRIES,
                             {path.name for path in (fixture.output / "native-evidence").iterdir()})
            leaf = fixture.output / "native-evidence" / producer.LEAF_EVIDENCE
            self.assertEqual(producer.LEAF_FILES, {path.name for path in leaf.iterdir()})
            self.assertEqual(fixture.leaf_source.read_bytes(), (leaf / "real-leaf-boundary.c").read_bytes())
            self.assertEqual(b"fixture executable", (leaf / producer.LEAF_EXECUTABLE).read_bytes())
            self.assertEqual(source_program, (fixture.output / "test-program").read_bytes())

    def test_missing_or_extra_native_auxiliaries_cannot_become_full_proof(self):
        for mutation in ("missing", "extra", "empty", "symlink", "leaf-missing", "leaf-extra",
                         "leaf-empty", "leaf-symlink", "classifier-mismatch", "schema-bool",
                         "exit-float", "base64-padbits", "library-directory"):
            with self.subTest(mutation=mutation), Fixture() as fixture:
                def run(command, *, cwd, env, check, stdout, stderr):
                    result = fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)
                    native = cwd / "build/parity"
                    path = native / sorted(producer.NATIVE_RECEIPTS)[0]
                    if mutation == "missing":
                        path.unlink()
                    elif mutation == "extra":
                        (native / "undeclared.tsv").write_text("extra")
                    elif mutation == "empty":
                        path.write_text("")
                    elif mutation == "symlink":
                        path.unlink()
                        path.symlink_to(fixture.api)
                    elif mutation == "leaf-missing":
                        (native / producer.LEAF_EVIDENCE / "compiler-execution.json").unlink()
                    elif mutation == "leaf-extra":
                        (native / producer.LEAF_EVIDENCE / "undeclared").write_text("extra")
                    elif mutation == "leaf-empty":
                        (native / producer.LEAF_EVIDENCE / producer.LEAF_EXECUTABLE).write_bytes(b"")
                    elif mutation == "leaf-symlink":
                        leaf = native / producer.LEAF_EVIDENCE / "real-leaf-boundary.c"
                        leaf.unlink()
                        leaf.symlink_to(fixture.api)
                    elif mutation == "classifier-mismatch":
                        (native / "host-classifier.txt").write_text("linux-x64\n")
                    else:
                        execution = native / producer.LEAF_EVIDENCE / "compiler-execution.json"
                        value = json.loads(execution.read_text())
                        if mutation == "schema-bool":
                            value["schemaVersion"] = True
                        elif mutation == "exit-float":
                            value["exitCode"] = 0.0
                        elif mutation == "base64-padbits":
                            value["stdoutBase64"] = "AB=="
                        else:
                            value["runtimeLibraryDirectory"] = str(fixture.root / "wrong-library")
                        execution.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
                    return result
                with patch.object(producer.subprocess, "run", side_effect=run), self.assertRaises(ValueError):
                    fixture.produce()
                self.assertFalse(fixture.output.exists())

    def test_all_five_classifiers_use_real_boundaries_and_leaf_retains_lossless_execution(self):
        root = Path(__file__).resolve().parents[2]
        for name in ("agent_parity.dart", "host_parity.dart", "conversation_parity.dart",
                     "leaf_service_parity.dart"):
            source = (root / "test" / name).read_text()
            self.assertIn("currentClassifier()", source, name)
            self.assertNotIn("if (!Platform.isMacOS) return", source, name)
            self.assertNotIn("real-macos-arm64", source, name)
            self.assertNotIn("requires macOS Arm64", source, name)
        leaf = (root / "test/leaf_service_parity.dart").read_text()
        for expected in ("codex_agent.lib", "compiler-execution.json", "boundary-execution.json",
                         "stdoutEncoding: null", "stderrEncoding: null", "'/WX'", "'-Werror'",
                         "'/I${requiredCSdkInclude().path}'", "'PATH': <String>[",
                         "'runtimeLibraryDirectory': runtimeLibraryDirectory", "currentClassifier()"):
            self.assertIn(expected, leaf)
        self.assertIn("if (!Platform.isWindows) '-fPIC'", leaf)
        self.assertIn("if (!Platform.isWindows)\n            '-Wl,-rpath", leaf)

    def test_failed_and_incomplete_execution_invalidates_only_owned_output(self):
        with Fixture() as fixture:
            fixture.output.mkdir()
            (fixture.output / "stale").write_text("stale")
            with patch.object(producer.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "dart")), \
                    self.assertRaises(subprocess.CalledProcessError):
                fixture.produce()
            self.assertFalse(fixture.output.exists())

            def incomplete(command, *, cwd, env, check, stdout, stderr):
                result = fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)
                path = Path(env[producer.EVIDENCE_ENV]) / "executed-tests.tsv"
                path.write_text("executedTestId\tstatus\nfixture\tpassed\n")
                return result
            with patch.object(producer.subprocess, "run", side_effect=incomplete), \
                    self.assertRaisesRegex(ValueError, "exactly 556"):
                fixture.produce()
            self.assertFalse(fixture.output.exists())
            self.assertTrue(fixture.program.is_file())

    def test_missing_artifact_config_runner_or_test_program_fails_before_deletion(self):
        for name in ("api", "bootstrap", "library", "compatibility", "config", "runner", "program", "marker"):
            with self.subTest(name=name), Fixture() as fixture:
                fixture.output.mkdir()
                retained = fixture.output / "retained"
                retained.write_text("original")
                getattr(fixture, name).unlink()
                with patch.object(producer.subprocess, "run") as runner, self.assertRaises(ValueError):
                    fixture.produce()
                runner.assert_not_called()
                self.assertEqual("original", retained.read_text())

    def test_package_resolution_has_no_remote_duplicate_or_wrong_source_fallback(self):
        for mutation in ("remote", "duplicate", "missing-test", "wrong-source", "wrong-package-uri"):
            with self.subTest(mutation=mutation), Fixture() as fixture:
                config = json.loads(fixture.config.read_text())
                if mutation == "remote":
                    config["packages"][1]["rootUri"] = "https://example.invalid/test"
                elif mutation == "duplicate":
                    config["packages"].append(config["packages"][1])
                elif mutation == "missing-test":
                    config["packages"].pop()
                elif mutation == "wrong-package-uri":
                    config["packages"][0]["packageUri"] = (fixture.source / "lib").as_uri()
                else:
                    config["packages"][0]["rootUri"] = fixture.test_package.as_uri()
                fixture.config.write_text(json.dumps(config))
                with patch.object(producer.subprocess, "run") as runner, self.assertRaises(ValueError):
                    fixture.produce()
                runner.assert_not_called()

    def test_output_scope_protects_broad_source_and_input_paths(self):
        with Fixture() as fixture:
            for path in (Path(fixture.root.anchor), fixture.repository, fixture.source,
                         fixture.source / "test", fixture.sdk, fixture.source / "pubspec.yaml"):
                with self.subTest(path=path), patch.object(producer, "_invalidate") as invalidator, \
                        patch.object(producer.subprocess, "run") as runner, self.assertRaises(ValueError):
                    fixture.produce(output=path)
                invalidator.assert_not_called()
                runner.assert_not_called()
            self.assertTrue(fixture.program.is_file())

    def test_source_native_resources_are_not_inputs_or_copied_fallbacks(self):
        for mutation in ("missing", "stale-payload", "symlink-tree", "symlink-library"):
            with self.subTest(mutation=mutation), Fixture() as fixture:
                native = fixture.source / producer.NATIVE_RESOURCE
                fixture.source_compatibility.unlink()
                if mutation == "symlink-tree":
                    native.rmdir()
                    native.symlink_to(fixture.sdk, target_is_directory=True)
                elif mutation == "symlink-library":
                    (native / "ignored-library.dylib").symlink_to(fixture.library)
                elif mutation == "stale-payload":
                    (native / "ignored-library.dylib").write_bytes(b"untrusted source runtime")

                def run(command, *, cwd, env, check, stdout, stderr):
                    private = cwd / producer.NATIVE_RESOURCE
                    self.assertFalse(private.is_symlink())
                    self.assertEqual({"sdk-compatibility.json"}, {path.name for path in private.iterdir()})
                    self.assertEqual(fixture.compatibility.read_bytes(),
                                     (private / "sdk-compatibility.json").read_bytes())
                    return fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)

                with patch.object(producer.subprocess, "run", side_effect=run):
                    fixture.produce()

    def test_invalid_imported_compatibility_and_overlap_fail_before_deletion(self):
        for mutation in ("empty", "symlink", "overlap"):
            with self.subTest(mutation=mutation), Fixture() as fixture:
                fixture.output.mkdir()
                sentinel = fixture.output / "preserved"
                sentinel.write_text("original")
                if mutation == "empty":
                    fixture.compatibility.write_bytes(b"")
                elif mutation == "symlink":
                    fixture.compatibility.unlink()
                    fixture.compatibility.symlink_to(fixture.api)
                else:
                    fixture.compatibility = sentinel
                with patch.object(producer.subprocess, "run") as runner, self.assertRaises(ValueError):
                    fixture.produce()
                runner.assert_not_called()
                self.assertEqual("original", sentinel.read_text())

    def test_imported_compatibility_uses_captured_bytes_not_a_later_source_read(self):
        with Fixture() as fixture:
            captured = fixture.compatibility.read_bytes()
            original_source_files = producer._source_files

            def source_files():
                fixture.compatibility.write_bytes(b"later mutation\n")
                return original_source_files()

            def run(command, *, cwd, env, check, stdout, stderr):
                self.assertEqual(captured, (cwd / producer.NATIVE_RESOURCE / "sdk-compatibility.json").read_bytes())
                fixture.compatibility.write_bytes(captured)
                return fixture.run(command, cwd=cwd, env=env, check=check, stdout=stdout, stderr=stderr)

            with patch.object(producer, "_source_files", side_effect=source_files), \
                    patch.object(producer.subprocess, "run", side_effect=run):
                fixture.produce()
            self.assertEqual(captured, fixture.compatibility.read_bytes())

    def test_symbolic_sources_inputs_and_output_parents_are_rejected(self):
        for mutation in ("source", "input", "output-parent"):
            with self.subTest(mutation=mutation), Fixture() as fixture:
                output = fixture.output
                if mutation == "source":
                    (fixture.source / "lib/unsafe.dart").symlink_to(fixture.api)
                elif mutation == "input":
                    fixture.library.unlink()
                    fixture.library.symlink_to(fixture.api)
                else:
                    parent = fixture.root / "linked"
                    parent.symlink_to(fixture.source, target_is_directory=True)
                    output = parent / "build/output"
                with patch.object(producer, "_invalidate") as invalidator, \
                        patch.object(producer.subprocess, "run") as runner, self.assertRaises(ValueError):
                    fixture.produce(output=output)
                invalidator.assert_not_called()
                runner.assert_not_called()

    def test_legacy_evidence_path_remains_default_and_full_suite_calls_are_retained(self):
        source = (Path(__file__).resolve().parents[2] / "test/enum_parity_test.dart").read_text()
        self.assertIn("Platform.environment['CODEX_AGENT_DART_EVIDENCE_DIRECTORY'] ??", source)
        self.assertIn("'build/parity'", source)
        for call in ("verifyRealLeafBoundary", "verifyRealConversationBoundary", "verifyRealAgentBoundary",
                     "verifyRealHostBoundary", "_compileValueHeaderReferences"):
            self.assertIn(f"await {call}(", source)

    def test_finalizer_children_use_existing_package_config_without_pub_dispatch(self):
        source = (Path(__file__).resolve().parents[2] / "test/native_behavior_test.dart").read_text()
        finalizers = source[source.index("'host finalizer performs semantic close") :]
        for expected in ("Platform.resolvedExecutable", "'--enable-vm-service=0'",
                         "'--disable-service-auth-codes'", "'tool/finalizer_probe.dart'",
                         "'--packages=${Platform.environment['CODEX_AGENT_TEST_PACKAGE_CONFIG']}'",
                         ").timeout(const Duration(seconds: 30))"):
            self.assertEqual(2, finalizers.count(expected), expected)
        self.assertIn("libraryPath,\n        'child',", finalizers)
        self.assertNotIn("'run'", finalizers)
        self.assertNotIn("'pub'", finalizers)

    def test_positive_security_identities_follow_imported_resource_and_negatives_stay_distinct(self):
        root = Path(__file__).resolve().parents[2]
        security = (root / "test/runtime_compatibility_test.dart").read_text()
        self.assertIn("'contractDigest': RuntimeCompatibility.load().contractDigest,", security)
        self.assertIn("RuntimeCompatibility.load().contractDigest == _digestA ? _digestB : _digestA;",
                      " ".join(security.split()))
        self.assertIn("{...valid, 'contractDigest': _wrongContractDigest}", security)
        self.assertIn("_runtime(value)['requiredContractDigest'] = _wrongContractDigest", security)
        self.assertIn("identity['contractDigest'] = _wrongContractDigest;", security)
        self.assertIn("File('lib/src/native/sdk-compatibility.json').readAsStringSync()", security)
        self.assertNotIn("sha256:" + "1" * 64, security)
        fixture = (root / "test/native_fixture.dart").read_text()
        self.assertIn("final compatibility = RuntimeCompatibility.load();", fixture)
        self.assertIn("${compatibility.contractDigest}", fixture)
        loader = (root / "lib/src/runtime_compatibility.dart").read_text()
        self.assertIn("package:codex_agent/src/native/sdk-compatibility.json", loader)


class Fixture:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repository"
        self.source = self.repository / "codex-agent-bindings/dart"
        self.program = self.file("repository/codex-agent-bindings/dart/test/enum_parity_test.dart", "original fixture program")
        self.leaf_source = self.file(
            "repository/codex-agent-bindings/dart/test/native/real_leaf_boundary.c",
            "fixture real leaf source\n",
        )
        self.file("repository/codex-agent-bindings/dart/lib/codex_agent.dart", "fixture source")
        self.source_compatibility = self.file(
            "repository/codex-agent-bindings/dart/lib/src/native/sdk-compatibility.json", "stale source declaration")
        self.file("repository/codex-agent-bindings/dart/pubspec.yaml", "name: codex_agent\n")
        self.marker = self.file("repository/settings.gradle.kts", "fixture repository marker")
        self.test_package = self.root / "test-package"
        self.runner = self.file("test-package/bin/test.dart", "fixture test runner")
        self.config = self.file("repository/codex-agent-bindings/dart/.dart_tool/package_config.json", json.dumps({
            "configVersion": 2,
            "packages": [
                {"name": "codex_agent", "rootUri": "../", "packageUri": "lib/"},
                {"name": "test", "rootUri": self.test_package.as_uri(), "packageUri": "lib/"},
            ],
        }))
        self.api = self.file("inputs/api.json", "{}")
        self.bootstrap = self.file("inputs/bootstrap.json", "{}")
        self.compatibility = self.file("inputs/sdk-compatibility.json", '{"fixture":"imported exact bytes"}\n')
        self.sdk = self.root / "inputs/c-sdk"
        self.file("inputs/c-sdk/include/codex_agent.h", "fixture header")
        self.library = self.file("inputs/library.dylib", "fixture runtime")
        self.output = self.root / "output"
        self.patch = patch.multiple(producer, ROOT=self.source, CHECKOUT=self.repository)

    def file(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def produce(self, *, output=None):
        producer.produce(self.api, self.bootstrap, self.sdk, self.library, output or self.output,
                         sdk_compatibility=self.compatibility,
                         dart_executable="selected-dart", package_config=self.config)

    def run(self, command, *, cwd, env, check, stdout, stderr):
        if stderr != subprocess.STDOUT or "b" not in stdout.mode:
            raise AssertionError("Dart subprocess output must be captured as combined raw bytes")
        evidence = Path(env[producer.EVIDENCE_ENV])
        (evidence / "compiler-evidence.tsv").write_text("compilerEvidenceId\tpublicSymbols\nfixture\tsymbol\n")
        (evidence / "executed-tests.tsv").write_text("executedTestId\tstatus\n" + "".join(
            f"fixture-{number:03}\tpassed\n" for number in range(556)
        ))
        native = cwd / "build/parity"
        native.mkdir(parents=True)
        classifier = "macos-arm64"
        (native / "host-classifier.txt").write_text(f"{classifier}\n")
        receipts = {
            "agent-native-tests.tsv":
                "capabilityKey\tcSymbol\tclassifier\tstatus\nfixture.agent\tcodex_agent_fixture\tmacos-arm64\tpassed\n",
            "host-native-tests.tsv":
                "executedTestId\tnativeSymbol\tclassifier\tstatus\nfixture.host\tcodex_agent_fixture\tmacos-arm64\tpassed\n",
            "conversation-real-sdk-receipt.tsv":
                "capabilityKey\tpublicSymbol\texactNativeCalls\tclassifier\tboundary\tstatus\n"
                "fixture.conversation\tConversation.fixture\tcodex_agent_fixture:1\tmacos-arm64\t"
                "typed-null-handle\tpassed\n",
            "leaf-real-sdk-receipt.tsv":
                "capabilityKey\tpublicSymbol\texactNativeCalls\tclassifier\tboundary\tstatus\n"
                "fixture.leaf\tLeaf.fixture\tcodex_agent_fixture\tmacos-arm64\tnull-handle\tpassed\n",
        }
        for name, contents in receipts.items():
            (native / name).write_text(contents)
        leaf = native / producer.LEAF_EVIDENCE
        leaf.mkdir()
        (leaf / "real-leaf-boundary.c").write_bytes((cwd / "test/native/real_leaf_boundary.c").read_bytes())
        executable = leaf / producer.LEAF_EXECUTABLE
        executable.write_bytes(b"fixture executable")
        executable.chmod(0o755)
        for name, command in (
            ("compiler-execution.json", [
                "cc",
                str(leaf / "real-leaf-boundary.c"),
                str(Path(env["CODEX_AGENT_REAL_LIBRARY"]).absolute()),
                "-fPIC",
                f"-Wl,-rpath,{Path(env['CODEX_AGENT_REAL_LIBRARY']).absolute().parent}",
            ]),
            ("boundary-execution.json", [str(executable)]),
        ):
            value = {
                "classifier": classifier,
                "command": command,
                "exitCode": 0,
                "runtimeLibraryDirectory": str(Path(env["CODEX_AGENT_REAL_LIBRARY"]).absolute().parent),
                "schemaVersion": 1,
                "stderrBase64": base64.b64encode(b"").decode(),
                "stdoutBase64": base64.b64encode(b"fixture output\x00\xff").decode(),
            }
            (leaf / name).write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        return subprocess.CompletedProcess(command, 0)

    def __enter__(self):
        self.patch.start()
        return self

    def __exit__(self, *args):
        self.patch.stop()
        self.temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
