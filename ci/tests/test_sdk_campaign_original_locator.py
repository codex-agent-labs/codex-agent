"""Official SDK original lookup: synthetic API, exact fresh shard bytes."""

from dataclasses import replace
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_campaign_original_locator as locator
from ci import sdk_campaign_original_worker as worker
from ci.sdk_campaign_catalog_producer import FreshSdkOriginalPin
from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.tests import test_sdk_worker_collection as fixture_module
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.receipt import validate_phase_receipt, write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


class SdkCampaignOriginalLocatorTest(TestCase):
    def setUp(self):
        self.fixture = fixture_module.SdkWorkerCollectionTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.original_names = self.fixture.names

    def selected(self, *, core=False, android_phase=None):
        if core or android_phase is not None:
            instance = (PhaseInstanceId("sdk", "sdk-core", "package", "common") if core else
                PhaseInstanceId("sdk", "sdk-android", android_phase, "android"))
            base = self.fixture.repository / ("core-original" if core else f"android-{android_phase}-original")
            stage = base / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/package").write_bytes(b"exact Core package")
            manifest = write_output_manifest(stage, "sdk", instance.component, instance.phase, instance.target, "0.3.0",
                {"package": "outputs"})
            receipt = write_receipt(base / "fixture-receipt.json", product="sdk", component=instance.component,
                phase=instance.phase, target=instance.target, outputs=manifest["outputs"], upstream=[],
                version="0.3.0", version_identity="0.3.0",
                context={"producer": self.fixture.producer})
            ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
            shard = base / "shard"
            descriptor = finalize_phase_object(stage_root=stage, phase_plan=ready,
                producer=self.fixture.producer, product_version="0.3.0",
                trust_domain="development", destination=shard)
            files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                for row in regular_file_inventory(shard)}
            self.fixture.names = lambda selected, key: locator.fresh_sdk_worker_route(
                selected, descriptor["receipt"])
        else:
            self.fixture.names = self.original_names
            instance, ready, shard, descriptor, files = self.fixture.shard("package")
        record = {"product": instance.product, "component": instance.component,
            "phase": instance.phase, "target": instance.target,
            "buildKey": ready["buildKey"], "receiptSha256": descriptor["receiptSha256"],
            "objectSha256": descriptor["objectSha256"], "state": "retained",
            "source": None, "transportSource": None, "misses": []}
        original = ObservedSdkOriginal(descriptor["receiptBytes"], canonical_json_bytes(record),
            shard / descriptor["objectPath"], shard.parent / "stage")
        return instance, ready, original, archive(files)

    def locate(self, instance, original, digest=None, environ=None):
        return locator.locate_fresh_sdk_original_upload(instance, original,
            expected_receipt_sha256=digest or sha256_bytes(original.receipt_bytes),
            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token",
            environ={} if environ is None else environ)

    def test_fresh_pin_is_derived_from_official_worker_not_observed_state(self):
        for family in ("javascript", "core", "android"):
            with self.subTest(family=family):
                instance, ready, original, raw = self.selected(
                    core=family == "core",
                    android_phase="package" if family == "android" else None)
                job, _ = locator.fresh_sdk_worker_route(instance,
                    validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes)))
                arguments = dict(producer=self.fixture.producer, expected_build_key=ready["buildKey"],
                    expected_product_version="0.3.0", trusted_workflow_sha=fixture_module.PIN,
                    trusted_workflow_path=".github/workflows/product-validation.yml",
                    trusted_job_name=job, token="synthetic-token", environ={})
                with self.fixture.official_api({instance: ready}, {instance: raw}) as (_, _, download):
                    pin = locator.discover_fresh_sdk_original_pin(instance, **arguments)
                    self.assertEqual(sha256_bytes(original.receipt_bytes), pin["receipt_sha256"])
                    self.assertEqual(sha256_bytes(raw), pin["artifact_sha256"])
                    self.assertEqual(901, pin["artifact_id"])
                    self.assertEqual(job, pin["job_name"])
                    self.assertIsInstance(FreshSdkOriginalPin(**pin), FreshSdkOriginalPin)
                    download.assert_called_once()
                    with self.assertRaisesRegex(ValueError, "independent phase identity"):
                        locator.discover_fresh_sdk_original_pin(
                            instance, **{**arguments, "expected_product_version": "0.9.0"})
                with patch.object(locator.products, "api_json") as api, \
                     self.assertRaisesRegex(ValueError, "independent version, token and workflow route"):
                    locator.discover_fresh_sdk_original_pin(instance,
                        **{**arguments, "trusted_job_name": ""})
                api.assert_not_called()
                with patch.dict(locator.os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}), \
                     patch.object(locator.products, "api_json") as api, \
                     self.assertRaisesRegex(ValueError, "signing-secret"):
                    locator.discover_fresh_sdk_original_pin(instance, **arguments)
                api.assert_not_called()

    def test_core_and_noncore_official_locator_feed_exact_worker_verifier(self):
        for core in (True, False):
            with self.subTest(core=core):
                instance, ready, original, raw = self.selected(core=core)
                expected_job, expected_name = locator.fresh_sdk_worker_route(
                    instance, validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes)))
                self.assertEqual("product-validation / sdk-core-package-common" if core
                                 else "product-validation / sdk-javascript-package-node", expected_job)
                self.assertTrue(expected_name.startswith("codex-agent-sdk-worker-"))
                with self.fixture.official_api({instance: ready}, {instance: raw}) as (_, _, download):
                    pin = self.locate(instance, original)
                    self.assertEqual({"artifact_id": 901, "artifact_sha256": sha256_bytes(raw)}, pin)
                    self.assertFalse(download.called)
                    with worker.held_fresh_sdk_worker_upload(instance, original,
                            canonical_json_bytes({"captureProducer": self.fixture.producer}),
                            expected_receipt_sha256=sha256_bytes(original.receipt_bytes),
                            artifact_id=pin["artifact_id"], artifact_sha256=pin["artifact_sha256"],
                            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={}) as (evidence, _):
                        self.assertEqual(901, evidence["artifact"]["id"])
                    download.assert_called_once()

    def test_independent_receipt_digest_and_reused_state_reject_before_api(self):
        instance, _, original, _ = self.selected()
        reused = replace(original, replay_record_canonical=canonical_json_bytes({
            **load_canonical_json_bytes(original.replay_record_canonical),
            "state": "reused", "source": "same-pr", "transportSource": {"kind": "same-pr"}}))
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "independent"):
            self.locate(instance, original, digest="sha256:" + "0" * 64)
        api.assert_not_called()
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "retained"):
            self.locate(instance, reused)
        api.assert_not_called()

    def test_ambiguous_listing_and_detail_mismatch_reject(self):
        instance, ready, original, raw = self.selected()
        with self.fixture.official_api({instance: ready}, {instance: raw}) as (_, listing, download):
            previous = listing.side_effect
            listing.side_effect = lambda url, field, token: (
                previous(url, field, token) * 2 if field == "artifacts" else previous(url, field, token))
            with self.assertRaisesRegex(ValueError, "ambiguous"):
                self.locate(instance, original)
            download.assert_not_called()
        with self.fixture.official_api({instance: ready}, {instance: raw}) as (query, _, download):
            previous = query.side_effect
            def wrong_detail(url, token):
                value = previous(url, token)
                return {**value, "digest": "sha256:" + "0" * 64} if "/actions/artifacts/" in url else value
            query.side_effect = wrong_detail
            with self.assertRaisesRegex(ValueError, "differs"):
                self.locate(instance, original)
            download.assert_not_called()

    def test_four_android_original_routes_match_worker_uploads(self):
        producer = self.fixture.producer
        for phase in ("binary", "package", "validation", "metadata"):
            with self.subTest(phase=phase):
                instance, _, original, raw = self.selected(android_phase=phase)
                receipt = validate_phase_receipt(load_canonical_json_bytes(original.receipt_bytes))
                job, name = locator.fresh_sdk_worker_route(instance, receipt)
                self.assertEqual(f"product-validation / sdk-sdk-android-{phase}-android", job)
                self.assertEqual(f"codex-agent-sdk-worker-sdk-android-{phase}-android-"
                    f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}", name)
                with self.fixture.official_api({instance: receipt}, {instance: raw}) as (_, _, download):
                    pin = self.locate(instance, original)
                    self.assertEqual({"artifact_id": 901, "artifact_sha256": sha256_bytes(raw)}, pin)
                    download.assert_not_called()
                    with worker.held_fresh_sdk_worker_upload(instance, original,
                            canonical_json_bytes({"captureProducer": producer}),
                            expected_receipt_sha256=sha256_bytes(original.receipt_bytes),
                            artifact_id=pin["artifact_id"], artifact_sha256=pin["artifact_sha256"],
                            trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={}) as (evidence, _):
                        self.assertEqual(901, evidence["artifact"]["id"])
                    download.assert_called_once()

    def test_invalid_android_route_and_signing_context_reject_before_api(self):
        instance, _, original, _ = self.selected()
        android = PhaseInstanceId("sdk", "sdk-android", "package", "desktop")
        with self.assertRaisesRegex(ValueError, "one exact worker phase"):
            locator.fresh_sdk_worker_route(android, {"producer": self.fixture.producer})
        with patch.object(locator.products, "api_json") as api, self.assertRaisesRegex(ValueError, "signing-secret"):
            self.locate(instance, original, environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""})
        api.assert_not_called()
