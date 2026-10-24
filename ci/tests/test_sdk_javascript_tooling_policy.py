"""Caller-policy routing only; original authentication and execution are seams."""

from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_javascript_workflow as fixture_module
from ci.products.inventory import canonical_json_bytes


workflow = fixture_module.workflow


class SdkJavascriptToolingPolicyTest(unittest.TestCase):
    def setUp(self):
        # Reuse setup/helpers, not inherited tests or a second synthetic model.
        self.fixture = fixture_module.SdkJavascriptWorkflowTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        root = self.fixture.root
        self.policy = {"evidence": str(root / "caller/evidence"), "publicKey": str(root / "caller/public.pub"),
            "javaExecutable": str(root / "caller/java"), "requiredTrustDomain": "release",
            "keyring": str(root / "caller/keyring.json"), "keysDirectory": str(root / "caller/keys")}
        self.policy_path = root / "tooling-policy.json"
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))

    def argv(self):
        fixture = self.fixture
        fields = {"plan": fixture.plan, "discovery-root": fixture.discovery, "state-root": fixture.state,
            "destination": fixture.destination, "repository-root": fixture.repository,
            "keyring": fixture.arguments["keyring"], "keys-directory": fixture.arguments["keys_directory"]}
        fields.update({name.replace("_", "-"): fixture.arguments[name] for name in
            ("expected_build_key", "artifact_id", "artifact_sha256", "trusted_workflow_sha")})
        return ["javascript", "--phase", "package",
                *(value for key, item in fields.items() for value in ("--" + key, str(item)))]

    def test_cli_reads_canonical_caller_policy_and_omission_preserves_legacy_arguments(self):
        for supplied in (False, True):
            with self.subTest(supplied=supplied), patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token"}, clear=True), \
                    patch.object(workflow, "execute_javascript") as execute:
                argv = self.argv() + (["--sdk-validation-tooling", str(self.policy_path)] if supplied else [])
                self.assertEqual(0, workflow.main(argv))
                execute.assert_called_once()
                self.assertEqual((self.fixture.plan, self.fixture.discovery, self.fixture.state,
                                  self.fixture.destination), execute.call_args.args)
                expected = {**self.fixture.arguments, "phase": "package", "environ": os.environ,
                            "token": "caller-token"}
                if supplied:
                    expected["sdk_validation_tooling"] = self.policy
                self.assertEqual(expected, execute.call_args.kwargs)

    def test_cli_rejects_malformed_noncanonical_or_nonobject_policy_before_controller(self):
        for raw in (b"{", b"[]\n", b'{ "evidence": "untrusted" }\n', b'{"a":1,"a":2}\n'):
            with self.subTest(raw=raw), patch.object(workflow, "execute_javascript") as execute:
                self.policy_path.write_bytes(raw)
                with self.assertRaises(SystemExit) as error:
                    workflow.main(self.argv() + ["--sdk-validation-tooling", str(self.policy_path)])
                self.assertEqual(2, error.exception.code)
                execute.assert_not_called()

    def test_controller_forwards_same_policy_to_both_replays_without_importing_embedded_authority(self):
        fixture = self.fixture
        embedded = {"evidence": "/untrusted/imported-policy"}
        fixture.inputs["sdk"]["sdk_validation_tooling"] = embedded
        for phase in ("package", "validation"):
            for supplied in (False, True):
                with self.subTest(phase=phase, supplied=supplied):
                    fixture.destination = fixture.repository / f"build/{phase}-{supplied}"
                    fixture.events.clear()
                    before = deepcopy(self.policy)
                    optional = {"sdk_validation_tooling": self.policy} if supplied else {}

                    def materialize(*args, **kwargs):
                        if supplied:
                            self.assertIs(self.policy, kwargs.pop("sdk_validation_tooling"))
                        else:
                            self.assertNotIn("sdk_validation_tooling", kwargs)
                        return fixture.materialize(*args, **kwargs)

                    with patch.object(workflow, "verified_inputs", side_effect=fixture.verified) as verified, \
                            patch.object(workflow.product_reuse, "materialize_product_predecessors", side_effect=materialize) as restored, \
                            patch.object(fixture_module.worker, "execute", side_effect=fixture.execute), \
                            patch.object(workflow.product_reuse, "finalize_phase_object", side_effect=fixture.finalize):
                        workflow.execute_javascript(fixture.plan, fixture.discovery, fixture.state, fixture.destination,
                            phase=phase, **fixture.arguments, **optional)
                    verified.assert_called_once()
                    restored.assert_called_once()
                    for call in (verified.call_args, restored.call_args):
                        if supplied:
                            self.assertIs(self.policy, call.kwargs["sdk_validation_tooling"])
                        else:
                            self.assertNotIn("sdk_validation_tooling", call.kwargs)
                    self.assertEqual(before, self.policy)
                    self.assertIs(embedded, fixture.inputs["sdk"]["sdk_validation_tooling"])
                    self.assertEqual(["enter", "materialize", "worker", "exit-check", "exited", "finalize"], fixture.events)


if __name__ == "__main__":
    unittest.main()
