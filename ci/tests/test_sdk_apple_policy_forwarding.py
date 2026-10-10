"""SDK workflow caller-policy routing only; replay and execution are mocked."""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow


class ApplePolicyForwardingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b'{"fixture":"caller plan"}\n')
        self.discovery, self.state, self.destination, self.output = (
            self.root / name for name in ("discovery", "state", "destination", "github-output"))
        self.policy = {"plan": str(self.plan), "fixture": "explicit caller policy, never admission"}
        self.tooling = {"fixture": "independent existing tooling policy"}
        self.policy_path = self.root / "policy.json"
        self.policy_path.write_bytes(workflow.canonical_json_bytes(self.policy))
        self.environment = {"GITHUB_RUN_ID": "91"}
        self.common = dict(repository_root=self.root, environ=self.environment, token="caller-token")
        self.upload = dict(artifact_id=71, artifact_sha256="sha256:" + "7" * 64,
            trusted_workflow_sha="a" * 40, keyring=self.root / "keys.json", keys_directory=self.root / "keys")

    def optional(self, present):
        return {"sdk_apple_validation_policy": self.policy} if present else {}

    def assert_policy(self, call, present):
        if present:
            self.assertIs(self.policy, call.kwargs["sdk_apple_validation_policy"])
        else:
            self.assertNotIn("sdk_apple_validation_policy", call.kwargs)

    def test_selection_and_both_stage_sources_forward_only_to_replay(self):
        selection = {"source": "released-default", "sdkVersion": "0.8.0", "compatibleReleaseRange": ">=0.8.0 <0.9.0",
            "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0", "contractPayloadSha256": "sha256:" + "c" * 64}
        for source in ("released-default", "current-runtime"):
            selection["source"] = source
            for present in (False, True):
                with self.subTest(source=source, present=present), \
                        patch.object(workflow.product_reuse, "_validate_plan", return_value={"validationCommit": "a" * 40}), \
                        patch.object(workflow.product_reuse, "inspect_products", return_value={"sdkInputSelection": selection}) as inspect, \
                        patch.object(workflow.product_reuse, "materialize_sdk_default_inputs") as released, \
                        patch.object(workflow.sdk_handoff, "capture_sdk_handoff") as fresh:
                    workflow.stage(self.plan, self.discovery, self.state, self.destination, **self.common, **self.upload,
                        expected_build_key="sha256:" + "b" * 64, expected_metadata_receipt_sha256="sha256:" + "d" * 64,
                        sdk_validation_tooling=self.tooling, **self.optional(present))
                    self.assert_policy(inspect.call_args, present)
                    self.assertIs(self.tooling, inspect.call_args.kwargs["sdk_validation_tooling"])
                    if source == "released-default":
                        self.assert_policy(released.call_args, present)
                        fresh.assert_not_called()
                    else:
                        released.assert_not_called()
                        self.assertNotIn("sdk_apple_validation_policy", fresh.call_args.kwargs)

    def test_verified_input_contexts_forward_policy_before_any_capture(self):
        for present in (False, True):
            with self.subTest(context="SDK", present=present), \
                    patch.object(workflow, "_selection", side_effect=ValueError("replay stopped")) as selection:
                with self.assertRaisesRegex(ValueError, "replay stopped"):
                    with workflow.verified_inputs(self.plan, self.discovery, self.state,
                            **self.common, **self.upload, **self.optional(present)):
                        self.fail("mock replay unexpectedly yielded")
                self.assert_policy(selection.call_args, present)
            with self.subTest(context="binary", present=present), \
                    patch.object(workflow.product_reuse, "_product_materialization_paths", return_value=(self.discovery, self.state, self.destination)), \
                    patch.object(workflow.product_reuse, "_verified_product_state", side_effect=ValueError("replay stopped")) as replay:
                with self.assertRaisesRegex(ValueError, "replay stopped"):
                    with workflow.verified_ios_binary_inputs(self.plan, self.discovery, self.state, self.destination,
                            expected_build_key="sha256:" + "b" * 64, native_uploads={},
                            trusted_workflow_sha="a" * 40, **self.common, **self.optional(present)):
                        self.fail("mock replay unexpectedly yielded")
                self.assert_policy(replay.call_args, present)

    def test_worker_and_preparation_forward_to_input_context_and_materialization(self):
        for kind in ("javascript", "prepare", "binary"):
            for present in (False, True):
                fields = {"product": "sdk", "component": "rust" if kind == "prepare" else "javascript",
                          "phase": "package", "target": "desktop" if kind == "prepare" else "node"}

                @contextmanager
                def inputs(*args, **kwargs):
                    if kind == "binary":
                        raise ValueError("input context stopped")
                    yield {"selection": {"consumers": [fields]}}

                with self.subTest(kind=kind, present=present), \
                        patch.object(workflow.product_reuse, "_product_materialization_paths", return_value=(self.discovery, self.state, self.destination)), \
                        patch.object(workflow, "verified_ios_binary_inputs" if kind == "binary" else "verified_inputs", side_effect=inputs) as joined, \
                        patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=ValueError("materialization stopped")) as materialize:
                    with self.assertRaisesRegex(ValueError, "stopped"):
                        if kind == "binary":
                            workflow.execute_ios_binary(self.plan, self.discovery, self.state, self.destination,
                                expected_build_key="sha256:" + "b" * 64, native_uploads={},
                                trusted_workflow_sha="a" * 40, **self.common, **self.optional(present))
                        else:
                            method = workflow.prepare_native if kind == "prepare" else workflow.execute_javascript
                            method(self.plan, self.discovery, self.state, self.destination,
                                **({"component": "rust"} if kind == "prepare" else {"phase": "package"}),
                                expected_build_key="sha256:" + "b" * 64, **self.common, **self.upload, **self.optional(present))
                    self.assert_policy(joined.call_args, present)
                    if kind != "binary":
                        self.assert_policy(materialize.call_args, present)

    def test_matrix_capture_and_collection_forward_policy_without_serializing_it(self):
        for present in (False, True):
            with self.subTest(present=present), patch.object(workflow.product_reuse, "inspect_products", return_value={"readyPlans": []}) as inspect:
                workflow.matrix(self.plan, self.discovery, self.state, self.output,
                    repository_root=self.root, environ=self.environment, **self.optional(present))
                self.assert_policy(inspect.call_args, present)
                self.assertNotIn("sdk_apple_validation_policy=", self.output.read_text())
                self.assertNotIn("sdkAppleValidationPolicy", self.output.read_text())
                self.assertNotIn(self.policy["fixture"], self.output.read_text())
            with patch.object(workflow.product_reuse, "capture_runtime_resume_upload") as transport, \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                result = workflow.capture(self.plan, self.destination, self.output, artifact_id=71,
                    artifact_sha256="sha256:" + "7" * 64, trusted_workflow_sha="a" * 40,
                    **self.common, **self.optional(present))
                self.assert_policy(matrix.call_args, present)
                self.assertNotIn("sdk_apple_validation_policy", transport.call_args.kwargs)
                self.assertNotIn("sdk_apple_validation_policy", result)
            with patch.object(workflow.product_reuse, "_product_materialization_paths", return_value=(self.discovery, self.discovery, self.destination)), \
                    patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": []}) as collect, \
                    patch.object(workflow.product_reuse, "advance_products", return_value={"fixture": "advanced"}) as advance, \
                    patch.object(workflow, "snapshot_regular_tree"), \
                    patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                workflow.collect(self.discovery, self.destination, self.output, wave=1,
                    trusted_workflow_sha="a" * 40, **self.common, **self.optional(present))
                for operation in (collect, advance, matrix):
                    self.assert_policy(operation.call_args, present)

    def argv(self, mode):
        paths = {"plan": self.plan, "discovery-root": self.discovery, "state-root": self.state,
                 "destination": self.destination, "repository-root": self.root}
        if mode in ("matrix", "capture", "collect"):
            fields = {"repository-root": self.root, "github-output": self.output}
            if mode == "matrix":
                fields.update({key: paths[key] for key in ("plan", "discovery-root", "state-root")})
            else:
                fields.update(destination=self.destination, **{"trusted-workflow-sha": "a" * 40})
                if mode == "capture":
                    fields.update(plan=self.plan, **{"artifact-id": 71, "artifact-sha256": "sha256:" + "7" * 64})
                else:
                    fields.update(**{"input-root": self.discovery, "wave": 1})
        else:
            fields = dict(paths)
            if mode == "ios-binary":
                fields.update(**{"trusted-workflow-sha": "a" * 40, "expected-build-key": "sha256:" + "b" * 64})
                for lane in ("native-tests", "rust-device", "rust-simulator"):
                    fields[f"{lane}-artifact-id"] = 71
                    fields[f"{lane}-artifact-sha256"] = "sha256:" + "7" * 64
            else:
                fields.update(keyring=self.root / "keys.json", **{"keys-directory": self.root / "keys"})
                if mode != "stage":
                    fields.update(**{"artifact-id": 71, "artifact-sha256": "sha256:" + "7" * 64,
                                     "trusted-workflow-sha": "a" * 40, "expected-build-key": "sha256:" + "b" * 64})
                    fields["component" if mode == "native-prepare" else "phase"] = "rust" if mode == "native-prepare" else "package"
        return ([] if mode == "stage" else [mode]) + [str(value) for key, field in fields.items() for value in ("--" + key, field)]

    def test_all_owned_cli_modes_read_external_canonical_policy_and_preserve_omission(self):
        for mode, action in (("stage", "stage"), ("javascript", "execute_javascript"), ("native-prepare", "prepare_native"),
                             ("ios-binary", "execute_ios_binary"), ("matrix", "matrix"), ("capture", "capture"), ("collect", "collect")):
            for present in (False, True):
                with self.subTest(mode=mode, present=present), patch.object(workflow, action) as called, \
                        patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token"}):
                    self.assertEqual(0, workflow.main(self.argv(mode) + (
                        ["--sdk-apple-validation-policy", str(self.policy_path)] if present else [])))
                    if present:
                        self.assertEqual(self.policy, called.call_args.kwargs["sdk_apple_validation_policy"])
                    else:
                        self.assertNotIn("sdk_apple_validation_policy", called.call_args.kwargs)
                    self.assertIs(os.environ, called.call_args.kwargs["environ"])
                    if mode != "matrix":
                        self.assertEqual("caller-token", called.call_args.kwargs["token"])

    def test_noncanonical_policy_fails_before_any_action_for_each_parser(self):
        for mode, action in (("stage", "stage"), ("ios-binary", "execute_ios_binary"), ("matrix", "matrix")):
            for raw in (b"[]\n", b'{"a":1,"a":2}\n', b'{ "a": 1 }\n'):
                self.policy_path.write_bytes(raw)
                with self.subTest(mode=mode, raw=raw), patch.object(workflow, action) as called, \
                        self.assertRaises(SystemExit) as error:
                    workflow.main(self.argv(mode) + ["--sdk-apple-validation-policy", str(self.policy_path)])
                self.assertEqual(2, error.exception.code)
                called.assert_not_called()
        self.assertFalse(self.destination.exists())
