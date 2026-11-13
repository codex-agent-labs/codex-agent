"""Protected SDK original catalog capture, using synthetic official API bytes."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.sdk_catalog_promotion_caller import (
    capture_official_sdk_phase10_index, capture_promotable_sdk_original_catalog,
    sign_promoted_sdk_catalog,
)
from ci.products.index import IndexEntrySource
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, sha256_file, snapshot_regular_tree,
)
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object
from ci.products.sdk_campaign_dev_catalog import stage_sdk_same_pr_catalog
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen required")
class SdkCatalogPromotionCallerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-catalog-capture-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 71,
            "runAttempt": 2, "pullRequest": 31}
        sources, envelopes, archives, paths = {}, {}, {}, {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            phase = self.root / f"phase-{position}"
            stage = phase / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(phase / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": self.producer})
            plan = {key: receipt[key] for key in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            completed = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=self.producer, product_version="0.8.0", trust_domain="development",
                destination=phase / "shard")
            sources[instance] = IndexEntrySource(completed["receiptBytes"],
                                                 "outputs/fixture/content.bin")
            envelopes[instance] = {key: completed[key] for key in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            archives[instance] = phase / "shard" / completed["objectPath"]
            paths[instance] = sources[instance].artifact_path
        self.catalog = self.root / "catalog"
        stage_sdk_same_pr_catalog(sources, envelopes, archives,
            producer=self.producer, destination=self.catalog)
        self.index_sha = sha256_file(self.catalog / "product-index.json")
        self.key_sha = sha256_file(self.catalog / "public-key.pub")
        self.upload = archive({item["relativePath"]: (self.catalog / item["relativePath"]).read_bytes()
                               for item in regular_file_inventory(self.catalog)})
        self.name = ("codex-agent-product-catalog-v1-pull-request-31-"
                     f"{self.producer['tree']}-attempt-2")
        self.artifact = {"id": 902, "digest": sha256_bytes(self.upload),
            "expired": False, "name": self.name,
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/902/zip",
            "size_in_bytes": len(self.upload), "created_at": "2026-01-01T00:05:00Z",
            "workflow_run": {"id": 71, "head_sha": self.producer["commit"]}}
        self.workflow_sha = "c" * 40
        self.signed_index_sha = sha256_bytes(b"independent Phase-10 signed index")
        self.object_pins = self.root / "object-pins.json"
        self.object_pins.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "signedIndexSha256": self.signed_index_sha,
            "objects": [{"product": instance.product, "component": instance.component,
                "phase": instance.phase, "target": instance.target,
                "buildKey": envelopes[instance]["receipt"]["buildKey"],
                "receiptSha256": envelopes[instance]["receiptSha256"],
                "objectSha256": envelopes[instance]["objectSha256"],
                "relativePath": completed_path(envelopes[instance])}
                for instance in sorted(SDK_CAMPAIGN_INSTANCES)]}))
        self.authority = self.root / "authority.json"
        self.authority.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "product": "sdk", "sdkVersion": "0.8.0",
            "electionSha256": {family: sha256_bytes(family.encode())
                for family in ("core-android", "native", "apple-js")},
            "semanticSha256": {family: sha256_bytes((family + "semantic").encode())
                for family in ("core-android", "native", "apple-js")},
            "artifactPaths": [{"identity": {name: getattr(instance, name)
                for name in ("product", "component", "phase", "target")},
                "relativePath": paths[instance]}
                for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
            "completedCatalogPin": {"producer": self.producer,
                "artifact_name": self.name, "artifact_id": 902,
                "artifact_sha256": self.artifact["digest"], "index_sha256": self.index_sha,
                "public_key_sha256": self.key_sha,
                "trusted_workflow_path": ".github/workflows/product-validation.yml",
                "trusted_job_name": "product-validation / sdk-catalog"}}))
        self.destination = self.root / "captured"

    def _capture(self, *, job_completed_at="2026-01-01T00:10:00Z", **changes):
        run = {"id": 71, "run_attempt": 2, "path": ".github/workflows/ci.yml",
               "head_sha": self.producer["commit"]}
        observed = {"run": run, "testedCommit": {"sha": self.producer["commit"],
            "tree": {"sha": self.producer["tree"]}}, "jobs": [{"name":
            "product-validation / sdk-catalog", "started_at": "2026-01-01T00:00:00Z",
            "completed_at": job_completed_at}]}
        args = dict(expected_authority_sha256=sha256_file(self.authority),
            expected_object_pins_sha256=sha256_file(self.object_pins),
            expected_signed_index_sha256=self.signed_index_sha,
            expected_catalog_artifact_size=len(self.upload),
            trusted_workflow_sha=self.workflow_sha, token="synthetic-token", environ={})
        with patch("ci.sdk_campaign_reused_original.product_reuse.api_json", return_value=self.artifact), \
             patch("ci.sdk_campaign_reused_original.product_reuse.download_artifact_to_file",
                   side_effect=lambda _artifact, _token, destination, **_kw:
                       Path(destination).write_bytes(self.upload)), \
             patch("ci.sdk_campaign_reused_original.product_reuse._same_pr_run",
                   return_value={key: observed[key] for key in ("run", "testedCommit")}), \
             patch("ci.sdk_campaign_reused_original.product_reuse._observe_ci_producer_jobs",
                   return_value=[observed]):
            return capture_promotable_sdk_original_catalog(
                self.authority, self.object_pins, self.destination, **{**args, **changes})

    def test_exact_official_catalog_and_all_objects_are_captured(self):
        result = self._capture()
        self.assertEqual(result["artifactSha256"], self.artifact["digest"])
        self.assertEqual((self.destination / "official-catalog.zip").read_bytes(), self.upload)
        self.assertEqual((self.destination / "object-pins.json").read_bytes(),
                         self.object_pins.read_bytes())

    def test_wrong_independent_pin_fails_before_observation(self):
        with patch("ci.sdk_campaign_reused_original.held_completed_sdk_catalog",
                   side_effect=AssertionError("official API must not be reached")):
            with self.assertRaisesRegex(ValueError, "independent S1048"):
                self._capture(expected_object_pins_sha256=sha256_bytes(b"wrong"))
        self.assertFalse(self.destination.exists())

    def test_wrong_upload_size_digest_and_job_window_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "protected pin"):
            self._capture(expected_catalog_artifact_size=len(self.upload) + 1)
        self.assertFalse(self.destination.exists())
        original = self.artifact
        self.artifact = {**original, "digest": sha256_bytes(b"forged upload")}
        try:
            with self.assertRaisesRegex(ValueError, "official artifact identity"):
                self._capture()
        finally:
            self.artifact = original
        self.assertFalse(self.destination.exists())
        with self.assertRaisesRegex(ValueError, "original job-attempt window"):
            self._capture(job_completed_at="2026-01-01T00:01:00Z")
        self.assertFalse(self.destination.exists())

    def test_capture_rejects_signing_secret_before_observation(self):
        with patch.dict("os.environ", {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"}), \
             patch("ci.sdk_catalog_promotion_caller.held_completed_sdk_catalog",
                   side_effect=AssertionError("official API must not be reached")):
            with self.assertRaisesRegex(ValueError, "signing-secret context"):
                self._capture()
        self.assertFalse(self.destination.exists())

    def test_fixed_protected_index_upload_is_observed_before_capture(self):
        original = self.root / "phase10-original"
        original.mkdir()
        landed = self.root / "landed-fixture"
        landed.mkdir()
        (original / "marker.json").write_bytes(canonical_json_bytes({"index": "pinned"}))
        raw = archive({"marker.json": (original / "marker.json").read_bytes()})
        producer = {**self.producer, "event": "workflow_dispatch", "pullRequest": None,
                    "runId": 92, "runAttempt": 3}
        pins = {"producerSha256": sha256_bytes(canonical_json_bytes(producer)),
            "artifactId": 904, "artifactSha256": sha256_bytes(raw),
            "artifactSize": len(raw), "trustedWorkflowSha": "d" * 40,
            "captureInventorySha256": sha256_bytes(canonical_json_bytes(
                regular_file_inventory(original)))}
        observed = {"run": {"id": 92, "run_attempt": 3,
            "status": "completed", "conclusion": "success"},
            "jobs": [{"name": "sdk-phase10-maven-sidecars / sdk-phase10-maven-sidecars",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:10:00Z"}]}
        artifact = {"id": 904, "digest": pins["artifactSha256"],
            "size_in_bytes": len(raw), "created_at": "2026-01-01T00:05:00Z"}
        handoff = {"expected_source_tree": self.producer["tree"]}
        target = self.root / "official-index"

        def download(_id, _digest, name, _producer, _run, _token, *, destination, **_kw):
            self.assertEqual(name, "codex-agent-sdk-phase10-maven-index-admission-"
                             f"{self.producer['tree']}-attestation-92-attempt-3")
            Path(destination).write_bytes(raw)
            return artifact, Path(destination)

        def forward(source, destination, **_kw):
            snapshot_regular_tree(source, destination)

        with patch("ci.sdk_catalog_promotion_caller.product_reuse._observe_ci_producer_jobs",
                   return_value=[observed]) as observation, \
             patch("ci.sdk_catalog_promotion_caller.product_reuse._download_contract_ci_upload",
                   side_effect=download), \
             patch("ci.sdk_catalog_promotion_caller.forward_verified_sdk_phase10_bytes",
                   side_effect=forward):
            result = capture_official_sdk_phase10_index(producer, pins, target,
                landed_repository=landed, index_handoff_pins=handoff,
                token="synthetic-token", environ={})
        self.assertEqual(result["artifactSha256"], pins["artifactSha256"])
        self.assertEqual((target / "official-upload.zip").read_bytes(), raw)
        self.assertEqual((target / "phase10/marker.json").read_bytes(),
                         (original / "marker.json").read_bytes())
        self.assertEqual(observation.call_args.kwargs["trusted_workflows_by_phase"],
            {"index": {"path": ".github/workflows/sdk-phase10-maven-sidecars.yml",
                       "sha": "d" * 40}})
        self.assertEqual(observation.call_args.kwargs["jobs_by_phase"],
                         {"index": "sdk-phase10-maven-sidecars / sdk-phase10-maven-sidecars"})
        with patch("ci.sdk_catalog_promotion_caller.product_reuse._observe_ci_producer_jobs",
                   side_effect=AssertionError("observer must not run")):
            with self.assertRaisesRegex(ValueError, "independent approval"):
                capture_official_sdk_phase10_index(producer,
                    {**pins, "producerSha256": sha256_bytes(b"wrong")},
                    self.root / "bad-index", landed_repository=landed,
                    index_handoff_pins=handoff, token="synthetic-token", environ={})

    def test_signer_joins_exact_captures_and_rejects_observation_token(self):
        captured = self._capture()
        private, public, development = generate_development_key(self.root / "signer-key")
        keys = self.root / "release-keys"
        keys.mkdir()
        signing = {**development, "trustDomain": "release", "keyId": "release-test"}
        (keys / "release-test.pub").write_bytes(public.read_bytes())
        keyring = self.root / "release-keyring.json"
        keyring.write_bytes(canonical_json_bytes({"schemaVersion": 1,
            "namespace": signing["namespace"], "algorithm": signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": "release-test",
                "fingerprint": signing["fingerprint"]}, "retiredKeys": []}))
        campaign = load_canonical_json_bytes((self.catalog / "product-index.json").read_bytes())
        campaign.update(trustDomain="release", signing=signing)
        phase10 = self.root / "phase10"
        pair = phase10 / "signed-pair"
        pair.mkdir(parents=True)
        index_path = pair / "product-index.json"
        index_path.write_bytes(canonical_json_bytes(campaign))
        sign_manifest(index_path, private, signing)
        index_pin = sha256_file(index_path)
        self.signed_index_sha = index_pin
        self.object_pins.write_bytes(canonical_json_bytes({
            **load_canonical_json_bytes(self.object_pins.read_bytes()),
            "signedIndexSha256": index_pin}))
        # The token-only capture must itself be re-elected with the new pin file.
        self.destination = self.root / "recaptured"
        recaptured = self._capture()
        landing = self.root / "landed"
        landing.mkdir()
        subprocess.run(["git", "init", "-q", str(landing)], check=True)
        subprocess.run(["git", "-C", str(landing), "-c", "user.name=SDK Test",
                        "-c", "user.email=sdk-test@example.invalid", "commit", "-q",
                        "--allow-empty", "-m", "landed synthetic checkout"], check=True)
        landed_head = subprocess.check_output(["git", "-C", str(landing),
                                               "rev-parse", "HEAD"], text=True).strip()
        output = self.root / "promoted"
        push = {**self.producer, "event": "push", "pullRequest": None,
                "runId": 91, "commit": landed_head, "tree": self.producer["tree"]}
        context = {"kind": "promoted-main", "commit": push["commit"],
                   "tree": push["tree"], "promotionRunId": 91,
                   "promotionRunAttempt": push["runAttempt"]}
        dig = sha256_bytes(b"separately approved synthetic input")
        handoff = dict(expected_inventory_sha256=dig, expected_index_sha256=index_pin,
            expected_signature_sha256=sha256_file(pair / "product-index.sig"),
            expected_authority_sha256=sha256_file(self.authority),
            expected_signed_upload_sha256=dig, expected_authority_upload_sha256=dig,
            expected_authority_transport_sha256=dig,
            expected_keyring_sha256=sha256_file(keyring),
            expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                regular_file_inventory(keys))), expected_sdk_version="0.8.0",
            expected_source_commit=self.producer["commit"],
            expected_source_tree=self.producer["tree"],
            expected_validation_tree=self.producer["tree"])
        carrier_producer = {**self.producer, "event": "workflow_dispatch",
            "pullRequest": None, "runId": 92, "runAttempt": 3}
        carrier_upload = archive({row["relativePath"]: (phase10 / row["relativePath"]).read_bytes()
                                  for row in regular_file_inventory(phase10)})
        carrier_pins = {"producerSha256": sha256_bytes(canonical_json_bytes(carrier_producer)),
            "artifactId": 904, "artifactSha256": sha256_bytes(carrier_upload),
            "artifactSize": len(carrier_upload), "trustedWorkflowSha": "d" * 40,
            "captureInventorySha256": sha256_bytes(canonical_json_bytes(
                regular_file_inventory(phase10)))}
        carrier_name = ("codex-agent-sdk-phase10-maven-index-admission-"
            f"{self.producer['tree']}-attestation-92-attempt-3")
        carrier_artifact = {"id": 904, "digest": carrier_pins["artifactSha256"],
            "size_in_bytes": len(carrier_upload), "name": carrier_name,
            "created_at": "2026-01-01T00:05:00Z",
            "workflow_run": {"id": 92, "head_sha": carrier_producer["commit"]}}
        carrier_observed = {"run": {"id": 92, "run_attempt": 3,
            "path": ".github/workflows/ci.yml", "event": "workflow_dispatch",
            "head_sha": carrier_producer["commit"], "status": "completed",
            "conclusion": "success"},
            "testedCommit": {"sha": carrier_producer["commit"],
                "tree": {"sha": carrier_producer["tree"]}},
            "jobs": [{"name": "sdk-phase10-maven-sidecars / sdk-phase10-maven-sidecars",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:10:00Z",
                "status": "completed", "conclusion": "success"}]}
        carrier = self.root / "official-index-carrier"
        carrier.mkdir()
        snapshot_regular_tree(phase10, carrier / "phase10", allow_empty=False)
        (carrier / "official-upload.zip").write_bytes(carrier_upload)
        (carrier / "transport.json").write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "producer": carrier_producer,
            "observed": carrier_observed, "artifact": carrier_artifact,
            "trustedWorkflowSha": carrier_pins["trustedWorkflowSha"]}))
        args = dict(expected_catalog_capture_inventory_sha256=recaptured["inventorySha256"],
            expected_authority_sha256=sha256_file(self.authority),
            expected_object_pins_sha256=sha256_file(self.object_pins),
            expected_catalog_artifact_size=len(self.upload),
            trusted_workflow_sha=self.workflow_sha, index_handoff_pins=handoff,
            index_carrier_producer=carrier_producer, index_carrier_pins=carrier_pins,
            expected_index_carrier_inventory_sha256=sha256_bytes(canonical_json_bytes(
                regular_file_inventory(carrier))),
            repository=self.producer["repository"], context=context, producer=push,
            keyring=keyring, keys_directory=keys, private_key=private, environ={})
        with self.assertRaisesRegex(ValueError, "Phase-10 landed tree"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output,
                **{**args, "producer": {**push, "tree": "f" * 40},
                   "context": {**context, "tree": "f" * 40}})
        with self.assertRaisesRegex(ValueError, "Phase-10 landed tree"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output,
                **{**args, "context": {**context, "tree": "f" * 40}})
        with self.assertRaisesRegex(ValueError, "landed checkout HEAD"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output,
                **{**args, "producer": {**push, "commit": "e" * 40},
                   "context": {**context, "commit": "e" * 40}})
        with self.assertRaisesRegex(ValueError, "landed checkout HEAD"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output,
                **{**args, "context": {**context, "commit": "e" * 40}})
        original_keyring = keyring.read_bytes()
        _, retired_public, retired = generate_development_key(self.root / "retired-key")
        (keys / "retired-test.pub").write_bytes(retired_public.read_bytes())
        changed_policy = load_canonical_json_bytes(original_keyring)
        changed_policy["retiredKeys"] = [{"keyId": "retired-test",
            "fingerprint": retired["fingerprint"]}]
        keyring.write_bytes(canonical_json_bytes(changed_policy))
        with self.assertRaisesRegex(ValueError, "pinned Phase-10 policy"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output, **args)
        keyring.write_bytes(original_keyring)
        (keys / "retired-test.pub").unlink()
        self.assertFalse(output.exists())

        transport_path = self.destination / "transport.json"
        original_transport = transport_path.read_bytes()
        forged = load_canonical_json_bytes(original_transport)
        forged["observed"][0]["run"]["id"] = 72
        transport_path.write_bytes(canonical_json_bytes(forged))
        forged_inventory = sha256_bytes(canonical_json_bytes(
            regular_file_inventory(self.destination)))
        with self.assertRaisesRegex(ValueError, "producer observation"):
            sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output,
                **{**args, "expected_catalog_capture_inventory_sha256": forged_inventory})
        transport_path.write_bytes(original_transport)
        self.assertFalse(output.exists())

        def verified_forward(_source, destination, **_pins):
            snapshot_regular_tree(phase10, destination)
            evidence = destination / "replay-evidence"
            evidence.mkdir()
            (evidence / "product-signing-keys.json").write_bytes(keyring.read_bytes())
            snapshot_regular_tree(keys, evidence / "keys")

        with patch("ci.sdk_catalog_promotion_caller.forward_verified_sdk_phase10_bytes",
                   side_effect=verified_forward) as forwarded:
            local_change = carrier / "phase10/signed-pair/product-index.json"
            original_index = local_change.read_bytes()
            local_change.write_bytes(b"caller-local replacement")
            with self.assertRaisesRegex(ValueError, "inner bytes"):
                sign_promoted_sdk_catalog(self.destination, carrier,
                    self.authority, self.object_pins, landing, output,
                    **{**args, "expected_index_carrier_inventory_sha256": sha256_bytes(
                        canonical_json_bytes(regular_file_inventory(carrier)))})
            local_change.write_bytes(original_index)
            with self.assertRaisesRegex(ValueError, "observation token"):
                sign_promoted_sdk_catalog(self.destination, carrier,
                    self.authority, self.object_pins, landing, output,
                    **{**args, "environ": {"GITHUB_TOKEN": "synthetic"}})
            forwarded.assert_not_called()
            with patch("ci.sdk_catalog_promotion_caller._landed_commit",
                       side_effect=[landed_head, "f" * 40]) as changing_head:
                with self.assertRaisesRegex(ValueError, "HEAD changed during catalog signing"):
                    sign_promoted_sdk_catalog(self.destination, carrier,
                        self.authority, self.object_pins, landing, output, **args)
            self.assertEqual(changing_head.call_count, 2)
            self.assertFalse(output.exists())
            result = sign_promoted_sdk_catalog(self.destination, carrier,
                self.authority, self.object_pins, landing, output, **args)
        self.assertEqual(len(result["entries"]), 62)
        self.assertEqual(result["context"], context)
        self.assertTrue((output / "product-index.sig").is_file())


def completed_path(envelope):
    from ci.products.restore import object_relative_path
    return object_relative_path(envelope["receipt"]["buildKey"], envelope["receiptSha256"])
