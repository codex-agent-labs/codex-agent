"""Incomplete SDK campaign recovery is a development cache, not release evidence."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.products.index import SignedProductIndex, verify_signed_product_index
from ci.products.inventory import sha256_bytes
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object, object_relative_path
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.sdk_campaign_partial_catalog_caller import (
    SDK_CAMPAIGN_INSTANCES as CALLER_SDK_INSTANCES,
    stage_partial_sdk_catalog,
)
from ci import product_reuse
from ci.tests.product_chain_support import write_receipt


class PartialSdkCampaignCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-partial-fixture-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.instances = sorted(SDK_CAMPAIGN_INSTANCES)[:2]
        cls.stable_instance = sorted(SDK_CAMPAIGN_INSTANCES)[2]
        cls.producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        cls.sources, cls.envelopes, cls.archives = {}, {}, {}
        stable_producer = {**cls.producer, "commit": "c" * 40, "tree": "d" * 40,
            "event": "push", "pullRequest": None}
        for position, instance in enumerate((*cls.instances, cls.stable_instance)):
            original_producer = stable_producer if instance == cls.stable_instance else cls.producer
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
                upstream=[], context={"producer": original_producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=original_producer, product_version="0.8.0",
                trust_domain="release" if instance == cls.stable_instance else "development",
                destination=directory / "shard")
            cls.sources[instance] = finalized["receiptBytes"]
            cls.envelopes[instance] = finalized
            cls.archives[instance] = directory / "shard" / finalized["objectPath"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _state(self, selected=None):
        selected = set(self.instances if selected is None else selected)
        records = {}
        archives = {}
        caller_id = type(next(iter(CALLER_SDK_INSTANCES)))
        for instance in SDK_CAMPAIGN_INSTANCES:
            identity = caller_id(instance.product, instance.component, instance.phase, instance.target)
            envelope = self.envelopes.get(instance)
            records[identity] = {
                "state": "reused" if instance == self.stable_instance and instance in selected
                         else "retained" if instance in selected else "build",
                "source": "stable" if instance == self.stable_instance and instance in selected else None,
                "buildKey": envelope["receipt"]["buildKey"] if envelope else "sha256:" + "0" * 64,
                "receiptSha256": envelope["receiptSha256"] if envelope else "sha256:" + "0" * 64,
                "objectSha256": envelope["objectSha256"] if envelope else "sha256:" + "0" * 64,
            }
            if instance in selected and envelope:
                archives[identity] = self.archives[instance]
        return SimpleNamespace(prior_by_instance=records,
            sources=archives,
            expected_fixed={"versions": {"sdk": "0.8.0"}}, producer=self.producer)

    def test_partial_catalog_preserves_only_original_completed_objects(self):
        state = self._state()
        with tempfile.TemporaryDirectory(prefix="sdk-partial-test-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            result = stage_partial_sdk_catalog(state, destination)
            index, _ = verify_signed_product_index(SignedProductIndex(
                destination / "product-index.json", destination / "product-index.sig"),
                destination / "public-key.pub")
            self.assertEqual(result["phaseCount"], 2)
            self.assertEqual(index["trustDomain"], "development")
            self.assertEqual({(entry["product"], entry["component"], entry["phase"], entry["target"])
                              for entry in index["entries"]},
                             {(instance.product, instance.component, instance.phase, instance.target)
                              for instance in self.instances})
            for instance in self.instances:
                envelope = self.envelopes[instance]
                source = self.sources[instance]
                copied = destination / object_relative_path(envelope["receipt"]["buildKey"],
                    sha256_bytes(source))
                self.assertEqual(copied.read_bytes(), self.archives[instance].read_bytes())
            with self.assertRaisesRegex(ValueError, "must not exist"):
                stage_partial_sdk_catalog(state, destination)

    def test_empty_complete_and_missing_original_reject_before_output(self):
        with tempfile.TemporaryDirectory(prefix="sdk-partial-negative-") as temporary:
            destination = Path(temporary) / "empty"
            with self.assertRaisesRegex(ValueError, "incomplete nonempty"):
                stage_partial_sdk_catalog(self._state(set()), destination)
            self.assertFalse(destination.exists())
            destination = Path(temporary) / "complete-without-originals"
            with self.assertRaisesRegex(ValueError, "lacks an original"):
                stage_partial_sdk_catalog(self._state(set(SDK_CAMPAIGN_INSTANCES)), destination)
            self.assertFalse(destination.exists())
            state = self._state()
            state.sources.pop(next(iter(state.sources)))
            destination = Path(temporary) / "missing"
            with self.assertRaisesRegex(ValueError, "lacks an original"):
                stage_partial_sdk_catalog(state, destination)
            self.assertFalse(destination.exists())

    def test_wrong_sdk_version_and_pr_context_reject(self):
        with tempfile.TemporaryDirectory(prefix="sdk-partial-context-") as temporary:
            state = self._state()
            state.expected_fixed["versions"]["sdk"] = "0.8.1"
            with self.assertRaisesRegex(ValueError, "phase/version"):
                stage_partial_sdk_catalog(state, Path(temporary) / "version")
            state = self._state()
            state.producer = {**self.producer, "pullRequest": 32}
            with self.assertRaisesRegex(ValueError, "producer context"):
                stage_partial_sdk_catalog(state, Path(temporary) / "pr")

    def test_tampered_original_object_rejects_before_publication(self):
        with tempfile.TemporaryDirectory(prefix="sdk-partial-object-") as temporary:
            state = self._state()
            identity = next(iter(state.sources))
            changed = Path(temporary).resolve() / "changed.zip"
            changed.write_bytes(state.sources[identity].read_bytes() + b"x")
            state.sources[identity] = changed
            destination = Path(temporary).resolve() / "catalog"
            with self.assertRaises(ValueError):
                stage_partial_sdk_catalog(state, destination)
            self.assertFalse(destination.exists())

    def test_mixed_stable_and_current_selection_indexes_only_current(self):
        state = self._state({self.instances[0], self.stable_instance})
        with tempfile.TemporaryDirectory(prefix="sdk-partial-mixed-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            result = stage_partial_sdk_catalog(state, destination)
            index, _ = verify_signed_product_index(SignedProductIndex(
                destination / "product-index.json", destination / "product-index.sig"),
                destination / "public-key.pub")
            self.assertEqual(result["phaseCount"], 1)
            self.assertEqual(index["entries"][0]["component"], self.instances[0].component)
            self.assertNotEqual(index["entries"][0]["buildKey"],
                                self.envelopes[self.stable_instance]["receipt"]["buildKey"])

    def test_existing_same_pr_lookup_rejects_failed_campaign_run(self):
        artifact = {"workflow_run": {"id": 3, "head_sha": self.producer["commit"]}}
        failed_run = {"id": 3, "status": "completed", "conclusion": "failure"}
        with patch.object(product_reuse, "api_json", return_value=failed_run):
            with self.assertRaisesRegex(ValueError, "allowed successful CI run"):
                product_reuse._same_pr_run(artifact, "https://api.github.com",
                    self.producer["repository"], self.producer["pullRequest"], "fixture-token",
                    self.producer["commit"], self.producer["tree"], expected_attempt=1)
