"""Exact binary-package CLI forwarding tests; no product or Apple execution occurs."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_ios_package_workflow as command
from ci import sdk_workflow as dispatcher


class SdkIosPackageCliTest(unittest.TestCase):
    def arguments(self):
        return [
            "--plan", "/work/plan.json",
            "--discovery-root", "/work/discovery",
            "--state-root", "/work/state",
            "--destination", "/work/output",
            "--expected-build-key", "sha256:" + "a" * 64,
            "--sdk-inputs-artifact-id", "11",
            "--sdk-inputs-artifact-sha256", "sha256:" + "b" * 64,
            "--trusted-workflow-sha", "d" * 40,
            "--keyring", "/work/product-signing-keys.json",
            "--keys-directory", "/work/keys",
            "--developer-directory", "/Applications/Xcode.app/Contents/Developer",
            "--tooling-evidence", "/work/tooling",
            "--tooling-public-key", "/work/tooling.pub",
            "--java-executable", "/jdk/bin/java",
            "--policy-revision", "e" * 40,
            "--required-trust-domain", "release",
            "--repository-root", "/work/repository",
        ]

    def test_exact_fixed_arguments_and_environment_are_forwarded(self):
        calls = []

        def invoke(**arguments):
            calls.append({**arguments, "environ": dict(arguments["environ"])})
            return {"synthetic": "shard"}

        with patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token", "SAFE": "value"}, clear=True), \
                patch.object(command, "execute", side_effect=invoke) as execute:
            self.assertEqual(0, command.main(self.arguments()))
        execute.assert_called_once()
        self.assertEqual({
            "plan": Path("/work/plan.json"),
            "discovery": Path("/work/discovery"),
            "state": Path("/work/state"),
            "destination": Path("/work/output"),
            "expected_build_key": "sha256:" + "a" * 64,
            "sdk_inputs_artifact_id": 11,
            "sdk_inputs_artifact_sha256": "sha256:" + "b" * 64,
            "trusted_workflow_sha": "d" * 40,
            "keyring": Path("/work/product-signing-keys.json"),
            "keys_directory": Path("/work/keys"),
            "developer_directory": Path("/Applications/Xcode.app/Contents/Developer"),
            "tooling_evidence": Path("/work/tooling"),
            "tooling_public_key": Path("/work/tooling.pub"),
            "java_executable": Path("/jdk/bin/java"),
            "policy_revision": "e" * 40,
            "required_trust_domain": "release",
            "repository_root": Path("/work/repository"),
            "tooling_keyring": None,
            "tooling_keys_directory": None,
            "environ": {"GITHUB_TOKEN": "caller-token", "SAFE": "value"},
            "token": "caller-token",
        }, calls[0])

    def test_tooling_trust_is_required_and_cannot_be_inferred(self):
        arguments = self.arguments()
        index = arguments.index("--required-trust-domain")
        for candidate in (
            arguments[:index] + arguments[index + 2:],
            arguments[:index + 1] + ["inferred"] + arguments[index + 2:],
        ):
            with self.subTest(candidate=candidate), redirect_stderr(io.StringIO()), \
                    patch.object(command, "execute") as execute, self.assertRaises(SystemExit):
                command.main(candidate)
            execute.assert_not_called()

    def test_optional_tooling_policy_is_paired_and_forwarded(self):
        arguments = self.arguments() + [
            "--tooling-keyring", "/work/tooling-keyring.json",
            "--tooling-keys-directory", "/work/tooling-keys",
        ]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "token"}, clear=True), \
                patch.object(command, "execute") as execute:
            self.assertEqual(0, command.main(arguments))
        self.assertEqual(Path("/work/tooling-keyring.json"), execute.call_args.kwargs["tooling_keyring"])
        self.assertEqual(Path("/work/tooling-keys"), execute.call_args.kwargs["tooling_keys_directory"])

    def test_removed_legacy_apple_native_and_proof_flags_are_rejected(self):
        removed = (
            ("--apple-artifact-id", "12"),
            ("--apple-artifact-sha256", "sha256:" + "c" * 64),
            ("--native-tests-artifact-id", "21"),
            ("--rust-device-artifact-sha256", "sha256:" + "2" * 64),
            ("--expected-distribution-proof", "/work/proof.json"),
        )
        for option in removed:
            with self.subTest(option=option), redirect_stderr(io.StringIO()), \
                    patch.object(command, "execute") as execute, self.assertRaisesRegex(SystemExit, "2"):
                command.main(self.arguments() + list(option))
            execute.assert_not_called()

    def test_shared_sdk_cli_dispatches_only_the_ios_package_tail(self):
        with patch("sdk_ios_package_workflow.main", return_value=17) as package:
            self.assertEqual(17, dispatcher.main(["ios-package", "--fixed", "tail"]))
        package.assert_called_once_with(["--fixed", "tail"])

    def test_missing_unknown_half_policy_and_executor_errors_exit_two(self):
        cases = (
            self.arguments()[:-2],
            self.arguments() + ["--unknown-option", "value"],
            self.arguments() + ["--tooling-keyring", "/work/tooling-keyring.json"],
        )
        for arguments in cases:
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), \
                    patch.object(command, "execute") as execute, self.assertRaisesRegex(SystemExit, "2"):
                command.main(arguments)
            execute.assert_not_called()
        with patch.object(command, "execute", side_effect=ValueError("fixed caller rejection")), \
                self.assertRaisesRegex(SystemExit, "2"):
            command.main(self.arguments())


if __name__ == "__main__":
    unittest.main()
