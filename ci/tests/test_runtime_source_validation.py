from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import importlib.util

source = Path(__file__).resolve().parents[2] / ".github/actions/run-ci-lane/runtime_source_validation.py"
spec = importlib.util.spec_from_file_location("runtime_source_validation", source)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class RetainedSourceValidationTest(unittest.TestCase):
    def test_discovery_rejects_empty_duplicate_and_malformed_selection(self):
        self.assertEqual(["example.One.a", "example.Two.b"],
            subject._native_listing(b"example.One.\n  a\nexample.Two.\n  b\n"))
        for raw in (b"", b"example.One.\n  a\n  a\n", b"  a\n", b"example.One.\n --filter=x\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                subject._native_listing(raw)

    def test_current_source_inventory_rejects_added_or_changed_test_inputs(self):
        row = {"relativePath": subject._SOURCE + "nativeTest/kotlin/Test.kt", "bytes": 1, "sha256": "sha256:" + "a" * 64}
        receipt = {"inputs": {"inventory": [row]}}
        with patch.object(subject, "git_inventory", return_value="tree"), \
                patch.object(subject, "git_inventory_paths", return_value={row["relativePath"]}), \
                patch.object(subject, "git_file_inventory", return_value=[row]):
            self.assertEqual([row], subject._source_inventory(receipt, Path("."), "a" * 40))
            with patch.object(subject, "git_file_inventory", return_value=[{**row, "bytes": 2}]), self.assertRaises(ValueError):
                subject._source_inventory(receipt, Path("."), "a" * 40)
            with patch.object(subject, "git_inventory_paths", return_value={row["relativePath"], "extra"}), self.assertRaises(ValueError):
                subject._source_inventory(receipt, Path("."), "a" * 40)

    def test_wasm_and_unverified_state_fail_before_materialization(self):
        for target in ("node-wasm", "linux-x64"):
            with patch.object(subject, "_copy_outputs") as copy, self.assertRaises(ValueError):
                subject.run_retained_native_tests(None, target=target,
                    plan_path=Path("unused"), repository_root=Path("."), environ={}, trusted_workflow_sha="a" * 40)
            copy.assert_not_called()

    def test_full_native_invocation_and_late_failure_never_return_success(self):
        for mutate in (False, True):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                plan = {"validationCommit": "a" * 40, "validationTree": "b" * 40,
                        "lanes": {"desktop-linux-x64": {"test": True}}}
                plan_path = root / "plan.json"
                plan_path.write_bytes(subject.canonical_json_bytes(plan))
                producer = {"commit": "a" * 40, "tree": "b" * 40}
                identities = [subject.PhaseInstanceId("runtime", "linux-x64", phase, "linux-x64") for phase in ("binary", "package")]
                records = {i: {**dict(zip(subject._FIELDS[:4], (i.product, i.component, i.phase, i.target))),
                    **{k: "sha256:" + "c" * 64 for k in subject._FIELDS[4:]}, "state": "retained"} for i in identities}
                state = subject.products._VerifiedProductState(plan=plan, producer=producer,
                    consumer={"kind": "ci", "producer": producer}, requested=(), closure=(), expected_fixed={},
                    rebased_request={}, prior={}, prior_by_instance=records, sources={}, prior_carrier_phases=records.copy(),
                    prior_ready_plans={}, completed_frozen=object.__new__(subject.CompletedFrozenReuse))
                runner = {"kind": "validation-runner", "relativePath": "outputs/validation-runner/test.kexe", "bytes": 1, "sha256": "sha256:" + "d" * 64}
                envelope = {"receipt": {"outputs": [runner]}}
                calls, private_inputs = [], []

                def copy(_state, _instance, kinds, destination, _stack, _workflow, _token):
                    self.assertEqual(("app-server", "validation-runner"), kinds)
                    p = destination / runner["relativePath"]
                    p.parent.mkdir(parents=True); p.write_bytes(b"x")
                    (destination / "outputs/app-server").mkdir()
                    private_inputs.append(p)
                    return envelope, {"validation-runner": runner, "app-server": {}}

                def run(command, **kwargs):
                    calls.append(command)
                    self.assertEqual(kwargs["env"]["TMPDIR"], kwargs["env"]["TEMP"])
                    self.assertEqual(Path(kwargs["env"]["TMP"]), Path(kwargs["cwd"]) / "tmp")
                    kwargs["stdout"].write(b"example.Full.\n  first\n  second\n" if "--ktest_list_tests" in command
                        else b"[  PASSED  ] 2 tests.\n")
                    if mutate and "--ktest_logger=GTEST" in command:
                        private_inputs[0].write_bytes(b"changed")
                    return SimpleNamespace(returncode=0)

                env = {"RUNNER_OS": "Linux", "RUNNER_ARCH": "X64", "CI_VALIDATION_COMMIT": "a" * 40, "CI_VALIDATION_TREE": "b" * 40}
                with patch.object(subject.CompletedFrozenReuse, "check_consumer"), \
                     patch.object(subject.CompletedFrozenReuse, "envelope", return_value=envelope), \
                     patch.object(subject.products, "_consumer", return_value=state.consumer), \
                     patch.object(subject.products, "_runtime_worker_checkout"), \
                     patch.object(subject.products, "_worker_process_environment", return_value=env.copy()), \
                     patch.object(subject, "host_classifier", return_value="linux-x64"), \
                     patch.object(subject, "_source_inventory", return_value=[]), \
                     patch.object(subject, "_copy_outputs", side_effect=copy) as copied, \
                     patch.object(subject.subprocess, "run", side_effect=run):
                    args = dict(target="linux-x64", plan_path=plan_path,
                                repository_root=root, environ=env, trusted_workflow_sha="e" * 40)
                    if mutate:
                        with self.assertRaisesRegex(ValueError, "input changed"):
                            subject.run_retained_native_tests(state, **args)
                        self.assertEqual(b"[  PASSED  ] 2 tests.\n", (root / "build/ci/retained-source-tests/native-linux-x64/failure.log").read_bytes())
                    else:
                        result = subject.run_retained_native_tests(state, **args)
                        self.assertEqual({"retained-source-tests.json", "discovery.log", "execution.log"}, set(result))
                    self.assertEqual(1, copied.call_count)
                self.assertEqual(["--ktest_list_tests", "--ktest_logger=GTEST"], [c[1] for c in calls])
                self.assertTrue(all(len(c) == 2 and "filter" not in c[1] for c in calls))
                self.assertFalse(private_inputs[0].exists())


if __name__ == "__main__":
    unittest.main()
