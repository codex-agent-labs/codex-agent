"""Invocation-only tooling-policy forwarding for native SDK preparation."""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci import sdk_workflow
from ci.tests import test_sdk_native_prepare_workflow as fixture_module
from products.inventory import regular_file_inventory, write_canonical_json


class NativePrepareToolingPolicyTest(unittest.TestCase):
    def fixture(self):
        source = fixture_module.SdkNativePrepareWorkflowTest(
            methodName="test_returns_exact_prepared_result_only_after_verified_context_exit",
        )
        source.setUp()
        self.addCleanup(source.doCleanups)
        self.addCleanup(source.tearDown)
        return source

    def test_supplied_policy_is_forwarded_to_both_authenticated_replays_only(self):
        source = self.fixture()
        policy = {"invocationOnly": "never transported"}
        original_verified = source.verified
        original_materialize = source.materialize

        @contextmanager
        def verified(*args, **kwargs):
            self.assertIs(policy, kwargs.pop("sdk_validation_tooling"))
            with original_verified(*args, **kwargs) as inputs:
                yield inputs

        def materialize(*args, **kwargs):
            self.assertIs(policy, kwargs.pop("sdk_validation_tooling"))
            return original_materialize(*args, **kwargs)

        source.verified = verified
        source.materialize = materialize
        source.invoke(sdk_validation_tooling=policy)
        self.assertIs(policy, source.context_mock.call_args.kwargs["sdk_validation_tooling"])
        self.assertIs(policy, source.materialize_mock.call_args.kwargs["sdk_validation_tooling"])
        for row in regular_file_inventory(source.destination / "upload", allow_empty=True):
            self.assertNotIn(b"invocationOnly", (source.destination / "upload" / row["relativePath"]).read_bytes())

    def test_omitted_policy_preserves_both_existing_replay_calls(self):
        source = self.fixture()
        source.invoke()
        self.assertNotIn("sdk_validation_tooling", source.context_mock.call_args.kwargs)
        self.assertNotIn("sdk_validation_tooling", source.materialize_mock.call_args.kwargs)

    def test_cli_canonically_forwards_supplied_policy_and_preserves_omission(self):
        with tempfile.TemporaryDirectory(prefix="native-prepare-tooling-cli-") as temporary:
            root = Path(temporary).resolve()
            paths = {name: root / name for name in (
                "plan", "discovery-root", "state-root", "destination", "keyring",
                "keys-directory", "repository-root",
            )}
            argv = ["native-prepare", "--component", "python", *[
                item for name, value in paths.items() for item in (f"--{name}", str(value))
            ], "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
                "--trusted-workflow-sha", "b" * 40, "--expected-build-key", "c" * 64]
            policy = {"invocationOnly": "canonical caller control"}
            policy_path = root / "tooling-policy.json"
            write_canonical_json(policy_path, policy)
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "cli-token"}, clear=True), \
                    mock.patch.object(sdk_workflow, "prepare_native") as prepare:
                self.assertEqual(0, sdk_workflow.main(argv))
                self.assertNotIn("sdk_validation_tooling", prepare.call_args.kwargs)
                prepare.reset_mock()
                self.assertEqual(0, sdk_workflow.main([
                    *argv, "--sdk-validation-tooling", str(policy_path),
                ]))
                self.assertEqual(policy, prepare.call_args.kwargs["sdk_validation_tooling"])


if __name__ == "__main__":
    unittest.main()
