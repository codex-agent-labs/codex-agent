"""Reuse orchestration only: mocked plans/envelopes do not prove Apple admission."""

from contextlib import ExitStack
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ci.products import reuse
from ci.products.registry import PhaseInstanceId


class AppleReuseAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.identity = PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
        self.envelope = {
            "receipt": {"synthetic": "already validated envelope seam"},
            "receiptSha256": "sha256:" + "1" * 64,
            "objectSha256": "sha256:" + "2" * 64,
        }
        self.plan = {"buildKey": "sha256:" + "3" * 64}
        self.transport = {"synthetic": "already authenticated lookup seam"}
        self.admission = object.__new__(reuse.AppleValidationAdmission)
        self.package_admission = object.__new__(reuse.ApplePackageAdmission)

    def run_route(self, route, admission=None, package_admission=None, package_factory=None):
        # A real session is required by the public API. Only its lookup is
        # replaced: these tests isolate the transition into resolved state,
        # not catalog authentication, dependency planning or receipt parsing.
        session = reuse.LookupSession(repository="codex-agent-labs/codex-agent", pull_request=7)

        def plan(*_args):
            self.events.append("plan")
            return self.plan

        def lookup(source, selected):
            self.assertEqual(reuse.SOURCES[0], source)
            self.assertIs(self.plan, selected)
            self.events.append("lookup")
            return SimpleNamespace(envelope=self.envelope, reason=None, transport_source=self.transport)

        with ExitStack() as stack:
            for name, options in (
                ("_dependency_closure", {"return_value": (self.identity,)}),
                ("phase_instance_dependencies", {"return_value": ()}),
                ("required_contract_components", {"return_value": ()}),
                ("runtime_validation_dependencies", {"return_value": ()}),
                ("native_runtime_validation_dependencies", {"return_value": ()}),
                ("sdk_validation_dependencies", {"return_value": ()}),
                ("_validate_envelope", {"return_value": (self.identity, self.envelope)}),
                ("verify_build_key_output_consistency", {}),
            ):
                stack.enter_context(patch.object(reuse, name, **options))
            self.planning = stack.enter_context(patch.object(reuse, "_plan", side_effect=plan))
            self.lookup = stack.enter_context(patch.object(session, "lookup", side_effect=lookup))
            self.build_consumer = Mock()
            options = {} if admission is None else {"sdk_apple_validation_admission": admission}
            if package_admission is not None:
                options["sdk_apple_package_admission"] = package_admission
            if package_factory is not None:
                options["sdk_apple_package_admission_factory"] = package_factory
            result = reuse.advance_reuse(
                (self.identity,), {self.identity: {}},
                (self.envelope,) if route == "retained" else (), session,
                build_plan_consumer=self.build_consumer, **options,
            )
            self.events.append("returned")
            return result

    def test_both_routes_require_admission_before_returning_resolution(self):
        for route in ("retained", "lookup"):
            self.events.clear()
            with self.subTest(route=route), patch.object(reuse.AppleValidationAdmission, "verify") as verify, \
                    self.assertRaisesRegex(ValueError, "lacks authenticated original evidence"):
                self.run_route(route)
            verify.assert_not_called()
            self.build_consumer.assert_not_called()
            self.assertNotIn("returned", self.events)
            self.assertEqual(0 if route == "retained" else 1, self.lookup.call_count)

    def test_both_routes_propagate_full_verifier_rejection_without_fallback(self):
        for route in ("retained", "lookup"):
            self.events.clear()
            with self.subTest(route=route), patch.object(reuse.AppleValidationAdmission, "verify",
                    autospec=True, side_effect=ValueError("full Apple replay rejected")) as verify, \
                    self.assertRaisesRegex(ValueError, "full Apple replay rejected"):
                self.run_route(route, self.admission)
            verify.assert_called_once_with(self.admission, self.envelope)
            self.build_consumer.assert_not_called()
            self.assertNotIn("returned", self.events)
            self.assertEqual(0 if route == "retained" else 1, self.lookup.call_count)

    def test_both_targets_and_routes_resolve_only_after_concrete_verifier_call(self):
        def verify(admission, envelope):
            self.assertIs(self.admission, admission)
            self.assertIs(self.envelope, envelope)
            self.events.append("verify")

        for target in ("ios-arm64", "ios-simulator-arm64"):
            self.identity = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
            for route in ("retained", "lookup"):
                self.events.clear()
                with self.subTest(target=target, route=route), patch.object(
                        reuse.AppleValidationAdmission, "verify", autospec=True, side_effect=verify) as gate:
                    result, originals = self.run_route(route, self.admission)
                gate.assert_called_once_with(self.admission, self.envelope)
                self.assertEqual(["plan", *(["lookup"] if route == "lookup" else []), "verify", "returned"], self.events)
                self.assertTrue(result["fullReuse"])
                self.assertEqual("complete", result["result"])
                self.assertEqual("retained" if route == "retained" else "reused", result["phases"][0]["state"])
                self.assertEqual(self.envelope["receiptSha256"], result["phases"][0]["receiptSha256"])
                self.assertEqual((self.envelope,), originals)
                self.assertIs(self.envelope, originals[0])
                self.build_consumer.assert_not_called()

    def test_arbitrary_callback_or_duck_typed_provider_cannot_replace_admission(self):
        for provider in (Mock(), SimpleNamespace(verify=Mock())):
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, "concrete full verifier"):
                self.run_route("retained", provider)
            self.planning.assert_not_called()
            self.lookup.assert_not_called()
            if isinstance(provider, Mock):
                provider.assert_not_called()
            else:
                provider.verify.assert_not_called()

    def test_package_reuse_requires_concrete_full_original_admission(self):
        self.identity = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        for route in ("retained", "lookup"):
            with self.subTest(route=route), patch.object(reuse.ApplePackageAdmission, "verify") as verify, \
                    self.assertRaisesRegex(ValueError, "package reuse lacks authenticated original evidence"):
                self.run_route(route)
            verify.assert_not_called()
            with self.subTest(route=route), patch.object(reuse.ApplePackageAdmission, "verify",
                    autospec=True, side_effect=ValueError("original package replay failed")) as verify, \
                    self.assertRaisesRegex(ValueError, "original package replay failed"):
                self.run_route(route, package_admission=self.package_admission)
            verify.assert_called_once_with(self.package_admission, self.envelope)
            with patch.object(reuse.ApplePackageAdmission, "verify", autospec=True) as verify:
                result, originals = self.run_route(route, package_admission=self.package_admission)
            verify.assert_called_once_with(self.package_admission, self.envelope)
            self.assertTrue(result["fullReuse"])
            self.assertEqual((self.envelope,), originals)

    def test_package_factory_runs_only_after_selected_envelope_and_must_return_full_verifier(self):
        self.identity = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        for route in ("retained", "lookup"):
            self.events.clear()
            def factory(envelope):
                self.assertIs(self.envelope, envelope)
                self.events.append("factory")
                return self.package_admission
            with self.subTest(route=route), patch.object(
                    reuse.ApplePackageAdmission, "verify", autospec=True) as verify:
                result, _ = self.run_route(route, package_factory=factory)
            verify.assert_called_once_with(self.package_admission, self.envelope)
            self.assertEqual(["plan", *(["lookup"] if route == "lookup" else []),
                              "factory", "returned"], self.events)
            self.assertTrue(result["fullReuse"])
            with self.subTest(route=route), self.assertRaisesRegex(ValueError, "lacks authenticated original evidence"):
                self.run_route(route, package_factory=lambda _: SimpleNamespace(verify=Mock()))
            with self.subTest(route=route), self.assertRaisesRegex(ValueError, "one concrete source"):
                self.run_route(route, package_admission=self.package_admission,
                               package_factory=factory)

    def test_metadata_routes_require_full_join_and_propagate_rejection(self):
        self.identity = PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")
        for route in ("retained", "lookup"):
            with self.subTest(route=route), self.assertRaisesRegex(ValueError, "metadata reuse lacks"):
                self.run_route(route)
            with patch.object(reuse.AppleValidationAdmission, "verify_metadata", autospec=True,
                    side_effect=ValueError("full metadata replay rejected")) as verify, \
                    self.assertRaisesRegex(ValueError, "full metadata replay rejected"):
                self.run_route(route, self.admission)
            verify.assert_called_once_with(self.admission, self.envelope, ())
            self.build_consumer.assert_not_called()
            # This orchestration fixture removes dependencies; the concrete
            # metadata gate separately rejects an empty predecessor tuple.
            with patch.object(reuse.AppleValidationAdmission, "verify_metadata", autospec=True) as verify:
                result, originals = self.run_route(route, self.admission)
            verify.assert_called_once_with(self.admission, self.envelope, ())
            self.assertTrue(result["fullReuse"])
            self.assertEqual((self.envelope,), originals)

    def test_transported_apple_policy_is_rejected_before_rebase_or_planning(self):
        with patch.object(sys, "path", [str(Path(__file__).resolve().parents[1]), *sys.path]):
            import product_reuse as adapter

        request = {"sdkAppleValidationPolicy": {"untrusted": "transported authority"}}
        with patch.object(adapter, "plan_reuse_wave") as planner, \
                patch.object(adapter, "_rebase_native_evidence_paths") as paths:
            for helper, arguments in (
                (adapter._rebase_native_request, (request, None, None)),
                (adapter._plan_with_sdk_tooling, (request, None)),
            ):
                with self.subTest(helper=helper.__name__), self.assertRaisesRegex(
                        ValueError, "cannot supply current-invocation tooling authority"):
                    helper(*arguments)
            planner.assert_not_called()
            paths.assert_not_called()


if __name__ == "__main__":
    unittest.main()
