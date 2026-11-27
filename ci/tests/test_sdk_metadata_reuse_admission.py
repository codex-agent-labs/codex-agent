"""Resolution orchestration; mocked envelopes do not prove product admission."""

from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci.products import reuse
from ci.products.registry import PhaseInstanceId


class MetadataReuseAdmissionTest(unittest.TestCase):
    def run_route(self, component, route, admission=None, *, phase="metadata"):
        target = "common" if component == "sdk-core" else "android"
        identity = PhaseInstanceId("sdk", component, phase, target)
        envelope = {"receipt": {}, "receiptSha256": "sha256:" + "1" * 64,
                    "objectSha256": "sha256:" + "2" * 64}
        session = reuse.LookupSession(repository="codex-agent-labs/codex-agent", pull_request=7)
        options = {} if admission is None else {
            ("sdk_facade_metadata_admission" if component == "sdk-core"
             else "sdk_android_metadata_admission"): admission}
        self.consumer = Mock()
        with ExitStack() as stack:
            for name, value in (
                    ("_dependency_closure", (identity,)), ("phase_instance_dependencies", ()),
                    ("required_contract_components", ()), ("runtime_validation_dependencies", ()),
                    ("native_runtime_validation_dependencies", ()), ("sdk_validation_dependencies", ()),
                    ("_validate_envelope", (identity, envelope)),
                    ("verify_build_key_output_consistency", None),
                    ("_plan", {"buildKey": "sha256:" + "3" * 64})):
                stack.enter_context(patch.object(reuse, name, return_value=value))
            self.lookup = stack.enter_context(patch.object(session, "lookup", return_value=SimpleNamespace(
                envelope=envelope, reason=None, transport_source=None)))
            return reuse.advance_reuse((identity,), {identity: {}},
                (envelope,) if route == "retained" else (), session,
                build_plan_consumer=self.consumer, **options)

    def test_retained_and_lookup_require_full_concrete_admission(self):
        for component in ("sdk-core", "sdk-android"):
            for route in ("retained", "lookup"):
                with self.subTest(component=component, route=route), self.assertRaisesRegex(
                        ValueError, "metadata reuse lacks authenticated original evidence"):
                    self.run_route(component, route)
                self.consumer.assert_not_called()

    def test_both_routes_propagate_replay_failure_without_build_fallback(self):
        for component, cls in (("sdk-core", reuse.FacadeMetadataAdmission),
                               ("sdk-android", reuse.AndroidMetadataAdmission)):
            admission = object.__new__(cls)
            for route in ("retained", "lookup"):
                with self.subTest(component=component, route=route), patch.object(
                        cls, "verify_metadata", side_effect=ValueError("full replay rejected")) as gate, \
                        self.assertRaisesRegex(ValueError, "full replay rejected"):
                    self.run_route(component, route, admission)
                gate.assert_called_once()
                self.consumer.assert_not_called()

    def test_resolution_preserves_original_only_after_full_gate(self):
        for component, cls in (("sdk-core", reuse.FacadeMetadataAdmission),
                               ("sdk-android", reuse.AndroidMetadataAdmission)):
            admission = object.__new__(cls)
            for route in ("retained", "lookup"):
                with self.subTest(component=component, route=route), patch.object(
                        cls, "verify_metadata", autospec=True) as gate:
                    result, originals = self.run_route(component, route, admission)
                gate.assert_called_once_with(admission, originals[0], ())
                self.assertTrue(result["fullReuse"])
                self.assertEqual("retained" if route == "retained" else "reused",
                                 result["phases"][0]["state"])
                self.consumer.assert_not_called()
                # Concrete family tests separately reject this empty predecessor
                # tuple; this fixture isolates the orchestration transition.

    def test_callbacks_or_duck_types_cannot_replace_concrete_admission(self):
        for component in ("sdk-core", "sdk-android"):
            for provider in (Mock(), SimpleNamespace(verify_metadata=Mock())):
                with self.subTest(component=component), self.assertRaisesRegex(
                        ValueError, "concrete full verifier"):
                    self.run_route(component, "retained", provider)

    def test_package_resolution_does_not_require_metadata_gate(self):
        for component in ("sdk-core", "sdk-android"):
            result, _ = self.run_route(component, "retained", phase="package")
            self.assertTrue(result["fullReuse"])


if __name__ == "__main__":
    unittest.main()
