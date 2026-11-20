"""Runner/lifetime fixtures only; no Gradle, toolkit execution or product admission."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products import tooling
from ci.products.inventory import canonical_json_bytes
from ci.products.registry import PHASE_INSTANCE_IDS
from ci.products.selection import phase_inventory_paths


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/actions/run-ci-lane/build-logic-tests.py"
spec = importlib.util.spec_from_file_location("build_logic_tests", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BuildLogicToolingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="build-logic-tooling-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        evidence = self.root / "evidence"
        evidence.mkdir()
        (evidence / "original.jar").write_bytes(b"synthetic original; never executed")
        public_key = self.root / "public.pub"
        public_key.write_bytes(b"synthetic key; signature boundary mocked")
        self.policy = {"evidence": str(evidence), "publicKey": str(public_key),
            "javaExecutable": str(self.root / "jdk/bin/java"), "requiredTrustDomain": "release",
            "keyring": str(self.root / "keyring.json"), "keysDirectory": str(self.root / "keys")}
        self.policy_path = self.root / "policy.json"
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.options = dict(repository_root=self.root, tooling_policy=self.policy_path,
                            policy_revision="a" * 40)
        self.addCleanup(patch.stopall)
        patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}).start()

    def test_new_runner_and_test_have_no_product_input_owners(self):
        paths = (SCRIPT.relative_to(ROOT).as_posix(), Path(__file__).relative_to(ROOT).as_posix())
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_fixed_command_uses_private_jar_last_for_whole_subprocess_and_preserves_exit(self):
        observed = {}

        def execute(command, **kwargs):
            jar = Path(next(value.split("=", 1)[1] for value in command
                            if value.startswith("-DcodexAgent.verifiedTestTooling=")))
            init = Path(command[command.index("--init-script") + 1])
            observed.update(jar=jar, init=init)
            self.assertEqual(b"synthetic original; never executed", jar.read_bytes())
            self.assertNotEqual(jar, Path(self.policy["evidence"]) / "original.jar")
            self.assertEqual(runner._INIT, init.read_text())
            self.assertIn("test.classpath = test.classpath + project.files(jar)", init.read_text())
            self.assertIn("test.systemProperty('codexAgent.releaseToolingJar', jar)", init.read_text())
            self.assertEqual([str(self.root / "gradlew"), "-p", "gradle/build-logic", "test",
                "-Pkotlin.daemon.jvmargs=-Xmx2g", "--configuration-cache",
                "--configuration-cache-problems=fail", "--no-build-cache", "-x", "releaseToolingJar",
                "--init-script", str(init), f"-DcodexAgent.verifiedTestTooling={jar}",
                "--tests", "SdkVerificationTaskGraphTest"], command)
            self.assertEqual({"cwd": self.root, "check": False}, kwargs)
            return subprocess.CompletedProcess(command, 7)

        with patch.object(tooling, "_verify_capture", side_effect=lambda root, *args: root / "original.jar") as signature, \
                patch.object(tooling, "_verify_tooling_policy") as policy, \
                patch.object(runner.subprocess, "run", side_effect=execute):
            self.assertEqual(7, runner.run(**self.options, tests=["SdkVerificationTaskGraphTest"]))
        self.assertEqual((self.root, observed["jar"].parents[1] / "pinned.pub", "release",
                          Path(self.policy["keyring"]), Path(self.policy["keysDirectory"]), None),
                         signature.call_args.args[1:])
        self.assertEqual((observed["jar"], observed["jar"].parent, self.root, "a" * 40), policy.call_args.args)
        self.assertEqual({"use": "full"}, policy.call_args.kwargs)
        self.assertFalse(observed["jar"].exists())
        self.assertFalse(observed["init"].exists())

    def test_real_capture_exit_rejects_mutation_even_after_failed_gradle(self):
        def execute(command, **kwargs):
            jar = Path(next(value.split("=", 1)[1] for value in command
                            if value.startswith("-DcodexAgent.verifiedTestTooling=")))
            jar.write_bytes(b"mutated private executable")
            return subprocess.CompletedProcess(command, 7)

        with patch.object(tooling, "_verify_capture", side_effect=lambda root, *args: root / "original.jar"), \
                patch.object(tooling, "_verify_tooling_policy"), \
                patch.object(runner.subprocess, "run", side_effect=execute), \
                self.assertRaisesRegex(ValueError, "changed during use"):
            runner.run(**self.options)

    def test_launch_failure_still_exits_capture_before_reraising(self):
        with patch.object(tooling, "_verify_capture", side_effect=lambda root, *args: root / "original.jar"), \
                patch.object(tooling, "_verify_tooling_policy"), \
                patch.object(tooling, "regular_file_inventory", wraps=tooling.regular_file_inventory) as inventory, \
                patch.object(runner.subprocess, "run", side_effect=OSError("launch failed")), \
                self.assertRaisesRegex(OSError, "launch failed"):
            runner.run(**self.options)
        self.assertEqual(4, inventory.call_count)

    def test_policy_and_selector_rejections_happen_before_capture(self):
        with patch.object(runner, "verified_tooling_capture") as capture:
            for change in ({"policy_revision": "HEAD"}, {"tests": ["--init-script=evil"]},
                           {"tests": ["SomeTest.method"] + ["*"]}, {"tests": ["build test"]}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    runner.run(**{**self.options, **change})
            with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), self.assertRaisesRegex(ValueError, "local-only"):
                runner.run(**self.options, tests=["SomeTest"])
            for policy in ({**self.policy, "requiredTrustDomain": "development"},
                           {**self.policy, "keyring": None}, {**self.policy, "evidence": "relative"},
                           {key: value for key, value in self.policy.items() if key != "javaExecutable"},
                           {**self.policy, "extra": "unexpected"}):
                self.policy_path.write_bytes(canonical_json_bytes(policy))
                with self.subTest(policy=policy), self.assertRaises(ValueError):
                    runner.run(**self.options)
            capture.assert_not_called()

    def test_cli_rejects_arbitrary_task_passthrough(self):
        with patch.object(runner, "run") as execute, self.assertRaises(SystemExit):
            runner.main(["--repository-root", str(self.root), "--tooling-policy", str(self.policy_path),
                         "--policy-revision", "a" * 40, "releaseToolingJar"])
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
