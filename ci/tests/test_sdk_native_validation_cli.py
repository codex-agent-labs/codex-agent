"""Strict CLI dispatch only; the execution/authentication boundary is mocked."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_native_validation_workflow as workflow
from ci.tests.test_sdk_native_package_execution import caller_apple_policy
from products.inventory import canonical_json_bytes


class SdkNativeValidationCliTest(unittest.TestCase):
    def setUp(self):
        self.arguments = {name: Path("/synthetic inputs") / name for name in (
            "plan", "discovery", "state", "destination", "preparation_state", "keyring",
            "keys_directory", "repository_root", "tooling_evidence", "tooling_public_key", "java_executable")}
        self.arguments.update(component="python", target="linux-x64", preparation_component="rust",
            expected_build_key="sha256:" + "a" * 64, preparation_build_key="sha256:" + "b" * 64,
            prepared_artifact_id=72, prepared_artifact_sha256="sha256:" + "c" * 64,
            sdk_inputs_artifact_id=71, sdk_inputs_artifact_sha256="sha256:" + "d" * 64,
            trusted_workflow_sha="e" * 40, policy_revision="f" * 40, required_trust_domain="development")
        names = {"discovery": "discovery-root", "state": "state-root", "preparation_state": "preparation-state-root"}
        self.argv = [part for name, value in self.arguments.items()
                     for part in ("--" + names.get(name, name.replace("_", "-")), str(value))]
        self.optional = {name: None for name in ("tooling_keyring", "tooling_keys_directory",
            "dotnet_executable", "dart_executable", "dart_package_config")}
        self.optional.update(preparation_phase="package", preparation_target="desktop")

    def test_exact_original_state_upload_target_and_tooling_forward_with_environment_only_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic token"}, clear=True), \
                patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(self.argv))
            execute.assert_called_once_with(**self.arguments, **self.optional,
                                            environ=os.environ, token="synthetic token")

    def test_cli_canonical_apple_policy_forwarding_and_malformed_rejection(self):
        with tempfile.TemporaryDirectory(prefix="native-validation-apple-cli-") as temporary:
            root = Path(temporary).resolve()
            path = root / "apple policy.json"
            policy = caller_apple_policy(root)
            raw = canonical_json_bytes(policy)
            path.write_bytes(raw)
            with patch.dict(os.environ, {"GITHUB_TOKEN": "caller token"}, clear=True), \
                    patch.object(workflow, "execute") as execute:
                self.assertEqual(0, workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)]))
                execute.assert_called_once_with(**self.arguments, **self.optional,
                    environ=os.environ, token="caller token", sdk_apple_validation_policy=policy)
                self.assertEqual(raw, path.read_bytes())
            for invalid in (b"{", b"[]\n", b"null\n", b'{ "plan": "noncanonical" }\n'):
                with self.subTest(invalid=invalid), patch.object(workflow, "execute") as execute, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    path.write_bytes(invalid)
                    workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)])
                self.assertEqual(2, failure.exception.code)
                execute.assert_not_called()

    def test_optional_release_policy_and_language_executable_paths_forward_without_defaults(self):
        for component, extra in (("csharp", {"dotnet_executable": Path("/trusted tools/dotnet")}),
                                  ("dart", {"dart_executable": Path("/trusted tools/dart"),
                                            "dart_package_config": Path("/original/package_config.json")})):
            with self.subTest(component=component):
                args = self.argv.copy()
                args[args.index("--component") + 1] = component
                args[args.index("--required-trust-domain") + 1] = "release"
                values = {**extra, "tooling_keyring": Path("/caller/keyring.json"),
                          "tooling_keys_directory": Path("/caller/keys")}
                args += [part for name, value in values.items()
                         for part in ("--" + name.replace("_", "-"), str(value))]
                with patch.dict(os.environ, {}, clear=True), patch.object(workflow, "execute") as execute:
                    self.assertEqual(0, workflow.main(args))
                    execute.assert_called_once_with(**{**self.arguments, "component": component,
                        "required_trust_domain": "release", **self.optional, **values}, environ=os.environ, token="")

    def test_mandatory_identity_policy_no_abbreviations_or_caller_command_override(self):
        invalid = []
        for flag in ("--preparation-state-root", "--target", "--tooling-evidence", "--policy-revision",
                     "--required-trust-domain", "--expected-build-key"):
            args = self.argv.copy()
            index = args.index(flag)
            del args[index:index + 2]
            invalid.append(args)
        for flag, value in (("--target", "desktop"), ("--component", "javascript"),
                            ("--preparation-component", "sdk-ios"), ("--required-trust-domain", "any"),
                            ("--prepared-artifact-id", "not-integer")):
            args = self.argv.copy()
            args[args.index(flag) + 1] = value
            invalid.append(args)
        invalid.append(["--preparation-state" if value == "--preparation-state-root" else value for value in self.argv])
        for name in ("command", "phase", "phase-plan", "staged-sdks", "runtime-stages", "token"):
            invalid.append([*self.argv, f"--{name}", "caller override"])
        for args in invalid:
            with self.subTest(args=args), patch.object(workflow, "execute") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                workflow.main(args)
            self.assertEqual(2, error.exception.code)
            execute.assert_not_called()

    def test_execution_or_io_rejection_is_exit_two(self):
        for error in (ValueError("original input rejected"), OSError("unavailable original")):
            with self.subTest(error=type(error).__name__), patch.object(workflow, "execute", side_effect=error), \
                    redirect_stderr(io.StringIO()) as output, self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv)
            self.assertEqual(2, failure.exception.code)
            self.assertIn(str(error), output.getvalue())


if __name__ == "__main__":
    unittest.main()
