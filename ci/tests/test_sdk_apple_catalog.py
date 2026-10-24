"""Catalog structure/routing only; mocked index authority is not Apple admission."""

from copy import deepcopy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse as adapter
from ci.products import sdk_apple_validation_inputs as carrier
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    snapshot_regular_tree, write_canonical_json,
)
from ci.tests import test_sdk_apple_validation_inputs as fixtures


class AppleCatalogTest(unittest.TestCase):
    def setUp(self):
        # Delegate fixture construction only; do not inherit its test methods.
        self.fixture = fixtures.AppleValidationInputsTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        entries = [self.fixture.entry(), self.fixture.entry("simulator", "ios-simulator-arm64")]
        self.source = self.root / "source-carrier"
        self.records = carrier.capture_sdk_apple_validation_evidence(entries, self.source)
        producer = self.fixture.producer
        indexed = []
        for record in self.records:
            receipt = load_canonical_json_bytes((self.source / record["evidenceRoot"] /
                "capture/original/shard/phase-receipt.json").read_bytes())
            indexed.append({**receipt, "receiptSha256": record["receiptSha256"]})
        self.index = {"repository": producer["repository"], "producer": producer,
                      "context": {"kind": "pull-request", **{key: producer[key] for key in
                          ("pullRequest", "commit", "tree", "runId", "runAttempt")}}, "entries": indexed}
        self.observed = {"run": {"id": producer["runId"], "run_attempt": producer["runAttempt"],
                                 "path": producer["workflowPath"]},
                         "testedCommit": {"sha": producer["commit"], "tree": {"sha": producer["tree"]}}}

    def layout(self, name, *, index=None, include_carrier=True):
        extracted = self.root / name / "contents"
        extracted.mkdir(parents=True)
        write_canonical_json(extracted / "product-index.json", self.index if index is None else index)
        (extracted / "product-index.sig").write_bytes(b"opaque index signature: outside test scope")
        (extracted / "public-key.pub").write_bytes(b"caller observed key: outside test scope")
        if include_carrier:
            snapshot_regular_tree(self.source, extracted / "sdk-apple-validation-evidence", allow_empty=True)
        return extracted

    def read_catalog(self, extracted):
        # Exact index validation/signing belongs to existing index tests. The
        # strict Apple loader, inventory allowlist and tuple binding remain real.
        with patch.object(adapter, "validate_product_index", side_effect=lambda value: value):
            return adapter._read_catalog_directory("same-pr", extracted, extracted.parent, None,
                repository=self.fixture.producer["repository"], pull_request=self.fixture.producer["pullRequest"],
                provenance_root=extracted.parent, workflow_run=self.observed)

    def test_cli_policy_and_carrier_roots_are_explicit_and_omission_preserves_old_calls(self):
        policy = {"fixture": "caller-owned policy"}
        path = self.root / "policy.json"
        write_canonical_json(path, policy)
        argv = ["discover", "--plan", str(self.root / "plan"), "--destination", str(self.root / "destination"),
                "--github-output", str(self.root / "output")]
        with patch.object(adapter, "discover") as discover:
            self.assertEqual(0, adapter.main(argv))
            self.assertNotIn("sdk_apple_validation_policy", discover.call_args.kwargs)
            self.assertNotIn("sdk_apple_evidence_roots", discover.call_args.kwargs)
            self.assertEqual(0, adapter.main([*argv, "--sdk-apple-validation-policy", str(path),
                                             "--sdk-apple-validation-evidence", str(self.source)]))
            self.assertEqual(policy, discover.call_args.kwargs["sdk_apple_validation_policy"])
            self.assertEqual((self.source,), discover.call_args.kwargs["sdk_apple_evidence_roots"])

    def test_both_target_carriers_are_index_bound_and_preserved_without_admission(self):
        before = regular_file_inventory(self.source, allow_empty=True)
        extracted = self.layout("valid")
        catalog = self.read_catalog(extracted)
        self.assertEqual(extracted / "sdk-apple-validation-evidence", catalog.sdk_apple_validation_evidence_root)
        self.assertEqual(self.records, carrier.load_sdk_apple_validation_evidence(catalog.sdk_apple_validation_evidence_root))
        self.assertEqual(before, regular_file_inventory(catalog.sdk_apple_validation_evidence_root, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.source, allow_empty=True))
        self.assertEqual({}, catalog.objects)  # No object/admission fabricated by retaining evidence.
        self.assertNotIn("sdkAppleValidationPolicy", catalog.request)

    def test_other_index_identities_or_receipt_digests_cannot_authorize_apple_carrier(self):
        changes = (
            {"receiptSha256": "sha256:" + "f" * 64},
            {"target": "ios-simulator-arm64" if self.records[0]["target"] == "ios-arm64" else "ios-arm64"},
            {"component": "javascript", "target": "node"},
            {"phase": "package", "target": "ios"},
            {"product": "runtime"},
        )
        for number, change in enumerate(changes):
            index = deepcopy(self.index)
            index["entries"][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read_catalog(self.layout(f"wrong-index-{number}", index=index))
        index = {**self.index, "entries": []}
        with self.assertRaises(ValueError):
            self.read_catalog(self.layout("unindexed", index=index))

    def test_strict_carrier_and_catalog_allowlists_reject_missing_extra_or_changed_bytes(self):
        for mutation in ("extra-root", "extra-entry", "missing-signature", "changed-capture", "catalog-extra"):
            extracted = self.layout(mutation)
            evidence = extracted / "sdk-apple-validation-evidence"
            entry = evidence / self.records[0]["evidenceRoot"]
            if mutation == "extra-root":
                (evidence / "unexpected.json").write_bytes(b"extra")
            elif mutation == "extra-entry":
                (entry / "unexpected.json").write_bytes(b"extra")
            elif mutation == "missing-signature":
                (entry / carrier.SIGNATURE_NAME).unlink()
            elif mutation == "changed-capture":
                (entry / "capture/original/empty.log").write_bytes(b"altered raw stream")
            else:
                (extracted / "unrequested-private-key").write_bytes(b"not allowed")
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, OSError)):
                self.read_catalog(extracted)

    def test_catalog_without_apple_carrier_preserves_legacy_optional_field(self):
        catalog = self.read_catalog(self.layout("legacy", include_carrier=False))
        self.assertIsNone(catalog.sdk_apple_validation_evidence_root)
        self.assertIsNone(adapter.Catalog("same-pr", {}, "sha256:" + "0" * 64, {}, {}).sdk_apple_validation_evidence_root)

    def test_catalog_and_explicit_carriers_retain_records_but_policy_is_invocation_only(self):
        catalog = self.read_catalog(self.layout("forwarding"))
        destination = self.root / "discovery"
        records = adapter._capture_apple_handoffs((catalog.sdk_apple_validation_evidence_root, self.source),
            destination / "sdk-apple-validation-evidence", destination)
        self.assertEqual(records, adapter._retained_apple_handoffs(destination, destination))
        # Merge duplicate receipt references using the production request seam.
        request = {}
        adapter._merge_native_comparison_records(request, records, key="sdkAppleValidationEvidence")
        before = canonical_json_bytes(request)
        policy = {"explicit": "independent caller policy seam"}
        tooling = {"explicit": "independent tooling seam"}
        with patch.object(adapter, "plan_reuse_wave", return_value={}) as planner:
            adapter._plan_with_sdk_tooling(request, tooling, apple_policy=policy)
        invocation = planner.call_args.args[0]
        self.assertIs(policy, invocation["sdkAppleValidationPolicy"])
        self.assertIs(tooling, invocation["sdkValidationTooling"])
        self.assertEqual(before, canonical_json_bytes(request))
        self.assertNotIn("sdkAppleValidationPolicy", request)
        for child in (destination / "sdk-apple-validation-evidence").iterdir():
            manifest = load_canonical_json_bytes((child / carrier.REQUEST_NAME).read_bytes())
            self.assertEqual({"schemaVersion", "records"}, set(manifest))
        with patch.object(adapter, "plan_reuse_wave") as planner, self.assertRaisesRegex(ValueError, "caller-owned validation policy"):
            adapter._plan_with_sdk_tooling(request, tooling)
        planner.assert_not_called()

    def test_discover_orders_selected_apple_roots_and_keeps_policy_out_of_retained_request(self):
        from ci.tests import test_product_reuse_adapter as discovery_fixture

        plan = discovery_fixture.impact_plan(changed=["codex-agent-runtime-ios/apple/TestApp/TestApp.swift"])
        plan_path = self.root / "impact-plan.json"
        write_canonical_json(plan_path, plan)
        catalogs = [adapter.Catalog(source, {}, "sha256:" + "a" * 64,
                    {"manifest": source + "/product-index.json"}, {},
                    sdk_apple_validation_evidence_root=self.root / source)
                    for source in ("same-pr", "stable", "promoted-main")]
        policy = {"explicit-caller": "never-serialized"}
        apple = adapter.PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64")
        contract = adapter.PhaseInstanceId("contract", "contract", "metadata", "common")
        for instance, selected in ((apple, True), (contract, False)):
            events = []
            destination = self.root / ("apple-discovery" if selected else "unrelated-discovery")
            explicit = (self.root / "explicit",) if selected else ()
            records = self.records if selected else []

            def catalog_lookup(*_args, **_kwargs):
                events.append("catalogs")
                return catalogs

            def capture(roots, output, artifact_root):
                events.append("capture")
                self.assertEqual(tuple(self.root / name for name in
                    ("stable", "promoted-main", "same-pr", "explicit")) if selected else (), roots)
                self.assertEqual(destination / "sdk-apple-validation-evidence", output)
                self.assertEqual(destination, artifact_root)
                return records  # Structural capture is independently covered above.

            def wave(request, **_kwargs):
                events.append("planner")
                if selected:
                    self.assertEqual(records, request["sdkAppleValidationEvidence"])
                    self.assertIs(policy, request["sdkAppleValidationPolicy"])
                else:
                    self.assertNotIn("sdkAppleValidationEvidence", request)
                    self.assertNotIn("sdkAppleValidationPolicy", request)
                return {"fullReuse": False, "phases": []}

            with self.subTest(instance=instance), ExitStack() as stack:
                for name, options in (
                    ("_validate_plan", {"return_value": plan}),
                    ("_requested", {"return_value": (instance,)}),
                    ("_authorities", {"return_value": ([], None)}),
                    ("_versions", {"return_value": discovery_fixture.VERSIONS}),
                    ("_release_trust", {"return_value": None}),
                    ("sdk_runtime_source", {"return_value": None}),
                    ("_discover_catalogs", {"side_effect": catalog_lookup}),
                    ("_capture_apple_handoffs", {"side_effect": capture}),
                    ("plan_reuse_wave", {"side_effect": wave}),
                ):
                    stack.enter_context(patch.object(adapter, name, **options))
                result = adapter.discover(plan_path, destination, self.root / f"outputs-{selected}",
                    repository_root=self.root, environ={}, sdk_apple_evidence_roots=explicit,
                    sdk_apple_validation_policy=policy)
            self.assertEqual(["catalogs", "capture", "planner"], events)
            self.assertEqual("product-build-required", result["reason"])
            retained = load_canonical_json_bytes((destination / "contract-reuse-request.json").read_bytes())
            self.assertEqual(records, retained.get("sdkAppleValidationEvidence", []))
            self.assertNotIn("sdkAppleValidationPolicy", retained)
            self.assertNotIn("sdkValidationTooling", retained)


if __name__ == "__main__":
    unittest.main()
