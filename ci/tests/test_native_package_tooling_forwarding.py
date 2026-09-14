"""Optional caller-policy routing; authentication and execution are explicit seams."""

from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_native_package_execution as fixture_module
from ci.products.inventory import canonical_json_bytes


workflow = fixture_module.workflow
ROOT = Path(__file__).resolve().parents[2]


class NativePackageToolingForwardingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SdkNativePackageExecutionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        root = self.fixture.root
        self.policy = {"evidence": str(root / "caller/evidence"), "publicKey": str(root / "caller/public.pub"),
            "javaExecutable": str(root / "caller/java"), "requiredTrustDomain": "release",
            "keyring": str(root / "caller/keyring.json"), "keysDirectory": str(root / "caller/keys")}

    def test_same_optional_mapping_reaches_all_three_replays_and_is_not_product_data(self):
        fixture = self.fixture
        for supplied in (False, True):
            with self.subTest(supplied=supplied):
                fixture.destination = fixture.root / f"build/policy-{supplied}"
                fixture.events.clear()
                before = deepcopy(self.policy)
                fixture.verified_inputs["sdk"]["sdk_validation_tooling"] = {"evidence": "/untrusted/imported"}
                optional = {"sdk_validation_tooling": self.policy} if supplied else {}
                def forwarded(delegate):
                    def invoke(*args, **kwargs):
                        if supplied:
                            self.assertIs(self.policy, kwargs.pop("sdk_validation_tooling"))
                        else:
                            self.assertNotIn("sdk_validation_tooling", kwargs)
                        return delegate(*args, **kwargs)
                    return invoke
                with patch.object(workflow.sdk_workflow, "verified_inputs", side_effect=forwarded(fixture.verified)) as verified, \
                        patch.object(workflow.product_reuse, "inspect_products", side_effect=forwarded(fixture.inspect)) as inspected, \
                        patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=forwarded(fixture.materialize)) as materialized, \
                        patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload", side_effect=fixture.capture), \
                        patch.object(workflow, "execute_package", side_effect=fixture.worker), \
                        patch.object(workflow, "verify_sdk_package_inputs", side_effect=fixture.gate):
                    result = workflow.execute(fixture.plan_path, fixture.discovery, fixture.state, fixture.destination,
                        **fixture.arguments, **optional)
                for call in (verified, inspected, materialized):
                    call.assert_called_once()
                    if supplied:
                        self.assertIs(self.policy, call.call_args.kwargs["sdk_validation_tooling"])
                    else:
                        self.assertNotIn("sdk_validation_tooling", call.call_args.kwargs)
                self.assertNotIn("sdkValidationTooling", result["receipt"])
                self.assertNotIn("sdk_validation_tooling", result["receipt"])
                self.assertEqual(before, self.policy)
                self.assertEqual(fixture.original_plan_bytes, fixture.plan_path.read_bytes())
                self.assertEqual(["enter", "inspect", "capture", "materialize", "worker", "gate", "exit-check", "exited"], fixture.events)

    def test_cli_canonical_policy_and_absence_preserve_exact_arguments(self):
        cli = fixture_module.SdkNativePackageCliTest()
        cli.setUp()
        policy_path = self.fixture.root / "policy.json"
        policy_path.write_bytes(canonical_json_bytes(self.policy))
        for supplied in (False, True):
            with self.subTest(supplied=supplied), patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token"}, clear=True), \
                    patch.object(workflow, "execute") as execute:
                argv = cli.argv + (["--sdk-validation-tooling", str(policy_path)] if supplied else [])
                self.assertEqual(0, workflow.main(argv))
                execute.assert_called_once_with(**cli.arguments, environ=os.environ, token="caller-token",
                    **({"sdk_validation_tooling": self.policy} if supplied else {}))
        for contents in (b"{", b"[]\n", b'{ "evidence": "value" }\n'):
            with self.subTest(contents=contents), patch.object(workflow, "execute") as execute:
                policy_path.write_bytes(contents)
                with self.assertRaises(SystemExit) as failure:
                    workflow.main(cli.argv + ["--sdk-validation-tooling", str(policy_path)])
                self.assertEqual(2, failure.exception.code)
                execute.assert_not_called()


class NativePackageToolingActionTest(unittest.TestCase):
    def test_action_forwards_local_policy_to_shared_capture_and_both_shell_calls(self):
        action = (ROOT / ".github/actions/sdk-native-package-worker/action.yml").read_text()
        captured = action.split("    - id: captured\n", 1)[1].split("\n    - ", 1)[0]
        self.assertIn("sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}", captured)
        preparation = action.split("    - id: preparation\n", 1)[1].split("\n    - ", 1)[0]
        execution = action.split("    - name: Execute one imported-source package with full admission\n", 1)[1].split("\n    - ", 1)[0]
        with tempfile.TemporaryDirectory(prefix="package-tooling-action-") as temporary:
            root = Path(temporary).resolve()
            binary = root / "bin"
            binary.mkdir()
            stub = binary / "python3"
            stub.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\n')
            stub.chmod(0o700)
            recorded = root / "arguments"
            environment = {"PATH": str(binary), "RECORDED_ARGS": str(recorded), "GITHUB_WORKSPACE": str(root),
                "GITHUB_OUTPUT": str(root / "output"), "PLAN": "original-plan", "DISCOVERY": "original-discovery",
                "STATE": "current-state", "PREPARATION_STATE": "original-preparation", "ARTIFACT_ID": "7",
                "ARTIFACT_SHA256": "sha256:" + "a" * 64, "STATE_WAVE": "0", "SDK_STATE_WAVE": "",
                "COMPONENT": "python", "BUILD_KEY": "sha256:" + "b" * 64, "PREPARATION_COMPONENT": "rust",
                "PREPARATION_BUILD_KEY": "sha256:" + "c" * 64, "PREPARED_ARTIFACT_ID": "8",
                "PREPARED_ARTIFACT_SHA256": "sha256:" + "d" * 64, "SDK_INPUTS_ID": "9",
                "SDK_INPUTS_SHA256": "sha256:" + "e" * 64, "TRUSTED_WORKFLOW_SHA": "f" * 40}
            for block in (preparation, execution):
                self.assertIn("SDK_VALIDATION_TOOLING: ${{ inputs.sdk-validation-tooling }}", block)
                script = textwrap.dedent(block.split("      run: |\n", 1)[1])
                calls = []
                for policy in ("", str(root / "caller policy.json")):
                    with self.subTest(policy=policy, preparation=block is preparation):
                        completed = subprocess.run([shutil.which("bash"), "-c", script],
                            env={**environment, "SDK_VALIDATION_TOOLING": policy}, capture_output=True, text=True)
                        self.assertEqual(0, completed.returncode, completed.stderr)
                        args = recorded.read_bytes().decode().split("\0")[:-1]
                        self.assertEqual(["-B", "-m", "ci.sdk_workflow"], args[:3])
                        self.assertEqual("capture" if block is preparation else "native-package", args[3])
                        if policy:
                            index = args.index("--sdk-validation-tooling")
                            self.assertEqual(policy, args[index + 1])
                            del args[index:index + 2]
                        else:
                            self.assertNotIn("--sdk-validation-tooling", args)
                        calls.append(args)
                self.assertEqual(calls[0], calls[1])


if __name__ == "__main__":
    unittest.main()
