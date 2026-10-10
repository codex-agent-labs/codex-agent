"""Invocation boundary only: controllers are mocked; no signing or replay runs."""

import builtins
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci import sdk_apple_release_cli as command


class AppleReleaseCliTest(unittest.TestCase):
    def fields(self, mode):
        fields = {
            "plan": "/work/plan.json", "validation-receipt": "/work/receipt.json",
            "destination": "/work/output", "repository-root": "/work/repository",
            "target": "ios-arm64", "expected-receipt-sha256": "sha256:" + "1" * 64,
            "artifact-id": "91", "artifact-sha256": "sha256:" + "2" * 64,
            "trusted-workflow-sha": "a" * 40,
        }
        if mode == "prepare":
            fields.update({name: f"/work/{name}" for name in (
                "keyring", "keys-directory", "tooling-evidence", "tooling-public-key",
                "java-executable", "tooling-keyring", "tooling-keys-directory")})
            fields["policy-revision"] = "b" * 40
        else:
            fields.update({"candidate-root": "/work/candidate", "preparation-artifact-id": "92",
                "preparation-artifact-sha256": "sha256:" + "3" * 64,
                "trusted-source-sha": "c" * 40, "validation-tree": "d" * 40})
        return fields

    def arguments(self, mode, fields=None):
        return [mode, *(part for key, value in (self.fields(mode) if fields is None else fields).items()
                        for part in (f"--{key}", value))]

    def modules(self, prepare, sign):
        return patch.dict("sys.modules", {
            "sdk_ios_original_validation": SimpleNamespace(prepare_ios_validation_signing_inputs=prepare),
            "sdk_apple_prepared_release": SimpleNamespace(attest_prepared_apple_validation_ci=sign),
        })

    def test_prepare_exact_forwarding_both_targets_fixed_release_and_original_environment(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            fields = {**self.fields("prepare"), "target": target}
            prepare, sign = Mock(), Mock()
            with self.subTest(target=target), self.modules(prepare, sign), \
                    patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token"}, clear=True), \
                    patch.object(command, "read_regular_file_bytes") as read:
                self.assertEqual(0, command.main(self.arguments("prepare", fields)))
                prepare.assert_called_once_with(Path(fields["plan"]), Path(fields["validation-receipt"]),
                    Path(fields["destination"]), target=target,
                    expected_receipt_sha256=fields["expected-receipt-sha256"], artifact_id=91,
                    artifact_sha256=fields["artifact-sha256"], trusted_workflow_sha=fields["trusted-workflow-sha"],
                    repository_root=Path(fields["repository-root"]), environ=os.environ, token="caller-token",
                    required_trust_domain="release", policy_revision=fields["policy-revision"],
                    **{name.replace("-", "_"): Path(fields[name]) for name in (
                        "keyring", "keys-directory", "tooling-evidence", "tooling-public-key",
                        "java-executable", "tooling-keyring", "tooling-keys-directory")})
                self.assertIs(os.environ, prepare.call_args.kwargs["environ"])
                read.assert_not_called()
                sign.assert_not_called()

    def test_sign_exact_producer_event_routing_and_no_replay_import(self):
        actual_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name == "sdk_ios_original_validation":
                raise AssertionError("sign mode imported replay")
            return actual_import(name, *args, **kwargs)
        for target, event in (("ios-arm64", "pull_request"), ("ios-simulator-arm64", "merge_group")):
            fields = {**self.fields("sign"), "target": target}
            environment = {"GITHUB_EVENT_PATH": "/work/event.json", "GITHUB_EVENT_NAME": event,
                "GITHUB_REPOSITORY": "owner/repository", "GITHUB_SHA": "e" * 40,
                "GITHUB_RUN_ID": "81", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_TOKEN": "observer-token",
                "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "opaque-test-value"}
            prepare, sign = Mock(), Mock()
            with self.subTest(target=target), self.modules(prepare, sign), \
                    patch.dict(os.environ, environment, clear=True), \
                    patch.object(command, "read_regular_file_bytes", return_value=b'{"number":31}') as read, \
                    patch("builtins.__import__", side_effect=guarded_import):
                self.assertEqual(0, command.main(self.arguments("sign", fields)))
                sign.assert_called_once_with(Path(fields["repository-root"]), Path(fields["candidate-root"]),
                    Path(fields["plan"]), Path(fields["validation-receipt"]), Path(fields["destination"]),
                    target=target, expected_receipt_sha256=fields["expected-receipt-sha256"],
                    artifact_id=91, artifact_sha256=fields["artifact-sha256"],
                    trusted_workflow_sha=fields["trusted-workflow-sha"], token="observer-token",
                    preparation_artifact_id=92, preparation_artifact_sha256=fields["preparation-artifact-sha256"],
                    trusted_source_sha=fields["trusted-source-sha"], event_payload={"number": 31},
                    environment=os.environ, transport_producer={"repository": "owner/repository",
                        "workflowPath": ".github/workflows/ci.yml", "commit": "e" * 40, "tree": "d" * 40,
                        "event": event, "runId": 81, "runAttempt": 2,
                        "pullRequest": 31 if event == "pull_request" else None})
                self.assertIs(os.environ, sign.call_args.kwargs["environment"])
                read.assert_called_once_with(Path("/work/event.json"), max_bytes=16 * 1024 * 1024,
                                             reject_symlink_parents=True)
                prepare.assert_not_called()

    def test_missing_malformed_and_foreign_mode_arguments_fail_before_reads_or_imports(self):
        actual_import = builtins.__import__
        for mode in ("prepare", "sign"):
            baseline = self.fields(mode)
            cases = [self.arguments(mode, {key: value for key, value in baseline.items() if key != missing})
                     for missing in baseline]
            cases.extend(self.arguments(mode, {**baseline, key: value}) for key, value in (
                ("target", "ios"), ("artifact-id", "0"), ("artifact-id", "not-int"),
                ("artifact-sha256", "a" * 64), ("expected-receipt-sha256", "sha256:" + "A" * 64),
                ("trusted-workflow-sha", "HEAD")))
            extras = (("--tooling-evidence", "/work/evidence"), ("--keyring", "/work/keys")) if mode == "sign" else (
                ("--candidate-root", "/work/candidate"), ("--preparation-artifact-id", "92"))
            cases.extend(self.arguments(mode) + list(extra) for extra in (*extras,
                ("--required-trust-domain", "development"), ("--trusted-workflow", "a" * 40),
                ("--producer", "/work/producer")))
            for args in cases:
                with self.subTest(args=args), patch.object(command, "read_regular_file_bytes") as read, \
                        patch("builtins.__import__", side_effect=actual_import) as imports, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as error:
                    command.main(args)
                self.assertEqual(2, error.exception.code)
                read.assert_not_called()
                self.assertFalse(any(call.args[0] in {"sdk_ios_original_validation", "sdk_apple_prepared_release"}
                                     for call in imports.call_args_list))

    def test_secret_presence_blocks_before_original_reader_import_or_reads(self):
        actual_import = builtins.__import__
        def guarded_import(name, *args, **kwargs):
            if name in {"sdk_ios_original_validation", "sdk_apple_prepared_release"}:
                raise AssertionError("controller imported before secret guard")
            return actual_import(name, *args, **kwargs)
        for value in ("", "opaque-test-value"):
            with self.subTest(empty=not value), patch.dict(os.environ,
                    {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": value}, clear=True), \
                    patch.object(command, "read_regular_file_bytes") as read, \
                    patch("builtins.__import__", side_effect=guarded_import), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                command.main(self.arguments("prepare"))
            self.assertEqual(2, error.exception.code)
            read.assert_not_called()

    def test_controller_failure_fails_and_missing_token_is_not_invented(self):
        prepare = Mock(side_effect=ValueError("original verification failed"))
        with self.modules(prepare, Mock()), patch.dict(os.environ, {}, clear=True), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            command.main(self.arguments("prepare"))
        self.assertEqual(2, error.exception.code)
        self.assertEqual("", prepare.call_args.kwargs["token"])


if __name__ == "__main__":
    unittest.main()
