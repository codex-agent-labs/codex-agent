"""The observed state is transport; original receipt and reuse provenance stay intact."""

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from ci import sdk_campaign_observation as observed
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import finalize_phase_object
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.tests.product_chain_support import write_receipt
from ci.tests import test_runtime_resume_capture as resume_fixture


class SdkCampaignObservationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-campaign-observation-test-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.sources, cls.records = {}, {}
        producer = {"repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            directory = cls.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(directory / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=producer, product_version="0.8.0", trust_domain="development",
                destination=directory / "shard")
            cls.sources[instance] = directory / "shard" / finalized["objectPath"]
            cls.records[instance] = {"product": instance.product, "component": instance.component,
                "phase": instance.phase, "target": instance.target, "state": "reused",
                "buildKey": receipt["buildKey"], "receiptSha256": finalized["receiptSha256"],
                "objectSha256": finalized["objectSha256"], "source": "same-pr",
                "transportSource": {"originalRunId": 3}}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def observe(self, state, *, expected_wave=18, expected_state_wave=0):
        transport = {"artifact": {"id": 7, "digest": "sha256:" + "c" * 64},
                     "captureProducer": {"runId": 9}}

        def capture(plan, destination, **kwargs):
            self.assertEqual(kwargs["artifact_id"], 7)
            self.assertEqual(kwargs["sdk_state_wave"], expected_wave)
            self.assertEqual(kwargs["state_wave"], expected_state_wave)
            (destination / "original/product-resume-inputs/plan").mkdir(parents=True)
            (destination / "original/product-resume-state").mkdir()
            if expected_wave is not None or expected_state_wave:
                (destination / "original/runtime-state").mkdir()
            (destination / "original/product-resume-inputs/plan/impact-plan.json").write_bytes(b"{}\n")
            write_canonical_json(destination / "capture-transport.json", transport)
            return transport

        def verify(plan, discovery, state_root, *_args, **_kwargs):
            self.assertTrue(discovery.is_dir())
            advanced = expected_wave is not None or expected_state_wave
            self.assertEqual(state_root, discovery if not advanced
                             else discovery.parent / "runtime-state")
            self.assertEqual((discovery.parent / "runtime-state").exists(), bool(advanced))
            return state

        return patch.object(observed.product_reuse, "capture_runtime_resume_upload", side_effect=capture), \
            patch.object(observed.product_reuse, "_verified_product_state", side_effect=verify)

    def kwargs(self):
        return dict(artifact_id=7, artifact_sha256="sha256:" + "c" * 64,
            trusted_workflow_sha="d" * 40, sdk_state_wave=18,
            repository_root=self.root, environ={}, token="unused")

    def test_holds_all_originals_and_preserves_reuse_provenance(self):
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)
        capture, replay = self.observe(state)
        with capture, replay, observed.held_sdk_campaign_observation(self.root / "plan.json", **self.kwargs()) as (
                transport, originals):
            self.assertEqual(len(originals), 61)
            self.assertEqual(load_canonical_json_bytes(transport)["artifact"]["id"], 7)
            first = min(SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(originals[first].replay_record_canonical, canonical_json_bytes(self.records[first]))
            self.assertEqual(load_canonical_json_bytes(originals[first].receipt_bytes)["producer"]["runId"], 3)
            self.assertEqual((originals[first].stage_path / "outputs/fixture/content.bin").read_bytes(),
                             str(first).encode())

    def test_missing_original_fails_closed(self):
        missing = min(SDK_CAMPAIGN_INSTANCES)
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases={key: value for key, value in self.records.items() if key != missing},
            sources=self.sources)
        capture, replay = self.observe(state)
        with capture, replay, self.assertRaisesRegex(ValueError, "lacks an original phase object"):
            with observed.held_sdk_campaign_observation(self.root / "plan.json", **self.kwargs()):
                pass

    def test_full_reuse_uses_original_resume_upload(self):
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)
        capture, replay = self.observe(state, expected_wave=None)
        selected = {**self.kwargs(), "sdk_state_wave": None}
        with capture, replay, observed.held_sdk_campaign_observation(self.root / "plan.json", **selected) as (_, originals):
            self.assertEqual(set(originals), SDK_CAMPAIGN_INSTANCES)

    def test_full_reuse_reads_real_observed_resume_shape(self):
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)

        def verified(_plan, discovery, state_root, *_args, **_kwargs):
            self.assertEqual(discovery, state_root)
            self.assertEqual({"product-resume-inputs", "product-resume-state"},
                {path.name for path in discovery.parent.iterdir()})
            return state

        with patch.object(observed.product_reuse, "api_json",
                          side_effect=[fixture.run, fixture.commit, fixture.artifact]), \
             patch.object(observed.product_reuse, "paginated_items", return_value=[fixture.job]), \
             patch.object(observed.product_reuse, "download_artifact", return_value=fixture.raw), \
             patch.object(observed.product_reuse, "_verified_product_state", side_effect=verified), \
             observed.held_sdk_campaign_observation(fixture.plan_path,
                 artifact_id=101, artifact_sha256=fixture.artifact["digest"],
                 trusted_workflow_sha=fixture.pin, sdk_state_wave=None,
                 repository_root=fixture.root, environ=fixture.environment,
                 token="not-a-real-token") as (transport, originals):
            self.assertEqual(set(originals), SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(load_canonical_json_bytes(transport)["artifact"], fixture.artifact)

    def test_runtime_wave_five_reads_exact_advanced_shape(self):
        fixture = resume_fixture.RuntimeResumeCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)
        raw = resume_fixture.archive({**fixture.contents,
            "runtime-state/reuse-wave-result.json": b"synthetic advanced state\n"})
        artifact = {**fixture.artifact,
            "name": f"codex-agent-runtime-wave-5-state-{fixture.producer['tree']}-attempt-3",
            "digest": sha256_bytes(raw), "size_in_bytes": len(raw)}
        job = {**fixture.job, "name": "product-validation / runtime-collect-5"}

        def verified(_plan, discovery, state_root, *_args, **_kwargs):
            self.assertEqual(state_root, discovery.parent / "runtime-state")
            self.assertEqual({"product-resume-inputs", "product-resume-state", "runtime-state"},
                {path.name for path in discovery.parent.iterdir()})
            return state

        with patch.object(observed.product_reuse, "api_json",
                          side_effect=[fixture.run, fixture.commit, artifact]), \
             patch.object(observed.product_reuse, "paginated_items", return_value=[job]), \
             patch.object(observed.product_reuse, "download_artifact", return_value=raw), \
             patch.object(observed.product_reuse, "_verified_product_state", side_effect=verified), \
             observed.held_sdk_campaign_observation(fixture.plan_path,
                 artifact_id=101, artifact_sha256=artifact["digest"],
                 trusted_workflow_sha=fixture.pin, state_wave=5, sdk_state_wave=None,
                 repository_root=fixture.root, environ=fixture.environment,
                 token="not-a-real-token") as (transport, originals):
            self.assertEqual(set(originals), SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(load_canonical_json_bytes(transport)["artifact"], artifact)

    def test_runtime_and_sdk_waves_cannot_mix(self):
        with patch.object(observed.product_reuse, "api_json") as query, \
             self.assertRaisesRegex(ValueError, "SDK state wave"):
            with observed.held_sdk_campaign_observation(self.root / "plan.json",
                    **{**self.kwargs(), "state_wave": 5}):
                pass
        query.assert_not_called()

    def test_signing_secret_rejected_before_capture(self):
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)
        capture, replay = self.observe(state)
        selected = {**self.kwargs(), "environ": {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}}
        with capture as download, replay, self.assertRaisesRegex(ValueError, "signing-secret context"):
            with observed.held_sdk_campaign_observation(self.root / "plan.json", **selected):
                pass
        download.assert_not_called()

    def test_late_stage_mutation_fails_closed(self):
        state = SimpleNamespace(prior_by_instance=self.records,
            prior_carrier_phases=self.records, sources=self.sources)
        capture, replay = self.observe(state)
        with capture, replay, self.assertRaisesRegex(ValueError, "changed during replay"):
            with observed.held_sdk_campaign_observation(self.root / "plan.json", **self.kwargs()) as (_, originals):
                first = min(SDK_CAMPAIGN_INSTANCES)
                (originals[first].stage_path / "outputs/fixture/content.bin").write_bytes(b"tampered")
