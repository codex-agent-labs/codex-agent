"""Compiler-free orchestration fixtures, not installed/native package acceptance."""

import importlib.util
import ast
from pathlib import Path
import shutil
import subprocess
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


if __name__ == "__main__":
    unittest.main()
