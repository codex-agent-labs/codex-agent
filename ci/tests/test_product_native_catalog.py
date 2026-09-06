"""Signed synthetic catalog consistency; never hosted or stable-release acceptance.

The promoted-main index exercises catalog comparison only. Actual restore below
uses the same-PR development catalog and preserves its original receipt trust.
"""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci.products.c_abi import STRICT_CONSUMERS
from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import (
    load_canonical_json_bytes, regular_file_inventory, sha256_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from ci.products.receipt import output_inventory_digest
from ci.products.restore import store_local_object
from ci.products.reuse import LookupSession, RemoteCatalog, _native_comparison_provider
from ci.products.sdk_runtime_content import verify_native_runtime_projection
from ci.products.signatures import sign_manifest
from ci.tests.product_chain_variants import _CONSUMER_ROOT, build_variants
from ci.tests.test_product_native_chain import build_chain


class NativeRuntimeCatalogTest(unittest.TestCase):
    target = "linux-x64"

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="native-catalog-fixtures-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chains = {name: build_chain(cls.root / name, run, include_bootstrap=cls.target == "macos-arm64")
                      for name, run in (("left", 171), ("right", 172))}
        cls.projections = {}
        for name, chain in cls.chains.items():
            contract = chain["contract"]
            cls.projections[name] = verify_contract_component_projection(
                contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
                contract["signature"], chain["context"]["public_key"],
                expected_trust_domain="development", expected_contract_version="0.2.0",
                required_components=("common", cls.target),
            )
        # A distinct, fully signed semantic fixture under the same validation key.
        sources = cls.root / "changed-consumers"
        snapshot_regular_tree(_CONSUMER_ROOT, sources)
        source = sources / min(STRICT_CONSUMERS)
        source.write_bytes(source.read_bytes() + b"\n/* changed catalog semantic fixture */\n")
        left = cls.chains["left"]
        with patch("ci.tests.product_chain_variants._CONSUMER_ROOT", sources):
            variants = build_variants(cls.root / "changed-variants", left["contract"], left["context"],
                                      include_bootstrap=cls.target == "macos-arm64")
        cls.chains["changed"] = {**left, "variants": variants}
        cls.projections["changed"] = cls.projections["left"]
        cls.objects, cls.receipts = {}, {}
        for name, chain in cls.chains.items():
            receipt_path = chain["variants"]["variant_phase_receipts"][cls.target]["validation"]
            cls.receipts[name] = receipt_path.read_bytes()
            cls.objects[name] = store_local_object(
                chain["variants"]["stages"] / cls.target / "validation", receipt_path,
                cls.root / f"cache-{name}",
            )["path"]
        cls.repository = left["context"]["producer"]["repository"]
        cls.release_signing = {**left["context"]["signing"], "trustDomain": "release", "keyId": "catalog-fixture"}
        cls.release_keys = cls.root / "release-keys"
        cls.release_keys.mkdir()
        (cls.release_keys / "catalog-fixture.pub").write_bytes(left["context"]["public_key"].read_bytes())
        cls.keyring = cls.root / "release-keyring.json"
        write_canonical_json(cls.keyring, {
            "schemaVersion": 1, "namespace": cls.release_signing["namespace"],
            "algorithm": cls.release_signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": "catalog-fixture", "fingerprint": cls.release_signing["fingerprint"]},
            "retiredKeys": [],
        })

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="native-catalog-test-")
        self.addCleanup(self.workspace.cleanup)
        self.work = Path(self.workspace.name).resolve()
        self.calls = []

    def proof(self, name):
        chain = self.chains[name]
        variants = chain["variants"]
        return verify_native_runtime_projection(
            target=self.target, runtime_stage_root=variants["stages"],
            phase_receipts=variants["variant_phase_receipts"][self.target],
            variant_payload=variants["variant_bundles"][self.target],
            attestation=variants["variant_attestations"][self.target],
            signature=variants["variant_attestation_signatures"][self.target],
            public_key=variants["variant_public_keys"][self.target],
            contract_projection=self.projections[name], contract_payload=chain["contract"]["payload"],
            required_trust_domain="development",
        )

    def callback(self, entry, verified_object_path):
        name = next(name for name, raw in self.receipts.items() if sha256_bytes(raw) == entry["receiptSha256"])
        self.assertEqual(self.objects[name], verified_object_path)
        self.calls.append(name)
        return self.proof(name)

    def catalog(self, name, source):
        chain = self.chains[name]
        receipt = load_canonical_json_bytes(self.receipts[name])
        artifact = receipt["outputs"][0]
        entry = {
            **{field: receipt[field] for field in ("buildKey", "product", "component", "phase", "target", "productVersion")},
            "coordinate": f"fixture:runtime-{self.target}",
            "outputInventoryDigest": output_inventory_digest(receipt["outputs"]), "outputs": receipt["outputs"],
            "artifactName": artifact["relativePath"], "artifactSha256": artifact["sha256"],
            "receiptSha256": sha256_bytes(self.receipts[name]),
        }
        release = source == "promoted-main"
        context = chain["context"]
        signing = self.release_signing if release else context["signing"]
        producer = {**context["producer"], "event": "push" if release else "pull_request",
                    "pullRequest": None if release else 31}
        index_context = ({"kind": "promoted-main", "commit": producer["commit"], "tree": producer["tree"],
                          "promotionRunId": producer["runId"], "promotionRunAttempt": 1} if release else
                         {"kind": "pull-request", "pullRequest": 31, "commit": producer["commit"],
                          "tree": producer["tree"], "runId": producer["runId"], "runAttempt": 1})
        manifest = self.work / f"{source}-{name}.json"
        write_canonical_json(manifest, {
            "schemaVersion": 1, "repository": self.repository, "context": index_context, "entries": [entry],
            "trustDomain": "release" if release else "development", "signing": signing, "producer": producer,
        })
        key = self.chains["left"]["context"]["private_key"] if release else context["private_key"]
        signature = sign_manifest(manifest, key, signing)
        return RemoteCatalog(
            manifest, signature, {receipt["buildKey"]: self.objects[name]},
            public_key=None if release else context["public_key"],
            keyring=self.keyring if release else None, keys_directory=self.release_keys if release else None,
        )

    def session(self, left, right, callback):
        return LookupSession(repository=self.repository, pull_request=31, promoted_main=left, same_pr=right,
                             native_runtime_projection=callback)

    def test_two_signed_raw_run_variants_preserve_original_objects_and_same_pr_receipt(self):
        left, right = (load_canonical_json_bytes(self.receipts[name]) for name in ("left", "right"))
        self.assertEqual(left["buildKey"], right["buildKey"])
        self.assertNotEqual(left["outputs"], right["outputs"])
        before = {name: regular_file_inventory(chain["variants"]["stages"] / self.target)
                  for name, chain in self.chains.items()}
        originals = {name: path.read_bytes() for name, path in self.objects.items()}
        session = self.session(self.catalog("left", "promoted-main"), self.catalog("right", "same-pr"), self.callback)
        result = session.lookup("same-pr", right)
        self.assertEqual(self.receipts["right"], result.envelope["receiptBytes"])
        self.assertEqual({"left", "right"}, set(self.calls))
        self.assertEqual(originals, {name: path.read_bytes() for name, path in self.objects.items()})
        self.assertEqual(before, {name: regular_file_inventory(chain["variants"]["stages"] / self.target)
                                 for name, chain in self.chains.items()})

    def test_missing_or_crosspaired_original_object_fails_before_its_callback(self):
        left, right = self.catalog("left", "promoted-main"), self.catalog("right", "same-pr")
        key = load_canonical_json_bytes(self.receipts["left"])["buildKey"]
        corrupt = self.work / "corrupt-object.zip"
        corrupt.write_bytes(b"not a product object")
        for supplied in (None, self.work / "missing.zip", self.objects["right"], corrupt):
            callback = Mock(wraps=self.callback)
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                self.session(replace(left, objects={key: supplied}), right, callback)
            callback.assert_not_called()

    def test_missing_forged_or_other_original_receipt_projection_cannot_normalize(self):
        left, right = self.catalog("left", "promoted-main"), self.catalog("right", "same-pr")
        with self.assertRaises(ValueError):
            self.session(left, right, None)
        for callback in (lambda *_: {}, lambda *_: self.proof("right")):
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                self.session(left, right, callback)

    def test_signed_semantic_change_retains_same_key_conflict_rejection(self):
        left, changed = (load_canonical_json_bytes(self.receipts[name]) for name in ("left", "changed"))
        self.assertEqual(left["buildKey"], changed["buildKey"])
        self.assertNotEqual(left["outputs"], changed["outputs"])
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.session(self.catalog("left", "promoted-main"), self.catalog("changed", "same-pr"), self.callback)
        self.assertEqual({"left", "changed"}, set(self.calls))

    def test_request_provider_authenticates_both_original_contract_and_runtime_closures(self):
        def relative(path):
            return Path(path).relative_to(self.root).as_posix()
        records = []
        for name in ("left", "right"):
            chain = self.chains[name]
            contract, variants = chain["contract"], chain["variants"]
            records.append({
                "receiptSha256": sha256_bytes(self.receipts[name]),
                "contractEvidence": {
                    "stageRoot": relative(contract["payload"].parent.parent),
                    "phaseReceipt": relative(contract["receipt"]), "attestation": relative(contract["attestation"]),
                    "attestationSignature": relative(contract["signature"]), "publicKey": relative(chain["context"]["public_key"]),
                    "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None,
                },
                "runtimeEvidence": {
                    "target": self.target, "stageRoot": relative(variants["stages"]),
                    "phaseReceipts": {phase: relative(path) for phase, path in variants["variant_phase_receipts"][self.target].items()},
                    "payload": relative(variants["variant_bundles"][self.target]),
                    "attestation": relative(variants["variant_attestations"][self.target]),
                    "attestationSignature": relative(variants["variant_attestation_signatures"][self.target]),
                    "publicKey": relative(variants["variant_public_keys"][self.target]), "keyring": None, "keysDirectory": None,
                },
            })
        records.sort(key=lambda record: record["receiptSha256"])
        left, right = self.catalog("left", "promoted-main"), self.catalog("right", "same-pr")
        provider = _native_comparison_provider(self.root, records)
        self.session(left, right, provider)
        from ci.products.index import _native_object_projection
        indexed = load_canonical_json_bytes(left.manifest.read_bytes())["entries"][0]
        object_provider = _native_object_projection(
            {sha256_bytes(raw): self.objects[name] for name, raw in self.receipts.items()}, provider)
        proof = object_provider(indexed)
        self.assertIs(proof, object_provider(indexed))
        with self.assertRaisesRegex(ValueError, "both authenticated objects"):
            _native_object_projection({}, provider)(indexed)
        with self.assertRaisesRegex(ValueError, "lacks original"):
            self.session(left, right, _native_comparison_provider(self.root, records[:1]))
        for invalid in (records * 2, list(reversed(records)), [{**records[0], "claimedDigest": "sha256:" + "a" * 64}],
                        [{**records[0], "runtimeEvidence": {**records[0]["runtimeEvidence"], "payload": "../escape.zip"}}]):
            with self.assertRaises(ValueError):
                _native_comparison_provider(self.root, invalid)


class NativeMacRuntimeCatalogTest(NativeRuntimeCatalogTest):
    target = "macos-arm64"


if __name__ == "__main__":
    unittest.main()
