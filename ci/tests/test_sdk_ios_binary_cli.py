"""CLI composition only: no native, receipt, planner or signing authority mocked in."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow


class SdkIosBinaryCliTest(unittest.TestCase):
    def setUp(self):
        self.fields = {
            "--plan": "original plan/impact-plan.json",
            "--discovery-root": "original discovery",
            "--state-root": "original state",
            "--destination": "fresh worker",
            "--repository-root": "candidate repository",
            "--trusted-workflow-sha": "a" * 40,
            "--expected-build-key": "sha256:" + "b" * 64,
            "--native-tests-artifact-id": "101",
            "--native-tests-artifact-sha256": "sha256:" + "1" * 64,
            "--rust-device-artifact-id": "102",
            "--rust-device-artifact-sha256": "sha256:" + "2" * 64,
            "--rust-simulator-artifact-id": "103",
            "--rust-simulator-artifact-sha256": "sha256:" + "3" * 64,
        }

    def argv(self, *, omit=None, replace=None):
        values = {**self.fields, **(replace or {})}
        return ["ios-binary", *(item for name, value in values.items() if name != omit for item in (name, value))]

    def test_exact_paths_upload_mapping_and_original_environment_are_forwarded(self):
        environment = {"GITHUB_TOKEN": "synthetic-token", "SDK_TEST_CONTEXT": "unchanged"}
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(workflow, "execute_ios_binary", return_value={"synthetic": "controller result"}) as execute:
            self.assertEqual(0, workflow.main(self.argv()))
            execute.assert_called_once_with(
                Path(self.fields["--plan"]), Path(self.fields["--discovery-root"]),
                Path(self.fields["--state-root"]), Path(self.fields["--destination"]),
                expected_build_key=self.fields["--expected-build-key"],
                trusted_workflow_sha=self.fields["--trusted-workflow-sha"],
                repository_root=Path(self.fields["--repository-root"]),
                native_uploads={f"ios-{lane}": {"artifactId": int(self.fields[f"--{lane}-artifact-id"]),
                    "artifactSha256": self.fields[f"--{lane}-artifact-sha256"]}
                    for lane in ("native-tests", "rust-device", "rust-simulator")},
                environ=os.environ, token="synthetic-token")
            self.assertIs(os.environ, execute.call_args.kwargs["environ"])
            self.assertEqual(environment, dict(execute.call_args.kwargs["environ"]))

    def test_every_required_field_is_mandatory_before_controller_dispatch(self):
        for field in self.fields:
            with self.subTest(field=field), patch.object(workflow, "execute_ios_binary") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv(omit=field))
            self.assertEqual(2, failure.exception.code)
            execute.assert_not_called()

    def test_upload_ids_are_integers_and_authority_or_phase_overrides_are_unsupported(self):
        cases = [self.argv(replace={f"--{lane}-artifact-id": "not-an-integer"})
                 for lane in ("native-tests", "rust-device", "rust-simulator")]
        cases.extend([*self.argv(), flag, value] for flag, value in (
            ("--keyring", "caller-selected-policy"), ("--keys-directory", "caller-selected-keys"),
            ("--source", "caller-selected-source"), ("--phase", "package"),
            ("--native-evidence", "unobserved-native-directory"),
        ))
        for arguments in cases:
            with self.subTest(arguments=arguments[-2:]), patch.object(workflow, "execute_ios_binary") as execute, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                workflow.main(arguments)
            self.assertEqual(2, failure.exception.code)
            execute.assert_not_called()

    def test_controller_rejection_is_cli_failure_without_falling_back_to_other_modes(self):
        for error in (ValueError("elected key rejected"), OSError("original input unavailable")):
            with self.subTest(error=error), patch.object(workflow, "execute_ios_binary", side_effect=error) as execute, \
                    patch.object(workflow, "stage") as stage, patch.object(workflow, "execute_javascript") as javascript, \
                    redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as failure:
                workflow.main(self.argv())
            self.assertEqual(2, failure.exception.code)
            self.assertIn(str(error), stderr.getvalue())
            execute.assert_called_once()
            stage.assert_not_called()
            javascript.assert_not_called()


if __name__ == "__main__":
    unittest.main()
