"""Offline provisioning controls with a mocked Dart process; no SDK evidence."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("dart_dependency_provisioning", ROOT / "tool/provision_dependencies.py")
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)


class DartDependencyProvisioningTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dart-provisioning-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.number = 0
        self.fixture()

    def fixture(self):
        self.number += 1
        self.root = self.base / str(self.number)
        self.checkout = self.root / "repository"
        self.source = self.checkout / "codex-agent-bindings/dart"
        (self.source / "lib").mkdir(parents=True)
        (self.source / "lib/codex_agent.dart").write_bytes(b"original binding source")
        (self.source / "pubspec.yaml").write_bytes(b"name: codex_agent\ndev_dependencies:\n  test: ^1.25.8\n")
        (self.source / "pubspec.lock").write_bytes(b"synthetic fixed lock; actual resolution is mocked\n")
        self.cache = self.root / "pub-cache"
        self.test_package = self.cache / "hosted/pub.dev/test-1.25.8"
        (self.test_package / "bin").mkdir(parents=True)
        (self.test_package / "bin/test.dart").write_bytes(b"original cached test runner")
        self.dart = self.root / "toolchain/dart"
        self.dart.parent.mkdir()
        self.dart.write_bytes(b"supplied installed Dart seam")
        self.output = self.root / "output"
        self.before = self.inventory(self.source)
        self.configuration = {"configVersion": 2, "packages": [
            {"name": "codex_agent", "rootUri": "../", "packageUri": "lib/"},
            {"name": "test", "rootUri": self.test_package.as_uri() + "/", "packageUri": "lib/"}]}
        self.return_code, self.failure = 0, None
        self.calls = []

    @staticmethod
    def inventory(root):
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}

    def process(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.dart), "pub", "get", "--enforce-lockfile", "--offline"], command)
        self.assertEqual(self.output / "resolution", kwargs["cwd"])
        self.assertFalse(kwargs["cwd"].is_relative_to(self.checkout))
        self.assertEqual(str(self.cache), kwargs["env"]["PUB_CACHE"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        self.assertFalse(kwargs["check"])
        self.assertEqual({"pubspec.yaml", "pubspec.lock"}, {path.name for path in kwargs["cwd"].iterdir()})
        for name in ("pubspec.yaml", "pubspec.lock"):
            self.assertEqual((self.source / name).read_bytes(), (kwargs["cwd"] / name).read_bytes())
        self.assertFalse((self.source / ".dart_tool").exists())
        kwargs["stdout"].write(b"raw pub output\x00\xff\n")
        if self.failure == "launch": raise OSError("synthetic launch failure")
        config = kwargs["cwd"] / ".dart_tool/package_config.json"
        config.parent.mkdir()
        self.raw_config = (json.dumps(self.configuration, indent=2) + "\n").encode()
        config.write_bytes(self.raw_config)
        if self.failure == "source": (self.source / "lib/codex_agent.dart").write_bytes(b"changed source")
        if self.failure == "lock": (kwargs["cwd"] / "pubspec.lock").write_bytes(b"lock rewritten")
        if self.failure == "executable": self.dart.write_bytes(b"changed Dart")
        return subprocess.CompletedProcess(command, self.return_code)

    def invoke(self, **changes):
        with patch.multiple(provision.evidence, ROOT=self.source, CHECKOUT=self.checkout), \
                patch.object(provision.subprocess, "run", side_effect=self.process):
            return provision.prepare(**{**{"dart_executable": self.dart, "pub_cache": self.cache,
                                           "output": self.output}, **changes})

    def test_fixed_offline_resolution_preserves_sources_raw_logs_and_exact_binding_root(self):
        result = self.invoke()
        self.assertEqual(self.output / "package_config.json", result)
        self.assertEqual(self.before, self.inventory(self.source))
        self.assertEqual(self.raw_config, (self.output / "resolution/.dart_tool/package_config.json").read_bytes())
        self.assertEqual(b"raw pub output\x00\xff\n", (self.output / "pub.log").read_bytes())
        trace = json.loads((self.output / "execution.json").read_bytes())
        self.assertEqual(self.calls[0], trace["command"])
        self.assertEqual(str(self.output / "resolution"), trace["workingDirectory"])
        self.assertEqual(0, trace["returnCode"])
        self.assertIsNone(trace["launchError"])
        with patch.multiple(provision.evidence, ROOT=self.source, CHECKOUT=self.checkout):
            configured, runner = provision.evidence._resolved_runner(result)
        self.assertEqual(self.test_package / "bin/test.dart", runner)
        roots = {item["name"]: item["rootUri"] for item in configured["packages"]}
        self.assertEqual(self.source.as_uri() + "/", roots["codex_agent"])
        self.assertEqual(self.test_package.as_uri() + "/", roots["test"])
        self.assertFalse((self.source / ".dart_tool").exists())

    def test_process_failure_retains_raw_diagnostics_without_publishing_configuration(self):
        for mode in ("exit", "launch"):
            self.fixture()
            self.return_code = 7
            self.failure = mode
            with self.subTest(mode=mode), self.assertRaises((ValueError, OSError)):
                self.invoke()
            self.assertFalse((self.output / "package_config.json").exists())
            self.assertEqual(self.before, self.inventory(self.source))
            self.assertEqual(b"raw pub output\x00\xff\n", (self.output / "pub.log").read_bytes())
            trace = json.loads((self.output / "execution.json").read_bytes())
            self.assertEqual(None if mode == "launch" else 7, trace["returnCode"])
            self.assertEqual("synthetic launch failure" if mode == "launch" else None, trace["launchError"])

    def test_original_source_lock_and_executable_mutation_prevent_configuration(self):
        for mode in ("source", "lock", "executable"):
            self.fixture()
            self.failure = mode
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "source, executable or exact resolution lock changed"):
                self.invoke()
            self.assertFalse((self.output / "package_config.json").exists())
            self.assertTrue((self.output / "execution.json").is_file())

    def test_wrong_root_missing_runner_duplicate_names_and_cache_escape_reject(self):
        for mode in ("root", "missing-test", "duplicate", "escape", "package-uri", "symlink"):
            self.fixture()
            if mode == "root": self.configuration["packages"][0]["rootUri"] = self.source.as_uri()
            elif mode == "missing-test": self.configuration["packages"] = self.configuration["packages"][:1]
            elif mode == "duplicate": self.configuration["packages"].append(deepcopy(self.configuration["packages"][1]))
            elif mode == "escape":
                self.configuration["packages"][1]["rootUri"] = self.source.as_uri()
            elif mode == "package-uri": self.configuration["packages"][0]["packageUri"] = "other/"
            else:
                link = self.cache / "linked-test"
                link.symlink_to(self.test_package, target_is_directory=True)
                self.configuration["packages"][1]["rootUri"] = link.as_uri()
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.invoke()
            self.assertFalse((self.output / "package_config.json").exists())
            self.assertEqual(self.before, self.inventory(self.source))

    def test_output_cache_and_executable_safety_reject_before_process(self):
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "original"
        sentinel.write_bytes(b"preserved")
        link = self.root / "linked-output"
        link.symlink_to(existing, target_is_directory=True)
        for changes in ({"output": self.checkout / "build/provision"}, {"output": self.root},
                        {"output": self.cache / "output"}, {"output": existing}, {"output": link},
                        {"output": Path("relative")}, {"pub_cache": self.source},
                        {"dart_executable": self.source / "pubspec.yaml"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.invoke(**changes)
        self.assertEqual([], self.calls)
        self.assertEqual(b"preserved", sentinel.read_bytes())
        self.assertEqual(self.before, self.inventory(self.source))

    def test_cli_is_fixed_and_returns_external_config_path(self):
        args = ["--dart-executable", str(self.dart), "--pub-cache", str(self.cache), "--output", str(self.output)]
        with patch.object(provision, "prepare", return_value=self.output / "package_config.json") as prepare, \
                redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(0, provision.main(args))
        prepare.assert_called_once_with(dart_executable=self.dart, pub_cache=self.cache, output=self.output)
        self.assertEqual(str(self.output / "package_config.json") + "\n", stdout.getvalue())
        with patch.object(provision, "prepare") as prepare, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            provision.main([*args, "--command", "caller override"])
        prepare.assert_not_called()


class DartConsumerLockedClosureTest(unittest.TestCase):
    def test_consumer_retains_exact_already_locked_runtime_dependency_chain(self):
        def blocks(path):
            return {name: block for name, block in re.findall(
                r"(?ms)^  ([a-z_]+):\n(.*?)(?=^  [a-z_]+:|^sdks:)", path.read_text())}
        binding, consumer = blocks(ROOT / "pubspec.lock"), blocks(ROOT / "consumer/pubspec.lock")
        self.assertIn("  crypto: ^3.0.7", (ROOT / "pubspec.yaml").read_text())
        self.assertEqual({"codex_agent", "crypto", "typed_data", "collection", "lints"}, set(consumer))
        for name in ("crypto", "typed_data", "collection"):
            self.assertEqual(binding[name].replace('dependency: "direct main"', "dependency: transitive"), consumer[name])
        self.assertIn('      path: ".."', consumer["codex_agent"])


if __name__ == "__main__":
    unittest.main()
