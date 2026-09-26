"""An in-progress nested SDK upload can carry an original partial phase object.

The full product-state planner is a separate gate; only official HTTP is mocked
here, along with that planner's already-verified state projection.
"""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_resume_capture as resume_fixture
from ci.products.index import SignedProductIndex, verify_signed_product_index
from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object, object_relative_path
from ci.sdk_campaign_partial_catalog_caller import SDK_CAMPAIGN_INSTANCES, stage_partial_sdk_catalog
from ci.sdk_nested_wave_locator import _COLLECTORS
from ci.tests.product_chain_support import write_receipt


product_reuse = resume_fixture.product_reuse


class NestedPartialIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = resume_fixture.RuntimeResumeCaptureTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.instance = next(instance for instance in SDK_CAMPAIGN_INSTANCES
            if (instance.component, instance.phase, instance.target) ==
               ("sdk-core", "binary", "common"))
        stage = self.root / "phase/stage"
        output = stage / "outputs/fixture"
        output.mkdir(parents=True)
        (output / "content.bin").write_bytes(b"sdk-core binary")
        manifest = write_output_manifest(stage, "sdk", "sdk-core", "binary", "common",
            "0.8.0", {"fixture": "outputs/fixture"})
        receipt = write_receipt(self.root / "phase/planned.json", product="sdk",
            component="sdk-core", phase="binary", target="common", version="0.8.0",
            version_identity="0.8.0", outputs=manifest["outputs"], upstream=[],
            context={"producer": self.fixture.producer})
        plan = {key: receipt[key] for key in (
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        self.object = finalize_phase_object(stage_root=stage, phase_plan=plan,
            producer=self.fixture.producer, product_version="0.8.0",
            trust_domain="development", destination=self.root / "phase/shard")
        self.object_path = object_relative_path(receipt["buildKey"], self.object["receiptSha256"])
        self.object_bytes = (self.root / "phase/shard" / self.object_path).read_bytes()

    def _capture(self, *, object_bytes=None):
        source = self.fixture
        workflow, parent = _COLLECTORS[11]
        source.run.update(status="in_progress", conclusion=None)
        source.run["referenced_workflows"].append({
            "path": f"{source.producer['repository']}/.github/workflows/{workflow}.yml@{source.pin}",
            "sha": source.pin,
        })
        job = {**source.job, "name": f"product-validation / {parent} / sdk-collect-11",
            "started_at": "2026-09-13T10:00:00Z", "completed_at": "2026-09-13T10:02:00Z"}
        member = "runtime-state/reused-carrier/" + self.object_path
        raw = resume_fixture.archive({**source.contents,
            "runtime-state/reuse-wave-result.json": b"synthetic partial state\n",
            member: self.object_bytes if object_bytes is None else object_bytes})
        artifact = {**source.artifact,
            "name": f"codex-agent-sdk-wave-11-state-{source.producer['tree']}-attempt-3",
            "digest": sha256_bytes(raw), "size_in_bytes": len(raw),
            "created_at": "2026-09-13T10:01:00Z"}
        destination = self.root / "build/sdk-nested-capture"
        with patch.object(product_reuse, "api_json", side_effect=[source.run, source.commit, artifact]), \
                patch.object(product_reuse, "paginated_items", return_value=[job]), \
                patch.object(product_reuse, "download_artifact_to_file",
                    side_effect=lambda _artifact, _token, output, **_:
                        Path(output).write_bytes(raw)):
            transport = product_reuse.capture_runtime_resume_upload(source.plan_path,
                destination, artifact_id=artifact["id"], artifact_sha256=artifact["digest"],
                trusted_workflow_sha=source.pin, repository_root=self.root,
                environ=source.environment, token="synthetic-token", sdk_state_wave=11)
        return destination, transport

    def _state(self, captured):
        instance = self.instance
        record = {**{key: getattr(instance, key) for key in
            ("product", "component", "phase", "target")},
            "state": "retained", "source": None,
            "buildKey": self.object["receipt"]["buildKey"],
            "receiptSha256": self.object["receiptSha256"],
            "objectSha256": self.object["objectSha256"]}
        return SimpleNamespace(producer=self.fixture.producer,
            prior_by_instance={instance: record},
            sources={instance: captured / "original/runtime-state/reused-carrier" / self.object_path},
            expected_fixed={"versions": {"sdk": "0.8.0"}})

    def test_in_progress_nested_capture_stages_only_original_verified_object(self):
        captured, transport = self._capture()
        self.assertEqual("in_progress", transport["observed"][0]["run"]["status"])
        state = self._state(captured)
        destination = self.root / "partial-catalog"
        result = stage_partial_sdk_catalog(state, destination)
        index, _ = verify_signed_product_index(SignedProductIndex(
            destination / "product-index.json", destination / "product-index.sig"),
            destination / "public-key.pub")
        self.assertEqual(1, result["phaseCount"])
        self.assertEqual("development", index["trustDomain"])
        self.assertEqual("sdk-core", index["entries"][0]["component"])
        self.assertEqual(self.object_bytes,
            (destination / self.object_path).read_bytes())

    def test_tampered_original_object_never_publishes_catalog(self):
        captured, _ = self._capture(object_bytes=self.object_bytes + b"tampered")
        destination = self.root / "partial-catalog"
        with self.assertRaises(ValueError):
            stage_partial_sdk_catalog(self._state(captured), destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
