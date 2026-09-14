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
        self.assertEqual({"complete": True, "phaseCount": len(self.sdk)}, self.call(value))
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
        self.assertEqual({"complete": True, "phaseCount": 0}, self.call(inspected([phase(other, "build")])))
        self.assertEqual({"complete": True, "phaseCount": 1}, self.call(inspected([
            phase(other, "waiting"), phase(self.sdk[0])])))
        self.assertEqual({"complete": True, "phaseCount": 0}, self.call(inspected([])))

    def test_exact_caller_tooling_is_forwarded_and_replay_error_cannot_be_overridden(self):
        policy = {"synthetic": "caller-owned policy boundary"}
        self.call(inspected([]), sdk_validation_tooling=policy)
        self.assertIs(policy, self.inspect.call_args.kwargs["sdk_validation_tooling"])
        with patch.object(completion.products, "inspect_products", side_effect=ValueError("original evidence rejected")):
            with self.assertRaisesRegex(ValueError, "original evidence rejected"):
                completion.require_sdk_completion(*self.paths)

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
            policy = {"synthetic": "caller policy"}
            policy_path.write_bytes(canonical_json_bytes(policy))
            argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]),
                "--state-root", str(self.paths[2]), "--repository-root", str(self.root),
                "--sdk-validation-tooling", str(policy_path), "--github-output", str(output)]
            with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 2}) as gate:
                self.assertEqual(0, completion.main(argv))
            gate.assert_called_once_with(*self.paths, repository_root=self.root, environ=os.environ, sdk_validation_tooling=policy)
            self.assertEqual("complete=true\nphaseCount=2\n", output.read_text())
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

    def test_cli_omitted_policy_preserves_legacy_shape_and_prints_concise_summary(self):
        argv = ["--plan", str(self.paths[0]), "--discovery-root", str(self.paths[1]), "--repository-root", str(self.root)]
        stdout = io.StringIO()
        with patch.object(completion, "require_sdk_completion", return_value={"complete": True, "phaseCount": 0}) as gate, redirect_stdout(stdout):
            self.assertEqual(0, completion.main(argv))
        gate.assert_called_once_with(*self.paths[:2], None, repository_root=self.root, environ=os.environ)
        self.assertEqual('{"complete":true,"phaseCount":0}\n', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
