from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from ci.products import index as product_index
from ci.products import reuse as product_reuse
from ci.products.contract_attestation import build_contract_attestation
from ci.products.inventory import load_canonical_json, regular_file_inventory, write_canonical_json
from ci.products.reuse import RemoteCatalog, ReuseLookupError
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests import test_product_reuse as reuse_fixture
from ci.tests.test_product_reuse import (
    CONTRACT_BINARY, CONTRACT_METADATA, REPOSITORY, VERSIONS,
    all_inputs, contract_execution_chain, plan_for,
)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractReleasePolicyCaptureTest(unittest.TestCase):
    """Real synthetic signatures test policy capture, not hosted release authority."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="contract-release-policy-originals-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        cls.inputs = all_inputs(CONTRACT_METADATA)
        cls.resolved, cls.objects, payload, receipt, closure = contract_execution_chain(cls.root / "chain", cls.inputs)
        cls.policies = {}
        for name in ("a", "b"):
            root = cls.root / name
            private, public, development = generate_development_key(root / "generated")
            signing = {**development, "trustDomain": "release", "keyId": "release-test"}
            keys = root / "public-keys"
            keys.mkdir()
            (keys / "release-test.pub").write_bytes(public.read_bytes())
            keyring = root / "keyring.json"
            write_canonical_json(keyring, {
                "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
                "trustDomain": "release", "activeKey": {
                    "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
                }, "retiredKeys": [],
            })
            attestation_root = root / "attestation"
            # The normal producer invokes the full verifier before publishing either signed closure.
            build_contract_attestation(payload, receipt, signing, private, public, attestation_root,
                                       execution_closure=closure, keyring=keyring, keys_directory=keys)
            stem = f"codex-agent-contract-{VERSIONS['contract']}.attestation"
            cls.policies[name] = {
                "private": private, "public": public, "signing": signing, "keyring": keyring, "keys": keys,
                "attestation": attestation_root / f"{stem}.json", "signature": attestation_root / f"{stem}.sig",
            }
        policy = cls.policies["a"]
        fixture = reuse_fixture.ProductReuseTest()
        fixture.root, fixture.counter = cls.root, 0
        fixture.private_key, fixture.public_key = policy["private"], policy["public"]
        fixture.release_signing = policy["signing"]
        fixture.development_signing = {**policy["signing"], "trustDomain": "development"}
        fixture.release_keyring, fixture.release_keys = policy["keyring"], policy["keys"]
        template = fixture.catalog("promoted-main", [cls.objects[CONTRACT_METADATA]])
        template_index = load_canonical_json(template.manifest)
        sources = []
        for original, _ in cls.objects.values():
            kind = {"binary": "contract-execution", "package": "maven", "validation": "validation",
                    "metadata": "contract-bundle"}[original["receipt"]["phase"]]
            artifact = next(output["relativePath"] for output in original["receipt"]["outputs"] if output["kind"] == kind)
            source = product_index.IndexEntrySource(original["receiptBytes"], artifact)
            admission = product_index.release_attested_contract_admission(
                source, payload=payload, metadata_receipt=receipt, attestation=policy["attestation"],
                signature=policy["signature"], public_key=policy["public"], keyring=policy["keyring"],
                keys_directory=policy["keys"])
            sources.append(product_index.IndexEntrySource(source.receipt_bytes, source.artifact_path, admission))
        index = product_index.build_product_index(
            sources, repository=REPOSITORY, context=template_index["context"], trust_domain="release",
            signing=policy["signing"], producer=template_index["producer"], stable_history=None)
        manifest = cls.root / "admitted-product-index.json"
        write_canonical_json(manifest, index)
        signature = sign_manifest(manifest, policy["private"], policy["signing"])
        cls.catalog = RemoteCatalog(
            manifest, signature, {original["receipt"]["buildKey"]: path for original, path in cls.objects.values()},
            keyring=policy["keyring"], keys_directory=policy["keys"],
            contract_attestation=policy["attestation"], contract_attestation_signature=policy["signature"],
            contract_public_key=policy["public"])
        cls.original_inventory = regular_file_inventory(cls.root, allow_empty=True)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="contract-release-policy-live-")
        self.addCleanup(temporary.cleanup)
        self.live = Path(temporary.name).resolve()
        self.keys = self.live / "keys"
        self.keys.mkdir()
        self.keyring = self.live / "keyring.json"
        self.install_policy("a")

    def tearDown(self):
        self.assertEqual(self.original_inventory, regular_file_inventory(self.root, allow_empty=True))

    def install_policy(self, name):
        policy = self.policies[name]
        self.keyring.write_bytes(policy["keyring"].read_bytes())
        (self.keys / "release-test.pub").write_bytes(policy["public"].read_bytes())

    def session(self, attestation="a"):
        policy = self.policies[attestation]
        catalog = replace(self.catalog, keyring=self.keyring, keys_directory=self.keys,
                          contract_attestation=policy["attestation"], contract_attestation_signature=policy["signature"],
                          contract_public_key=policy["public"])
        return reuse_fixture.ProductReuseTest.session(promoted_main=catalog)

    def planned(self, instance):
        return plan_for(instance, self.inputs, self.resolved)

    def test_policy_a_catalog_preserves_every_original_contract_phase(self):
        session = self.session()
        for instance, (original, _) in self.objects.items():
            with self.subTest(phase=instance.phase):
                actual = session.lookup("promoted-main", self.planned(instance)).envelope
                self.assertEqual(original["receiptBytes"], actual["receiptBytes"])
                self.assertEqual(original["receiptSha256"], actual["receiptSha256"])
                self.assertEqual(original["receipt"], actual["receipt"])

    def test_live_policy_b_after_session_construction_cannot_authorize_a_catalog(self):
        for instance in (CONTRACT_METADATA, CONTRACT_BINARY):
            with self.subTest(phase=instance.phase):
                self.install_policy("a")
                session = self.session("b")
                self.install_policy("b")
                with self.assertRaises(ReuseLookupError):
                    session.lookup("promoted-main", self.planned(instance))

    def test_late_live_swap_cannot_change_policy_seen_by_actual_full_admission(self):
        actual_admission = product_reuse.release_attested_contract_admission
        for instance in (CONTRACT_METADATA, CONTRACT_BINARY):
            for attestation in ("a", "b"):
                with self.subTest(phase=instance.phase, attestation=attestation):
                    self.install_policy("a")
                    session = self.session(attestation)

                    def swap_after_index(*arguments, **keywords):
                        captured_keyring = Path(keywords["keyring"])
                        captured_keys = Path(keywords["keys_directory"])
                        self.assertNotEqual(self.keyring, captured_keyring)
                        self.assertNotEqual(self.keys, captured_keys)
                        self.assertEqual(self.policies["a"]["keyring"].read_bytes(), captured_keyring.read_bytes())
                        self.assertEqual(self.policies["a"]["public"].read_bytes(),
                                         (captured_keys / "release-test.pub").read_bytes())
                        self.install_policy("b")
                        return actual_admission(*arguments, **keywords)

                    with mock.patch.object(product_reuse, "release_attested_contract_admission",
                                           side_effect=swap_after_index) as admission:
                        if attestation == "b":
                            with self.assertRaises(ReuseLookupError):
                                session.lookup("promoted-main", self.planned(instance))
                        else:
                            actual = session.lookup("promoted-main", self.planned(instance)).envelope
                            self.assertEqual(self.objects[instance][0]["receiptBytes"], actual["receiptBytes"])
                    admission.assert_called_once()


if __name__ == "__main__":
    unittest.main()
