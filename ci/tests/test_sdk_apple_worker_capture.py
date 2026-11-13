"""Worker-receipt bootstrap routing; locator and authenticated capture are mocked."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_apple_worker_capture as command
from ci.products.inventory import sha256_bytes


class AppleWorkerCaptureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-worker-capture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan, self.candidate, self.destination = (self.root / name for name in ("plan.json", "candidate", "capture"))
        self.output = self.root / "github-output"
        self.locator = {"artifact_id": 91, "artifact_sha256": "sha256:" + "a" * 64}
        self.raw = b"exact original receipt bytes from mocked capture\n"
        self.digest = sha256_bytes(self.raw)
        self.environment = {"GITHUB_TOKEN": "caller-token", "GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        self.arguments = {"target": "ios-arm64", "expected_build_key": "sha256:" + "b" * 64,
                          "trusted_workflow_sha": "c" * 40, "environ": self.environment, "token": "caller-token"}

    def call(self, **changes):
        return command.capture_worker(self.plan, self.candidate, self.destination, **{**self.arguments, **changes})

    def fields(self):
        return {"plan": str(self.plan), "candidate-root": str(self.candidate), "destination": str(self.destination),
                "target": "ios-arm64", "expected-build-key": self.arguments["expected_build_key"],
                "trusted-workflow-sha": self.arguments["trusted_workflow_sha"]}

    def argv(self, fields=None):
        return [part for name, value in (self.fields() if fields is None else fields).items()
                for part in ("--" + name, value)]

    def test_both_targets_exact_lookup_then_capture_return_only_locator_and_receipt(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            calls = []
            def locate(*args, **kwargs):
                calls.append("lookup")
                return dict(self.locator)
            def capture(*args, **kwargs):
                self.assertEqual(["lookup"], calls)
                calls.append("capture")
                receipt = self.destination / "original/shard/phase-receipt.json"
                receipt.parent.mkdir(parents=True, exist_ok=True)
                receipt.write_bytes(self.raw)
                return {"validationReceiptSha256": self.digest, "opaqueCaptureField": "must not escape"}
            with self.subTest(target=target), patch.dict(os.environ, {}, clear=True), \
                    patch.object(command, "locate_apple_upload", side_effect=locate) as lookup, \
                    patch.object(command.products, "capture_elected_sdk_ios_validation_upload", side_effect=capture) as captured:
                result = self.call(target=target)
            lookup.assert_called_once_with(self.plan, self.candidate, mode="validation", target=target,
                expected_build_key=self.arguments["expected_build_key"], trusted_workflow_sha=self.arguments["trusted_workflow_sha"],
                environ=self.environment, token="caller-token")
            captured.assert_called_once_with(self.plan, self.destination, target=target,
                expected_build_key=self.arguments["expected_build_key"], **self.locator,
                trusted_workflow_sha=self.arguments["trusted_workflow_sha"], repository_root=self.candidate,
                environ=self.environment, token="caller-token")
            self.assertIs(self.environment, lookup.call_args.kwargs["environ"])
            self.assertIs(self.environment, captured.call_args.kwargs["environ"])
            self.assertEqual(["lookup", "capture"], calls)
            self.assertEqual({**self.locator, "receipt_path": str(self.destination / "original/shard/phase-receipt.json"),
                              "receipt_sha256": self.digest}, result)
            self.assertEqual(self.raw, Path(result["receipt_path"]).read_bytes())

    def test_secret_presence_in_caller_or_process_rejects_before_lookup(self):
        secret = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"
        for caller, process in (({secret: ""}, {}), ({}, {secret: "opaque-test-value"})):
            with self.subTest(caller=bool(caller)), patch.dict(os.environ, process, clear=True), \
                    patch.object(command, "locate_apple_upload") as lookup, \
                    patch.object(command.products, "capture_elected_sdk_ios_validation_upload") as capture, \
                    self.assertRaises(ValueError):
                self.call(environ=caller)
            lookup.assert_not_called()
            capture.assert_not_called()

    def test_cli_exact_environment_and_outputs_without_policy_or_token_fields(self):
        for github_output in (False, True):
            stdout = io.StringIO()
            with self.subTest(github_output=github_output), patch.dict(os.environ, self.environment, clear=True), \
                    patch.object(command, "locate_apple_upload", return_value=self.locator) as lookup, \
                    patch.object(command.products, "capture_elected_sdk_ios_validation_upload",
                                 return_value={"validationReceiptSha256": self.digest}) as capture, redirect_stdout(stdout):
                argv = self.argv() + (["--github-output", str(self.output)] if github_output else [])
                self.assertEqual(0, command.main(argv))
                self.assertIs(os.environ, lookup.call_args.kwargs["environ"])
                self.assertIs(os.environ, capture.call_args.kwargs["environ"])
                self.assertEqual("caller-token", capture.call_args.kwargs["token"])
            expected = {**self.locator, "receipt_path": str(self.destination / "original/shard/phase-receipt.json"),
                        "receipt_sha256": self.digest}
            if github_output:
                self.assertEqual({key: str(value) for key, value in expected.items()},
                                 dict(line.split("=", 1) for line in self.output.read_text().splitlines()))
                self.assertEqual("", stdout.getvalue())
            else:
                self.assertEqual(expected, json.loads(stdout.getvalue()))

    def test_cli_failures_bad_digest_and_late_secret_never_emit_success_output(self):
        for case in ("lookup", "capture", "bad-digest", "missing-digest", "late-secret"):
            def capture(*args, **kwargs):
                if case == "capture": raise ValueError("capture rejected")
                if case == "late-secret": os.environ["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
                if case == "missing-digest": return {}
                return {"validationReceiptSha256": "invalid" if case == "bad-digest" else self.digest}
            stdout = io.StringIO()
            with self.subTest(case=case), patch.dict(os.environ, self.environment, clear=True), \
                    patch.object(command, "locate_apple_upload", return_value=self.locator,
                                 side_effect=ValueError("lookup rejected") if case == "lookup" else None), \
                    patch.object(command.products, "capture_elected_sdk_ios_validation_upload", side_effect=capture), \
                    redirect_stdout(stdout), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                command.main(self.argv() + ["--github-output", str(self.output)])
            self.assertEqual(2, error.exception.code)
            self.assertFalse(self.output.exists())
            self.assertEqual("", stdout.getvalue())

    def test_cli_required_and_unknown_switches_reject_before_lookup(self):
        baseline = self.fields()
        cases = [self.argv({key: value for key, value in baseline.items() if key != missing}) for missing in baseline]
        cases.append(self.argv({**baseline, "target": "ios"}))
        cases.extend(self.argv() + list(extra) for extra in (
            ("--token", "not-a-cli-input"), ("--tooling-policy", "/transported/policy"),
            ("--sdk-apple-validation-policy", "/transported/policy"), ("--command", "arbitrary"),
            ("--expected-build", "sha256:" + "a" * 64)))
        for argv in cases:
            with self.subTest(argv=argv), patch.object(command, "locate_apple_upload") as lookup, \
                    patch.object(command.products, "capture_elected_sdk_ios_validation_upload") as capture, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                command.main(argv)
            self.assertEqual(2, error.exception.code)
            lookup.assert_not_called()
            capture.assert_not_called()
        with patch.object(command, "locate_apple_upload") as lookup, self.assertRaises(ValueError):
            command.capture_worker(self.plan, self.candidate, Path("/invalid\noutput"), **self.arguments)
        lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
