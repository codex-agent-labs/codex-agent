"""Automatic Apple policy routing; cryptographic gates are tested separately."""

from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
import sdk_apple_policy  # noqa: E402
import tooling_discovery  # noqa: E402
from products.inventory import canonical_json_bytes  # noqa: E402
from products.registry import PhaseInstanceId  # noqa: E402
from ci.tests import test_product_tooling_discovery as tooling_fixture  # noqa: E402
from ci.tests.test_product_reuse_adapter import VERSIONS, impact_plan  # noqa: E402


WORKFLOW_PIN = "c" * 40


class ProductAppleDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = tooling_fixture.ProductToolingDiscoveryTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.plan_path = self.fixture.plan_path
        self.output = self.fixture.output
        self.java = self.fixture.java
        self.number = 0

    def invoke(self, *, tooling_hit, explicit_roots=(), explicit_policy=None, package_only=False):
        self.number += 1
        plan = impact_plan(changed=["codex-agent-runtime-ios/apple/TestApp/TestApp.swift"])
        self.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        destination = self.root / f"discovery-{self.number}"
        catalog_root = self.root / "catalog-apple"
        catalog = product_reuse.Catalog(
            source="same-pr", index={}, index_sha256="sha256:" + "a" * 64,
            request={}, objects={}, sdk_apple_validation_evidence_root=catalog_root,
        )
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        package = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        validation = PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
        closure = (contract, package) if package_only else (contract, package, validation)
        events, selected_roots, planner_calls = [], [], []

        def release_trust(_root, _revision, output):
            keys = output / "trust/keys"
            keys.mkdir(parents=True)
            keyring = output / "trust/product-signing-keys.json"
            keyring.write_bytes(b"current Git release keyring\n")
            (keys / "release.pub").write_bytes(b"current Git public key\n")
            return product_reuse.ReleaseTrust(keyring, keys)

        def catalogs(*_args, **kwargs):
            events.append("catalogs")
            kwargs["tooling_candidate_runs"].extend((41, 39))
            return [catalog]

        def discover_tooling(output, repository, **kwargs):
            events.append("tooling")
            self.assertEqual(self.root, repository)
            self.assertEqual([41, 39], kwargs["candidate_run_ids"])
            self.assertEqual(WORKFLOW_PIN, kwargs["trusted_workflow_sha"])
            self.assertEqual(plan["validationCommit"], kwargs["policy_revision"])
            self.assertEqual(self.java, kwargs["java_executable"])
            policy = None
            selected = None
            if tooling_hit:
                evidence = output / "capture/evidence"
                keys = output / "capture/policy/keys"
                evidence.mkdir(parents=True)
                keys.mkdir(parents=True)
                (evidence / "tooling-evidence.json").write_bytes(b"authenticated tooling evidence\n")
                public_key = keys / "release.pub"
                public_key.write_bytes(b"authenticated tooling key\n")
                keyring = output / "capture/policy/product-signing-keys.json"
                keyring.write_bytes(b"authenticated tooling keyring\n")
                policy = {
                    "evidence": str(evidence), "publicKey": str(public_key),
                    "javaExecutable": str(self.java), "requiredTrustDomain": "release",
                    "keyring": str(keyring), "keysDirectory": str(keys),
                }
                selected = {"artifactId": 71, "artifactSha256": "sha256:" + "e" * 64,
                            "transportProducer": {"repository": "fixture/repository", "tree": "d" * 40}}
                (output / "capture/tooling-policy.json").write_bytes(canonical_json_bytes(policy))
            report = {"schemaVersion": 1, "selected": selected, "attempts": [], "toolingPolicy": policy}
            output.mkdir(parents=True, exist_ok=True)
            (output / "discovery.json").write_bytes(canonical_json_bytes(report))
            return report

        def capture_apple(roots, _output, _artifact_root):
            events.append("apple")
            selected_roots.append(tuple(roots))
            return ([{"receiptSha256": "sha256:" + "f" * 64}] if roots else [])

        def planner(invocation, **_kwargs):
            events.append("planner")
            if _kwargs.get("sdk_apple_package_admission_factory") is not None:
                events.append("apple-factory")
            planner_calls.append(invocation)
            if len(planner_calls) == 1:
                return {"result": "complete", "fullReuse": True, "phases": []}
            return {"result": "incomplete", "fullReuse": False, "phases": [],
                    "matrices": {"contract": [], "runtime": [], "sdk": []}}

        environment = {"GITHUB_TOKEN": "token", "GITHUB_RUN_ID": "81", "GITHUB_RUN_ATTEMPT": "2"}
        with ExitStack() as stack:
            for owner, name, options in (
                (product_reuse, "_validate_plan", {"return_value": plan}),
                (product_reuse, "_requested", {"return_value": (package,) if package_only else (validation,)}),
                (product_reuse, "_dependency_closure", {"side_effect":
                    lambda selected, **_options: (contract,) if tuple(selected) == (contract,) else closure}),
                (product_reuse, "sdk_runtime_source", {"return_value": None}),
                (product_reuse, "_versions", {"return_value": VERSIONS}),
                (product_reuse, "_release_trust", {"side_effect": release_trust}),
                (product_reuse, "_discover_catalogs", {"side_effect": catalogs}),
                (product_reuse, "_capture_native_handoffs", {"return_value": []}),
                (product_reuse, "_capture_sdk_handoffs", {"return_value": []}),
                (product_reuse, "_capture_apple_handoffs", {"side_effect": capture_apple}),
                (product_reuse, "_capture_aggregate_handoffs", {"return_value": []}),
                (product_reuse, "_authorities", {"return_value": ([], None)}),
                (product_reuse, "_contract_evidence", {"return_value": {"authenticated": "fixture"}}),
                (product_reuse, "plan_reuse_wave", {"side_effect": planner}),
                (tooling_discovery, "discover_tooling_ci", {"side_effect": discover_tooling}),
            ):
                stack.enter_context(patch.object(owner, name, **options))
            stack.enter_context(patch("sdk_apple_original_package_selection.caller_original_apple_package_selector",
                                      return_value=nullcontext(object())))
            result = product_reuse.discover(
                self.plan_path, destination, self.output, repository_root=self.root,
                environ=environment, sdk_apple_evidence_roots=tuple(explicit_roots),
                sdk_apple_validation_policy=explicit_policy,
                tooling_java_executable=self.java, tooling_workflow_sha=WORKFLOW_PIN,
            )
        return result, destination, catalog_root, events, selected_roots, planner_calls

    def test_authenticated_tooling_builds_one_ephemeral_policy_for_every_planner(self):
        result, destination, catalog_root, events, roots, planners = self.invoke(tooling_hit=True)
        self.assertEqual("product-build-required", result["reason"])
        self.assertEqual([(catalog_root,)], roots)
        self.assertEqual(2, len(planners))
        policies = [invocation["sdkAppleValidationPolicy"] for invocation in planners]
        self.assertIs(policies[0], policies[1])
        policy = policies[0]
        for name, value in policy.items():
            if name.endswith(("TrustDomain", "PublicKey")) and value is None:
                continue
            if name in {"attestationTrustDomain", "toolingTrustDomain"}:
                continue
            self.assertTrue(Path(value).exists(), (name, value))
        self.assertIn("tooling", events)
        self.assertEqual(2, events.count("planner"))
        for name in ("contract-reuse-request.json", "reuse-wave-request.json", "request.json"):
            retained = (destination / name).read_bytes()
            self.assertNotIn(b"sdkAppleValidationPolicy", retained)
            self.assertNotIn(b"attestationTrustDomain", retained)

    def test_automatic_miss_excludes_catalog_proof_but_explicit_proof_fails_closed(self):
        result, _, _, _, roots, planners = self.invoke(tooling_hit=False)
        self.assertEqual("product-build-required", result["reason"])
        self.assertEqual([()], roots)
        self.assertEqual(2, len(planners))
        self.assertTrue(all("sdkAppleValidationPolicy" not in invocation for invocation in planners))

        explicit = self.root / "explicit-apple-proof"
        with self.assertRaisesRegex(ValueError, "caller-owned validation policy"):
            self.invoke(tooling_hit=False, explicit_roots=(explicit,))

    def test_package_only_reuse_gets_caller_policy_without_validation_evidence(self):
        with patch.object(sdk_apple_policy, "caller_apple_validation_policy",
                          wraps=sdk_apple_policy.caller_apple_validation_policy) as mapping:
            _, _, _, events, roots, planners = self.invoke(tooling_hit=True, package_only=True)
        mapping.assert_called_once()
        self.assertEqual([()], roots)
        self.assertEqual(1, events.count("apple-factory"))
        self.assertTrue(all("sdkAppleValidationEvidence" not in request for request in planners))
        with patch.object(sdk_apple_policy, "caller_apple_validation_policy",
                          wraps=sdk_apple_policy.caller_apple_validation_policy) as mapping:
            self.invoke(tooling_hit=False, package_only=True)
        mapping.assert_not_called()

    def test_explicit_policy_is_never_replaced_by_automatic_discovery(self):
        explicit = {"caller": "original explicit policy", "plan": str(self.plan_path)}
        with patch.object(sdk_apple_policy, "caller_apple_validation_policy",
                          side_effect=AssertionError("explicit policy must not be replaced")) as automatic:
            _, _, _, _, _, planners = self.invoke(tooling_hit=True, explicit_policy=explicit)
        automatic.assert_not_called()
        self.assertEqual(2, len(planners))
        self.assertTrue(all(invocation["sdkAppleValidationPolicy"] is explicit for invocation in planners))


if __name__ == "__main__":
    unittest.main()
