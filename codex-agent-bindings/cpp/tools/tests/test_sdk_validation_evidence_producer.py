"""Compiler-free orchestration fixtures; no C++ or native acceptance evidence."""

import importlib.util
import io
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "produce_sdk_validation_evidence.py"
SPEC = importlib.util.spec_from_file_location("cpp_evidence_producer", SCRIPT)
producer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(producer)


class ProducerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.checkout = self.root / "repository"
        self.source = self.checkout / "codex-agent-bindings/cpp"
        for name in producer.SOURCE_DIRECTORIES:
            (self.source / name).mkdir(parents=True)
        for name in producer.SOURCE_FILES:
            self.write(self.source / name, "fixture source\n")
        self.program = self.write(self.source / "tests/value_parity_test.cpp", "fixture full program\n")
        self.write(self.source / "native/macos-arm64/libcodex_agent.dylib", "must not copy source native runtime")
        self.api = self.write(self.root / "input/api.txt", "explicit API")
        self.bootstrap = self.write(self.root / "input/bootstrap.json", "explicit bootstrap")
        self.sdk = self.root / "input/sdk"
        self.header = self.write(self.sdk / "include/codex_agent.h", "explicit header")
        self.compatibility = self.write(self.root / "input/sdk-compatibility.json", "explicit compatibility")
        self.library = self.write(self.sdk / "lib/libcodex_agent.dylib", "explicit native")
        self.output = self.root / "outputs/raw"
        self.classifier = "macos-arm64"
        self.calls = []
        self.environments = []
        self.mutation = lambda evidence, build: None
        for field, value in (("ROOT", self.source), ("CHECKOUT", self.checkout)):
            patcher = mock.patch.object(producer, field, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def junit(self, path, names):
        suite = ET.Element("testsuite", tests=str(len(names)), failures="0", skipped="0")
        for name in sorted(names):
            ET.SubElement(suite, "testcase", name=name)
        path.write_bytes(ET.tostring(suite))

    def execute(self, command, *, cwd, env, stdout, stderr, check):
        self.calls.append(command)
        self.environments.append(env.copy())
        self.assertTrue(check)
        self.assertEqual(stderr, subprocess.STDOUT)
        self.assertNotEqual(cwd, self.source)
        self.assertEqual((cwd / "tests/value_parity_test.cpp").read_bytes(), self.program.read_bytes())
        self.assertFalse((cwd / "native").exists())
        evidence = cwd.parent
        self.assertEqual(env["TMPDIR"], str(evidence / "scratch"))
        self.assertEqual(env["TMP"], env["TEMP"])
        stdout.write(b"original tool log\n")
        build = evidence / "build"
        if command[0] == "ctest":
            self.assertEqual(command[command.index("--test-dir") + 1], str(build))
            self.assertEqual(command[command.index("--parallel") + 1], "1")
            self.assertIn("--no-tests=error", command)
            final = "-R" in command
            self.assertEqual(command[command.index("-R" if final else "-E") + 1], f"^{producer.VALUE_TEST}$")
            names = {producer.VALUE_TEST} if final else producer.REQUIRED_TESTS - {producer.VALUE_TEST}
            if not final and self.classifier != "windows-x64":
                names |= {"codex_agent_native_loader_no_test_root_symbol"}
            self.junit(Path(command[command.index("--output-junit") + 1]), names)
            self.write(build / "parity/compiler-evidence.tsv", "compilerEvidenceId\tpublicSymbols\nc-header:a\ta\n")
            self.write(build / "parity/executed-tests.tsv", "executedTestId\tstatus\n" +
                       "".join(f"test-{index:03}\tpassed\n" for index in range(556 if final else 110)))
            for name in producer.AUXILIARIES:
                self.write(build / "parity" / name, f"original {name}\n")
            self.write(build / "Testing/Temporary/LastTest.log", "full value run" if final else "first suite run")
            if final:
                self.mutation(evidence, build)
        elif "--build" in command:
            self.write(build / "tests/codex_agent_cpp_value_test", "fixture compiled bytes, not native proof")
        else:
            private = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("-DCodexAgent_C_SDK_ROOT=")))
            self.assertEqual(evidence / "imported-c-sdk", private)
            self.assertEqual(self.compatibility.read_bytes(), (private / producer.COMPATIBILITY_RESOURCE).read_bytes())
            self.assertEqual(self.header.read_bytes(), (private / "include/codex_agent.h").read_bytes())
            self.assertEqual(self.library.read_bytes(), (private / self.library.relative_to(self.sdk)).read_bytes())
        return subprocess.CompletedProcess(command, 0)

    def produce(self, **kwargs):
        self.classifier = kwargs.get("classifier", "macos-arm64")
        with mock.patch.object(producer.subprocess, "run", side_effect=self.execute):
            producer.produce(self.api, self.bootstrap, self.sdk, self.library,
                             kwargs.pop("output", self.output), classifier=kwargs.pop("classifier", "macos-arm64"),
                             sdk_compatibility=self.compatibility)

    def test_complete_existing_suite_command_and_original_raw_evidence(self):
        self.produce()
        self.assertEqual(len(self.calls), 4)
        configure = self.calls[0]
        for arg in ("-DCODEX_AGENT_CPP_BUILD_TESTS=ON", "-DCODEX_AGENT_CPP_PACKAGE_ONLY=OFF",
                    "-DCODEX_AGENT_CPP_INSTALL_PACKAGE=OFF",
                    "-DCodexAgent_NATIVE_CLASSIFIER=macos-arm64", f"-DCodexAgent_CANONICAL_API_REPORT={self.api}",
                    f"-DCodexAgent_C_ABI_BOOTSTRAP_EVIDENCE={self.bootstrap}"):
            self.assertIn(arg, configure)
        self.assertFalse(any(arg in ("--install", "install", "package", "--preset")
                             for call in self.calls for arg in call))
        self.assertEqual((self.output / "test-program").read_bytes(), self.program.read_bytes())
        self.assertEqual(len((self.output / "executed-tests.tsv").read_text().splitlines()), 557)
        self.assertEqual(len((self.output / "prerequisite-evidence/executed-tests.tsv").read_text().splitlines()), 111)
        self.assertEqual((self.output / "prerequisite-ctest/Temporary/LastTest.log").read_text(), "first suite run")
        for name in producer.AUXILIARIES:
            self.assertEqual((self.output / "build/parity" / name).read_text(), f"original {name}\n")
        self.assertTrue((self.output / "build/tests/codex_agent_cpp_value_test").is_file())
        self.assertFalse((self.source / "build").exists())
        self.assertEqual(self.library.read_text(), "explicit native")
        self.assertEqual(self.compatibility.read_text(), "explicit compatibility")
        self.assertFalse((self.sdk / producer.COMPATIBILITY_RESOURCE).exists())
        expected = {path.relative_to(self.sdk): path.read_bytes() for path in self.sdk.rglob("*") if path.is_file()}
        expected[producer.COMPATIBILITY_RESOURCE] = self.compatibility.read_bytes()
        private = self.output / "imported-c-sdk"
        self.assertEqual(expected, {path.relative_to(private): path.read_bytes()
                                    for path in private.rglob("*") if path.is_file()})

    def test_existing_matching_compatibility_is_retained_without_modifying_originals(self):
        resource = self.write(self.sdk / producer.COMPATIBILITY_RESOURCE, self.compatibility.read_text())
        before = {path.relative_to(self.sdk): path.read_bytes() for path in self.sdk.rglob("*") if path.is_file()}
        self.produce()
        self.assertEqual(before, {path.relative_to(self.sdk): path.read_bytes()
                                  for path in self.sdk.rglob("*") if path.is_file()})
        self.assertEqual(resource.read_bytes(), (self.output / "imported-c-sdk" / producer.COMPATIBILITY_RESOURCE).read_bytes())

    def test_invalid_compatibility_overlay_fails_before_invalidation(self):
        for mutation in ("conflict", "empty", "symbolic", "overlap"):
            with self.subTest(mutation=mutation):
                original = self.compatibility
                original_bytes = original.read_bytes()
                resource = self.sdk / producer.COMPATIBILITY_RESOURCE
                sentinel = self.write(self.output / "preserved", "prior evidence")
                if mutation == "conflict":
                    self.write(resource, "different existing declaration")
                elif mutation == "empty":
                    original.write_bytes(b"")
                elif mutation == "symbolic":
                    original.unlink()
                    original.symlink_to(self.api)
                else:
                    self.compatibility = sentinel
                with self.assertRaises(ValueError):
                    self.produce()
                self.assertEqual("prior evidence", sentinel.read_text())
                if resource.exists():
                    resource.unlink()
                if original.is_symlink():
                    original.unlink()
                original.write_bytes(original_bytes)
                self.compatibility = original
        self.assertEqual([], self.calls)

    def test_overlay_ancestor_files_preserve_prior_evidence_before_invalidation(self):
        sentinel = self.write(self.output / "preserved", "prior evidence")
        for relative in ("share", "share/CodexAgent", "share/CodexAgent/native"):
            with self.subTest(relative=relative):
                ancestor = self.write(self.sdk / relative, "not a directory")
                with mock.patch.object(producer, "_invalidate") as invalidate, self.assertRaises(ValueError):
                    self.produce()
                invalidate.assert_not_called()
                self.assertEqual("prior evidence", sentinel.read_text())
                self.assertEqual("not a directory", ancestor.read_text())
                ancestor.unlink()
        self.assertEqual([], self.calls)

    def test_required_imports_and_source_program_fail_before_invalidation(self):
        for path in (self.api, self.bootstrap, self.library, self.header, self.compatibility, self.program):
            with self.subTest(path=path):
                content = path.read_bytes()
                path.unlink()
                sentinel = self.write(self.output / "preserved", "prior evidence")
                with self.assertRaises(ValueError):
                    self.produce()
                self.assertEqual(sentinel.read_text(), "prior evidence")
                path.write_bytes(content)
        self.assertEqual(self.calls, [])

    def test_classifier_and_exact_cmake_library_mapping_are_required(self):
        self.library = self.write(self.root / "unrelated.dylib", "explicit native")
        with self.assertRaisesRegex(ValueError, "exact CMake-selected"):
            self.produce()
        with self.assertRaisesRegex(ValueError, "exact supported"):
            self.produce(classifier="host")
        self.assertEqual(self.calls, [])

    def test_windows_commands_use_private_imported_dll_directory_without_copying_into_build(self):
        self.library = self.write(self.sdk / "bin/codex_agent.dll", "explicit Windows native")
        imports = [self.write(self.sdk / name, "explicit import library")
                   for name in ("lib/codex_agent.lib", "lib/libcodex_agent.dll.a")]
        before = {path.relative_to(self.sdk): path.read_bytes() for path in self.sdk.rglob("*") if path.is_file()}
        with mock.patch.dict(os.environ, {"PATH": "original-tool-path"}):
            self.produce(classifier="windows-x64")
        self.assertEqual(4, len(self.calls))
        private = Path(next(arg.split("=", 1)[1] for arg in self.calls[0]
                            if arg.startswith("-DCodexAgent_C_SDK_ROOT=")))
        for environment in self.environments:
            self.assertEqual(str(private / "bin") + os.pathsep + "original-tool-path", environment["PATH"])
        self.assertFalse((self.output / "build/tests/codex_agent.dll").exists())
        self.assertEqual(before, {path.relative_to(self.sdk): path.read_bytes()
                                  for path in self.sdk.rglob("*") if path.is_file()})
        for original in [self.library, *imports]:
            self.assertEqual(original.read_bytes(),
                             (self.output / "imported-c-sdk" / original.relative_to(self.sdk)).read_bytes())

    def test_each_existing_loader_case_is_required_without_skipping(self):
        self.assertEqual(39, len(producer.LOADER_TESTS))
        for name in sorted(producer.LOADER_TESTS):
            with self.subTest(name=name):
                def omit(evidence, build):
                    self.junit(evidence / "ctest-suite.xml",
                               (producer.REQUIRED_TESTS - {producer.VALUE_TEST, name}) |
                               {"codex_agent_native_loader_no_test_root_symbol"})
                self.mutation = omit
                with self.assertRaisesRegex(ValueError, "omits an existing capability/native proof"):
                    self.produce()
                self.assertFalse(self.output.exists())

    def test_unix_symbol_hygiene_case_is_required_but_windows_does_not_register_it(self):
        name = "codex_agent_native_loader_no_test_root_symbol"

        def omit(evidence, build):
            self.junit(evidence / "ctest-suite.xml", producer.REQUIRED_TESTS - {producer.VALUE_TEST})

        self.mutation = omit
        with self.assertRaisesRegex(ValueError, "omits an existing capability/native proof"):
            self.produce()
        self.assertFalse(self.output.exists())
        self.mutation = lambda evidence, build: None
        self.library = self.write(self.sdk / "bin/codex_agent.dll", "explicit Windows native")
        for member in ("lib/codex_agent.lib", "lib/libcodex_agent.dll.a"):
            self.write(self.sdk / member, "explicit import library")
        self.produce(classifier="windows-x64")
        self.assertTrue(self.output.is_dir())

    def test_output_scope_and_symbolic_inputs_fail_before_deletion(self):
        for output in (self.root, self.checkout, self.source, self.source / "tests/destroy",
                       self.api.parent, self.sdk / "result", self.checkout / "unowned", Path.home()):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.produce(output=output)
        alias = self.root / "alias"
        alias.symlink_to(self.sdk, target_is_directory=True)
        original = self.library
        self.library = alias / "lib/libcodex_agent.dylib"
        with self.assertRaises(ValueError):
            self.produce()
        self.library = original
        alias.unlink()
        alias.symlink_to(self.root / "outputs", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.produce(output=alias / "raw")
        self.assertEqual(self.calls, [])

    def test_subprocess_failure_removes_only_owned_stale_output(self):
        self.write(self.output / "stale", "stale")
        with mock.patch.object(producer.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "fixture")):
            with self.assertRaises(subprocess.CalledProcessError):
                producer.produce(self.api, self.bootstrap, self.sdk, self.library, self.output,
                                 classifier="macos-arm64", sdk_compatibility=self.compatibility)
        self.assertFalse(self.output.exists())
        self.assertTrue(self.program.is_file())

    def test_every_failed_command_forwards_exact_binary_diagnostics_before_cleanup(self):
        original_program = self.program.read_bytes()
        for position in range(1, 5):
            for raw in (b"failure\xff\x00\r\n", b""):
                with self.subTest(position=position, raw=raw):
                    self.write(self.output / "stale", "old evidence")
                    diagnostics = io.BytesIO()
                    failure = subprocess.CalledProcessError(7, "fixture")
                    observed = []

                    def fail(command, **kwargs):
                        observed.append(command)
                        if len(observed) == position:
                            kwargs["stdout"].write(raw)
                            raise failure
                        return self.execute(command, **kwargs)

                    with mock.patch.object(producer.subprocess, "run", side_effect=fail), \
                            mock.patch.object(producer.sys, "stderr", SimpleNamespace(buffer=diagnostics)), \
                            self.assertRaises(subprocess.CalledProcessError) as caught:
                        producer.produce(self.api, self.bootstrap, self.sdk, self.library, self.output,
                                         classifier="macos-arm64", sdk_compatibility=self.compatibility)
                    self.assertEqual(position, len(observed))
                    self.assertIs(failure, caught.exception)
                    self.assertEqual(raw, diagnostics.getvalue())
                    self.assertFalse(self.output.exists())
                    self.assertEqual(original_program, self.program.read_bytes())
                    self.assertFalse(any(self.output.parent.glob(".cpp-binding-evidence-*")))

    def test_missing_empty_extra_and_symbolic_native_evidence_reject_publication(self):
        def missing(evidence, build):
            (build / "parity" / producer.AUXILIARIES[0]).unlink()
        def empty(evidence, build):
            (build / "parity" / producer.AUXILIARIES[0]).write_bytes(b"")
        def extra(evidence, build):
            self.write(build / "parity/unexpected.tsv", "unexpected")
        def symbolic(evidence, build):
            path = build / "parity" / producer.AUXILIARIES[0]
            path.unlink()
            path.symlink_to(self.api)
        for mutation in (missing, empty, extra, symbolic):
            with self.subTest(mutation=mutation.__name__):
                self.mutation = mutation
                with self.assertRaises(ValueError):
                    self.produce()
                self.assertFalse(self.output.exists())

    def test_incomplete_raw_rows_and_skipped_ctest_fail_closed(self):
        def incomplete(evidence, build):
            self.write(build / "parity/executed-tests.tsv", "executedTestId\tstatus\none\tpassed\n")
        def skipped(evidence, build):
            path = evidence / "ctest-value.xml"
            suite = ET.fromstring(path.read_bytes())
            ET.SubElement(suite.find("testcase"), "skipped")
            path.write_bytes(ET.tostring(suite))
        def missing(evidence, build):
            self.junit(evidence / "ctest-suite.xml", {"unrelated"})
        for mutation in (incomplete, skipped, missing):
            with self.subTest(mutation=mutation.__name__):
                self.mutation = mutation
                with self.assertRaises(ValueError):
                    self.produce()
                self.assertFalse(self.output.exists())

    def test_existing_suite_keeps_compiler_behavior_and_native_dependencies(self):
        cmake = (SCRIPT.parents[1] / "tests/CMakeLists.txt").read_text()
        self.assertIn("if(NOT DEFINED CODEX_AGENT_CPP_INSTALL_PACKAGE OR CODEX_AGENT_CPP_INSTALL_PACKAGE)", cmake)
        self.assertIn("NAME codex_agent_cpp_installed_package_tamper", cmake)
        names = set(re.findall(r"\bNAME\s+(codex_agent_\w+)\s", cmake))
        for modes in re.findall(r"foreach\(mode\s+([^)]*)\)", cmake):
            names.update("codex_agent_native_loader_" + mode.replace("-", "_") for mode in modes.split())
        for aliases in re.findall(r"foreach\(alias\s+([^)]*)\)", cmake):
            names.update(f"codex_agent_native_loader_abi_{alias}_alias" for alias in aliases.split())
        self.assertEqual(producer.REQUIRED_TESTS,
                         names - {"codex_agent_cpp_installed_package_tamper",
                                  "codex_agent_native_loader_no_test_root_symbol"})
        self.assertNotIn("if(NOT WIN32)", cmake)
        full = (SCRIPT.parents[1] / "tests/value_parity_test.cpp").read_text()
        self.assertIn('require(all_claims.size() == 556', full)
        self.assertIn('"executed evidence is incomplete"', full)
        self.assertIn('"compiler evidence is incomplete"', full)

    def test_windows_import_mock_and_release_assertion_wiring_is_scoped(self):
        # Source contract only; real generated links and host execution remain separate gates.
        root = SCRIPT.parents[1]
        source = (root / "CMakeLists.txt").read_text()
        installed = (root / "cmake/CodexAgentConfig.cmake.in").read_text()
        for text, target in ((source, "CodexAgentC"), (installed, "CodexAgent::C")):
            self.assertIn(f"if(WIN32)\n", text)
            self.assertIn(f"add_library({target} SHARED IMPORTED)", text)
            self.assertIn(f"add_library({target} UNKNOWN IMPORTED)", text)
            self.assertIn(f"set_property(TARGET {target} PROPERTY IMPORTED_IMPLIB", text)
        self.assertIn('"${CODEX_AGENT_C_SDK_MSVC_IMPORT}"', source)
        self.assertIn('"${CODEX_AGENT_C_SDK_GNU_IMPORT}"', source)
        tests = (root / "tests/CMakeLists.txt").read_text()
        consumers = re.search(r"foreach\(consumer\s+([^)]*)\)", tests).group(1).split()
        self.assertEqual({"codex_agent_cpp_test", *(f"codex_agent_cpp_{family}_test"
                                                  for family in producer.FAMILIES)}, set(consumers))
        self.assertIn("target_compile_definitions(${consumer} PRIVATE CODEX_AGENT_BUILD)", tests)
        self.assertIn("target_compile_options(codex_agent_cpp_test PRIVATE /W4 /WX /UNDEBUG)", tests)
        self.assertIn("target_compile_options(codex_agent_cpp_test PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)", tests)
        wrapper = (root / "tests/wrapper_test.cpp").read_text()
        self.assertIn("assert(host_terminal)", wrapper)
        self.assertIn("assert(host_events == 3)", wrapper)

    def test_loader_symlink_setup_must_finish_before_rejection_can_pass(self):
        # Compiler-free control-flow regression; actual filesystem/loader proof
        # remains mandatory on every host, including Windows privilege failures.
        source = (SCRIPT.parents[1] / "tests/native_loader_test.cpp").read_text()
        self.assertIn("bool hostile_link_prepared = false;", source)
        assignments = re.findall(
            r"std::filesystem::create_(?:directory_)?symlink\([^;]+\);\s*"
            r"hostile_link_prepared = true;\s*return resolved\(", source,
        )
        self.assertEqual(4, len(assignments))
        self.assertEqual(4, source.count("hostile_link_prepared = true;"))
        main = source[source.index("int main("):]
        for mode in ("parent-symlink-library", "final-symlink-library",
                     "parent-symlink-compatibility", "final-symlink-compatibility"):
            self.assertIn(f'mode == "{mode}"', main)
        self.assertIn("hostile_link_prepared);", main)
        failure = main[main.index("} catch (const std::exception& error) {"):]
        self.assertRegex(failure, r"if \(symlink_mode && !hostile_link_prepared\)\s*\{[^}]+return 1;")
        self.assertLess(failure.index("if (symlink_mode"), failure.index("return 0;"))


if __name__ == "__main__":
    unittest.main()
