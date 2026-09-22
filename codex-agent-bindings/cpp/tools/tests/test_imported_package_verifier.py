"""Compiler-free orchestration fixtures, not installed/native package acceptance."""

import importlib.util
import ast
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "verify_imported_package.py"
SPEC = importlib.util.spec_from_file_location("cpp_imported_package_verifier", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


class ImportedPackageVerifierTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.package = self.root / "original"
        self.library = "lib/libcodex_agent.dylib"
        self.members = ("include/codex_agent.h", self.library,
                        "share/CodexAgent/native/sdk-compatibility.json",
                        "share/CodexAgent/loader/native_loader.cpp",
                        "lib/cmake/CodexAgent/CodexAgentConfig.cmake")
        for name in self.members:
            path = self.package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"original imported fixture: " + name.encode())
        self.output = self.root / "output"
        self.calls = []

    def snapshot(self, root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def configure_fixture(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual("fixture-cmake", command[0])
        self.assertEqual({"-S", "-B"}, {arg for arg in command if arg.startswith("-") and not arg.startswith("-D")})
        self.assertFalse(any(arg in ("--install", "--build", "--preset", "install", "package") for arg in command))
        source = Path(command[command.index("-S") + 1])
        build = Path(command[command.index("-B") + 1])
        prefix = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("-DCodexAgent_DIR="))).parents[2]
        self.assertNotEqual(self.package, prefix)
        self.assertEqual("find_package(CodexAgent REQUIRED CONFIG NO_DEFAULT_PATH)",
                         source.joinpath("CMakeLists.txt").read_text().splitlines()[-1])
        actual, original = self.snapshot(prefix), self.snapshot(self.package)
        name = build.name.removeprefix("build-")
        if name == "baseline":
            self.assertEqual(original, actual)
        elif name.startswith("tampered-"):
            changed = self.members[int(name.removeprefix("tampered-"))]
            self.assertEqual({key: value + (b"\0" if key == changed else b"")
                              for key, value in original.items()}, actual)
        else:
            removed = self.members[2 if name == "missing-sidecar" else 3]
            self.assertEqual({key: value for key, value in original.items() if key != removed}, actual)
        build.mkdir()
        (build / "CMakeCache.txt").write_text("raw fixture configuration output")
        return subprocess.CompletedProcess(command, 0 if name == "baseline" else 1,
                                           stdout=f"original configure fixture {name}\n")

    def invoke(self, **kwargs):
        verifier.verify_imported_package(kwargs.pop("package", self.package), kwargs.pop("output", self.output),
                                          cmake="fixture-cmake", libdir=kwargs.pop("libdir", "lib"),
                                          library=kwargs.pop("library", self.library))

    def test_original_seven_cases_no_install_and_all_raw_artifacts_retained(self):
        original = self.snapshot(self.package)
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        self.assertEqual(7, len(self.calls))
        self.assertEqual(original, self.snapshot(self.package))
        self.assertEqual(original, self.snapshot(self.output / "baseline"))
        self.assertEqual(verifier.VERIFIER.read_bytes(), (self.output / "test-program.py").read_bytes())
        names = ("baseline", *(f"tampered-{index}" for index in range(4)), "missing-sidecar", "missing-loader")
        contents = (self.output / "package-tamper-results.tsv").read_bytes()
        self.assertNotIn(b"\r", contents)
        self.assertTrue(contents.endswith(b"\n"))
        rows = contents.decode("utf-8").splitlines()
        self.assertEqual("caseId\texpectedExit\tactualExitCode\tstatus\tlogPath", rows[0])
        self.assertEqual([
            f"{name}\t{'zero' if name == 'baseline' else 'nonzero'}\t"
            f"{0 if name == 'baseline' else 1}\tpassed\tconfigure-{name}.log"
            for name in sorted(names)
        ], rows[1:])
        for name in names:
            self.assertIn(f"original configure fixture {name}",
                          (self.output / f"configure-{name}.log").read_text())
            self.assertIn(f"\nreturncode: {0 if name == 'baseline' else 1}\n",
                          (self.output / f"configure-{name}.log").read_text())
            self.assertTrue((self.output / f"build-{name}/CMakeCache.txt").is_file())

    def test_case_inventory_records_actual_nonzero_exit_without_inventing_a_fixed_code(self):
        def observed(command, **kwargs):
            result = self.configure_fixture(command, **kwargs)
            if Path(command[command.index("-B") + 1]).name == "build-tampered-2":
                result.returncode = 7
            return result

        with patch.object(subprocess, "run", side_effect=observed):
            self.invoke()
        self.assertIn("tampered-2\tnonzero\t7\tpassed\tconfigure-tampered-2.log\n",
                      (self.output / "package-tamper-results.tsv").read_text())
        self.assertIn("\nreturncode: 7\n", (self.output / "configure-tampered-2.log").read_text())

    def test_retained_evidence_verifies_after_relocation_without_execution_or_mutation(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        relocated = self.root / "relocated"
        shutil.copytree(self.output, relocated)
        original = self.snapshot(relocated)
        with patch.object(subprocess, "run") as run, patch.object(verifier.runpy, "run_path") as execute:
            verifier.verify_imported_package_evidence(relocated, verifier.VERIFIER.read_bytes())
        run.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(original, self.snapshot(relocated))

    def test_corrupted_program_copy_is_rejected_before_execution_or_publication(self):
        original_program = verifier.VERIFIER.read_bytes()
        original_package = self.snapshot(self.package)
        copyfile = shutil.copyfile

        def corrupt_program(source, destination, **kwargs):
            result = copyfile(source, destination, **kwargs)
            if Path(destination).name == "test-program.py":
                Path(destination).write_bytes(original_program + b"\n# corrupted copy\n")
            return result

        with patch.object(verifier.shutil, "copyfile", side_effect=corrupt_program), \
                patch.object(verifier.runpy, "run_path") as execute, \
                patch.object(subprocess, "run") as run, \
                self.assertRaisesRegex(ValueError, "Copied C\\+\\+ test program"):
            self.invoke()
        execute.assert_not_called()
        run.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertFalse(any(path.name.startswith(".cpp-imported-package-") for path in self.root.iterdir()))
        self.assertEqual(original_program, verifier.VERIFIER.read_bytes())
        self.assertEqual(original_package, self.snapshot(self.package))

    def test_corrupted_package_copy_is_rejected_before_any_configure(self):
        original = self.snapshot(self.package)
        copytree = shutil.copytree

        def corrupt_copy(source, destination, *args, **kwargs):
            result = copytree(source, destination, *args, **kwargs)
            if Path(source) == self.package:
                Path(destination, self.library).write_bytes(b"unrelated copied library")
            return result

        with patch.object(verifier.shutil, "copytree", side_effect=corrupt_copy), \
                patch.object(subprocess, "run") as run, \
                self.assertRaisesRegex(ValueError, "Copied C\\+\\+ package"):
            self.invoke()
        run.assert_not_called()
        self.assertEqual(original, self.snapshot(self.package))
        self.assertFalse(self.output.exists())

    def test_empty_package_files_are_preserved_and_compared(self):
        empty = self.package / "share/empty-marker"
        empty.write_bytes(b"")
        original = verifier._package_inventory(self.package)
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        self.assertEqual(b"", (self.output / "baseline/share/empty-marker").read_bytes())
        self.assertEqual(original, verifier._package_inventory(self.output / "baseline"))
        empty.write_bytes(b"no longer empty")
        self.assertNotEqual(original, verifier._package_inventory(self.package))

    def test_inventory_stays_on_opened_directory_when_path_is_replaced(self):
        expected = verifier._package_inventory(self.package)
        alternate = self.root / "alternate"
        alternate.mkdir()
        (alternate / "unrelated").write_bytes(b"not the imported package")
        original = self.root / "held-original"
        inventory = verifier._directory_inventory

        def replace_after_open(descriptor, **kwargs):
            self.package.rename(original)
            self.package.symlink_to(alternate, target_is_directory=True)
            try:
                return inventory(descriptor, **kwargs)
            finally:
                self.package.unlink()
                original.rename(self.package)

        with patch.object(verifier, "_directory_inventory", side_effect=replace_after_open):
            self.assertEqual(expected, verifier._package_inventory(self.package))

    def test_package_source_and_baseline_mutations_after_configure_publish_nothing(self):
        original = self.snapshot(self.package)
        program = self.root / "original-test-program.py"
        source = verifier.VERIFIER.read_bytes()
        for kind in ("package", "source", "baseline"):
            self.calls.clear()
            program.write_bytes(source)
            for name, contents in original.items():
                (self.package / name).write_bytes(contents)

            def configure(command, **kwargs):
                result = self.configure_fixture(command, **kwargs)
                if len(self.calls) == 7:
                    build = Path(command[command.index("-B") + 1])
                    path = {"package": self.package / self.library, "source": program,
                            "baseline": build.parent / "baseline" / self.library}[kind]
                    with path.open("ab") as stream:
                        stream.write(b"changed after configuration")
                return result

            with self.subTest(kind=kind), patch.object(verifier, "VERIFIER", program), \
                    patch.object(subprocess, "run", side_effect=configure), \
                    self.assertRaisesRegex(ValueError, "changed during verification"):
                self.invoke()
            self.assertEqual(7, len(self.calls))
            self.assertFalse(self.output.exists())
            self.assertFalse(any(path.name.startswith(".cpp-imported-package-") for path in self.root.iterdir()))

    def test_failed_configure_still_checks_original_inputs(self):
        def failed(command, **kwargs):
            (self.package / self.library).write_bytes(b"changed during failed configure")
            raise RuntimeError("configure process failed")

        with patch.object(subprocess, "run", side_effect=failed), \
                self.assertRaisesRegex(ValueError, "Original C\\+\\+ package"):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_publication_time_original_mutation_preserves_failed_diagnostics_or_replacement(self):
        original = (self.package / self.library).read_bytes()
        rename = Path.rename
        for replace in (False, True):
            self.calls.clear()
            (self.package / self.library).write_bytes(original)

            def publish(path, target):
                result = rename(path, target)
                if Path(target) == self.output:
                    if replace:
                        rename(self.output, self.root / "original-publication")
                        shutil.copytree(self.root / "original-publication", self.output)
                        (self.output / "independent-marker").write_bytes(b"caller replacement")
                    (self.package / self.library).write_bytes(b"changed at publication")
                return result

            with self.subTest(replace=replace), patch.object(Path, "rename", publish), \
                    patch.object(subprocess, "run", side_effect=self.configure_fixture), \
                    self.assertRaisesRegex(ValueError, "Original C\\+\\+ package"):
                self.invoke()
            if replace:
                self.assertEqual(b"caller replacement", (self.output / "independent-marker").read_bytes())
            else:
                self.assertTrue(self.output.exists())  # Failed raw diagnostics, not accepted evidence.

    def test_final_input_check_cannot_accept_or_delete_late_replacement(self):
        inventory = verifier._package_inventory
        original = self.snapshot(self.package)
        for kind in ("identical", "empty", "changed-log"):
            self.calls.clear()
            output_checked = replaced = False

            def replace_during_final_input_check(path):
                nonlocal output_checked, replaced
                if Path(path) == self.output:
                    output_checked = True
                if Path(path) == self.package and output_checked and not replaced:
                    if kind == "changed-log":
                        (self.output / "configure-baseline.log").write_bytes(b"late log mutation")
                    else:
                        moved = self.root / ("owned-" + kind)
                        self.output.rename(moved)
                        if kind == "identical":
                            shutil.copytree(moved, self.output)
                        else:
                            self.output.mkdir()
                    replaced = True
                return inventory(path)

            with self.subTest(kind=kind), \
                    patch.object(verifier, "_package_inventory", side_effect=replace_during_final_input_check), \
                    patch.object(subprocess, "run", side_effect=self.configure_fixture), \
                    self.assertRaisesRegex(ValueError, "after final input check"):
                self.invoke()
            self.assertTrue(replaced)
            self.assertEqual(original, self.snapshot(self.package))
            self.assertTrue(self.output.is_dir())
            if kind == "empty":
                self.assertEqual([], list(self.output.iterdir()))
            elif kind == "changed-log":
                self.assertEqual(b"late log mutation", (self.output / "configure-baseline.log").read_bytes())
            else:
                self.assertEqual(self.snapshot(self.root / "owned-identical"), self.snapshot(self.output))

    def test_publication_checks_entire_evidence_and_identity(self):
        rename = Path.rename
        for replacement in (False, True):
            self.calls.clear()

            def publish(path, target):
                result = rename(path, target)
                if Path(target) == self.output:
                    if replacement:
                        rename(self.output, self.root / "unchanged-owned-publication")
                        shutil.copytree(self.root / "unchanged-owned-publication", self.output)
                    else:
                        (self.output / "configure-baseline.log").write_bytes(b"changed log")
                return result

            with self.subTest(replacement=replacement), patch.object(Path, "rename", publish), \
                    patch.object(subprocess, "run", side_effect=self.configure_fixture), \
                    self.assertRaisesRegex(ValueError, "evidence changed during publication"):
                self.invoke()
            self.assertTrue(self.output.is_dir())

    def test_direct_and_packaged_read_only_cli_resolve_existing_inventory_helper(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        before = self.snapshot(self.output)
        extracted = self.root / "packaged"
        script = extracted / "codex-agent-bindings/cpp/tools/verify_imported_package.py"
        script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, script)
        products = extracted / "ci/products"
        products.mkdir(parents=True)
        (extracted / "ci/__init__.py").write_bytes(b"")
        (products / "__init__.py").write_bytes(b"")
        shutil.copyfile(verifier.CHECKOUT / "ci/products/inventory.py", products / "inventory.py")
        arguments = ["verify-evidence", "--evidence", str(self.output),
                     "--expected-test-program", str(verifier.VERIFIER)]
        # Mirrors the isolated packaged bootstrap; only the structural reader
        # runs, never CMake, a compiler, source packaging, or receipt admission.
        bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); runpy.run_path(sys.argv.pop(1),run_name='__main__')"
        for command in ([sys.executable, "-B", str(SCRIPT), *arguments],
                        [sys.executable, "-I", "-S", "-B", "-c", bootstrap,
                         str(extracted), str(script), *arguments]):
            with self.subTest(command=command):
                result = subprocess.run(command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(0, result.returncode, result.stderr.decode())
        self.assertEqual(before, self.snapshot(self.output))

    def test_invalid_original_program_preserves_prior_output_before_capture(self):
        empty_program = self.root / "empty-program.py"
        empty_program.write_bytes(b"")
        self.output.mkdir()
        (self.output / "sentinel").write_bytes(b"previous evidence")
        with patch.object(verifier, "VERIFIER", empty_program), \
                patch.object(verifier.shutil, "rmtree") as remove, \
                patch.object(verifier.runpy, "run_path") as execute, self.assertRaises(ValueError):
            self.invoke()
        remove.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(b"previous evidence", (self.output / "sentinel").read_bytes())

    def test_retained_evidence_rejects_changed_program_and_noncanonical_case_results(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        expected_program = verifier.VERIFIER.read_bytes()
        program = self.output / "test-program.py"
        program.write_bytes(expected_program + b"\n# changed\n")
        with self.assertRaisesRegex(ValueError, "original source"):
            verifier.verify_imported_package_evidence(self.output, expected_program)
        program.write_bytes(expected_program)
        with self.assertRaisesRegex(ValueError, "original source"):
            verifier.verify_imported_package_evidence(self.output, b"other original program")
        results = self.output / "package-tamper-results.tsv"
        original = results.read_bytes()
        rows = original.splitlines(keepends=True)
        mutations = [original[:-1], original.replace(b"\n", b"\r\n"), original.replace(b"\n", b"\v", 1),
                     b"".join(rows[:-1]),
                     original + rows[-1], b"".join([rows[0], rows[2], rows[1], *rows[3:]]),
                     original.replace(b"caseId", b"unknown"), original.replace(b"passed", b"skipped", 1),
                     original.replace(b"baseline\tzero", b"baseline\tnonzero"),
                     original.replace(b"configure-baseline.log", b"../configure-baseline.log")]
        mutations += [original.replace(b"\t1\tpassed", b"\t" + value + b"\tpassed", 1)
                      for value in (b"01", b"+1", b"1.0", b" 1", b"0")]
        for content in mutations:
            with self.subTest(content=content), patch.object(subprocess, "run") as run:
                results.write_bytes(content)
                before = self.snapshot(self.output)
                with self.assertRaises(ValueError):
                    verifier.verify_imported_package_evidence(self.output, expected_program)
                run.assert_not_called()
                self.assertEqual(before, self.snapshot(self.output))
        results.write_bytes(original)

    def test_retained_evidence_rejects_missing_extra_and_crosspaired_configure_logs(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        expected_program = verifier.VERIFIER.read_bytes()
        log = self.output / "configure-tampered-2.log"
        original = log.read_bytes()
        log.unlink()
        with self.assertRaisesRegex(ValueError, "inventory"):
            verifier.verify_imported_package_evidence(self.output, expected_program)
        log.write_bytes(original)
        extra = self.output / "configure-extra.log"
        extra.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "inventory"):
            verifier.verify_imported_package_evidence(self.output, expected_program)
        extra.unlink()
        lines = original.decode().splitlines(keepends=True)
        command = ast.literal_eval(lines[0].removeprefix("command: ").strip())
        crosspaired = command.copy()
        crosspaired[4] = crosspaired[4].replace("build-tampered-2", "build-tampered-1")
        wrong_prefix = command.copy()
        wrong_prefix[5] = wrong_prefix[5].replace("/tampered-2/", "/tampered-1/")
        install = [command[0], "--install", command[4]]
        mutations = [original.replace(b"returncode: 1", b"returncode: 0"),
                     b"command: __import__('os').system('forbidden')\n" + b"".join(original.splitlines(keepends=True)[1:])]
        mutations += [(f"command: {args!r}\n" + "".join(lines[1:])).encode()
                      for args in (crosspaired, wrong_prefix, install)]
        for contents in mutations:
            with self.subTest(contents=contents), patch.object(subprocess, "run") as run:
                log.write_bytes(contents)
                before = self.snapshot(self.output)
                with self.assertRaises(ValueError):
                    verifier.verify_imported_package_evidence(self.output, expected_program)
                run.assert_not_called()
                self.assertEqual(before, self.snapshot(self.output))
        log.write_bytes(original)
        shutil.rmtree(self.output / "build-tampered-2")
        with self.assertRaises(ValueError):
            verifier.verify_imported_package_evidence(self.output, expected_program)

    def test_missing_each_required_member_preserves_prior_output_without_cmake_or_deletion(self):
        self.output.mkdir()
        sentinel = self.output / "previous-proof"
        sentinel.write_bytes(b"original prior evidence")
        for name in self.members:
            with self.subTest(name=name):
                path = self.package / name
                content = path.read_bytes()
                path.unlink()
                with patch.object(subprocess, "run") as run, patch.object(verifier.shutil, "rmtree") as remove, \
                        self.assertRaises(ValueError):
                    self.invoke()
                run.assert_not_called()
                remove.assert_not_called()
                self.assertEqual(b"original prior evidence", sentinel.read_bytes())
                path.write_bytes(content)

    def test_unsafe_output_and_member_paths_and_symbolic_package_are_rejected(self):
        with patch.object(subprocess, "run") as run:
            for output in (self.root, self.package, self.package / "child", verifier.ROOT,
                           verifier.ROOT / "tests/erase", verifier.CHECKOUT, Path.home()):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    self.invoke(output=output)
            for path in ("../escape", "/absolute", "lib/../escape", "lib\\escape", "lib//file", ".", "lib\nfile",
                         "C:/outside/runtime.dll", "C:runtime.dll", "lib/runtime.dll:stream"):
                for option in ("libdir", "library"):
                    with self.subTest(path=path, option=option), self.assertRaises(ValueError):
                        self.invoke(**{option: path})
            alias = self.root / "alias"
            alias.symlink_to(self.package, target_is_directory=True)
            with self.assertRaises(ValueError):
                self.invoke(package=alias)
            with self.assertRaises(ValueError):
                self.invoke(output=alias / "proof")
            (self.package / "untrusted-link").symlink_to(self.root / "outside")
            with self.assertRaises(ValueError):
                self.invoke()
        run.assert_not_called()

    def test_wrong_baseline_or_unrejected_tamper_removes_stale_output_and_private_workspace(self):
        for reject_baseline in (True, False):
            with self.subTest(reject_baseline=reject_baseline):
                self.output.mkdir()
                (self.output / "stale").write_bytes(b"stale")
                def incorrect(command, **kwargs):
                    result = self.configure_fixture(command, **kwargs)
                    result.returncode = 1 if reject_baseline else 0
                    return result
                with patch.object(subprocess, "run", side_effect=incorrect), self.assertRaises(SystemExit):
                    self.invoke()
                self.assertFalse(self.output.exists())
                self.assertFalse(any(path.name.startswith(".cpp-imported-package-") for path in self.root.iterdir()))
        self.assertEqual(set(self.members), set(self.snapshot(self.package)))

    def test_explicit_arguments_are_required(self):
        args = ["--package-root", str(self.package), "--output", str(self.output), "--cmake", "fixture-cmake",
                "--libdir", "lib", "--library", self.library]
        self.assertEqual(self.package, verifier.parse_args(args).package_root)
        for index in range(0, len(args), 2):
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                verifier.parse_args(args[:index] + args[index + 2:])

    def test_read_only_cli_uses_explicit_original_source_without_execution_or_output_mutation(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        arguments = ["verify-evidence", "--evidence", str(self.output),
                     "--expected-test-program", str(verifier.VERIFIER)]
        before = self.snapshot(self.root)
        with patch.object(verifier, "verify_imported_package") as produce, \
                patch.object(subprocess, "run") as run, \
                patch.object(verifier.runpy, "run_path") as execute:
            verifier.main(arguments)
        produce.assert_not_called()
        run.assert_not_called()
        execute.assert_not_called()
        self.assertEqual(before, self.snapshot(self.root))
        for incomplete in (arguments[:1], arguments[:1] + arguments[3:], arguments[:3]):
            with patch("sys.stderr"), self.assertRaises(SystemExit):
                verifier.main(incomplete)

    def test_read_only_cli_rejects_missing_symbolic_changed_original_and_mutated_evidence(self):
        with patch.object(subprocess, "run", side_effect=self.configure_fixture):
            self.invoke()
        changed = self.root / "changed-program.py"
        changed.write_bytes(verifier.VERIFIER.read_bytes() + b"\n# another original\n")
        symbolic = self.root / "symbolic-program.py"
        symbolic.symlink_to(verifier.VERIFIER)
        with patch.object(subprocess, "run") as run, patch.object(verifier.runpy, "run_path") as execute:
            for expected in (self.root / "missing", self.root, changed, symbolic):
                with self.subTest(expected=expected), self.assertRaises(ValueError):
                    verifier.main(["verify-evidence", "--evidence", str(self.output),
                                   "--expected-test-program", str(expected)])
            result = self.output / "package-tamper-results.tsv"
            result.write_bytes(result.read_bytes().replace(b"passed", b"skipped", 1))
            before = self.snapshot(self.root)
            with self.assertRaises(ValueError):
                verifier.main(["verify-evidence", "--evidence", str(self.output),
                               "--expected-test-program", str(verifier.VERIFIER)])
            self.assertEqual(before, self.snapshot(self.root))
        run.assert_not_called()
        execute.assert_not_called()

    def test_legacy_execution_cli_dispatch_is_unchanged(self):
        with patch.object(verifier, "verify_imported_package") as produce:
            verifier.main(["--package-root", str(self.package), "--output", str(self.output),
                           "--cmake", "fixture-cmake", "--libdir", "lib", "--library", self.library])
        produce.assert_called_once_with(self.package, self.output, cmake="fixture-cmake",
                                        libdir="lib", library=self.library)


if __name__ == "__main__":
    unittest.main()
