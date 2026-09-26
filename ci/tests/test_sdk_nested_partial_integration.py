"""Locally replay an in-progress nested SDK upload into a partial catalog.

Official HTTP and product bytes are synthetic; one case uses the real planner.
"""

from pathlib import Path
from contextlib import ExitStack
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_resume_capture as resume_fixture
from ci.products.index import SignedProductIndex, verify_signed_product_index
from ci.products.inventory import load_canonical_json, regular_file_inventory, sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object, object_relative_path
from ci.sdk_campaign_partial_catalog_caller import SDK_CAMPAIGN_INSTANCES, stage_partial_sdk_catalog
from ci.sdk_nested_wave_locator import _COLLECTORS
from ci.tests.product_chain_support import write_receipt
from ci.tests import test_product_contract_resume as contract_fixture


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


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class NestedSdkPlannerReplayTest(unittest.TestCase):
    """Reuse the real Contract handoff fixture for one SDK-core phase replay."""

    setUpClass = classmethod(contract_fixture.ContractProductResumeTest.setUpClass.__func__)
    setUp = contract_fixture.ContractProductResumeTest.setUp
    tearDown = contract_fixture.ContractProductResumeTest.tearDown
    resume = contract_fixture.ContractProductResumeTest.resume
    sdk = contract_fixture.adapter.PhaseInstanceId("sdk", "sdk-core", "binary", "common")

    @classmethod
    def control_seams(cls):
        # The fixture already authenticates Contract4; select only the SDK
        # binary successor, leaving the real product-state planner in place.
        stack = ExitStack()
        stack.enter_context(patch.object(contract_fixture.adapter, "_validate_plan",
            return_value=cls.plan))
        stack.enter_context(patch.object(contract_fixture.adapter, "_requested",
            return_value=(cls.sdk,)))
        return stack

    def test_nested_upload_replays_real_state_before_partial_catalog(self):
        adapter = contract_fixture.adapter
        resumed = self.resume()
        ready = load_canonical_json(resumed / "phase-plans/sdk-sdk-core-binary-common.json")
        stage = self.scratch / "sdk-stage"
        output = stage / "outputs/fixture"
        output.mkdir(parents=True)
        (output / "content.bin").write_bytes(b"synthetic SDK-core binary")
        write_output_manifest(stage, "sdk", "sdk-core", "binary", "common", "0.2.0",
            {"fixture": "outputs/fixture"})
        shard = self.scratch / "sdk-shard"
        contract_fixture.fixture.finalize_phase_object(stage_root=stage,
            phase_plan=ready, producer=self.producer, product_version="0.2.0",
            trust_domain="development", destination=shard)
        advanced = self.scratch / "advanced"
        with self.control_seams():
            result = adapter.advance_products(self.plan_path, resumed, None, [shard],
                advanced, self.scratch / "advance-output", repository_root=self.repository,
                environ=self.environment)
        self.assertTrue(result["fullReuse"])

        files = {"product-resume-inputs/plan/impact-plan.json": self.plan_path.read_bytes()}
        for source, prefix in ((resumed, "product-resume-state"), (advanced, "runtime-state")):
            files.update({f"{prefix}/{item['relativePath']}":
                (source / item["relativePath"]).read_bytes()
                for item in regular_file_inventory(source)})
        raw = resume_fixture.archive(files)
        pin = "c" * 40
        workflow, parent = _COLLECTORS[11]
        repository = self.producer["repository"]
        run = {"id": 7, "run_attempt": 2, "path": self.producer["workflowPath"],
            "event": "pull_request", "status": "in_progress", "conclusion": None,
            "head_sha": self.producer["commit"],
            "repository": {"full_name": repository, "fork": False},
            "head_repository": {"full_name": repository, "fork": False},
            "pull_requests": [{"number": 31, "base": {"sha": "1" * 40},
                               "head": {"sha": "2" * 40}}],
            "referenced_workflows": [{
                "path": f"{repository}/.github/workflows/{workflow}.yml@{pin}", "sha": pin,
            }]}
        commit = {"sha": self.producer["commit"],
            "tree": {"sha": self.producer["tree"]},
            "parents": [{"sha": "1" * 40}, {"sha": "2" * 40}]}
        job = {"id": 901, "run_id": 7, "head_sha": run["head_sha"],
            "name": f"product-validation / {parent} / sdk-collect-11",
            "status": "completed", "conclusion": "success",
            "started_at": "2026-09-13T10:00:00Z", "completed_at": "2026-09-13T10:02:00Z"}
        url = f"https://api.github.com/repos/{repository}/actions/artifacts/101"
        artifact = {"id": 101, "name": f"codex-agent-sdk-wave-11-state-{self.producer['tree']}-attempt-2",
            "digest": sha256_bytes(raw), "size_in_bytes": len(raw), "expired": False,
            "created_at": "2026-09-13T10:01:00Z",
            "archive_download_url": url + "/zip",
            "workflow_run": {"id": 7, "head_sha": run["head_sha"]}}
        captured = self.scratch / "nested-upload"
        with self.control_seams(), \
                patch.object(adapter, "api_json", side_effect=[run, commit, artifact]), \
                patch.object(adapter, "paginated_items", return_value=[job]), \
                patch.object(adapter, "download_artifact_to_file",
                    side_effect=lambda _artifact, _token, destination, **_:
                        Path(destination).write_bytes(raw)):
            transport = adapter.capture_runtime_resume_upload(self.plan_path, captured,
                artifact_id=101, artifact_sha256=artifact["digest"],
                trusted_workflow_sha=pin, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_state_wave=11)
        self.assertEqual("in_progress", transport["observed"][0]["run"]["status"])
        original = captured / "original"
        with self.control_seams():
            state = adapter._verified_product_state(
                original / "product-resume-inputs/plan/impact-plan.json",
                original / "product-resume-state", original / "runtime-state",
                self.repository, self.environment, None, sdk_original_workflow_sha=pin)
        self.assertEqual("retained", state.prior_by_instance[self.sdk]["state"])
        destination = self.scratch / "partial-catalog"
        summary = stage_partial_sdk_catalog(state, destination)
        self.assertEqual(1, summary["phaseCount"])
        index, _ = verify_signed_product_index(SignedProductIndex(
            destination / "product-index.json", destination / "product-index.sig"),
            destination / "public-key.pub")
        self.assertEqual("sdk-core", index["entries"][0]["component"])


if __name__ == "__main__":
    unittest.main()
