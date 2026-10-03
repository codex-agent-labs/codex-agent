"""Structural Apple carrier transport and explicit caller-policy routing only.

Opaque fixture signatures and a mocked planner are not authentication or phase
admission. Carrier storage, byte bindings, path rebasing and control parsing are
real; no observer, network, compiler or signing operation runs here.
"""

from copy import deepcopy
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse as adapter
from ci.products.inventory import canonical_json_bytes, regular_file_inventory, write_canonical_json
from ci.products.sdk_apple_validation_inputs import capture_sdk_apple_validation_evidence
from ci.tests import test_sdk_apple_validation_inputs as fixtures


class AppleTransportTest(TestCase):
    def setUp(self):
        self.fixture = fixtures.AppleValidationInputsTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.discovery = self.root / "outer/state/discovery"
        self.carrier = self.discovery / "sdk-apple-validation-evidence/0"
        self.records = capture_sdk_apple_validation_evidence([self.fixture.entry()], self.carrier)
        self.policy = {"plan": str(self.root / "caller-plan"), "attestationPublicKey": str(self.root / "caller.pub"),
            "attestationTrustDomain": "development", "keyring": str(self.root / "keys.json"),
            "keysDirectory": str(self.root / "keys"), "toolingEvidence": str(self.root / "tooling"),
            "toolingPublicKey": str(self.root / "tooling.pub"), "javaExecutable": str(self.root / "java"),
            "toolingTrustDomain": "release", "toolingKeyring": str(self.root / "tooling-keys.json"),
            "toolingKeysDirectory": str(self.root / "tooling-keys")}

    def retained(self):
        return adapter._retained_apple_handoffs(self.discovery, self.discovery)

    def wave(self):
        return {"schemaVersion": 1, "requestType": "pull-request", "repository": "owner/repository",
            "pullRequest": 31, "repositoryRoot": str(self.root), "repositoryRevision": "a" * 40,
            "artifactRoot": str(self.root / "build/product-reuse"), "requested": [],
            "versions": {"contract": "0.8.0", "runtime-release": "0.8.0", "sdk": "0.8.0"},
            "phaseAuthorities": [], "contractEvidence": None, "runtimeValidationEvidence": [],
            "availableObjects": [], "catalogs": {"stable": [], "promotedMain": None, "samePr": None, "local": None}}

    def test_retained_carrier_rebases_through_two_enclosing_roots_without_rewriting(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        records = self.retained()
        self.assertEqual([{**record, "evidenceRoot": "sdk-apple-validation-evidence/0/" + record["evidenceRoot"]}
                          for record in self.records], records)
        original_request = {"sdkAppleValidationEvidence": records}
        original_bytes = canonical_json_bytes(original_request)
        first = adapter._rebase_native_request(original_request, self.discovery, self.discovery.parent)
        second = adapter._rebase_native_request(first, self.discovery.parent, self.root / "outer")
        self.assertEqual([{**record, "evidenceRoot": "state/discovery/" + record["evidenceRoot"]} for record in records],
                         second["sdkAppleValidationEvidence"])
        self.assertEqual(original_bytes, canonical_json_bytes(original_request))
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))
        self.assertNotIn("sdkAppleValidationPolicy", first)
        self.assertNotIn("sdkAppleValidationPolicy", second)

    def test_discovery_requires_exact_complete_retained_references(self):
        records = self.retained()
        adapter._verify_discovery_sdk_records({"sdkAppleValidationEvidence": records}, self.discovery)
        changed = [{**records[0], "target": "ios-simulator-arm64"}]
        escaped = [{**records[0], "evidenceRoot": "../" + records[0]["evidenceRoot"]}]
        for request in ({}, {"sdkAppleValidationEvidence": []}, {"sdkAppleValidationEvidence": records + records},
                        {"sdkAppleValidationEvidence": changed}, {"sdkAppleValidationEvidence": escaped}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                adapter._verify_discovery_sdk_records(request, self.discovery)
        empty = self.root / "empty-discovery"
        empty.mkdir()
        adapter._verify_discovery_sdk_records({}, empty)
        with self.assertRaises(ValueError):
            adapter._verify_discovery_sdk_records({"sdkAppleValidationEvidence": records}, empty)

    def test_resumed_nested_discovery_retains_exact_references(self):
        enclosing = self.discovery.parent
        records = adapter._retained_apple_handoffs(self.discovery, enclosing)
        adapter._verify_discovery_sdk_records({"sdkAppleValidationEvidence": records}, enclosing)
        with self.assertRaises(ValueError):
            adapter._verify_discovery_sdk_records({}, enclosing)

    def test_symlink_carrier_ancestry_and_dangling_collection_reject(self):
        alias = self.root / "alias-discovery"
        alias.symlink_to(self.discovery, target_is_directory=True)
        with self.assertRaises(ValueError):
            adapter._retained_apple_handoffs(alias, self.root)
        empty = self.root / "dangling-discovery"
        empty.mkdir()
        (empty / "sdk-apple-validation-evidence").symlink_to(self.root / "absent", target_is_directory=True)
        with self.assertRaises(ValueError):
            adapter._retained_apple_handoffs(empty, self.root)

    def test_wave_control_accepts_only_evidence_not_transported_policy(self):
        path = self.root / "wave.json"
        request = {**self.wave(), "sdkAppleValidationEvidence": self.retained()}
        write_canonical_json(path, request)
        self.assertEqual(request, adapter._wave_control(path, "synthetic retained wave"))
        for field in ("sdkAppleValidationPolicy", "sdkValidationTooling", "unknownAuthority"):
            write_canonical_json(path, {**request, field: self.policy})
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter._wave_control(path, "synthetic retained wave")

    def test_explicit_policy_is_invocation_only_and_only_forwarded_with_apple_evidence(self):
        tooling = {"synthetic": "caller-owned tooling seam"}
        for evidence in (None, [], self.retained()):
            request = self.wave()
            if evidence is not None:
                request["sdkAppleValidationEvidence"] = evidence
            before = canonical_json_bytes(request)
            policy_before = deepcopy(self.policy)
            with self.subTest(evidence=evidence), patch.object(adapter, "plan_reuse_wave", return_value={"fixture": "planned"}) as plan:
                result = adapter._plan_with_sdk_tooling(request, tooling, apple_policy=self.policy, phase_selector="fixture")
                self.assertEqual({"fixture": "planned"}, result)
                invocation = plan.call_args.args[0]
                self.assertEqual({"phase_selector": "fixture"}, plan.call_args.kwargs)
                self.assertIs(tooling, invocation["sdkValidationTooling"])
                if evidence is not None:
                    self.assertIs(self.policy, invocation["sdkAppleValidationPolicy"])
                else:
                    self.assertNotIn("sdkAppleValidationPolicy", invocation)
                self.assertEqual(before, canonical_json_bytes(request))
                self.assertEqual(policy_before, self.policy)
                self.assertNotIn("sdkValidationTooling", request)
                self.assertNotIn("sdkAppleValidationPolicy", request)

    def test_transported_policy_never_substitutes_for_caller_policy(self):
        for field in ("sdkValidationTooling", "sdkAppleValidationPolicy"):
            request = {"sdkAppleValidationEvidence": self.retained(), field: self.policy}
            with self.subTest(field=field), patch.object(adapter, "plan_reuse_wave") as plan:
                with self.assertRaises(ValueError):
                    adapter._plan_with_sdk_tooling(request, None, apple_policy=self.policy)
                plan.assert_not_called()
                with self.assertRaises(ValueError):
                    adapter._rebase_native_request(request, self.discovery, self.root)

    def test_omitted_policy_preserves_legacy_shape_and_does_not_invent_authority(self):
        with patch.object(adapter, "plan_reuse_wave", return_value={}) as plan:
            adapter._plan_with_sdk_tooling({}, None)
            self.assertEqual({}, plan.call_args.args[0])
        for evidence in ([], self.retained()):
            with self.subTest(evidence=evidence), patch.object(adapter, "plan_reuse_wave") as plan:
                with self.assertRaisesRegex(ValueError, "requires caller-owned validation policy"):
                    adapter._plan_with_sdk_tooling({"sdkAppleValidationEvidence": evidence}, None)
                plan.assert_not_called()

    def test_two_structural_captures_preserve_all_original_bytes_without_policy(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        first = self.root / "first/sdk-apple-validation-evidence"
        first_records = adapter._capture_apple_handoffs([self.carrier], first, self.root)
        second = self.root / "second/sdk-apple-validation-evidence"
        second_records = adapter._capture_apple_handoffs([first / "0"], second, self.root)
        for location in (self.carrier, first / "0", second / "0"):
            self.assertEqual(before, regular_file_inventory(location, allow_empty=True))
        self.assertEqual([{**record, "evidenceRoot": "first/sdk-apple-validation-evidence/0/" + record["evidenceRoot"]}
                         for record in self.records], first_records)
        self.assertEqual([{**record, "evidenceRoot": "second/sdk-apple-validation-evidence/0/" + record["evidenceRoot"]}
                         for record in self.records], second_records)
        self.assertEqual(second_records, adapter._retained_apple_handoffs(self.root / "second", self.root))
        self.assertTrue(all(set(record) == {"receiptSha256", "target", "evidenceRoot"} for record in second_records))
