"""SDK final routing over an explicit mocked authenticated inspection boundary.

Fixtures use the real result field names and registered identities, not product
or CI proof. The production inspector retains all original evidence validation.
"""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_completion as completion
from products.inventory import canonical_json_bytes
from products.registry import PHASE_INSTANCE_IDS


def inspected(phases):
    complete = all(row["state"] in {"retained", "reused"} for row in phases)
    return {"result": {"schemaVersion": 1, "result": "complete" if complete else "build-required",
        "fullReuse": complete, "phases": phases, "matrices": {"contract": [], "runtime": [], "sdk": []},
        "continuationRequirements": []}, "readyPlans": []}


def phase(identity, state="retained"):
    done = state in {"retained", "reused"}
    return {"product": identity.product, "component": identity.component, "phase": identity.phase,
        "target": identity.target, "state": state, "buildKey": "sha256:" + "a" * 64 if state != "waiting" else None,
        "receiptSha256": "sha256:" + "b" * 64 if done else None,
        "objectSha256": "sha256:" + "c" * 64 if done else None,
        "source": "stable" if state == "reused" else None, "transportSource": None, "misses": []}


class SdkCompletionTest(unittest.TestCase):
    def setUp(self):
        self.sdk = sorted(identity for identity in PHASE_INSTANCE_IDS if identity.product == "sdk")
        self.paths = (Path("/original/plan"), Path("/original/discovery"), Path("/original/state"))
        self.root = Path("/caller/repository")
        self.environment = {"CALLER": "original environment"}

    def call(self, value, **changes):
        with patch.object(completion.products, "inspect_products", return_value=value) as inspect:
            result = completion.require_sdk_completion(*self.paths, repository_root=self.root,
                environ=self.environment, **changes)
        self.inspect = inspect
        return result

    def test_all_registered_sdk_phases_must_be_retained_or_reused_and_originals_stay_unchanged(self):
        value = inspected([phase(identity, "retained" if index % 2 else "reused") for index, identity in enumerate(self.sdk)])
        original = deepcopy(value)
        self.assertEqual({"complete": True, "phaseCount": len(self.sdk), "fullReuse": True}, self.call(value))
        self.assertEqual(original, value)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root, environ=self.environment)

    def test_every_unresolved_sdk_identity_rejects_even_when_all_worker_matrices_are_empty(self):
        for identity in self.sdk:
            for state in ("build", "waiting"):
                with self.subTest(identity=identity, state=state):
                    value = inspected([phase(identity, state)])
                    with self.assertRaisesRegex(ValueError, "Selected SDK phases remain unresolved") as error:
                        self.call(value)
                    self.assertIn(f"{identity.component}/{identity.phase}/{identity.target}: {state}", str(error.exception))

    def test_other_product_misses_and_zero_sdk_selection_do_not_claim_sdk_production(self):
        other = next(identity for identity in PHASE_INSTANCE_IDS if identity.product == "runtime")
        self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": False}, self.call(inspected([phase(other, "build")])))
        self.assertEqual({"complete": True, "phaseCount": 1, "fullReuse": False}, self.call(inspected([
            phase(other, "waiting"), phase(self.sdk[0])])))
        self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": True}, self.call(inspected([])))

    def test_exact_caller_tooling_is_forwarded_and_replay_error_cannot_be_overridden(self):
        policy = {"synthetic": "caller-owned policy boundary"}
        apple = {"synthetic": "independent caller-owned Apple policy"}
        before = deepcopy(apple)
        self.call(inspected([]), sdk_validation_tooling=policy, sdk_apple_validation_policy=apple)
        self.assertIs(policy, self.inspect.call_args.kwargs["sdk_validation_tooling"])
        self.assertIs(apple, self.inspect.call_args.kwargs["sdk_apple_validation_policy"])
        self.assertEqual(before, apple)
        self.call(inspected([]), sdk_apple_validation_policy=apple)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root,
            environ=self.environment, sdk_apple_validation_policy=apple)
        self.call(inspected([]), sdk_apple_validation_policy=None)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root, environ=self.environment)
        with patch.object(completion.products, "inspect_products", side_effect=ValueError("original evidence rejected")):
            with self.assertRaisesRegex(ValueError, "original evidence rejected"):
                completion.require_sdk_completion(*self.paths, sdk_apple_validation_policy=apple)
        self.call(inspected([]), sdk_apple_validation_policy=apple,
                  sdk_original_workflow_sha="d" * 40)
        self.inspect.assert_called_once_with(*self.paths, repository_root=self.root,
            environ=self.environment, sdk_apple_validation_policy=apple,
            sdk_original_workflow_sha="d" * 40)

    def test_metadata_admissions_are_independent_opaque_caller_objects(self):
        admissions = {name: object() for name in (
            "sdk_facade_metadata_admission", "sdk_android_metadata_admission")}
        for selected in ((), tuple(admissions), *((name,) for name in admissions)):
            with self.subTest(selected=selected):
                optional = {name: value if name in selected else None
                            for name, value in admissions.items()}
                self.assertEqual({"complete": True, "phaseCount": 0, "fullReuse": True},
                                 self.call(inspected([]), **optional))
                for name, value in admissions.items():
                    if name in selected:
                        self.assertIs(value, self.inspect.call_args.kwargs[name])
                    else:
                        self.assertNotIn(name, self.inspect.call_args.kwargs)

    def test_completed_apple_validations_do_not_complete_unresolved_ios_metadata(self):
        validations = sorted(identity for identity in self.sdk
                             if identity.component == "sdk-ios" and identity.phase == "validation")
        self.assertEqual(["ios-arm64", "ios-simulator-arm64"], [identity.target for identity in validations])
        metadata = next(identity for identity in self.sdk
                        if (identity.component, identity.phase, identity.target) == ("sdk-ios", "metadata", "ios"))
        for state in ("build", "waiting"):
            value = inspected([*(phase(identity) for identity in validations), phase(metadata, state)])
            before = deepcopy(value)
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "sdk-ios/metadata/ios: " + state):
                self.call(value, sdk_apple_validation_policy={"synthetic": "caller policy"})
            self.assertEqual(before, value)

    def test_malformed_or_duplicate_inspected_rows_cannot_claim_completion(self):
        row = phase(self.sdk[0])
        for rows in ([row, row], [{**row, "state": "success"}], [{**row, "receiptSha256": None}],
                     [{**row, "phase": "unknown"}], [{**row, "extra": True}],
                     [{key: value for key, value in row.items() if key != "state"}]):
            value = inspected([row])
            value["result"]["phases"] = rows
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.call(value)
        for changes in ({"schemaVersion": True}, {"result": "success"}, {"fullReuse": "true"}):
            value = inspected([])
            value["result"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.call(value)

    def test_cli_canonical_policy_paths_and_output_only_after_success(self):
        with tempfile.TemporaryDirectory(prefix="sdk-completion-cli-") as temporary:
            root = Path(temporary).resolve()
            policy_path, output = root / "policy.json", root / "github-output"
            apple_path = root / "apple-policy.json"
            policy = {"synthetic": "caller policy"}
            apple = {"synthetic": "caller Apple policy"}
            policy_path.write_bytes(canonical_json_bytes(policy))
            apple_path.write_bytes(canonical_json_bytes(apple))
            argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--state-root", str(self.paths[2]), "--repository-root", str(self.root),
                "--sdk-validation-tooling", str(policy_path), "--sdk-apple-validation-policy", str(apple_path),
                "--github-output", str(output)]
            with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 2, "fullReuse": False}) as gate:
                self.assertEqual(0, completion.main(argv))
            gate.assert_called_once_with(*self.paths, repository_root=self.root, environ=os.environ,
                                         sdk_validation_tooling=policy, sdk_apple_validation_policy=apple)
            self.assertEqual("complete=true\nphaseCount=2\nfullReuse=false\n", output.read_text())
            self.assertEqual(canonical_json_bytes(apple), apple_path.read_bytes())
            with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 2, "fullReuse": False}) as gate:
                self.assertEqual(0, completion.main([*argv, "--sdk-original-workflow-sha", "d" * 40]))
            self.assertEqual("d" * 40, gate.call_args.kwargs["sdk_original_workflow_sha"])
            output.unlink()
            with patch.object(completion, "require_sdk_completion", side_effect=ValueError("unresolved")), \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                completion.main(argv)
            self.assertFalse(output.exists())
            for bad in (argv + ["--phase", "metadata"], argv + ["--command", "arbitrary"],
                        argv + ["--repository", str(self.root)]):
                with patch.object(completion, "require_sdk_completion") as gate, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    completion.main(bad)
                gate.assert_not_called()
            for malformed in (b'{"synthetic": "noncanonical"}', b'{"a":1,"a":2}\n'):
                apple_path.write_bytes(malformed)
                with patch.object(completion, "require_sdk_completion") as gate, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit):
                    completion.main(argv)
                gate.assert_not_called()
                self.assertFalse(output.exists())

    def test_cli_omitted_policy_preserves_legacy_shape_and_prints_concise_summary(self):
        argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]), "--repository-root", str(self.root)]
        stdout = io.StringIO()
        with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 0, "fullReuse": True}) as gate, redirect_stdout(stdout):
            self.assertEqual(0, completion.main(argv))
        gate.assert_called_once_with(*self.paths[:2], None, repository_root=self.root, environ=os.environ)
        self.assertEqual('{"complete":true,"fullReuse":true,"phaseCount":0}\n', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
