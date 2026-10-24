"""Execute the action wrapper with a mocked existing policy CLI; no Git or tools."""

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class ApplePolicyActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-policy-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "caller checkout"
        self.repository.mkdir()
        self.original = self.repository / "source.txt"
        self.original.write_bytes(b"original checkout bytes\x00\xff")
        self.scratch = self.root / "runner temp"
        self.scratch.mkdir()
        self.plan, self.tooling = self.root / "original plan.json", self.root / "caller tooling.json"
        self.plan.write_bytes(b"original plan bytes\n")
        self.tooling.write_bytes(b"caller authenticated policy boundary\n")
        self.output = self.root / "github output"
        self.environment = {"GITHUB_WORKSPACE": str(self.repository), "RUNNER_TEMP": str(self.scratch),
            "PLAN_PATH": str(self.plan), "TOOLING_POLICY": str(self.tooling),
            "GITHUB_OUTPUT": str(self.output), "GITHUB_TOKEN": "caller-observation-token"}
        self.action = (ROOT / ".github/actions/prepare-sdk-apple-policy/action.yml").read_text()

    def execute(self):
        source = textwrap.dedent(self.action.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        with patch.dict(os.environ, self.environment, clear=True):
            exec(compile(source, "apple-policy-action", "exec"), {})

    def child(self, argv, **kwargs):
        self.assertEqual([sys.executable, "-B", "-m", "ci.sdk_apple_policy"], argv[:4])
        fields = dict(zip(argv[4::2], argv[5::2]))
        destination = Path(fields.pop("--destination"))
        self.assertEqual({"--plan": str(self.plan), "--tooling-policy": str(self.tooling),
                          "--repository-root": str(self.repository), "--github-output": str(self.output)}, fields)
        self.assertTrue(destination.is_relative_to(self.scratch))
        self.assertFalse(destination.is_relative_to(self.repository))
        self.assertFalse(destination.exists())
        self.assertEqual("policy", destination.name)
        self.assertTrue(destination.parent.is_dir())
        self.assertEqual(destination, destination.resolve())
        self.assertEqual(self.repository, kwargs["cwd"])
        self.assertIs(os.environ, kwargs["env"])
        self.assertEqual("caller-observation-token", kwargs["env"]["GITHUB_TOKEN"])
        self.assertEqual({"cwd", "env", "check"}, set(kwargs))
        self.assertTrue(kwargs["check"])
        # Model the existing CLI's success output, not policy construction/authentication.
        destination.mkdir()
        policy_path = destination / "apple-validation-policy.json"
        policy_path.write_bytes(b"mocked policy CLI output\n")
        self.output.write_text("policy_path=" + str(policy_path) + "\n")
        self.destination = destination
        return subprocess.CompletedProcess(argv, 0)

    def test_exact_cli_with_spaces_external_fresh_output_and_inherited_environment(self):
        with patch("subprocess.run", side_effect=self.child) as child:
            self.execute()
        child.assert_called_once()
        self.assertEqual("policy_path=" + str(self.destination / "apple-validation-policy.json") + "\n", self.output.read_text())
        self.assertEqual({"source.txt"}, {path.name for path in self.repository.iterdir()})
        self.assertEqual(b"original checkout bytes\x00\xff", self.original.read_bytes())
        self.assertEqual(b"original plan bytes\n", self.plan.read_bytes())
        self.assertEqual(b"caller authenticated policy boundary\n", self.tooling.read_bytes())

    def test_resolved_runner_temp_alias_still_uses_external_real_path(self):
        alias = self.root / "scratch alias"
        alias.symlink_to(self.scratch, target_is_directory=True)
        self.environment["RUNNER_TEMP"] = str(alias)
        with patch("subprocess.run", side_effect=self.child):
            self.execute()
        self.assertTrue(self.destination.is_relative_to(self.scratch))

    def test_invalid_paths_reject_before_allocation_and_child(self):
        original = dict(self.environment)
        alias = self.root / "plan alias"
        alias.symlink_to(self.plan)
        checkout_alias = self.root / "checkout alias"
        checkout_alias.symlink_to(self.repository, target_is_directory=True)
        changes = [{"PLAN_PATH": "relative"}, {"TOOLING_POLICY": str(alias)},
                   {"RUNNER_TEMP": "relative"}, {"RUNNER_TEMP": str(self.repository)},
                   {"RUNNER_TEMP": str(checkout_alias)}, {"RUNNER_TEMP": str(self.root)},
                   {"RUNNER_TEMP": str(self.root / "missing")}, {"PLAN_PATH": str(self.root / "missing")},
                   {"TOOLING_POLICY": str(self.repository)}, {"PLAN_PATH": "/invalid\npath"}]
        for values in changes:
            self.environment = {**original, **values}
            with self.subTest(values=values), patch("tempfile.mkdtemp") as allocate, \
                    patch("subprocess.run") as child, self.assertRaises((OSError, ValueError)):
                self.execute()
            allocate.assert_not_called()
            child.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_secret_even_empty_rejects_before_reads_or_allocation(self):
        for secret in ("", "opaque-fixture"):
            self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = secret
            with self.subTest(empty=not secret), patch("tempfile.mkdtemp") as allocate, \
                    patch("ci.products.inventory.read_regular_file_bytes") as read, \
                    patch("subprocess.run") as child, self.assertRaises(ValueError):
                self.execute()
            allocate.assert_not_called()
            child.assert_not_called()
            read.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_child_failure_does_not_publish_output_or_mutate_checkout(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, ["mocked-cli"])), \
                self.assertRaises(subprocess.CalledProcessError):
            self.execute()
        self.assertFalse(self.output.exists())
        self.assertEqual({"source.txt"}, {path.name for path in self.repository.iterdir()})

    def test_only_local_plan_tooling_inputs_and_cli_owned_output(self):
        inputs = self.action.split("inputs:\n", 1)[1].split("outputs:\n", 1)[0]
        self.assertEqual({"plan-path", "tooling-policy"}, set(re.findall(r"^  ([a-z0-9-]+):$", inputs, re.MULTILINE)))
        self.assertIn("value: ${{ steps.policy.outputs.policy_path }}", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "download-artifact", "upload-artifact", "setup-kmp",
                          "setup-java", "java -jar", "gradlew", "--token", "--public-key", "--trust-domain"):
            self.assertNotIn(forbidden, self.action)


if __name__ == "__main__":
    unittest.main()
