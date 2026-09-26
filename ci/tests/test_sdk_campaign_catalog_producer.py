"""The no-secret SDK catalog preflight holds every original until replay ends."""

from contextlib import contextmanager
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_campaign_catalog_producer as catalog
from ci.sdk_campaign_observation import ObservedSdkOriginal
from products.inventory import canonical_json_bytes
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


_DIGEST = "sha256:" + "a" * 64


class SdkCampaignCatalogProducerTest(TestCase):
    def setUp(self):
        self.instances = sorted(SDK_CAMPAIGN_INSTANCES)
        self.observations = {
            instance: ObservedSdkOriginal(b"receipt", canonical_json_bytes({
                "state": "retained", "source": None,
            }), Path("unused-object"), Path("unused-stage"))
            for instance in self.instances
        }
        self.pins = {
            instance: catalog.FreshSdkOriginalPin(
                _DIGEST, position + 1, _DIGEST,
                ".github/workflows/sdk-validation.yml", "product-validation / sdk-worker")
            for position, instance in enumerate(self.instances)
        }

    def held(self):
        return catalog.held_sdk_campaign_original_uploads(
            self.observations, b"current-transport", self.pins,
            trusted_workflow_sha="pinned-workflow", token="observation-token", environ={})

    def test_independent_phase_selection_discovers_all_61_before_replay(self):
        fresh = {instance: {
            "producer": {"selected": position}, "expected_build_key": _DIGEST,
            "expected_product_version": "0.8.0",
            "trusted_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_job_name": "product-validation / sdk-worker",
        } for position, instance in enumerate(self.instances)}
        reused = {}
        selected = self.instances[:2]
        shared_reused = {
            "expected_build_key": _DIGEST, "expected_product_version": "0.8.0",
            "pull_request": 31, "repository": "codex-agent-labs/codex-agent",
            "catalog_artifact_name": "codex-agent-product-catalog-v1-pull-request-31-original",
            "catalog_public_key": Path("independent.pub"),
            "expected_public_key_sha256": _DIGEST,
            "trusted_worker_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_worker_job_name": "product-validation / sdk-worker",
            "trusted_catalog_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_catalog_job_name": "product-validation / sdk-catalog",
        }
        for instance in selected:
            reused[instance] = dict(shared_reused)
            fresh.pop(instance)
        reused_pin = catalog.ReusedSdkOriginalPin(
            _DIGEST, 101, _DIGEST, 201, _DIGEST, Path("independent.pub"), _DIGEST, 31,
            ".github/workflows/product-validation.yml", "product-validation / sdk-worker",
            ".github/workflows/product-validation.yml", "product-validation / sdk-catalog")
        with patch.object(catalog, "discover_fresh_sdk_original_pin", return_value={
                "receipt_sha256": _DIGEST, "artifact_id": 1, "artifact_sha256": _DIGEST,
                "workflow_path": ".github/workflows/product-validation.yml",
                "job_name": "product-validation / sdk-worker"}) as discover_fresh, \
             patch.object(catalog, "discover_reused_sdk_original_pins", return_value={
                instance: {field: getattr(reused_pin, field)
                           for field in reused_pin.__dataclass_fields__}
                for instance in selected
             }) as discover_reused:
            pins = catalog.discover_sdk_campaign_original_pins(fresh, reused,
                trusted_workflow_sha="reviewed-sha", token="observation-token", environ={})
            self.assertEqual(61, len(pins))
            self.assertEqual(59, discover_fresh.call_count)
            discover_reused.assert_called_once()
            self.assertEqual(set(selected), set(discover_reused.call_args.args[0]))
            self.assertEqual(reused[selected[0]]["catalog_artifact_name"],
                             discover_reused.call_args.kwargs["catalog_artifact_name"])
            self.assertIsInstance(pins[selected[0]], catalog.ReusedSdkOriginalPin)
            self.assertIsInstance(pins[self.instances[2]], catalog.FreshSdkOriginalPin)
            fresh.pop(self.instances[2])
            with self.assertRaisesRegex(ValueError, "exactly 61 disjoint"):
                catalog.discover_sdk_campaign_original_pins(fresh, reused,
                    trusted_workflow_sha="reviewed-sha", token="observation-token", environ={})
            self.assertEqual(59, discover_fresh.call_count)

    def test_all_61_originals_remain_held_through_replay_and_close_on_failure(self):
        active = set()
        closed = []

        @contextmanager
        def fresh(instance, *_args, **_kwargs):
            active.add(instance)
            try:
                yield {"instance": instance}, Path("unused-upload")
            finally:
                active.remove(instance)
                closed.append(instance)

        with patch.object(catalog, "held_fresh_sdk_worker_upload", side_effect=fresh), \
             patch.object(catalog, "held_reused_sdk_original") as reused:
            with self.assertRaisesRegex(RuntimeError, "replay failed"):
                with self.held() as evidence:
                    self.assertEqual(set(self.instances), active)
                    self.assertEqual(set(self.instances), set(evidence))
                    self.assertEqual([], closed)
                    raise RuntimeError("replay failed")
            self.assertEqual(set(), active)
            self.assertEqual(list(reversed(self.instances)), closed)
            reused.assert_not_called()

    def test_route_and_pin_mismatch_reject_before_any_original_observation(self):
        instance = self.instances[0]
        self.observations[instance] = ObservedSdkOriginal(b"receipt", canonical_json_bytes({
            "state": "reused", "source": "same-pr",
        }), Path("unused-object"), Path("unused-stage"))
        with patch.object(catalog, "held_fresh_sdk_worker_upload") as fresh, \
             patch.object(catalog, "held_reused_sdk_original") as reused, \
             self.assertRaisesRegex(ValueError, "same-PR catalog pin"):
            with self.held():
                pass
        fresh.assert_not_called()
        reused.assert_not_called()

        self.pins.pop(instance)
        with self.assertRaisesRegex(ValueError, "exact 61"):
            with self.held():
                pass

    def test_reused_phase_uses_pinned_catalog_and_original_route(self):
        instance = self.instances[0]
        self.observations[instance] = ObservedSdkOriginal(b"receipt", canonical_json_bytes({
            "state": "reused", "source": "same-pr",
        }), Path("unused-object"), Path("unused-stage"))
        self.pins[instance] = catalog.ReusedSdkOriginalPin(
            _DIGEST, 101, _DIGEST, 201, _DIGEST, Path("independent.pub"), _DIGEST, 31,
            ".github/workflows/sdk-validation.yml", "product-validation / sdk-worker",
            ".github/workflows/product-validation.yml", "product-validation / sdk-catalog")

        @contextmanager
        def holder(*_args, **_kwargs):
            yield {}, Path("unused-upload")

        with patch.object(catalog, "held_fresh_sdk_worker_upload", side_effect=holder) as fresh, \
             patch.object(catalog, "held_reused_sdk_original", side_effect=holder) as reused:
            with self.held() as evidence:
                self.assertEqual(61, len(evidence))
            self.assertEqual(60, fresh.call_count)
            reused.assert_called_once()
            self.assertEqual(101, reused.call_args.kwargs["original_artifact_id"])
            self.assertEqual(201, reused.call_args.kwargs["catalog_artifact_id"])

    def test_reused_phases_share_one_held_catalog_but_each_hold_its_original(self):
        selected = self.instances[:2]
        pin = catalog.ReusedSdkOriginalPin(
            _DIGEST, 101, _DIGEST, 201, _DIGEST, Path("independent.pub"), _DIGEST, 31,
            ".github/workflows/sdk-validation.yml", "product-validation / sdk-worker",
            ".github/workflows/product-validation.yml", "product-validation / sdk-catalog")
        for instance in selected:
            self.observations[instance] = ObservedSdkOriginal(canonical_json_bytes({
                "producer": {"repository": "codex-agent-labs/codex-agent"}}), canonical_json_bytes({
                "state": "reused", "source": "same-pr",
            }), Path("unused-object"), Path("unused-stage"))
            self.pins[instance] = pin
        active, originals = set(), []
        snapshot = {"held": "catalog"}

        @contextmanager
        def catalog_holder(**_kwargs):
            active.add("catalog")
            try:
                yield snapshot
            finally:
                active.remove("catalog")

        @contextmanager
        def original_holder(instance, *_args, _shared_catalog=None, **_kwargs):
            self.assertIs(snapshot, _shared_catalog)
            self.assertIn("catalog", active)
            originals.append(instance)
            active.add(instance)
            try:
                yield {"instance": instance}, Path("unused-upload")
            finally:
                active.remove(instance)

        @contextmanager
        def fresh_holder(*_args, **_kwargs):
            yield {}, Path("unused-upload")

        with patch.object(catalog, "validate_phase_receipt", return_value={
                "producer": {"repository": "codex-agent-labs/codex-agent"}}), \
             patch.object(catalog, "held_reused_sdk_catalog", side_effect=catalog_holder) as shared, \
             patch.object(catalog, "_held_reused_sdk_original", side_effect=original_holder), \
             patch.object(catalog, "held_fresh_sdk_worker_upload", side_effect=fresh_holder):
            with self.held():
                self.assertEqual(set(selected) | {"catalog"}, active)
                self.assertEqual(list(selected), originals)
            self.assertEqual(set(), active)
        shared.assert_called_once()

    def test_caller_owned_routes_are_forwarded_and_unpaired_routes_fail_before_observation(self):
        instance = self.instances[0]
        self.pins[instance] = catalog.FreshSdkOriginalPin(
            _DIGEST, 1, _DIGEST, ".github/workflows/sdk-validation.yml",
            "product-validation / sdk-validation / sdk-worker")

        @contextmanager
        def holder(*_args, **_kwargs):
            yield {}, Path("unused-upload")

        with patch.object(catalog, "held_fresh_sdk_worker_upload", side_effect=holder) as fresh:
            with self.held():
                pass
            selected = next(call for call in fresh.call_args_list if call.args[0] == instance)
            self.assertEqual(".github/workflows/sdk-validation.yml",
                             selected.kwargs["trusted_workflow_path"])
            self.assertEqual("product-validation / sdk-validation / sdk-worker",
                             selected.kwargs["trusted_job_name"])
        self.pins[instance] = catalog.FreshSdkOriginalPin(
            _DIGEST, 1, _DIGEST, ".github/workflows/sdk-validation.yml", "")
        with patch.object(catalog, "held_fresh_sdk_worker_upload") as fresh, \
             self.assertRaisesRegex(ValueError, "must both be pinned"):
            with self.held():
                pass
        fresh.assert_not_called()

        self.pins[instance] = catalog.ReusedSdkOriginalPin(
            _DIGEST, 101, _DIGEST, 201, _DIGEST, Path("independent.pub"), _DIGEST, 31,
            ".github/workflows/sdk-validation.yml", "product-validation / sdk-worker",
            ".github/workflows/product-validation.yml", "")
        self.observations[instance] = ObservedSdkOriginal(b"receipt", canonical_json_bytes({
            "state": "reused", "source": "same-pr",
        }), Path("unused-object"), Path("unused-stage"))
        with patch.object(catalog, "held_reused_sdk_original") as reused, \
             self.assertRaisesRegex(ValueError, "must be pinned"):
            with self.held():
                pass
        reused.assert_not_called()

    def test_semantic_replay_holds_all_uploads_and_preserves_original_receipts(self):
        active = set()
        receipts = {instance: canonical_json_bytes({"fixture": position})
                    for position, instance in enumerate(self.instances)}
        for instance in self.instances:
            self.observations[instance] = ObservedSdkOriginal(receipts[instance], canonical_json_bytes({
                "receiptSha256": _DIGEST, "objectSha256": _DIGEST,
            }), Path("unused-object"), Path("unused-stage"))
        artifacts = {instance: "outputs/fixture.bin" for instance in self.instances}

        @contextmanager
        def originals(*_args, **_kwargs):
            active.add("uploads")
            try:
                yield {instance: {"original": True} for instance in self.instances}
            finally:
                active.remove("uploads")

        @contextmanager
        def selection(sources, envelopes, archives, stages):
            self.assertEqual({instance: receipts[instance] for instance in self.instances},
                             {instance: source.receipt_bytes for instance, source in sources.items()})
            self.assertEqual(set(archives), set(self.instances))
            self.assertEqual(set(stages), set(self.instances))
            active.add("selection")
            try:
                yield sources, envelopes, stages, {}
            finally:
                active.remove("selection")

        def semantics(**values):
            self.assertEqual({"uploads", "selection"}, active)
            self.assertEqual({"fixture": True}, values["maven_controls"])
            return receipts

        with patch.object(catalog, "held_sdk_campaign_original_uploads", side_effect=originals), \
             patch.object(catalog, "held_sdk_campaign_selection", side_effect=selection), \
             patch.object(catalog, "verify_sdk_campaign_semantics", side_effect=semantics) as verify:
            with catalog.held_sdk_campaign_semantic_replay(self.observations, b"transport", self.pins,
                    artifacts, {"maven_controls": {"fixture": True}}, trusted_workflow_sha="pin",
                    token="token", environ={}) as (verified, evidence):
                self.assertEqual(receipts, verified)
                self.assertEqual(set(self.instances), set(evidence))
                self.assertEqual({"uploads", "selection"}, active)
            self.assertEqual(set(), active)
            self.assertEqual(1, verify.call_count)

        changed = dict(receipts)
        changed[self.instances[0]] = b"different original"
        with patch.object(catalog, "held_sdk_campaign_original_uploads", side_effect=originals), \
             patch.object(catalog, "held_sdk_campaign_selection", side_effect=selection), \
             patch.object(catalog, "verify_sdk_campaign_semantics", return_value=changed), \
             self.assertRaisesRegex(ValueError, "changed an original receipt"):
            with catalog.held_sdk_campaign_semantic_replay(self.observations, b"transport", self.pins,
                    artifacts, {"maven_controls": {"fixture": True}}, trusted_workflow_sha="pin",
                    token="token", environ={}):
                pass
        self.assertEqual(set(), active)

    def test_semantic_replay_rejects_missing_artifact_or_changed_receipt(self):
        missing = {instance: "outputs/fixture.bin" for instance in self.instances[1:]}
        with patch.object(catalog, "held_sdk_campaign_original_uploads") as originals, \
             self.assertRaisesRegex(ValueError, "61 caller-selected artifacts"):
            with catalog.held_sdk_campaign_semantic_replay(self.observations, b"transport", self.pins,
                    missing, {}, trusted_workflow_sha="pin", token="token", environ={}):
                pass
        originals.assert_not_called()
