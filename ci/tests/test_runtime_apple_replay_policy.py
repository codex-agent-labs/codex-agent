"""Caller forwarding stops at replay; no product execution or proof is mocked true."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse as adapter
from products.inventory import write_canonical_json


class RuntimeAppleReplayPolicyTest(unittest.TestCase):
    def test_all_runtime_state_consumers_forward_only_explicit_policy_before_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            plan, discovery, destination = (root / name for name in ("plan", "discovery", "output"))
            discovery.mkdir()
            (root / "variants").mkdir()
            identity = adapter.PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
            key = "sha256:" + "a" * 64
            policy = {"fixture": "caller-only policy"}
            calls = (
                (adapter.runtime_worker_matrix, (plan, discovery), {}),
                (adapter.prepare_runtime_phase, (plan, discovery, None, identity, destination), {"expected_build_key": key}),
                (adapter.execute_runtime_phase, (plan, discovery, None, identity, destination), {"expected_build_key": key}),
                (adapter.execute_runtime_supervisor, (plan, discovery, None, destination), {"expected_build_key": key}),
                (adapter.execute_runtime_aggregate, (plan, discovery, None, destination),
                 {"expected_build_key": key, "variant_trust_root": root / "variants"}),
                (adapter.materialize_runtime_attestation_inputs, (plan, discovery, None, destination),
                 {"expected_build_key": key, "target": "linux-x64"}),
                (adapter.materialize_runtime_aggregate_release_evidence, (plan, discovery, None, destination),
                 {"expected_build_key": key, "keyring": root / "keys.json", "keys_directory": root / "keys"}),
            )
            for operation, args, options in calls:
                for present in (False, True):
                    with self.subTest(operation=operation.__name__, present=present), patch.object(
                            adapter, "_verified_product_state", side_effect=ValueError("stop at replay")) as replay:
                        with self.assertRaisesRegex(ValueError, "stop at replay"):
                            operation(*args, **options, repository_root=root, environ={},
                                **({"sdk_apple_validation_policy": policy} if present else {}))
                        replay.assert_called_once()
                        if present:
                            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
                        else:
                            self.assertNotIn("sdk_apple_validation_policy", replay.call_args.kwargs)
                        self.assertFalse(destination.exists())

    def test_runtime_cli_passes_external_policy_and_preserves_omitted_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy = {"fixture": "explicit caller"}
            path = root / "policy.json"
            write_canonical_json(path, policy)
            base = ["--plan", str(root / "plan"), "--discovery-root", str(root / "discovery")]
            commands = (
                ("runtime-worker-matrix", "runtime_worker_matrix", ["--github-output", str(root / "outputs")], {"include": []}),
                ("execute-runtime-supervisor", "execute_runtime_supervisor", ["--destination", str(root / "out"), "--expected-build-key", "key"], {}),
                ("execute-runtime-aggregate", "execute_runtime_aggregate", ["--destination", str(root / "out"), "--expected-build-key", "key", "--variant-trust-root", str(root / "variants")], {}),
                *((name, name.replace("-", "_"), ["--destination", str(root / "out"), "--expected-build-key", "key",
                    "--product", "runtime", "--component", "linux-x64", "--phase", "binary", "--target", "linux-x64"], {})
                  for name in ("prepare-runtime-phase", "execute-runtime-phase", "materialize-product-predecessors")),
            )
            for command, function, flags, result in commands:
                for present in (False, True):
                    with self.subTest(command=command, present=present), patch.object(adapter, function, return_value=result) as invoke:
                        self.assertEqual(0, adapter.main([command, *base, *flags,
                            *(["--sdk-apple-validation-policy", str(path)] if present else [])]))
                        if present:
                            self.assertEqual(policy, invoke.call_args.kwargs["sdk_apple_validation_policy"])
                        else:
                            self.assertNotIn("sdk_apple_validation_policy", invoke.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
