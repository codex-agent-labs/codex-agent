"""Strict invocation forwarding with mocked controller; no Apple execution."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from ci import sdk_ios_validation_workflow as command
from ci import sdk_workflow as dispatcher


class SdkIosValidationCliTest(unittest.TestCase):
    def test_optional_apple_policy_is_canonical_caller_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary).resolve() / "caller policy.json"
            policy.write_bytes(b'{"caller":"policy"}\n')
            argv = self.arguments() + ["--sdk-apple-validation-policy", str(policy)]
            with patch.object(command, "execute") as controller:
                self.assertEqual(0, command.main(argv))
            self.assertEqual({"caller": "policy"}, controller.call_args.kwargs["sdk_apple_validation_policy"])
            for malformed in (b'[]\n', b'{"a":1,"a":2}\n', b'{"caller": "policy"}'):
                policy.write_bytes(malformed)
                with patch.object(command, "execute") as controller, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit):
                    command.main(argv)
                controller.assert_not_called()

    def fields(self):
        return {
            "plan": "/work/plan.json", "discovery-root": "/work/discovery",
            "state-root": "/work/state", "destination": "/work/output",
            "repository-root": "/work/repository", "target": "ios-arm64",
            "expected-build-key": "sha256:" + "1" * 64,
            "package-artifact-id": "71", "package-artifact-sha256": "sha256:" + "2" * 64,
            "binary-artifact-id": "72", "binary-artifact-sha256": "sha256:" + "3" * 64,
            "rust-host": "aarch64-apple-darwin", "trusted-workflow-sha": "a" * 40,
            "keyring": "/work/product-keys.json", "keys-directory": "/work/keys",
            "tooling-evidence": "/work/tooling", "tooling-public-key": "/work/tooling.pub",
            "java-executable": "/jdk/bin/java", "policy-revision": "b" * 40,
            "required-trust-domain": "release",
        }

    def arguments(self, fields=None):
        return [part for key, value in (self.fields() if fields is None else fields).items()
                for part in (f"--{key}", value)]

    def test_exact_arguments_both_targets_optional_policy_and_original_environment(self):
        path_fields = {"plan", "discovery-root", "state-root", "destination", "repository-root",
                       "keyring", "keys-directory", "tooling-evidence", "tooling-public-key", "java-executable"}
        for target, policy in (("ios-arm64", False), ("ios-simulator-arm64", True)):
            fields = {**self.fields(), "target": target}
            if policy:
                fields.update({"tooling-keyring": "/work/tooling-keys.json", "tooling-keys-directory": "/work/tooling-keys"})
            expected = {}
            for name, value in fields.items():
                key = {"discovery-root": "discovery", "state-root": "state"}.get(name, name.replace("-", "_"))
                expected[key] = (Path(value) if name in path_fields or name.startswith("tooling-key") else
                                 int(value) if name.endswith("-artifact-id") else value)
            expected.setdefault("tooling_keyring", None)
            expected.setdefault("tooling_keys_directory", None)
            calls = []
            def execute(**arguments):
                self.assertIs(os.environ, arguments["environ"])
                calls.append({**arguments, "environ": dict(arguments["environ"])})
            environment = {"GITHUB_TOKEN": "caller-token", "DEVELOPER_DIR": "/original/Xcode", "SAFE": "unchanged"}
            with self.subTest(target=target), patch.dict(os.environ, environment, clear=True), \
                    patch.object(command, "execute", side_effect=execute) as controller:
                self.assertEqual(0, command.main(self.arguments(fields)))
                controller.assert_called_once()
            self.assertEqual([{**expected, "environ": environment, "token": "caller-token"}], calls)

    def test_every_required_argument_and_invalid_choices_fail_before_controller(self):
        baseline = self.fields()
        cases = [{key: value for key, value in baseline.items() if key != removed} for removed in baseline]
        cases.extend({**baseline, key: value} for key, value in (
            ("target", "ios"), ("rust-host", "x86_64-apple-darwin"),
            ("required-trust-domain", "trusted"), ("package-artifact-id", "not-int"),
            ("binary-artifact-id", "true"),
        ))
        for fields in cases:
            with self.subTest(fields=fields), redirect_stderr(io.StringIO()), \
                    patch.object(command, "execute") as controller, self.assertRaises(SystemExit) as error:
                command.main(self.arguments(fields))
            self.assertEqual(2, error.exception.code)
            controller.assert_not_called()

    def test_unknown_overrides_abbreviations_and_unpaired_tooling_are_rejected(self):
        for extra in (("--source-revision", "c" * 40), ("--command", "arbitrary"),
                      ("--original-working-directory", "/other"), ("--producer", "/other.json"),
                      ("--tooling-keyring", "/work/tooling-keys.json"),
                      ("--tooling-keys-directory", "/work/tooling-keys"), ("--policy-rev", "c" * 40)):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), \
                    patch.object(command, "execute") as controller, self.assertRaises(SystemExit) as error:
                command.main(self.arguments() + list(extra))
            self.assertEqual(2, error.exception.code)
            controller.assert_not_called()

    def test_absent_predecessor_pairs_are_forwarded_as_absent_without_choosing_current_uploads(self):
        for omitted in (("package",), ("binary",), ("package", "binary")):
            fields = self.fields()
            for phase in omitted:
                fields.pop(f"{phase}-artifact-id")
                fields.pop(f"{phase}-artifact-sha256")
            with self.subTest(omitted=omitted), patch.object(command, "execute") as controller:
                self.assertEqual(0, command.main(self.arguments(fields)))
            for phase in omitted:
                self.assertIsNone(controller.call_args.kwargs[f"{phase}_artifact_id"])
                self.assertIsNone(controller.call_args.kwargs[f"{phase}_artifact_sha256"])

    def test_controller_errors_fail_and_absent_token_is_not_invented(self):
        for failure in (ValueError("verification failed"), OSError("input unavailable")):
            with self.subTest(failure=failure), redirect_stderr(io.StringIO()), \
                    patch.dict(os.environ, {}, clear=True), patch.object(command, "execute", side_effect=failure) as controller, \
                    self.assertRaises(SystemExit) as error:
                command.main(self.arguments())
            self.assertEqual(2, error.exception.code)
            self.assertEqual("", controller.call_args.kwargs["token"])

    def test_shared_dispatch_preserves_only_the_validation_argument_tail(self):
        with patch("sdk_ios_validation_workflow.main", return_value=17) as validation:
            self.assertEqual(17, dispatcher.main(["ios-validation", "--fixed", "tail"]))
        validation.assert_called_once_with(["--fixed", "tail"])


if __name__ == "__main__":
    unittest.main()
