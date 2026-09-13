"""Strict CLI forwarding only; the actual authenticated controller is mocked."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_javascript_metadata_workflow as workflow


class SdkJavaScriptMetadataCliTest(unittest.TestCase):
    def setUp(self):
        self.paths = {"plan": "original plan.json", "discovery-root": "original discovery",
            "state-root": "original state", "destination": "fresh worker", "keyring": "caller keyring.json",
            "keys-directory": "caller keys", "repository-root": "candidate repository",
            "tooling-evidence": "original tooling", "tooling-public-key": "tooling.pub", "java-executable": "pinned java"}
        self.fields = {**self.paths, "expected-build-key": "sha256:" + "a" * 64,
            "sdk-inputs-artifact-id": "71", "sdk-inputs-artifact-sha256": "sha256:" + "b" * 64,
            "validation-artifact-id": "72", "validation-artifact-sha256": "sha256:" + "c" * 64,
            "trusted-workflow-sha": "d" * 40, "policy-revision": "e" * 40, "required-trust-domain": "release"}

    def argv(self, *, omit=None, replace=None):
        return [item for name, value in {**self.fields, **(replace or {})}.items() if name != omit
                for item in ("--" + name, value)]

    def test_exact_inputs_optional_key_pair_and_original_environment_forwarded(self):
        for paired in (False, True):
            pair = {"tooling-keyring": "original tooling policy.json", "tooling-keys-directory": "original tooling keys"} if paired else {}
            with self.subTest(paired=paired), patch.dict(os.environ, {"GITHUB_TOKEN": "explicit token", "CONTEXT": "original"}, clear=True), \
                    patch.object(workflow, "execute") as execute:
                self.assertEqual(0, workflow.main(self.argv(replace=pair)))
                expected = {}
                for name, value in {**self.fields, **pair}.items():
                    argument = {"discovery-root": "discovery", "state-root": "state"}.get(name, name.replace("-", "_"))
                    expected[argument] = (Path(value) if name in self.paths or name in pair
                                          else int(value) if name.endswith("-artifact-id") else value)
                if not paired:
                    expected.update(tooling_keyring=None, tooling_keys_directory=None)
                execute.assert_called_once_with(**expected, environ=os.environ, token="explicit token")
                self.assertIs(os.environ, execute.call_args.kwargs["environ"])

    def test_every_authority_and_identity_argument_is_required(self):
        for name in self.fields:
            with self.subTest(name=name), patch.object(workflow, "execute") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv(omit=name))
            self.assertEqual(2, failure.exception.code)
            execute.assert_not_called()

    def test_malformed_ids_unpaired_keys_and_source_command_overrides_reject(self):
        cases = [self.argv(replace={name: "not-an-integer"})
                 for name in ("sdk-inputs-artifact-id", "validation-artifact-id")]
        cases.extend(self.argv(replace={name: "unpaired"}) for name in ("tooling-keyring", "tooling-keys-directory"))
        cases.append(self.argv(replace={"required-trust-domain": "caller-trust"}))
        cases.extend([*self.argv(), flag, value] for flag, value in (
            ("--original-consumer-directory", "/unobserved/consumer"), ("--source", "unobserved-source"),
            ("--command", "arbitrary-command"), ("--phase", "validation"), ("--tooling-evid", "abbreviation")))
        for arguments in cases:
            with self.subTest(arguments=arguments[-2:]), patch.object(workflow, "execute") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(arguments)
            self.assertEqual(2, failure.exception.code)
            execute.assert_not_called()

    def test_controller_failure_is_nonzero_and_missing_token_has_no_fallback(self):
        for error in (ValueError("original source rejected"), OSError("original missing")):
            with self.subTest(error=error), patch.dict(os.environ, {}, clear=True), \
                    patch.object(workflow, "execute", side_effect=error) as execute, \
                    redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv())
            self.assertEqual(2, failure.exception.code)
            self.assertIn(str(error), stderr.getvalue())
            self.assertEqual("", execute.call_args.kwargs["token"])


if __name__ == "__main__":
    unittest.main()
