"""Signed index/original binding; synthetic signatures are not hosted release proof."""

from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest

from ci.products.index import IndexEntrySource, SignedProductIndex, build_product_index
from ci.products.inventory import sha256_bytes, write_canonical_json
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object
from ci.products.sdk_campaign_index import verify_signed_sdk_campaign_originals
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.product_chain_support import write_receipt


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkCampaignIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-campaign-index-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.repository = "owner/repository"
        cls.producer = {"repository": cls.repository,
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        cls.context = {"kind": "pull-request", "pullRequest": 31,
            "commit": cls.producer["commit"], "tree": cls.producer["tree"],
            "runId": 3, "runAttempt": 1}
        cls.sources, cls.envelopes, cls.archives, cls.stages = {}, {}, {}, {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            directory = cls.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            (output / "other.bin").write_bytes(b"another declared output")
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(directory / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": cls.producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            shard = directory / "shard"
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=cls.producer, product_version="0.8.0", trust_domain="development",
                destination=shard)
            cls.sources[instance] = IndexEntrySource(finalized["receiptBytes"],
                "outputs/fixture/content.bin")
            cls.envelopes[instance] = {name: finalized[name] for name in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            cls.archives[instance] = shard / finalized["objectPath"]
            cls.stages[instance] = stage
        cls.private_key, public_key, development = generate_development_key(cls.root / "keys")
        cls.signing = {**development, "trustDomain": "release", "keyId": "release-test"}
        cls.keys_directory = cls.root / "release-keys"
        cls.keys_directory.mkdir()
        shutil.copyfile(public_key, cls.keys_directory / "release-test.pub")
        cls.keyring = cls.root / "keyring.json"
        write_canonical_json(cls.keyring, {"schemaVersion": 1,
            "namespace": "codex-agent-product-v1", "algorithm": "ssh-ed25519",
            "trustDomain": "release", "activeKey": {"keyId": "release-test",
                "fingerprint": cls.signing["fingerprint"]}, "retiredKeys": []})
        index = build_product_index(cls.sources.values(), repository=cls.repository,
            context=cls.context, trust_domain="development", signing=development,
            producer=cls.producer, stable_history=None)
        cls.index = {**index, "trustDomain": "release", "signing": cls.signing}
        cls.source = cls._signed(cls.index, "index")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _signed(cls, index, name):
        manifest = cls.root / f"{name}.json"
        write_canonical_json(manifest, index)
        signature = sign_manifest(manifest, cls.private_key, cls.signing)
        return SignedProductIndex(manifest, signature)

    def _verify(self, source=None, **overrides):
        values = {"sources": self.sources, "envelopes": self.envelopes,
            "archives": self.archives, "stages": self.stages}
        values.update(overrides)
        return verify_signed_sdk_campaign_originals(source or self.source,
            repository=self.repository, context=self.context,
            keyring_path=self.keyring, keys_directory=self.keys_directory, **values)

    def test_signed_index_binds_all_original_receipts_and_objects(self):
        index, raw = self._verify()
        self.assertEqual(len(index["entries"]), 62)
        self.assertEqual(raw, self.source.manifest.read_bytes())

    def test_signed_wrong_original_or_context_fails(self):
        original = min(SDK_CAMPAIGN_INSTANCES)
        envelopes = deepcopy(self.envelopes)
        envelopes[original]["objectSha256"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError):
            self._verify(envelopes=envelopes)
        with self.assertRaisesRegex(ValueError, "wrong release context"):
            verify_signed_sdk_campaign_originals(self.source, repository=self.repository,
                context={**self.context, "runId": 4}, keyring_path=self.keyring,
                keys_directory=self.keys_directory, sources=self.sources,
                envelopes=self.envelopes, archives=self.archives, stages=self.stages)

    def test_signed_index_rejects_foreign_original_repository(self):
        instance = min(SDK_CAMPAIGN_INSTANCES)
        with tempfile.TemporaryDirectory(prefix="sdk-foreign-original-") as temporary:
            root = Path(temporary).resolve()
            original = self.envelopes[instance]["receipt"]
            foreign = {**self.producer, "repository": "other/repository"}
            plan = {name: original[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            finalized = finalize_phase_object(stage_root=self.stages[instance], phase_plan=plan,
                producer=foreign, product_version="0.8.0", trust_domain="development",
                destination=root / "shard")
            sources, envelopes, archives = dict(self.sources), dict(self.envelopes), dict(self.archives)
            sources[instance] = IndexEntrySource(finalized["receiptBytes"], sources[instance].artifact_path)
            envelopes[instance] = {name: finalized[name] for name in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            archives[instance] = root / "shard" / finalized["objectPath"]
            changed = deepcopy(self.index)
            entry = next(entry for entry in changed["entries"] if
                (entry["product"], entry["component"], entry["phase"], entry["target"]) ==
                (instance.product, instance.component, instance.phase, instance.target))
            entry["receiptSha256"] = sha256_bytes(finalized["receiptBytes"])
            with self.assertRaisesRegex(ValueError, "another repository"):
                self._verify(self._signed(changed, "foreign-repository"), sources=sources,
                    envelopes=envelopes, archives=archives)

    def test_signed_index_allows_push_but_rejects_other_campaign_original(self):
        instance = min(SDK_CAMPAIGN_INSTANCES)
        for event, pull_request in (("push", None), ("pull_request", 32),
                                    ("merge_group", None), ("workflow_dispatch", None),
                                    ("local", None)):
            with self.subTest(event=event), tempfile.TemporaryDirectory(
                    prefix="sdk-foreign-context-") as temporary:
                root = Path(temporary).resolve()
                original = self.envelopes[instance]["receipt"]
                producer = {**self.producer, "event": event, "pullRequest": pull_request}
                if event == "local":
                    producer.update(workflowPath=None, runId=None, runAttempt=None)
                plan = {name: original[name] for name in (
                    "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
                finalized = finalize_phase_object(stage_root=self.stages[instance], phase_plan=plan,
                    producer=producer, product_version="0.8.0", trust_domain="development",
                    destination=root / "shard")
                sources, envelopes, archives = dict(self.sources), dict(self.envelopes), dict(self.archives)
                sources[instance] = IndexEntrySource(finalized["receiptBytes"], sources[instance].artifact_path)
                envelopes[instance] = {name: finalized[name] for name in (
                    "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
                archives[instance] = root / "shard" / finalized["objectPath"]
                changed = deepcopy(self.index)
                entry = next(entry for entry in changed["entries"] if
                    (entry["product"], entry["component"], entry["phase"], entry["target"]) ==
                    (instance.product, instance.component, instance.phase, instance.target))
                entry["receiptSha256"] = sha256_bytes(finalized["receiptBytes"])
                signed = self._signed(changed, f"foreign-{event}")
                if event == "push":
                    self._verify(signed, sources=sources, envelopes=envelopes, archives=archives)
                    continue
                with self.assertRaisesRegex(ValueError, "another producer context"):
                    self._verify(signed, sources=sources,
                        envelopes=envelopes, archives=archives)

    def test_signed_index_entry_cannot_choose_a_different_original_artifact(self):
        changed = deepcopy(self.index)
        alternate = next(output for output in changed["entries"][0]["outputs"]
            if output["relativePath"] == "outputs/fixture/other.bin")
        changed["entries"][0]["artifactName"] = alternate["relativePath"]
        changed["entries"][0]["artifactSha256"] = alternate["sha256"]
        with self.assertRaisesRegex(ValueError, "selected original artifact"):
            self._verify(self._signed(changed, "different-artifact"))

    def test_signature_or_keyring_mismatch_fails(self):
        manifest = self.root / "tampered.json"
        manifest.write_bytes(self.source.manifest.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self._verify(SignedProductIndex(manifest, self.source.signature))


if __name__ == "__main__":
    unittest.main()
