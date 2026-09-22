"""Runtime caller-policy forwarding only; mocked gates grant no Apple authority."""

from contextlib import redirect_stderr
import io
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_workflow as fixture
from ci.tests.test_sdk_native_package_execution import caller_metadata_admissions


workflow = fixture.workflow


class RuntimeApplePolicyForwardingTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.RuntimeWorkflowTest(methodName="runTest")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.policy = {"caller-policy": "opaque forwarding fixture, not admission"}
        self.tooling = {"caller-tooling": "independent policy fixture"}
        self.admissions = caller_metadata_admissions()
        self.paths = tuple(self.case.root / name for name in ("plan", "discovery", "state"))
        self.policy_path = self.case.root / "apple-policy.json"
        self.policy_path.write_bytes(workflow.canonical_json_bytes(self.policy))

    def assert_policy(self, call, supplied):
        for name, admission in self.admissions.items():
            if supplied:
                self.assertIs(admission, call.call_args.kwargs[name])
            else:
                self.assertNotIn(name, call.call_args.kwargs)
        if supplied:
            self.assertIs(self.policy, call.call_args.kwargs["sdk_apple_validation_policy"])
        else:
            self.assertNotIn("sdk_apple_validation_policy", call.call_args.kwargs)

    def test_matrix_and_continuation_forward_policy_without_changing_legacy_omission(self):
        for supplied in (False, True):
            optional = {"sdk_apple_validation_policy": self.policy, **self.admissions} if supplied else {}
            with self.subTest(supplied=supplied), patch.object(workflow.products, "runtime_worker_matrix",
                    return_value={"include": []}) as matrix, patch.object(workflow.products, "inspect_products",
                    return_value=self.case.final_fixture("retained")) as inspect:
                workflow.matrix(*self.paths, self.case.output, sdk_validation_tooling=self.tooling, **optional)
                workflow.continuation(*self.paths, self.case.output, sdk_validation_tooling=self.tooling, **optional)
            for replay in (matrix, inspect):
                replay.assert_called_once()
                self.assert_policy(replay, supplied)
                self.assertIs(self.tooling, replay.call_args.kwargs["sdk_validation_tooling"])
            self.assertNotIn("caller-policy", self.case.output.read_text())

    def test_capture_forwards_to_matrix_and_aggregate_but_never_transport(self):
        for supplied in (False, True):
            optional = {"sdk_apple_validation_policy": self.policy, **self.admissions} if supplied else {}
            with self.subTest(supplied=supplied), patch.object(workflow.products, "capture_runtime_resume_upload") as transport, \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix, \
                    patch.object(workflow, "continuation", return_value={"aggregate": {
                        "state": "ready", "buildKey": fixture.KEY}}) as continuation:
                result = workflow.capture(self.paths[0], self.case.root / "captured", self.case.output,
                    artifact_id=17, artifact_sha256=fixture.KEY, trusted_workflow_sha=fixture.PIN,
                    state_wave=4, instance=fixture.AGGREGATE, expected_build_key=fixture.KEY,
                    token="explicit-token", sdk_validation_tooling=self.tooling, **optional)
            transport.assert_called_once()
            self.assertNotIn("sdk_apple_validation_policy", transport.call_args.kwargs)
            self.assertNotIn("sdk_validation_tooling", transport.call_args.kwargs)
            for name in self.admissions:
                self.assertNotIn(name, transport.call_args.kwargs)
                self.assertNotIn(name, result)
            for replay in (matrix, continuation):
                replay.assert_called_once()
                self.assert_policy(replay, supplied)
                self.assertIs(self.tooling, replay.call_args.kwargs["sdk_validation_tooling"])
            self.assertNotIn("sdk_apple_validation_policy", result)

    def test_metadata_admissions_are_independently_optional_and_explicit_none_is_omitted(self):
        for selected in (None, *self.admissions):
            optional = {name: admission if name == selected else None
                        for name, admission in self.admissions.items()}
            with self.subTest(selected=selected), patch.object(workflow.products,
                    "runtime_worker_matrix", return_value={"include": []}) as matrix, \
                    patch.object(workflow.products, "inspect_products",
                        return_value=self.case.final_fixture("retained")) as inspect:
                workflow.matrix(*self.paths, self.case.output, **optional)
                workflow.continuation(*self.paths, self.case.output, **optional)
            for replay in (matrix, inspect):
                for name, admission in self.admissions.items():
                    if name == selected:
                        self.assertIs(admission, replay.call_args.kwargs[name])
                    else:
                        self.assertNotIn(name, replay.call_args.kwargs)
            for name in self.admissions:
                self.assertNotIn(name, self.case.output.read_text())

    def test_all_collection_waves_forward_policy_through_advance_and_final_replay(self):
        for wave in range(1, 6):
            for supplied in (False, True):
                optional = {"sdk_apple_validation_policy": self.policy, **self.admissions} if supplied else {}
                destination = self.case.root / f"wave-{wave}-{supplied}"
                with self.subTest(wave=wave, supplied=supplied), patch.object(workflow.products,
                        "collect_runtime_workers", side_effect=self.case.aggregate_collection if wave == 5 else self.case.collection) as collector, \
                        patch.object(workflow.products, "advance_products", side_effect=self.case.advanced) as advance, \
                        patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": []}) as matrix, \
                        patch.object(workflow.products, "inspect_products", return_value=self.case.final_fixture("retained")) as inspect:
                    self.case.collect(destination, wave, **optional)
                for replay in (collector, advance, inspect if wave == 5 else matrix):
                    replay.assert_called_once()
                    self.assert_policy(replay, supplied)
                for name, raw in self.case.base.items():
                    self.assertEqual(raw, (destination / "handoff" / name).read_bytes())

    def cli_arguments(self, command):
        common = ["--github-output", str(self.case.output)]
        if command in ("matrix", "continuation"):
            return [command, *common, *(value for name, path in zip(
                ("plan", "discovery-root", "state-root"), self.paths) for value in ("--" + name, str(path)))]
        common += ["--destination", str(self.case.root / "cli-output"), "--trusted-workflow-sha", fixture.PIN]
        if command == "capture":
            return [command, *common, "--plan", str(self.paths[0]), "--artifact-id", "17", "--artifact-sha256", fixture.KEY]
        return [command, *common, "--input-root", str(self.case.input), "--wave", "5"]

    def test_all_replay_cli_commands_load_canonical_external_policy_and_preserve_omission(self):
        for command in ("matrix", "continuation", "capture", "collect"):
            for supplied in (False, True):
                extra = ["--sdk-apple-validation-policy", str(self.policy_path)] if supplied else []
                with self.subTest(command=command, supplied=supplied), patch.object(workflow, command) as called:
                    self.assertEqual(0, workflow.main(self.cli_arguments(command) + extra))
                called.assert_called_once()
                if supplied:
                    self.assertEqual(self.policy, called.call_args.kwargs["sdk_apple_validation_policy"])
                else:
                    self.assertNotIn("sdk_apple_validation_policy", called.call_args.kwargs)

    def test_malformed_cli_policy_rejects_before_any_replay_or_capture(self):
        for command in ("matrix", "continuation", "capture", "collect"):
            for raw in (b"{", b"[]\n", b'{ "policy": "noncanonical" }\n', b'{"a":1,"a":2}\n'):
                self.policy_path.write_bytes(raw)
                with self.subTest(command=command, raw=raw), redirect_stderr(io.StringIO()), \
                        patch.object(workflow, command) as called, self.assertRaises(SystemExit) as failure:
                    workflow.main(self.cli_arguments(command) + ["--sdk-apple-validation-policy", str(self.policy_path)])
                self.assertEqual(2, failure.exception.code)
                called.assert_not_called()


if __name__ == "__main__":
    unittest.main()
