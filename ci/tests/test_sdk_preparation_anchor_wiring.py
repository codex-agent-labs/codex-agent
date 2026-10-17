"""Registered anchor routing with explicit election/content/process seams.

Original receipt inventories are real fixture bytes; these tests do not prove
SDK semantics, elected-source authority, hosted execution or preparation trust.
"""

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests import test_sdk_native_prepare_workflow as preparation_fixture
from ci.tests import test_sdk_native_validation_worker_action as validation_fixture
from ci.tests.product_chain_support import write_receipt
from products.inventory import canonical_json_bytes, snapshot_regular_tree, write_canonical_json
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS
import sdk_native_prepare as worker
import sdk_native_validation_workflow as validation


ROOT = Path(__file__).resolve().parents[2]
ANCHORS = (("validation", "linux-x64"), ("validation", "macos-arm64"), ("metadata", "desktop"))


class SdkPreparationAnchorWiringTest(unittest.TestCase):
    def fixture(self):
        fixture = preparation_fixture.SdkNativePrepareWorkflowTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        return fixture

    def test_registered_anchor_plan_reaches_leaf_and_original_upload_unchanged(self):
        for phase, target in ANCHORS:
            with self.subTest(phase=phase, target=target):
                f = self.fixture()
                identity = PhaseInstanceId("sdk", "python", phase, target)
                self.assertTrue(workflow.product_reuse._sdk_family_worker_instance(identity, "native-" + phase))
                receipt = write_receipt(f.root / "anchor.json", product="sdk", component="python",
                    phase=phase, target=target, version="0.3.0", version_identity="0.3.0",
                    outputs=f.ready["outputs"] if "outputs" in f.ready else f.contract["receipt"]["outputs"],
                    upstream=[], context={"producer": f.producer})
                f.ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
                f.arguments["expected_build_key"] = f.ready["buildKey"]
                f.selection["consumers"] = [{"product": "sdk", "component": "python", "phase": phase, "target": target}]

                def materialize(plan, discovery, state, actual, destination, **kwargs):
                    self.assertEqual(identity, actual)
                    self.assertTrue(f.live)
                    self.assertEqual(f.ready["buildKey"], kwargs["expected_build_key"])
                    for original, value in {**f.original_paths, preparation_fixture.CONTRACT: f.contract}.items():
                        directory = destination / f.name(original)
                        snapshot_regular_tree(value["stage"], directory / "stage")
                        (directory / "phase-receipt.json").write_bytes(value["receiptPath"].read_bytes())
                    write_canonical_json(destination / "producer.json", f.producer)
                    write_canonical_json(destination / "phase-plan.json", f.ready)
                    return f.ready

                with patch.object(workflow, "verified_inputs", side_effect=f.verified), \
                        patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=materialize), \
                        patch.object(worker, "execute", side_effect=f.prepare) as leaf:
                    workflow.prepare_native(f.plan_path, f.discovery, f.state, f.destination,
                        **f.arguments, preparation_phase=phase, preparation_target=target)
                self.assertIs(f.ready, leaf.call_args.args[0])
                self.assertEqual(canonical_json_bytes(f.ready),
                    (f.destination / "upload/original-plan/phase-plan.json").read_bytes())
                self.assertFalse((f.destination / "shard").exists())

    def test_invalid_anchor_rejects_before_authenticated_input_or_materialization(self):
        f = self.fixture()
        for phase, target in (("validation", "desktop"), ("metadata", "linux-x64"), ("package", "macos-arm64"), ("binary", "desktop")):
            with self.subTest(phase=phase, target=target), patch.object(workflow, "verified_inputs") as inputs, \
                    patch.object(workflow.product_reuse, "materialize_product_predecessors") as materialize:
                with self.assertRaises(ValueError):
                    workflow.prepare_native(f.plan_path, f.discovery, f.state, f.destination,
                        **f.arguments, preparation_phase=phase, preparation_target=target)
                inputs.assert_not_called()
                materialize.assert_not_called()
                self.assertFalse(f.destination.exists())

    def test_prepare_cli_forwards_anchor_without_relabeling(self):
        argv = ["native-prepare"]
        for name in ("plan", "discovery-root", "state-root", "destination", "keyring", "keys-directory", "repository-root"):
            argv += ["--" + name, "/caller/" + name]
        argv += ["--component", "python", "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
                 "--trusted-workflow-sha", "b" * 40, "--expected-build-key", "sha256:" + "c" * 64]
        for phase, target in ANCHORS:
            with self.subTest(phase=phase, target=target), patch.object(workflow, "prepare_native") as prepare:
                self.assertEqual(0, workflow.main(argv + ["--preparation-phase", phase, "--preparation-target", target]))
                self.assertEqual((phase, target), (prepare.call_args.kwargs["preparation_phase"], prepare.call_args.kwargs["preparation_target"]))
        with patch.object(workflow, "prepare_native") as prepare, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            workflow.main(argv + ["--preparation-phase", "binary"])
        prepare.assert_not_called()

    def test_prepare_identity_runs_in_fresh_python_without_imported_fixture_bootstrap(self):
        action = (ROOT / ".github/actions/sdk-native-prepare/action.yml").read_text()
        block = action.split("    - id: identity\n", 1)[1].split("\n    - ", 1)[0]
        code = textwrap.dedent(block.split("<<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        with tempfile.TemporaryDirectory(prefix="native-anchor-action-") as temporary:
            plan = Path(temporary) / "plan.json"
            plan.write_text(json.dumps({"validationTree": "a" * 40}))
            for phase, target in ANCHORS + (("validation", "desktop"), ("metadata", "linux-x64")):
                with self.subTest(phase=phase, target=target):
                    row = {"product": "sdk", "component": "python", "phase": phase, "target": target,
                           "buildKey": "sha256:" + "b" * 64, "runnerOs": "macOS" if target == "macos-arm64" else "Linux",
                           "runnerArch": "ARM64" if target == "macos-arm64" else "X64"}
                    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
                    env.update(PLAN=str(plan), MATRIX=json.dumps({"include": [row]}), COMPONENT="python",
                               PREPARATION_PHASE=phase, PREPARATION_TARGET=target, BUILD_KEY=row["buildKey"], TREE="a" * 40)
                    result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)
                    if (phase, target) in ANCHORS:
                        self.assertEqual(0, result.returncode, result.stderr)
                    else:
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn("Invalid native preparation consumer identity", result.stderr)

    def test_validation_action_and_cli_preserve_original_anchor(self):
        f = validation_fixture.SdkNativeValidationWorkerActionTest(methodName="runTest")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.assertIn('--family "native-$PREPARATION_PHASE"', f.block("preparation"))
        for phase, target in ANCHORS:
            with self.subTest(phase=phase, target=target):
                f.environment.update(PREPARATION_PHASE=phase, PREPARATION_TARGET=target)
                f.preparation.update(phase=phase, target=target,
                    runnerOs="macOS" if target == "macos-arm64" else "Linux",
                    runnerArch="ARM64" if target == "macos-arm64" else "X64")
                f.matrices()
                with patch.object(validation_fixture.native_wrappers, "host_classifier", return_value="linux-x64"):
                    f.execute("identity")
                with patch("subprocess.run") as process:
                    f.execute("execute")
                command = process.call_args.args[0]
                with patch.object(validation, "execute") as execute:
                    self.assertEqual(0, validation.main(command[5:]))
                self.assertEqual((phase, target), (execute.call_args.kwargs["preparation_phase"], execute.call_args.kwargs["preparation_target"]))


if __name__ == "__main__":
    unittest.main()
