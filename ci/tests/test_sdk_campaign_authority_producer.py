"""The SDK authority upload contains only independently pinned source bytes."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from ci.sdk_campaign_authority_producer import stage_sdk_campaign_authority
from products.inventory import canonical_json_bytes, sha256_bytes
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


_ROOT = Path(__file__).resolve().parents[2]
_DIGEST = "sha256:" + "a" * 64
_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/product-validation.yml",
    "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
    "runId": 71, "runAttempt": 2, "pullRequest": 31}


def _authority() -> bytes:
    return canonical_json_bytes({
        "schemaVersion": 1, "product": "sdk", "sdkVersion": "0.8.0",
        "electionSha256": {family: _DIGEST for family in
            ("core-android", "native", "apple-js")},
        "semanticSha256": {family: _DIGEST for family in
            ("core-android", "native", "apple-js")},
        "artifactPaths": [{"identity": {field: getattr(instance, field)
            for field in ("product", "component", "phase", "target")},
            "relativePath": "outputs/package.bin"}
            for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
        "completedCatalogPin": {"producer": dict(_PRODUCER),
            "artifact_name": "sdk-catalog", "artifact_id": 7,
            "artifact_sha256": _DIGEST, "index_sha256": _DIGEST,
            "public_key_sha256": _DIGEST,
            "trusted_workflow_path": ".github/workflows/product-validation.yml",
            "trusted_job_name": "product-validation / sdk-catalog"},
    })


class SdkCampaignAuthorityProducerTest(TestCase):
    def test_exact_single_file_and_external_input_provenance(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary).resolve()
            source, destination = root / "approved.json", root / "upload"
            raw = _authority()
            source.write_bytes(raw)
            result = stage_sdk_campaign_authority(source, sha256_bytes(raw), destination)
            self.assertEqual(["sdk-campaign-authority.json"],
                [item.name for item in destination.iterdir()])
            self.assertEqual(raw, (destination / "sdk-campaign-authority.json").read_bytes())
            self.assertEqual({"inputPath": str(source),
                "inputSha256": sha256_bytes(raw),
                "outputPath": str(destination / "sdk-campaign-authority.json"),
                "outputSha256": sha256_bytes(raw)}, result)
            with self.assertRaisesRegex(ValueError, "must not exist"):
                stage_sdk_campaign_authority(source, sha256_bytes(raw), destination)

    def test_wrong_approval_or_bad_schema_never_publishes(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary).resolve()
            source, destination = root / "approved.json", root / "upload"
            raw = _authority()
            source.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "independent digest"):
                stage_sdk_campaign_authority(source, "sha256:" + "0" * 64,
                    destination)
            self.assertFalse(destination.exists())
            source.write_bytes(canonical_json_bytes({"schemaVersion": 1}))
            with self.assertRaisesRegex(ValueError, "fields are invalid"):
                stage_sdk_campaign_authority(source,
                    sha256_bytes(source.read_bytes()), destination)
            self.assertFalse(destination.exists())

    def test_source_mutation_before_publish_rejects_without_output(self):
        with TemporaryDirectory(dir=_ROOT) as temporary:
            root = Path(temporary).resolve()
            source, destination = root / "approved.json", root / "upload"
            raw = _authority()
            source.write_bytes(raw)

            from ci import sdk_campaign_authority_producer as producer
            original = producer.read_regular_file_bytes
            calls = 0

            def mutate_after_snapshot(path, **kwargs):
                nonlocal calls
                result = original(path, **kwargs)
                calls += 1
                if calls == 1:
                    source.write_bytes(b"changed\n")
                return result

            with patch.object(producer, "read_regular_file_bytes", mutate_after_snapshot):
                with self.assertRaisesRegex(ValueError, "changed during replay"):
                    stage_sdk_campaign_authority(source, sha256_bytes(raw), destination)
            self.assertFalse(destination.exists())
