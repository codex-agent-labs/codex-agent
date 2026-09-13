"""Exact family projection/transport controls; mocked election is not host proof."""

import unittest
from unittest.mock import patch

from ci.tests import test_sdk_workflow as fixture
from ci.tests import test_sdk_worker_collection as collection_fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import regular_file_inventory
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS, PhaseInstanceId


workflow = fixture.workflow


class SdkFamilyWorkflowTest(unittest.TestCase):
    setUp = fixture.SdkWorkflowTest.setUp

    def test_exact_native_and_metadata_matrices_exclude_all_other_instances(self):
        self.inspect.return_value = {"readyPlans": [
            {**workflow.product_reuse._identity_record(instance),
             "buildKey": "sha256:" + "a" * 64} for instance in PHASE_INSTANCE_IDS]}
        for family, expected in (
                ("native-package", {PhaseInstanceId("sdk", language, "package", "desktop") for language in NATIVE_BINDINGS}),
                ("javascript-metadata", {PhaseInstanceId("sdk", "javascript", "metadata", "node")})):
            value = workflow.matrix(self.plan, self.discovery, self.state, self.repository / family,
                family=family, repository_root=self.repository, environ={})
            self.assertEqual(expected, {workflow.product_reuse._identity(row) for row in value["include"]})
            self.assertTrue(all(row["runner"] == "ubuntu-24.04" for row in value["include"]))
        self.inspect.return_value = {"readyPlans": []}
        self.assertEqual({"include": []}, workflow.matrix(self.plan, self.discovery, self.state,
            self.repository / "empty", family="native-package", repository_root=self.repository, environ={}))

    def test_family_scope_rejects_unknown_or_binary_mix_before_election(self):
        for options in ({"family": "other"}, {"family": True}, {"family": "native-package", "ios_binary": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                workflow.matrix(self.plan, self.discovery, self.state, self.repository / "invalid", **options)
        self.inspect.assert_not_called()

    def test_family_collection_preserves_exact_scope_and_waits_for_all_results(self):
        source = self.repository / "original"
        for name in ("product-resume-inputs", "product-resume-state"):
            (source / name).mkdir(parents=True)
            (source / name / "retained").write_bytes(b"original\x00\xff")
        for family, wave, identity in (
                ("native-package", 4, PhaseInstanceId("sdk", "python", "package", "desktop")),
                ("javascript-metadata", 6, PhaseInstanceId("sdk", "javascript", "metadata", "node"))):
            for failure in (False, True):
                destination = self.repository / f"{family}-{failure}"
                row = {**workflow.product_reuse._identity_record(identity),
                    "result": "failure" if failure else "success", "shardDirectory": "rows/original/shard"}
                def advance(*args, **kwargs):
                    self.assertEqual(family, kwargs["sdk_family"])
                    self.assertEqual((identity,) if failure else (), kwargs["failed_instances"])
                    self.assertEqual([] if failure else [destination / "collection/rows/original/shard"], args[3])
                    args[4].mkdir(parents=True)
                    return {"synthetic": "advanced"}
                with patch.object(workflow.product_reuse, "collect_runtime_workers", return_value={"rows": [row]}) as collect, \
                        patch.object(workflow.product_reuse, "advance_products", side_effect=advance), \
                        patch.object(workflow, "matrix", return_value={"include": []}) as matrix:
                    workflow.collect(source, destination, self.repository / f"out-{family}-{failure}",
                        wave=wave, family=family, trusted_workflow_sha="a" * 40,
                        repository_root=self.repository, environ={}, token="synthetic")
                self.assertEqual(family, collect.call_args.kwargs["sdk_family"])
                self.assertEqual(not failure, matrix.called)
                self.assertEqual(b"original\x00\xff", (destination / "handoff/product-resume-state/retained").read_bytes())
            with self.assertRaises(ValueError):
                workflow.collect(source, self.repository / "wrong-wave", self.repository / "unused",
                    wave=1, family=family, trusted_workflow_sha="a" * 40, token="synthetic")


class SdkNativeFamilyCollectionTest(unittest.TestCase):
    setUp = collection_fixture.SdkWorkerCollectionTest.setUp
    names = collection_fixture.SdkWorkerCollectionTest.names
    state = collection_fixture.SdkWorkerCollectionTest.state
    official_api = collection_fixture.SdkWorkerCollectionTest.official_api

    def test_all_five_jobs_are_collected_and_successful_siblings_survive_bad_upload(self):
        adapter = collection_fixture.adapter
        ready, uploads, originals = {}, {}, {}
        for language in NATIVE_BINDINGS:
            identity = PhaseInstanceId("sdk", language, "package", "desktop")
            base = self.repository / language
            stage = base / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/package").write_bytes(language.encode())
            manifest = write_output_manifest(stage, "sdk", language, "package", "desktop", "0.3.0", {"evidence": "outputs"})
            receipt = write_receipt(base / "receipt.json", product="sdk", component=language,
                phase="package", target="desktop", version="0.3.0", version_identity="0.3.0",
                outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
            ready[identity] = {name: receipt[name] for name in PHASE_PLAN_KEYS}
            shard = base / "shard"
            finalized = finalize_phase_object(stage_root=stage, phase_plan=ready[identity], producer=self.producer,
                product_version="0.3.0", trust_domain="development", destination=shard)
            files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                     for row in regular_file_inventory(shard)}
            files["worker/gradle.log"] = b""
            uploads[identity] = archive(files if language != "python" else {"worker/gradle.log": b"failed fixture"})
            originals[identity] = finalized["receiptBytes"]
        unrelated = PhaseInstanceId("sdk", "javascript", "metadata", "node")
        elected = {**ready, unrelated: {**adapter._identity_record(unrelated), "buildKey": "sha256:" + "f" * 64}}
        destination = self.repository / "build/collection"
        with patch.object(adapter, "_verified_product_state", return_value=self.state(elected)), self.official_api(ready, uploads):
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=collection_fixture.PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_family="native-package")
        self.assertEqual(set(ready), {adapter._identity(row) for row in result["rows"]})
        for row in result["rows"]:
            self.assertEqual("failure" if row["component"] == "python" else "success", row["result"])
            if row["result"] == "success":
                self.assertEqual(originals[adapter._identity(row)],
                    (destination / row["shardDirectory"] / "phase-receipt.json").read_bytes())
